"""Unit tests for detect_referenced_data_files and render_declared_types_section (F61).

Covers:
- detect_referenced_data_files: match by input_datasets, match by raw_sas,
  exclusion of files with empty column_types, deterministic sorted output.
- render_declared_types_section: empty-string on no match, correct header and
  sub-headers, character/numeric type rendering, trailing instruction line.
"""

from types import SimpleNamespace

from src.worker.engine.agents.shared import (
    detect_referenced_data_files,
    render_declared_types_section,
)
from src.worker.engine.models import DataFileInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _block(input_datasets: list[str], raw_sas: str = "") -> object:
    """Minimal stand-in for a SASBlock with only the fields the helpers need."""
    return SimpleNamespace(input_datasets=input_datasets, raw_sas=raw_sas)


def _info(path: str, column_types: dict[str, str] | None = None) -> DataFileInfo:
    return DataFileInfo(
        path=path,
        disk_path="/tmp/" + path,
        extension="." + path.rsplit(".", 1)[-1],
        column_types=column_types or {},
    )


# ---------------------------------------------------------------------------
# detect_referenced_data_files
# ---------------------------------------------------------------------------


class TestDetectReferencedDataFiles:
    def test_match_via_input_datasets(self) -> None:
        """Basename found inside an input_datasets entry returns the key."""
        block = _block(input_datasets=["work.adsl"])
        data_files = {
            "data/raw/ADSL.sas7bdat": _info("data/raw/ADSL.sas7bdat", {"age": "double"}),
        }
        result = detect_referenced_data_files(block, data_files)
        assert result == ["data/raw/ADSL.sas7bdat"]

    def test_match_via_raw_sas_fallback(self) -> None:
        """Basename found in raw_sas when not in input_datasets."""
        block = _block(input_datasets=[], raw_sas="set adsl; run;")
        data_files = {
            "data/raw/ADSL.sas7bdat": _info("data/raw/ADSL.sas7bdat", {"age": "double"}),
        }
        result = detect_referenced_data_files(block, data_files)
        assert result == ["data/raw/ADSL.sas7bdat"]

    def test_excludes_files_without_column_types(self) -> None:
        """Files with empty column_types are silently ignored."""
        block = _block(input_datasets=["adsl"])
        data_files = {
            "data/raw/ADSL.sas7bdat": _info("data/raw/ADSL.sas7bdat", {}),
        }
        result = detect_referenced_data_files(block, data_files)
        assert result == []

    def test_returns_sorted_keys(self) -> None:
        """Multiple matches are returned in sorted order."""
        block = _block(input_datasets=[], raw_sas="adsl adae run;")
        data_files = {
            "data/raw/ADAE.sas7bdat": _info("data/raw/ADAE.sas7bdat", {"aedecod": "string"}),
            "data/raw/ADSL.sas7bdat": _info("data/raw/ADSL.sas7bdat", {"age": "double"}),
        }
        result = detect_referenced_data_files(block, data_files)
        assert result == ["data/raw/ADAE.sas7bdat", "data/raw/ADSL.sas7bdat"]

    def test_no_match_returns_empty_list(self) -> None:
        """Block that references nothing returns an empty list."""
        block = _block(input_datasets=[], raw_sas="data mydata; set other; run;")
        data_files = {
            "data/raw/ADSL.sas7bdat": _info("data/raw/ADSL.sas7bdat", {"age": "double"}),
        }
        result = detect_referenced_data_files(block, data_files)
        assert result == []

    def test_empty_data_files_returns_empty(self) -> None:
        """Empty catalog always returns an empty list."""
        block = _block(input_datasets=["adsl"], raw_sas="set adsl;")
        result = detect_referenced_data_files(block, {})
        assert result == []

    def test_case_insensitive_matching(self) -> None:
        """Matching is case-insensitive for both basename and dataset references."""
        block = _block(input_datasets=["ADSL"])
        data_files = {
            "data/raw/adsl.sas7bdat": _info("data/raw/adsl.sas7bdat", {"age": "double"}),
        }
        result = detect_referenced_data_files(block, data_files)
        assert result == ["data/raw/adsl.sas7bdat"]


