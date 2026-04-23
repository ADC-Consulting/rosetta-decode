"""MigrationPlannerAgent — produces a structured migration plan from a JobContext.

# agent: MigrationPlannerAgent
"""

# SAS: src/worker/engine/agents/migration_planner.py:1

import logging
import textwrap
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider
from src.worker.core.config import worker_settings
from src.worker.engine.models import (
    BlockPlan,
    BlockRisk,
    JobContext,
    MigrationPlan,
    TranslationStrategy,
)

logger = logging.getLogger("src.worker.engine.agents.migration_planner")


# ── Output model ──────────────────────────────────────────────────────────────


class PlannerResult(BaseModel):
    """Structured output from the MigrationPlannerAgent LLM call."""

    summary: str
    overall_risk: str
    block_plans: list[dict[str, Any]]
    recommended_review_blocks: list[str]
    cross_file_dependencies: list[str]


# ── Error ─────────────────────────────────────────────────────────────────────


class MigrationPlannerError(Exception):
    """Raised when the MigrationPlannerAgent LLM call fails after retries.

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
    # agent: MigrationPlannerAgent

    You are a senior SAS-to-Python migration architect. Before any code is translated,
    analyse the full SAS codebase and produce a structured migration plan that guides
    the downstream translation agents and gives the client a clear action list.

    Input:
    - One or more SAS source files with their filenames.
    - A list of pre-resolved macro variables.
    - A list of parsed blocks: each has block_id ("source_file:start_line"), block_type
      (DATA_STEP | PROC_SQL | PROC_SORT | UNTRANSLATABLE), input_datasets, output_datasets.

    Your tasks:
    1. Write 1-2 sentences describing what this SAS codebase does at a business level.
       Write as if explaining to a non-technical business stakeholder — what business
       process does it support, what decision or report does it produce? Do NOT mention
       SAS, Python, datasets, files, code, or any technical terms. Focus solely on the
       business outcome (e.g. "This pipeline calculates monthly revenue by region and
       flags anomalies for the finance team's risk review.").
    2. For each block, assign:
       - strategy: one of the values below (use exactly these strings).

    Translation strategy values (use exactly these strings):
    - "translate"             Fully auto-translated. DATA steps, PROC SQL, PROC SORT,
                              PROC MEANS — anything the agents handle reliably.
    - "translate_with_review" Translated but flagged for human check. Use when date/time
                              semantics differ (INTNX, INTCK, SAS date literals), format
                              conversions (PICTURE, INFORMATs), or ambiguous merges.
    - "manual_ingestion"      PROC IMPORT / PROC EXPORT / any file I/O. Emit a pandas
                              read/write shell with TODOs only.
    - "manual"                PROC IML, PROC OPTMODEL, PROC FCMP, no pandas equivalent.
                              Emit a # TODO placeholder comment only.
    - "skip"                  PROC PRINT, PROC CONTENTS, PROC DATASETS, standalone
                              comments, title/footnote statements. Emit nothing.
       - risk: "low", "medium", or "high" based on:
           HIGH  — CALL SYMPUT/SYMPUTX, dynamic dataset names, nested macros, %INCLUDE,
                   PROC types we don't handle, deeply nested DO loops with RETAIN
           MEDIUM — BY-group processing, MERGE with complex BY, multi-output DATA steps,
                    CASE expressions in PROC SQL, PROC SORT with complex BY clause
           LOW   — simple SET/filter/rename DATA steps, straightforward PROC SQL SELECTs
       - rationale: one sentence explaining the risk level and strategy.
       - estimated_effort: "low" (< 1 hour review), "medium" (1-4 hours),
         "high" (> 4 hours or requires domain knowledge).
    3. Set overall_risk to the highest risk level across all blocks.
    4. List recommended_review_blocks: block_ids the human should inspect first
       (all HIGH risk blocks, plus MEDIUM blocks with cross-file dependencies).
    5. List cross_file_dependencies: plain-English notes for any dataset that flows
       between files.

    Return ONLY a JSON object — no prose, no markdown fences:
    {
      "summary": "...",
      "overall_risk": "low|medium|high",
      "block_plans": [
        {
          "block_id": "source_file:start_line",
          "source_file": "...",
          "start_line": <int>,
          "block_type": "DATA_STEP|PROC_SQL|PROC_SORT|UNTRANSLATABLE",
          "strategy": "translate|translate_with_review|manual_ingestion|manual|skip",
          "risk": "low|medium|high",
          "rationale": "...",
          "estimated_effort": "low|medium|high"
        }
      ],
      "recommended_review_blocks": ["source_file:start_line", ...],
      "cross_file_dependencies": ["...", ...]
    }
""")


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[PlannerResult]":
    """Instantiate the Pydantic AI agent for migration planning.

    When ``TENSORZERO_GATEWAY_URL`` is set, routes through TensorZero via an
    OpenAI-compatible endpoint.  When ``AZURE_OPENAI_ENDPOINT`` is set, uses
    Azure OpenAI.  Otherwise falls back to the direct provider string.

    Returns:
        A Pydantic AI Agent configured to return PlannerResult outputs.
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
        output_type=PlannerResult,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class MigrationPlannerAgent:
    """Produces a MigrationPlan for a full SAS codebase via a single LLM call."""

    def __init__(self) -> None:
        """Instantiate MigrationPlannerAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[PlannerResult] = _make_agent()

    async def plan(self, context: JobContext) -> MigrationPlan:
        """Run LLM planning on the provided JobContext.

        Args:
            context: The shared job context containing source files, resolved
                macros, and parsed blocks from the analysis stage.

        Returns:
            A MigrationPlan with per-block plans, overall risk, recommended
            review targets, and cross-file dependency notes.

        Raises:
            MigrationPlannerError: If the LLM call fails after retries.
        """
        prompt = _build_prompt(context)
        try:
            result = await self._agent.run(
                prompt,
                model_settings={"max_tokens": 6000},
            )
        except Exception as exc:
            logger.exception("MigrationPlannerAgent LLM call failed")
            raise MigrationPlannerError(f"MigrationPlannerAgent failed: {exc}", cause=exc) from exc

        planner_result: PlannerResult = result.output  # type: ignore[assignment]
        return _build_migration_plan(planner_result)


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(context: JobContext) -> str:
    """Build the user-facing prompt from the job context.

    Args:
        context: The shared job context with source files, macros, and blocks.

    Returns:
        A formatted prompt string for the LLM.
    """
    parts: list[str] = []

    parts.append("## Pre-resolved macro variables")
    if context.resolved_macros:
        for mv in context.resolved_macros:
            parts.append(
                f"  - {mv.name} = {mv.raw_value!r}  (declared in {mv.source_file}:{mv.line})"
            )
    else:
        parts.append("  (none)")

    parts.append("")
    parts.append("## Parsed blocks")
    for block in context.blocks:
        block_id = f"{block.source_file}:{block.start_line}"
        inputs = ", ".join(block.input_datasets) if block.input_datasets else "none"
        outputs = ", ".join(block.output_datasets) if block.output_datasets else "none"
        parts.append(
            f"  - block_id={block_id!r}  type={block.block_type}"
            f"  inputs=[{inputs}]  outputs=[{outputs}]"
        )

    parts.append("")
    parts.append("## SAS source files")
    for filename, content in context.source_files.items():
        parts.append(f"\n### {filename}\n```sas\n{content}\n```")

    return "\n".join(parts)


