"""Tests for src/worker/engine/ddl_generator.py.

Covers:
- All 6 known semantic_type → SQL type mappings (String, Date, Timestamp, Decimal,
  Number, Integer)
- Unknown / unrecognised semantic type → TEXT fallback
- Full multi-column DDL structure (indentation, commas, semicolon)
- Empty columns list → stub DDL with comment
- Qualified name (schema + table) in output header
- Column names are lowercased in output
"""

from src.worker.engine.ddl_generator import _semantic_to_sql_type, generate_create_table

# ---------------------------------------------------------------------------
# _semantic_to_sql_type unit tests (each semantic type tested in isolation)
# ---------------------------------------------------------------------------


class TestSemanticToSqlType:
    """Direct tests of the internal mapping helper."""

    def test_string_maps_to_text(self) -> None:
        assert _semantic_to_sql_type("String") == "TEXT"

    def test_date_maps_to_date(self) -> None:
        assert _semantic_to_sql_type("Date") == "DATE"

    def test_timestamp_maps_to_timestamp(self) -> None:
        assert _semantic_to_sql_type("Timestamp") == "TIMESTAMP"

    def test_decimal_maps_to_decimal(self) -> None:
        assert _semantic_to_sql_type("Decimal") == "DECIMAL"

    def test_number_maps_to_double_precision(self) -> None:
        assert _semantic_to_sql_type("Number") == "DOUBLE PRECISION"

    def test_integer_maps_to_bigint(self) -> None:
        assert _semantic_to_sql_type("Integer") == "BIGINT"

    def test_unknown_maps_to_text(self) -> None:
        assert _semantic_to_sql_type("Unknown") == "TEXT"

    def test_empty_string_maps_to_text(self) -> None:
        assert _semantic_to_sql_type("") == "TEXT"

    def test_arbitrary_value_maps_to_text(self) -> None:
        assert _semantic_to_sql_type("SomeWeirdType") == "TEXT"


# ---------------------------------------------------------------------------
# generate_create_table — structural tests
# ---------------------------------------------------------------------------


class TestGenerateCreateTable:
    """Integration-level tests for the full DDL output."""

    def test_empty_columns_emits_stub_ddl(self) -> None:
        ddl = generate_create_table("patients", "clinical", [])
        assert "CREATE TABLE clinical.patients" in ddl
        assert "-- no columns extracted" in ddl
        assert ddl.endswith(";")

    def test_qualified_name_in_output(self) -> None:
        ddl = generate_create_table(
            "dm_raw", "public", [{"name": "id", "semantic_type": "Integer"}]
        )
        assert ddl.startswith("CREATE TABLE public.dm_raw (")

    def test_column_name_is_lowercased(self) -> None:
        ddl = generate_create_table("t", "s", [{"name": "PatientID", "semantic_type": "String"}])
        assert "patientid TEXT" in ddl

    def test_single_column_no_trailing_comma(self) -> None:
        ddl = generate_create_table("t", "s", [{"name": "col", "semantic_type": "Date"}])
        # The last (and only) column line must not end with a comma
        lines = ddl.splitlines()
        col_line = next(ln for ln in lines if "col" in ln)
        assert not col_line.rstrip().endswith(",")

    def test_multi_column_trailing_commas_except_last(self) -> None:
        columns = [
            {"name": "col1", "semantic_type": "String"},
            {"name": "col2", "semantic_type": "Date"},
            {"name": "col3", "semantic_type": "Number"},
        ]
        ddl = generate_create_table("t", "s", columns)
        lines = [ln for ln in ddl.splitlines() if ln.strip() and not ln.startswith("CREATE")]
        # First two lines should end with comma
        assert lines[0].rstrip().endswith(",")
        assert lines[1].rstrip().endswith(",")
        # Last column line must NOT end with comma (before closing paren)
        last_col_line = lines[2]
        assert not last_col_line.rstrip().endswith(",")

    def test_column_lines_are_four_space_indented(self) -> None:
        columns = [{"name": "x", "semantic_type": "Integer"}]
        ddl = generate_create_table("t", "s", columns)
        col_line = next(ln for ln in ddl.splitlines() if "x BIGINT" in ln)
        assert col_line.startswith("    ")

    def test_statement_ends_with_semicolon(self) -> None:
        columns = [{"name": "a", "semantic_type": "String"}]
        ddl = generate_create_table("t", "s", columns)
        assert ddl.endswith(");")

    def test_full_multi_column_ddl_structure(self) -> None:
        """Full structural test covering schema, indentation, commas, and semicolon."""
        columns = [
            {"name": "USUBJID", "semantic_type": "String"},
            {"name": "VISIT_DT", "semantic_type": "Date"},
            {"name": "WEIGHT_KG", "semantic_type": "Number"},
        ]
        ddl = generate_create_table("adsl", "analytics", columns)
        expected = (
            "CREATE TABLE analytics.adsl (\n"
            "    usubjid TEXT,\n"
            "    visit_dt DATE,\n"
            "    weight_kg DOUBLE PRECISION\n"
            ");"
        )
        assert ddl == expected

    def test_decimal_type_in_ddl(self) -> None:
        columns = [{"name": "amount", "semantic_type": "Decimal"}]
        ddl = generate_create_table("transactions", "finance", columns)
        assert "amount DECIMAL" in ddl

    def test_timestamp_type_in_ddl(self) -> None:
        columns = [{"name": "created_at", "semantic_type": "Timestamp"}]
        ddl = generate_create_table("events", "logs", columns)
        assert "created_at TIMESTAMP" in ddl

    def test_unknown_semantic_type_falls_back_to_text(self) -> None:
        columns = [{"name": "misc", "semantic_type": "Unknown"}]
        ddl = generate_create_table("t", "s", columns)
        assert "misc TEXT" in ddl

    def test_missing_semantic_type_key_falls_back_to_text(self) -> None:
        # Column dict with no "semantic_type" key should default to TEXT safely
        columns = [{"name": "orphan"}]
        ddl = generate_create_table("t", "s", columns)
        assert "orphan TEXT" in ddl
