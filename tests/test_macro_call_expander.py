"""Unit tests for src.worker.engine.macro_call_expander — all public functions."""

import pytest
from src.worker.engine.macro_call_expander import (
    _is_expandable,
    bind_args,
    expand_macro_calls,
    parse_call_args,
    parse_macro_params,
)
from src.worker.engine.models import MacroDef

# ---------------------------------------------------------------------------
# parse_macro_params
# ---------------------------------------------------------------------------


def test_parse_macro_params_empty() -> None:
    assert parse_macro_params("") == []


def test_parse_macro_params_positional_only() -> None:
    assert parse_macro_params("a, b, c") == [("a", None), ("b", None), ("c", None)]


def test_parse_macro_params_keyword_no_default() -> None:
    assert parse_macro_params("in=, out=") == [("in", ""), ("out", "")]


def test_parse_macro_params_keyword_with_default() -> None:
    assert parse_macro_params("by=USUBJID") == [("by", "USUBJID")]


def test_parse_macro_params_mixed() -> None:
    assert parse_macro_params("in=, out=, by=USUBJID") == [
        ("in", ""),
        ("out", ""),
        ("by", "USUBJID"),
    ]


# ---------------------------------------------------------------------------
# parse_call_args
# ---------------------------------------------------------------------------


def test_parse_call_args_empty() -> None:
    assert parse_call_args("") == ([], {})


def test_parse_call_args_positional_only() -> None:
    positional, keyword = parse_call_args("val1, val2")
    assert positional == ["val1", "val2"]
    assert keyword == {}


def test_parse_call_args_keyword_only() -> None:
    positional, keyword = parse_call_args("in=sdtm.ex, out=work.dose")
    assert positional == []
    assert keyword == {"in": "sdtm.ex", "out": "work.dose"}


def test_parse_call_args_mixed() -> None:
    positional, keyword = parse_call_args("sdtm.ex, out=work.dose")
    assert positional == ["sdtm.ex"]
    assert keyword == {"out": "work.dose"}


# ---------------------------------------------------------------------------
# bind_args
# ---------------------------------------------------------------------------


def test_bind_args_keyword_wins_over_default() -> None:
    params: list[tuple[str, str | None]] = [("by", "USUBJID")]
    result = bind_args(params, [], {"by": "SUBJECTID"})
    assert result == {"by": "SUBJECTID"}


def test_bind_args_default_fallback() -> None:
    params: list[tuple[str, str | None]] = [("by", "USUBJID")]
    result = bind_args(params, [], {})
    assert result == {"by": "USUBJID"}


def test_bind_args_positional_fill() -> None:
    params: list[tuple[str, str | None]] = [("a", None), ("b", None)]
    result = bind_args(params, ["x", "y"], {})
    assert result == {"a": "x", "b": "y"}


def test_bind_args_missing_required_raises() -> None:
    params: list[tuple[str, str | None]] = [("in", "")]
    with pytest.raises(ValueError):
        bind_args(params, [], {})


def test_bind_args_case_insensitive_keyword_match() -> None:
    params: list[tuple[str, str | None]] = [("IN", "")]
    result = bind_args(params, [], {"in": "sdtm.ex"})
    assert result == {"IN": "sdtm.ex"}


# ---------------------------------------------------------------------------
# _is_expandable
# ---------------------------------------------------------------------------


def test_is_expandable_clean_body() -> None:
    body = "proc sql; create table work.out as select * from sdtm.ex; quit;"
    assert _is_expandable(body) is True


def test_is_expandable_body_with_if() -> None:
    body = "proc sql; quit; %if &debug %then %put debug on;"
    assert _is_expandable(body) is False


def test_is_expandable_body_with_let_uppercase() -> None:
    body = "data work.out; set in; run; %LET x = 1;"
    assert _is_expandable(body) is False


def test_is_expandable_body_with_do() -> None:
    body = "data work.out; %do i = 1 %to 5; x = &i; %end; run;"
    assert _is_expandable(body) is False


def test_is_expandable_body_with_global() -> None:
    body = "%global myvar; data work.out; set in; run;"
    assert _is_expandable(body) is False


def test_is_expandable_body_with_return() -> None:
    body = "data work.out; set in; %return; run;"
    assert _is_expandable(body) is False


# ---------------------------------------------------------------------------
# expand_macro_calls
# ---------------------------------------------------------------------------

_FIRST_DOSE_BODY = "proc sql; create table &out as select * from &in; quit;"

_FIRST_DOSE_BODY_WITH_BY = "proc sql; create table &out as select * from &in order by &by; quit;"


def _first_dose_macro(body: str = _FIRST_DOSE_BODY, param_str: str = "in=, out=") -> MacroDef:
    return MacroDef(
        name="M_FIRST_DOSE",
        param_str=param_str,
        body=body,
        source_file="m_first_dose.sas",
        line=1,
    )


def test_expand_unknown_macro_left_untouched() -> None:
    source = "%unknown_macro(a=1);"
    result = expand_macro_calls(source, {})
    assert result == source


def test_expand_non_expandable_macro_left_untouched() -> None:
    body_with_if = "data work.out; set in; %if &debug %then %put on; run;"
    macro = MacroDef(
        name="MYMACRO",
        param_str="a=",
        body=body_with_if,
        source_file="mymacro.sas",
        line=1,
    )
    source = "%mymacro(a=1);"
    result = expand_macro_calls(source, {"MYMACRO": macro})
    assert result == source


def test_expand_basic_substitution() -> None:
    macro = _first_dose_macro()
    source = "%m_first_dose(in=sdtm.ex, out=work.dose);"
    result = expand_macro_calls(source, {"M_FIRST_DOSE": macro})
    assert "work.dose" in result
    assert "sdtm.ex" in result
    assert "SAS-MACRO-EXPANDED: M_FIRST_DOSE" in result
    assert "%m_first_dose" not in result.lower()


def test_expand_default_parameter_substituted() -> None:
    macro = _first_dose_macro(
        body=_FIRST_DOSE_BODY_WITH_BY,
        param_str="in=, out=, by=USUBJID",
    )
    source = "%m_first_dose(in=sdtm.ex, out=work.dose);"
    result = expand_macro_calls(source, {"M_FIRST_DOSE": macro})
    assert "USUBJID" in result


def test_expand_cycle_guard_terminates() -> None:
    # A calls B, B calls A — mutual recursion must not loop.
    macro_a = MacroDef(
        name="A",
        param_str="",
        body="%b();",
        source_file="a.sas",
        line=1,
    )
    macro_b = MacroDef(
        name="B",
        param_str="",
        body="%a();",
        source_file="b.sas",
        line=1,
    )
    source = "%a();"
    # Must return in finite time and not raise.
    result = expand_macro_calls(source, {"A": macro_a, "B": macro_b})
    assert isinstance(result, str)


def test_expand_nested_expansion_fixed_point() -> None:
    # A's body calls B; B is expandable. After expansion B's body is inlined.
    macro_b = MacroDef(
        name="B",
        param_str="",
        body="proc sql; select 1; quit;",
        source_file="b.sas",
        line=1,
    )
    macro_a = MacroDef(
        name="A",
        param_str="",
        body="%b();",
        source_file="a.sas",
        line=1,
    )
    source = "%a();"
    result = expand_macro_calls(source, {"A": macro_a, "B": macro_b})
    # B's body must appear in the final output.
    assert "proc sql; select 1; quit;" in result
    # Neither call site should remain.
    assert "%a(" not in result.lower()
    assert "%b(" not in result.lower()
