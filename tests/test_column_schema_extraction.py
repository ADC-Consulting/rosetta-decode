"""Unit tests for column-schema extraction (P2-C of F34).

Covers:
- LENGTH statement parsing (character and numeric, multi-column)
- FORMAT statement parsing (multi-pair)
- ATTRIB statement parsing (LENGTH=, FORMAT=, LABEL= sub-options)
- _extract_column_schema combinator
- SASBlock.column_schema population via _extract_data_steps / SASParser.parse
- _merge_source_column_schema in worker pipeline
"""

from typing import Any

from src.worker.engine.models import BlockType, SASBlock
from src.worker.engine.parser import (
    SASParser,
    _extract_column_schema,
    _parse_attrib_stmt,
    _parse_format_stmt,
    _parse_length_stmt,
)
from src.worker.main import _merge_source_column_schema

# ── LENGTH statement ──────────────────────────────────────────────────────────


class TestParseLengthStmt:
    """Tests for _parse_length_stmt."""

    def test_character_with_width(self) -> None:
        result = _parse_length_stmt("col $40")
        assert result == {"col": {"sas_type": "character", "sas_format": "$40"}}

    def test_character_bare_dollar(self) -> None:
        result = _parse_length_stmt("col $")
        assert result == {"col": {"sas_type": "character", "sas_format": "$"}}

    def test_numeric_width(self) -> None:
        result = _parse_length_stmt("age 8")
        assert result == {"age": {"sas_type": "numeric", "sas_format": "8"}}

    def test_multi_column_mixed(self) -> None:
        result = _parse_length_stmt("col $40 age 8")
        assert result["col"] == {"sas_type": "character", "sas_format": "$40"}
        assert result["age"] == {"sas_type": "numeric", "sas_format": "8"}

    def test_multiple_cols_same_specifier(self) -> None:
        # LENGTH a b $20;  — both columns get the same format
        result = _parse_length_stmt("a b $20")
        assert result["a"] == {"sas_type": "character", "sas_format": "$20"}
        assert result["b"] == {"sas_type": "character", "sas_format": "$20"}

    def test_empty_body(self) -> None:
        assert _parse_length_stmt("") == {}

    def test_keys_are_lowercase(self) -> None:
        result = _parse_length_stmt("PatientID $20")
        assert "patientid" in result


# ── FORMAT statement ──────────────────────────────────────────────────────────


class TestParseFormatStmt:
    """Tests for _parse_format_stmt."""

    def test_single_pair(self) -> None:
        result = _parse_format_stmt("col date9.")
        assert result == {"col": {"sas_format": "DATE9."}}

    def test_uppercase_format(self) -> None:
        result = _parse_format_stmt("dt date9.")
        assert result["dt"]["sas_format"] == "DATE9."

    def test_multi_pair(self) -> None:
        result = _parse_format_stmt("col date9. amount comma12.2")
        assert result["col"] == {"sas_format": "DATE9."}
        assert result["amount"] == {"sas_format": "COMMA12.2"}

    def test_char_format(self) -> None:
        result = _parse_format_stmt("name $char40.")
        assert result["name"]["sas_format"] == "$CHAR40."

    def test_empty_body(self) -> None:
        assert _parse_format_stmt("") == {}

    def test_keys_are_lowercase(self) -> None:
        result = _parse_format_stmt("SUBJID $20.")
        assert "subjid" in result


# ── ATTRIB statement ──────────────────────────────────────────────────────────


class TestParseAttribStmt:
    """Tests for _parse_attrib_stmt."""

    def test_length_and_format_and_label(self) -> None:
        body = 'col LENGTH=$40 FORMAT=$CHAR40. LABEL="Patient ID"'
        result = _parse_attrib_stmt(body)
        assert "col" in result
        entry = result["col"]
        assert entry["sas_type"] == "character"
        assert entry["sas_format"] == "$CHAR40."
        assert entry["label"] == "Patient ID"

    def test_numeric_length_only(self) -> None:
        body = "age LENGTH=8"
        result = _parse_attrib_stmt(body)
        assert result["age"]["sas_type"] == "numeric"
        assert result["age"]["sas_format"] == "8"

    def test_label_only(self) -> None:
        body = 'trt01p LABEL="Treatment Arm"'
        result = _parse_attrib_stmt(body)
        assert result["trt01p"]["label"] == "Treatment Arm"

    def test_format_only(self) -> None:
        body = "visit FORMAT=date9."
        result = _parse_attrib_stmt(body)
        assert result["visit"]["sas_format"] == "DATE9."

    def test_empty_body(self) -> None:
        assert _parse_attrib_stmt("") == {}

    def test_keys_are_lowercase(self) -> None:
        body = 'USUBJID LENGTH=$40 LABEL="Subject ID"'
        result = _parse_attrib_stmt(body)
        assert "usubjid" in result


