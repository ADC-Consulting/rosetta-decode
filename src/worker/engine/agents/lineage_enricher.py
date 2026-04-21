"""LineageEnricherAgent — produces an enriched lineage map from a JobContext.

# agent: LineageEnricherAgent
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
from src.worker.engine.models import (
    BlockStatus,
    ColumnFlow,
    EnrichedLineage,
    FileEdge,
    FileNode,
    JobContext,
    LogLink,
    MacroUsage,
    PipelineStep,
)

logger = logging.getLogger("src.worker.engine.agents.lineage_enricher")


# ── Output model ──────────────────────────────────────────────────────────────


class LineageEnrichmentResult(BaseModel):
    """Structured output from the LineageEnricherAgent LLM call."""

    column_flows: list[ColumnFlow]
    macro_usages: list[MacroUsage]
    cross_file_edges: list[dict[str, str]]
    dataset_summaries: dict[str, str]
    file_nodes: list[FileNode] = Field(default_factory=list)
    file_edges: list[FileEdge] = Field(default_factory=list)
    pipeline_steps: list[PipelineStep] = Field(default_factory=list)
    block_status: list[BlockStatus] = Field(default_factory=list)
    log_links: list[LogLink] = Field(default_factory=list)


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
    lineage map that goes beyond block-to-block edges. Reconstruct the full SAS pipeline at
    three levels: dataset level, block/file level, and pipeline-step level.

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

    5. file_nodes: One entry per distinct SAS source file present in the input.
       Classify file_type as one of: PROGRAM | MACRO | AUTOEXEC | LOG | OTHER.
         PROGRAM  — a standard SAS program (%include'd or run directly)
         MACRO    — a file whose primary purpose is defining SAS macros
         AUTOEXEC — a file named autoexec.sas or fulfilling that role
         LOG      — a SAS log file (.log)
         OTHER    — anything that does not fit the above
       List all block_ids belonging to that file in `blocks`.
       Set status (OK | UNTRANSLATABLE | ERROR_PRONE) only when you have evidence; otherwise null.
       Each entry: { filename, file_type, blocks, status, status_reason }

    6. file_edges: One edge per directly observable file-to-file dependency
       (%INCLUDE, macro call resolving to another file, shared dataset written in one file
       and read in another).
       reason must be one of: INCLUDE | MACRO_CALL | READS_DATASET | WRITES_DATASET
       Omit any edge you cannot support with evidence in the source.
       Each entry: { source_file, target_file, reason, via_block_id }

    7. pipeline_steps: Group the pipeline into logical named stages a human analyst would
       recognise (e.g. "Ingest raw data", "Apply business rules", "Write output").
       step_id must be "step_1", "step_2", etc. in execution order.
       Only emit steps you can justify from the SAS logic; do not invent stages.
       Each entry: { step_id, name, description, files, blocks, inputs, outputs }

    8. block_status: Per-block health — only emit when status is UNTRANSLATABLE or ERROR_PRONE.
       OK blocks may be omitted unless there is a specific reason to flag them.
       Each entry: { block_id, status, reason }

    9. log_links: Only applicable when one or more LOG files are present in the input.
       Link each log file to the source files and block_ids it references.
       severity must reflect the highest level found: INFO | WARNING | ERROR
       Each entry: { log_file, related_files, related_blocks, severity }

    General rules:
    - Only emit entries you can support with evidence from the provided SAS source.
    - If you are unsure about a field value, omit the entry rather than guessing.
    - All new list fields default to [] — it is correct to return an empty list.

    Return ONLY a JSON object — no prose, no markdown fences:
    {
      "column_flows": [...],
      "macro_usages": [...],
      "cross_file_edges": [...],
      "dataset_summaries": {"dataset_name": "description", ...},
      "file_nodes": [...],
      "file_edges": [...],
      "pipeline_steps": [...],
      "block_status": [...],
      "log_links": [...]
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
            dataset_summaries, file_nodes, file_edges, pipeline_steps, block_status,
            and log_links populated.

        Raises:
            LineageEnricherError: If the LLM call fails after retries.
        """
        prompt = _build_prompt(context)
        try:
            result = await self._agent.run(
                prompt,
                model_settings={"max_tokens": 16000},
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
            file_nodes=enrichment.file_nodes,
            file_edges=enrichment.file_edges,
            pipeline_steps=enrichment.pipeline_steps,
            block_status=enrichment.block_status,
            log_links=enrichment.log_links,
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
