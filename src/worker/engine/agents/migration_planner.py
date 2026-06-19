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
    SASBlock,
    TranslationStrategy,
)
from src.worker.engine.usage import record_usage

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
    1. Write a 2-3 sentence plain-English summary of what this SAS codebase does as a
       whole, at a business level (not technical). Assume the reader is a business analyst.
    2. For each block, assign:
       - strategy: one of the values below (use exactly these strings).

    Translation strategy values (use exactly these strings):
    - "translated"             Fully auto-translated. DATA steps, PROC SQL, PROC SORT,
                               PROC MEANS, PROC FREQ, PROC TRANSPOSE — anything the agents
                               handle reliably.
    - "translated_with_review" Translated but flagged for human check. Use when:
                               - Date/time semantics differ (INTNX, INTCK, SAS date literals)
                               - Format conversions (PICTURE, INFORMATs) or ambiguous merges
                               - PROC IMPORT / PROC EXPORT (GenericProcAgent emits runnable
                                 pd.read_csv / to_csv with TODO path comments)
                               - PROC PRINT / PROC CONTENTS / PROC DATASETS (translate to
                                 Python display/inspection equivalent)
                               - PROC IML / PROC FCMP / PROC OPTMODEL (translate with review)
                               - Any unrecognised PROC (PROC_UNKNOWN)
    - "manual"                 ONLY when the block relies on features with genuinely no
                               Python equivalent. MUST list those features in detected_features.
                               NEVER use "manual" if detected_features would be empty.
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

    Special rules for macro utility blocks:
    - Blocks inside `macros/` files (e.g. `working/macros/assert_rowcount.sas`) that are
      assertion or validation helpers — recognisable by macro parameter names like `&ds` or
      `&lib` used as dataset names — have no Python equivalent. Assign strategy: `manual`
      and risk: `high` for these. Do NOT attempt to translate them as runnable PySpark/pandas
      code. Set detected_features to the macro parameter names that make translation impossible.
    - More generally: if a block references SAS macro parameters (variables of the form
      `&<name>`) as dataset or library names, assign strategy: `manual` because the macro
      context is not available at translation time.

    Return ONLY a JSON object — no prose, no markdown fences:
    {
      "summary": "...",
      "overall_risk": "low|medium|high",
      "block_plans": [
        {
          "block_id": "source_file:start_line",
          "source_file": "...",
          "start_line": <int>,
          "block_type": "<exact value from the parsed block list above, e.g. if the list says type=PROC_IML write PROC_IML>",
          "strategy": "translated|translated_with_review|manual",
          "risk": "low|medium|high",
          "rationale": "...",
          "estimated_effort": "low|medium|high",
          "confidence_score": "<float 0.0-1.0, how confident are you this block can be translated correctly? 0.0 = impossible, 1.0 = trivial>",
          "detected_features": ["<required non-empty when strategy=manual>"]
        }
      ],
      "recommended_review_blocks": ["source_file:start_line", ...],
      "cross_file_dependencies": ["...", ...]
    }
