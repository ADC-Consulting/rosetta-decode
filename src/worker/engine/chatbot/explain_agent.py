"""ExplainAgent — streaming chatbot for SAS migration and general SAS questions.

Uses a 4-agent cache keyed on (mode, audience) to avoid re-creating agents per request.
"""

from collections.abc import AsyncGenerator

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.openai import OpenAIProvider
from src.worker.core.config import worker_settings

# SAS: explain_agent.py:1

# ── System prompt layers ──────────────────────────────────────────────────────

_BASE_SYSTEM_PROMPT = (
    "You are an expert assistant built into Rosetta, a SAS-to-Python migration tool. "
    "\n\n"
    "ACCURACY: Never invent code, variable names, column names, or logic not present in "
    "the provided context. If uncertain, say so explicitly rather than guessing. "
    "\n\n"
    "FORMAT: Answer only what is asked — no preamble, no closing summaries unless requested. "
    "Always render code in fenced blocks with the correct language tag: `python`, `sas`, or `sql`. "
    "\n\n"
    "LIMITATIONS: If the context is insufficient to answer accurately, state exactly what "
    "information is missing rather than speculating."
)

_MODE_PROMPTS: dict[str, str] = {
    "migration": (
        "SCOPE: Your knowledge is strictly limited to the migration artefacts provided in this "
        "conversation (migration plan, generated Python/PySpark code, lineage graph, "
        "documentation). "
        "If a question is not about these artefacts, politely decline and explain that "
        "you can only answer questions about the current migration. "
        "\n\n"
        "CITATIONS: When referencing code, always cite the exact file name and line number "
        "(e.g. 'output.py line 42')."
    ),
    "sas_general": (
        "SCOPE: You are a broad SAS expert. Answer any question about SAS — syntax, PROC steps, "
        "macro language, data steps, performance, migration patterns — whether or not a file has "
        "been uploaded. If a file is provided, use it as supplementary context. "
        "\n\n"
        "KNOWLEDGE: Draw on your full knowledge of SAS, including legacy SAS 9.x and modern "
        "Viya features. When relevant, mention how the SAS concept maps to "
        "Python/PySpark equivalents."
    ),
}

_AUDIENCE_PROMPTS: dict[str, str] = {
    "tech": (
        "AUDIENCE: You are speaking to a data engineer. Be precise, technical, and use correct "
        "SAS and Python/PySpark terminology. Concise answers are preferred."
    ),
    "non_tech": (
        "AUDIENCE: You are speaking to a business stakeholder — an analyst or manager. "
        "Use plain, everyday language. Spell out every abbreviation on first use. "
        "Do not include code unless the user explicitly asks for it. "
        "Give short, clear answers with bullet points. Avoid walls of text."
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_system_prompt(mode: str, audience: str) -> str:
    """Compose the 3-layer system prompt from base, mode, and audience sections.

    Args:
        mode: One of ``"migration"`` or ``"sas_general"``.
        audience: One of ``"tech"`` or ``"non_tech"``.

    Returns:
        A single system prompt string with layers separated by blank lines.
    """
    return "\n\n".join(
        [
            _BASE_SYSTEM_PROMPT,
            _MODE_PROMPTS.get(mode, _MODE_PROMPTS["sas_general"]),
            _AUDIENCE_PROMPTS.get(audience, _AUDIENCE_PROMPTS["tech"]),
        ]
    )


def _make_agent(system_prompt: str) -> "Agent[None, str]":
    """Instantiate a Pydantic AI streaming agent with the given system prompt.

    Respects TensorZero gateway and Azure OpenAI configuration from worker_settings,
    falling back to the direct provider string otherwise.

    Args:
        system_prompt: The composed system prompt to use.

    Returns:
        A Pydantic AI Agent configured for plain-text streaming output.
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
        output_type=str,
        system_prompt=system_prompt,
    )


# ── ExplainAgent ──────────────────────────────────────────────────────────────


class ExplainAgent:
    """Streaming chatbot agent for the Rosetta explain feature.

    Maintains a cache of 4 pre-built agents keyed on (mode, audience) to avoid
    re-initialising agents per request.
    """

    def __init__(self) -> None:
        """Build the 4-agent cache at construction time."""
        self._agents: dict[tuple[str, str], Agent[None, str]] = {
            (m, a): _make_agent(_build_system_prompt(m, a))
            for m in ("migration", "sas_general")
            for a in ("tech", "non_tech")
        }

    def _get_agent(self, mode: str, audience: str) -> "Agent[None, str]":
        """Return the cached agent for the given mode and audience.

        Falls back to ``("sas_general", "tech")`` for unknown combinations.

        Args:
            mode: Conversation mode — ``"migration"`` or ``"sas_general"``.
            audience: Target audience — ``"tech"`` or ``"non_tech"``.

        Returns:
            The matching pre-built Pydantic AI agent.
        """
        return self._agents.get((mode, audience), self._agents[("sas_general", "tech")])

    async def answer_stream(
        self,
        prompt: str,
        audience: str = "tech",
        mode: str = "migration",
    ) -> AsyncGenerator[str, None]:
        """Stream an answer to the given prompt.

        Args:
            prompt: The user's question or message.
            audience: Target audience — ``"tech"`` (default) or ``"non_tech"``.
            mode: Conversation mode — ``"migration"`` (default) or ``"sas_general"``.

        Yields:
            Text delta chunks from the LLM stream.
        """
        agent = self._get_agent(mode, audience)
        async with agent.run_stream(prompt) as stream:
            async for chunk in stream.stream_text(delta=True):
                yield chunk
