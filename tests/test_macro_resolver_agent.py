"""Unit tests for MacroResolverAgent and MacroExpander resolver integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.worker.engine.agents.macro_resolver import MacroResolution, MacroResolverAgent
from src.worker.engine.macro_expander import CannotExpandError, MacroExpander
from src.worker.engine.models import BlockType, JobContext, MacroVar, SASBlock

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_context() -> JobContext:
    return JobContext(
        source_files={"test.sas": ""},
        resolved_macros=[MacroVar(name="ENV", raw_value="PROD", source_file="test.sas", line=1)],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )


def _make_block(raw: str = "DATA out; SET in; RUN;") -> SASBlock:
    return SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="test.sas",
        start_line=1,
        end_line=1,
        raw_sas=raw,
    )


def _make_run_result(resolution: MacroResolution) -> MagicMock:
    mock = MagicMock()
    mock.output = resolution
    return mock


# ── S07 Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_macro_expander_does_not_call_resolver_when_expansion_succeeds() -> None:
    """Resolver agent must NOT be called when MacroExpander handles it deterministically."""
    resolver = MagicMock(spec=MacroResolverAgent)
    resolver.resolve = AsyncMock()

    expander = MacroExpander(resolver=resolver)
    macro_vars = [MacroVar(name="DEPT", raw_value="SALES", source_file="t.sas", line=1)]
    block = _make_block('DATA out; WHERE dept = "&DEPT"; RUN;')
    context = _make_context()

    result = await expander.expand_with_fallback([block], macro_vars, context)

    resolver.resolve.assert_not_called()
    assert result[0].raw_sas == 'DATA out; WHERE dept = "SALES"; RUN;'


@pytest.mark.asyncio
async def test_macro_expander_calls_resolver_on_cannot_expand_error() -> None:
    """Resolver agent IS called when MacroExpander raises CannotExpandError."""
    resolved_text = "DATA out; SET in; WHERE x = 1; RUN;"
    resolver = MagicMock(spec=MacroResolverAgent)
    resolver.resolve = AsyncMock(return_value=resolved_text)

    expander = MacroExpander(resolver=resolver)
    # Parameterised macro — triggers CannotExpandError
    block = _make_block("%my_macro(arg1); DATA out; SET in; RUN;")
    blocks_with_def = [
        SASBlock(
            block_type=BlockType.DATA_STEP,
            source_file="test.sas",
            start_line=1,
            end_line=1,
            raw_sas="%MACRO my_macro(x); DATA out; SET in; WHERE col = &x; RUN; %MEND my_macro;",
        ),
        block,
    ]
    context = _make_context()

    result = await expander.expand_with_fallback(blocks_with_def, [], context)

    resolver.resolve.assert_called_once()
    # The block that triggered the error gets the resolver's expanded text
    expanded_texts = [b.raw_sas for b in result]
    assert resolved_text in expanded_texts


@pytest.mark.asyncio
async def test_cannot_expand_error_reraised_when_resolver_also_fails() -> None:
    """CannotExpandError is re-raised when the LLM resolver cannot resolve either."""
    resolver = MagicMock(spec=MacroResolverAgent)
    resolver.resolve = AsyncMock(side_effect=CannotExpandError("my_macro", "LLM could not resolve"))

    expander = MacroExpander(resolver=resolver)
    block = _make_block("%my_macro(arg1);")
    blocks_with_def = [
        SASBlock(
            block_type=BlockType.DATA_STEP,
            source_file="test.sas",
            start_line=1,
            end_line=1,
            raw_sas="%MACRO my_macro(x); DATA out; SET in; %MEND my_macro;",
        ),
        block,
    ]
    context = _make_context()

    with pytest.raises(CannotExpandError):
        await expander.expand_with_fallback(blocks_with_def, [], context)


@pytest.mark.asyncio
async def test_expand_with_fallback_uses_plain_expand_when_no_resolver() -> None:
    """When resolver=None, expand_with_fallback falls back to plain expand()."""
    expander = MacroExpander()
    macro_vars = [MacroVar(name="X", raw_value="42", source_file="t.sas", line=1)]
    block = _make_block("DATA out; val = &X; RUN;")
    context = _make_context()

    result = await expander.expand_with_fallback([block], macro_vars, context)
    assert "42" in result[0].raw_sas


@pytest.mark.asyncio
async def test_macro_resolver_agent_returns_expanded_text() -> None:
    """MacroResolverAgent.resolve() returns expanded_text when could_resolve=True."""
    agent = MacroResolverAgent()
    resolution = MacroResolution(expanded_text="DATA out; SET in; RUN;", could_resolve=True)
    agent._agent.run = AsyncMock(return_value=_make_run_result(resolution))  # type: ignore[method-assign]

    context = _make_context()
    result = await agent.resolve("%my_macro;", context)

    assert result == "DATA out; SET in; RUN;"


@pytest.mark.asyncio
async def test_macro_resolver_agent_raises_macro_resolver_error_on_llm_failure() -> None:
    """MacroResolverAgent.resolve() raises MacroResolverError when the LLM call throws."""
    from src.worker.engine.agents.macro_resolver import MacroResolverError

    agent = MacroResolverAgent()
    agent._agent.run = AsyncMock(side_effect=RuntimeError("timeout"))  # type: ignore[method-assign]

    context = _make_context()
    with pytest.raises(MacroResolverError) as exc_info:
        await agent.resolve("%bad_macro;", context)

    assert isinstance(exc_info.value.cause, RuntimeError)


def test_macro_resolver_error_stores_cause() -> None:
    """MacroResolverError must expose the cause attribute."""
    from src.worker.engine.agents.macro_resolver import MacroResolverError

    cause = ValueError("root cause")
    err = MacroResolverError("failed", cause=cause)
    assert err.cause is cause
    assert "failed" in str(err)


def test_macro_resolver_system_prompt_tagged() -> None:
    """System prompt must contain the agent tag for TensorZero routing."""
    from src.worker.engine.agents.macro_resolver import _SYSTEM_PROMPT

    assert "# agent: MacroResolverAgent" in _SYSTEM_PROMPT


def test_build_prompt_includes_macro_vars_and_risk_flags() -> None:
    """_build_prompt() must include resolved macro vars, risk flags, and SAS text."""
    from src.worker.engine.agents.macro_resolver import _build_prompt

    context = JobContext(
        source_files={"t.sas": ""},
        resolved_macros=[MacroVar(name="ENV", raw_value="PROD", source_file="t.sas", line=2)],
        dependency_order=[],
        risk_flags=["nested macro"],
        blocks=[],
        generated=[],
    )
    prompt = _build_prompt("%dynamic_macro;", context)

    assert "ENV" in prompt
    assert "PROD" in prompt
    assert "nested macro" in prompt
    assert "%dynamic_macro;" in prompt
