"""Tests for agentic pipeline context improvements (DataFileInfo, shared_context, stub).

Covers:
- DataFileInfo model construction
- JobContext new fields have default_factory (no breakage)
- windowed_context() includes macro/autoexec source files and passes data_files/libname_map
- build_context_section() rendering logic
- StubGenerator.generate() with data_files catalogue
- _StrategyStubAdapter passes data_files to generate()
- _sniff_file() CSV/TSV/XLSX/sas7bdat branches and error handling
"""

from unittest.mock import MagicMock, patch

import pytest
from src.worker.engine.agents.shared_context import build_context_section
from src.worker.engine.models import BlockType, DataFileInfo, JobContext, SASBlock
from src.worker.engine.router import _StrategyStubAdapter
from src.worker.engine.stub_generator import StubGenerator
from src.worker.main import _sniff_file

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_block(
    block_type: BlockType = BlockType.PROC_IMPORT,
    input_datasets: list[str] | None = None,
    output_datasets: list[str] | None = None,
) -> SASBlock:
    return SASBlock(
        block_type=block_type,
        source_file="01_load_sources.sas",
        start_line=3,
        end_line=6,
        raw_sas="proc import datafile=csvcust out=rawdir.customers dbms=csv replace; run;",
        input_datasets=input_datasets or [],
        output_datasets=output_datasets or ["rawdir.customers"],
    )


def _make_context(
    data_files: dict[str, DataFileInfo] | None = None,
    libname_map: dict[str, str] | None = None,
    source_files: dict[str, str] | None = None,
) -> JobContext:
    return JobContext(
        source_files=source_files or {},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
        data_files=data_files or {},
        libname_map=libname_map or {},
    )


# ── DataFileInfo ──────────────────────────────────────────────────────────────


def test_data_file_info_defaults() -> None:
    info = DataFileInfo(path="data/raw/x.csv", disk_path="/tmp/x.csv", extension=".csv")
    assert info.columns == []
    assert info.row_count is None


def test_data_file_info_full() -> None:
    info = DataFileInfo(
        path="data/raw/customers.csv",
        disk_path="/tmp/customers.csv",
        extension=".csv",
        columns=["id", "name"],
        row_count=100,
    )
    assert info.columns == ["id", "name"]
    assert info.row_count == 100


# ── JobContext defaults ────────────────────────────────────────────────────────


def test_job_context_default_fields() -> None:
    """New fields must not break existing JobContext construction."""
    ctx = JobContext(
        source_files={},
        resolved_macros=[],
        dependency_order=[],
        risk_flags=[],
        blocks=[],
        generated=[],
    )
    assert ctx.data_files == {}
    assert ctx.libname_map == {}


# ── windowed_context ──────────────────────────────────────────────────────────


def test_windowed_context_includes_macro_files() -> None:
    ctx = _make_context(
        source_files={
            "sas/01_load.sas": "proc import; run;",
            "macros/clean_string.sas": "%macro clean_string(x); &x; %mend;",
            "autoexec.sas": "libname rawdir 'data/raw/';",
        },
        data_files={
            "data/raw/customers.csv": DataFileInfo(
                path="data/raw/customers.csv",
                disk_path="/tmp/customers.csv",
                extension=".csv",
                columns=["id", "name"],
                row_count=10,
            )
        },
        libname_map={"rawdir": "data/raw/"},
    )
    block = _make_block()
    windowed = ctx.windowed_context(block)
    # Macro and autoexec files must be present
    assert "macros/clean_string.sas" in windowed.source_files
    assert "autoexec.sas" in windowed.source_files
    # Regular SAS program file must NOT be present
    assert "sas/01_load.sas" not in windowed.source_files
    # data_files and libname_map must pass through
    assert windowed.data_files == ctx.data_files
    assert windowed.libname_map == ctx.libname_map


def test_windowed_context_no_macro_files() -> None:
    ctx = _make_context(source_files={"sas/01_load.sas": "proc import; run;"})
    block = _make_block()
    windowed = ctx.windowed_context(block)
    assert windowed.source_files == {}


# ── build_context_section ─────────────────────────────────────────────────────


def test_build_context_section_empty() -> None:
    ctx = _make_context()
    assert build_context_section(ctx) == ""