# ── _extract_column_schema combinator ────────────────────────────────────────


class TestExtractColumnSchema:
    """Tests for _extract_column_schema acting on raw DATA step source."""

    def test_length_statement(self) -> None:
        raw = "DATA out;\n    LENGTH col $40 age 8;\n    SET src;\nRUN;"
        result = _extract_column_schema(raw)
        assert result["col"]["sas_type"] == "character"
        assert result["age"]["sas_type"] == "numeric"

    def test_format_statement(self) -> None:
        raw = "DATA out;\n    FORMAT dt date9.;\n    SET src;\nRUN;"
        result = _extract_column_schema(raw)
        assert result["dt"]["sas_format"] == "DATE9."

    def test_attrib_statement(self) -> None:
        raw = 'DATA out;\n    ATTRIB col LENGTH=$20 LABEL="My Col";\n    SET src;\nRUN;'
        result = _extract_column_schema(raw)
        assert result["col"]["label"] == "My Col"
        assert result["col"]["sas_type"] == "character"

    def test_merge_all_three(self) -> None:
        raw = (
            "DATA out;\n"
            "    LENGTH col $40;\n"
            "    FORMAT col $char40.;\n"
            '    ATTRIB col LABEL="Test";\n'
            "    SET src;\n"
            "RUN;"
        )
        result = _extract_column_schema(raw)
        entry = result["col"]
        assert entry["sas_type"] == "character"
        assert entry["sas_format"] == "$CHAR40."  # FORMAT wins over LENGTH for sas_format
        assert entry["label"] == "Test"

    def test_no_declarations(self) -> None:
        raw = "DATA out;\n    SET src;\n    x = 1;\nRUN;"
        assert _extract_column_schema(raw) == {}

    def test_case_insensitive_keywords(self) -> None:
        raw = "data out;\n    length col $40;\n    set src;\nrun;"
        result = _extract_column_schema(raw)
        assert "col" in result


# ── SASParser integration ─────────────────────────────────────────────────────


class TestSASParserColumnSchema:
    """Integration tests verifying column_schema is populated via SASParser.parse."""

    def test_parser_populates_column_schema_from_length(self) -> None:
        sas = "DATA out;\n    LENGTH col $40 age 8;\n    SET src;\nRUN;\n"
        result = SASParser().parse({"test.sas": sas})
        data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
        assert len(data_blocks) == 1
        schema = data_blocks[0].column_schema
        assert "col" in schema
        assert schema["col"]["sas_type"] == "character"
        assert "age" in schema
        assert schema["age"]["sas_type"] == "numeric"

    def test_parser_populates_column_schema_from_format(self) -> None:
        sas = "DATA out;\n    FORMAT dt date9.;\n    SET src;\nRUN;\n"
        result = SASParser().parse({"test.sas": sas})
        data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
        assert data_blocks[0].column_schema["dt"]["sas_format"] == "DATE9."

    def test_parser_populates_column_schema_from_attrib(self) -> None:
        sas = 'DATA out;\n    ATTRIB col LENGTH=$20 LABEL="Patient";\n    SET src;\nRUN;\n'
        result = SASParser().parse({"test.sas": sas})
        data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
        schema = data_blocks[0].column_schema
        assert schema["col"]["label"] == "Patient"

    def test_block_without_declarations_has_empty_schema(self) -> None:
        sas = "DATA out;\n    SET src;\n    x = 1;\nRUN;\n"
        result = SASParser().parse({"test.sas": sas})
        data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
        assert data_blocks[0].column_schema == {}


# ── _merge_source_column_schema ───────────────────────────────────────────────


