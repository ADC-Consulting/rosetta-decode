"""Subprocess-based code runner for the executor microservice.

Executes arbitrary Python code in an isolated subprocess, captures stdout/stderr,
and extracts any pandas DataFrame result written to a known tmp path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Any

# Injected at the end of every submitted code string.
# Uses an env var _ROSETTA_RESULT_PATH so the path is unique per run.
_RESULT_CAPTURE_SNIPPET = """
import json as _json, os as _os, pandas as _pd
_result_path = _os.environ.get('_ROSETTA_RESULT_PATH', '')
if _result_path:
    _result = None
    for _v in list(globals().values()):
        if isinstance(_v, _pd.DataFrame):
            _result = _v
            break
    if _result is not None:
        _result.to_json(_result_path, orient='records')
"""


def run_code(code: str, timeout: int = 60) -> dict[str, Any]:
    """Execute *code* in a subprocess and return captured outputs.

    The code is written to a temp file, the result-capture snippet is appended,
    and the file is executed with the current Python interpreter.  Any DataFrame
    produced by the code is read back from ``/tmp/rosetta_result.json``.

    Args:
        code: Python source code to execute.
        timeout: Maximum seconds to allow the subprocess to run.

    Returns:
        Dict with keys:
            stdout (str): Captured standard output.
            stderr (str): Captured standard error.
            result_json (list[dict] | None): DataFrame rows or None.
            result_columns (list[str] | None): Column names or None.
            error (str | None): Exception message if subprocess crashed.
            elapsed_ms (int): Wall-clock time in milliseconds.
    """
    augmented = code + "\n" + _RESULT_CAPTURE_SNIPPET

    result_json: list[dict[str, Any]] | None = None
    result_columns: list[str] | None = None
    error: str | None = None
    stdout = ""
    stderr = ""

    start = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
            tmp.write(augmented)
            tmp_path = tmp.name

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as result_tmp:
            result_path = result_tmp.name

        env = os.environ.copy()
        env["_ROSETTA_RESULT_PATH"] = result_path

        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            timeout=timeout,
            text=True,
            env=env,
        )
        stdout = proc.stdout
        stderr = proc.stderr

        # Read captured DataFrame result if it was written
        try:
            with open(result_path) as fh:
                raw = json.load(fh)
            if isinstance(raw, list) and raw:
                result_json = raw
                result_columns = list(raw[0].keys())
            elif isinstance(raw, list):
                result_json = raw
                result_columns = []
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        if proc.returncode != 0 and not error:
            error = stderr or f"Process exited with code {proc.returncode}"

    except subprocess.TimeoutExpired:
        error = f"Execution timed out after {timeout}s"
    except Exception as exc:
        error = str(exc)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "stdout": stdout,
        "stderr": stderr,
        "result_json": result_json,
        "result_columns": result_columns,
        "error": error,
        "elapsed_ms": elapsed_ms,
    }
