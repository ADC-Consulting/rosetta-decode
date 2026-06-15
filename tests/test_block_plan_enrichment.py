"""Unit tests for F56 post-run block-plan risk/rationale enrichment.

Covers :func:`_enrich_block_plan_post_run` (pure, rule-based, no LLM) and the
:func:`effective_migration_plan` accessor.
"""

from typing import Any

from src.backend.db.models import Job, effective_migration_plan
from src.worker.engine.models import (
    BlockPlan,
    BlockRisk,
    BlockType,
    GeneratedBlock,
    MigrationPlan,
    SASBlock,
    TranslationStrategy,
)
from src.worker.main import _enrich_block_plan_post_run

_SOURCE_FILE = "prog.sas"
_START_LINE = 10
_BLOCK_ID = f"{_SOURCE_FILE}:{_START_LINE}"


def _make_block_plan(
    *,
    block_id: str = _BLOCK_ID,
    source_file: str = _SOURCE_FILE,
    start_line: int = _START_LINE,
    strategy: TranslationStrategy = TranslationStrategy.TRANSLATED,
    risk: BlockRisk = BlockRisk.MEDIUM,
    rationale: str = "planner rationale",
    confidence_band: str = "unknown",
    detected_features: list[str] | None = None,
) -> BlockPlan:
    """Build a BlockPlan for enrichment tests.

    Args:
        block_id: Unique block identifier (defaults to the shared fixture id).
        source_file: Source SAS file name.
        start_line: 1-based start line.
        strategy: Translation strategy.
        risk: Planner-assigned risk.
        rationale: Planner rationale text.
        confidence_band: Planner confidence band.
        detected_features: Detected features (required non-empty for MANUAL).

    Returns:
        A constructed :class:`BlockPlan`.
    """
    return BlockPlan(
        block_id=block_id,
        source_file=source_file,
        start_line=start_line,
        block_type="DATA_STEP",
        strategy=strategy,
        risk=risk,
        rationale=rationale,
        estimated_effort="low",
        confidence_band=confidence_band,
        detected_features=detected_features or [],
    )


def _make_generated_block(
    *,
    source_file: str = _SOURCE_FILE,
    start_line: int = _START_LINE,
    confidence_band: str = "high",
    exec_ok: bool = True,
    recon_checks: list[dict[str, Any]] | None = None,
) -> GeneratedBlock:
    """Build a GeneratedBlock carrying post-run recon outcomes.

    Args:
        source_file: Source SAS file name (must pair with the BlockPlan).
        start_line: 1-based start line (must pair with the BlockPlan).
        confidence_band: Post-run confidence band.
        exec_ok: Whether execution/recon passed.
        recon_checks: Recon check list; None means recon did not run.

    Returns:
        A constructed :class:`GeneratedBlock`.
    """
    block = SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file=source_file,
        start_line=start_line,
        end_line=start_line + 1,
        raw_sas="data a; run;",
    )
    return GeneratedBlock(
        source_block=block,
        python_code="# code",
        confidence_band=confidence_band,
        exec_ok=exec_ok,
        recon_checks=recon_checks,
    )


def _make_plan(block_plans: list[BlockPlan], overall_risk: BlockRisk) -> MigrationPlan:
    """Build a MigrationPlan wrapping the given block plans."""
    return MigrationPlan(
        summary="summary",
        block_plans=block_plans,
        overall_risk=overall_risk,
        recommended_review_blocks=[],
        cross_file_dependencies=[],
    )


def _recon_pass() -> list[dict[str, Any]]:
    return [{"status": "pass"}]


def _recon_fail() -> list[dict[str, Any]]:
    return [{"status": "fail"}]


def test_recon_pass_high_confidence_sets_low_risk() -> None:
    """recon pass + confidence high → LOW."""
    plan = _make_plan([_make_block_plan(risk=BlockRisk.MEDIUM)], BlockRisk.MEDIUM)
    gb = _make_generated_block(confidence_band="high", exec_ok=True, recon_checks=_recon_pass())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.LOW


def test_recon_fail_sets_high_risk() -> None:
    """recon ran and failed → HIGH."""
    plan = _make_plan([_make_block_plan(risk=BlockRisk.LOW)], BlockRisk.LOW)
    gb = _make_generated_block(confidence_band="high", exec_ok=False, recon_checks=_recon_fail())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.HIGH


