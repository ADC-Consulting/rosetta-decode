"""Unit tests for src/backend/api/runbook_templates.py (F35 S-E).

Covers remediation_outline and why_risky for all major block types, modifier
features, and boundary conditions. No async, no DB, no LLM calls.
"""

# SAS: tests/test_runbook_templates.py:1

from src.backend.api.runbook_templates import remediation_outline, why_risky

# ---------------------------------------------------------------------------
# remediation_outline tests
# ---------------------------------------------------------------------------


def test_proc_iml_returns_non_empty_steps() -> None:
    """PROC_IML block produces a non-empty step list."""
    steps = remediation_outline("PROC_IML", "manual", [])
    assert isinstance(steps, list)
    assert len(steps) > 0


def test_proc_iml_mentions_udf() -> None:
    """PROC_IML steps reference pandas_udf or mapInPandas."""
    steps = remediation_outline("PROC_IML", "manual", [])
    combined = " ".join(steps)
    assert "pandas_udf" in combined or "mapInPandas" in combined


def test_proc_sql_returns_non_empty_steps() -> None:
    """PROC_SQL block with translated_with_review produces non-empty steps."""
    steps = remediation_outline("PROC_SQL", "translated_with_review", [])
    assert len(steps) > 0


def test_proc_sql_mentions_spark_sql() -> None:
    """PROC_SQL steps reference Spark SQL or spark.sql."""
    steps = remediation_outline("PROC_SQL", "translated_with_review", [])
    combined = " ".join(steps)
    assert "Spark SQL" in combined or "spark.sql" in combined


def test_unknown_block_hits_fallback() -> None:
    """An unrecognised block_type falls back to generic steps (still non-empty)."""
    steps = remediation_outline("UNKNOWN_BLOCK", "manual", [])
    assert len(steps) > 0


def test_data_step_with_retain_includes_retain_step() -> None:
    """DATA_STEP + RETAIN detected feature appends a RETAIN-specific step."""
    steps = remediation_outline("DATA_STEP", "manual", ["RETAIN"])
    retain_steps = [s for s in steps if "RETAIN" in s or "window function" in s.lower()]
    assert len(retain_steps) > 0


def test_data_step_retain_in_generic_path_appends_modifier() -> None:
    """DATA_STEP with strategy='translate' still gets RETAIN modifier step via feature list."""
    # Even if strategy is not 'manual', the modifier step fires for 'RETAIN' feature
    steps_no_retain = remediation_outline("DATA_STEP", "translate", [])
    steps_with_retain = remediation_outline("DATA_STEP", "translate", ["RETAIN"])
    # The modifier step should add at least one extra step
    assert len(steps_with_retain) >= len(steps_no_retain)
    combined = " ".join(steps_with_retain)
    assert "RETAIN" in combined or "window function" in combined.lower()


def test_macro_with_call_symput_includes_symput_step() -> None:
    """MACRO block with CALL SYMPUT feature includes the SYMPUT-specific step."""
    steps = remediation_outline("MACRO", "manual", ["CALL SYMPUT"])
    combined = " ".join(steps)
    assert "CALL SYMPUT" in combined or "SYMPUT" in combined


def test_proc_macro_with_call_symputx() -> None:
    """PROC_MACRO block with CALL SYMPUTX also triggers the modifier step."""
    steps = remediation_outline("PROC_MACRO", "manual", ["CALL SYMPUTX"])
    combined = " ".join(steps)
    assert "SYMPUT" in combined


def test_unrecognized_block_type() -> None:
    """UNRECOGNIZED block type produces steps that mention reviewing SAS source."""
    steps = remediation_outline("UNRECOGNIZED", "manual", [])
    combined = " ".join(steps)
    assert "SAS" in combined or "source" in combined.lower()


def test_proc_format_returns_steps() -> None:
    """PROC_FORMAT produces steps that mention VALUE statements or dict/lookup."""
    steps = remediation_outline("PROC_FORMAT", "manual", [])
    combined = " ".join(steps)
    assert "VALUE" in combined or "dict" in combined or "lookup" in combined