def test_build_context_section_libname_only() -> None:
    ctx = _make_context(libname_map={"rawdir": "data/raw/", "outdir": "data/output/"})
    section = build_context_section(ctx)
    assert "## Project context" in section
    assert "### SAS libname / filename mappings" in section
    assert "rawdir → data/raw/" in section
    assert "outdir → data/output/" in section
    assert "For any file I/O block" in section


def test_build_context_section_data_files_only() -> None:
    ctx = _make_context(
        data_files={
            "data/raw/customers.csv": DataFileInfo(
                path="data/raw/customers.csv",
                disk_path="/tmp/customers.csv",
                extension=".csv",
                columns=["id", "name"],
                row_count=42,
            )
        }
    )
    section = build_context_section(ctx)
    assert "### Data files in this project" in section
    assert "data/raw/customers.csv" in section
    assert "[columns: id, name]" in section
    assert "(42 rows)" in section


def test_build_context_section_no_libnames_subsection_when_empty() -> None:
    ctx = _make_context(
        data_files={
            "data/raw/x.csv": DataFileInfo(
                path="data/raw/x.csv", disk_path="/tmp/x.csv", extension=".csv"
            )
        }
    )
    section = build_context_section(ctx)
    assert "### SAS libname" not in section


def test_build_context_section_columns_omitted_when_empty() -> None:
    ctx = _make_context(
        data_files={
            "data/raw/x.csv": DataFileInfo(
                path="data/raw/x.csv", disk_path="/tmp/x.csv", extension=".csv"
            )
        }
    )
    section = build_context_section(ctx)
    assert "[columns:" not in section
    assert "(None rows)" not in section


# ── StubGenerator ─────────────────────────────────────────────────────────────


def test_stub_generator_manual_ingestion_no_data_files() -> None:
    stub = StubGenerator()
    block = _make_block()
    gb = stub.generate(block, strategy="manual_ingestion")
    assert 'pd.read_csv("path/to/input.csv")' in gb.python_code
    assert gb.is_untranslatable is True


def test_stub_generator_manual_ingestion_with_real_path() -> None:
    stub = StubGenerator()
    # Use output dataset whose normalised form appears in the file path key:
    # "data/raw/customers" -> norm -> contained in "data/raw/customers.csv"
    block = _make_block(output_datasets=["data/raw/customers"])
    data_files = {
        "data/raw/customers.csv": DataFileInfo(
            path="data/raw/customers.csv",
            disk_path="/tmp/customers.csv",
            extension=".csv",
            columns=["id", "name"],
            row_count=10,
        )
    }
    gb = stub.generate(block, strategy="manual_ingestion", data_files=data_files)
    assert '"data/raw/customers.csv"' in gb.python_code
    assert "# Columns: id, name" in gb.python_code


def test_stub_generator_normal_stub() -> None:
    stub = StubGenerator()
    block = _make_block()
    gb = stub.generate(block, strategy=None)
    assert "SAS-UNTRANSLATABLE" in gb.python_code
    assert gb.is_untranslatable is True


# ── _StrategyStubAdapter ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_strategy_stub_adapter_passes_data_files() -> None:
    stub = StubGenerator()
    adapter = _StrategyStubAdapter(stub, "manual_ingestion")
    data_files = {
        "data/raw/customers.csv": DataFileInfo(
            path="data/raw/customers.csv",
            disk_path="/tmp/customers.csv",
            extension=".csv",
            columns=["id", "name"],
            row_count=10,
        )
    }
    ctx = _make_context(data_files=data_files)
    # Normalised form of "data/raw/customers" is in "data/raw/customers.csv"
    block = _make_block(output_datasets=["data/raw/customers"])
    gb = await adapter.translate(block, ctx)
    assert '"data/raw/customers.csv"' in gb.python_code


@pytest.mark.asyncio
async def test_strategy_stub_adapter_empty_data_files() -> None:
    stub = StubGenerator()
    adapter = _StrategyStubAdapter(stub, "manual_ingestion")
    ctx = _make_context()
    block = _make_block()
    gb = await adapter.translate(block, ctx)
    assert 'pd.read_csv("path/to/input.csv")' in gb.python_code


# ── _sniff_file ───────────────────────────────────────────────────────────────