def test_manual_strategy_sets_high_risk() -> None:
    """strategy MANUAL → HIGH (detected_features required)."""
    plan = _make_plan(
        [
            _make_block_plan(
                strategy=TranslationStrategy.MANUAL,
                risk=BlockRisk.LOW,
                detected_features=["proc_iml"],
            )
        ],
        BlockRisk.LOW,
    )
    gb = _make_generated_block(confidence_band="high", exec_ok=True, recon_checks=_recon_pass())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.HIGH


def test_manual_beats_passing_recon() -> None:
    """MANUAL precedence wins even when recon passed with high confidence."""
    plan = _make_plan(
        [
            _make_block_plan(
                strategy=TranslationStrategy.MANUAL,
                risk=BlockRisk.MEDIUM,
                detected_features=["proc_iml"],
            )
        ],
        BlockRisk.MEDIUM,
    )
    # A passing high-confidence recon would otherwise force LOW.
    gb = _make_generated_block(confidence_band="high", exec_ok=True, recon_checks=_recon_pass())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.HIGH


def test_no_recon_low_confidence_sets_high_risk() -> None:
    """no recon + confidence low → HIGH."""
    plan = _make_plan([_make_block_plan(risk=BlockRisk.MEDIUM)], BlockRisk.MEDIUM)
    gb = _make_generated_block(confidence_band="low", exec_ok=True, recon_checks=None)

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.HIGH


def test_no_recon_very_low_confidence_sets_high_risk() -> None:
    """no recon + confidence very_low → HIGH."""
    plan = _make_plan([_make_block_plan(risk=BlockRisk.MEDIUM)], BlockRisk.MEDIUM)
    gb = _make_generated_block(confidence_band="very_low", exec_ok=True, recon_checks=None)

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.HIGH


def test_recon_pass_medium_confidence_leaves_risk_unchanged() -> None:
    """recon pass + confidence medium → risk UNCHANGED (no rule fires)."""
    plan = _make_plan([_make_block_plan(risk=BlockRisk.MEDIUM)], BlockRisk.MEDIUM)
    gb = _make_generated_block(confidence_band="medium", exec_ok=True, recon_checks=_recon_pass())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.MEDIUM


def test_recon_ran_pass_medium_confidence_unchanged_low_planner() -> None:
    """recon ran + pass + medium confidence keeps whatever the planner set."""
    plan = _make_plan([_make_block_plan(risk=BlockRisk.LOW)], BlockRisk.LOW)
    gb = _make_generated_block(confidence_band="medium", exec_ok=True, recon_checks=_recon_pass())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.LOW


def test_rationale_suffix_format() -> None:
    """Rationale gets the ` · post-run: recon=..., confidence=... → risk=...` suffix."""
    plan = _make_plan(
        [_make_block_plan(risk=BlockRisk.MEDIUM, rationale="base text")], BlockRisk.MEDIUM
    )
    gb = _make_generated_block(confidence_band="high", exec_ok=True, recon_checks=_recon_pass())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    rationale = enriched.block_plans[0].rationale
    assert rationale == "base text · post-run: recon=pass, confidence=high → risk=low"


def test_rationale_suffix_recon_none_when_no_recon() -> None:
    """recon=none label appears when recon did not run."""
    plan = _make_plan([_make_block_plan(risk=BlockRisk.MEDIUM)], BlockRisk.MEDIUM)
    gb = _make_generated_block(confidence_band="medium", exec_ok=True, recon_checks=None)

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert "recon=none" in enriched.block_plans[0].rationale


def test_idempotent_risk_and_single_suffix() -> None:
    """Applying twice yields identical risk and exactly one post-run segment."""
    plan = _make_plan([_make_block_plan(risk=BlockRisk.MEDIUM)], BlockRisk.MEDIUM)
    gb = _make_generated_block(confidence_band="high", exec_ok=True, recon_checks=_recon_pass())

    once = _enrich_block_plan_post_run(plan, [gb])
    twice = _enrich_block_plan_post_run(once, [gb])

    assert once.block_plans[0].risk == twice.block_plans[0].risk
    assert twice.block_plans[0].rationale.count(" · post-run:") == 1
    assert once.block_plans[0].rationale == twice.block_plans[0].rationale