# ---------------------------------------------------------------------------
# render_declared_types_section
# ---------------------------------------------------------------------------


class TestRenderDeclaredTypesSection:
    def test_empty_referenced_returns_empty_string(self) -> None:
        """No referenced keys produces an empty string (caller skips section)."""
        result = render_declared_types_section([], {})
        assert result == ""

    def test_referenced_key_not_in_data_files_returns_empty(self) -> None:
        """A stale key in referenced that is absent from data_files yields empty."""
        result = render_declared_types_section(["missing/key"], {})
        assert result == ""

    def test_referenced_key_with_empty_column_types_returns_empty(self) -> None:
        """A referenced key whose column_types is empty yields empty string."""
        data_files = {"data/raw/X.sas7bdat": _info("data/raw/X.sas7bdat", {})}
        result = render_declared_types_section(["data/raw/X.sas7bdat"], data_files)
        assert result == ""

    def test_single_file_renders_header_and_columns(self) -> None:
        """A single referenced file renders the section header, sub-header, and columns."""
        data_files = {
            "data/raw/ADSL.sas7bdat": _info(
                "data/raw/ADSL.sas7bdat",
                {"age": "double", "usubjid": "string"},
            )
        }
        result = render_declared_types_section(["data/raw/ADSL.sas7bdat"], data_files)
        lines = result.splitlines()
        assert lines[0] == "## Declared source column types"
        assert lines[1] == "### data/raw/ADSL.sas7bdat"
        assert "- age: numeric" in lines
        assert "- usubjid: character" in lines

    def test_string_type_maps_to_character(self) -> None:
        """column_types value 'string' renders as 'character'."""
        data_files = {"k": _info("k.sas7bdat", {"col": "string"})}
        result = render_declared_types_section(["k"], data_files)
        assert "- col: character" in result

    def test_non_string_type_maps_to_numeric(self) -> None:
        """Any cast_type other than 'string' renders as 'numeric'."""
        data_files = {"k": _info("k.sas7bdat", {"col": "double"})}
        result = render_declared_types_section(["k"], data_files)
        assert "- col: numeric" in result

    def test_columns_sorted_deterministically(self) -> None:
        """Columns within a file are rendered in sorted (alphabetical) order."""
        data_files = {"k": _info("k.sas7bdat", {"zzz": "double", "aaa": "string", "mmm": "double"})}
        result = render_declared_types_section(["k"], data_files)
        col_lines = [ln for ln in result.splitlines() if ln.startswith("- ")]
        assert col_lines == ["- aaa: character", "- mmm: numeric", "- zzz: numeric"]

    def test_trailing_instruction_line_present(self) -> None:
        """The trailing cast instruction line is always appended."""
        data_files = {"k": _info("k.sas7bdat", {"col": "double"})}
        result = render_declared_types_section(["k"], data_files)
        assert result.endswith(
            "Use these types when deciding join/compare/derivation logic."
            " Do NOT write the load-time `.cast(...)` yourself —"
            " it is injected automatically after the lowercase-normalization step."
        )

    def test_multiple_files_rendered_in_input_order(self) -> None:
        """Multiple referenced files each get their own sub-header."""
        data_files = {
            "data/raw/ADAE.sas7bdat": _info("data/raw/ADAE.sas7bdat", {"aedecod": "string"}),
            "data/raw/ADSL.sas7bdat": _info("data/raw/ADSL.sas7bdat", {"age": "double"}),
        }
        # referenced is already sorted (as produced by detect_referenced_data_files)
        referenced = ["data/raw/ADAE.sas7bdat", "data/raw/ADSL.sas7bdat"]
        result = render_declared_types_section(referenced, data_files)
        adae_pos = result.index("### data/raw/ADAE.sas7bdat")
        adsl_pos = result.index("### data/raw/ADSL.sas7bdat")
        assert adae_pos < adsl_pos
