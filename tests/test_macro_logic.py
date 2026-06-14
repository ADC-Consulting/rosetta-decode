"""Unit tests for src.worker.engine.macro_logic — F59 macro control-flow evaluator."""

import pytest
from src.worker.engine.macro_logic import (
    MAX_UNROLL,
    CannotResolveMacroLogic,
    _tokenize,
    evaluate_condition,
    resolve_macro_body,
)

# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------


def test_tokenize_strips_block_and_macro_comments() -> None:
    body = "data x; /* block comment */ %* macro comment ; set y; run;"
    tokens = _tokenize(body)
    joined = "".join(tok.text for tok in tokens)
    assert "block comment" not in joined
    assert "macro comment" not in joined
    assert "data x" in joined
    assert "set y" in joined


def test_tokenize_if_then_do_end_order() -> None:
    body = "%if &x = 1 %then %do; data a; run; %end;"
    tokens = _tokenize(body)
    kinds = [tok.kind for tok in tokens]
    assert kinds[:3] == ["MIF", "MTHEN", "MDO_BLOCK"]
    assert "MEND" in kinds
    mif = next(tok for tok in tokens if tok.kind == "MIF")
    assert mif.text == "&x = 1"


def test_tokenize_do_iter() -> None:
    tokens = _tokenize("%do i=1 %to 3;")
    iter_tokens = [tok for tok in tokens if tok.kind == "MDO_ITER"]
    assert len(iter_tokens) == 1


def test_tokenize_do_while() -> None:
    tokens = _tokenize("%do %while(x);")
    assert any(tok.kind == "MDO_WHILE" for tok in tokens)


def test_tokenize_do_until() -> None:
    tokens = _tokenize("%do %until(x);")
    assert any(tok.kind == "MDO_UNTIL" for tok in tokens)


def test_tokenize_do_block() -> None:
    tokens = _tokenize("%do;")
    assert any(tok.kind == "MDO_BLOCK" for tok in tokens)


def test_tokenize_plain_sas_becomes_sas_text() -> None:
    tokens = _tokenize("proc print data=adsl; run;")
    assert len(tokens) == 1
    assert tokens[0].kind == "SAS_TEXT"
    assert "proc print data=adsl" in tokens[0].text


# ---------------------------------------------------------------------------
# evaluate_condition — returns bool
# ---------------------------------------------------------------------------


def test_evaluate_condition_simple_true() -> None:
    assert evaluate_condition("&in = 1", {"IN": "1"}) is True


def test_evaluate_condition_simple_false() -> None:
    assert evaluate_condition("&in = 1", {"IN": "2"}) is False


def test_evaluate_condition_length_nonempty_false() -> None:
    assert evaluate_condition("%length(&in) = 0", {"IN": "work.adsl_pre"}) is False


def test_evaluate_condition_length_empty_true() -> None:
    assert evaluate_condition("%length(&in) = 0", {"IN": ""}) is True


def test_evaluate_condition_op_eq() -> None:
    assert evaluate_condition("&x = 5", {"X": "5"}) is True
    assert evaluate_condition("&x eq 5", {"X": "5"}) is True


def test_evaluate_condition_op_ne() -> None:
    assert evaluate_condition("&x ne 5", {"X": "6"}) is True
    assert evaluate_condition("&x ^= 5", {"X": "5"}) is False


def test_evaluate_condition_op_lt() -> None:
    assert evaluate_condition("&x < 5", {"X": "4"}) is True
    assert evaluate_condition("&x lt 5", {"X": "6"}) is False


def test_evaluate_condition_op_gt() -> None:
    assert evaluate_condition("&x > 5", {"X": "6"}) is True
    assert evaluate_condition("&x gt 5", {"X": "4"}) is False


def test_evaluate_condition_op_le() -> None:
    assert evaluate_condition("&x <= 5", {"X": "5"}) is True
    assert evaluate_condition("&x le 5", {"X": "6"}) is False