""")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _score_to_band(score: float) -> str:
    """Map a confidence score to a named band."""
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    if score >= 0.40:
        return "low"
    return "very_low"


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
            record_usage(result.usage())
        except Exception as exc:
            logger.exception("MigrationPlannerAgent LLM call failed")
            raise MigrationPlannerError(f"MigrationPlannerAgent failed: {exc}", cause=exc) from exc

        planner_result: PlannerResult = result.output  # type: ignore[assignment]
        return _build_migration_plan(planner_result, context.blocks)


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

    if context.log_contents:
        parts.append("## SAS execution logs")
        parts.append(
            "Use these logs to understand actual runtime behaviour, row counts,"
            " NOTE: lines, and macro expansions."
        )
        for log_path, content in context.log_contents.items():
            parts.append(f"### {log_path}")
            log_lines = content.splitlines()
            parts.append("\n".join(log_lines[:200]))

    return "\n".join(parts)


# ── Plan assembler ────────────────────────────────────────────────────────────


def _build_migration_plan(result: PlannerResult, blocks: list[SASBlock]) -> MigrationPlan:
    """Convert a PlannerResult into a typed MigrationPlan.

    Args:
        result: Raw structured output from the LLM.
        blocks: Parsed SASBlock objects used to resolve end_line by block_id.

    Returns:
        A fully-typed MigrationPlan instance.
    """
    end_line_by_id: dict[str, int] = {f"{b.source_file}:{b.start_line}": b.end_line for b in blocks}
    # Authoritative block_type from the parser — never trust the LLM's copy
    parsed_type_by_id: dict[str, str] = {
        f"{b.source_file}:{b.start_line}": b.block_type for b in blocks
    }
    block_lookup: dict[str, SASBlock] = {f"{b.source_file}:{b.start_line}": b for b in blocks}
    block_plans: list[BlockPlan] = []
    for bp in result.block_plans:
        source_file = bp.get("source_file", "")
        start_line = int(bp.get("start_line", 1))
        block_id = bp.get("block_id", f"{source_file}:{start_line}")
        confidence_score = float(bp.get("confidence_score", 0.5))
        confidence_band = _score_to_band(confidence_score)
        sas_block = block_lookup.get(block_id)
        block_plans.append(
            BlockPlan(
                block_id=block_id,
                source_file=source_file,
                start_line=start_line,
                end_line=end_line_by_id.get(f"{source_file}:{start_line}", 0),
                block_type=parsed_type_by_id.get(block_id, bp.get("block_type", "")),
                strategy=TranslationStrategy(bp.get("strategy", "translated")),
                risk=BlockRisk(bp.get("risk", "low")),
                rationale=bp.get("rationale", ""),
                estimated_effort=bp.get("estimated_effort", "low"),
                confidence_score=confidence_score,
                confidence_band=confidence_band,
                detected_features=bp.get("detected_features", []),
                input_datasets=sas_block.input_datasets if sas_block is not None else [],
                output_datasets=sas_block.output_datasets if sas_block is not None else [],
            )
        )

    _override_consumed_manual_blocks(block_plans)

    return MigrationPlan(
        summary=result.summary,
        block_plans=block_plans,
        overall_risk=BlockRisk(result.overall_risk),
        recommended_review_blocks=result.recommended_review_blocks,
        cross_file_dependencies=result.cross_file_dependencies,
    )


def _to_stem(dataset: str) -> str:
    """Normalise a dataset name to its stem (lowercase, libname prefix stripped).

    Mirrors the stem logic used by ``build_block_output_stems`` in
    ``src.worker.engine.agents.shared`` so the planner guardrail and the codegen
    safety net agree on what counts as the "same" dataset.

    Args:
        dataset: A dataset name, possibly libname-qualified (``work.adsl_age``).

    Returns:
        The lowercased stem (``adsl_age``).
    """
    return dataset.lower().split(".")[-1]


def _override_consumed_manual_blocks(block_plans: list[BlockPlan]) -> None:
    """Force MANUAL blocks whose output is consumed downstream to be translated.

    A block routed to the stub generator emits only a ``# SAS-UNRECOGNIZED``
    comment and never creates its output dataset. If any later block reads that
    dataset, the assembled pipeline raises ``NameError`` at runtime. To preserve
    the deterministic invariant — *a consumed dataset must always be produced* —
    every MANUAL block whose output stem is consumed by another block is upgraded
    to ``TRANSLATED_WITH_REVIEW`` in place. Blocks whose outputs are not consumed
    (e.g. assertion-macro utilities) keep their MANUAL strategy.

    Args:
        block_plans: The fully-built per-block plans; mutated in place.
    """
    consumed_stems: set[str] = set()
    for bp in block_plans:
        for ds in bp.input_datasets:
            consumed_stems.add(_to_stem(ds))

    for bp in block_plans:
        if bp.strategy != TranslationStrategy.MANUAL:
            continue
        for ds in bp.output_datasets:
            if _to_stem(ds) in consumed_stems:
                logger.warning(
                    "migration_planner: overriding MANUAL->translated_with_review for %s"
                    " — its output %s is consumed downstream (a stub would break the"
                    " pipeline)",
                    bp.block_id,
                    ds,
                )
                bp.strategy = TranslationStrategy.TRANSLATED_WITH_REVIEW
                break
