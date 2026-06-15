"""Unit tests for the deterministic PROC FORMAT catalog extractor (F60 S-C).

Also covers F60 S-F: cross-file catalog population by ``SASParser`` and prompt
injection of the ``## Available SAS formats`` section by the translation agents.
"""

from pathlib import Path

from src.worker.engine.agents.data_step import _build_prompt as _data_step_build_prompt
from src.worker.engine.agents.proc import _build_prompt as _proc_build_prompt
from src.worker.engine.format_catalog import (
    extract_format_catalog,
    normalize_format_name,
)
from src.worker.engine.models import BlockType, JobContext, SASBlock
from src.worker.engine.parser import SASParser

# Repo root is two levels up from this test file (tests/ -> repo root).
_REPO_ROOT = Path(__file__).parent.parent
_PHARMA_FORMATS = (
    _REPO_ROOT / "data" / "medium_test" / "sas_pharma_sandbox" / "formats" / "pharma_formats.sas"
)


def test_numeric_ranges_with_low_high_and_exclusive_upper() -> None:
    """An agegr1f-style numeric format parses ranges incl. low/high and -<."""
    source = """
    proc format;
        value agegr1f
            low  -<  18  = '<18'
            18   -<  65  = '18-64'
            65   -<  75  = '65-74'
            75   -  high = '>=75';
    run;
    """
    catalog = extract_format_catalog(source)

    assert set(catalog) == {"agegr1f"}
    fmt = catalog["agegr1f"]
    assert fmt.name == "agegr1f"
    assert fmt.is_char is False
    assert len(fmt.entries) == 4

    first = fmt.entries[0]
    assert first.low == "low"
    assert first.high == "18"
    assert first.exclusive_upper is True
    assert first.label == "<18"
    assert first.value is None

    last = fmt.entries[3]
    assert last.low == "75"
    assert last.high == "high"
    assert last.exclusive_upper is False
    assert last.label == ">=75"


def test_char_format_keeps_quotes_and_normalizes_name() -> None:
    """A $-prefixed format is char, name normalized, operands keep quotes."""
    source = """
    proc format;
        value $sexdec
            'M' = 'Male'
            'F' = 'Female'
            other = 'Unknown';
    run;
    """
    catalog = extract_format_catalog(source)

    assert "$sexdec" in catalog
    fmt = catalog["$sexdec"]
    assert fmt.name == "$sexdec"
    assert fmt.is_char is True
    assert len(fmt.entries) == 3

    assert fmt.entries[0].value == "'M'"
    assert fmt.entries[0].label == "Male"
    assert fmt.entries[1].value == "'F'"
    assert fmt.entries[1].label == "Female"


def test_other_catch_all_entry() -> None:
    """The ``other`` keyword produces an is_other catch-all entry."""
    source = """
    proc format;
        value $sexdec
            'M' = 'Male'
            other = 'Unknown';
    run;
    """
    catalog = extract_format_catalog(source)
    other_entry = catalog["$sexdec"].entries[-1]

    assert other_entry.is_other is True
    assert other_entry.label == "Unknown"
    assert other_entry.value is None
    assert other_entry.low is None
    assert other_entry.high is None


def test_single_value_entries() -> None:
    """An aegrf-style format yields one single-value entry per line."""
    source = """
    proc format;
        value aegrf
            1 = 'Mild'
            2 = 'Moderate'
            3 = 'Severe'
            4 = 'Life-threatening'
            5 = 'Fatal';
    run;
    """
    fmt = extract_format_catalog(source)["aegrf"]

    assert fmt.is_char is False
    assert len(fmt.entries) == 5
    assert [e.value for e in fmt.entries] == ["1", "2", "3", "4", "5"]
    assert [e.label for e in fmt.entries] == [
        "Mild",
        "Moderate",
        "Severe",
        "Life-threatening",
        "Fatal",
    ]
    assert all(e.low is None and e.high is None and not e.is_other for e in fmt.entries)


def test_multiple_value_blocks_in_one_proc_format() -> None:
    """Two ``value`` statements within one PROC FORMAT both register."""
    source = """
    proc format;
        value sevf
            1 = 'Low'
            2 = 'High';
        value $yn
            'Y' = 'Yes'
            'N' = 'No';
    run;
    """
    catalog = extract_format_catalog(source)

    assert set(catalog) == {"sevf", "$yn"}
    assert catalog["sevf"].is_char is False
    assert len(catalog["sevf"].entries) == 2
    assert catalog["$yn"].is_char is True
    assert len(catalog["$yn"].entries) == 2