def _make_pandas_mock(columns: list[str], row_count: int) -> MagicMock:
    """Return a minimal mock for pandas with read_csv / read_excel."""
    header_df = MagicMock()
    header_df.columns = columns
    full_df = MagicMock()
    full_df.__len__ = MagicMock(return_value=row_count)

    pd_mock = MagicMock()
    pd_mock.read_csv.side_effect = [header_df, full_df]
    pd_mock.read_excel.side_effect = [header_df, full_df]
    return pd_mock


def test_sniff_file_csv() -> None:
    """_sniff_file returns columns and row count for .csv files."""
    pd_mock = _make_pandas_mock(["a", "b"], 5)
    with patch.dict("sys.modules", {"pandas": pd_mock}):
        cols, rows = _sniff_file("/tmp/test.csv", ".csv")
    assert cols == ["a", "b"]
    assert rows == 5


def test_sniff_file_tsv() -> None:
    """_sniff_file uses tab separator for .tsv files."""
    pd_mock = _make_pandas_mock(["x", "y"], 3)
    with patch.dict("sys.modules", {"pandas": pd_mock}):
        cols, rows = _sniff_file("/tmp/test.tsv", ".tsv")
    assert cols == ["x", "y"]
    assert rows == 3
    # Verify tab separator was used
    call_args = pd_mock.read_csv.call_args_list[0]
    assert call_args.kwargs.get("sep") == "\t" or (
        len(call_args.args) > 1 and call_args.args[1] == "\t"
    )


def test_sniff_file_xlsx() -> None:
    """_sniff_file returns columns and row count for .xlsx files."""
    pd_mock = _make_pandas_mock(["col1", "col2"], 10)
    with patch.dict("sys.modules", {"pandas": pd_mock}):
        cols, rows = _sniff_file("/tmp/test.xlsx", ".xlsx")
    assert cols == ["col1", "col2"]
    assert rows == 10


def test_sniff_file_xls() -> None:
    """_sniff_file returns columns and row count for .xls files."""
    pd_mock = _make_pandas_mock(["name"], 2)
    with patch.dict("sys.modules", {"pandas": pd_mock}):
        cols, rows = _sniff_file("/tmp/test.xls", ".xls")
    assert cols == ["name"]
    assert rows == 2


def test_sniff_file_sas7bdat_with_pyreadstat() -> None:
    """_sniff_file returns columns and None row count for .sas7bdat via pyreadstat."""
    meta = MagicMock()
    meta.column_names = ["id", "value"]

    pyreadstat_mock = MagicMock()
    pyreadstat_mock.read_sas7bdat.return_value = (MagicMock(), meta)

    pd_mock = MagicMock()
    with patch.dict("sys.modules", {"pandas": pd_mock, "pyreadstat": pyreadstat_mock}):
        cols, rows = _sniff_file("/tmp/test.sas7bdat", ".sas7bdat")
    assert cols == ["id", "value"]
    assert rows is None


def test_sniff_file_sas7bdat_no_pyreadstat() -> None:
    """_sniff_file returns ([], None) when pyreadstat is not installed."""
    pd_mock = MagicMock()

    import sys

    original = sys.modules.pop("pyreadstat", None)
    try:
        with patch.dict("sys.modules", {"pandas": pd_mock, "pyreadstat": None}):
            cols, rows = _sniff_file("/tmp/test.sas7bdat", ".sas7bdat")
        assert cols == []
        assert rows is None
    finally:
        if original is not None:
            sys.modules["pyreadstat"] = original


def test_sniff_file_exception_returns_empty() -> None:
    """_sniff_file returns ([], None) when any read error occurs."""
    pd_mock = MagicMock()
    pd_mock.read_csv.side_effect = OSError("file not found")
    with patch.dict("sys.modules", {"pandas": pd_mock}):
        cols, rows = _sniff_file("/tmp/missing.csv", ".csv")
    assert cols == []
    assert rows is None


def test_sniff_file_unknown_extension_returns_empty() -> None:
    """_sniff_file returns ([], None) for unsupported extensions."""
    pd_mock = MagicMock()
    with patch.dict("sys.modules", {"pandas": pd_mock}):
        cols, rows = _sniff_file("/tmp/data.parquet", ".parquet")
    assert cols == []
    assert rows is None
