"""Unit tests for src.backend.api.schema_utils.map_sas_to_semantic_type."""

from src.backend.api.schema_utils import map_sas_to_semantic_type


def test_character_is_string() -> None:
    assert map_sas_to_semantic_type("character", "$40.") == "String"


def test_character_no_format_is_string() -> None:
    assert map_sas_to_semantic_type("character", None) == "String"


def test_double_with_date_format() -> None:
    assert map_sas_to_semantic_type("double", "DATE9.") == "Date"


def test_double_with_datetime_format() -> None:
    assert map_sas_to_semantic_type("double", "DATETIME20.") == "Timestamp"


def test_double_with_decimal_format() -> None:
    assert map_sas_to_semantic_type("double", "COMMA12.2") == "Decimal"


def test_double_no_format_is_number() -> None:
    assert map_sas_to_semantic_type("double", None) == "Number"


def test_double_empty_format_is_number() -> None:
    assert map_sas_to_semantic_type("double", "") == "Number"


def test_iso8601_date() -> None:
    assert map_sas_to_semantic_type("double", "ISO8601DA10.") == "Date"


def test_time_is_timestamp() -> None:
    assert map_sas_to_semantic_type("double", "TIME8.") == "Timestamp"


def test_yymmdd_date() -> None:
    assert map_sas_to_semantic_type("double", "YYMMDD10.") == "Date"


def test_dollar_decimal_with_decimal_point() -> None:
    assert map_sas_to_semantic_type("double", "DOLLAR12.2") == "Decimal"


def test_dollar_no_decimal_point_is_number() -> None:
    # No "." within the format string itself → not Decimal
    assert map_sas_to_semantic_type("double", "DOLLAR12") == "Number"


def test_case_insensitive_date() -> None:
    assert map_sas_to_semantic_type("double", "date9.") == "Date"


def test_case_insensitive_datetime() -> None:
    assert map_sas_to_semantic_type("double", "datetime20.") == "Timestamp"
