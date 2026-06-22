"""Markdown renderer for the F77 scoping / assessment report.

Produces a proposal-ready markdown string from a deterministic ``ScopingReport``
(no LLM). The structured report is stored verbatim per job; the run timestamp is
injected here at render time so the stored report stays byte-identical for a
given SAS input. Mirrors the structure/style of ``scoping_markdown.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.worker.engine.models import (
        BlockBreakdown,
        DataAssetInventory,
        EffortEstimate,
        FileInventoryItem,
        RiskFlag,
        ScopingReport,
    )


def render_scoping_report_markdown(
    report: ScopingReport,
    job_name: str,
    run_date: str,
) -> str:
    """Render a proposal-ready markdown assessment from a scoping report.

    Args:
        report: Deterministic, rule-based scoping report for the project.
        job_name: Human-readable job name shown in the report header.
        run_date: ISO date/timestamp string (e.g. "2026-06-19") for the report date.

    Returns:
        A complete markdown string ready for display or clipboard copy. Output is
        deterministic for a fixed ``report``, ``job_name`` and ``run_date``.
    """
    sections: list[str] = [
        _render_header(report, job_name, run_date),
        _render_file_inventory(report.file_inventory),
        _render_block_breakdown(report.block_breakdown),
        _render_risk_flags(report.risk_flags),
        _render_data_assets(report.data_assets),
        _render_effort(report.effort_estimate),
        _render_notes(report.notes),
    ]
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_header(report: ScopingReport, job_name: str, run_date: str) -> str:
    """Render the top-level title and project-totals metadata table.

    Args:
        report: Scoping report supplying project totals.
        job_name: Human-readable job name.
        run_date: ISO date/timestamp string.

    Returns:
        Markdown string for the header section.
    """
    lines = [
        f"# Migration Assessment — {job_name}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Job | {job_name} |",
        f"| Date | {run_date} |",
        f"| Source files | {report.total_files} |",
        f"| Total lines | {report.total_lines} |",
        f"| Total blocks | {report.total_blocks} |",
    ]
    return "\n".join(lines)


def _render_file_inventory(file_inventory: list[FileInventoryItem]) -> str:
    """Render the per-file inventory table.

    Args:
        file_inventory: Per-file summaries (rendered in stored order).

    Returns:
        Markdown string for the file inventory section.
    """
    lines = [
        "## File Inventory",
        "",
        "| File | Lines | Blocks | Complexity |",
        "|---|---|---|---|",
    ]
    if not file_inventory:
        lines.append("| _(none)_ | 0 | 0 | — |")
        return "\n".join(lines)
    for item in file_inventory:
        lines.append(
            f"| {item.source_file} | {item.line_count}"
            f" | {item.block_count} | {item.complexity_tier} |"
        )
    return "\n".join(lines)


def _render_block_breakdown(breakdown: BlockBreakdown) -> str:
    """Render the project-wide block breakdown table.

    Args:
        breakdown: Block counts and translation categories by type.

    Returns:
        Markdown string for the block breakdown section.
    """
    lines = [
        "## Block Breakdown",
        "",
        "| Block type | Count | Translation category |",
        "|---|---|---|",
    ]
    for block_type in sorted(breakdown.counts_by_type):
        count = breakdown.counts_by_type[block_type]
        category = breakdown.category_by_type.get(block_type, "—")
        lines.append(f"| {block_type} | {count} | {category} |")
    lines.append(f"| **Total** | **{breakdown.total_blocks}** | |")
    return "\n".join(lines)


def _render_risk_flags(risk_flags: list[RiskFlag]) -> str:
    """Render the risk-flags table.

    Args:
        risk_flags: Rule-based risk flags (rendered in stored order).

    Returns:
        Markdown string for the risk flags section.
    """
    lines = ["## Risk Flags", ""]
    if not risk_flags:
        lines.append("_No risk flags raised._")
        return "\n".join(lines)
    lines += [
        "| Kind | Severity | Count | Message |",
        "|---|---|---|---|",
    ]
    for flag in risk_flags:
        lines.append(f"| {flag.kind} | {flag.severity} | {flag.count} | {flag.message} |")
    return "\n".join(lines)


def _render_data_assets(assets: DataAssetInventory) -> str:
    """Render the data-asset inventory section.

    Args:
        assets: Inventory of libnames, datasets, and external paths.

    Returns:
        Markdown string for the data assets section.
    """
    lines = ["## Data Asset Inventory", ""]

    lines += ["### LIBNAMEs", "", "| Libref | Engine | Path |", "|---|---|---|"]
    if assets.libnames:
        for lib in assets.libnames:
            libref = lib.get("libref", "")
            engine = lib.get("engine", "")
            path = lib.get("path", "—")
            lines.append(f"| {libref} | {engine} | {path} |")
    else:
        lines.append("| _(none)_ | — | — |")

    lines += [
        "",
        "### Datasets",
        "",
        f"- Input datasets ({len(assets.input_datasets)}): "
        + (", ".join(assets.input_datasets) if assets.input_datasets else "_none_"),
        f"- Output datasets ({len(assets.output_datasets)}): "
        + (", ".join(assets.output_datasets) if assets.output_datasets else "_none_"),
    ]

    lines += ["", "### External file paths", ""]
    if assets.external_file_paths:
        lines += [f"- {path}" for path in assets.external_file_paths]
    else:
        lines.append("_No external file paths detected._")

    return "\n".join(lines)


def _render_effort(effort: EffortEstimate) -> str:
    """Render the provisional effort-estimate section.

    Args:
        effort: Provisional consultant-day effort estimate.

    Returns:
        Markdown string for the effort section, flagged provisional when
        ``effort.provisional`` is set.
    """
    lines = ["## Effort Estimate", ""]
    if effort.provisional:
        lines += [
            "> **PROVISIONAL effort estimate** — figures are uncalibrated and"
            " indicative only; they will change once rates are validated against"
            " real migration data.",
            "",
        ]
    lines += [
        "| Estimate | Consultant-days |",
        "|---|---|",
        f"| Low | {effort.low_days} |",
        f"| Mid | {effort.mid_days} |",
        f"| High | {effort.high_days} |",
        "",
        f"_Basis: {effort.basis}_",
    ]
    return "\n".join(lines)


def _render_notes(notes: list[str]) -> str:
    """Render the notes section (the "no silent caps" labels).

    Args:
        notes: Explicit labels for anything not statically detectable.

    Returns:
        Markdown string for the notes section.
    """
    lines = ["## Notes", ""]
    if not notes:
        lines.append("_No additional notes._")
        return "\n".join(lines)
    lines += [f"- {note}" for note in notes]
    return "\n".join(lines)
