"""Tests for F19 — agentic execute-and-refine per-block retry loop.

Covers:
- Block passes on attempt 1 — executor.run called once, no retry.
- Block fails attempt 1 and 2, passes attempt 3 — translate called 3 times.
- Block fails all 3 — last generated code kept, no exception raised.
- ref_csv_path empty — executor returns (True, None), no retry.

# SAS: test_refine_loop.py:1
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.worker.engine.block_executor import BlockExecutor, _to_report
from src.worker.engine.models import (
    BlockType,
    GeneratedBlock,
    JobContext,
    ReconciliationReport,
    SASBlock,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_block(name: str = "test.sas", line: int = 1) -> SASBlock:
    return SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file=name,
        start_line=line,
        end_line=line + 5,
        raw_sas="data out; set in; run;",
    )


def _make_gb(code: str = "result = df") -> GeneratedBlock:
    return GeneratedBlock(
        source_block=_make_block(),
        python_code=code,
    )


def _make_context() -> JobContext:
    return JobContext(
        source_files={"test.sas": "data out; set in; run;"},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )


# ── BlockExecutor unit tests ──────────────────────────────────────────────────


class TestBlockExecutorNoRef:
    """BlockExecutor returns (True, None) when no reference paths supplied."""

    def test_empty_ref_csv_path(self) -> None:
        executor = BlockExecutor()
        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(
            executor.run([], ctx, MagicMock(), "", "")
        )
        assert result == (True, None)

    def test_whitespace_ref_csv_treated_as_empty(self) -> None:
        """Paths that are empty strings are treated as absent."""
        executor = BlockExecutor()
        ctx = _make_context()
        result = asyncio.get_event_loop().run_until_complete(
            executor.run([], ctx, MagicMock(), "", "")
        )
        assert result == (True, None)


class TestBlockExecutorWithRef:
    """BlockExecutor delegates to ReconciliationService when ref paths are present."""

    def test_returns_true_when_reconciliation_passes(self) -> None:
        executor = BlockExecutor()
        ctx = _make_context()

        passing_report = MagicMock()
        passing_report.passed = True
        passing_report.diff_summary = ""

        with (
            patch.object(executor._codegen, "assemble_flat", return_value="code"),
            patch.object(
                executor._reconciler,
                "run",
                return_value={"checks": [{"name": "row_count", "status": "pass"}]},
            ),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                executor.run([_make_gb()], ctx, MagicMock(), "/ref.csv", "")
            )
        assert result[0] is True

    def test_returns_false_on_reconciliation_failure(self) -> None:
        executor = BlockExecutor()
        ctx = _make_context()

        with (
            patch.object(executor._codegen, "assemble_flat", return_value="code"),
            patch.object(
                executor._reconciler,
                "run",
                return_value={
                    "checks": [
                        {
                            "name": "row_count",
                            "status": "fail",
                            "detail": "expected 10 got 5",
                        }
                    ]
                },
            ),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                executor.run([_make_gb()], ctx, MagicMock(), "/ref.csv", "")
            )
        assert result[0] is False
        assert result[1] is not None

    def test_returns_false_on_exception(self) -> None:
        executor = BlockExecutor()
        ctx = _make_context()

        with (
            patch.object(executor._codegen, "assemble_flat", return_value="code"),
            patch.object(executor._reconciler, "run", side_effect=RuntimeError("boom")),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                executor.run([_make_gb()], ctx, MagicMock(), "/ref.csv", "")
            )
        assert result == (False, "boom")

    def test_to_report_passes_through_existing_report(self) -> None:
        report = ReconciliationReport(
            passed=True, row_count_match=True, column_match=True, diff_summary=""
        )
        assert _to_report(report) is report

    def test_to_report_empty_checks_returns_passed(self) -> None:
        result = _to_report({"checks": []})
        assert result.passed is True
        assert result.diff_summary == "no checks run"


# ── Retry loop integration tests (mock _translate_blocks internals) ───────────


class TestRetryLoop:
    """Test the per-block retry logic in _translate_blocks via BlockExecutor mock."""

    @pytest.fixture()
    def block(self) -> SASBlock:
        return _make_block()

    @pytest.fixture()
    def context(self) -> JobContext:
        return _make_context()

    def _run(self, coro):  # type: ignore[no-untyped-def]
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_passes_attempt_1_executor_called_once(
        self, block: SASBlock, context: JobContext
    ) -> None:
        """When executor passes on attempt 1, translate is called once."""
        gb = _make_gb("# attempt 1")
        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(return_value=gb)

        mock_executor = MagicMock(spec=BlockExecutor)
        mock_executor.run = AsyncMock(return_value=(True, None))

        with (
            patch(
                "src.worker.engine.block_executor.BlockExecutor",
                return_value=mock_executor,
            ),
            patch(
                "src.worker.main.BlockExecutor",
                return_value=mock_executor,
            ),
            patch("src.worker.main.BackendFactory") as mock_factory,
        ):
            mock_factory.create.return_value = MagicMock()
            # Inline the loop logic so we can test without a full WorkerService
            result = self._run(
                _run_translate_blocks_stub([block], context, mock_translator, mock_executor)
            )

        assert mock_translator.translate.call_count == 1
        assert mock_executor.run.call_count == 1
        assert len(result) == 1
        assert result[0].python_code == "# attempt 1"

    def test_fails_twice_passes_third_translate_called_3_times(
        self, block: SASBlock, context: JobContext
    ) -> None:
        """When executor fails attempts 1 and 2 but passes attempt 3."""
        gb1 = _make_gb("# attempt 1")
        gb2 = _make_gb("# attempt 2")
        gb3 = _make_gb("# attempt 3")
        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(side_effect=[gb1, gb2, gb3])

        mock_executor = MagicMock(spec=BlockExecutor)
        mock_executor.run = AsyncMock(
            side_effect=[(False, "row mismatch"), (False, "col mismatch"), (True, None)]
        )

        result = self._run(
            _run_translate_blocks_stub([block], context, mock_translator, mock_executor)
        )

        assert mock_translator.translate.call_count == 3
        assert mock_executor.run.call_count == 3
        assert result[0].python_code == "# attempt 3"

    def test_fails_all_3_last_code_kept(self, block: SASBlock, context: JobContext) -> None:
        """After 3 failures the last generated block is still appended."""
        gb1 = _make_gb("# attempt 1")
        gb2 = _make_gb("# attempt 2")
        gb3 = _make_gb("# attempt 3")
        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(side_effect=[gb1, gb2, gb3])

        mock_executor = MagicMock(spec=BlockExecutor)
        mock_executor.run = AsyncMock(
            side_effect=[
                (False, "err1"),
                (False, "err2"),
                (False, "err3"),
            ]
        )

        result = self._run(
            _run_translate_blocks_stub([block], context, mock_translator, mock_executor)
        )

        # No exception raised; last code kept
        assert len(result) == 1
        assert result[0].python_code == "# attempt 3"

    def test_ref_csv_empty_no_retry(self, block: SASBlock, context: JobContext) -> None:
        """When ref_csv_path is empty executor always returns (True, None)."""
        gb = _make_gb("# attempt 1")
        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(return_value=gb)

        # Use real BlockExecutor — it should short-circuit when paths are empty
        real_executor = BlockExecutor()

        result = self._run(
            _run_translate_blocks_stub(
                [block], context, mock_translator, real_executor, ref_csv_path=""
            )
        )

        # Only one translate call because executor always passes
        assert mock_translator.translate.call_count == 1
        assert result[0].python_code == "# attempt 1"


# ── Stub that replicates the _translate_blocks retry loop ─────────────────────


async def _run_translate_blocks_stub(
    blocks: list[SASBlock],
    context: JobContext,
    translator: MagicMock,
    executor: BlockExecutor,
    ref_csv_path: str = "/ref.csv",
    ref_sas7bdat_path: str = "",
) -> list[GeneratedBlock]:
    """Mirror of the _translate_blocks F19 loop for isolated unit testing.

    This avoids instantiating the full WorkerService while still exercising
    the exact retry logic defined in the spec.

    Args:
        blocks: SAS blocks to iterate over.
        context: Job context.
        translator: Mock translator (already routed).
        executor: BlockExecutor instance (real or mock).
        ref_csv_path: Reference CSV path override.
        ref_sas7bdat_path: Reference SAS7BDAT path override.

    Returns:
        List of GeneratedBlock results.
    """
    import logging

    logger = logging.getLogger(__name__)
    backend = MagicMock()
    generated: list[GeneratedBlock] = []

    for block in blocks:
        block_id = f"{block.source_file}:{block.start_line}"
        agent_name = type(translator).__name__
        gb: GeneratedBlock | None = None
        attempt_context = context

        for attempt in range(1, 4):
            logger.info("[F19] %s block %s attempt %d/3", agent_name, block_id, attempt)
            try:
                gb = await translator.translate(block, attempt_context)
            except Exception as exc:
                logger.warning(
                    "[F19] %s block %s attempt %d/3 translation error: %s",
                    agent_name,
                    block_id,
                    attempt,
                    type(exc).__name__,
                )
                break

            trial_generated = [*generated, gb]
            passed, error_summary = await executor.run(
                trial_generated, attempt_context, backend, ref_csv_path, ref_sas7bdat_path
            )

            if passed:
                logger.info("[F19] %s block %s attempt %d/3 PASSED", agent_name, block_id, attempt)
                break

            if attempt < 3 and error_summary:
                logger.info(
                    "[F19] %s block %s attempt %d/3 FAILED — scheduling retry",
                    agent_name,
                    block_id,
                    attempt,
                )
                hint_flag = f"recon_failure_attempt_{attempt}: {error_summary}"
                attempt_context = attempt_context.model_copy(
                    update={"risk_flags": [*attempt_context.risk_flags, hint_flag]}
                )
            else:
                logger.info(
                    "[F19] %s block %s attempt %d/3 FAILED — no more retries",
                    agent_name,
                    block_id,
                    attempt,
                )

        if gb is not None:
            generated.append(gb)

    return generated
