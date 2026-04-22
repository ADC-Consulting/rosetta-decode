"""PlainEnglishAgent — produces a plain-English business summary for a completed migration.

# agent: PlainEnglishAgent
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
from src.worker.engine.models import JobContext

logger = logging.getLogger("src.worker.engine.agents.plain_english")


# ── Output model ──────────────────────────────────────────────────────────────


class PlainEnglishResult(BaseModel):
    """Structured output from the PlainEnglishAgent LLM call."""

    non_technical_doc: str


# ── Error ─────────────────────────────────────────────────────────────────────


class PlainEnglishError(Exception):
    """Raised when the PlainEnglishAgent LLM call fails.

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
    # agent: PlainEnglishAgent

    You are a business communication specialist writing an executive summary for
    a non-technical audience: QC analysts, Finance managers, and senior stakeholders.

    Your task: write a clear, readable business summary of what a data program does —
    after it has been migrated from SAS to Python. The reader has no programming knowledge
    but needs to understand the business purpose, data flow, and outputs well enough to
    sign off on the migration.

    Produce structured Markdown a business stakeholder can read without further editing.

    Required ## sections in this order:

    ## Purpose
    2-3 sentences describing what business problem this program solves and what process
    it automates or supports. Infer the business domain from dataset names, column names,
    and file names.
    Example: If the program processes CLAIMS_PAID joined to MEMBER_ELIGIBILITY →
    "This program supports the monthly reconciliation of insurance claims against
    member eligibility records."

    ## Data and Process Flow
    - What information the program starts with (use business terms: "employee records",
      "claims transactions", "monthly enrolment files" — NOT table or file names).
    - What steps it performs: filtering, matching, aggregating, enriching, scoring, etc.
    - Use business language only (e.g. "matches employee records to their benefit
      elections", "calculates monthly totals per cost centre", "flags exceptions
      that exceed the threshold").

    ## Outputs and Business Value
    - What the program produces — a report, a summary dataset, a score, a flag list.
    - Who would use these outputs and for what decision or action.
    - If reconciliation failed, append: "The outputs from this migration should be
      reviewed manually before being used in production, as some automated checks
      did not pass."

    Return JSON with exactly one field:
    { "markdown": "..." }

    Rules for "markdown":
    - Raw GitHub-Flavored Markdown string with all sections above.
    - Each section MUST start with a ## heading exactly as shown.
    - Within each section, write flowing prose paragraphs — no bullet points.
    - Do NOT wrap the markdown in a code fence inside the JSON value.
    - Do NOT add any preamble before the first ## heading.

    Rules — STRICT:
    - NO technical terms. Do NOT use: DataFrame, pandas, SAS, Python, proc, dataset,
      macro, variable, column, field, SQL, function, code, script, pipeline, ETL, API,
      or any programming concept.
    - DO use business domain language inferred from names in the input.
    - Total length: 8-12 sentences across the three sections.

    No code fences around the JSON object itself.
    Max output: 1200 tokens.
""")


# ── Agent factory ─────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[PlainEnglishResult]":
    """Instantiate the Pydantic AI agent for plain-English summary generation.

    Returns:
        A Pydantic AI Agent configured to return PlainEnglishResult outputs.
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
        output_type=PlainEnglishResult,  # type: ignore[arg-type]
        system_prompt=_SYSTEM_PROMPT,
    )


_AGENT: "Agent[PlainEnglishResult] | None" = None


def _get_agent() -> "Agent[PlainEnglishResult]":
    """Return the singleton PlainEnglishAgent, creating it on first call."""
    global _AGENT
    if _AGENT is None:
        _AGENT = _make_agent()
    return _AGENT


# ── Agent class ───────────────────────────────────────────────────────────────


class PlainEnglishAgent:
    """Generates a plain-English business summary from JobContext metadata."""

    def __init__(self) -> None:
        """Instantiate PlainEnglishAgent and build the underlying pydantic-ai agent."""
        self._agent: Agent[PlainEnglishResult] = _make_agent()

    async def generate(
        self,
        context: JobContext,
        python_code: str,
        recon_summary: str,
    ) -> str:
        """Produce a plain-English business paragraph for a completed migration.

        Args:
            context: The full job context including macros, blocks, and source file names.
            python_code: The assembled Python pipeline code (not passed to LLM directly).
            recon_summary: Human-readable reconciliation summary.

        Returns:
            A plain-English string (3-6 sentences).

        Raises:
            PlainEnglishError: When the LLM call fails.
        """
        prompt = _build_prompt(context, recon_summary)
        try:
            result = await self._agent.run(prompt)
        except Exception as exc:
            raise PlainEnglishError(f"PlainEnglishAgent LLM call failed: {exc}", cause=exc) from exc

        output: PlainEnglishResult = result.output  # type: ignore[assignment]
        return output.non_technical_doc


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_prompt(context: JobContext, recon_summary: str) -> str:
    """Build the compact metadata prompt for plain-English generation.

    Passes only metadata (file names, macro names/values, block summaries) —
    NOT the full source code or generated Python.

    Args:
        context: Full job context.
        recon_summary: Reconciliation summary line.

    Returns:
        Formatted prompt string for the LLM.
    """
    file_names = ", ".join(context.source_files.keys()) or "N/A"

    macro_lines = (
        "\n".join(f'- {m.name} = "{m.raw_value}"' for m in context.resolved_macros) or "None"
    )

    block_lines = (
        "\n".join(
            f"- {b.block_type}: inputs={b.input_datasets}, outputs={b.output_datasets}"
            for b in context.blocks
            if hasattr(b, "input_datasets") and hasattr(b, "output_datasets")
        )
        or "None"
    )

    return "\n".join(
        [
            "## Source file names",
            file_names,
            "",
            "## Macro variables (name = value)",
            macro_lines,
            "",
            "## Block summaries (type: inputs → outputs)",
            block_lines,
            "",
            "## Reconciliation summary",
            recon_summary or "Reconciliation not run.",
        ]
    )
