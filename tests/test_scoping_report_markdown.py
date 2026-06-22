"""Unit tests for src/backend/core/scoping_report_markdown.py."""

import pytest
from src.backend.core.scoping_report_markdown import render_scoping_report_markdown
from src.worker.engine.models import (
    BlockBreakdown,
    DataAssetInventory,
    EffortEstimate,
    FileInventoryItem,
    RiskFlag,
    ScopingReport,
)


@pytest.fixture()
def sample_report() -> ScopingReport:
    """A populated ScopingReport covering every section."""
    return ScopingReport(
        total_files=2,
        total_lines=240,
        total_blocks=5,
        file_inventory=[
            FileInventoryItem(
                source_file="etl.sas",
                line_count=180,
                block_count=4,
                complexity_tier="moderate",
                block_type_counts={"DATA_STEP": 2, "PROC_SQL": 2},
            ),
            FileInventoryItem(
                source_file="report.sas",
                line_count=60,
                block_count=1,
                complexity_tier="simple",
                block_type_counts={"PROC_PRINT": 1},
            ),
        ],
        block_breakdown=BlockBreakdown(
            counts_by_type={"DATA_STEP": 2, "PROC_SQL": 2, "PROC_PRINT": 1},
            category_by_type={
                "DATA_STEP": "auto_translatable",
                "PROC_SQL": "needs_review",
                "PROC_PRINT": "auto_translatable",
            },
            total_blocks=5,
        ),
        risk_flags=[
            RiskFlag(
                kind="missing_macro",
                severity="high",
                message="Macro %CALC referenced but not defined.",
                detail=["%CALC"],
                count=1,
            ),
        ],
        data_assets=DataAssetInventory(
            libnames=[{"libref": "raw", "engine": "BASE", "path": "/data/raw"}],
            input_datasets=["raw.dm"],
            output_datasets=["work.out"],
            external_file_paths=["/data/in/source.csv"],
        ),
        effort_estimate=EffortEstimate(
            low_days=3.0,
            mid_days=5.0,
            high_days=8.0,
            provisional=True,
            basis="Rule-based from block counts and complexity tiers.",
        ),
        notes=["Macro expansion depth not statically detectable (no silent caps)."],
    )


def test_render_contains_all_sections(sample_report: ScopingReport) -> None:
    """Rendered markdown includes header + every section heading."""
    md = render_scoping_report_markdown(sample_report, "My Project", "2026-06-19")
    assert "# Migration Assessment — My Project" in md
    assert "| Date | 2026-06-19 |" in md
    assert "## File Inventory" in md
    assert "## Block Breakdown" in md
    assert "## Risk Flags" in md
    assert "## Data Asset Inventory" in md
    assert "## Effort Estimate" in md
    assert "## Notes" in md


def test_render_flags_provisional_effort(sample_report: ScopingReport) -> None:
    """The effort section carries the PROVISIONAL caveat when flagged."""
    md = render_scoping_report_markdown(sample_report, "My Project", "2026-06-19")
    assert "PROVISIONAL effort estimate" in md
    assert "| Mid | 5.0 |" in md


def test_render_includes_content(sample_report: ScopingReport) -> None:
    """File rows, risk flags, data assets, and notes appear in the output."""
    md = render_scoping_report_markdown(sample_report, "My Project", "2026-06-19")
    assert "etl.sas" in md
    assert "missing_macro" in md
    assert "/data/in/source.csv" in md
    assert "no silent caps" in md


def test_render_is_deterministic(sample_report: ScopingReport) -> None:
    """Same report + job_name + run_date yields byte-identical output."""
    md1 = render_scoping_report_markdown(sample_report, "My Project", "2026-06-19")
    md2 = render_scoping_report_markdown(sample_report, "My Project", "2026-06-19")
    assert md1 == md2


def test_render_empty_sections() -> None:
    """A minimal report with empty collections renders graceful placeholders."""
    report = ScopingReport(
        total_files=0,
        total_lines=0,
        total_blocks=0,
        block_breakdown=BlockBreakdown(counts_by_type={}, category_by_type={}, total_blocks=0),
        data_assets=DataAssetInventory(),
        effort_estimate=EffortEstimate(
            low_days=0.0, mid_days=0.0, high_days=0.0, provisional=True, basis="empty project"
        ),
    )
    md = render_scoping_report_markdown(report, "Empty", "2026-06-19")
    assert "_No risk flags raised._" in md
    assert "_No additional notes._" in md
    assert "## File Inventory" in md
