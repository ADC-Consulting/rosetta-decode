"""Tests that verify the parser emits the correct BlockType for each known SAS PROC."""

# SAS: tests/test_parser_proc_types.py:1

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser


@pytest.fixture()
def parser() -> SASParser:
    return SASParser()


_KNOWN_PROCS: list[tuple[str, BlockType]] = [
    ("PROC SQL; SELECT 1; QUIT;", BlockType.PROC_SQL),
    ("PROC SORT DATA=ds; BY id; RUN;", BlockType.PROC_SORT),
    ("PROC IML; x = {1,2,3}; RUN;", BlockType.PROC_IML),
    ("PROC FCMP; FUNCTION f(x); RETURN(x*2); ENDFUNC; RUN;", BlockType.PROC_FCMP),
    ("PROC MEANS DATA=ds; VAR x; RUN;", BlockType.PROC_MEANS),
    ("PROC FREQ DATA=ds; TABLES a*b; RUN;", BlockType.PROC_FREQ),
    ("PROC TRANSPOSE DATA=ds OUT=out; RUN;", BlockType.PROC_TRANSPOSE),
    ("PROC IMPORT DATAFILE='a.csv' OUT=ds DBMS=CSV REPLACE; RUN;", BlockType.PROC_IMPORT),
    ("PROC EXPORT DATA=ds OUTFILE='out.csv' DBMS=CSV REPLACE; RUN;", BlockType.PROC_EXPORT),
    ("PROC PRINT DATA=ds; RUN;", BlockType.PROC_PRINT),
    ("PROC CONTENTS DATA=ds; RUN;", BlockType.PROC_CONTENTS),
    ("PROC DATASETS LIBRARY=work; RUN;", BlockType.PROC_DATASETS),
    ("PROC OPTMODEL; VAR x >= 0; MIN z = x; SOLVE; RUN;", BlockType.PROC_OPTMODEL),
]


@pytest.mark.parametrize("sas_src,expected_type", _KNOWN_PROCS)
def test_known_proc_block_type(parser: SASParser, sas_src: str, expected_type: BlockType) -> None:
    """Each known PROC should map to its specific BlockType enum member."""
    result = parser.parse({"test.sas": sas_src})
    types = [b.block_type for b in result.blocks]
    assert expected_type in types, (
        f"Expected {expected_type!r} in parsed block types, got {types!r}"
    )


def test_unknown_proc_maps_to_proc_unknown(parser: SASParser) -> None:
    """An unrecognised PROC should yield PROC_UNKNOWN, not UNTRANSLATABLE."""
    sas_src = "PROC REPORT DATA=ds; COLUMN a b; RUN;"
    result = parser.parse({"test.sas": sas_src})
    types = [b.block_type for b in result.blocks]
    assert BlockType.PROC_UNKNOWN in types
    assert BlockType.UNTRANSLATABLE not in types


def test_proc_unknown_no_untranslatable_reason(parser: SASParser) -> None:
    """PROC_UNKNOWN blocks should not have an untranslatable_reason set."""
    sas_src = "PROC MIXED; MODEL y = x; RUN;"
    result = parser.parse({"test.sas": sas_src})
    for block in result.blocks:
        if block.block_type == BlockType.PROC_UNKNOWN:
            assert block.untranslatable_reason is None
            return
    pytest.fail("No PROC_UNKNOWN block found in parse result")


def test_untranslatable_only_for_truly_unparsable(parser: SASParser) -> None:
    """UNTRANSLATABLE should only appear when the SAS cannot be parsed at all."""
    # Known procs and unknown procs should never produce UNTRANSLATABLE any more
    sas_src = "\n".join(
        [
            "PROC MIXED; MODEL y = x; RUN;",
            "PROC REPORT DATA=ds; RUN;",
            "PROC SORT DATA=a; BY id; RUN;",
        ]
    )
    result = parser.parse({"test.sas": sas_src})
    for block in result.blocks:
        assert block.block_type != BlockType.UNTRANSLATABLE, (
            f"Unexpected UNTRANSLATABLE block: {block.raw_sas!r}"
        )
