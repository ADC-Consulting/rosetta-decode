"""LineageEnricherAgent — produces an enriched lineage map from a JobContext.

# agent: LineageEnricherAgent
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
from src.worker.engine.models import ColumnFlow, EnrichedLineage, JobContext, MacroUsage

logger = logging.getLogger("src.worker.engine.agents.lineage_enricher")


# ── Output model ──────────────────────────────────────────────────────────────


class LineageEnrichmentResult(BaseModel):
    """Structured output from the LineageEnricherAgent LLM call."""

    column_flows: list[ColumnFlow]
    macro_usages: list[MacroUsage]
    cross_file_edges: list[dict[str, str]]
    dataset_summaries: dict[str, str]


# ── Error ─────────────────────────────────────────────────────────────────────


class LineageEnricherError(Exception):
    """Raised when the LineageEnricherAgent LLM call fails after retries.

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
    # agent: LineageEnricherAgent

    You are a SAS data lineage analyst. Given the original SAS source files, resolved
    macro variables, and the dependency-ordered list of parsed blocks, produce an enriched
    lineage map that goes beyond block-to-block edges.

    Input:
    - SAS source files with filenames.
    - Resolved macro variables.
    - Parsed blocks with block_id ("source_file:start_line"), block_type, input_datasets,
      output_datasets, and raw SAS text.

    Your tasks:
    1. column_flows: For each dataset-to-dataset data flow, identify columns that are
       passed, renamed, or derived. Only emit entries you can determine with confidence.
       Do not guess column names not present in the SAS source.
       Each entry: { column, source_dataset, target_dataset, via_block_id, transformation }
       where transformation is a short description or null for pass-through.

    2. macro_usages: For each block referencing a macro variable (&name), one entry per
       block per macro referenced:
       { macro_name (UPPERCASE), macro_value, used_in_block_id }

    3. cross_file_edges: If a dataset produced in one file is consumed in a different file:
       { source_block_id, target_block_id, shared_dataset (lowercased) }

    4. dataset_summaries: For each distinct dataset name, one sentence describing what it
       contains, inferred from column names and SAS logic. Write "No description available."
       if nothing can be inferred.

    Return ONLY a JSON object — no prose, no markdown fences:
    {
      "column_flows": [...],
      "macro_usages": [...],
      "cross_file_edges": [...],
      "dataset_summaries": {"dataset_name": "description", ...}
    }
""")


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[LineageEnrichmentResult]":
    """Instantiate the Pydantic AI agent for SAS lineage enrichment.

    When ``TENSORZERO_GATEWAY_URL`` is set, routes through TensorZero via an
    OpenAI-compatible endpoint.  When ``AZURE_OPENAI_ENDPOINT`` is set, uses
    Azure OpenAI.  Otherwise falls back to the direct provider string.

    Returns:
        A Pydantic AI Agent configured to return LineageEnrichmentResult outputs.
    """
    model_obj: OpenAIChatModel | KnownModelName

    if worker_settings.tensorzero_gateway_url:
        raw = worker_settings.llm_model
        base_name = raw.split(":", 1)[-1] if ":" in raw else raw
        tz_model_name = f"tensorzero::model_name::{base_name}"
        tz_provider = OpenAIProvider(
            base_url=worker_settings.tensorzero_gateway_url,
            api_key="tensorzero",  # TensorZero ignores the key but client requires one
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
        output_type=LineageEnrichmentResult,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class LineageEnricherAgent:
    """Enriches SAS data lineage via a single LLM call and returns an EnrichedLineage."""

    def __init__(self) -> None:
        """Instantiate LineageEnricherAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[LineageEnrichmentResult] = _make_agent()

    async def enrich(self, context: JobContext) -> EnrichedLineage:
        """Run LLM lineage enrichment on the provided JobContext.

        Args:
            context: The full job context containing source files, resolved macros,
                and dependency-ordered parsed blocks.

        Returns:
            An EnrichedLineage with column_flows, macro_usages, cross_file_edges,
            and dataset_summaries populated.

        Raises:
            LineageEnricherError: If the LLM call fails after retries.
        """
        prompt = _build_prompt(context)
        try:
            result = await self._agent.run(
                prompt,
                model_settings={"max_tokens": 8000},
            )
        except Exception as exc:
            logger.exception("LineageEnricherAgent LLM call failed")
            raise LineageEnricherError(f"LineageEnricherAgent failed: {exc}", cause=exc) from exc

        enrichment: LineageEnrichmentResult = result.output  # type: ignore[assignment]
        return EnrichedLineage(
            column_flows=enrichment.column_flows,
            macro_usages=enrichment.macro_usages,
            cross_file_edges=enrichment.cross_file_edges,
            dataset_summaries=enrichment.dataset_summaries,
        )


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(context: JobContext) -> str:
    """Build the user-facing prompt from the JobContext.

    Args:
        context: The full job context with source files, resolved macros, and blocks.

    Returns:
        A formatted prompt string for the LLM.
    """
    parts: list[str] = []

    parts.append("## Resolved macro variables")
    if context.resolved_macros:
        for mv in context.resolved_macros:
            parts.append(
                f"  - {mv.name} = {mv.raw_value!r}  (declared in {mv.source_file}:{mv.line})"
            )
    else:
        parts.append("  (none)")

    parts.append("")
    parts.append("## SAS source files")
    for filename, content in context.source_files.items():
        parts.append(f"\n### {filename}\n```sas\n{content}\n```")

    parts.append("")
    parts.append("## Parsed blocks (dependency order)")
    for block in context.blocks:
        block_id = f"{block.source_file}:{block.start_line}"  # SAS: models.py:53
        parts.append(f"\n### Block {block_id}  [{block.block_type}]")
        parts.append(f"  inputs:  {block.input_datasets}")
        parts.append(f"  outputs: {block.output_datasets}")
        parts.append(f"```sas\n{block.raw_sas}\n```")

    return "\n".join(parts)
