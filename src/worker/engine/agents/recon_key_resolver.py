"""ReconKeyResolverAgent — proposes the correct business join key for row_hash_diff.

When the deterministic ``row_hash_diff`` check fails because the inferred key is
unique-but-wrong (e.g. ``(subjid, aestdtc)`` on adverse-event data, where a
subject can have several events on one date), this agent reads the failure, both
schemas, the block's raw SAS, and deterministic per-column stats, and proposes
the correct key. The worker then re-runs ONLY the comparison in-process with the
proposed key — the LLM never touches generated pipeline code (DECISIONS
2026-06-15). See ``docs/plans`` F15 record-level reconciliation.

# agent: ReconKeyResolverAgent
"""

from __future__ import annotations

import logging
import textwrap
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider
from src.worker.core.config import worker_settings
from src.worker.engine.usage import record_usage

logger = logging.getLogger("src.worker.engine.agents.recon_key_resolver")


# ── Output model ──────────────────────────────────────────────────────────────


class KeyResolution(BaseModel):
    """Structured output from the ReconKeyResolverAgent LLM call.

    Attributes:
        proposed_keys: Lowercased column names forming the proposed join key.
        rationale: One- or two-sentence justification grounded in the SAS source.
        confidence_score: Self-reported confidence, 0.0-1.0 (default 0.8).
    """

    proposed_keys: list[str] = Field(default_factory=list)
    rationale: str = ""
    confidence_score: float = 0.8


# ── Error ─────────────────────────────────────────────────────────────────────


