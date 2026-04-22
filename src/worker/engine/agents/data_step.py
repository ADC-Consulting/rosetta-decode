"""DataStepAgent — translates a single SAS DATA step into pandas Python code.

# agent: DataStepAgent
"""

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

logger = logging.getLogger("src.worker.engine.agents.data_step")


# ── Output model ──────────────────────────────────────────────────────────────


class DataStepResult(BaseModel):
    """Structured output from the DataStepAgent LLM call."""

    python_code: str
    strategy_used: str = "translate"
    confidence_score: float = 0.9
    confidence_band: str = "high"
    uncertainty_notes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


# ── Error ─────────────────────────────────────────────────────────────────────


class DataStepError(Exception):
    """Raised when the DataStepAgent LLM call fails.

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
    # agent: DataStepAgent

    You are a SAS-to-Python migration engineer. Translate the SAS DATA step below into
    idiomatic Python targeting a modern Python 3.12 data platform.

    Target environment: PySpark, pandas, numpy, pyarrow, scipy, statsmodels are all available.
    PREFER PySpark idioms for all data transformations (DataFrame API, Column expressions,
    Window functions). Fall back to pandas/numpy only when PySpark has no equivalent for the
    specific construct.
    The code must run in Databricks (PySpark native) or plain Python 3.12.

    Output schema — ALL fields are REQUIRED:
    {
      "python_code": "<translated Python source>",
      "strategy_used": "translate|translate_with_review",
      "confidence_score": <float 0.0-1.0>,
      "confidence_band": "high|medium|low|very_low",
      "uncertainty_notes": ["<one sentence per uncertain construct>"],
      "assumptions": ["<SAS semantic quirk this translation relies on>"]
    }
    - Emit only the JSON object. No prose. No markdown fences.
    - confidence_score: 1.0=certain translation, 0.0=highly uncertain. Required.
      1.00-0.85 high / 0.84-0.65 medium / 0.64-0.40 low / 0.39-0.00 very_low
    - confidence_band: derived from confidence_score (see above). Required.
    - uncertainty_notes: REQUIRED list (may be empty [] for high confidence). Each entry must be
      one sentence naming the specific SAS construct or pattern that may not translate cleanly.
    - assumptions: list SAS semantic quirks your translation relies on.
    - strategy_used: "translate" or "translate_with_review" (DATA steps are always translated).
    - For low/medium confidence constructs, insert before the relevant lines:
        # UNCERTAIN: <reason> — human review required
    - Add # SAS: <source_file>:<line_number> after each logical section.
    - Preserve SAS column names exactly, lowercased.
    - Treat each SAS dataset name as an already-loaded Spark DataFrame variable (lowercased).
      If falling back to pandas, treat as pd.DataFrame.
    - Macro variables are pre-resolved; use their literal values directly.

    ## SAS semantic preservation rules (MUST follow)
    - SAS std() = sample std (ddof=1). NumPy default is ddof=0 — always specify ddof=1
      when computing standard deviations.
    - SAS date origin = 1 January 1960.
      Conversion: pd.Timestamp('1960-01-01') + pd.to_timedelta(sas_date_value, unit='D')
    - SAS missing numeric = . (propagates as NaN in pandas — correct by default).
    - SAS special missings .A-.Z are not representable in float64.
      Add to uncertainty_notes when present in the source.
    - BY-group FIRST./LAST. logic must use .diff().ne(0) or groupby markers, not direct access.

    ## Translation patterns (PySpark preferred; pandas as fallback)
    - IF/THEN/ELSE → pyspark.sql.functions.when().otherwise() for simple; df.withColumn with
      Column expr for multi-statement. pandas fallback: np.where() for simple; .loc[mask] for
      multi-statement blocks.
    - RETAIN → df.withColumn using Window lag/lead with accumulator UDF.
      pandas fallback: iterrows() with explicit accumulator, or shift()+cumsum() for running totals.
    - Arrays (ARRAY x{n}) → PySpark: list of Column references; iterate with for-loop.
    - BY-group (BY var; FIRST.var / LAST.var) → Window.partitionBy(var).orderBy(var) + lag()
      comparison. pandas fallback: sort + groupby().transform() or .diff().ne(0).
    - DO / END → for-loop over DataFrame operations; prefer vectorised Column expressions.
    - Implicit OUTPUT → every-row output; standard DataFrame construction.
    - Explicit OUTPUT inside DO → build list of dicts, use spark.createDataFrame(rows).
    - MERGE with BY → df.join(right, on=key, how="outer").
      pandas fallback: df.merge(..., how="outer") + sort_values(BY).
    - KEEP / DROP → df.select([kept_cols]) or df.drop(col).
    - LENGTH / FORMAT / INFORMAT → comment out with # SAS: preserved as metadata.
    - SET with multiple datasets → df1.unionByName(df2).
      pandas fallback: pd.concat([...], ignore_index=True).
    - CALL SYMPUT/SYMPUTX → assign to a Python variable; add uncertainty note.

    Assign final output to lowercased OUTPUT dataset name (dots → underscores).
""")


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(block: SASBlock, windowed: JobContext) -> str:
    """Build the user prompt for a DATA step translation.

    Args:
        block: The SAS block to translate.
        windowed: A windowed JobContext scoped to this block.

    Returns:
        A formatted prompt string for the LLM.
    """
    lines: list[str] = []

    lines.append("## Macro variable context")
    for macro in windowed.resolved_macros:
        lines.append(f'- {macro.name} = "{macro.raw_value}"  ({macro.source_file}:{macro.line})')

    lines.append("")
    lines.append("## Upstream datasets (dependency order)")
    for i, ds in enumerate(windowed.dependency_order):
        lines.append(f"{i + 1}. {ds}")

    lines.append("")
    lines.append("## Risk flags")
    for flag in windowed.risk_flags:
        lines.append(f"- {flag}")

    lines.append("")
    lines.append("## SAS DATA step to translate")
    lines.append(f"Source: {block.source_file}, lines {block.start_line}-{block.end_line}")
    lines.append("")
    lines.append("```sas")
    lines.append(block.raw_sas)
    lines.append("```")

    return "\n".join(lines)


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[DataStepResult]":
    """Instantiate the Pydantic AI agent for DATA step translation.

    When ``TENSORZERO_GATEWAY_URL`` is set, routes through TensorZero via an
    OpenAI-compatible endpoint using the ``"translation"`` model name.
    When ``AZURE_OPENAI_ENDPOINT`` is set, uses Azure OpenAI.
    Otherwise falls back to the direct provider string.

    Returns:
        A Pydantic AI Agent configured to return DataStepResult outputs.
    """
    model_obj: OpenAIChatModel | KnownModelName

    if worker_settings.tensorzero_gateway_url:
        tz_provider = OpenAIProvider(
            base_url=worker_settings.tensorzero_gateway_url,
            api_key="tensorzero",  # TensorZero ignores the key but client requires one
        )
        raw = worker_settings.llm_model
        base_name = raw.split(":", 1)[-1] if ":" in raw else raw
        tz_model_name = f"tensorzero::model_name::{base_name}"
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
        output_type=DataStepResult,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class DataStepAgent:
    """Translates a single SAS DATA step into pandas Python code via an LLM call."""

    def __init__(self) -> None:
        """Instantiate DataStepAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[DataStepResult] = _make_agent()

    async def translate(self, block: SASBlock, context: JobContext) -> GeneratedBlock:
        """Translate a SAS DATA step block into a GeneratedBlock with pandas code.

        Args:
            block: The SAS DATA step block to translate.
            context: The full job context; windowed to the block before use.

        Returns:
            A GeneratedBlock with translated Python code.

        Raises:
            DataStepError: When the LLM call fails for any reason.
        """
        try:
            windowed = context.windowed_context(block)
            user_prompt = _build_prompt(block, windowed)
            result = await self._agent.run(user_prompt, model_settings={"max_tokens": 4000})
            output: DataStepResult = result.output  # type: ignore[assignment]
            return GeneratedBlock(
                source_block=block,
                python_code=output.python_code,
                confidence=output.confidence_band,
                confidence_score=output.confidence_score,
                confidence_band=output.confidence_band,
                uncertainty_notes=output.uncertainty_notes,
                assumptions=output.assumptions,
                strategy_used=output.strategy_used,
                is_untranslatable=False,
            )
        except Exception as e:
            raise DataStepError(message=str(e), cause=e) from e
