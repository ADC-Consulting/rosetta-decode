"""LLM client — translates a single SASBlock into Python via a Pydantic AI agent.

The provider and model are resolved entirely from the ``LLM_MODEL`` environment
variable (e.g. ``anthropic:claude-sonnet-4-6``).  No provider-specific code
exists here; swapping models requires only an env-var change.
"""

import textwrap
from typing import cast

from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from src.worker.core.config import worker_settings
from src.worker.engine.models import BlockType, GeneratedBlock, SASBlock

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert SAS-to-Python migration engineer.

    Your job is to translate a single SAS construct (DATA step or PROC SQL block)
    into equivalent Python code that works with pandas DataFrames.

    Rules you MUST follow:
    1. Every logical group of lines you generate must end with a provenance comment
       in the form:  # SAS: <source_file>:<line_number>
       Use the start_line of the block for all lines if no finer grain is available.
    2. Do NOT emit pandas-specific idioms that have no PySpark equivalent.
       Use parameterised DataFrame operations (e.g. df["col"] rather than df.col).
    3. If you cannot reliably translate the construct, set is_untranslatable=True
       and put the reason in python_code as a single comment:
       # SAS-UNTRANSLATABLE: <reason>
    4. Assume input DataFrames are already available as local variables named after
       the SAS dataset (lowercased).  Your output code should assign the result to
       the output dataset name (lowercased).
    5. Return ONLY the python_code string and the is_untranslatable flag.
       Do not include markdown fences or explanatory prose.
""")

# ── Agent ─────────────────────────────────────────────────────────────────────


def _make_agent() -> "Agent[GeneratedBlock]":
    """Instantiate the Pydantic AI agent using the configured model.

    Returns:
        A Pydantic AI Agent configured to return GeneratedBlock outputs.
    """
    model: KnownModelName = worker_settings.llm_model  # type: ignore[assignment]
    # pydantic-ai overloads default to str output; GeneratedBlock works at runtime.
    return Agent(  # type: ignore[arg-type, return-value]
        model=model,
        output_type=GeneratedBlock,
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Public API ────────────────────────────────────────────────────────────────


class LLMClient:
    """Translates individual SAS blocks to Python using a hosted LLM."""

    def __init__(self) -> None:
        """Instantiate the Pydantic AI agent from the configured LLM_MODEL."""
        self._agent: Agent[GeneratedBlock] = _make_agent()

    def translate(self, block: SASBlock) -> GeneratedBlock:
        """Translate *block* into Python via the configured LLM.

        For UNTRANSLATABLE blocks the LLM is not called; a comment is returned
        immediately so we do not waste tokens on blocks we know can't be handled.

        Args:
            block: The parsed SAS construct to translate.

        Returns:
            GeneratedBlock with translated Python code and provenance.
        """
        if block.block_type == BlockType.UNTRANSLATABLE:
            reason = block.untranslatable_reason or "no translation rule available"
            code = (
                f"# SAS-UNTRANSLATABLE: {reason}" f"  # SAS: {block.source_file}:{block.start_line}"
            )
            return GeneratedBlock(
                source_block=block,
                python_code=code,
                is_untranslatable=True,
            )

        user_message = self._build_prompt(block)
        result = self._agent.run_sync(user_message)
        generated = cast(GeneratedBlock, result.output)
        return GeneratedBlock(
            source_block=block,
            python_code=generated.python_code,
            is_untranslatable=generated.is_untranslatable,
        )

    @staticmethod
    def _build_prompt(block: SASBlock) -> str:
        """Format the user-turn prompt for a single SAS block.

        Args:
            block: The SAS block to translate.

        Returns:
            Formatted prompt string for the LLM agent.
        """
        return textwrap.dedent(f"""\
            Translate the following SAS {block.block_type.value} block to Python/pandas.

            Source file: {block.source_file}
            Start line:  {block.start_line}
            End line:    {block.end_line}
            Input datasets:  {block.input_datasets}
            Output datasets: {block.output_datasets}

            SAS source:
            {block.raw_sas}
        """)
