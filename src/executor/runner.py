"""Subprocess-based code runner for the executor microservice.

Executes arbitrary Python code in an isolated subprocess, captures stdout/stderr,
and extracts any pandas DataFrame result written to a known tmp path.
"""

from __future__ import annotations

import json
import os
import pathlib
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

# Prepended when a session_dir is provided and contains existing .parquet files.
# Uses Spark to load Parquet so prior-block Spark DataFrames are available by name.
_DATAFRAME_LOAD_SNIPPET_TEMPLATE = """\
import pathlib as _path_load
for _pf in _path_load.Path({session_dir!r}).glob("*.parquet"):
    try:
        globals()[_pf.stem] = spark.read.parquet(str(_pf))
    except Exception:
        pass
"""

# Appended after _RESULT_CAPTURE_SNIPPET to persist non-private Spark DataFrames to the cache.
_DATAFRAME_SAVE_SNIPPET = """\
import pathlib as _path_save, os as _os_save
_session_dir = _os_save.environ.get("_ROSETTA_SESSION_DIR", "")
if _session_dir:
    _path_save.Path(_session_dir).mkdir(parents=True, exist_ok=True)
    try:
        from pyspark.sql import DataFrame as _SparkDF
    except ImportError:
        _SparkDF = None
    for _vname, _vval in list(globals().items()):
        if _vname.startswith("_") or _SparkDF is None:
            continue
        if isinstance(_vval, _SparkDF):
            try:
                _vval.write.mode("overwrite").parquet(
                    f"{_session_dir}/{_vname}.parquet"
                )
            except Exception:
                pass
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
        # SAS DATE columns (Spark DateType) arrive from toPandas() as a column of
        # datetime.date objects. pandas' to_json(date_format='iso') would still
        # render them as "YYYY-MM-DDT00:00:00.000" — a spurious midnight timestamp
        # the SAS source never declared. Emit bare "YYYY-MM-DD" for any column
        # whose populated cells are pure dates (datetime.date but NOT
        # datetime.datetime); datetime columns (TimestampType) keep their time.
        import datetime as _dt

        for _col in _result.columns:
            _non_null = _result[_col].dropna()
            if len(_non_null) == 0:
                continue
            if all(
                type(_cell) is _dt.date for _cell in _non_null
            ):
                _result[_col] = _result[_col].map(
                    lambda _cell: _cell.isoformat() if isinstance(_cell, _dt.date) else _cell
                )
        # date_format='iso' keeps remaining datetime columns as ISO strings
        # (matching the golden CSV). The pandas default 'epoch' encodes them as
        # millisecond integers, which recon then misreads as numeric SAS days.
        _result.to_json(_result_path, orient='records', date_format='iso')
"""


def normalise_date_columns(df: Any) -> Any:
    """Render pure-date columns as bare ``YYYY-MM-DD`` strings, in place.

    A SAS DATE column (Spark ``DateType``) arrives from ``toPandas()`` as a column
    of :class:`datetime.date` objects. ``pandas.to_json(date_format='iso')`` would
    serialize these as ``YYYY-MM-DDT00:00:00.000`` — a spurious midnight timestamp
    the SAS source never declared. This converts any column whose populated cells
    are *pure* dates (``datetime.date`` but NOT ``datetime.datetime``) to ISO date
    strings, so the delivered output matches the source's declared date format.

    ``datetime.datetime`` is a subclass of ``datetime.date``, so the
    ``type(cell) is datetime.date`` test fires only for true dates; datetime
    (``TimestampType``) columns keep their time component.

    This logic is duplicated inside ``_RESULT_CAPTURE_SNIPPET`` because the
    executor subprocess runs in a fresh namespace and must not import from the
    package — the snippet and this function must be kept in sync.

    Args:
        df: A pandas DataFrame (typed loosely to avoid a hard pandas import).

    Returns:
        The same DataFrame instance, with pure-date columns stringified.
    """
    import datetime as _dt

    for col in df.columns:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        if all(type(cell) is _dt.date for cell in non_null):
            df[col] = df[col].map(
                lambda cell: cell.isoformat() if isinstance(cell, _dt.date) else cell
            )
    return df


