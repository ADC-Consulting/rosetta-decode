"""ProcAgent — translates a single SAS PROC SQL block into pandas Python code.

# agent: ProcAgent
"""

import logging
import textwrap

from pydantic import BaseModel
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
    Translate the SAS PROC SQL block below into idiomatic pandas code.

    Rules:
    - Emit only Python code. No prose. No markdown fences.
    - Return: {"python_code": "...", "confidence": "high|medium|low", "uncertainty_notes": [...]}
    - Set confidence and uncertainty_notes following the same rules as DataStepAgent.
    - Add # SAS: <source_file>:<line_number> after each logical section (once per statement).
    - Do NOT use pandasql, sqlite3, duckdb, or any SQL engine. Use pure pandas.
    - Treat SAS dataset names as already-loaded pd.DataFrame variables (lowercased).
    - Macro variables are pre-resolved; use their literal values directly.

    - PROC IMPORT / PROC EXPORT: set strategy to "manual_ingestion". Emit a pandas read/write
      shell only:
        import pandas as pd
        # TODO: verify file path, separator, and column names
        df_<output_dataset> = pd.read_csv("<infile_path>")  # SAS: <file>:<line>
      Do NOT attempt to replicate PROC IMPORT options in Python.
    - PROC PRINT / PROC CONTENTS / PROC DATASETS: set strategy to "skip". Emit nothing.
    - PROC IML / PROC OPTMODEL / PROC FCMP: set strategy to "manual". Emit:
        # TODO: manual implementation required — no pandas equivalent for <PROC_NAME>
        # SAS: <file>:<line>

    Translation patterns:
    - JOIN → df.merge(right, on=[...], how="inner|left|right|outer")
    - GROUP BY + agg → .groupby([...]).agg({...}).reset_index()
    - WHERE (pre-agg) → boolean indexing or .query()
    - HAVING (post-agg) → .loc[condition] after .agg()
    - ORDER BY → .sort_values([...])
    - CREATE TABLE x AS SELECT → assign to x (lowercased)
    - DISTINCT → .drop_duplicates()
    - CASE WHEN → np.select(conditions, choices, default=...) or np.where() for binary
    - Window: SUM(col) OVER (PARTITION BY p) → .groupby(p)[col].transform("sum")
    - Window: ROW_NUMBER() OVER (PARTITION BY p ORDER BY o) →
        df.sort_values(o).groupby(p).cumcount() + 1
    - CTEs (WITH x AS ...) → assign intermediate to variable named after CTE alias
    - INSERT INTO existing SELECT → pd.concat([existing, new_rows]).reset_index(drop=True)
    - SELECT INTO :macro_var → extract scalar, assign to Python var, add # SAS: comment
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
                is_untranslatable=False,
            )
        except Exception as e:
            raise ProcError(message=str(e), cause=e) from e
