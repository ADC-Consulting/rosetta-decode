"""Markdown renderer for the scoping summary report.

Produces the canonical markdown string used by the frontend's
"Copy as Markdown" action and stored in ScopingSummaryResponse.markdown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.backend.api.schemas import BomSummary, CostEstimate, TokenUsageStats


def render_scoping_markdown(
    job_name: str,
    llm_model: str,
    run_date: str,
    bom: BomSummary,
    token_usage: TokenUsageStats | None,
    cost: CostEstimate | None,
) -> str:
    """Render a structured markdown scoping report from summary data.

    Args:
        job_name: Human-readable job name shown in the report header.
        llm_model: LLM model identifier used for this job.
        run_date: ISO date string (e.g. "2026-06-12") for the report date.
        bom: Bill-of-materials summary from the scoping phase.
        token_usage: Aggregated token counters, or None for legacy/LLM-skipped jobs.
        cost: USD cost estimate, or None when model pricing is unknown.

    Returns:
        A complete markdown string ready for display or clipboard copy.
    """
    sections: list[str] = [
        _render_header(job_name, llm_model, run_date),
        _render_bom(bom),
        _render_risk(bom),
        _render_usage(token_usage, cost, llm_model),
    ]
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_header(job_name: str, llm_model: str, run_date: str) -> str:
    """Render the top-level title and metadata table.

    Args:
        job_name: Human-readable job name.
        llm_model: LLM model identifier.
        run_date: ISO date string.

    Returns:
        Markdown string for the header section.
    """
    lines = [
        f"# Migration Scoping Summary — {job_name}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Job | {job_name} |",
        f"| Model | {llm_model} |",
        f"| Date | {run_date} |",
    ]
    return "\n".join(lines)


def _render_bom(bom: BomSummary) -> str:
    """Render the Bill of Materials section.

    Args:
        bom: BomSummary instance containing block counts.

    Returns:
        Markdown string for the BOM section.
    """
    lines = [
        "## Bill of Materials",
        "",
        "| Category | Count |",
        "|---|---|",
        f"| Total blocks | {bom.total_blocks} |",
        f"| DATA steps | {bom.data_steps} |",
        f"| PROC steps | {bom.procs} |",
        f"| Macros | {bom.macros} |",
        f"| Untranslatable | {bom.untranslatable} |",
        f"| Human review required | {bom.human_review_required} |",
    ]

    if bom.proc_counts:
        lines += [
            "",
            "### PROC breakdown",
            "| PROC | Count |",
            "|---|---|",
        ]
        for proc, n in bom.proc_counts.items():
            lines.append(f"| {proc} | {n} |")

    return "\n".join(lines)


def _render_risk(bom: BomSummary) -> str:
    """Render the Risk & Review Effort section.

    Args:
        bom: BomSummary instance containing bucket and strategy counts.

    Returns:
        Markdown string for the risk section.
    """
    lines = [
        "## Risk & Review Effort",
        "",
        "### Risk distribution",
        "| Risk level | Blocks |",
        "|---|---|",
    ]
    for level, count in bom.risk_buckets.items():
        lines.append(f"| {level} | {count} |")

    lines += [
        "",
        "### Criticality distribution",
        "| Criticality | Blocks |",
        "|---|---|",
    ]
    for crit, count in bom.criticality_buckets.items():
        lines.append(f"| {crit} | {count} |")

    lines += [
        "",
        "### Migration strategy",
        "| Strategy | Blocks |",
        "|---|---|",
    ]
    for strategy, count in bom.strategy_counts.items():
        lines.append(f"| {strategy} | {count} |")

    return "\n".join(lines)


_BLOCK_DISPLAY_NAMES: dict[str, str] = {
    "data_step": "Data step",
    "proc_sql": "PROC SQL",
    "macro": "Macro",
    "generic_proc": "Generic PROC",
}


def _block_display_name(key: str) -> str:
    """Return a human-readable display name for a block type key.

    Args:
        key: Raw block type key from translation_by_block (e.g. ``"proc_sql"``).

    Returns:
        Display name (e.g. ``"PROC SQL"``), falling back to stripping a
        ``proc_`` prefix and title-casing.
    """
    if key in _BLOCK_DISPLAY_NAMES:
        return _BLOCK_DISPLAY_NAMES[key]
    if key.startswith("proc_"):
        return "PROC " + key[len("proc_") :].upper()
    return key.replace("_", " ").title()


_PHASE_DISPLAY_NAMES: dict[str, str] = {
    "parse_analysis": "Parse & Analysis",
    "migration_planning": "Migration Planning",
    "translation": "Translation",
    "assembly_recon": "Assembly & Reconciliation",
    "enrichment": "Enrichment",
}


def _phase_display_name(key: str) -> str:
    """Return a human-readable display name for a phase key.

    Args:
        key: Raw phase key from TokenUsageStats (e.g. "parse_analysis").

    Returns:
        Display name (e.g. "Parse & Analysis"), falling back to title-case.
    """
    return _PHASE_DISPLAY_NAMES.get(key, key.replace("_", " ").title())


def _render_usage(
    token_usage: TokenUsageStats | None,
    cost: CostEstimate | None,
    llm_model: str = "",
) -> str:
    """Render the LLM Usage & Estimated Cost section.

    Args:
        token_usage: Aggregated token counters, or None.
        cost: USD cost estimate, or None.
        llm_model: LLM model identifier used for this job.

    Returns:
        Markdown string for the usage section.
    """
    if token_usage is None:
        return (
            "## LLM Usage & Estimated Cost\n\n"
            "_Token usage not available for this job (legacy run or LLM skipped)._"
        )

    include_cost = cost is not None

    if include_cost:
        header = "| Phase | Input tokens | Output tokens | Est. cost (USD) |"
        divider = "|---|---|---|---|"
    else:
        header = "| Phase | Input tokens | Output tokens |"
        divider = "|---|---|---|"

    lines = [
        "## LLM Usage & Estimated Cost",
        "",
        header,
        divider,
    ]

    for phase_key, phase in token_usage.phases.items():
        if phase.input_tokens == 0 and phase.output_tokens == 0:
            continue
        display = _phase_display_name(phase_key)
        if include_cost:
            assert cost is not None  # narrowing for mypy
            phase_cost = cost.per_phase_usd.get(phase_key, 0.0)
            lines.append(
                f"| {display} | {phase.input_tokens} | {phase.output_tokens} | ${phase_cost:.4f} |"
            )
        else:
            lines.append(f"| {display} | {phase.input_tokens} | {phase.output_tokens} |")

        # Emit per-block sub-rows immediately after the translation phase row
        if phase_key == "translation" and token_usage.translation_by_block:
            input_price = (
                cost.prices.get("input_usd_per_mtok", 0.0) if include_cost and cost else 0.0
            )
            output_price = (
                cost.prices.get("output_usd_per_mtok", 0.0) if include_cost and cost else 0.0
            )
            for bt_key, bt_phase in token_usage.translation_by_block.items():
                sub_display = f"  {_block_display_name(bt_key)}"
                if include_cost:
                    bt_cost = (
                        bt_phase.input_tokens * input_price / 1_000_000
                        + bt_phase.output_tokens * output_price / 1_000_000
                    )
                    lines.append(
                        f"| {sub_display} | {bt_phase.input_tokens}"
                        f" | {bt_phase.output_tokens} | ${bt_cost:.4f} |"
                    )
                else:
                    lines.append(
                        f"| {sub_display} | {bt_phase.input_tokens} | {bt_phase.output_tokens} |"
                    )

    total = token_usage.total
    if include_cost:
        assert cost is not None  # narrowing for mypy
        lines.append(
            f"| **Total** | {total.input_tokens} | {total.output_tokens}"
            f" | **${cost.total_usd:.4f}** |"
        )
    else:
        lines.append(f"| **Total** | {total.input_tokens} | {total.output_tokens} |")

    if not include_cost:
        lines.append("")
        lines.append("_Cost estimate unavailable — model pricing unknown._")
    else:
        assert cost is not None  # narrowing for mypy
        input_price = cost.prices.get("input_usd_per_mtok", 0.0)
        output_price = cost.prices.get("output_usd_per_mtok", 0.0)
        lines.append("")
        lines.append(
            f"> Costs are approximate. Model: {llm_model}."
            f" Pricing: ${input_price}/M input, ${output_price}/M output."
        )

    return "\n".join(lines)
