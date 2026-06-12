"""GenericProcAgent — translates any SAS PROC block into idiomatic Python.

Handles PROC IML, PROC FCMP, PROC MEANS/SUMMARY, PROC FREQ, PROC TRANSPOSE,
PROC IMPORT/EXPORT, PROC OPTMODEL, and any unfamiliar (PROC_UNKNOWN) blocks.
Default assumption: translation is always attempted; manual is only chosen when
detected_features is non-empty and the features have no Python equivalent.

# agent: GenericProcAgent
"""

# SAS: src/worker/engine/agents/generic_proc.py:1

import logging
import os as _os
import re as _re
import textwrap

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider
from src.worker.core.config import worker_settings
from src.worker.engine.agents.shared import (
    SHARED_TRANSLATION_RULES,
    normalise_output_var,
    normalise_output_var_in_code,
)
from src.worker.engine.models import GeneratedBlock, JobContext, SASBlock
from src.worker.engine.usage import record_usage

logger = logging.getLogger("src.worker.engine.agents.generic_proc")


def _fix_excel_spark_reads(python_code: str) -> str:
    """Replace spark.read...load(path.xlsx) with pandas read_excel + createDataFrame.

    Spark has no native xlsx/xls reader.  The LLM sometimes emits
    spark.read.format("xlsx").load(path) or spark.read.load(path) for Excel files,
    which always crashes.  This guard rewrites those calls to the pandas bridge pattern.
    """

    def _rewrite(m: _re.Match[str]) -> str:
        var_name = m.group(1).strip()
        path = m.group(2)
        logger.warning(
            "GenericProcAgent: rewriting Spark Excel read for '%s' → pandas bridge",
            path,
        )
        return f"import pandas as _pd\n{var_name} = spark.createDataFrame(_pd.read_excel({path}))"

    # Matches: <var> = spark.read.<anything>.load("<path.xlsx|xls>")
    #       or <var> = spark.read.load("<path.xlsx|xls>")
    return _re.sub(
        r"([A-Za-z_]\w*)\s*=\s*spark\.read(?:\.\w+)*\.load\((['\"][^'\"]+\.xlsx?['\"])\)",
        _rewrite,
        python_code,
    )


def _fix_workspace_paths(python_code: str) -> str:
    """Replace /workspace/data/<nested/path/file.ext> with /workspace/data/<file.ext>.

    LLMs sometimes copy the full relative path from the SAS DATAFILE= value instead of
    using the basename.  This guard normalises any nested path back to a flat basename.
    """

    def _basename_only(m: _re.Match[str]) -> str:
        full_path = m.group(1)
        basename = _os.path.basename(full_path)
        if basename == full_path:
            return m.group(0)
        logger.warning(
            "GenericProcAgent: correcting nested workspace path '%s' → '/workspace/data/%s'",
            full_path,
            basename,
        )
        return f"/workspace/data/{basename}"

    return _re.sub(r"/workspace/data/([^\s\"']+)", _basename_only, python_code)


# ── Output model ──────────────────────────────────────────────────────────────


class GenericProcResult(BaseModel):
    """Structured output from the GenericProcAgent LLM call."""

    python_code: str
    output_var: str | None = None
    strategy_used: str = "translated"
    confidence_score: float = 0.8
    confidence_band: str = "high"
    uncertainty_notes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    detected_features: list[str] = Field(default_factory=list)


# ── Error ─────────────────────────────────────────────────────────────────────


