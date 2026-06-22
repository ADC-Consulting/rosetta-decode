"""Unit tests for the F77 rule-based scoping engine (LLM-free, deterministic).

Covers complexity-tier classification (simple/moderate/complex incl. non-BASE
engine, INFILE, and macro-nesting paths), the exhaustive translation-category
map, each risk-flag kind (including the engine-only-libref gotcha), data-asset
assembly, and effort math.
"""

from src.worker.engine.estimation_model import RATE_TABLE, estimate_effort
from src.worker.engine.models import (
    BlockType,
    FileInventoryItem,
    MacroDef,
    ParseResult,
    SASBlock,
)
from src.worker.engine.parser import SASParser
from src.worker.engine.scoping import (
    _CATEGORY_BY_TYPE,
    _category_by_type,
    build_scoping_report,
)


def _parse(files: dict[str, str]) -> ParseResult:
    return SASParser().parse(files)


def _tier_of(files: dict[str, str], source_file: str = "t.sas") -> str:
    report = build_scoping_report(_parse(files), files)
    item = next(f for f in report.file_inventory if f.source_file == source_file)
    return item.complexity_tier


# ── Complexity tier ───────────────────────────────────────────────────────────


def test_tier_simple_data_and_sort_only() -> None:
    sas = (
        "DATA work.clean;\n  SET work.raw;\n  x = 1;\nRUN;\n"
        "PROC SORT DATA=work.clean OUT=work.s;\n  BY id;\nRUN;\n"
    )
    assert _tier_of({"t.sas": sas}) == "simple"


def test_tier_moderate_proc_sql() -> None:
    sas = "PROC SQL;\n  CREATE TABLE work.a AS SELECT * FROM work.b;\nQUIT;\n"
    assert _tier_of({"t.sas": sas}) == "moderate"


def test_tier_complex_proc_iml() -> None:
    sas = "PROC IML;\n  x = {1 2 3};\nQUIT;\n"
    assert _tier_of({"t.sas": sas}) == "complex"


def test_tier_complex_unknown_proc() -> None:
    sas = "PROC FROBNICATE DATA=x;\nRUN;\n"
    assert _tier_of({"t.sas": sas}) == "complex"


def test_tier_complex_non_base_engine() -> None:
    sas = 'LIBNAME ora oracle "/d";\nDATA work.c;\n  SET ora.raw;\nRUN;\n'
    assert _tier_of({"t.sas": sas}) == "complex"


def test_tier_complex_infile_external_io() -> None:
    sas = "DATA work.out;\n  INFILE '/raw/in.txt';\n  INPUT x y;\nRUN;\n"
    assert _tier_of({"t.sas": sas}) == "complex"


def test_tier_complex_ods_present() -> None:
    sas = 'ODS PDF FILE="/out/r.pdf";\nDATA work.x;\n  SET work.y;\nRUN;\nODS PDF CLOSE;\n'
    assert _tier_of({"t.sas": sas}) == "complex"


def test_tier_complex_heavy_macro_nesting() -> None:
    sas = (
        "%macro deep();\n"
        "  %do i=1 %to 3;\n    %do j=1 %to 2;\n      %do k=1 %to 2;\n"
        "        data work.t&i; set work.s; run;\n"
        "      %end;\n    %end;\n  %end;\n"
        "%mend;\n"
        "%deep();\n"
    )
    assert _tier_of({"t.sas": sas}) == "complex"


# ── Translation-category map ──────────────────────────────────────────────────


def test_category_map_exhaustive_over_block_type() -> None:
    # Every BlockType must be categorised; helper raises otherwise.
    mapping = _category_by_type()
    assert set(mapping) == set(BlockType)
    assert all(bt in _CATEGORY_BY_TYPE for bt in BlockType)


def test_category_map_known_assignments() -> None:
    assert _CATEGORY_BY_TYPE[BlockType.DATA_STEP] == "auto_translatable"
    assert _CATEGORY_BY_TYPE[BlockType.PROC_SQL] == "needs_review"
    assert _CATEGORY_BY_TYPE[BlockType.PROC_IML] == "manual"
    assert _CATEGORY_BY_TYPE[BlockType.PROC_UNKNOWN] == "manual"
    assert _CATEGORY_BY_TYPE[BlockType.UNTRANSLATABLE] == "untranslatable"


