"""FailureInterpreterAgent — interprets reconciliation failures and produces a retry hint.

# agent: FailureInterpreterAgent
"""

import logging
import textwrap
from typing import cast

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider
from src.worker.core.config import worker_settings
from src.worker.engine.models import JobContext

logger = logging.getLogger("src.worker.engine.agents.failure_interpreter")


# ── Output model ──────────────────────────────────────────────────────────────


class FailureInterpretation(BaseModel):
    """Structured output from the FailureInterpreterAgent LLM call.

    Attributes:
        retry_hint: A short natural-language hint describing the correction to apply
            when re-invoking the specialist agent for the failing block.
        affected_block_id: The block identifier (source_file:start_line) that caused
            the reconciliation failure.
    """

    retry_hint: str
    affected_block_id: str


# ── Error ─────────────────────────────────────────────────────────────────────


class FailureInterpreterError(Exception):
    """Raised when the FailureInterpreterAgent LLM call fails.

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
    # agent: FailureInterpreterAgent

    You are a SAS-to-Python migration debugger. A reconciliation test comparing
    the generated Python output against a reference CSV has failed. Your task is
    to identify the most likely cause and produce a concise retry hint.

    Input:
    - A diff between expected (reference) and actual (generated) output.
    - The generated Python code that produced the incorrect output.

    Output rules:
    - Return ONLY a JSON object with exactly two keys:
        { "retry_hint": "...", "affected_block_id": "..." }
    - retry_hint: A one-to-two-sentence instruction for the translation agent,
        explaining what went wrong and how to fix it on retry.
    - affected_block_id: The block identifier in the format "source_file:start_line"
        (e.g. "etl.sas:12"). Identify this from provenance comments in the code
        (# SAS: <file>:<line>). If multiple blocks are affected, pick the primary one.
    - No prose, no markdown fences.
""")


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[FailureInterpretation]":
    """Instantiate the Pydantic AI agent for failure interpretation.

    Returns:
        A Pydantic AI Agent configured to return FailureInterpretation outputs.
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
        output_type=FailureInterpretation,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class FailureInterpreterAgent:
    """Interprets a reconciliation diff and returns a retry hint with block ID."""

    def __init__(self) -> None:
        """Instantiate FailureInterpreterAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[FailureInterpretation] = _make_agent()

    async def interpret(
        self,
        diff: str,
        generated_code: str,
        context: JobContext,
    ) -> tuple[str, str]:
        """Interpret a reconciliation failure and produce a retry hint.

        Args:
            diff: Text diff between expected and actual output (unified diff format).
            generated_code: The Python code that produced the failing output.
            context: The current job context for additional hints.

        Returns:
            A 2-tuple of (retry_hint, affected_block_id).

        Raises:
            FailureInterpreterError: When the LLM call fails.
        """
        prompt = _build_prompt(diff, generated_code, context)
        try:
            result = await self._agent.run(prompt)
        except Exception as exc:
            raise FailureInterpreterError(
                f"FailureInterpreterAgent LLM call failed: {exc}", cause=exc
            ) from exc

        interp = cast(FailureInterpretation, result.output)
        return interp.retry_hint, interp.affected_block_id


def _build_prompt(diff: str, generated_code: str, context: JobContext) -> str:
    """Build the user prompt for failure interpretation.

    Args:
        diff: Reconciliation diff text.
        generated_code: The generated Python pipeline code.
        context: Current job context.

    Returns:
        A formatted prompt string for the LLM.
    """
    lines: list[str] = [
        "## Reconciliation diff (expected vs actual)",
        "```diff",
        diff,
        "```",
        "",
        "## Risk flags from analysis",
        *[f"- {flag}" for flag in context.risk_flags],
        "",
        "## Generated Python code",
        "```python",
        generated_code,
        "```",
    ]
    return "\n".join(lines)
