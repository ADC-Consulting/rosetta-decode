"""Unit tests for inject_declared_casts (F61).

Covers:
- Happy path with toDF line present: cast block injected immediately after toDF.
- Happy path with toDF absent: toDF is synthesised, cast block follows.
- Idempotence: calling inject_declared_casts twice yields the same result.
- No-op when column_types is empty.
- Column names are already lowercased by _sniff_file; withColumn uses them verbatim.
- Provenance comment format.
"""

import textwrap

from src.worker.engine.agents.shared import inject_declared_casts
from src.worker.engine.models import DataFileInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _data_file(
    path: str = "data/raw/adsl.sas7bdat",
    column_types: dict[str, str] | None = None,
) -> DataFileInfo:
    """Construct a DataFileInfo with sensible defaults for tests."""
    return DataFileInfo(
        path=path,
        disk_path="/fake/" + path.rsplit("/", 1)[-1],
        extension=".sas7bdat",
        column_types=column_types or {},
    )


# ---------------------------------------------------------------------------
# Happy path — toDF line present
# ---------------------------------------------------------------------------


def test_inject_with_todf_line_inserts_cast_block_after_todf() -> None:
    """When a toDF normalisation line exists, casts are injected immediately after it."""
    code = textwrap.dedent("""
        adsl = spark.read.format("sas7bdat").load("/workspace/data/adsl.sas7bdat")
        adsl = adsl.toDF(*[c.lower() for c in adsl.columns])
        adsl = adsl.filter(F.col("subjid").isNotNull())
    """).strip()

    data_files = {
        "data/raw/adsl.sas7bdat": _data_file(column_types={"subjid": "string", "age": "double"})
    }
    result = inject_declared_casts(code, data_files, "TestAgent")

    assert "# SAS: data/raw/adsl.sas7bdat (declared type)" in result
    assert 'adsl = adsl.withColumn("subjid", F.col("subjid").cast("string"))' in result
    assert 'adsl = adsl.withColumn("age", F.col("age").cast("double"))' in result

    # Cast block must appear before the downstream filter
    assert result.index("# SAS:") < result.index("adsl.filter")


def test_inject_with_todf_preserves_rest_of_code() -> None:
    """Injecting casts does not corrupt code that comes after the cast block."""
    code = textwrap.dedent("""
        adsl = spark.read.format("sas7bdat").load("/workspace/data/adsl.sas7bdat")
        adsl = adsl.toDF(*[c.lower() for c in adsl.columns])
        result = adsl.select("subjid", "age")
    """).strip()

    data_files = {"data/raw/adsl.sas7bdat": _data_file(column_types={"subjid": "string"})}
    result = inject_declared_casts(code, data_files, "TestAgent")

    # Downstream select must still be present
    assert 'result = adsl.select("subjid", "age")' in result


# ---------------------------------------------------------------------------
# Happy path — toDF line absent (synthesised)
# ---------------------------------------------------------------------------


def test_inject_without_todf_synthesises_it() -> None:
    """When no toDF line is present, one is synthesised after the read assignment."""
    code = 'adsl = spark.read.format("sas7bdat").load("/workspace/data/adsl.sas7bdat")'
    data_files = {"data/raw/adsl.sas7bdat": _data_file(column_types={"subjid": "string"})}
    result = inject_declared_casts(code, data_files, "TestAgent")

    assert "adsl.toDF(" in result
    assert '.cast("string")' in result


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


def test_inject_is_idempotent() -> None:
    """Calling inject_declared_casts twice on its own output produces the same string."""
    code = textwrap.dedent("""
        adsl = spark.read.format("sas7bdat").load("/workspace/data/adsl.sas7bdat")
        adsl = adsl.toDF(*[c.lower() for c in adsl.columns])
        result = adsl.filter(F.col("subjid").isNotNull())
    """).strip()

    data_files = {
        "data/raw/adsl.sas7bdat": _data_file(column_types={"subjid": "string", "age": "double"})
    }
    result1 = inject_declared_casts(code, data_files, "TestAgent")
    result2 = inject_declared_casts(result1, data_files, "TestAgent")
    assert result1 == result2


