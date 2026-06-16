"""Executor microservice — runs generated Python code in a subprocess sandbox.

Exposes a single POST /execute endpoint that accepts Python source code,
executes it in an isolated subprocess, and returns captured outputs plus
optional reconciliation checks against a reference dataset.
"""

from __future__ import annotations

import logging
import sys

import pandas as pd
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from recon import run_recon  # type: ignore[import-not-found]
from runner import run_code  # type: ignore[import-not-found]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="rosetta-executor", version="0.1.0")


class ExecuteRequest(BaseModel):
    """Request body for POST /execute."""

    code: str
    ref_csv_path: str = ""
    ref_sas7bdat_path: str = ""
    data_dir: str = ""
    session_dir: str = ""
    # Record-level reconciliation config (join_keys, float_tolerance). Kept a
    # plain dict on the wire — the executor cannot import the worker ReconConfig.
    recon_config: dict = {}  # type: ignore[type-arg]


class ExecuteResponse(BaseModel):
    """Response body for POST /execute."""

    stdout: str
    stderr: str
    result_json: list[dict] | None = None  # type: ignore[type-arg]
    result_columns: list[str] | None = None
    result_dtypes: dict[str, str] | None = None
    checks: list[dict] | None = None  # type: ignore[type-arg]
    error: str | None = None
    elapsed_ms: int


@app.post("/execute", response_model=ExecuteResponse)
def execute(request: ExecuteRequest) -> ExecuteResponse:
    """Execute Python code in a subprocess sandbox and return outputs.

    Runs *request.code* via :func:`runner.run_code`, then (if reference data
    paths are provided and a result DataFrame was produced) runs reconciliation
    checks via :func:`recon.run_recon`.

    Args:
        request: Code to run and optional reference dataset paths.

    Returns:
        ExecuteResponse containing stdout, stderr, result rows, recon checks,
        any error message, and wall-clock elapsed time.
    """
    logger.info("Executing code submission (%d chars)", len(request.code))
    run_result = run_code(request.code, data_dir=request.data_dir, session_dir=request.session_dir)

    if run_result["error"]:
        logger.warning("Execution error: %s", run_result["error"])
    else:
        rows = len(run_result["result_json"]) if run_result["result_json"] else 0
        cols = run_result["result_columns"] or []
        logger.info(
            "Execution OK — %d rows, columns=%s, elapsed=%dms",
            rows,
            cols,
            run_result["elapsed_ms"],
        )
    if run_result["stderr"]:
        logger.warning("Execution stderr: %s", run_result["stderr"][:500])

    # SAS: executor/main.py:result_dtypes — derive column dtypes from result rows
    result_dtypes: dict[str, str] | None = None
    if run_result["result_json"] is not None:
        _df_for_dtypes = pd.DataFrame(run_result["result_json"])
        result_dtypes = {str(col): str(dtype) for col, dtype in _df_for_dtypes.dtypes.items()}

    checks: list[dict] | None = None  # type: ignore[type-arg]
    if (request.ref_csv_path or request.ref_sas7bdat_path) and run_result["result_json"]:
        try:
            checks = run_recon(
                run_result["result_json"],
                request.ref_csv_path,
                request.ref_sas7bdat_path,
                request.recon_config,
            )
            statuses = {c["name"]: c["status"] for c in checks}
            logger.info("Recon checks: %s", statuses)
        except Exception as exc:
            logger.warning("Recon failed: %s", exc)
            checks = [{"name": "execution", "status": "fail", "detail": str(exc)}]
    elif request.ref_csv_path or request.ref_sas7bdat_path:
        logger.info("Recon skipped — no result DataFrame produced by the code")

    return ExecuteResponse(
        stdout=run_result["stdout"],
        stderr=run_result["stderr"],
        result_json=run_result["result_json"],
        result_columns=run_result["result_columns"],
        result_dtypes=result_dtypes,
        checks=checks,
        error=run_result["error"],
        elapsed_ms=run_result["elapsed_ms"],
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