# ── Block breakdown ───────────────────────────────────────────────────────────


def test_block_breakdown_includes_macro_pseudo_types() -> None:
    sas = (
        "%macro helper();\n  data work.h; set work.s; run;\n%mend;\n"
        "%helper();\n%helper();\n"
        "DATA work.x;\n  SET work.y;\nRUN;\n"
    )
    report = build_scoping_report(_parse({"t.sas": sas}), {"t.sas": sas})
    bd = report.block_breakdown
    assert bd.counts_by_type["macro_def"] == 1
    assert bd.counts_by_type["macro_call"] >= 2
    assert bd.total_blocks >= 1
    # category_by_type only carries real block types, not the pseudo-types.
    assert "macro_def" not in bd.category_by_type


# ── Risk flags ────────────────────────────────────────────────────────────────


def test_risk_missing_macro_flag() -> None:
    sas = "DATA work.x;\n  %undefined_macro();\nRUN;\n"
    report = build_scoping_report(_parse({"t.sas": sas}), {"t.sas": sas})
    flag = next(f for f in report.risk_flags if f.kind == "missing_macro")
    assert flag.count >= 1


def test_risk_missing_include_flag() -> None:
    sas = '%INCLUDE "/macros/util.sas";\nDATA work.x;\n  SET work.y;\nRUN;\n'
    report = build_scoping_report(_parse({"t.sas": sas}), {"t.sas": sas})
    assert any(f.kind == "missing_include" for f in report.risk_flags)


def test_risk_unknown_proc_flag_has_locations() -> None:
    sas = "PROC FROBNICATE DATA=x;\nRUN;\n"
    report = build_scoping_report(_parse({"t.sas": sas}), {"t.sas": sas})
    flag = next(f for f in report.risk_flags if f.kind == "unknown_proc")
    assert flag.count == 1
    assert isinstance(flag.detail, list)
    assert flag.detail[0]["source_file"] == "t.sas"


def test_risk_external_dependency_flag() -> None:
    sas = "LIBNAME ora oracle \"/d\";\nDATA work.x;\n  INFILE '/raw/in.txt';\n  INPUT a;\nRUN;\n"
    report = build_scoping_report(_parse({"t.sas": sas}), {"t.sas": sas})
    flag = next(f for f in report.risk_flags if f.kind == "external_dependency")
    assert flag.count >= 2  # one external path + one non-BASE engine libname


def test_risk_missing_reference_data_flag_for_unmapped_libref() -> None:
    sas = "DATA work.x;\n  SET unmapped.raw;\nRUN;\n"
    report = build_scoping_report(_parse({"t.sas": sas}), {"t.sas": sas})
    flag = next(f for f in report.risk_flags if f.kind == "missing_reference_data")
    assert isinstance(flag.detail, list)
    assert "unmapped" in flag.detail


def test_engine_only_libref_not_flagged_as_missing_reference() -> None:
    """The S-A gotcha: engine-form LIBNAME populates libname_engines only.

    Such a libref must be treated as KNOWN, never flagged missing_reference_data.
    """
    sas = 'LIBNAME ora oracle "/d";\nDATA work.x;\n  SET ora.raw;\nRUN;\n'
    parse_result = _parse({"t.sas": sas})
    # Precondition: confirms the gotcha — engine map has it, legacy map does not.
    assert "ora" in parse_result.libname_engines
    assert "ora" not in parse_result.libname_map
    report = build_scoping_report(parse_result, {"t.sas": sas})
    missing = [f for f in report.risk_flags if f.kind == "missing_reference_data"]
    assert all("ora" not in (f.detail or []) for f in missing)


def test_implicit_work_libref_not_flagged() -> None:
    sas = "DATA work.x;\n  SET work.y;\nRUN;\n"
    report = build_scoping_report(_parse({"t.sas": sas}), {"t.sas": sas})
    assert not any(f.kind == "missing_reference_data" for f in report.risk_flags)


