"""Unit test for the AMBIGUOUS_REFERENCE self-heal branch of _safe_exec.

Simulates the Spark code-rewrite loop without a SparkSession: the executed
code raises an ``AMBIGUOUS_REFERENCE`` exception while it still contains the
bare ``F.col("usubjid")`` form, and stops raising once
``qualify_ambiguous_column`` rewrites it to the alias-qualified
``F.col("a.usubjid")``. This exercises the in-place code patching path
(lines ~225-230 / 240-259 are guarded behind it).
"""

from __future__ import annotations

from typing import Any

import pytest
from src.worker.validation.reconciliation import _safe_exec

pytestmark = pytest.mark.reconciliation

_AMBIGUOUS_MSG = (
    "[AMBIGUOUS_REFERENCE] Reference `usubjid` is ambiguous, could be: [`a`.`usubjid`, `usubjid`]."
)

# Code that raises while the bare ref is present, but succeeds once the
# alias-qualified form 'a.usubjid' appears (after qualify_ambiguous_column).
_CODE = (
    'if F.col("a.usubjid"):\n'
    "    result['ok'] = True\n"
    "else:\n"
    f'    raise Exception("{_AMBIGUOUS_MSG}")\n'
)


def test_safe_exec_self_heals_ambiguous_reference() -> None:
    """_safe_exec rewrites the bare ref, then the patched code runs cleanly."""
    captured: dict[str, Any] = {}

    class _FakeColExpr:
        """Truthy only when built from the alias-qualified name."""

        def __init__(self, name: str) -> None:
            self._qualified = "." in name

        def __bool__(self) -> bool:
            return self._qualified

    class _FakeF:
        @staticmethod
        def col(name: str) -> _FakeColExpr:
            return _FakeColExpr(name)

    ns: dict[str, Any] = {"F": _FakeF, "result": captured}

    _safe_exec(_CODE, ns)

    assert captured.get("ok") is True