def test_multiple_proc_format_blocks_in_one_source() -> None:
    """Two separate PROC FORMAT blocks are both scanned."""
    source = """
    proc format;
        value aef 1 = 'One';
    run;

    proc format library=library;
        value $gf 'M' = 'Male';
    run;
    """
    catalog = extract_format_catalog(source)

    assert set(catalog) == {"aef", "$gf"}
    assert catalog["aef"].entries[0].value == "1"
    assert catalog["$gf"].entries[0].value == "'M'"


def test_normalize_format_name() -> None:
    """Width/dot stripping, $ preservation, lowercasing, name-internal digits."""
    assert normalize_format_name("agegr1f8.") == "agegr1f"
    # Name-internal digit (the 1 in agegr1f) is preserved.
    assert normalize_format_name("agegr1f") == "agegr1f"
    assert normalize_format_name("$sexdec.") == "$sexdec"
    assert normalize_format_name("AEGRF") == "aegrf"


def test_malformed_input_does_not_raise() -> None:
    """Picture formats / garbage value lines are skipped without raising."""
    source = """
    proc format;
        picture pricefmt low-high = '000,009.99';
        value badfmt
            this is not a valid mapping
            7 = 'Seven';
    run;
    """
    # Must not raise; returns a (partial) catalog.
    catalog = extract_format_catalog(source)

    # The valid single-value mapping is still captured.
    assert "badfmt" in catalog
    labels = [e.label for e in catalog["badfmt"].entries]
    assert "Seven" in labels


def test_real_pharma_formats_fixture() -> None:
    """The on-disk pharma fixture parses to the expected catalog shape."""
    source = _PHARMA_FORMATS.read_text(encoding="utf-8")
    catalog = extract_format_catalog(source)

    assert {"agegr1f", "$sexdec", "aegrf"} <= set(catalog)
    assert len(catalog["agegr1f"].entries) == 4
    assert len(catalog["$sexdec"].entries) == 3
    assert len(catalog["aegrf"].entries) == 5


# ── F60 S-F: cross-file catalog population by SASParser ───────────────────────


def test_parser_collects_format_catalog_across_files() -> None:
    """PROC FORMAT in one file resolves for a put() reference in another file.

    Proves S-D collects the catalog across the whole file set: the format
    definitions live in ``formats.sas`` while the consuming DATA step (with a
    ``put(AGE, agegr1f.)`` derivation) lives in a separate ``derive.sas``.
    """
    formats_source = _PHARMA_FORMATS.read_text(encoding="utf-8")
    derive_source = (
        "data work.adsl;\n"
        "    set raw.dm;\n"
        "    agegr1 = put(age, agegr1f.);\n"
        "    sexd = put(sex, $sexdec.);\n"
        "run;\n"
    )
    files = {"formats.sas": formats_source, "derive.sas": derive_source}

    result = SASParser().parse(files)

    assert "agegr1f" in result.format_catalog
    assert "$sexdec" in result.format_catalog
    # The catalog content survives parsing (one of agegr1f's labels).
    labels = [e.label for e in result.format_catalog["agegr1f"].entries]
    assert "18-64" in labels


# ── F60 S-F: prompt-builder injection of "## Available SAS formats" ───────────


def _job_context_with_catalog(block: SASBlock) -> JobContext:
    """Build a minimal JobContext carrying the pharma catalog and *block*."""
    catalog = extract_format_catalog(_PHARMA_FORMATS.read_text(encoding="utf-8"))
    return JobContext(
        source_files={block.source_file: block.raw_sas},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[block],
        generated=[],
        format_catalog=catalog,
    )


def _data_step_block(raw_sas: str) -> SASBlock:
    """Construct a DATA step SASBlock with the given raw source."""
    return SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="derive.sas",
        start_line=1,
        end_line=4,
        raw_sas=raw_sas,
        input_datasets=["raw.dm"],
        output_datasets=["work.adsl"],
    )


def test_data_step_prompt_injects_referenced_format() -> None:
    """The DATA step prompt carries the format header and the agegr1f mapping."""
    block = _data_step_block("data work.adsl; set raw.dm; agegr1 = put(AGE, agegr1f.); run;")
    ctx = _job_context_with_catalog(block)
    windowed = ctx.windowed_context(block)

    prompt = _data_step_build_prompt(block, windowed, ctx.blocks)

    assert "## Available SAS formats" in prompt
    assert "agegr1f" in prompt
    assert "'18-64'" in prompt


def test_proc_prompt_injects_referenced_format() -> None:
    """The generic proc-agent prompt also injects the format section."""
    block = SASBlock(
        block_type=BlockType.PROC_SQL,
        source_file="derive.sas",
        start_line=1,
        end_line=3,
        raw_sas="proc sql; create table t as select put(AGE, agegr1f.) as grp from raw.dm; quit;",
        input_datasets=["raw.dm"],
        output_datasets=["t"],
    )
    ctx = _job_context_with_catalog(block)
    windowed = ctx.windowed_context(block)

    prompt = _proc_build_prompt(block, windowed, ctx.blocks)

    assert "## Available SAS formats" in prompt
    assert "'18-64'" in prompt