# ---------------------------------------------------------------------------
# No-op for empty column_types
# ---------------------------------------------------------------------------


def test_inject_noop_when_column_types_empty() -> None:
    """When column_types is empty, the code is returned unchanged."""
    code = textwrap.dedent("""
        adsl = spark.read.format("sas7bdat").load("/workspace/data/adsl.sas7bdat")
        adsl = adsl.toDF(*[c.lower() for c in adsl.columns])
    """).strip()

    data_files = {"data/raw/adsl.sas7bdat": _data_file(column_types={})}
    result = inject_declared_casts(code, data_files, "TestAgent")
    assert result == code


# ---------------------------------------------------------------------------
# Already-lowercased column names produce correct withColumn calls
# ---------------------------------------------------------------------------


def test_inject_lowercased_column_names_in_withcolumn() -> None:
    """Column names in column_types are already lowercased; withColumn uses them verbatim."""
    code_with_todf = textwrap.dedent("""
        adsl = spark.read.format("sas7bdat").load("/workspace/data/adsl.sas7bdat")
        adsl = adsl.toDF(*[c.lower() for c in adsl.columns])
    """).strip()

    # column_types keys are already lowercased by _sniff_file
    data_files = {"data/raw/adsl.sas7bdat": _data_file(column_types={"subjid": "string"})}
    result = inject_declared_casts(code_with_todf, data_files, "TestAgent")

    assert 'withColumn("subjid"' in result


# ---------------------------------------------------------------------------
# Provenance comment format
# ---------------------------------------------------------------------------


def test_inject_provenance_comment_format() -> None:
    """The provenance comment must match the exact format '# SAS: <path> (declared type)'."""
    code = textwrap.dedent("""
        adsl = spark.read.format("sas7bdat").load("/workspace/data/adsl.sas7bdat")
        adsl = adsl.toDF(*[c.lower() for c in adsl.columns])
    """).strip()

    data_files = {"data/raw/adsl.sas7bdat": _data_file(column_types={"age": "double"})}
    result = inject_declared_casts(code, data_files, "TestAgent")

    assert "# SAS: data/raw/adsl.sas7bdat (declared type)" in result


# ---------------------------------------------------------------------------
# Multiple columns sorted deterministically
# ---------------------------------------------------------------------------


def test_inject_columns_emitted_in_sorted_order() -> None:
    """Cast lines are emitted in sorted column-name order (deterministic output)."""
    code = textwrap.dedent("""
        adsl = spark.read.format("sas7bdat").load("/workspace/data/adsl.sas7bdat")
        adsl = adsl.toDF(*[c.lower() for c in adsl.columns])
    """).strip()

    data_files = {
        "data/raw/adsl.sas7bdat": _data_file(
            column_types={"zzz": "double", "aaa": "string", "mmm": "double"}
        )
    }
    result = inject_declared_casts(code, data_files, "TestAgent")

    aaa_pos = result.index('"aaa"')
    mmm_pos = result.index('"mmm"')
    zzz_pos = result.index('"zzz"')
    assert aaa_pos < mmm_pos < zzz_pos


# ---------------------------------------------------------------------------
# No-op when read-assignment line for the file is absent
# ---------------------------------------------------------------------------


def test_inject_noop_when_file_not_referenced_in_code() -> None:
    """When no read-assignment for the file is found, code is returned unchanged."""
    code = "result = spark.range(10)"
    data_files = {"data/raw/adsl.sas7bdat": _data_file(column_types={"subjid": "string"})}
    result = inject_declared_casts(code, data_files, "TestAgent")
    # No read-assignment for adsl — nothing injected; code unchanged
    assert result == code