def _make_block(
    output_datasets: list[str],
    column_schema: dict[str, dict[str, str]],
) -> SASBlock:
    """Build a minimal SASBlock for merge tests."""
    return SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="test.sas",
        start_line=1,
        end_line=5,
        raw_sas="DATA out; SET src; RUN;",
        output_datasets=output_datasets,
        column_schema=column_schema,
    )


class TestMergeSourceColumnSchema:
    """Tests for _merge_source_column_schema."""

    def test_fills_empty_schema_entry(self) -> None:
        blocks = [
            _make_block(
                ["sdtm_dm"],
                {"usubjid": {"sas_type": "character", "sas_format": "$40"}},
            )
        ]
        data_schema: dict[str, Any] = {
            "data/sdtm_dm.sas7bdat": {
                "columns": [],
                "column_types": {},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            }
        }
        _merge_source_column_schema(blocks, data_schema)
        entry = data_schema["data/sdtm_dm.sas7bdat"]
        assert "usubjid" in entry["columns"]
        assert entry["column_types"]["usubjid"] == "character"
        assert entry["column_formats"]["usubjid"] == "$40"

    def test_does_not_overwrite_existing_columns(self) -> None:
        blocks = [
            _make_block(
                ["adsl"],
                {"usubjid": {"sas_type": "character"}},
            )
        ]
        data_schema: dict[str, Any] = {
            "data/adsl.sas7bdat": {
                "columns": ["usubjid", "age"],  # already populated from pyreadstat
                "column_types": {"usubjid": "character", "age": "double"},
                "column_labels": {},
                "column_formats": {},
                "row_count": 100,
            }
        }
        _merge_source_column_schema(blocks, data_schema)
        # Must remain untouched
        assert data_schema["data/adsl.sas7bdat"]["columns"] == ["usubjid", "age"]

    def test_strips_libname_prefix(self) -> None:
        blocks = [
            _make_block(
                ["outdir.sdtm_dm"],
                {"col": {"sas_type": "character", "sas_format": "$20"}},
            )
        ]
        data_schema: dict[str, Any] = {
            "data/sdtm_dm.sas7bdat": {
                "columns": [],
                "column_types": {},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            }
        }
        _merge_source_column_schema(blocks, data_schema)
        assert "col" in data_schema["data/sdtm_dm.sas7bdat"]["columns"]

    def test_creates_new_entry_for_derived_dataset(self) -> None:
        blocks = [
            _make_block(
                ["adsl_output"],
                {
                    "usubjid": {"sas_type": "character", "sas_format": "$40"},
                    "age": {"sas_type": "numeric", "sas_format": "8"},
                },
            )
        ]
        data_schema: dict[str, Any] = {}
        _merge_source_column_schema(blocks, data_schema)
        assert "adsl_output" in data_schema
        entry = data_schema["adsl_output"]
        assert "usubjid" in entry["columns"]
        assert "age" in entry["columns"]
        assert entry["column_types"]["usubjid"] == "character"
        assert entry["row_count"] is None

    def test_label_propagated_to_column_labels(self) -> None:
        blocks = [
            _make_block(
                ["out"],
                {"trt01p": {"sas_type": "character", "label": "Treatment Arm"}},
            )
        ]
        data_schema: dict[str, Any] = {
            "out": {
                "columns": [],
                "column_types": {},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            }
        }
        _merge_source_column_schema(blocks, data_schema)
        assert data_schema["out"]["column_labels"]["trt01p"] == "Treatment Arm"

    def test_block_without_column_schema_is_skipped(self) -> None:
        blocks = [_make_block(["out"], {})]
        data_schema: dict[str, Any] = {}
        _merge_source_column_schema(blocks, data_schema)
        assert data_schema == {}

    def test_block_without_output_datasets_is_skipped(self) -> None:
        block = SASBlock(
            block_type=BlockType.DATA_STEP,
            source_file="test.sas",
            start_line=1,
            end_line=5,
            raw_sas="DATA out; SET src; RUN;",
            output_datasets=[],
            column_schema={"col": {"sas_type": "character"}},
        )
        data_schema: dict[str, Any] = {}
        _merge_source_column_schema([block], data_schema)
        assert data_schema == {}
