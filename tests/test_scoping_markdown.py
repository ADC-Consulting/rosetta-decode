"""Unit tests for src/backend/core/scoping_markdown.py."""

import pytest
from src.backend.api.schemas import (
    BomSummary,
    CostEstimate,
    PhaseTokens,
    TokenUsageStats,
)
from src.backend.core.scoping_markdown import render_scoping_markdown

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_bom() -> BomSummary:
    """BomSummary with non-empty proc_counts and populated buckets."""
    return BomSummary(
        total_blocks=10,
        data_steps=4,
        procs=3,
        macros=2,
        untranslatable=1,
        human_review_required=2,
        proc_counts={"PROC SQL": 2, "PROC MEANS": 1},
        risk_buckets={"low": 5, "medium": 3, "high": 2},
        criticality_buckets={"critical": 2, "high": 1, "medium": 4, "low": 3},
        strategy_counts={"direct_translate": 6, "manual_review": 4},
    )


@pytest.fixture()
def bom_no_procs() -> BomSummary:
    """BomSummary with empty proc_counts."""
    return BomSummary(
        total_blocks=5,
        data_steps=5,
        procs=0,
        macros=0,
        untranslatable=0,
        human_review_required=0,
        proc_counts={},
        risk_buckets={"low": 5},
        criticality_buckets={"medium": 5},
        strategy_counts={"direct_translate": 5},
    )


@pytest.fixture()
def phase_tokens() -> PhaseTokens:
    """A single-phase token counter."""
    return PhaseTokens(
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=200,
        cache_write_tokens=50,
        requests=3,
    )


@pytest.fixture()
def token_usage(phase_tokens: PhaseTokens) -> TokenUsageStats:
    """TokenUsageStats with one phase and matching total."""
    total = PhaseTokens(
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=200,
        cache_write_tokens=50,
        requests=3,
    )
    return TokenUsageStats(phases={"parse": phase_tokens}, total=total)


@pytest.fixture()
def cost_estimate() -> CostEstimate:
    """A simple CostEstimate fixture."""
    return CostEstimate(
        total_usd=0.0075,
        per_phase_usd={"parse": 0.0075},
        prices={"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0},
        price_source="litellm",
    )


# ---------------------------------------------------------------------------
# 1. Header contains job name
# ---------------------------------------------------------------------------


def test_header_contains_job_name(minimal_bom: BomSummary) -> None:
    """Output must include the job name in the H1 heading."""
    result = render_scoping_markdown(
        job_name="my_job",
        llm_model="claude-sonnet-4-6",
        run_date="2026-06-12",
        bom=minimal_bom,
        token_usage=None,
        cost=None,
    )
    assert "# Migration Scoping Summary — my_job" in result
    assert "| Job | my_job |" in result
    assert "| Model | claude-sonnet-4-6 |" in result
    assert "| Date | 2026-06-12 |" in result


# ---------------------------------------------------------------------------
# 2. BOM table rows for total_blocks, data_steps, procs
# ---------------------------------------------------------------------------


def test_bom_table_rows(minimal_bom: BomSummary) -> None:
    """BOM section must contain rows for total blocks, DATA steps and PROC steps."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=None,
        cost=None,
    )
    assert "| Total blocks | 10 |" in result
    assert "| DATA steps | 4 |" in result
    assert "| PROC steps | 3 |" in result
    assert "| Macros | 2 |" in result
    assert "| Untranslatable | 1 |" in result
    assert "| Human review required | 2 |" in result


# ---------------------------------------------------------------------------
# 3. PROC breakdown present/absent based on proc_counts
# ---------------------------------------------------------------------------


def test_proc_breakdown_present(minimal_bom: BomSummary) -> None:
    """PROC breakdown sub-table must appear when proc_counts is non-empty."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=None,
        cost=None,
    )
    assert "### PROC breakdown" in result
    assert "| PROC SQL | 2 |" in result
    assert "| PROC MEANS | 1 |" in result


def test_proc_breakdown_absent(bom_no_procs: BomSummary) -> None:
    """PROC breakdown sub-table must NOT appear when proc_counts is empty."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=bom_no_procs,
        token_usage=None,
        cost=None,
    )
    assert "### PROC breakdown" not in result


# ---------------------------------------------------------------------------
# 4. Risk / criticality / strategy tables
# ---------------------------------------------------------------------------


def test_risk_criticality_strategy_tables(minimal_bom: BomSummary) -> None:
    """Risk, criticality, and strategy sub-tables must all be present."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=None,
        cost=None,
    )
    assert "### Risk distribution" in result
    assert "| low | 5 |" in result
    assert "| medium | 3 |" in result
    assert "| high | 2 |" in result

    assert "### Criticality distribution" in result
    assert "| critical | 2 |" in result

    assert "### Migration strategy" in result
    assert "| direct_translate | 6 |" in result
    assert "| manual_review | 4 |" in result


