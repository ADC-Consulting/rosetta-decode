"""LLM client — translates a single SASBlock into Python via a Pydantic AI agent.

The provider and model are resolved entirely from the ``LLM_MODEL`` environment
variable (e.g. ``anthropic:claude-sonnet-4-6``).  No provider-specific code
exists here; swapping models requires only an env-var change.
"""

import logging
import textwrap
import time
from typing import cast

import httpx
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName
from src.worker.core.config import worker_settings
from src.worker.engine.models import BlockType, GeneratedBlock, SASBlock

logger = logging.getLogger("src.worker.engine.llm_client")

_RETRY_DELAYS = (2, 4, 8)


class LLMTranslationError(Exception):
    """Raised when the LLM fails to translate a SAS block.

    Args:
        message: Human-readable description of the failure.
        is_transient: True if the error may succeed on retry (rate-limit, network).
        cause: The underlying exception, if any.
    """

    def __init__(
        self,
        message: str,
        *,
        is_transient: bool,
        cause: BaseException | None = None,
    ) -> None:
        """Initialise LLMTranslationError with transience flag and optional cause."""
        super().__init__(message)
        self.is_transient = is_transient
        self.cause = cause


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior SAS-to-Python/PySpark migration expert with deep knowledge
    of both SAS programming patterns and modern Python data engineering.

    Your job is to translate a single SAS construct into equivalent Python code
    that works with pandas DataFrames locally and is compatible with PySpark idioms.

    Supported SAS constructs and their Python equivalents:
    - DATA step          → pandas DataFrame operations (filter, assign, merge, etc.)
    - PROC SQL           → pandas merge / query / groupby
    - PROC SORT          → df.sort_values(by=[...], ascending=[...])
    - %LET macro vars    → already resolved to Python constants before this call (see rule 6)

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
    6. Macro variable values will already be substituted into the SAS source before
       you see it. Do not attempt to resolve &macrovar references yourself.
    7. When translating PROC SORT, always use df.sort_values(). The by argument
       must be a list. Use ascending=False for DESCENDING.
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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _is_transient_http_error(exc_name: str, exc_str: str) -> bool:
    """Return True when an exception string indicates a retryable HTTP error.

    Checks for HTTP 429 (rate-limit) and 5xx (server-side) status codes in the
    exception message, which pydantic-ai surfaces as plain exceptions without a
    dedicated type hierarchy we can safely import.
    """
    if "429" in exc_str:
        return True
    return any(code in exc_str for code in ("500", "502", "503", "504"))


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
            code = f"# SAS-UNTRANSLATABLE: {reason}  # SAS: {block.source_file}:{block.start_line}"
            return GeneratedBlock(
                source_block=block,
                python_code=code,
                is_untranslatable=True,
            )

        user_message = self._build_prompt(block)
        last_exc: BaseException | None = None

        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            try:
                result = self._agent.run_sync(user_message)
                generated = cast(GeneratedBlock, result.output)
                return GeneratedBlock(
                    source_block=block,
                    python_code=generated.python_code,
                    is_untranslatable=generated.is_untranslatable,
                )
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning(
                    "Attempt %d/%d transient error: %s; retrying in %ds",
                    attempt,
                    len(_RETRY_DELAYS),
                    exc,
                    delay,
                )
                time.sleep(delay)
            except Exception as exc:
                exc_str = str(exc)
                exc_name = type(exc).__name__
                if _is_transient_http_error(exc_name, exc_str):
                    last_exc = exc
                    logger.warning(
                        "Attempt %d/%d transient error: %s; retrying in %ds",
                        attempt,
                        len(_RETRY_DELAYS),
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    raise LLMTranslationError(
                        f"Permanent LLM translation error: {exc}",
                        is_transient=False,
                        cause=exc,
                    ) from exc

        raise LLMTranslationError(
            f"LLM translation failed after {len(_RETRY_DELAYS)} attempts",
            is_transient=True,
            cause=last_exc,
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
