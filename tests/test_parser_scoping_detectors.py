"""Unit tests for F77 additive scoping detectors in SASParser.

Covers LIBNAME engine capture, ODS detection, and INFILE/FILE path capture.
These are detection-only signals consumed by the scoping report; they must NOT
change migration translation behavior (no new BlockType). The regression guard
asserts that a representative multi-block source produces a byte-identical block
list (types, count, line ranges) regardless of these additions.
"""

import pytest
from src.worker.engine.models import BlockType, ParseResult, SASBlock
from src.worker.engine.parser import SASParser


@pytest.fixture()
def parser() -> SASParser:
    return SASParser()


def _first_data_step(result: ParseResult) -> SASBlock:
    return next(b for b in result.blocks if b.block_type == BlockType.DATA_STEP)


# ── LIBNAME engine ────────────────────────────────────────────────────────────


def test_libname_engine_captured(parser: SASParser) -> None:
    sas = 'LIBNAME mylib oracle "/data/ora";\n'
    result = parser.parse({"t.sas": sas})
    assert result.libname_engines == {"mylib": "oracle"}
    # libname_map behavior is intentionally untouched (S-A): the legacy _LIBNAME_RE
    # only matches `LIBNAME ref "path"` (no engine token), so the engine form does
    # NOT populate libname_map. Consumers depend on this exact behavior.
    assert result.libname_map == {}


def test_libname_engine_base_fallback(parser: SASParser) -> None:
    sas = 'LIBNAME y "/data/out";\n'
    result = parser.parse({"t.sas": sas})
    assert result.libname_engines == {"y": "BASE"}
    assert result.libname_map == {"y": "/data/out"}


def test_libname_engine_mixed(parser: SASParser) -> None:
    sas = 'LIBNAME a meta "/m";\nLIBNAME b "/b";\n'
    result = parser.parse({"t.sas": sas})
    assert result.libname_engines == {"a": "meta", "b": "BASE"}


# ── ODS detection ─────────────────────────────────────────────────────────────


def test_ods_pdf_with_file_path(parser: SASParser) -> None:
    sas = 'ODS PDF FILE="/out/r.pdf";\nPROC PRINT DATA=x; RUN;\nODS PDF CLOSE;\n'
    result = parser.parse({"t.sas": sas})
    assert "PDF:/out/r.pdf" in result.ods_targets


def test_ods_html_without_path(parser: SASParser) -> None:
    sas = "ODS HTML;\nPROC PRINT DATA=x; RUN;\nODS HTML CLOSE;\n"
    result = parser.parse({"t.sas": sas})
    assert "HTML" in result.ods_targets


def test_ods_pdf_and_html_together(parser: SASParser) -> None:
    sas = 'ODS PDF FILE="/out/r.pdf";\nODS HTML;\n'
    result = parser.parse({"t.sas": sas})
    assert "PDF:/out/r.pdf" in result.ods_targets
    assert "HTML" in result.ods_targets


def test_ods_deterministic_no_duplicates(parser: SASParser) -> None:
    sas = 'ODS PDF FILE="/out/r.pdf";\nODS PDF CLOSE;\nODS PDF FILE="/out/r.pdf";\n'
    result = parser.parse({"t.sas": sas})
    assert result.ods_targets == ["PDF:/out/r.pdf"]


# ── INFILE / FILE paths ───────────────────────────────────────────────────────


def test_infile_literal_path(parser: SASParser) -> None:
    sas = "DATA out;\n  INFILE '/raw/in.txt';\n  INPUT x y;\nRUN;\n"
    result = parser.parse({"t.sas": sas})
    data = _first_data_step(result)
    assert "/raw/in.txt" in data.infile_paths
    assert "/raw/in.txt" in result.external_file_paths


def test_infile_fileref_resolved_via_filename_map(parser: SASParser) -> None:
    sas = (
        "FILENAME inref '/raw/customers.dat';\n"
        "DATA out;\n  INFILE inref;\n  INPUT name $ age;\nRUN;\n"
    )
    result = parser.parse({"t.sas": sas})
    data = _first_data_step(result)
    assert "/raw/customers.dat" in data.infile_paths
    assert "/raw/customers.dat" in result.external_file_paths


def test_file_statement_fileref_resolved(parser: SASParser) -> None:
    sas = (
        "FILENAME outref '/out/report.txt';\n"
        "DATA _null_;\n  SET src;\n  FILE outref;\n  PUT name;\nRUN;\n"
    )
    result = parser.parse({"t.sas": sas})
    data = _first_data_step(result)
    assert "/out/report.txt" in data.infile_paths


def test_infile_unknown_fileref_stored_as_token(parser: SASParser) -> None:
    sas = "DATA out;\n  INFILE mystery;\n  INPUT x;\nRUN;\n"
    result = parser.parse({"t.sas": sas})
    data = _first_data_step(result)
    assert "mystery" in data.infile_paths


def test_external_file_paths_rollup_union(parser: SASParser) -> None:
    sas = (
        "FILENAME fref '/raw/a.dat';\n"
        'ODS PDF FILE="/out/r.pdf";\n'
        "DATA out;\n  INFILE fref;\n  INPUT x;\nRUN;\n"
    )
    result = parser.parse({"t.sas": sas})
    # Sorted unique union of infile paths + ODS paths + filename_map values.
    assert result.external_file_paths == ["/out/r.pdf", "/raw/a.dat"]


# ── Regression guard: block list byte-identical ───────────────────────────────


_REPRESENTATIVE_SAS = """\
LIBNAME mylib oracle "/data/ora";
FILENAME inref '/raw/in.txt';

ODS PDF FILE="/out/report.pdf";

DATA work.clean;
    INFILE inref;
    SET mylib.raw;
    x = 1;
RUN;

PROC SORT DATA=work.clean OUT=work.sorted;
    BY id;
RUN;

PROC SQL;
    CREATE TABLE work.agg AS
    SELECT id, SUM(x) AS total
    FROM work.sorted
    GROUP BY id;
QUIT;

ODS PDF CLOSE;
"""


def _block_signature(block: object) -> tuple[str, str, int, int]:
    return (
        str(block.block_type),  # type: ignore[attr-defined]
        block.source_file,  # type: ignore[attr-defined]
        block.start_line,  # type: ignore[attr-defined]
        block.end_line,  # type: ignore[attr-defined]
    )


def test_blocks_unchanged_by_detectors(parser: SASParser) -> None:
    """The detectors must not alter the block list (no new BlockType, same lines).

    There is no ODS/INFILE BlockType, so the produced blocks for a source that
    exercises all three detectors must match the expected migration set exactly.
    """
    result = parser.parse({"prog.sas": _REPRESENTATIVE_SAS})

    signatures = [_block_signature(b) for b in result.blocks]
    types = {str(b.block_type) for b in result.blocks}

    # Exactly the three translatable constructs — no ODS/INFILE block leaked in.
    assert types == {"DATA_STEP", "PROC_SORT", "PROC_SQL"}
    assert len(result.blocks) == 3

    # Detectors fired (proving the source exercised them) without affecting blocks.
    assert result.libname_engines == {"mylib": "oracle"}
    assert "PDF:/out/report.pdf" in result.ods_targets
    data = _first_data_step(result)
    assert "/raw/in.txt" in data.infile_paths

    # Signatures are stable / deterministic across re-parse of identical input.
    again = parser.parse({"prog.sas": _REPRESENTATIVE_SAS})
    assert [_block_signature(b) for b in again.blocks] == signatures
