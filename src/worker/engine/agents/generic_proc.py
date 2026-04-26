"""GenericProcAgent — translates any SAS PROC block into idiomatic Python.

Handles PROC IML, PROC FCMP, PROC MEANS/SUMMARY, PROC FREQ, PROC TRANSPOSE,
PROC IMPORT/EXPORT, PROC OPTMODEL, and any unfamiliar (PROC_UNKNOWN) blocks.
Default assumption: translation is always attempted; manual is only chosen when
detected_features is non-empty and the features have no Python equivalent.

# agent: GenericProcAgent
"""

# SAS: src/worker/engine/agents/generic_proc.py:1

import logging
import textwrap

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider
from src.worker.core.config import worker_settings
from src.worker.engine.models import GeneratedBlock, JobContext, SASBlock

logger = logging.getLogger("src.worker.engine.agents.generic_proc")


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

_SYSTEM_PROMPT = textwrap.dedent("""\
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
       - PROC IMPORT / PROC EXPORT: emit a runnable spark.read / df.write call with
         TODO comments for file path and format verification.
         Example:
           # TODO: verify file path, format, and schema
           df_output = spark.read.csv("<infile_path>", header=True, inferSchema=True)  # SAS: <file>:<line>
           # pandas fallback: df_output = pd.read_csv("<infile_path>")
         CRITICAL: spark.read.csv() / spark.read.parquet() / spark.read.json() MUST receive
         a string literal path (e.g. "/workspace/data/foo.csv"), NEVER a DataFrame variable.
         If the input is already a DataFrame in scope, use it directly — do not pass it to spark.read.
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
        result = rawdir_transactions_clean
    - Set the `output_var` field in your JSON response to the name of the primary output variable (lowercased dataset name). Example: "output_var": "rawdir_transactions_clean"

    ## PROC-specific translation guidance

    ### PROC MEANS / PROC SUMMARY
    Use PySpark df.groupBy().agg().
    - CLASS → groupBy columns
    - VAR → columns to aggregate
    - N → F.count(), MEAN → F.mean(), STD → F.stddev_samp() (sample std, matches SAS)
    - MIN/MAX/MEDIAN → F.min()/F.max()/F.percentile_approx(col, 0.5)
    - OUTPUT OUT= → assign result to the OUT= variable name (lowercased)
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
    - OUT= → assign to the OUT= variable name (lowercased)

    ### PROC TRANSPOSE
    - ID → becomes new column names after pivoting
    - VAR → columns to transpose
    - BY → group-by columns (pivot within group)
    - OUT= → assign result to OUT= variable name
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
    - INPUT datasets are already-loaded Spark/pandas DataFrame variables (lowercased, dots → underscores).
      OUTPUT datasets must be CREATED by your code — do not reference them as if they already exist.
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
""")


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(block: SASBlock, windowed: JobContext) -> str:
    """Build the user prompt for a generic PROC translation.

    Args:
        block: The SAS block to translate.
        windowed: A windowed JobContext scoped to this block.

    Returns:
        A formatted prompt string for the LLM.
    """
    lines: list[str] = []

    lines.append(f"## PROC type: {block.block_type}")
    lines.append("")

    lines.append("## Macro variable context")
    for macro in windowed.resolved_macros:
        lines.append(f'- {macro.name} = "{macro.raw_value}"  ({macro.source_file}:{macro.line})')
    if not windowed.resolved_macros:
        lines.append("  (none)")

    lines.append("")
    lines.append("## Upstream datasets (dependency order)")
    for i, ds in enumerate(windowed.dependency_order):
        lines.append(f"{i + 1}. {ds}")
    if not windowed.dependency_order:
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
    lines.append(f"## SAS {block.block_type} block to translate")
    lines.append(f"Source: {block.source_file}, lines {block.start_line}-{block.end_line}")
    lines.append("")
    lines.append("```sas")
    lines.append(block.raw_sas)
    lines.append("```")

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
        prompt = _build_prompt(block, windowed)

        try:
            result = await self._agent.run(
                prompt,
                model_settings={"max_tokens": 8000},
            )
        except Exception as exc:
            logger.exception("GenericProcAgent LLM call failed for %s", block.block_type)
            raise GenericProcError(
                f"GenericProcAgent failed for {block.block_type}: {exc}", cause=exc
            ) from exc

        proc_result: GenericProcResult = result.output  # type: ignore[assignment]

        is_untranslatable = proc_result.strategy_used == "manual"
        python_code = proc_result.python_code

        return GeneratedBlock(
            source_block=block,
            python_code=python_code,
            output_var=proc_result.output_var,
            is_untranslatable=is_untranslatable,
            confidence=proc_result.confidence_band,
            confidence_score=proc_result.confidence_score,
            confidence_band=proc_result.confidence_band,
            uncertainty_notes=proc_result.uncertainty_notes,
            assumptions=proc_result.assumptions,
            strategy_used=proc_result.strategy_used,
        )
