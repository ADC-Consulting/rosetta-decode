"""ExplainAgent — audience-aware streaming Q&A for the Explain page."""

from collections.abc import AsyncGenerator

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider
from src.worker.core.config import worker_settings


def _make_agent(system_prompt: str = "") -> "Agent[None, str]":
    """Build a pydantic-ai Agent for explain streaming.

    Args:
        system_prompt: System prompt to inject at construction time.

    Returns:
        Configured Agent instance for string output.
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

    return Agent(model_obj, output_type=str, system_prompt=system_prompt)


_TECH_SYSTEM_PROMPT = (
    "You are an expert SAS-to-Python migration assistant for the Rosetta tool. "
    "Your knowledge is strictly limited to the migration context supplied in each conversation "
    "(generated Python/PySpark code, migration plan, lineage graph, documentation). "
    "If a question is not about the provided migration artefacts, politely decline and explain "
    "that you can only answer questions about the current migration context. "
    "\n\n"
    "ACCURACY: Never invent code, variable names, column names, or logic that does not appear "
    "in the provided context. If you are uncertain about something, say so explicitly rather "
    "than guessing. "
    "\n\n"
    "CITATIONS: When referencing any code, always cite the exact file name and line number "
    "(e.g. 'output.py line 42'). "
    "Always render code in fenced blocks with the correct language tag: "
    "`python`, `sas`, or `sql`. "
    "\n\n"
    "FORMAT: Answer only what is asked — no preamble, no closing summaries unless requested. "
    "Use markdown headers and bullet lists only when they genuinely improve clarity. "
    "\n\n"
    "AUDIENCE: You are speaking to a data engineer. Be precise, technical, and use correct "
    "SAS and Python/PySpark terminology. "
    "\n\n"
    "LIMITATIONS: If the provided context is insufficient to answer accurately, state exactly "
    "what information is missing (e.g. 'The lineage graph was not included in this context') "
    "rather than speculating."
)

_NON_TECH_SYSTEM_PROMPT = (
    "You are a plain-English explainer for a SAS-to-Python migration produced by the Rosetta "
    "tool. Your role is to help business stakeholders — analysts and managers — understand "
    "what changed in their data pipelines, why it matters, and what it means for their data "
    "outputs. "
    "Your knowledge is strictly limited to the migration context supplied in each conversation. "
    "If a question is not about the provided migration, politely decline and explain that you "
    "can only answer questions about this migration. "
    "\n\n"
    "LANGUAGE: Use plain, everyday business language. Spell out any abbreviation or acronym on "
    "first use (e.g. 'ETL (Extract, Transform, Load)'). Do not include code unless the user "
    "explicitly asks for it. "
    "\n\n"
    "ACCURACY: Do not invent business logic, data transformations, or outcomes that are not "
    "present in the migration context. If you are unsure, say so. "
    "\n\n"
    "FORMAT: Give short, clear answers. Use bullet points for lists. Avoid walls of text. "
    "Answer only what is asked — no unnecessary preamble or summaries. "
    "\n\n"
    "LIMITATIONS: If the context is insufficient to answer accurately, tell the user what "
    "additional information would be needed (e.g. 'The data dictionary was not provided')."
)


class ExplainAgent:
    """Audience-aware streaming Q&A agent for the Explain page."""

    def __init__(self) -> None:
        """Initialise the ExplainAgent with tech and non_tech agents."""
        self._tech_agent: Agent[None, str] = _make_agent(_TECH_SYSTEM_PROMPT)
        self._non_tech_agent: Agent[None, str] = _make_agent(_NON_TECH_SYSTEM_PROMPT)

    def _get_agent(self, audience: str) -> "Agent[None, str]":
        """Select agent by audience.

        Args:
            audience: "tech" or "non_tech".

        Returns:
            The appropriate Agent instance.
        """
        return self._non_tech_agent if audience == "non_tech" else self._tech_agent

    async def answer_stream(
        self,
        prompt: str,
        audience: str = "tech",
    ) -> AsyncGenerator[str, None]:
        """Stream answer text chunks.

        Args:
            prompt: The full prompt (including context) to send to the LLM.
            audience: "tech" or "non_tech" — controls system prompt tone.

        Yields:
            Text chunks as they arrive from the LLM.
        """
        agent = self._get_agent(audience)
        async with agent.run_stream(prompt) as stream:
            async for chunk in stream.stream_text(delta=True):
                yield chunk
