"""Unit tests for MacroExpander."""

import pytest
from src.worker.engine.macro_expander import CannotExpand, MacroExpander
from src.worker.engine.models import BlockType, MacroVar, SASBlock


def _block(raw: str, source_file: str = "test.sas", start: int = 1, end: int = 5) -> SASBlock:
    return SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file=source_file,
        start_line=start,
        end_line=end,
        raw_sas=raw,
        input_datasets=[],
        output_datasets=[],
    )


def _var(name: str, value: str) -> MacroVar:
    return MacroVar(name=name, raw_value=value, source_file="test.sas", line=1)


expander = MacroExpander()


# ── %LET substitution ──────────────────────────────────────────────────────────


def test_let_simple_substitution() -> None:
    blocks = [_block("DATA &MYVAR; RUN;")]
    result = expander.expand(blocks, [_var("MYVAR", "work.out")])
    assert result[0].raw_sas == "DATA work.out; RUN;"


def test_let_dot_terminated_form() -> None:
    """&NAME. — the trailing dot is consumed and not present in output."""
    blocks = [_block("DATA &MYVAR.suffix; RUN;")]
    result = expander.expand(blocks, [_var("MYVAR", "work.out")])
    assert result[0].raw_sas == "DATA work.outsuffix; RUN;"


def test_let_case_insensitive_reference() -> None:
    """&name (lowercase) should match macro var stored as NAME (uppercase)."""
    blocks = [_block("SET &name;")]
    result = expander.expand(blocks, [_var("NAME", "work.ds")])
    assert result[0].raw_sas == "SET work.ds;"


def test_no_macro_vars_returns_unchanged() -> None:
    blocks = [_block("DATA work.a; RUN;")]
    result = expander.expand(blocks, [])
    assert result[0].raw_sas == "DATA work.a; RUN;"


# ── %MACRO/%MEND inlining ──────────────────────────────────────────────────────


def test_zero_arg_macro_inlined() -> None:
    macro_def = "%MACRO CLEANUP;\n  DELETE work.tmp;\n%MEND CLEANUP;"
    call_block = _block("%CLEANUP;")
    def_block = _block(macro_def)
    result = expander.expand([def_block, call_block], [])
    # call site should have been replaced by macro body
    assert "DELETE work.tmp" in result[1].raw_sas


def test_cannot_expand_if_inside_macro() -> None:
    macro_def = "%MACRO BAD;\n  %IF &X = 1 %THEN DO; x=1; %END;\n%MEND BAD;"
    call_block = _block("%BAD;")
    def_block = _block(macro_def)
    with pytest.raises(CannotExpand) as exc_info:
        expander.expand([def_block, call_block], [])
    assert "BAD" in str(exc_info.value)
    assert "%IF" in exc_info.value.reason or "conditional" in exc_info.value.reason


def test_cannot_expand_parameterised_macro() -> None:
    macro_def = "%MACRO WITHPARAM(dsn);\n  DATA &dsn; RUN;\n%MEND WITHPARAM;"
    call_block = _block("%WITHPARAM(work.x);")
    def_block = _block(macro_def)
    with pytest.raises(CannotExpand) as exc_info:
        expander.expand([def_block, call_block], [])
    assert "WITHPARAM" in str(exc_info.value)


def test_cannot_expand_undefined_macro_call() -> None:
    """A call to an unknown macro with explicit arg list raises CannotExpand."""
    call_block = _block("%UNKNOWN(arg1);")
    with pytest.raises(CannotExpand) as exc_info:
        expander.expand([call_block], [])
    assert "UNKNOWN" in str(exc_info.value)


def test_block_with_no_macro_calls_unchanged() -> None:
    """A block with no macro calls must pass through even if other blocks define macros."""
    macro_def = "%MACRO CLEAN;\n  DELETE work.tmp;\n%MEND CLEAN;"
    safe_block = _block("DATA work.a; x=1; RUN;")
    def_block = _block(macro_def)
    result = expander.expand([def_block, safe_block], [])
    assert result[1].raw_sas == "DATA work.a; x=1; RUN;"


# ── Immutability ───────────────────────────────────────────────────────────────


def test_input_blocks_not_mutated() -> None:
    original_raw = "DATA &DS; RUN;"
    block = _block(original_raw)
    result = expander.expand([block], [_var("DS", "work.out")])
    # original block unchanged
    assert block.raw_sas == original_raw
    # returned block is a new object
    assert result[0] is not block
    assert result[0].raw_sas == "DATA work.out; RUN;"
