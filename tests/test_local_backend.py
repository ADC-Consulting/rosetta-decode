"""Unit tests for LocalBackend — read_csv, run_sql, write_parquet, to_pandas."""

import pathlib

import pandas as pd
import pytest
from src.worker.compute.local import LocalBackend


@pytest.fixture()
def backend() -> LocalBackend:
    return LocalBackend()


@pytest.fixture()
def simple_csv(tmp_path: pathlib.Path) -> str:
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2\n3,4\n")
    return str(p)


def test_read_csv_returns_dataframe(backend: LocalBackend, simple_csv: str) -> None:
    df = backend.read_csv(simple_csv)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_run_sql_basic_select(backend: LocalBackend) -> None:
    df = pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]})
    result = backend.run_sql("SELECT x, y FROM t WHERE x > 1", {"t": df})
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2
    assert list(result["x"]) == [2, 3]


def test_run_sql_rejects_non_dataframe(backend: LocalBackend) -> None:
    with pytest.raises(TypeError, match="must be a pandas DataFrame"):
        backend.run_sql("SELECT 1", {"t": [1, 2, 3]})


def test_write_parquet_roundtrip(backend: LocalBackend, tmp_path: pathlib.Path) -> None:
    df = pd.DataFrame({"col": [10, 20]})
    dest = str(tmp_path / "out.parquet")
    backend.write_parquet(df, dest)
    loaded = pd.read_parquet(dest)
    pd.testing.assert_frame_equal(df, loaded)


def test_write_parquet_rejects_non_dataframe(backend: LocalBackend, tmp_path: pathlib.Path) -> None:
    with pytest.raises(TypeError, match="Expected pandas DataFrame"):
        backend.write_parquet({"not": "a df"}, str(tmp_path / "x.parquet"))


def test_to_pandas_passthrough(backend: LocalBackend) -> None:
    df = pd.DataFrame({"z": [99]})
    result = backend.to_pandas(df)
    assert result is df


def test_to_pandas_rejects_non_dataframe(backend: LocalBackend) -> None:
    with pytest.raises(TypeError, match="Expected pandas DataFrame"):
        backend.to_pandas([1, 2, 3])