def test_evaluate_condition_op_ge() -> None:
    assert evaluate_condition("&x >= 5", {"X": "5"}) is True
    assert evaluate_condition("&x ge 5", {"X": "4"}) is False


def test_evaluate_condition_numeric_leading_zero_true() -> None:
    # Both 1 and 01 match ^-?\d+$ -> numeric compare -> equal.
    assert evaluate_condition("&x = 01", {"X": "1"}) is True


def test_evaluate_condition_string_equal_true() -> None:
    assert evaluate_condition("&x = abc", {"X": "abc"}) is True


def test_evaluate_condition_string_case_sensitive_false() -> None:
    assert evaluate_condition("&x = ABC", {"X": "abc"}) is False


def test_evaluate_condition_and_or_parens_true() -> None:
    env = {"A": "1", "B": "2", "C": "9"}
    assert evaluate_condition("(&a = 1 and &b = 2) or &c = 3", env) is True


def test_evaluate_condition_and_or_parens_false() -> None:
    env = {"A": "0", "B": "2", "C": "9"}
    assert evaluate_condition("(&a = 1 and &b = 2) or &c = 3", env) is False


# ---------------------------------------------------------------------------
# evaluate_condition — returns None (never raises)
# ---------------------------------------------------------------------------


def test_evaluate_condition_unresolved_ref_none() -> None:
    assert evaluate_condition("&missing = 1", {}) is None


def test_evaluate_condition_unsupported_function_none() -> None:
    assert evaluate_condition("%sysfunc(today()) = 1", {}) is None


def test_evaluate_condition_malformed_none() -> None:
    assert evaluate_condition("&x =", {"X": "1"}) is None


# ---------------------------------------------------------------------------
# resolve_macro_body — branches & the real m_derive_age_group guard
# ---------------------------------------------------------------------------

_AGE_GROUP_BODY = """%if %length(&in) = 0 %then %do;
    %put ERROR: m_derive_age_group requires IN= dataset.;
    %return;
%end;
data &out;
    set &in;
    length &grpvar $8;
    &grpvar = put(&agevar, agegr1f.);
run;"""


def test_resolve_age_group_guard_false_emits_body() -> None:
    env = {
        "IN": "work.adsl_pre",
        "OUT": "work.adsl_age",
        "AGEVAR": "AGE",
        "GRPVAR": "AGEGR1",
    }
    result = resolve_macro_body(_AGE_GROUP_BODY, env)
    # &param refs are left INTACT (not substituted) by macro_logic.
    assert "data &out;" in result.sas_text
    assert "set &in;" in result.sas_text
    assert "%if" not in result.sas_text
    assert "%do" not in result.sas_text
    assert "%put" not in result.sas_text
    assert "%return" not in result.sas_text
    assert result.assigned_globals == {}


def test_resolve_age_group_guard_true_truncates_at_return() -> None:
    env = {
        "IN": "",
        "OUT": "work.adsl_age",
        "AGEVAR": "AGE",
        "GRPVAR": "AGEGR1",
    }
    result = resolve_macro_body(_AGE_GROUP_BODY, env)
    # Guard TRUE -> %do branch taken -> %return halts before the data step.
    assert "data" not in result.sas_text
    assert "set" not in result.sas_text
    assert "%put" not in result.sas_text
    assert result.assigned_globals == {}


def test_resolve_nested_if_inner_else_binding() -> None:
    # Outer true -> enters %do; inner false -> inner %else branch text.
    body = (
        "%if &a = 1 %then %do; "
        "%if &b = 1 %then inner_then; %else inner_else; "
        "%end; %else outer_else;"
    )
    result = resolve_macro_body(body, {"A": "1", "B": "0"})
    assert "inner_else" in result.sas_text
    assert "inner_then" not in result.sas_text
    assert "outer_else" not in result.sas_text


def test_resolve_else_arm_selected() -> None:
    body = "%if &x=1 %then aaa; %else bbb;"
    result = resolve_macro_body(body, {"X": "2"})
    assert "bbb" in result.sas_text
    assert "aaa" not in result.sas_text


