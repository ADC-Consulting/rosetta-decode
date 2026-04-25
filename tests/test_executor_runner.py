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