def test_proc_tabulate_returns_steps() -> None:
    """PROC_TABULATE produces steps mentioning GROUP BY or pivot."""
    steps = remediation_outline("PROC_TABULATE", "manual", [])
    combined = " ".join(steps)
    assert "GROUP BY" in combined or "pivot" in combined.lower()


def test_modifier_dynamic_dataset_names() -> None:
    """'dynamic dataset names' feature appends the parametrize step."""
    steps = remediation_outline("DATA_STEP", "translate", ["dynamic dataset names"])
    combined = " ".join(steps)
    assert "Parametrize" in combined or "dataset names" in combined.lower()


def test_modifier_include() -> None:
    """%INCLUDE feature appends the inline step."""
    steps = remediation_outline("DATA_STEP", "translate", ["%INCLUDE"])
    combined = " ".join(steps)
    assert "%INCLUDE" in combined


def test_modifier_multiple_output_datasets() -> None:
    """'multiple output datasets' feature appends the split step."""
    steps = remediation_outline("DATA_STEP", "translate", ["multiple output datasets"])
    combined = " ".join(steps)
    assert "OUTPUT" in combined or "split" in combined.lower()


def test_no_duplicate_modifier_steps() -> None:
    """Each modifier step is added at most once even if triggered multiple times."""
    steps = remediation_outline("DATA_STEP", "manual", ["RETAIN", "RETAIN"])
    retain_steps = [s for s in steps if "window function" in s.lower()]
    assert len(retain_steps) <= 1


# ---------------------------------------------------------------------------
# why_risky tests
# ---------------------------------------------------------------------------


def test_why_risky_all_reasons_present() -> None:
    """All risk reasons are returned when all risk factors apply."""
    reasons = why_risky("manual", "very_low", "fail", 5, ["RETAIN"])
    # Manual
    assert any("manual" in r.lower() for r in reasons)
    # Low confidence
    assert any("confidence" in r.lower() for r in reasons)
    # Recon fail
    assert any("reconciliation" in r.lower() or "failed" in r.lower() for r in reasons)
    # Blast radius
    assert any("downstream" in r.lower() for r in reasons)
    # Detected features
    assert any("RETAIN" in r for r in reasons)


def test_why_risky_manual_strategy() -> None:
    """manual strategy always produces at least one reason."""
    reasons = why_risky("manual", "high", None, None, [])
    assert len(reasons) >= 1
    assert any("manual" in r.lower() for r in reasons)


def test_why_risky_low_confidence() -> None:
    """very_low effective band triggers the confidence reason."""
    reasons = why_risky("translate", "very_low", None, None, [])
    assert any("confidence" in r.lower() for r in reasons)


def test_why_risky_recon_fail() -> None:
    """recon_status='fail' triggers the reconciliation reason."""
    reasons = why_risky("translate", "high", "fail", 0, [])
    assert any("reconciliation" in r.lower() or "diverged" in r.lower() for r in reasons)


def test_why_risky_blast_radius_threshold() -> None:
    """blast_radius >= 3 triggers the downstream-blocks reason; < 3 does not."""
    reasons_above = why_risky("translate", "high", None, 3, [])
    reasons_below = why_risky("translate", "high", None, 2, [])
    assert any("downstream" in r.lower() for r in reasons_above)
    assert not any("downstream" in r.lower() for r in reasons_below)


def test_why_risky_translated_with_review() -> None:
    """translated_with_review strategy triggers the human review reason."""
    reasons = why_risky("translated_with_review", "high", "pass", 1, [])
    assert any("human review" in r.lower() or "flagged" in r.lower() for r in reasons)


def test_why_risky_no_risks_returns_minimal() -> None:
    """A healthy block with no risk factors returns empty or near-empty list."""
    reasons = why_risky("translated", "high", "pass", 1, [])
    # No risk factors apply — list should be empty
    assert reasons == []


def test_why_risky_detected_features_listed() -> None:
    """Detected features appear in the reason string."""
    reasons = why_risky("translate", "high", None, None, ["RETAIN", "ARRAY"])
    assert any("RETAIN" in r and "ARRAY" in r for r in reasons)
