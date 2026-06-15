"""ProcAgent — translates a single SAS PROC SQL block into pandas Python code.

# agent: ProcAgent
"""

import logging
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
    build_block_output_stems,
    detect_referenced_data_files,
    detect_referenced_formats,
    inject_declared_casts,
    normalise_input_vars_in_code,
    normalise_output_var,
    normalise_output_var_in_code,
    render_declared_types_section,
    render_format_section,
)
from src.worker.engine.models import BlockType, GeneratedBlock, JobContext, SASBlock
from src.worker.engine.usage import record_usage

logger = logging.getLogger("src.worker.engine.agents.proc")


# ── Output model ──────────────────────────────────────────────────────────────


class ProcResult(BaseModel):
    """Structured output from the ProcAgent LLM call."""

    python_code: str
    output_var: str | None = None
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

_SYSTEM_PROMPT = textwrap.dedent(
    """\
    # agent: ProcAgent

    You are a SAS-to-Python migration engineer specialising in SQL translation.
    Translate the SAS PROC SQL block below into idiomatic Python targeting a modern
    Python 3.12 data platform.

    Target environment: PySpark, pandas, numpy, pyarrow, scipy, sqlalchemy, duckdb are available.
    DEFAULT: use PySpark (Spark SQL or DataFrame API) for ALL SQL translations.
    pandas is a LAST RESORT — only when the specific construct is impossible in PySpark.
    duckdb is a last resort for recursive CTEs or multi-level window functions PySpark cannot express.
    When falling back, add a comment: # pandas/duckdb fallback: <reason PySpark cannot do this>
    scipy/statsmodels are used for statistical operations beyond descriptive stats — wrap in pandas_udf.
    The code must run in Databricks (PySpark native) or a local SparkSession (CLOUD=false).

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
    - INPUT datasets referenced in FROM / JOIN clauses are already-loaded Spark DataFrame variables
      (lowercased, dots → underscores).
    - OUTPUT tables (CREATE TABLE x AS ...) must be CREATED by your code — do not reference them
      as if they already exist. `x = spark.sql(...)` is correct; `y = x.select(...)` before x is
      defined is WRONG.
    - Macro variables are pre-resolved; use their literal values directly.

    Translation patterns (PySpark; pandas/duckdb only as last resort):
    - JOIN → df.join(right, on=[col_name_strings], how="inner|left|right|outer").
      NEVER use dot-qualified column references like col("t.TX_DATE") or F.col("alias.col") in
      join conditions or post-join expressions — PySpark resolves columns by name after join, not
      by table alias. Use plain col("TX_DATE") or rename ambiguous columns with .alias() before joining.
      For multi-condition joins use a boolean expression: F.col("TX_DATE") == F.col("DATE").
      pandas last resort: df.merge(right, on=[...], how=...)
    - GROUP BY + agg → df.groupBy([...]).agg(F.sum("col"), ...).
      pandas last resort: .groupby([...]).agg({...}).reset_index()
    - WHERE (pre-agg) → df.filter(condition) using Column expressions.
      pandas last resort: boolean indexing or .query()
    - HAVING (post-agg) → df.filter(condition) after .agg().
      Any aggregate referenced by a HAVING / post-aggregation filter MUST be materialised inside
      the SAME .agg() call with an explicit .alias("name"), then filtered on that alias. NEVER
      reference Spark-SQL auto-generated names like "count(1)", "count(*)", "sum(x)" or "avg(x)"
      via F.col(...) after a DataFrame-API .agg() — those names do not exist (UNRESOLVED_COLUMN).
      Drop tautological/no-op filters such as F.col("count(1)").isNotNull() (a count is never null)
      — they have no SAS equivalent and must not be emitted.
        WRONG: df.groupBy("k").agg(F.min("x").alias("mn")).filter(F.col("count(1)") > 5)
        RIGHT: df.groupBy("k").agg(F.min("x").alias("mn"), F.count("*").alias("grp_n")).filter(F.col("grp_n") > 5)
      pandas last resort: .loc[condition] after .agg()
    - ORDER BY → df.orderBy([...]). NEVER use .sort_values() — it does not exist on Spark DataFrames.
    - CREATE TABLE x AS SELECT → assign to x (lowercased) as Spark DataFrame.
    - DISTINCT → df.distinct().
      pandas last resort: .drop_duplicates()
    - CASE WHEN → F.when(cond, val).when(cond2, val2).otherwise(default).
      pandas last resort: np.select(conditions, choices, default=...) or np.where()
    - Window: SUM(col) OVER (PARTITION BY p) →
        from pyspark.sql import Window
        df.withColumn("s", F.sum("col").over(Window.partitionBy("p")))
    - Window: ROW_NUMBER() OVER (PARTITION BY p ORDER BY o) →
        df.withColumn("rn", F.row_number().over(Window.partitionBy("p").orderBy("o")))
    - CTEs (WITH x AS ...) → assign intermediate to Spark DataFrame named after CTE alias.
    - INSERT INTO existing SELECT → existing.unionByName(new_rows).
      pandas last resort: pd.concat([existing, new_rows]).reset_index(drop=True)
    - SELECT INTO :macro_var → extract scalar with .first()[0], assign to Python var.
    - PROC IMPORT / PROC EXPORT: route to manual_ingestion (but ProcAgent should not receive these)
    - CALCULATED col → use Python expression; no SAS CALCULATED keyword

    - Always include any imports your code needs at the top of your block (e.g. `from pyspark.sql import functions as F`). Do NOT assume pandas or any other library is pre-imported.
    - Variable naming: use the DATASET STEM only — strip the libname prefix entirely.
        - CORRECT: `CREATE TABLE outdir.foo AS ...` → Python variable `foo`
        - WRONG:   `outdir_foo`, `outdir.foo`, any form with the libname
      The output variable name in your code MUST exactly match the `output_var` field you return in JSON.
      NEVER use the libname or a dot/underscore-joined form for the output variable.
      Input tables: use EXACTLY the variable name shown in the prompt (`→ variable name: <name>`).
      External source files use `libname_table` form; inter-block datasets use stem-only.
    - After computing your primary output DataFrame, set `result = <output_var>` as the final line.
      Example: `result = customer_revenue_daily`
    - Set the `output_var` field in your JSON response to the stem-only name.
      Example: `"output_var": "customer_revenue_daily"`
"""
    + SHARED_TRANSLATION_RULES
)


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(block: SASBlock, windowed: JobContext, all_blocks: list[SASBlock]) -> str:
    """Build the user prompt for a PROC SQL translation.

    Args:
        block: The SAS block to translate.
        windowed: A windowed JobContext scoped to this block.
        all_blocks: All SAS blocks in the job (used to resolve inter-block variable names).

    Returns:
        A formatted prompt string for the LLM.
    """
    lines: list[str] = []

    lines.append("## Macro variable context")
    for macro in windowed.resolved_macros:
        lines.append(f'- {macro.name} = "{macro.raw_value}"  ({macro.source_file}:{macro.line})')

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

    lines.append("")
    lines.append("## Risk flags")
    for flag in windowed.risk_flags:
        lines.append(f"- {flag}")

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

    referenced = detect_referenced_formats(block.raw_sas)
    format_section = render_format_section(referenced, windowed.format_catalog)
    if format_section:
        lines.append("")
        lines.append(format_section)

    types_refs = detect_referenced_data_files(block, windowed.data_files)
    types_section = render_declared_types_section(types_refs, windowed.data_files)
    if types_section:
        lines.append("")
        lines.append(types_section)

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
            user_prompt = _build_prompt(block, windowed, context.blocks)
            result = await self._agent.run(user_prompt, model_settings={"max_tokens": 4000})
            record_usage(result.usage())
            output: ProcResult = result.output  # type: ignore[assignment]
            fixed_code = normalise_output_var_in_code(
                output.python_code, block.output_datasets, "ProcAgent"
            )
            logger.debug(
                "ProcAgent block %s:%s input_datasets=%s output_datasets=%s",
                block.source_file,
                block.start_line,
                block.input_datasets,
                block.output_datasets,
            )
            fixed_code = normalise_input_vars_in_code(
                fixed_code,
                block.input_datasets,
                build_block_output_stems(context.blocks),
                "ProcAgent",
            )
            fixed_code = inject_declared_casts(fixed_code, context.data_files, "ProcAgent")
            fixed_output_var = normalise_output_var(block.output_datasets, output.output_var)
            if fixed_output_var and not _re.search(
                rf"\b{_re.escape(fixed_output_var)}\s*=", fixed_code
            ):
                logger.warning(
                    "ProcAgent: output_var '%s' not found as assignment in generated code"
                    " after rename — check LLM output",
                    fixed_output_var,
                )
            return GeneratedBlock(
                source_block=block,
                python_code=fixed_code,
                output_var=fixed_output_var,
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