class ReconKeyResolverError(Exception):
    """Raised when the ReconKeyResolverAgent LLM call fails.

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
    # agent: ReconKeyResolverAgent

    You are a clinical/financial data reconciliation expert. A record-level
    comparison (row_hash_diff) between a reference dataset (produced by the
    original SAS program) and the migrated Python output FAILED because the
    automatically-inferred join key is unique but is NOT the correct BUSINESS
    key for the dataset. Your job is to propose the correct join key so the two
    datasets can be aligned row-for-row.

    You are given: the failing comparison detail, the reference and actual
    column schemas, deterministic per-column statistics (null fraction and
    cardinality), the raw SAS source for the block, and — on retries — feedback
    on every key already tried (why it failed and how close it came).

    Rules:
    - Propose a key that is a genuine business identifier (e.g. subject + event
      sequence, subject + visit + parameter), grounded in the SAS source and the
      column stats. A correct key is non-null and UNIQUE per row in BOTH frames.
    - Prefer the SMALLEST key that is plausibly unique. Add discriminating
      columns (sequence numbers, event terms, visit identifiers) when a
      candidate is near-unique but not exact.
    - NEVER repeat a key already listed as tried-and-failed in the feedback.
      When no prior key was exact, build on the CLOSEST one (it is flagged) by
      adding a discriminating column rather than starting over.
    - Use only column names that appear in BOTH schemas. Lowercase them.

    Output schema — ALL fields REQUIRED:
    {
      "proposed_keys": ["<col>", ...],
      "rationale": "<one or two sentences grounded in the SAS source / stats>",
      "confidence_score": <float 0.0-1.0>
    }
    - Emit only the JSON object. No prose. No markdown fences.
    """
)


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> Agent[KeyResolution]:
    """Instantiate the Pydantic AI agent for join-key resolution.

    Mirrors :func:`src.worker.engine.agents.data_step._make_agent`: routes
    through TensorZero or Azure OpenAI when configured, otherwise uses the direct
    provider string from ``worker_settings.llm_model``.

    Returns:
        A Pydantic AI Agent configured to return KeyResolution outputs.
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
        output_type=KeyResolution,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(
    failure_detail: str,
    ref_schema: list[str],
    actual_schema: list[str],
    raw_sas: str,
    candidate_stats: str,
    attempts_feedback: str,
) -> str:
    """Build the user prompt for a join-key resolution call.

    Args:
        failure_detail: The failing ``row_hash_diff`` detail string.
        ref_schema: Reference frame column names (lowercased).
        actual_schema: Actual frame column names (lowercased).
        raw_sas: The block's raw SAS source.
        candidate_stats: Deterministic per-column null/cardinality stats text.
        attempts_feedback: Bounded feedback on prior proposals (empty on attempt 1).

    Returns:
        A formatted prompt string for the LLM.
    """
    lines: list[str] = []
    lines.append("## Failing row_hash_diff detail")
    lines.append(failure_detail or "(no detail)")
    lines.append("")
    lines.append("## Reference schema (columns)")
    lines.append(", ".join(ref_schema))
    lines.append("")
    lines.append("## Actual (migrated) schema (columns)")
    lines.append(", ".join(actual_schema))
    lines.append("")
    lines.append("## Per-column statistics (deterministic; null fraction, cardinality)")
    lines.append(candidate_stats or "(none)")
    if attempts_feedback:
        lines.append("")
        lines.append("## Keys already tried (do NOT repeat; build on the CLOSEST)")
        lines.append(attempts_feedback)
    lines.append("")
    lines.append("## Raw SAS source for this block")
    lines.append("```sas")
    lines.append(raw_sas)
    lines.append("```")
    return "\n".join(lines)


# ── Agent class ───────────────────────────────────────────────────────────────


class ReconKeyResolverAgent:
    """Proposes the correct business join key for a failed row_hash_diff via an LLM."""

    def __init__(self) -> None:
        """Instantiate ReconKeyResolverAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[KeyResolution] = _make_agent()

    async def resolve(
        self,
        failure_detail: str,
        ref_schema: list[str],
        actual_schema: list[str],
        raw_sas: str,
        candidate_stats: str,
        attempts_feedback: str = "",
    ) -> KeyResolution:
        """Propose a join key for a failed ``row_hash_diff`` comparison.

        Args:
            failure_detail: The failing ``row_hash_diff`` detail string.
            ref_schema: Reference frame column names (lowercased).
            actual_schema: Actual frame column names (lowercased).
            raw_sas: The block's raw SAS source.
            candidate_stats: Deterministic per-column null/cardinality stats text.
            attempts_feedback: Bounded feedback on prior proposals, flagging the
                single closest attempt (empty on the first attempt).

        Returns:
            A KeyResolution with the proposed lowercased key columns.

        Raises:
            ReconKeyResolverError: When the LLM call fails for any reason.
        """
        try:
            prompt = _build_prompt(
                failure_detail,
                ref_schema,
                actual_schema,
                raw_sas,
                candidate_stats,
                attempts_feedback,
            )
            result = await self._agent.run(prompt, model_settings={"max_tokens": 1000})
            record_usage(result.usage())
            output: KeyResolution = result.output  # type: ignore[assignment]
            output.proposed_keys = [
                str(k).strip().lower() for k in output.proposed_keys if str(k).strip()
            ]
            return output
        except Exception as exc:
            raise ReconKeyResolverError(message=str(exc), cause=exc) from exc


def build_candidate_stats(ref: Any, actual: Any) -> str:
    """Render bounded per-column null/cardinality stats for the resolver prompt.

    Pure, deterministic helper kept here (not in reconciliation.py, which holds
    no LLM-facing code) so the prompt is grounded in real column statistics.

    Args:
        ref: Reference pandas DataFrame (columns already lowercased).
        actual: Actual pandas DataFrame (columns already lowercased).

    Returns:
        One line per common column: ``name: ref_null=.., ref_card=.., act_null=.., act_card=..``.
    """
    common = [c for c in ref.columns if c in actual.columns]
    lines: list[str] = []
    n_ref = max(len(ref), 1)
    n_act = max(len(actual), 1)
    for col in common:
        ref_null = float(ref[col].isna().mean())
        act_null = float(actual[col].isna().mean())
        ref_card = ref[col].dropna().nunique() / n_ref
        act_card = actual[col].dropna().nunique() / n_act
        lines.append(
            f"{col}: ref_null={ref_null:.3f}, ref_card={ref_card:.3f}, "
            f"act_null={act_null:.3f}, act_card={act_card:.3f}"
        )
    return "\n".join(lines)
