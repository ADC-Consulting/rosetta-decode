"""Reconciliation tests: SAS LENGTH $w → CSV columns read as string (leading zeros preserved)."""

from src.worker.engine.agents.shared import enforce_csv_read_schema
from src.worker.engine.models import DataFileInfo
from src.worker.engine.parser import extract_declared_char_columns

# ---------------------------------------------------------------------------
# extract_declared_char_columns
# ---------------------------------------------------------------------------


def test_extract_char_columns_basic() -> None:
    sas = "length USUBJID $40 STUDYID $20 SUBJID $8 SITEID $4 AGE 8;"
    result = extract_declared_char_columns(sas)
    assert result == {"usubjid", "studyid", "subjid", "siteid"}
    assert "age" not in result


def test_extract_char_columns_multiple_stmts() -> None:
    sas = "length ARM $40 ACTARM $40;\nlength AGE 8 AGEU $8;"
    result = extract_declared_char_columns(sas)
    assert "arm" in result
    assert "actarm" in result
    assert "ageu" in result
    assert "age" not in result


def test_extract_char_columns_no_dollar() -> None:
    sas = "length AGE 8 WEIGHT 8.2;"
    assert extract_declared_char_columns(sas) == set()


def test_extract_char_columns_dollar_no_width() -> None:
    sas = "length FLAG $ SEX $;"
    result = extract_declared_char_columns(sas)
    assert "flag" in result
    assert "sex" in result


def test_extract_char_columns_empty() -> None:
    assert extract_declared_char_columns("") == set()
    assert extract_declared_char_columns("data foo; x = 1; run;") == set()


# ---------------------------------------------------------------------------
# enforce_csv_read_schema
# ---------------------------------------------------------------------------


def _make_info(
    columns: list[str],
    column_types: dict[str, str],
    path: str = "data/raw/dm_raw.csv",
    ext: str = ".csv",
) -> DataFileInfo:
    return DataFileInfo(
        path=path,
        disk_path=f"/workspace/{path}",
        extension=ext,
        columns=columns,
        row_count=10,
        column_types=column_types,
    )


def test_enforce_csv_read_schema_rewrites_infer_schema() -> None:
    code = 'dm = spark.read.csv("/workspace/data/raw/dm_raw.csv", header=True, inferSchema=True)'
    info = _make_info(
        columns=["STUDYID", "SITEID", "SUBJID", "AGE"],
        column_types={"studyid": "string", "siteid": "string", "subjid": "string", "age": "long"},
    )
    result = enforce_csv_read_schema(code, {"data/raw/dm_raw.csv": info}, "TestAgent")
    assert "inferSchema=True" not in result
    assert "schema=" in result
    assert "StructType" in result
    assert "StringType()" in result
    assert "LongType()" in result
    assert "from pyspark.sql.types import" in result


def test_enforce_csv_read_schema_idempotent() -> None:
    code = (
        'dm = spark.read.csv("/workspace/data/raw/dm_raw.csv", header=True, schema=_dm_raw_schema)'
    )
    info = _make_info(
        columns=["STUDYID", "SITEID", "SUBJID", "AGE"],
        column_types={"studyid": "string", "siteid": "string", "subjid": "string", "age": "long"},
    )
    result = enforce_csv_read_schema(code, {"data/raw/dm_raw.csv": info}, "TestAgent")
    assert result == code


def test_enforce_csv_read_schema_empty_column_types_noop() -> None:
    code = 'dm = spark.read.csv("/workspace/data/raw/dm_raw.csv", header=True, inferSchema=True)'
    info = _make_info(columns=["AGE", "WEIGHT"], column_types={})
    result = enforce_csv_read_schema(code, {"data/raw/dm_raw.csv": info}, "TestAgent")
    assert result == code


def test_enforce_csv_read_schema_preserves_header_option() -> None:
    code = 'dm = spark.read.csv("/workspace/data/raw/dm_raw.csv", header=True, inferSchema=True)'
    info = _make_info(
        columns=["SITEID"],
        column_types={"siteid": "string"},
    )
    result = enforce_csv_read_schema(code, {"data/raw/dm_raw.csv": info}, "TestAgent")
    assert "header=True" in result
    assert "schema=" in result


# ---------------------------------------------------------------------------
# Integration: declared-char override logic (mirrors main.py _execute)
# ---------------------------------------------------------------------------


def test_declared_char_override_forces_string() -> None:
    pandas_inferred = {"studyid": "string", "siteid": "long", "subjid": "long", "age": "long"}
    declared_char = {"studyid", "siteid", "subjid"}
    column_types = dict(pandas_inferred)
    for col in list(column_types.keys()):
        if col in declared_char:
            column_types[col] = "string"
    assert column_types["siteid"] == "string"
    assert column_types["subjid"] == "string"
    assert column_types["age"] == "long"
