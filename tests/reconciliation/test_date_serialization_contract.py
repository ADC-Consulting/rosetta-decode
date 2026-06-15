"""Serialization-contract tests for SAS-date columns (F15/F61).

These pin the executor behaviour that delivers a SAS DATE column as a bare
``YYYY-MM-DD`` value rather than the spurious midnight timestamp
``YYYY-MM-DDT00:00:00.000`` the F15 row_hash_diff surfaced for ``aestdtc``.

Root cause: a Spark ``DateType`` column arrives from ``toPandas()`` as a column
of ``datetime.date`` objects, but ``pandas.to_json(date_format='iso')`` still
renders those as ``...T00:00:00.000``. ``runner.normalise_date_columns`` rewrites
pure-date columns to ISO date strings *before* ``to_json`` so the delivered output
matches the source's declared date format. Datetime (``TimestampType``) columns —
which legitimately carry a time component — are left untouched.
"""

from __future__ import annotations

import datetime

import pandas as pd
import pytest
from src.executor.runner import normalise_date_columns


def _serialize_like_executor(df: pd.DataFrame) -> str:
    """Mirror the executor's serialization: normalise dates, then ISO to_json."""
    normalise_date_columns(df)
    return df.to_json(orient="records", date_format="iso")


@pytest.mark.reconciliation
def test_pure_date_column_serializes_without_time_component() -> None:
    """A DateType column (datetime.date cells) serializes as bare YYYY-MM-DD."""
    df = pd.DataFrame({"aestdtc": [datetime.date(2025, 6, 10)]})

    payload = _serialize_like_executor(df)

    assert '"aestdtc":"2025-06-10"' in payload
    # The spurious midnight timestamp must NOT appear for a bare-date column.
    assert "T00:00:00" not in payload


@pytest.mark.reconciliation
def test_datetime_column_keeps_its_time_component() -> None:
    """A datetime column (TimestampType) retains its real time-of-day."""
    df = pd.DataFrame({"aestdtm": [datetime.datetime(2025, 6, 10, 13, 30, 0)]})

    payload = _serialize_like_executor(df)

    assert "2025-06-10T13:30:00" in payload


@pytest.mark.reconciliation
def test_mixed_frame_only_dates_lose_time() -> None:
    """Date column goes bare; datetime and string columns are unaffected."""
    df = pd.DataFrame(
        {
            "aestdtc": [datetime.date(2025, 6, 10), None],
            "aestdtm": [datetime.datetime(2025, 6, 10, 9, 15, 0), None],
            "subjid": ["001", None],
        }
    )

    payload = _serialize_like_executor(df)

    assert '"aestdtc":"2025-06-10"' in payload  # bare date
    assert "2025-06-10T09:15:00" in payload  # datetime keeps time
    assert '"subjid":"001"' in payload  # string untouched


@pytest.mark.reconciliation
def test_all_null_date_column_is_left_alone() -> None:
    """A column with no populated cells is skipped (no false date classification)."""
    df = pd.DataFrame({"aestdtc": [None, None]})

    # Must not raise and must not invent a value.
    normalise_date_columns(df)
    assert df["aestdtc"].isna().all()