# Self-contained copy of the ambiguity-rewrite helper. The executor must NOT
# import from src/worker, so the small parsing/rewrite logic is duplicated here
# (it mirrors src/worker/validation/reconciliation.qualify_ambiguous_column).
def _qualify_ambiguous_column(code: str, stderr: str) -> str | None:
    """Alias-qualify bare ``F.col("<col>")`` refs from a Spark AMBIGUOUS_REFERENCE.

    Parses *stderr* for the ambiguous column name and the first alias-qualified
    candidate (``could be: [`a`.`col`, ...]``), then rewrites every bare
    ``F.col("<col>")`` / ``F.col('<col>')`` in *code* that is not already
    alias-qualified into ``F.col("<alias>.<col>")``.

    Args:
        code: The generated Python source to patch.
        stderr: Subprocess stderr text to parse.

    Returns:
        The patched code, or ``None`` if no AMBIGUOUS_REFERENCE / alias candidate
        could be parsed or nothing was rewritten.
    """
    if "AMBIGUOUS_REFERENCE" not in stderr:
        return None
    ref_match = re.search(r"Reference `(\w+)` is ambiguous", stderr)
    if ref_match is None:
        return None
    col = ref_match.group(1)
    alias_match = re.search(r"could be:\s*\[`(\w+)`\.`" + re.escape(col) + r"`", stderr)
    if alias_match is None:
        return None
    alias = alias_match.group(1)
    pattern = re.compile(r'F\.col\(\s*(["\'])' + re.escape(col) + r"\1\s*\)")
    patched, n_subs = pattern.subn(f'F.col("{alias}.{col}")', code)
    if n_subs == 0:
        return None
    return patched


def run_code(
    code: str,
    timeout: int = 60,
    data_dir: str = "",
    session_dir: str = "",
) -> dict[str, Any]:
    """Execute *code* in a subprocess and return captured outputs.

    The code is written to a temp file, the result-capture snippet is appended,
    and the file is executed with the current Python interpreter.  Any DataFrame
    produced by the code is read back from ``/tmp/rosetta_result.json``.

    When *session_dir* is non-empty, DataFrames from previous block runs are
    loaded from ``.parquet`` files in that directory before the user's code runs,
    and any DataFrames produced by this run are saved back to it.

    Args:
        code: Python source code to execute.
        timeout: Maximum seconds to allow the subprocess to run.
        data_dir: If non-empty, replaces ``/workspace/data/`` prefix in *code* so
            uploaded files are resolved to the correct job-specific directory.
        session_dir: If non-empty, path to a directory used as a per-job DataFrame
            cache.  Prior blocks' outputs are loaded at the start; this block's
            DataFrames are saved at the end.

    Returns:
        Dict with keys:
            stdout (str): Captured standard output.
            stderr (str): Captured standard error.
            result_json (list[dict] | None): DataFrame rows or None.
            result_columns (list[str] | None): Column names or None.
            error (str | None): Exception message if subprocess crashed.
            elapsed_ms (int): Wall-clock time in milliseconds.
    """
    if data_dir:
        code = code.replace("/workspace/data/", data_dir.rstrip("/") + "/")
    prefix = _SPARK_INIT_SNIPPET if re.search(r"\bspark\b", code) else ""

    load_prefix = ""
    if session_dir:
        sdir = pathlib.Path(session_dir)
        if sdir.exists() and any(sdir.glob("*.parquet")):
            load_prefix = _DATAFRAME_LOAD_SNIPPET_TEMPLATE.format(session_dir=session_dir)
        # Always init Spark when session_dir is set — load/save snippets need spark
        if not prefix:
            prefix = _SPARK_INIT_SNIPPET

    capture = "\n" + _RESULT_CAPTURE_SNIPPET + "\n" + _DATAFRAME_SAVE_SNIPPET
    # Order: Spark init → load prior-block DataFrames → user code → capture/save
    augmented = prefix + load_prefix + code + capture

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
        if session_dir:
            env["_ROSETTA_SESSION_DIR"] = session_dir

        # Bounded retry: on AMBIGUOUS_REFERENCE, alias-qualify the offending bare
        # column refs and re-run. Cap at 3 attempts to avoid infinite loops.
        for _attempt in range(3):
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                timeout=timeout,
                text=True,
                env=env,
            )
            stdout = proc.stdout
            # Strip JVM noise that appears before log4j initialises.
            stderr = "\n".join(
                line
                for line in proc.stderr.splitlines()
                if "incubator modules" not in line and line.strip()
            )

            if proc.returncode != 0 and "AMBIGUOUS_REFERENCE" in stderr:
                patched = _qualify_ambiguous_column(augmented, stderr)
                if patched is not None and patched != augmented:
                    augmented = patched
                    pathlib.Path(tmp_path).write_text(augmented)
                    continue
            break

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
