"""Unit tests for src/executor/runner.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Insert the executor directory on sys.path so we can import runner directly
# (executor is not installed as a package in the main venv).
# ---------------------------------------------------------------------------
_EXECUTOR_DIR = str(Path(__file__).parent.parent / "src" / "executor")
if _EXECUTOR_DIR not in sys.path:
    sys.path.insert(0, _EXECUTOR_DIR)

import runner  # type: ignore[import-not-found]  # noqa: E402


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_run_code_captures_stdout() -> None:
    """stdout from executed code is returned in the result dict."""
    fake_proc = _FakeProc(stdout="hello\n", returncode=0)
    with (
        patch("runner.subprocess.run", return_value=fake_proc),
        patch("runner.open", side_effect=FileNotFoundError),
    ):
        result = runner.run_code("print('hello')")
    assert result["stdout"] == "hello\n"
    assert result["error"] is None


def test_run_code_nonzero_exit_sets_error() -> None:
    """Non-zero return code sets the error field."""
    fake_proc = _FakeProc(stdout="", stderr="SyntaxError: …", returncode=1)
    with (
        patch("runner.subprocess.run", return_value=fake_proc),
        patch("runner.open", side_effect=FileNotFoundError),
    ):
        result = runner.run_code("x = (")
    assert result["error"] is not None


def test_run_code_timeout_sets_error() -> None:
    """subprocess.TimeoutExpired is caught and sets the error field."""
    import subprocess

    with patch("runner.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
        result = runner.run_code("import time; time.sleep(999)", timeout=1)
    assert "timed out" in (result["error"] or "").lower()


def test_run_code_reads_result_json(tmp_path: Path) -> None:
    """Result JSON written by the capture snippet is parsed and returned."""
    import json
    import tempfile
    from unittest.mock import MagicMock

    result_file = tmp_path / "rosetta_result.json"
    data = [{"col_a": 1, "col_b": 2}]
    result_file.write_text(json.dumps(data))

    # NamedTemporaryFile is called twice: once for the code file, once for the result path.
    # We need the second call to produce our known result_file path.
    real_ntf = tempfile.NamedTemporaryFile
    call_count = [0]

    def _fake_ntf(**kwargs):  # type: ignore[no-untyped-def]
        call_count[0] += 1
        if call_count[0] == 2:
            m = MagicMock()
            m.__enter__ = lambda s: m
            m.__exit__ = MagicMock(return_value=False)
            m.name = str(result_file)
            return m
        return real_ntf(**kwargs)

    fake_proc = _FakeProc(returncode=0)
    with (
        patch("runner.subprocess.run", return_value=fake_proc),
        patch("runner.tempfile.NamedTemporaryFile", side_effect=_fake_ntf),
    ):
        code = "import pandas as pd; df = pd.DataFrame({'col_a':[1],'col_b':[2]})"
        result = runner.run_code(code)
    assert result["result_json"] == data
    assert result["result_columns"] == ["col_a", "col_b"]


def test_run_code_elapsed_ms_is_non_negative() -> None:
    """elapsed_ms must be a non-negative integer."""
    fake_proc = _FakeProc(returncode=0)
    with (
        patch("runner.subprocess.run", return_value=fake_proc),
        patch("runner.open", side_effect=FileNotFoundError),
    ):
        result = runner.run_code("")
    assert isinstance(result["elapsed_ms"], int)
    assert result["elapsed_ms"] >= 0


def test_run_code_empty_result_json_list(tmp_path: Path) -> None:
    """An empty JSON array written by the capture snippet results in empty lists."""
    import json
    import tempfile
    from unittest.mock import MagicMock

    result_file = tmp_path / "rosetta_result_empty.json"
    result_file.write_text(json.dumps([]))

    real_ntf = tempfile.NamedTemporaryFile
    call_count = [0]

    def _fake_ntf(**kwargs):  # type: ignore[no-untyped-def]
        call_count[0] += 1
        if call_count[0] == 2:
            m = MagicMock()
            m.__enter__ = lambda s: m
            m.__exit__ = MagicMock(return_value=False)
            m.name = str(result_file)
            return m
        return real_ntf(**kwargs)

    fake_proc = _FakeProc(returncode=0)
    with (
        patch("runner.subprocess.run", return_value=fake_proc),
        patch("runner.tempfile.NamedTemporaryFile", side_effect=_fake_ntf),
    ):
        result = runner.run_code("pass")

    assert result["result_json"] == []
    assert result["result_columns"] == []


def test_run_code_generic_exception_sets_error() -> None:
    """A generic Exception during subprocess.run is caught and sets the error field."""
    with patch("runner.subprocess.run", side_effect=OSError("disk full")):
        result = runner.run_code("x = 1")
    assert result["error"] == "disk full"
    assert result["stdout"] == ""


# ---------------------------------------------------------------------------
# AMBIGUOUS_REFERENCE auto-patch — helper + bounded subprocess retry
# ---------------------------------------------------------------------------

_AMBIGUOUS_STDERR = (
    "pyspark.errors.exceptions.captured.AnalysisException: "
    "[AMBIGUOUS_REFERENCE] Reference `usubjid` is ambiguous, "
    "could be: [`a`.`usubjid`, `usubjid`]."
)


def test_qualify_ambiguous_column_rewrites_bare_ref() -> None:
    """A bare F.col(\"usubjid\") is rewritten to the first alias candidate."""
    code = 'df = df.withColumn("flag", F.when(F.col("usubjid").isNotNull(), 1))'
    patched = runner._qualify_ambiguous_column(code, _AMBIGUOUS_STDERR)
    assert patched is not None
    assert 'F.col("a.usubjid")' in patched
    assert 'F.col("usubjid")' not in patched


def test_qualify_ambiguous_column_leaves_qualified_refs() -> None:
    """Already alias-qualified refs are untouched (contain a dot)."""
    code = 'df = df.select(F.col("a.usubjid"), F.col("b.age"))'
    patched = runner._qualify_ambiguous_column(code, _AMBIGUOUS_STDERR)
    # Nothing bare to rewrite → None (no-op).
    assert patched is None


def test_qualify_ambiguous_column_single_quotes() -> None:
    """Single-quoted bare refs are also rewritten."""
    code = "df = df.filter(F.col('usubjid') > 0)"
    patched = runner._qualify_ambiguous_column(code, _AMBIGUOUS_STDERR)
    assert patched is not None
    assert 'F.col("a.usubjid")' in patched


def test_qualify_ambiguous_column_no_error_returns_none() -> None:
    """stderr without AMBIGUOUS_REFERENCE yields None."""
    code = 'df = df.select(F.col("usubjid"))'
    assert runner._qualify_ambiguous_column(code, "some other error") is None


def test_run_code_retries_on_ambiguous_reference() -> None:
    """run_code re-runs after patching the code on AMBIGUOUS_REFERENCE."""
    fail = _FakeProc(stderr=_AMBIGUOUS_STDERR, returncode=1)
    ok = _FakeProc(stdout="done\n", returncode=0)
    calls = {"n": 0}

    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return fail if calls["n"] == 1 else ok

    with (
        patch("runner.subprocess.run", side_effect=_fake_run),
        patch("runner.open", side_effect=FileNotFoundError),
    ):
        result = runner.run_code('df = df.select(F.col("usubjid"))')

    assert calls["n"] == 2
    assert result["error"] is None
    assert result["stdout"] == "done\n"


def test_run_code_caps_ambiguous_retries_at_three() -> None:
    """run_code never exceeds 3 attempts when AMBIGUOUS_REFERENCE persists.

    Each attempt reports a fresh ambiguous column so the rewrite always finds a
    bare ref to patch; the loop must still terminate at the 3-attempt cap and
    surface the error rather than looping forever.
    """

    def _err_for(col: str) -> str:
        return (
            f"[AMBIGUOUS_REFERENCE] Reference `{col}` is ambiguous, "
            f"could be: [`a`.`{col}`, `{col}`]."
        )

    cols = ["usubjid", "studyid", "siteid", "subjid"]
    calls = {"n": 0}

    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        col = cols[calls["n"]]
        calls["n"] += 1
        return _FakeProc(stderr=_err_for(col), returncode=1)

    code = 'df = df.select(F.col("usubjid"), F.col("studyid"), F.col("siteid"), F.col("subjid"))'
    with (
        patch("runner.subprocess.run", side_effect=_fake_run),
        patch("runner.open", side_effect=FileNotFoundError),
    ):
        result = runner.run_code(code)

    # Bounded at 3 even though a 4th distinct column remains patchable.
    assert calls["n"] == 3
    assert result["error"] is not None
