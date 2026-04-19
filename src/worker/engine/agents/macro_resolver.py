"""MacroResolverAgent — LLM fallback for macros that MacroExpander cannot handle.

# agent: MacroResolverAgent
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
from src.worker.engine.macro_expander import CannotExpandError
from src.worker.engine.models import JobContext

logger = logging.getLogger("src.worker.engine.agents.macro_resolver")


# ── Output model ──────────────────────────────────────────────────────────────


class MacroResolution(BaseModel):
    """Structured output from the MacroResolverAgent LLM call."""

    expanded_text: str
    could_resolve: bool


# ── Error ─────────────────────────────────────────────────────────────────────


class MacroResolverError(Exception):
    """Raised when MacroResolverAgent fails for a non-resolvable reason.

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
    # agent: MacroResolverAgent

    You are a SAS macro expansion expert. Given SAS code with macro calls the deterministic
    expander could not handle, attempt to expand them from context.

    Resolution rules:
    - could_resolve = true when ALL hold:
        (a) macro references only variables listed in "Already-resolved macros"
        (b) expansion produces a fixed string — no remaining &var or %macro refs
        (c) no SAS functions (%SYSFUNC, %EVAL with complex expressions) need to execute
    - could_resolve = false when:
        - macro variable was set via CALL SYMPUT / CALL SYMPUTX
        - macro is a parameterized %MACRO ... %MEND
        - expansion requires executing %SYSFUNC or %SYSCALL
        - recursive or deeply nested macros cannot be flattened statically

    Unambiguous examples (always resolve):
    - "&REPORT_YEAR" with REPORT_YEAR="2023" → "2023", could_resolve: true
    - "data &PREFIX.output;" with PREFIX="q1_" → "data q1_output;", could_resolve: true
    - "&START_DT"d with START_DT="01JAN2023" → "'01JAN2023'd", could_resolve: true

    Return ONLY: { "expanded_text": "...", "could_resolve": true|false }
    No prose. No markdown fences.
""")


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[MacroResolution]":
    """Instantiate the Pydantic AI agent for macro resolution.

    Returns:
        A Pydantic AI Agent configured to return MacroResolution outputs.
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
        output_type=MacroResolution,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class MacroResolverAgent:
    """LLM-backed fallback for macros that MacroExpander cannot expand deterministically."""

    def __init__(self) -> None:
        """Instantiate MacroResolverAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[MacroResolution] = _make_agent()

    async def resolve(self, macro_text: str, context: JobContext) -> str:
        """Attempt to expand *macro_text* using the LLM.

        Args:
            macro_text: The raw SAS text containing the unresolvable macro reference.
            context: The current job context for additional resolution hints.

        Returns:
            Expanded SAS text if the LLM can resolve it.

        Raises:
            CannotExpandError: If the LLM reports it cannot resolve the macro.
            MacroResolverError: If the LLM call itself fails.
        """
        prompt = _build_prompt(macro_text, context)
        try:
            result = await self._agent.run(prompt)
        except Exception as exc:
            raise MacroResolverError(
                f"MacroResolverAgent LLM call failed: {exc}", cause=exc
            ) from exc

        resolution = cast(MacroResolution, result.output)
        if not resolution.could_resolve:
            raise CannotExpandError(
                macro_name="<llm-unresolvable>",
                reason="LLM could not resolve macro without additional runtime context",
            )
        return resolution.expanded_text


def _build_prompt(macro_text: str, context: JobContext) -> str:
    """Build the user prompt for macro resolution.

    Args:
        macro_text: The SAS text with unresolvable macro calls.
        context: The job context for additional hints.

    Returns:
        A formatted prompt string for the LLM.
    """
    lines: list[str] = ["## Already-resolved macro variables"]
    for macro in context.resolved_macros:
        lines.append(f'- {macro.name} = "{macro.raw_value}"  ({macro.source_file}:{macro.line})')

    lines += [
        "",
        "## Risk flags",
        *[f"- {flag}" for flag in context.risk_flags],
        "",
        "## SAS text to expand",
        "```sas",
        macro_text,
        "```",
    ]
    return "\n".join(lines)