def test_data_step_prompt_matches_width_suffixed_reference() -> None:
    """A width-suffixed reference (agegr1f8.) still normalizes and renders."""
    block = _data_step_block("data work.adsl; set raw.dm; agegr1 = put(AGE, agegr1f8.); run;")
    ctx = _job_context_with_catalog(block)
    windowed = ctx.windowed_context(block)

    prompt = _data_step_build_prompt(block, windowed, ctx.blocks)

    assert "## Available SAS formats" in prompt
    assert "agegr1f" in prompt
    assert "'18-64'" in prompt


def test_data_step_prompt_matches_dollar_char_reference() -> None:
    """A $-prefixed char reference (put(SEX, $sexdec.)) renders its labels."""
    block = _data_step_block("data work.adsl; set raw.dm; sexd = put(SEX, $sexdec.); run;")
    ctx = _job_context_with_catalog(block)
    windowed = ctx.windowed_context(block)

    prompt = _data_step_build_prompt(block, windowed, ctx.blocks)

    assert "## Available SAS formats" in prompt
    assert "$sexdec" in prompt
    assert "'Male'" in prompt


def test_data_step_prompt_omits_section_for_builtin_format() -> None:
    """A built-in reference (dollar8.) not in the catalog yields no format section."""
    block = _data_step_block("data work.adsl; set raw.dm; amt = put(PAID, dollar8.); run;")
    ctx = _job_context_with_catalog(block)
    windowed = ctx.windowed_context(block)

    prompt = _data_step_build_prompt(block, windowed, ctx.blocks)

    assert "## Available SAS formats" not in prompt


# ---------------------------------------------------------------------------
# F61: declared column types section in _build_prompt (data_step agent)
# ---------------------------------------------------------------------------


def test_build_prompt_includes_declared_types_section() -> None:
    """_build_prompt includes declared-types section when block reads a typed sas7bdat."""
    from src.worker.engine.models import DataFileInfo

    block = SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="test.sas",
        start_line=1,
        end_line=5,
        raw_sas="data out; set adsl; run;",
        input_datasets=["adsl"],
        output_datasets=["out"],
    )
    data_file = DataFileInfo(
        path="data/raw/adsl.sas7bdat",
        disk_path="/fake/adsl.sas7bdat",
        extension=".sas7bdat",
        column_types={"subjid": "string", "age": "double"},
    )
    ctx = JobContext(
        source_files={},
        blocks=[block],
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        generated=[],
        libname_map={},
        data_files={"data/raw/adsl.sas7bdat": data_file},
    )
    windowed = ctx.windowed_context(block)

    prompt = _data_step_build_prompt(block, windowed, ctx.blocks)

    assert "## Declared source column types" in prompt
    assert "subjid: character" in prompt
    assert "age: numeric" in prompt
    assert "Do NOT write the load-time" in prompt


def test_build_prompt_omits_declared_types_section_when_no_data_files() -> None:
    """_build_prompt omits the declared-types section when data_files is empty."""
    block = SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="test.sas",
        start_line=1,
        end_line=5,
        raw_sas="data out; set adsl; run;",
        input_datasets=["adsl"],
        output_datasets=["out"],
    )
    ctx = JobContext(
        source_files={},
        blocks=[block],
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        generated=[],
        libname_map={},
        data_files={},  # empty — no typed files
    )
    windowed = ctx.windowed_context(block)

    prompt = _data_step_build_prompt(block, windowed, ctx.blocks)

    assert "## Declared source column types" not in prompt


def test_build_prompt_omits_declared_types_section_when_column_types_empty() -> None:
    """_build_prompt omits the declared-types section when column_types is empty ({})."""
    from src.worker.engine.models import DataFileInfo

    block = SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="test.sas",
        start_line=1,
        end_line=5,
        raw_sas="data out; set adsl; run;",
        input_datasets=["adsl"],
        output_datasets=["out"],
    )
    data_file = DataFileInfo(
        path="data/raw/adsl.sas7bdat",
        disk_path="/fake/adsl.sas7bdat",
        extension=".sas7bdat",
        column_types={},  # no declared types (e.g. CSV)
    )
    ctx = JobContext(
        source_files={},
        blocks=[block],
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        generated=[],
        libname_map={},
        data_files={"data/raw/adsl.sas7bdat": data_file},
    )
    windowed = ctx.windowed_context(block)

    prompt = _data_step_build_prompt(block, windowed, ctx.blocks)

    assert "## Declared source column types" not in prompt