# ---------------------------------------------------------------------------
# resolve_macro_body — %let / %global
# ---------------------------------------------------------------------------


def test_resolve_let_chaining_via_condition() -> None:
    body = "%let a=1; %if &a = 1 %then yes; %else no;"
    result = resolve_macro_body(body, {})
    assert "yes" in result.sas_text
    assert "no" not in result.sas_text


def test_resolve_global_assignment_recorded() -> None:
    body = "%global SAFETY_RESULT=Y;"
    result = resolve_macro_body(body, {})
    assert result.assigned_globals == {"SAFETY_RESULT": "Y"}


def test_resolve_global_bare_declaration_not_recorded() -> None:
    body = "%global FOO;"
    result = resolve_macro_body(body, {})
    assert result.assigned_globals == {}


def test_resolve_global_value_references_env() -> None:
    body = "%let d=1; %global R=&d;"
    result = resolve_macro_body(body, {})
    assert result.assigned_globals == {"R": "1"}


# ---------------------------------------------------------------------------
# resolve_macro_body — loops (S-B2)
# ---------------------------------------------------------------------------


def test_resolve_loop_basic_unroll() -> None:
    body = "%do i=1 %to 3; row&i %end;"
    result = resolve_macro_body(body, {})
    assert result.sas_text.index("row1") < result.sas_text.index("row2")
    assert result.sas_text.index("row2") < result.sas_text.index("row3")


def test_resolve_loop_with_by_step() -> None:
    body = "%do i=0 %to 4 %by 2; v&i %end;"
    result = resolve_macro_body(body, {})
    assert "v0" in result.sas_text
    assert "v2" in result.sas_text
    assert "v4" in result.sas_text
    assert "v1" not in result.sas_text
    assert "v3" not in result.sas_text


def test_resolve_loop_bound_from_env() -> None:
    body = "%do i=1 %to &n; x&i %end;"
    result = resolve_macro_body(body, {"N": "2"})
    assert "x1" in result.sas_text
    assert "x2" in result.sas_text
    assert "x3" not in result.sas_text


def test_resolve_loop_non_integer_bound_raises() -> None:
    body = "%do i=1 %to &n; x&i %end;"
    with pytest.raises(CannotResolveMacroLogic):
        resolve_macro_body(body, {"N": "abc"})


def test_resolve_loop_exceeds_max_unroll_raises() -> None:
    body = f"%do i=1 %to {MAX_UNROLL + 1}; x %end;"
    with pytest.raises(CannotResolveMacroLogic):
        resolve_macro_body(body, {})


def test_resolve_return_inside_loop_halts_all() -> None:
    body = "%do i=1 %to 5; a&i %if &i = 2 %then %do; %return; %end; %end; tail"
    result = resolve_macro_body(body, {})
    assert "a1" in result.sas_text
    assert "a2" in result.sas_text
    assert "a3" not in result.sas_text
    assert "tail" not in result.sas_text


# ---------------------------------------------------------------------------
# resolve_macro_body — rejection / all-or-nothing
# ---------------------------------------------------------------------------


def test_resolve_do_while_raises() -> None:
    with pytest.raises(CannotResolveMacroLogic):
        resolve_macro_body("%do %while(&x); a %end;", {"X": "1"})


def test_resolve_do_until_raises() -> None:
    with pytest.raises(CannotResolveMacroLogic):
        resolve_macro_body("%do %until(&x); a %end;", {"X": "1"})


def test_resolve_unresolvable_condition_raises() -> None:
    with pytest.raises(CannotResolveMacroLogic):
        resolve_macro_body("%if &missing = 1 %then x; %else y;", {})


def test_resolve_all_or_nothing_on_unsupported_construct() -> None:
    body = "data a; run; %do %until(&x); b %end;"
    with pytest.raises(CannotResolveMacroLogic):
        resolve_macro_body(body, {"X": "1"})
