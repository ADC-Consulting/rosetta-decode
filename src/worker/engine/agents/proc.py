"""ProcAgent — translates a single SAS PROC SQL block into pandas Python code.

# agent: ProcAgent
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
from src.worker.engine.models import BlockType, GeneratedBlock, JobContext, SASBlock

logger = logging.getLogger("src.worker.engine.agents.proc")


# ── Output model ──────────────────────────────────────────────────────────────


class ProcResult(BaseModel):
    """Structured output from the ProcAgent LLM call."""

    python_code: str
    strategy_used: str = "translate"
    confidence_score: float = 0.9
    confidence_band: str = "high"
    uncertainty_notes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


# ── Error ─────────────────────────────────────────────────────────────────────


class ProcError(Exception):
    """Raised when the ProcAgent LLM call fails.

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
    # agent: ProcAgent

    You are a SAS-to-Python migration engineer specialising in SQL translation.
    Translate the SAS PROC SQL block below into idiomatic Python targeting a modern
    Python 3.12 data platform.

    Target environment: PySpark, pandas, numpy, pyarrow, scipy, sqlalchemy, duckdb are available.
    PREFER PySpark for all SQL translations (Spark SQL or DataFrame API).
    For simple cases where PySpark is not applicable: use pandas.
    Use SciPy/statsmodels for statistical operations that go beyond descriptive stats.
    For complex SQL (multi-level window functions, recursive CTEs) not easily expressed in PySpark:
      you may use duckdb as a last resort: import duckdb; result = duckdb.query("SELECT ...").df()
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
    - confidence_score: 1.00-0.85 high / 0.84-0.65 medium / 0.64-0.40 low / 0.39-0.00 very_low.
    - uncertainty_notes: REQUIRED list (may be empty []). Each entry must be one sentence.
    - assumptions: list SAS semantic quirks your translation relies on.
    - Add # SAS: <source_file>:<line_number> after each logical section (once per statement).
    - Treat SAS dataset names as already-loaded Spark DataFrame variables (lowercased).
      If falling back to pandas, treat as pd.DataFrame.
    - Macro variables are pre-resolved; use their literal values directly.

    Translation patterns (PySpark preferred; pandas/duckdb as fallback):
    - JOIN → df.join(right, on=[...], how="inner|left|right|outer").
      pandas fallback: df.merge(right, on=[...], how=...)
    - GROUP BY + agg → df.groupBy([...]).agg(F.sum("col"), ...).
      pandas fallback: .groupby([...]).agg({...}).reset_index()
    - WHERE (pre-agg) → df.filter(condition) using Column expressions.
      pandas fallback: boolean indexing or .query()
    - HAVING (post-agg) → df.filter(condition) after .agg().
      pandas fallback: .loc[condition] after .agg()
    - ORDER BY → df.orderBy([...]).
      pandas fallback: .sort_values([...])
    - CREATE TABLE x AS SELECT → assign to x (lowercased) as Spark DataFrame.
    - DISTINCT → df.distinct().
      pandas fallback: .drop_duplicates()
    - CASE WHEN → F.when(cond, val).when(cond2, val2).otherwise(default).
      pandas fallback: np.select(conditions, choices, default=...) or np.where()
    - Window: SUM(col) OVER (PARTITION BY p) →
        from pyspark.sql import Window
        df.withColumn("s", F.sum("col").over(Window.partitionBy("p")))
      pandas fallback: .groupby(p)[col].transform("sum")
    - Window: ROW_NUMBER() OVER (PARTITION BY p ORDER BY o) →
        df.withColumn("rn", F.row_number().over(Window.partitionBy("p").orderBy("o")))
      pandas fallback: df.sort_values(o).groupby(p).cumcount() + 1
    - CTEs (WITH x AS ...) → assign intermediate to Spark DataFrame named after CTE alias.
    - INSERT INTO existing SELECT →
        existing.unionByName(new_rows).
      pandas fallback: pd.concat([existing, new_rows]).reset_index(drop=True)
    - SELECT INTO :macro_var → extract scalar with .first()[0], assign to Python var,
      add # SAS: comment.
    - PROC IMPORT / PROC EXPORT: route to manual_ingestion (but ProcAgent should not receive these)
    - CALCULATED col → use Python expression; no SAS CALCULATED keyword
""")


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(block: SASBlock, windowed: JobContext) -> str:
    """Build the user prompt for a PROC SQL translation.

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
    lines.append("## SAS PROC SQL to translate")
    lines.append(f"Source: {block.source_file}, lines {block.start_line}-{block.end_line}")
    lines.append("")
    lines.append("```sas")
    lines.append(block.raw_sas)
    lines.append("```")

    return "\n".join(lines)


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[ProcResult]":
    """Instantiate the Pydantic AI agent for PROC SQL translation.

    When ``TENSORZERO_GATEWAY_URL`` is set, routes through TensorZero via an
    OpenAI-compatible endpoint using the ``"translation"`` model name.
    When ``AZURE_OPENAI_ENDPOINT`` is set, uses Azure OpenAI.
    Otherwise falls back to the direct provider string.

    Returns:
        A Pydantic AI Agent configured to return ProcResult outputs.
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
        output_type=ProcResult,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class ProcAgent:
    """Translates a single SAS PROC SQL block into pandas Python code via an LLM call."""

    def __init__(self) -> None:
        """Instantiate ProcAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[ProcResult] = _make_agent()

    async def translate(self, block: SASBlock, context: JobContext) -> GeneratedBlock:
        """Translate a SAS PROC SQL block into a GeneratedBlock with pandas code.

        Args:
            block: The SAS PROC SQL block to translate.
            context: The full job context; windowed to the block before use.

        Returns:
            A GeneratedBlock with translated Python code.

        Raises:
            ValueError: When the block is not a PROC_SQL block.
            ProcError: When the LLM call fails for any reason.
        """
        if block.block_type is not BlockType.PROC_SQL:
            raise ValueError(
                f"ProcAgent only handles PROC_SQL; got {block.block_type!r}. "
                "PROC_SORT is handled by TranslationRouter._ProcSortHelper."
            )
        try:
            windowed = context.windowed_context(block)
            user_prompt = _build_prompt(block, windowed)
            result = await self._agent.run(user_prompt, model_settings={"max_tokens": 4000})
            output: ProcResult = result.output  # type: ignore[assignment]
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
            raise ProcError(message=str(e), cause=e) from e
