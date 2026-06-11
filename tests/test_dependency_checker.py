"""Unit tests for src/worker/engine/dependency_checker.py."""

from src.worker.engine.dependency_checker import detect_missing_dependencies
from src.worker.engine.models import MacroDef, ParseResult


def _make_parse_result(
    macro_defs: list[MacroDef] | None = None,
    includes: list[str] | None = None,
) -> ParseResult:
    """Build a minimal ParseResult for testing.

    Args:
        macro_defs: Optional list of MacroDef instances.
        includes: Optional list of include paths.

    Returns:
        ParseResult with only blocks, macro_defs, and includes set.
    """
    return ParseResult(
        blocks=[],
        macro_defs=macro_defs or [],
        includes=includes or [],
    )


def test_missing_macro_detected() -> None:
    """A %word token that is not defined in macro_defs should be flagged."""
    pr = _make_parse_result()
    result = detect_missing_dependencies(pr, {"file.sas": "data x; %my_macro(); run;"})
    assert any(d.name == "MY_MACRO" and d.type == "macro" for d in result)


def test_defined_macro_not_flagged() -> None:
    """A %word token whose name appears in macro_defs must not be flagged."""
    pr = _make_parse_result(
        macro_defs=[MacroDef(name="MY_MACRO", source_file="f.sas", start_line=1, body="", line=1)]
    )
    result = detect_missing_dependencies(pr, {"file.sas": "%my_macro();"})
    assert not any(d.name == "MY_MACRO" for d in result)


def test_sas_builtin_not_flagged() -> None:
    """SAS built-in macro keywords (%let, %if, %do, %end) must not be flagged."""
    pr = _make_parse_result()
    result = detect_missing_dependencies(pr, {"file.sas": "%let x=1; %if &x %then %do; %end;"})
    assert result == []


def test_missing_include_detected() -> None:
    """An include path whose basename is not among uploaded files should be flagged."""
    pr = _make_parse_result(includes=["/sas/macros/utils.sas"])
    result = detect_missing_dependencies(pr, {"main.sas": ""})
    assert any(d.name == "utils.sas" and d.type == "include" for d in result)


def test_include_present_not_flagged() -> None:
    """An include whose basename matches an uploaded file key must not be flagged."""
    pr = _make_parse_result(includes=["/sas/macros/utils.sas"])
    result = detect_missing_dependencies(pr, {"utils.sas": "", "main.sas": ""})
    assert not any(d.name == "utils.sas" for d in result)


def test_macro_variable_include_skipped() -> None:
    """Include paths that contain macro variable references (&) must be silently skipped."""
    pr = _make_parse_result(includes=["&macropath/utils.sas"])
    result = detect_missing_dependencies(pr, {"main.sas": ""})
    assert result == []


def test_reference_count_accumulated() -> None:
    """reference_count must reflect how many times the macro is called across all files."""
    pr = _make_parse_result()
    files = {
        "a.sas": "%my_macro(); %my_macro();",
        "b.sas": "%my_macro();",
    }
    result = detect_missing_dependencies(pr, files)
    entry = next((d for d in result if d.name == "MY_MACRO"), None)
    assert entry is not None
    assert entry.reference_count == 3


def test_macros_ordered_before_includes() -> None:
    """Macro entries must appear before include entries in the returned list."""
    pr = _make_parse_result(includes=["/sas/utils.sas"])
    result = detect_missing_dependencies(pr, {"main.sas": "%custom_macro();"})
    types = [d.type for d in result]
    # All macros should come before any include
    if "include" in types:
        last_macro = max((i for i, t in enumerate(types) if t == "macro"), default=-1)
        first_include = types.index("include")
        assert last_macro < first_include


def test_macro_case_insensitive_match() -> None:
    """MacroDef stored uppercase should match a lowercase invocation in source."""
    pr = _make_parse_result(
        macro_defs=[MacroDef(name="CLEANUP", source_file="f.sas", start_line=1, body="", line=1)]
    )
    result = detect_missing_dependencies(pr, {"file.sas": "%cleanup();"})
    assert not any(d.name == "CLEANUP" for d in result)
