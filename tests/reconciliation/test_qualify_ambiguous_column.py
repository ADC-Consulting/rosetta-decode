"""Unit tests for qualify_ambiguous_column in the reconciliation in-process runner."""

from __future__ import annotations

import pytest
from src.worker.validation.reconciliation import qualify_ambiguous_column

pytestmark = pytest.mark.reconciliation

_AMBIGUOUS_ERR = (
    "[AMBIGUOUS_REFERENCE] Reference `usubjid` is ambiguous, could be: [`a`.`usubjid`, `usubjid`]."
)


def test_rewrites_bare_double_quoted_ref() -> None:
    """A bare F.col(\"usubjid\") is alias-qualified with the first candidate."""
    code = 'df = df.withColumn("flag", F.when(F.col("usubjid").isNotNull(), 1))'
    patched = qualify_ambiguous_column(code, _AMBIGUOUS_ERR)
    assert patched is not None
    assert 'F.col("a.usubjid")' in patched
    assert 'F.col("usubjid")' not in patched


def test_rewrites_bare_single_quoted_ref() -> None:
    """Single-quoted bare refs are also rewritten."""
    code = "df = df.filter(F.col('usubjid') > 0)"
    patched = qualify_ambiguous_column(code, _AMBIGUOUS_ERR)
    assert patched is not None
    assert 'F.col("a.usubjid")' in patched


def test_already_qualified_refs_untouched() -> None:
    """Refs already carrying an alias dot are not matched → no-op (None)."""
    code = 'df = df.select(F.col("a.usubjid"), F.col("b.age"))'
    assert qualify_ambiguous_column(code, _AMBIGUOUS_ERR) is None


def test_no_ambiguous_error_returns_none() -> None:
    """An error string without AMBIGUOUS_REFERENCE yields None."""
    code = 'df = df.select(F.col("usubjid"))'
    assert qualify_ambiguous_column(code, "UNRESOLVED_COLUMN `usubjid`") is None


def test_unparseable_candidate_returns_none() -> None:
    """AMBIGUOUS_REFERENCE without a parseable alias candidate yields None."""
    code = 'df = df.select(F.col("usubjid"))'
    err = "[AMBIGUOUS_REFERENCE] Reference `usubjid` is ambiguous, could be: [unknown]."
    assert qualify_ambiguous_column(code, err) is None
