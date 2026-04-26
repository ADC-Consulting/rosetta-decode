"""Subprocess-based code runner for the executor microservice.

Executes arbitrary Python code in an isolated subprocess, captures stdout/stderr,
and extracts any pandas DataFrame result written to a known tmp path.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

# Prepended when the submitted code references the `spark` name.
_SPARK_INIT_SNIPPET = """\
import logging as _logging, os as _os, tempfile as _tempfile, pathlib as _pathlib
_logging.getLogger("py4j").setLevel(_logging.ERROR)
_logging.getLogger("py4j.clientserver").setLevel(_logging.ERROR)
# Write a log4j2 properties file so JVM Spark/Hadoop warnings are suppressed
_log4j2_props = _pathlib.Path(_tempfile.gettempdir()) / "rosetta_log4j2.properties"
if not _log4j2_props.exists():
    _log4j2_props.write_text(
        "rootLogger.level=ERROR\\n"
        "rootLogger.appenderRef.stdout.ref=ConsoleAppender\\n"
        "appender.console.type=Console\\n"
        "appender.console.name=ConsoleAppender\\n"
        "appender.console.layout.type=PatternLayout\\n"
        "appender.console.layout.pattern=%d{HH:mm:ss} %-5level %logger{1} - %msg%n\\n"
        "logger.hadoop.name=org.apache.hadoop\\n"
        "logger.hadoop.level=ERROR\\n"
        "logger.spark.name=org.apache.spark\\n"
        "logger.spark.level=ERROR\\n"
    )
_jvm_opts = f"-Dlog4j2.configurationFile={_log4j2_props}"
from pyspark.sql import SparkSession as _SparkSession
spark = (
    _SparkSession.builder
    .master("local[*]")
    .appName("rosetta-executor")
    .config("spark.ui.enabled", "false")
    .config("spark.sql.shuffle.partitions", "4")
    .config("spark.driver.extraJavaOptions", _jvm_opts)
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")
"""

# Injected at the end of every submitted code string.
# Captures the `result` variable first, then falls back to any DataFrame in globals.
_RESULT_CAPTURE_SNIPPET = """
import json as _json, os as _os, pandas as _pd
_result_path = _os.environ.get('_ROSETTA_RESULT_PATH', '')
if _result_path:
    _result = None
    try:
        from pyspark.sql import DataFrame as _SparkDF
        _has_spark = True
    except ImportError:
        _has_spark = False
    _candidate = globals().get('result')
    if _candidate is not None:
        if isinstance(_candidate, _pd.DataFrame):
            _result = _candidate
        elif _has_spark and isinstance(_candidate, _SparkDF):
            _result = _candidate.toPandas()
    if _result is None:
        for _v in list(globals().values()):
            if isinstance(_v, _pd.DataFrame):
                _result = _v
                break
            if _has_spark and isinstance(_v, _SparkDF):
                _result = _v.toPandas()
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
    prefix = _SPARK_INIT_SNIPPET if re.search(r"\bspark\b", code) else ""
    augmented = prefix + code + "\n" + _RESULT_CAPTURE_SNIPPET

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
