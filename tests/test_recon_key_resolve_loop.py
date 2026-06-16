"""Worker wiring tests for the F15 in-process LLM join-key resolve loop.

Exercises ``JobOrchestrator._resolve_join_key_and_recompare`` end-to-end with a
mocked resolver agent (never a real LLM call) and real pandas frames, asserting
the AE swapped-pair case is resolved, the status flips to pass, the resolved key
lands in ``recon_checks``, the key is persisted via a whole-dict ``files`` merge,
and the graceful-skip / genuine-diff invariants hold.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from src.worker.engine.agents.recon_key_resolver import KeyResolution
from src.worker.validation.reconciliation import ReconConfig


def _make_orchestrator() -> object:
    from src.worker.main import JobOrchestrator

    with (
        patch("src.worker.main.AnalysisAgent"),
        patch("src.worker.main.DataStepAgent"),
        patch("src.worker.main.ProcAgent"),
        patch("src.worker.main.StubGenerator"),
        patch("src.worker.main.TranslationRouter"),
        patch("src.worker.main.CodeGenerator"),
        patch("src.worker.main.ReconciliationService"),
        patch("src.worker.main.FailureInterpreterAgent"),
        patch("src.worker.main.DocumentationAgent"),
        patch("src.worker.main.MacroExpander"),
        patch("src.worker.main.MigrationPlannerAgent"),
        patch("src.worker.main.LineageEnricherAgent"),
        patch("src.worker.main.PlainEnglishAgent"),
        patch("src.worker.main.ReconKeyResolverAgent"),
    ):
        return JobOrchestrator()


def _ae_block() -> MagicMock:
    block = MagicMock()
    block.raw_sas = "data ae; set sdtm.ae; run;"
    block.source_file = "ae.sas"
    block.start_line = 1
    return block


# Adverse-event data: subject 1 has two AEs on the same date — (subjid,aestdtc)
# is unique-but-wrong; only (subjid,aestdtc,aeterm) aligns rows correctly.
_AE_ROWS = [
    {"subjid": "1", "aestdtc": "2025-01-01", "aeterm": "headache", "sev": 1},
    {"subjid": "1", "aestdtc": "2025-01-01", "aeterm": "nausea", "sev": 2},
    {"subjid": "2", "aestdtc": "2025-02-01", "aeterm": "rash", "sev": 3},
]


def _ae_ref_df() -> pd.DataFrame:
    return pd.DataFrame(_AE_ROWS)


def _failed_rhd_check() -> dict[str, object]:
    return {
        "name": "row_hash_diff",
        "status": "fail",
        "detail": "join_keys=['subjid', 'aestdtc']; 2 differing cell-group(s)",
    }


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_ae_case_resolves_and_flips_to_pass() -> None:
    """(subjid,aestdtc) fails → agent proposes +aeterm → recompare passes; key persisted."""
    orch = _make_orchestrator()
    orch._recon_key_resolver.resolve = AsyncMock(  # type: ignore[attr-defined]
        return_value=KeyResolution(
            proposed_keys=["subjid", "aestdtc", "aeterm"], rationale="event-level key"
        )
    )
    # Capture the cross-run persistence call without a real DB.
    persisted: dict[str, object] = {}

    async def _capture(cfg: ReconConfig) -> None:
        persisted["join_keys"] = cfg.join_keys

    orch._persist_resolved_key = _capture  # type: ignore[attr-defined]

    backend = MagicMock()
    backend.read_csv.return_value = _ae_ref_df()
    checks: list[dict[str, object]] = [
        {"name": "schema_parity", "status": "pass"},
        {"name": "row_count", "status": "pass"},
        {"name": "aggregate_parity", "status": "pass"},
        _failed_rhd_check(),
    ]
    recon_result = {"checks": checks, "result_json": _AE_ROWS}

    resolved = await orch._resolve_join_key_and_recompare(  # type: ignore[attr-defined]
        checks=checks,
        recon_result=recon_result,
        recon_config=ReconConfig(),
        block=_ae_block(),
        ref_paths=("ref.csv", ""),
        backend=backend,
    )

    assert resolved is True
    rhd = next(c for c in checks if c["name"] == "row_hash_diff")
    assert rhd["status"] == "pass"
    assert rhd["resolved_join_key"] == ["subjid", "aestdtc", "aeterm"]
    assert persisted["join_keys"] == ["subjid", "aestdtc", "aeterm"]


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_missing_result_json_skips_gracefully() -> None:
    """No result_json → no LLM call, no mutation, returns False."""
    orch = _make_orchestrator()
    orch._recon_key_resolver.resolve = AsyncMock()  # type: ignore[attr-defined]
    checks: list[dict[str, object]] = [_failed_rhd_check()]

    resolved = await orch._resolve_join_key_and_recompare(  # type: ignore[attr-defined]
        checks=checks,
        recon_result={"checks": checks},  # no result_json
        recon_config=ReconConfig(),
        block=_ae_block(),
        ref_paths=("ref.csv", ""),
        backend=MagicMock(),
    )
    assert resolved is False
    orch._recon_key_resolver.resolve.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_row_cap_skips_gracefully() -> None:
    """Frames above the row cap are left for human review (no LLM call)."""
    from src.worker import main as worker_main

    orch = _make_orchestrator()
    orch._recon_key_resolver.resolve = AsyncMock()  # type: ignore[attr-defined]
    checks: list[dict[str, object]] = [_failed_rhd_check()]
    big = [{"subjid": str(i)} for i in range(worker_main._RESOLVE_ROW_CAP + 1)]

    resolved = await orch._resolve_join_key_and_recompare(  # type: ignore[attr-defined]
        checks=checks,
        recon_result={"checks": checks, "result_json": big},
        recon_config=ReconConfig(),
        block=_ae_block(),
        ref_paths=("ref.csv", ""),
        backend=MagicMock(),
    )
    assert resolved is False
    orch._recon_key_resolver.resolve.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_disabled_flag_skips() -> None:
    """resolve_key_with_llm=False short-circuits the loop."""
    orch = _make_orchestrator()
    orch._recon_key_resolver.resolve = AsyncMock()  # type: ignore[attr-defined]
    checks: list[dict[str, object]] = [_failed_rhd_check()]

    resolved = await orch._resolve_join_key_and_recompare(  # type: ignore[attr-defined]
        checks=checks,
        recon_result={"checks": checks, "result_json": _AE_ROWS},
        recon_config=ReconConfig(resolve_key_with_llm=False),
        block=_ae_block(),
        ref_paths=("ref.csv", ""),
        backend=MagicMock(),
    )
    assert resolved is False
    orch._recon_key_resolver.resolve.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_genuine_value_diff_never_resolved() -> None:
    """A true value difference is not 'resolved' by any valid key — stays failed."""
    orch = _make_orchestrator()
    # Even with a perfectly unique key, the values genuinely differ → still fails.
    orch._recon_key_resolver.resolve = AsyncMock(  # type: ignore[attr-defined]
        return_value=KeyResolution(proposed_keys=["subjid"], rationale="unique subject")
    )
    orch._persist_resolved_key = AsyncMock()  # type: ignore[attr-defined]

    ref = pd.DataFrame({"subjid": ["1", "2"], "sev": [1, 2]})
    actual_rows = [{"subjid": "1", "sev": 99}, {"subjid": "2", "sev": 2}]
    backend = MagicMock()
    backend.read_csv.return_value = ref
    checks: list[dict[str, object]] = [
        {"name": "schema_parity", "status": "pass"},
        _failed_rhd_check(),
    ]

    resolved = await orch._resolve_join_key_and_recompare(  # type: ignore[attr-defined]
        checks=checks,
        recon_result={"checks": checks, "result_json": actual_rows},
        recon_config=ReconConfig(max_key_attempts=2),
        block=_ae_block(),
        ref_paths=("ref.csv", ""),
        backend=backend,
    )
    assert resolved is False
    rhd = next(c for c in checks if c["name"] == "row_hash_diff")
    assert rhd["status"] == "fail"
    orch._persist_resolved_key.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.reconciliation
@pytest.mark.asyncio
async def test_invalid_proposal_is_rejected_and_fed_back() -> None:
    """A near-unique invalid proposal is rejected; loop exhausts → stays failed."""
    orch = _make_orchestrator()
    # Agent keeps proposing the unique-but-wrong (subjid,aestdtc) — never valid
    # (subject 1 has two AEs on one date), so validate_proposed_key rejects it.
    orch._recon_key_resolver.resolve = AsyncMock(  # type: ignore[attr-defined]
        return_value=KeyResolution(proposed_keys=["subjid", "aestdtc"], rationale="x")
    )
    orch._persist_resolved_key = AsyncMock()  # type: ignore[attr-defined]
    backend = MagicMock()
    backend.read_csv.return_value = _ae_ref_df()
    checks = [{"name": "schema_parity", "status": "pass"}, _failed_rhd_check()]

    resolved = await orch._resolve_join_key_and_recompare(  # type: ignore[attr-defined]
        checks=checks,
        recon_result={"checks": checks, "result_json": _AE_ROWS},
        recon_config=ReconConfig(max_key_attempts=2),
        block=_ae_block(),
        ref_paths=("ref.csv", ""),
        backend=backend,
    )
    assert resolved is False
    # The resolver was called the full attempt budget (proposal rejected each time).
    assert orch._recon_key_resolver.resolve.call_count == 2  # type: ignore[attr-defined]
