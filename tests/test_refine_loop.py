"""Tests for F19 — agentic execute-and-refine per-block retry loop.

Covers:
- BlockExecutor.run returns None when executor returns no checks (no-op).
- BlockExecutor.run returns None on exception (soft-fail / no-op).
- BlockExecutor.run returns a checks dict when executor returns checks.
- _translate_blocks attempt loop: passes on attempt 1, retries on failure,
  keeps last code after 3 failures.

# SAS: test_refine_loop.py:1
"""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.worker.engine.block_executor import BlockExecutor
from src.worker.engine.models import (
    BlockType,
    GeneratedBlock,
    JobContext,
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


def _run(coro: object) -> object:
    return asyncio.get_event_loop().run_until_complete(coro)  # type: ignore[arg-type]


# ── BlockExecutor unit tests ──────────────────────────────────────────────────


class TestBlockExecutorNoRef:
    """BlockExecutor returns None when executor returns no checks."""

    def test_no_checks_returns_none(self) -> None:
        executor = BlockExecutor()
        backend = MagicMock()
        with patch("src.worker.engine.block_executor.RemoteReconciliationService") as mock_remote:
            mock_svc = AsyncMock()
            mock_svc.run = AsyncMock(return_value={"checks": []})
            mock_remote.return_value = mock_svc

            result = _run(executor.run("code", "test.sas:1", backend, data_dir=None))

        assert result is None

    def test_exception_returns_none(self) -> None:
        executor = BlockExecutor()
        backend = MagicMock()
        with patch("src.worker.engine.block_executor.RemoteReconciliationService") as mock_remote:
            mock_svc = AsyncMock()
            mock_svc.run = AsyncMock(side_effect=RuntimeError("boom"))
            mock_remote.return_value = mock_svc

            result = _run(executor.run("code", "test.sas:1", backend, data_dir=None))

        assert result is None


class TestBlockExecutorWithRef:
    """BlockExecutor returns checks dict when executor returns non-empty checks."""

    def test_returns_checks_dict_on_pass(self) -> None:
        executor = BlockExecutor()
        backend = MagicMock()
        checks_payload = {"checks": [{"name": "row_count", "status": "pass"}]}
        with patch("src.worker.engine.block_executor.RemoteReconciliationService") as mock_remote:
            mock_svc = AsyncMock()
            mock_svc.run = AsyncMock(return_value=checks_payload)
            mock_remote.return_value = mock_svc

            result = _run(executor.run("code", "test.sas:1", backend, data_dir="/uploads/abc"))

        result_dict = cast(dict[str, Any], result)
        assert result_dict is not None
        assert result_dict["checks"][0]["status"] == "pass"

    def test_returns_checks_dict_on_fail(self) -> None:
        executor = BlockExecutor()
        backend = MagicMock()
        checks_payload = {
            "checks": [{"name": "row_count", "status": "fail", "detail": "expected 10 got 5"}]
        }
        with patch("src.worker.engine.block_executor.RemoteReconciliationService") as mock_remote:
            mock_svc = AsyncMock()
            mock_svc.run = AsyncMock(return_value=checks_payload)
            mock_remote.return_value = mock_svc

            result = _run(executor.run("code", "test.sas:1", backend, data_dir=None))

        result_dict = cast(dict[str, Any], result)
        assert result_dict is not None
        assert result_dict["checks"][0]["status"] == "fail"


# ── Retry loop integration tests (mock _translate_blocks internals) ───────────


class TestRetryLoop:
    """Test the per-block retry logic in _translate_blocks via BlockExecutor mock."""

    @pytest.fixture()
    def block(self) -> SASBlock:
        return _make_block()

    @pytest.fixture()
    def context(self) -> JobContext:
        return _make_context()

    def test_passes_attempt_1_executor_called_once(
        self, block: SASBlock, context: JobContext
    ) -> None:
        """When executor passes on attempt 1, translate is called once."""
        gb = _make_gb("# attempt 1")
        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(return_value=gb)

        mock_executor = MagicMock(spec=BlockExecutor)
        # None = no checks = pass (no-op)
        mock_executor.run = AsyncMock(return_value=None)

        result = cast(
            list[GeneratedBlock],
            _run(_run_translate_blocks_stub([block], context, mock_translator, mock_executor)),
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

        fail1 = {"checks": [{"name": "row_count", "status": "fail", "detail": "row mismatch"}]}
        fail2 = {"checks": [{"name": "row_count", "status": "fail", "detail": "col mismatch"}]}
        mock_executor = MagicMock(spec=BlockExecutor)
        # attempt 1 fail, attempt 2 fail, attempt 3 -> None (no-op = pass)
        mock_executor.run = AsyncMock(side_effect=[fail1, fail2, None])

        result = cast(
            list[GeneratedBlock],
            _run(_run_translate_blocks_stub([block], context, mock_translator, mock_executor)),
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

        fail = {"checks": [{"name": "row_count", "status": "fail", "detail": "err"}]}
        mock_executor = MagicMock(spec=BlockExecutor)
        mock_executor.run = AsyncMock(side_effect=[fail, fail, fail])

        result = cast(
            list[GeneratedBlock],
            _run(_run_translate_blocks_stub([block], context, mock_translator, mock_executor)),
        )

        # No exception raised; last code kept
        assert len(result) == 1
        assert result[0].python_code == "# attempt 3"

    def test_ref_data_absent_no_retry(self, block: SASBlock, context: JobContext) -> None:
        """When executor returns None (no checks), only one translate call is made."""
        gb = _make_gb("# attempt 1")
        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(return_value=gb)

        mock_executor = MagicMock(spec=BlockExecutor)
        mock_executor.run = AsyncMock(return_value=None)

        result = cast(
            list[GeneratedBlock],
            _run(_run_translate_blocks_stub([block], context, mock_translator, mock_executor)),
        )

        assert mock_translator.translate.call_count == 1
        assert result[0].python_code == "# attempt 1"


class TestRetryErrorFeed:
    """Per-block retry feed: MANDATORY directive + prior-attempt code injection."""

    @pytest.fixture()
    def block(self) -> SASBlock:
        return _make_block()

    @pytest.fixture()
    def context(self) -> JobContext:
        return _make_context()

    def test_schema_parity_failure_injects_mandatory_and_prior_code(
        self, block: SASBlock, context: JobContext
    ) -> None:
        """A schema_parity failure surfaces a MANDATORY directive and the prior
        attempt's code (fenced python) into the next attempt's context."""
        gb1 = _make_gb("result = df.withColumn('rfstdtc', F.col('rfstdtc'))")
        gb2 = _make_gb("# attempt 2")
        seen_contexts: list[JobContext] = []

        async def _translate(_b: SASBlock, ctx: JobContext) -> GeneratedBlock:
            seen_contexts.append(ctx)
            return gb1 if len(seen_contexts) == 1 else gb2

        mock_translator = MagicMock()
        mock_translator.translate = AsyncMock(side_effect=_translate)

        fail = {
            "checks": [
                {
                    "name": "schema_parity",
                    "status": "fail",
                    "detail": "rfstdtc: ref=object, actual=numeric (int64)",
                }
            ]
        }
        mock_executor = MagicMock(spec=BlockExecutor)
        mock_executor.run = AsyncMock(side_effect=[fail, None])

        _run(_run_translate_blocks_stub([block], context, mock_translator, mock_executor))

        # Second attempt's context carries the new directive + prior code.
        assert len(seen_contexts) == 2
        retry_flags = seen_contexts[1].risk_flags
        # (a) MANDATORY directive present and imperative
        mandatory = [f for f in retry_flags if f.startswith("MANDATORY FIX (attempt 1)")]
        assert mandatory, retry_flags
        assert "cast('string')" in mandatory[0]
        # (b) prior attempt's code injected in a fenced python block
        prior = [f for f in retry_flags if "previous attempt for THIS block" in f]
        assert prior, retry_flags
        assert "```python" in prior[0]
        assert "rfstdtc" in prior[0]


# ── Stub that replicates the _translate_blocks F19 retry loop ────────────────


async def _run_translate_blocks_stub(
    blocks: list[SASBlock],
    context: JobContext,
    translator: MagicMock,
    executor: BlockExecutor,
    data_dir: str = "/uploads/test",
) -> list[GeneratedBlock]:
    """Mirror of the _translate_blocks F19 loop for isolated unit testing.

    Replicates the retry logic in JobOrchestrator._translate_blocks without
    instantiating the full orchestrator.

    Args:
        blocks: SAS blocks to iterate over.
        context: Job context.
        translator: Mock translator (already routed).
        executor: BlockExecutor instance (real or mock).
        data_dir: Data directory forwarded to executor.

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
                gb = None
                break

            recon_result = await executor.run(
                gb.python_code,
                block_id,
                backend,
                data_dir=data_dir,
            )

            if recon_result is None:
                # No reference data — treat as pass
                break

            checks: list[dict[str, Any]] = recon_result.get("checks", [])
            all_passed = all(c.get("status") == "pass" for c in checks)
            if all_passed:
                break

            if attempt < 3:
                failed_details = [
                    c.get("detail", c.get("name", "unknown"))
                    for c in checks
                    if c.get("status") != "pass"
                ]
                # Mirror of main.py: derive concrete cast hints from schema_parity.
                extra_hints: list[str] = []
                for check in checks:
                    if check.get("status") == "pass":
                        continue
                    name = check.get("name", "")
                    detail = check.get("detail", "")
                    if name == "schema_parity" and detail:
                        for col_part in detail.split(";"):
                            col_part = col_part.strip()
                            if "ref=" in col_part and "actual=" in col_part:
                                col_name = col_part.split(":")[0].strip()
                                ref_type = col_part.split("ref=")[1].split(",")[0].strip()
                                actual_type = col_part.split("actual=")[1].strip()
                                if ref_type == "object" and "numeric" in actual_type:
                                    extra_hints.append(
                                        f"column '{col_name}': ref is string/object"
                                        f" but output is {actual_type} —"
                                        f" add .withColumn('{col_name}',"
                                        f" F.col('{col_name}').cast('string'))"
                                    )
                error_summary = "; ".join(failed_details + extra_hints).replace("\n", " ")[:200]
                flag = f"recon_failure_attempt_{attempt}: {error_summary}"
                retry_flags: list[str] = [flag]
                # Change #1: high-salience MANDATORY directive when concrete hints exist.
                if extra_hints:
                    fix_instructions = "; ".join(extra_hints).replace("\n", " ")[:500]
                    retry_flags.append(
                        f"MANDATORY FIX (attempt {attempt}): your previous output was wrong."
                        f" The corrected code MUST contain these changes: {fix_instructions}."
                        f" Apply them exactly; do not omit them."
                    )
                # Change #3: feed the prior attempt's code back as a fenced python block.
                if gb is not None:
                    retry_flags.append(
                        "this is your previous attempt for THIS block; modify it minimally to"
                        " apply the MANDATORY FIX above and fix the issues; keep everything else"
                        f" identical:\n```python\n{gb.python_code}\n```"
                    )
                attempt_context = attempt_context.model_copy(
                    update={"risk_flags": [*attempt_context.risk_flags, *retry_flags]}
                )

        if gb is not None:
            generated.append(gb)

    return generated
