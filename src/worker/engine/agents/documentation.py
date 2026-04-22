"""DocumentationAgent — produces rich Markdown documentation for a completed migration.

# agent: DocumentationAgent
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

logger = logging.getLogger("src.worker.engine.agents.documentation")


# ── Output model ──────────────────────────────────────────────────────────────


class DocumentationResult(BaseModel):
    """Structured output from the DocumentationAgent LLM call."""

    markdown: str


# ── Error ─────────────────────────────────────────────────────────────────────


class DocumentationError(Exception):
    """Raised when the DocumentationAgent LLM call fails.

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
    # agent: DocumentationAgent

    You are a technical documentation expert for SAS-to-Python migrations.
    Produce structured Markdown a business analyst can read without further editing.

    Required ## sections in this order:

    ## Overview
    2-4 sentences describing what this codebase does at a BUSINESS level (not technical).
    Infer domain from dataset/column/variable names.
    Example: dataset CLAIMS_PAID with MEMBER_ID, AMOUNT → insurance claims processing.

    ## Key Datasets
    Table: | Dataset | Role | Row-level description |
    - Role: "Input", "Intermediate", or "Final Output"
    - Row-level description: what one row represents (e.g. "one claim payment per member
      per date"). Infer from column names. Write "Unknown" only if no inference is possible.

    ## Macro Variables
    Table: | Name | Resolved Value | Declared In | Purpose |
    - Purpose: what the macro controls. Infer from usage; write "Unknown" if not clear.

    ## Business Logic
    Numbered list in dependency order. Each item: one sentence stating WHAT HAPPENS
    (avoid pandas/SAS jargon).
    Example: "3. Claims are filtered to the report year and joined to the eligibility table."

    ## Migration Notes
    Bullet list per risk flag or untranslatable block:
    - `file.sas:42` — issue description — recommended action
    Write "No migration issues identified." if none.

    ## Reconciliation Summary
    One sentence stating pass/fail. If failed, list specific failed checks and implications.

    Return JSON with exactly one field:
    { "markdown": "..." }

    Rules for "markdown":
    - Raw GitHub-Flavored Markdown string with all sections above.
    - Do NOT wrap the markdown in a code fence inside the JSON value.
    - Do NOT add any preamble before the first ## heading.

    No code fences around the JSON object itself.
""")


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[DocumentationResult]":
    """Instantiate the Pydantic AI agent for documentation generation.

    Returns:
        A Pydantic AI Agent configured to return DocumentationResult outputs.
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
        output_type=DocumentationResult,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Agent class ───────────────────────────────────────────────────────────────


class DocumentationAgent:
    """Generates rich Markdown documentation from JobContext + generated pipeline."""

    def __init__(self) -> None:
        """Instantiate DocumentationAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[DocumentationResult] = _make_agent()

    async def generate(
        self,
        context: JobContext,
        generated_code: str,
        validation_result: str | None,
    ) -> str:
        """Produce Markdown documentation for a completed migration.

        Args:
            context: The full job context including macros, dependency order, and flags.
            generated_code: The assembled Python pipeline code.
            validation_result: Human-readable reconciliation summary, or None if not run.

        Returns:
            A GitHub-Flavored Markdown string with all documentation sections.

        Raises:
            DocumentationError: When the LLM call fails.
        """
        prompt = _build_prompt(context, generated_code, validation_result)
        try:
            result = await self._agent.run(prompt)
        except Exception as exc:
            raise DocumentationError(
                f"DocumentationAgent LLM call failed: {exc}", cause=exc
            ) from exc

        return cast(DocumentationResult, result.output).markdown


def _build_prompt(
    context: JobContext,
    generated_code: str,
    validation_result: str | None,
) -> str:
    """Build the user prompt for documentation generation.

    Args:
        context: Full job context.
        generated_code: Assembled Python pipeline.
        validation_result: Reconciliation summary or None.

    Returns:
        Formatted prompt string for the LLM.
    """
    sources_section = "\n\n".join(
        f"### {name}\n```sas\n{content}\n```" for name, content in context.source_files.items()
    )

    macro_lines = "\n".join(
        f'- {m.name} = "{m.raw_value}"  ({m.source_file}:{m.line})' for m in context.resolved_macros
    )

    risk_lines = "\n".join(f"- {flag}" for flag in context.risk_flags)
    dep_order = ", ".join(context.dependency_order) or "N/A"
    recon_summary = validation_result or "Reconciliation not run."

    return "\n".join(
        [
            "## Source files",
            sources_section,
            "",
            "## Resolved macro variables",
            macro_lines or "None",
            "",
            "## Dependency order",
            dep_order,
            "",
            "## Risk flags",
            risk_lines or "None",
            "",
            "## Generated Python pipeline",
            "```python",
            generated_code,
            "```",
            "",
            "## Reconciliation summary",
            recon_summary,
        ]
    )