class GenericProcError(Exception):
    """Raised when the GenericProcAgent LLM call fails.

    Args:
        message: Human-readable description of the failure.
        cause: The underlying exception.
    """

    def __init__(self, message: str, cause: BaseException) -> None:
        """Initialise with human-readable message and underlying cause."""
        super().__init__(message)
        self.cause = cause


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent(
    """\
    # agent: GenericProcAgent

    You are a SAS-to-Python migration engineer targeting a modern Python 3.12 data platform.
    The target environment has: PySpark, pandas, numpy, pyarrow, scipy, scikit-learn, statsmodels,
    sqlalchemy, duckdb, matplotlib.
    DEFAULT: use PySpark for ALL data transformations. pandas is a LAST RESORT — only when the
    specific construct is impossible in PySpark. When falling back, add a comment:
      # pandas fallback: <reason PySpark cannot do this>
    scipy/statsmodels for complex statistics → wrap in @pandas_udf to keep Spark execution.
    The code must run in Databricks (PySpark native) or a local SparkSession (CLOUD=false).

    Your job is to translate ANY SAS PROC block into idiomatic Python.
    DEFAULT ASSUMPTION: translation is POSSIBLE. Only choose strategy="manual" when the
    block relies on features with NO reasonable Python equivalent — and you MUST list those
    features in detected_features. If detected_features would be empty, you CANNOT choose manual.

    ## Strategy selection (in priority order)

    1. "translated"
       Fully automated, high confidence expected. Use for PROC MEANS, PROC FREQ,
       PROC TRANSPOSE, PROC SORT (simple), straightforward PROC IML matrix arithmetic.

    2. "translated_with_review"
       Translated but a human should verify. Use when:
       - SAS date/time semantics differ (INTNX, INTCK, SAS date literals from 1 Jan 1960)
       - SAS STD = sample std (ddof=1) — differs from numpy default (ddof=0)
       - SAS missing-value propagation (special missings .A-.Z not representable in float64)
       - CALL SYMPUT/SYMPUTX with dynamic dataset names
       - PROC IML matrix arithmetic where storage order matters
         (SAS column-major vs NumPy row-major)
       - PROC FCMP function definitions
       - Complex PROC OPTMODEL that maps to scipy.optimize
       - PROC IMPORT / PROC EXPORT: emit a runnable spark.read / df.write call.
         CRITICAL path rule: ALWAYS use "/workspace/data/<basename>" where <basename> is the
         filename (with extension) from the SAS DATAFILE= value — strip any directory prefix or
         macro variable path. NEVER use the SAS macro-expanded path (e.g. &ROOT./foo.csv).
         Example: DATAFILE="&ROOT./data/customers.csv" → "/workspace/data/customers.csv"
         If uploaded data files are listed in the prompt, use the exact path shown there.
         CRITICAL output variable naming for PROC IMPORT: the OUT= option is `libname.table` or
         `libname_table` — ALWAYS use the TABLE STEM ONLY as the Python variable name.
         CORRECT: OUT=rawdir.customers → variable name `customers`
         WRONG:   OUT=rawdir.customers → variable name `rawdir_customers` or `rawdir.customers`
         The `output_var` JSON field MUST be the stem only (e.g. "customers", not "rawdir_customers").
         Example:
           # TODO: verify file format and schema
           customers = spark.read.csv("/workspace/data/customers.csv", header=True, inferSchema=True)  # SAS: <file>:<line>
           # pandas fallback: customers = pd.read_csv("/workspace/data/customers.csv")
           result = customers
         CRITICAL: spark.read.csv() / spark.read.parquet() / spark.read.json() MUST receive
         a string literal path, NEVER a DataFrame variable.
         If the input is already a DataFrame in scope, use it directly — do not pass it to spark.read.
         For .xlsx / .xls files Spark has no native reader — use pandas then convert:
           import pandas as _pd
           df_output = spark.createDataFrame(_pd.read_excel("/workspace/data/products.xlsx"))  # SAS: <file>:<line>
         NEVER call spark.read.format("xlsx").load() or spark.read.load() for Excel files.
       - PROC PRINT / PROC CONTENTS / PROC DATASETS: translate to Python display/inspection
         equivalent (e.g. df.head(), df.dtypes, df.describe(), print(df.columns)).

    3. "manual"
       ONLY when detected_features is non-empty AND features have no reasonable Python equivalent.
       Example: PROC OPTMODEL LP/NLP with a model structure so complex no scaffold is meaningful.
       NEVER emit manual for PROC IML, PROC FCMP, PROC MEANS, PROC FREQ, PROC TRANSPOSE,
       PROC IMPORT, PROC EXPORT, PROC PRINT, PROC CONTENTS, or PROC DATASETS.
       When using manual, ALWAYS provide: a suggested Python library, a short explanation, and
       at minimum a scaffold comment pointing the reviewer to the right tool.
    - Always include any imports your code needs at the top of your block (e.g. `from pyspark.sql import functions as F`). Do NOT assume pandas or any other library is pre-imported.
    - After computing your primary output DataFrame, set `result = <output_var>` as the final line of your code block. Example:
        result = transactions_clean
    - Set the `output_var` field in your JSON response to the STEM-ONLY name (no libname prefix, no dots, no underscored libname). Example: "output_var": "transactions_clean"
      WRONG: "output_var": "rawdir_transactions_clean", "output_var": "outdir_customers"
      CORRECT: "output_var": "transactions_clean", "output_var": "customers"

    ## PROC-specific translation guidance

    ### PROC MEANS / PROC SUMMARY
    Use PySpark df.groupBy().agg().
    - CLASS → groupBy columns
    - VAR → columns to aggregate
    - N → F.count(), MEAN → F.mean(), STD → F.stddev_samp() (sample std, matches SAS)
    - MIN/MAX/MEDIAN → F.min()/F.max()/F.percentile_approx(col, 0.5)
    - OUTPUT OUT= → assign result to the TABLE STEM of the OUT= name (strip libname prefix)
    Example:
      import pyspark.sql.functions as F
      result = df.groupBy("dept").agg(
          F.count("salary").alias("n"),
          F.mean("salary").alias("mean_salary"),
          F.stddev_samp("salary").alias("std_salary"),
      )

    ### PROC FREQ
    - TABLES a → df.groupBy("a").count()
    - TABLES a*b → df.groupBy("a", "b").count()
    - TABLES a*b / CHISQ → collect contingency table to pandas, then scipy:
        from pyspark.sql.functions import pandas_udf
        import scipy.stats as stats
        ct = df.groupBy("a", "b").count().toPandas().pivot("a", "b", "count").fillna(0)
        chi2, p, dof, _ = stats.chi2_contingency(ct.values)
    - OUT= → assign to the TABLE STEM of the OUT= name (strip libname prefix)

    ### PROC TRANSPOSE
    - ID → becomes new column names after pivoting
    - VAR → columns to transpose
    - BY → group-by columns (pivot within group)
    - OUT= → assign result to the TABLE STEM of the OUT= name (strip libname prefix)
    Use df.groupBy(BY).pivot(ID).agg(F.first(VAR)) for wide pivots.
    For unpivoting (wide→long): use df.select(BY_cols + F.explode/stack or melt via pandas_udf).

    ### PROC IML
    Use NumPy for matrix arithmetic.
    - SAS IML uses column-major (Fortran) storage; NumPy defaults to row-major (C).
      Transpose when storage order affects the result.
    - SAS STD() in IML = sample std (ddof=1). Use np.std(x, ddof=1) or x.std(ddof=1).
    - z-scores: from scipy.stats import zscore; z = zscore(x, ddof=1)
    - Matrix multiply: A * B in IML = A @ B in NumPy
    - CALL EIGEN(eigenval, eigenvec, A) → eigenval, eigenvec = np.linalg.eig(A)
    - CALL SVD(U, Q, V, A) → U, Q, V = np.linalg.svd(A, full_matrices=True)
    - INV(A) → np.linalg.inv(A)
    - DET(A) → np.linalg.det(A)
    - T(A) (transpose) → A.T
    Add assumption notes about column-major vs row-major when relevant.

    ### PROC FCMP
    Emit as a standalone Python function with a docstring noting the SAS original.
    Map SAS function signatures to Python def. Preserve argument order.
    Example:
      def my_func(x: float, y: float) -> float:
          \"\"\"Translated from SAS PROC FCMP function MY_FUNC.\"\"\"
          return x + y  # SAS: file.sas:line

    ### PROC OPTMODEL with solver call
    - If objective/constraints are linear → suggest scipy.optimize.linprog or PuLP:
        from scipy.optimize import linprog
        # TODO: encode objective coefficients and constraint matrix
        result = linprog(c, A_ub=A, b_ub=b, bounds=bounds, method="highs")
    - If non-linear → scipy.optimize.minimize
    - detected_features must list: solver_type, variable_count (if known), constraint_types
    - Only use strategy="manual" if the solver structure is so complex that no scaffold
      is meaningful — this should be rare.

    ### PROC UNKNOWN (unfamiliar PROC)
    Attempt translation using any domain knowledge you have.
    If truly unfamiliar, emit translate_with_review with your best-effort scaffold and
    uncertainty_notes explaining what you assumed. Never emit a silent TODO — always
    include real code that at minimum shows the intent.

    ## SAS semantic preservation rules

    - SAS date origin = 1 January 1960.
      PySpark: F.date_add(F.lit("1960-01-01").cast("date"), F.col(sas_date_col).cast("int"))
      pandas last resort: pd.Timestamp('1960-01-01') + pd.to_timedelta(sas_date_value, unit='D')
    - SAS std() = sample std (ddof=1). PySpark: F.stddev_samp(). NumPy: specify ddof=1.
    - SAS missing numeric = . → null in PySpark (F.isNull / F.when(...).otherwise(None)).
    - SAS special missings .A-.Z are not representable in float64.
      Note in uncertainty_notes when present.
    - Preserve SAS column names exactly, lowercased.
    - INPUT datasets are already-loaded Spark/pandas DataFrame variables. The exact variable name
      for each input is shown in the prompt as `→  variable name: <name>`. Use EXACTLY that name —
      do not derive it yourself. External source files use `libname_table` form (e.g. `rawdir_transactions`);
      inter-block datasets use stem-only (e.g. `customer_revenue_daily`).
      OUTPUT datasets must be CREATED by your code — do not reference them as if they already exist.
    - NEVER use libname-qualified names (e.g. `outdir.revenue_summary`, `work.tmp`) anywhere in the
      Python code body. SAS libnames do not exist in Python. Always use the TABLE STEM ONLY as the
      Python variable name for both inputs and outputs (e.g. `revenue_summary`, not `outdir.revenue_summary`).
    - NEVER pass a DataFrame variable to spark.read.csv/parquet/json — these accept only string
      paths. If data is already in a DataFrame, use it directly without re-reading.
    - Macro variables are pre-resolved; use their literal values directly.
    - Do NOT invent datasets or columns not present in the SAS source.
    - When uncertain, prefer translate_with_review with explicit assumptions
      over either silent translation or outright manual.

    ## Confidence score guidelines

    1.00-0.85  high      trivial/well-known pattern, reconciliation expected to pass
    0.84-0.65  medium    pattern applied but output may differ in edge cases
    0.64-0.40  low       ambiguous semantics; human review mandatory
    0.39-0.00  very_low  best-effort; significant manual work expected

    ## Output schema — ALL fields REQUIRED

    {
      "python_code": "<translated Python — never empty for translate/translate_with_review>",
      "strategy_used": "translated|translated_with_review|manual",
      "confidence_score": <float 0.0-1.0>,
      "confidence_band": "high|medium|low|very_low",
      "uncertainty_notes": ["<one sentence per uncertain construct>"],
      "assumptions": ["<SAS semantic quirk this translation relies on>"],
      "detected_features": ["<required non-empty when strategy_used=manual>"]
    }

    Rules:
    - Emit only the JSON object. No prose. No markdown fences.
    - Add # SAS: <source_file>:<line_number> after each logical section.
    - For low/medium confidence constructs, insert before relevant lines:
        # UNCERTAIN: <reason> — human review required
    - python_code MUST be non-empty for translated and translated_with_review.
    - For manual, python_code contains a justified stub with suggested library.
"""
    + SHARED_TRANSLATION_RULES
)


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(block: SASBlock, windowed: JobContext, all_blocks: list[SASBlock]) -> str:
    """Build the user prompt for a generic PROC translation.

    Args:
        block: The SAS block to translate.
        windowed: A windowed JobContext scoped to this block.
        all_blocks: All SAS blocks in the job (used to resolve inter-block variable names).

    Returns:
        A formatted prompt string for the LLM.
    """
    lines: list[str] = []

    lines.append(f"## PROC type: {block.block_type}")
    # Warn when the SAS source contains a different PROC than the classified type
    # (parser heuristics can misclassify — trust the raw SAS, not the label)
    import re as _re_detect

    first_proc_match = _re_detect.search(r"\bPROC\s+(\w+)", block.raw_sas, _re_detect.IGNORECASE)
    if first_proc_match:
        detected_proc = first_proc_match.group(1).upper()
        classified = block.block_type.name.replace("PROC_", "")
        if detected_proc != classified:
            lines.append(
                f"**NOTE: Block is classified as {block.block_type} but the SAS source contains"
                f" PROC {detected_proc}. Translate based on the ACTUAL SAS content below, not"
                f" the classification label.**"
            )
    lines.append("")

    lines.append("## Macro variable context")
    for macro in windowed.resolved_macros:
        lines.append(f'- {macro.name} = "{macro.raw_value}"  ({macro.source_file}:{macro.line})')
    if not windowed.resolved_macros:
        lines.append("  (none)")

    block_output_stems: dict[str, str] = {}
    for b in all_blocks:
        for ds in b.output_datasets:
            stem = ds.lower().split(".")[-1]
            block_output_stems[ds.lower()] = stem
            block_output_stems[ds.lower().replace(".", "_")] = stem

    # Datasets this block itself produces — must NOT appear in "Upstream datasets"
    this_block_outputs: set[str] = {ds.lower() for ds in block.output_datasets}
    this_block_outputs |= {ds.lower().replace(".", "_") for ds in block.output_datasets}

    lines.append("")
    lines.append("## Upstream datasets (dependency order)")
    upstream = [ds for ds in windowed.dependency_order if ds.lower() not in this_block_outputs]
    for i, ds in enumerate(upstream):
        ds_lower = ds.lower()
        if ds_lower in block_output_stems:
            var_name = block_output_stems[ds_lower]
        else:
            var_name = ds_lower.replace(".", "_")
        lines.append(f"{i + 1}. {ds}  →  variable name: {var_name}")
    if not upstream:
        lines.append("  (none)")

    lines.append("")
    lines.append("## Risk flags")
    for flag in windowed.risk_flags:
        lines.append(f"- {flag}")
    if not windowed.risk_flags:
        lines.append("  (none)")

    if windowed.log_contents:
        lines.append("")
        lines.append(
            "## SAS execution logs (use for actual row counts, NOTE lines,"
            " WARNING/ERROR messages, and macro values)"
        )
        for log_path, content in windowed.log_contents.items():
            lines.append(f"### {log_path}")
            log_lines = content.splitlines()
            lines.append("\n".join(log_lines[:200]))

    lines.append("")
    if windowed.data_files:
        lines.append("")
        lines.append("## Uploaded data files (use these exact paths in spark.read calls)")
        for norm_path, info in windowed.data_files.items():
            basename = _os.path.basename(norm_path)
            lines.append(
                f"- /workspace/data/{basename}  ({info.extension}, {info.row_count or '?'} rows)"
            )

    lines.append(f"## SAS {block.block_type} block to translate")
    lines.append(f"Source: {block.source_file}, lines {block.start_line}-{block.end_line}")
    lines.append("")
    lines.append("```sas")
    lines.append(block.raw_sas)
    lines.append("```")

    # Log the input variable hints being sent to the LLM
    for line in lines:
        if "variable name:" in line:
            logger.debug("GenericProcAgent prompt input hint: %s", line.strip())
    return "\n".join(lines)


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[GenericProcResult]":
    """Instantiate the Pydantic AI agent for generic PROC translation.

    Routes through TensorZero, Azure OpenAI, or direct provider depending on
    which environment variables are set.

    Returns:
        A Pydantic AI Agent configured to return GenericProcResult outputs.
    """
    model_obj: OpenAIChatModel | KnownModelName

    if worker_settings.tensorzero_gateway_url:
        raw = worker_settings.llm_model
        base_name = raw.split(":", 1)[-1] if ":" in raw else raw
        tz_model_name = f"tensorzero::model_name::{base_name}"
        tz_provider = OpenAIProvider(
            base_url=worker_settings.tensorzero_gateway_url,
            api_key="tensorzero",
        )
        model_obj = OpenAIChatModel(model_name=tz_model_name, provider=tz_provider)
    elif worker_settings.azure_openai_endpoint:
        az_provider = AzureProvider(
            azure_endpoint=worker_settings.azure_openai_endpoint,
            api_key=worker_settings.azure_openai_api_key,
            api_version=worker_settings.openai_api_version,
        )
        raw = worker_settings.llm_model
        deployment = raw.split(":", 1)[-1] if ":" in raw else raw
        model_obj = OpenAIChatModel(model_name=deployment, provider=az_provider)
    else:
        model_obj = worker_settings.llm_model  # type: ignore[assignment]

    return Agent(
        model=model_obj,
        output_type=GenericProcResult,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class GenericProcAgent:
    """Translates any SAS PROC block into idiomatic Python via an LLM call.

    Handles PROC IML, FCMP, MEANS, FREQ, TRANSPOSE, IMPORT, EXPORT, OPTMODEL,
    and any unfamiliar PROC type. Default behaviour is to attempt translation;
    manual is only chosen when detected_features is non-empty.
    """

    def __init__(self) -> None:
        """Instantiate GenericProcAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[GenericProcResult] = _make_agent()

    async def translate(self, block: SASBlock, context: JobContext) -> GeneratedBlock:
        """Translate a SAS PROC block into a GeneratedBlock with Python code.

        Args:
            block: The SAS PROC block to translate.
            context: The full job context; windowed to the block before use.

        Returns:
            A GeneratedBlock with translated Python code and confidence metadata.

        Raises:
            GenericProcError: If the LLM call fails.
        """
        windowed = context.windowed_context(block)
        prompt = _build_prompt(block, windowed, context.blocks)

        try:
            result = await self._agent.run(
                prompt,
                model_settings={"max_tokens": 8000},
            )
            record_usage(result.usage())
        except Exception as exc:
            logger.exception("GenericProcAgent LLM call failed for %s", block.block_type)
            raise GenericProcError(
                f"GenericProcAgent failed for {block.block_type}: {exc}", cause=exc
            ) from exc

        proc_result: GenericProcResult = result.output  # type: ignore[assignment]

        logger.debug(
            "GenericProcAgent raw LLM output_var=%r, output_datasets=%r",
            proc_result.output_var,
            block.output_datasets,
        )
        logger.debug(
            "GenericProcAgent raw python_code (first 300 chars):\n%s", proc_result.python_code[:300]
        )

        is_untranslatable = proc_result.strategy_used == "manual"
        python_code = normalise_output_var_in_code(
            proc_result.python_code, block.output_datasets, "GenericProcAgent"
        )
        python_code = _fix_workspace_paths(python_code)
        python_code = _fix_excel_spark_reads(python_code)
        fixed_output_var = normalise_output_var(block.output_datasets, proc_result.output_var)
        logger.debug(
            "GenericProcAgent after normalise: output_var=%r, python_code has rawdir_customers=%s",
            fixed_output_var,
            "rawdir_customers" in python_code,
        )
        if fixed_output_var and not _re.search(
            rf"\b{_re.escape(fixed_output_var)}\s*=", python_code
        ):
            logger.warning(
                "GenericProcAgent: output_var '%s' not found as assignment in generated code"
                " after rename — check LLM output",
                fixed_output_var,
            )

        return GeneratedBlock(
            source_block=block,
            python_code=python_code,
            output_var=fixed_output_var,
            is_untranslatable=is_untranslatable,
            confidence=proc_result.confidence_band,
            confidence_score=proc_result.confidence_score,
            confidence_band=proc_result.confidence_band,
            uncertainty_notes=proc_result.uncertainty_notes,
            assumptions=proc_result.assumptions,
            strategy_used=proc_result.strategy_used,
        )
