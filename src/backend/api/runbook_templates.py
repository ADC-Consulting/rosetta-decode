"""Rule-based remediation templates for the migration runbook (F35).

Pure, side-effect-free module. No LLM calls, no I/O.
All functions are deterministic: same inputs → same outputs.
"""

# SAS: src/backend/api/runbook_templates.py:1

_GENERIC_STEPS: list[str] = [
    "Review the original SAS source block and document its intent.",
    "Identify the expected output schema (column names, types, row count).",
    "Write a PySpark equivalent using DataFrame API or Spark SQL.",
    "Reconcile output against the original SAS results with a row-count and value check.",
]

_MODIFIER_STEPS: dict[str, str] = {
    "CALL SYMPUT": (
        "Resolve all runtime macro variable assignments manually"
        " — `CALL SYMPUT` has no PySpark equivalent."
    ),
    "CALL SYMPUTX": (
        "Resolve all runtime macro variable assignments manually"
        " — `CALL SYMPUT` has no PySpark equivalent."
    ),
    "dynamic dataset names": (
        "Parametrize dataset names via Python variables;"
        " confirm all call sites pass the correct value."
    ),
    "%INCLUDE": (
        "Inline the included file's logic before migration — `%INCLUDE` has no Spark equivalent."
    ),
    "RETAIN": ("Replace RETAIN variables with window function lag/cumulative patterns."),
    "multiple output datasets": (
        "Split the PySpark transformation into one DataFrame per OUTPUT destination."
    ),
}


def remediation_outline(
    block_type: str,
    strategy: str,
    detected_features: list[str],
) -> list[str]:
    """Return ordered remediation steps for a block.

    Args:
        block_type: SAS block type string (e.g. ``"PROC_SQL"``, ``"DATA_STEP"``).
        strategy: Migration strategy (e.g. ``"manual"``, ``"translated_with_review"``).
        detected_features: List of SAS-specific feature strings detected in the block.

    Returns:
        Ordered list of remediation step strings.
    """
    # SAS: src/backend/api/runbook_templates.py:50
    bt = block_type.upper()
    steps: list[str]

    if bt == "PROC_IML":
        steps = [
            "Identify all matrix operations and linear algebra routines in the IML block.",
            "Rewrite numeric computations as `pandas_udf` or `mapInPandas` UDFs.",
            "Validate numeric parity between SAS IML output and the PySpark result.",
            "Run a reconciliation check covering shape, dtype, and value tolerance.",
        ]
    elif bt == "PROC_SQL":
        steps = [
            "Extract the SQL statement(s) from the PROC SQL block.",
            "Verify window function, CASE expression, and subquery compatibility in Spark SQL.",
            "Rewrite or adapt any SAS-specific SQL extensions (e.g. MONOTONIC(), CALCULATED).",
            "Register source DataFrames as temporary views and execute via `spark.sql`.",
            "Reconcile result set schema and row count against the SAS output.",
        ]
    elif bt == "DATA_STEP" and (
        strategy == "manual" or any(f in detected_features for f in ("RETAIN", "ARRAY"))
    ):
        steps = [
            "Map each DATA step variable to a PySpark column or intermediate variable.",
            "Convert step-level iteration logic to explicit PySpark aggregation or window ops.",
            "Replace SAS ARRAY processing with Python list comprehensions or vectorised ops.",
            "Validate output row count and schema match against the original SAS dataset.",
        ]
    elif bt == "PROC_FORMAT":
        steps = [
            "Extract all VALUE statements from the PROC FORMAT block.",
            "Replicate each format as a Python dict (value→label) or a Delta lookup table.",
            "Replace SAS FORMAT= references in downstream code with the Python equivalent.",
            "Verify that all label mappings produce the same output as the SAS format.",
        ]
    elif bt in ("PROC_TABULATE", "PROC_REPORT"):
        steps = [
            "Identify the row/column/page dimensions and statistics requested.",
            "Rewrite as `spark.sql` GROUP BY with aggregation or a pandas pivot table.",
            "Ensure output column names and aggregation functions match the SAS report.",
            "Validate totals and subtotals against the original SAS output.",
        ]
    elif bt in ("MACRO", "PROC_MACRO"):
        steps = [
            "List all macro parameters and local/global macro variables used.",
            "Expand each macro call site manually by substituting parameter values.",
            "Check for `%SYMPUT`/`%SYSFUNC` dynamic variable assignments and resolve them.",
            "Convert the expanded logic to a Python function or PySpark transformation.",
            "Test the Python equivalent against each distinct call-site invocation.",
        ]
    elif bt in ("UNRECOGNIZED", "PROC_UNKNOWN"):
        steps = [
            "Review the original SAS source directly — the block type was not recognised.",
            "Extract the block's intent from comments, variable names, and output datasets.",
            "Write a PySpark equivalent from scratch based on the extracted intent.",
            "Add inline comments mapping each SAS construct to its Python counterpart.",
            "Reconcile output schema and values against any available SAS reference output.",
        ]
    else:
        steps = list(_GENERIC_STEPS)

    # Append modifier steps for any detected SAS-specific features.
    for feature, extra_step in _MODIFIER_STEPS.items():
        if feature in detected_features and extra_step not in steps:
            steps.append(extra_step)

    return steps


def why_risky(
    strategy: str,
    effective_band: str,
    recon_status: str | None,
    blast_radius: int | None,
    detected_features: list[str],
) -> list[str]:
    """Return human-readable reason strings for why this block needs attention.

    Args:
        strategy: Migration strategy string (e.g. ``"manual"``).
        effective_band: Effective confidence band after reconciliation adjustment.
        recon_status: Reconciliation status string or ``None`` if not run.
        blast_radius: Number of downstream blocks depending on this block, or ``None``.
        detected_features: List of SAS-specific feature strings detected in the block.

    Returns:
        List of human-readable risk reason strings. Empty if no risk factors apply.
    """
    # SAS: src/backend/api/runbook_templates.py:120
    reasons: list[str] = []

    if strategy == "manual":
        reasons.append("Marked for manual translation — no safe automated migration path.")
    if strategy == "translated_with_review":
        reasons.append("Auto-translated but flagged for human review.")
    if effective_band in ("very_low", "low"):
        reasons.append(f"Low translation confidence ({effective_band}).")
    if recon_status == "fail":
        reasons.append(
            "Reconciliation failed against reference data — output schema or values diverged."
        )
    if blast_radius is not None and blast_radius >= 3:
        reasons.append(f"{blast_radius} downstream blocks depend on this block's output.")
    if detected_features:
        # Macro variable refs (e.g. &in, &out) mean the block depends on runtime macro
        # context — surface that as a human-readable message rather than raw identifiers.
        macro_refs = [f for f in detected_features if f.startswith("&")]
        pattern_names = [f for f in detected_features if not f.startswith("&")]
        if macro_refs:
            reasons.append(
                "Block uses macro parameters as dataset/library names"
                f" ({', '.join(macro_refs)}) — context not available at translation time."
            )
        if pattern_names:
            reasons.append(f"SAS-specific patterns detected: {', '.join(pattern_names)}.")

    return reasons
