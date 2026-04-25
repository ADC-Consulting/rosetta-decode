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
from src.worker.engine.agents.shared_context import build_context_section
from src.worker.engine.models import GeneratedBlock, JobContext, SASBlock

logger = logging.getLogger("src.worker.engine.agents.generic_proc")


# ── Output model ──────────────────────────────────────────────────────────────


class GenericProcResult(BaseModel):
    """Structured output from the GenericProcAgent LLM call."""

    python_code: str
    strategy_used: str = "translate"
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
    PREFER PySpark for all data transformations. Fall back to pandas/numpy only when PySpark
    cannot handle the specific construct.
    The code must run in a Databricks notebook (PySpark native) or plain Python 3.12 environment
    without SAS.

    **DEFAULT: always attempt a translation.** A best-effort translation with real code is always
    preferred over an empty placeholder. Set ``confidence_score`` to your honest estimate — low
    confidence is fine, but the code field must never be empty for ``translate`` or
    ``translate_with_review`` strategies. Use ``uncertainty_notes`` to explain what may differ.
    Only assign ``strategy="manual"`` when the SAS construct has absolutely no Python equivalent
    (e.g., PROC OPTMODEL LP/NLP with complex solver structure that cannot be approximated) —
    and you MUST list those features in detected_features. If detected_features would be empty,
    you CANNOT choose manual.

    ## Strategy selection (in priority order)

    1. "translate"
       Fully automated, high confidence expected. Use for PROC MEANS, PROC FREQ,
       PROC TRANSPOSE, PROC SORT (simple), straightforward PROC IML matrix arithmetic.

    2. "translate_with_review"
       Translated but a human should verify. Use when:
       - SAS date/time semantics differ (INTNX, INTCK, SAS date literals from 1 Jan 1960)
       - SAS STD = sample std (ddof=1) — differs from numpy default (ddof=0)
       - SAS missing-value propagation (special missings .A-.Z not representable in float64)
       - CALL SYMPUT/SYMPUTX with dynamic dataset names
       - PROC IML matrix arithmetic where storage order matters
         (SAS column-major vs NumPy row-major)
       - PROC FCMP function definitions
       - Complex PROC OPTMODEL that maps to scipy.optimize

    3. "manual_ingestion"
       PROC IMPORT / PROC EXPORT file I/O only. Emit a PySpark read/write shell with TODO comments.
       Example:
         # TODO: verify file path, format, and schema
         df_output = spark.read.csv(  # SAS: <file>:<line>
             "<infile_path>", header=True, inferSchema=True
         )
         # pandas fallback: df_output = pd.read_csv("<infile_path>")

    4. "manual"
       ONLY when detected_features is non-empty AND features have no reasonable Python equivalent.
       Example: PROC OPTMODEL LP/NLP with a model structure so complex no scaffold is meaningful.
       NEVER emit manual for PROC IML, PROC FCMP, PROC MEANS, PROC FREQ, or PROC TRANSPOSE.
       When using manual, ALWAYS provide: a suggested Python library, a short explanation, and
       at minimum a scaffold comment pointing the reviewer to the right tool.

    5. "skip"
       PROC PRINT, PROC CONTENTS, PROC DATASETS, standalone title/footnote statements.
       Emit an empty string for python_code.

    ## PROC-specific translation guidance

    ### PROC MEANS / PROC SUMMARY
    Use pandas .groupby().agg() or .describe().
    - CLASS → groupby columns
    - VAR → columns to aggregate
    - N → "count", MEAN → "mean", STD → "std" (pandas ddof=1 by default — correct)
    - MIN/MAX/MEDIAN → "min"/"max"/"median"
    - OUTPUT OUT= → assign result to the OUT= variable name (lowercased)
    Example:
      result = df.groupby(["dept"]).agg({"salary": ["count", "mean", "std"]})
      result.columns = ["n", "mean_salary", "std_salary"]
      result = result.reset_index()

    ### PROC FREQ
    - TABLES a → pd.Series.value_counts() or pd.crosstab(df.a, "All")
    - TABLES a*b → pd.crosstab(df.a, df.b)
    - TABLES a*b / CHISQ → from scipy import stats; stats.chi2_contingency(pd.crosstab(df.a, df.b))
    - OUT= → assign to the OUT= variable name (lowercased)

    ### PROC TRANSPOSE
    - ID → becomes the new column names after pivoting
    - VAR → columns to transpose
    - BY → group-by columns (pivot within group)
    - OUT= → assign result to OUT= variable name
    Use df.pivot() for wide→long or df.melt() for long→wide as appropriate.

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
      Convert: pd.Timestamp('1960-01-01') + pd.to_timedelta(sas_date_value, unit='D')
    - SAS std() = sample std (ddof=1). NumPy default is ddof=0 — always specify ddof=1.
    - SAS missing numeric = . (propagates as NaN in pandas — correct by default).
    - SAS special missings .A-.Z are not representable in float64.
      Note in uncertainty_notes when present.
    - Preserve SAS column names exactly, lowercased.
    - Treat SAS dataset names as already-loaded pd.DataFrame variables (lowercased,
      dots replaced with underscores).
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
      "strategy_used": "translate|translate_with_review|manual_ingestion|manual|skip",
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
    - python_code MUST be non-empty for translate and translate_with_review.
    - For skip, python_code = "".
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

    ctx_section = build_context_section(windowed)
    if ctx_section:
        lines.append(ctx_section)

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

        is_untranslatable = proc_result.strategy_used in ("manual",)
        # For skip strategy, emit a provenance comment rather than empty string
        python_code = proc_result.python_code
        if proc_result.strategy_used == "skip" and not python_code.strip():
            python_code = (
                f"# SAS: {block.source_file}:{block.start_line} - skipped ({block.block_type})"
            )

        return GeneratedBlock(
            source_block=block,
            python_code=python_code,
            is_untranslatable=is_untranslatable,
            confidence=proc_result.confidence_band,
            confidence_score=proc_result.confidence_score,
            confidence_band=proc_result.confidence_band,
            uncertainty_notes=proc_result.uncertainty_notes,
            assumptions=proc_result.assumptions,
            strategy_used=proc_result.strategy_used,
        )
