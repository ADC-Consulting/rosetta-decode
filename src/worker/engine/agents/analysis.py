"""AnalysisAgent — analyses SAS source files and produces a JobContext.

# agent: AnalysisAgent
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
from src.worker.engine.models import JobContext, MacroVar, SASBlock

logger = logging.getLogger("src.worker.engine.agents.analysis")


# ── Output model ──────────────────────────────────────────────────────────────


class AnalysisResult(BaseModel):
    """Structured output from the AnalysisAgent LLM call."""

    resolved_macros: list[MacroVar]
    dependency_order: list[str]
    risk_flags: list[str]


# ── Error ─────────────────────────────────────────────────────────────────────


class AnalysisError(Exception):
    """Raised when the AnalysisAgent LLM call fails after retries.

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
    # agent: AnalysisAgent

    You are a SAS migration analyst. Given one or more SAS source files and a list of
    already-resolved macro variables, perform a structural analysis and return a single
    JSON object — no prose, no markdown fences.

    Your tasks:
    1. Identify all macro variable declarations (%LET) and their resolved values.
       Include pre-resolved macro vars supplied in the input AND any additional ones you
       discover. Each entry: name (UPPERCASE), raw_value, source_file, line (int).

    2. Determine the dataset dependency order.
       Topologically sorted list of DATASET NAMES (not block IDs):
       - A dataset that is an input to any block must appear before the dataset that block outputs.
       - If no dependency between two datasets, preserve document order.
       - If a dataset appears only as output, list it last.
       - Use lowercased dataset names exactly as they appear in the SAS source.

    3. Flag high-risk SAS patterns in risk_flags.
       Each entry MUST be: "<source_file>:<start_line> — <short description>"
       Patterns to flag: nested %MACRO/%MEND, %INCLUDE, PROC DATASETS, dynamic dataset
       names from macros (DATA &prefix.out), CALL SYMPUT/CALL SYMPUTX, %SYSCALL/%SYSFUNC
       with non-trivial expressions, multiple output datasets (DATA a b c;), RETAIN with
       array references, DO loops with conditional OUTPUT statements.

    Return ONLY:
    {
      "resolved_macros": [{"name":"...","raw_value":"...","source_file":"...","line":<int>}],
      "dependency_order": ["dataset1", ...],
      "risk_flags": ["file.sas:12 — CALL SYMPUT assigns macro at runtime", ...]
    }
""")


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[AnalysisResult]":
    """Instantiate the Pydantic AI agent for SAS analysis.

    When ``TENSORZERO_GATEWAY_URL`` is set, routes through TensorZero via an
    OpenAI-compatible endpoint.  When ``AZURE_OPENAI_ENDPOINT`` is set, uses
    Azure OpenAI.  Otherwise falls back to the direct provider string.

    Returns:
        A Pydantic AI Agent configured to return AnalysisResult outputs.
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
        output_type=AnalysisResult,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class AnalysisAgent:
    """Analyses SAS source files via a single LLM call and returns a JobContext."""

    def __init__(self) -> None:
        """Instantiate AnalysisAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[AnalysisResult] = _make_agent()

    async def analyse(
        self,
        source_files: dict[str, str],
        macro_vars: list[MacroVar],
        blocks: list[SASBlock],
    ) -> JobContext:
        """Run LLM analysis on the provided SAS sources.

        Args:
            source_files: Mapping of filename → raw SAS source text.
            macro_vars: Pre-resolved macro variables from the parser.
            blocks: Parsed SAS blocks from the parser.

        Returns:
            A JobContext with source_files, resolved_macros, dependency_order,
            risk_flags, and blocks populated. generated is empty, reconciliation
            is None.

        Raises:
            AnalysisError: If the LLM call fails after retries.
        """
        prompt = _build_prompt(source_files, macro_vars)
        try:
            result = await self._agent.run(
                prompt,
                model_settings={"max_tokens": 8000},
            )
        except Exception as exc:
            logger.exception("AnalysisAgent LLM call failed")
            raise AnalysisError(f"AnalysisAgent failed: {exc}", cause=exc) from exc

        analysis: AnalysisResult = result.output  # type: ignore[assignment]
        return JobContext(
            source_files=source_files,
            resolved_macros=analysis.resolved_macros,
            dependency_order=analysis.dependency_order,
            risk_flags=analysis.risk_flags,
            blocks=blocks,
            generated=[],
            reconciliation=None,
        )


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(
    source_files: dict[str, str],
    macro_vars: list[MacroVar],
) -> str:
    """Build the user-facing prompt from source files and pre-resolved macros.

    Args:
        source_files: Mapping of filename → raw SAS source text.
        macro_vars: Pre-resolved macro variables from the parser.

    Returns:
        A formatted prompt string for the LLM.
    """
    parts: list[str] = []

    parts.append("## Pre-resolved macro variables")
    if macro_vars:
        for mv in macro_vars:
            parts.append(
                f"  - {mv.name} = {mv.raw_value!r}  (declared in {mv.source_file}:{mv.line})"
            )
    else:
        parts.append("  (none)")

    parts.append("")
    parts.append("## SAS source files")
    for filename, content in source_files.items():
        parts.append(f"\n### {filename}\n```sas\n{content}\n```")

    return "\n".join(parts)
