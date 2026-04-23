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

    You are a business communication specialist writing a structured executive summary
    for a non-technical audience: QC analysts, Finance managers, and senior stakeholders.

    Your task: produce a well-structured, scannable business document describing what a
    migrated data program does. The reader has no technical background but must be able to
    understand the business purpose, data inputs, process steps, and outputs well enough
    to sign off on the migration.

    Produce structured Markdown using the exact sections below, in order.

    ---

    ## Purpose
    One short paragraph (2-3 sentences). State what business problem this program solves
    and what recurring process it automates. Infer the domain from file names, dataset
    names, and macro variable names — do not guess beyond what the input tells you.

    ## Source Data
    A bullet list. Each bullet names one category of input information in plain business
    terms (e.g. "Customer records", "Daily transaction history", "Exchange rates by
    currency", "Product catalogue"). Do not use file names or technical identifiers.
    3-6 bullets.

    ## How It Works
    A numbered list of the main processing steps in plain business language. Each step
    should be one short sentence describing what happens to the data at that stage
    (e.g. "1. Transactions are converted to euros using the applicable daily exchange
    rate.", "2. Each transaction is matched to its product and customer record.",
    "3. Daily totals are calculated per product category."). 4-7 steps.

    ## Outputs
    A bullet list. Each bullet describes one output: what it is, who uses it, and for
    what decision or action (e.g. "**Daily revenue summary** — used by Finance to
    reconcile actual vs. forecast revenue each morning."). 2-4 bullets.
    If reconciliation checks did not pass, add a final bullet:
    "⚠ **Review required** — some automated quality checks did not pass. Outputs should
    be verified manually before use in production."

    ## Migration Status
    One sentence summarising the outcome: either "All quality checks passed — this
    program is ready for production use." or "Quality checks did not fully pass —
    manual review is recommended before promoting to production."

    ---

    Return JSON with exactly one field:
    { "non_technical_doc": "..." }

    Rules for "non_technical_doc":
    - Raw GitHub-Flavored Markdown string with all five sections above.
    - Each section MUST start with ## exactly as shown.
    - Use bullet lists (- item) and numbered lists (1. item) as specified per section.
    - Bold key terms in Outputs bullets using **bold**.
    - Do NOT use prose paragraphs in list sections.
    - Do NOT wrap the markdown in a code fence inside the JSON value.
    - Do NOT add any preamble before the first ## heading.

    Language rules — STRICT:
    - NO technical terms. Do NOT use: DataFrame, pandas, SAS, Python, proc, dataset,
      macro, variable, column, field, SQL, function, code, script, pipeline, ETL, API,
      migration, or any programming concept.
    - DO use business domain language inferred from names in the input.
    - Spell out all abbreviations on first use.

    No code fences around the JSON object itself.
    Max output: 1800 tokens.
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