def test_input_plan_not_mutated() -> None:
    """The input MigrationPlan is never mutated (deep copy returned)."""
    bp = _make_block_plan(risk=BlockRisk.MEDIUM, rationale="original")
    plan = _make_plan([bp], BlockRisk.MEDIUM)
    gb = _make_generated_block(confidence_band="high", exec_ok=True, recon_checks=_recon_pass())

    _enrich_block_plan_post_run(plan, [gb])

    assert plan.block_plans[0].risk == BlockRisk.MEDIUM
    assert plan.block_plans[0].rationale == "original"
    assert plan.overall_risk == BlockRisk.MEDIUM


def test_unmatched_block_plan_left_untouched() -> None:
    """A BlockPlan with no matching GeneratedBlock is untouched."""
    bp = _make_block_plan(block_id="other.sas:99", source_file="other.sas", start_line=99)
    plan = _make_plan([bp], BlockRisk.MEDIUM)
    # GeneratedBlock pairs with the default fixture id, not this block.
    gb = _make_generated_block(confidence_band="high", exec_ok=True, recon_checks=_recon_pass())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].risk == BlockRisk.MEDIUM
    assert enriched.block_plans[0].rationale == "planner rationale"
    assert " · post-run:" not in enriched.block_plans[0].rationale


def test_confidence_band_overwritten_with_post_run_band() -> None:
    """Enriched block confidence_band reflects the post-run band."""
    plan = _make_plan(
        [_make_block_plan(risk=BlockRisk.MEDIUM, confidence_band="unknown")], BlockRisk.MEDIUM
    )
    gb = _make_generated_block(confidence_band="medium", exec_ok=True, recon_checks=_recon_pass())

    enriched = _enrich_block_plan_post_run(plan, [gb])

    assert enriched.block_plans[0].confidence_band == "medium"


def test_overall_risk_recomputed_high_when_any_block_high() -> None:
    """overall_risk becomes HIGH when any enriched block is HIGH."""
    bp_low = _make_block_plan(
        block_id="prog.sas:10", source_file="prog.sas", start_line=10, risk=BlockRisk.MEDIUM
    )
    bp_high = _make_block_plan(
        block_id="prog.sas:20", source_file="prog.sas", start_line=20, risk=BlockRisk.LOW
    )
    plan = _make_plan([bp_low, bp_high], BlockRisk.LOW)
    gb_low = _make_generated_block(
        source_file="prog.sas", start_line=10, confidence_band="high", recon_checks=_recon_pass()
    )
    gb_high = _make_generated_block(
        source_file="prog.sas",
        start_line=20,
        confidence_band="high",
        exec_ok=False,
        recon_checks=_recon_fail(),
    )

    enriched = _enrich_block_plan_post_run(plan, [gb_low, gb_high])

    assert enriched.block_plans[1].risk == BlockRisk.HIGH
    assert enriched.overall_risk == BlockRisk.HIGH


def test_empty_block_plans_keeps_existing_overall_risk() -> None:
    """No block plans → overall_risk untouched."""
    plan = _make_plan([], BlockRisk.MEDIUM)

    enriched = _enrich_block_plan_post_run(plan, [])

    assert enriched.overall_risk == BlockRisk.MEDIUM


def test_effective_migration_plan_prefers_post_run() -> None:
    """effective_migration_plan returns the post-run plan when set."""
    pre = {"overall_risk": "medium"}
    post = {"overall_risk": "high"}
    job = Job(
        id="j1",
        status="proposed",
        input_hash="h",
        files={},
        migration_plan=pre,
        migration_plan_post_run=post,
    )

    assert effective_migration_plan(job) == post


def test_effective_migration_plan_falls_back_to_pre_run() -> None:
    """effective_migration_plan falls back to the pre-run plan when post-run is None."""
    pre = {"overall_risk": "medium"}
    job = Job(
        id="j2",
        status="proposed",
        input_hash="h",
        files={},
        migration_plan=pre,
        migration_plan_post_run=None,
    )

    assert effective_migration_plan(job) == pre