# ── Data-asset inventory ──────────────────────────────────────────────────────


def test_data_assets_merge_map_and_engines() -> None:
    sas = 'LIBNAME ora oracle "/d";\nLIBNAME out "/o";\nDATA out.clean;\n  SET ora.raw;\nRUN;\n'
    report = build_scoping_report(_parse({"t.sas": sas}), {"t.sas": sas})
    libnames = {entry["libref"]: entry for entry in report.data_assets.libnames}
    assert libnames["ora"]["engine"] == "oracle"
    assert "path" not in libnames["ora"]  # engine-form has no legacy path
    assert libnames["out"]["engine"] == "BASE"
    assert libnames["out"]["path"] == "/o"
    assert "ora.raw" in report.data_assets.input_datasets
    assert "out.clean" in report.data_assets.output_datasets


def test_sentinel_keys_skipped_in_inventory() -> None:
    sas = "DATA work.x;\n  SET work.y;\nRUN;\n"
    files = {"t.sas": sas, "__ref_csv__": "/disk/ref.csv", "notes.txt": "ignore"}
    report = build_scoping_report(_parse(files), files)
    assert report.total_files == 1
    assert [f.source_file for f in report.file_inventory] == ["t.sas"]


# ── Effort estimate ───────────────────────────────────────────────────────────


def test_effort_provisional_and_ordered() -> None:
    inventory = [
        FileInventoryItem(
            source_file="a.sas",
            line_count=10,
            block_count=2,
            complexity_tier="simple",
        ),
        FileInventoryItem(
            source_file="b.sas",
            line_count=50,
            block_count=5,
            complexity_tier="complex",
        ),
    ]
    estimate = estimate_effort(inventory)
    assert estimate.provisional is True
    assert estimate.low_days <= estimate.mid_days <= estimate.high_days
    expected_low = RATE_TABLE["simple"][0] + RATE_TABLE["complex"][0]
    assert estimate.low_days == round(expected_low, 4)


def test_effort_empty_inventory_is_zero() -> None:
    estimate = estimate_effort([])
    assert estimate.low_days == estimate.mid_days == estimate.high_days == 0.0


def test_effort_deterministic_rerun() -> None:
    inventory = [
        FileInventoryItem(
            source_file="a.sas",
            line_count=10,
            block_count=2,
            complexity_tier="moderate",
        ),
    ]
    assert estimate_effort(inventory).model_dump() == estimate_effort(inventory).model_dump()


# ── Full report determinism ───────────────────────────────────────────────────


def test_report_byte_identical_on_rerun() -> None:
    sas = (
        'LIBNAME ora oracle "/d";\n'
        "DATA work.clean;\n  SET ora.raw;\nRUN;\n"
        "PROC SQL;\n  CREATE TABLE work.a AS SELECT * FROM work.clean;\nQUIT;\n"
        "PROC FROBNICATE DATA=x;\nRUN;\n"
    )
    files = {"prog.sas": sas}
    first = build_scoping_report(_parse(files), files).model_dump()
    second = build_scoping_report(_parse(files), files).model_dump()
    assert first == second


def test_block_definition_macro_nesting_helper_direct() -> None:
    # A nested %macro alone triggers heavy nesting via the helper path.
    from src.worker.engine.scoping import _is_heavily_nested

    nested = MacroDef(
        name="OUTER",
        body="%macro inner(); data work.x; set work.y; run; %mend;",
        source_file="t.sas",
        line=1,
    )
    shallow = MacroDef(
        name="FLAT",
        body="data work.x; set work.y; run;",
        source_file="t.sas",
        line=1,
    )
    assert _is_heavily_nested(nested) is True
    assert _is_heavily_nested(shallow) is False


def test_block_has_blocks_attribute_sanity() -> None:
    # Guard that SASBlock is importable for fixture authoring.
    block = SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="t.sas",
        start_line=1,
        end_line=2,
        raw_sas="data x; run;",
    )
    assert block.block_type == BlockType.DATA_STEP