# ── Plan assembler ────────────────────────────────────────────────────────────


def _build_migration_plan(result: PlannerResult) -> MigrationPlan:
    """Convert a PlannerResult into a typed MigrationPlan.

    Args:
        result: Raw structured output from the LLM.

    Returns:
        A fully-typed MigrationPlan instance.
    """
    block_plans: list[BlockPlan] = []
    for bp in result.block_plans:
        strategy = TranslationStrategy(bp.get("strategy", "translate"))
        block_type = bp.get("block_type", "")
        detected_features: list[str] = bp.get("detected_features") or []
        if strategy == TranslationStrategy.MANUAL and not detected_features:
            detected_features = [block_type] if block_type else ["UNSUPPORTED"]
        no_translation = strategy in (
            TranslationStrategy.MANUAL,
            TranslationStrategy.MANUAL_INGESTION,
            TranslationStrategy.SKIP,
        )
        block_plans.append(
            BlockPlan(
                block_id=bp.get("block_id", ""),
                source_file=bp.get("source_file", ""),
                start_line=int(bp.get("start_line", 1)),
                block_type=block_type,
                strategy=strategy,
                risk=BlockRisk(bp.get("risk", "low")),
                rationale=bp.get("rationale", ""),
                estimated_effort=bp.get("estimated_effort", "low"),
                detected_features=detected_features,
                confidence_score=0.0 if no_translation else 1.0,
                confidence_band="very_low" if no_translation else "high",
            )
        )

    return MigrationPlan(
        summary=result.summary,
        block_plans=block_plans,
        overall_risk=BlockRisk(result.overall_risk),
        recommended_review_blocks=result.recommended_review_blocks,
        cross_file_dependencies=result.cross_file_dependencies,
    )