# ---------------------------------------------------------------------------
# 5. "not available" message when token_usage is None
# ---------------------------------------------------------------------------


def test_usage_not_available_message(minimal_bom: BomSummary) -> None:
    """When token_usage is None, a 'not available' notice must appear."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=None,
        cost=None,
    )
    assert "_Token usage not available for this job" in result


# ---------------------------------------------------------------------------
# 6. Usage table with correct total row when cost is None
# ---------------------------------------------------------------------------


def test_usage_table_no_cost(minimal_bom: BomSummary, token_usage: TokenUsageStats) -> None:
    """Usage table must render with phase rows and total row; cost column absent."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=token_usage,
        cost=None,
    )
    assert "## LLM Usage & Estimated Cost" in result
    assert "| Parse |" in result
    assert "| **Total** |" in result
    assert "Est. cost (USD)" not in result
    assert "_Cost estimate unavailable" in result


# ---------------------------------------------------------------------------
# 7. Cost column and total USD when both present
# ---------------------------------------------------------------------------


def test_usage_table_with_cost(
    minimal_bom: BomSummary,
    token_usage: TokenUsageStats,
    cost_estimate: CostEstimate,
) -> None:
    """Cost column must appear and total USD must be formatted to 4 dp."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=token_usage,
        cost=cost_estimate,
    )
    assert "Est. cost (USD)" in result
    assert "**$0.0075**" in result
    assert "$0.0075" in result  # per-phase cost


# ---------------------------------------------------------------------------
# 8. Footnote with price_source when cost is present
# ---------------------------------------------------------------------------


def test_price_source_footnote(
    minimal_bom: BomSummary,
    token_usage: TokenUsageStats,
    cost_estimate: CostEstimate,
) -> None:
    """A footnote naming the price_source must appear when cost is provided."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=token_usage,
        cost=cost_estimate,
    )
    assert "Pricing source: litellm" in result
    assert "$3.0/M input" in result
    assert "$15.0/M output" in result
    assert "Model: m." in result


# ---------------------------------------------------------------------------
# 9. No cache / requests columns in usage table
# ---------------------------------------------------------------------------


def test_usage_table_no_cache_or_requests_columns(
    minimal_bom: BomSummary, token_usage: TokenUsageStats
) -> None:
    """Cache read, cache write, and requests columns must not appear in output."""
    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=token_usage,
        cost=None,
    )
    assert "Cache read" not in result
    assert "Cache write" not in result
    assert "Requests" not in result


# ---------------------------------------------------------------------------
# 10. Pretty-printed phase names
# ---------------------------------------------------------------------------


def test_known_phase_keys_display_correctly(minimal_bom: BomSummary) -> None:
    """Known phase keys must map to their human-readable display names."""
    from src.backend.api.schemas import PhaseTokens, TokenUsageStats

    phases = {
        "parse_analysis": PhaseTokens(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            requests=1,
        ),
        "migration_planning": PhaseTokens(
            input_tokens=200,
            output_tokens=80,
            cache_read_tokens=0,
            cache_write_tokens=0,
            requests=1,
        ),
        "translation": PhaseTokens(
            input_tokens=300,
            output_tokens=120,
            cache_read_tokens=0,
            cache_write_tokens=0,
            requests=1,
        ),
        "assembly_recon": PhaseTokens(
            input_tokens=150,
            output_tokens=60,
            cache_read_tokens=0,
            cache_write_tokens=0,
            requests=1,
        ),
        "enrichment": PhaseTokens(
            input_tokens=50, output_tokens=20, cache_read_tokens=0, cache_write_tokens=0, requests=1
        ),
    }
    total = PhaseTokens(
        input_tokens=800, output_tokens=330, cache_read_tokens=0, cache_write_tokens=0, requests=5
    )
    usage = TokenUsageStats(phases=phases, total=total)

    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=usage,
        cost=None,
    )
    assert "| Parse & Analysis |" in result
    assert "| Migration Planning |" in result
    assert "| Translation |" in result
    assert "| Assembly & Reconciliation |" in result
    assert "| Enrichment |" in result


def test_unknown_phase_key_title_cases(minimal_bom: BomSummary) -> None:
    """An unrecognised phase key must be title-cased in the output table."""
    from src.backend.api.schemas import PhaseTokens, TokenUsageStats

    phase = PhaseTokens(
        input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0, requests=1
    )
    usage = TokenUsageStats(phases={"custom_step": phase}, total=phase)

    result = render_scoping_markdown(
        job_name="j",
        llm_model="m",
        run_date="2026-01-01",
        bom=minimal_bom,
        token_usage=usage,
        cost=None,
    )
    assert "| Custom Step |" in result
