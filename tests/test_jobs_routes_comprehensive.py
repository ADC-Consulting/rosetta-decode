"""Comprehensive coverage tests for src/backend/api/routes/jobs.py — fills 66 missing lines."""

import pathlib
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.backend.api.routes.jobs import (
    _classify_attachment,
    accept_job,
    download_attachment,
    download_job,
    get_job,
    get_job_attachments,
    get_job_audit,
    get_job_doc,
    get_job_lineage,
    get_job_plan,
    get_job_sources,
    list_jobs,
    patch_job_plan,
    save_block_python,
    update_python_code,
)
from src.backend.db.models import Job


def _make_job(
    job_id: str | None = None,
    status: str = "proposed",
    files: dict[str, object] | None = None,
    **kwargs: object,
) -> Job:
    """Factory for test Job instances."""
    if job_id is None:
        job_id = str(uuid.uuid4())
    elif not isinstance(job_id, str):
        job_id = str(job_id)
    if files is None:
        files = {"test.sas": "data step;"}
    _now = datetime.now(UTC)
    defaults: dict[str, object] = dict(
        input_hash="abc123",
        trigger="agent",
        skip_llm=False,
        created_at=_now,
        updated_at=_now,
    )
    defaults.update(kwargs)
    job = Job(
        id=job_id,
        status=status,
        files=files,
        **defaults,
    )
    return job


# ─── _classify_attachment ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ext,expected",
    [
        (".log", "log"),
        (".lst", "log"),
        (".csv", "output"),
        (".xlsx", "output"),
        (".xls", "output"),
        (".sas7bdat", "output"),
        (".txt", "other"),
        (".pdf", "other"),
    ],
)
def test_classify_attachment(ext: str, expected: str) -> None:
    """Test _classify_attachment for various extensions."""
    assert _classify_attachment(ext) == expected


# ─── list_jobs ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_jobs_no_filter() -> None:
    """Test list_jobs returns all jobs ordered by created_at desc."""
    session = AsyncMock()
    job1 = _make_job(status="proposed")
    job2 = _make_job(status="done")
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [job2, job1]
    session.execute.return_value = result_mock

    response = await list_jobs(None, session)

    assert len(response.jobs) == 2
    assert response.jobs[0].status == "done"
    assert response.jobs[1].status == "proposed"


@pytest.mark.asyncio
async def test_list_jobs_with_single_status_filter() -> None:
    """Test list_jobs with single status filter."""
    session = AsyncMock()
    job1 = _make_job(status="done")
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [job1]
    session.execute.return_value = result_mock

    response = await list_jobs("done", session)

    assert len(response.jobs) == 1
    assert response.jobs[0].status == "done"


@pytest.mark.asyncio
async def test_list_jobs_with_multiple_status_filters() -> None:
    """Test list_jobs with comma-separated status filters."""
    session = AsyncMock()
    job1 = _make_job(status="proposed")
    job2 = _make_job(status="done")
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [job1, job2]
    session.execute.return_value = result_mock

    response = await list_jobs("proposed,done", session)

    assert len(response.jobs) == 2


@pytest.mark.asyncio
async def test_list_jobs_with_empty_status_filter() -> None:
    """Test list_jobs with empty status string (should be ignored)."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock

    response = await list_jobs("", session)

    # Empty status should not add WHERE clause
    assert response.jobs == []


@pytest.mark.asyncio
async def test_list_jobs_with_whitespace_status_filter() -> None:
    """Test list_jobs with whitespace-only status filter."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock

    response = await list_jobs("  ,  , ", session)

    assert response.jobs == []


# ─── get_job ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_success() -> None:
    """Test get_job returns job successfully."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="done", python_code="x = 1")
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job(job_id, session)

    assert response.job_id == job_id
    assert response.status == "done"
    assert response.python_code == "x = 1"


@pytest.mark.asyncio
async def test_get_job_not_found() -> None:
    """Test get_job raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_job(job_id, session)

    assert exc_info.value.status_code == 404


# ─── get_job_sources ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_sources_excludes_sentinel_keys() -> None:
    """Test get_job_sources excludes __ref_ and __ prefixed keys."""
    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        files={
            "test.sas": "data step;",
            "__ref_csv_data.csv__": "/tmp/data.csv",
            "__internal__": "value",
        },
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_sources(job_id, session)

    assert "test.sas" in response.sources
    assert "__ref_csv_data.csv__" not in response.sources
    assert "__internal__" not in response.sources


@pytest.mark.asyncio
async def test_get_job_sources_not_found() -> None:
    """Test get_job_sources raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_job_sources(job_id, session)

    assert exc_info.value.status_code == 404


# ─── get_job_attachments ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_attachments_empty() -> None:
    """Test get_job_attachments with no attachment sentinel keys."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), files={"test.sas": "data;"})
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_attachments(job_id, session)

    assert response.attachments == []


@pytest.mark.asyncio
async def test_get_attachments_skips_malformed_sentinel() -> None:
    """Test get_job_attachments skips malformed sentinel keys."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), files={"__ref_noseparator__": "/tmp/file"})
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_attachments(job_id, session)

    assert response.attachments == []


@pytest.mark.asyncio
async def test_get_attachments_skips_missing_disk_file(tmp_path: object) -> None:
    """Test get_job_attachments skips missing disk files."""
    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        files={"__ref_log_missing.log__": "/tmp/does-not-exist-12345.log"},
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_attachments(job_id, session)

    assert response.attachments == []


@pytest.mark.asyncio
async def test_get_attachments_valid_file(tmp_path: pathlib.Path) -> None:
    """Test get_job_attachments returns valid attachment."""
    job_id = uuid.uuid4()
    disk_path = str(tmp_path / "output.log")
    with open(disk_path, "w") as f:
        f.write("log content")

    job = _make_job(
        str(job_id),
        files={"__ref_log_output.log__": disk_path},
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_attachments(job_id, session)

    assert len(response.attachments) == 1
    assert response.attachments[0].filename == "output.log"
    assert response.attachments[0].category == "log"


@pytest.mark.asyncio
async def test_get_attachments_not_found() -> None:
    """Test get_job_attachments raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_job_attachments(job_id, session)

    assert exc_info.value.status_code == 404


# ─── download_attachment ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_attachment_job_not_found() -> None:
    """Test download_attachment raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await download_attachment(job_id, "some_key", session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_download_attachment_key_not_found() -> None:
    """Test download_attachment raises 404 when key doesn't exist."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), files={"other_key": "/tmp/file"})
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await download_attachment(job_id, "missing_key", session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_download_attachment_disk_file_missing() -> None:
    """Test download_attachment raises 404 when disk file is missing."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), files={"__ref_log_missing.log__": "/tmp/does-not-exist.log"})
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await download_attachment(job_id, "__ref_log_missing.log__", session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_download_attachment_success(tmp_path: pathlib.Path) -> None:
    """Test download_attachment returns FileResponse successfully."""
    job_id = uuid.uuid4()
    disk_path = str(tmp_path / "output.csv")
    with open(disk_path, "w") as f:
        f.write("col1,col2\n1,2")

    job = _make_job(str(job_id), files={"__ref_csv_output.csv__": disk_path})
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await download_attachment(job_id, "__ref_csv_output.csv__", session)

    assert response.path == disk_path
    assert "text/csv" in (response.media_type or "")


# ─── get_job_audit ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_audit_success() -> None:
    """Test get_job_audit returns audit record."""
    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        input_hash="hash123",
        llm_model="claude-3",
        report={"checks": [{"status": "pass"}]},
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_audit(job_id, session)

    assert response.job_id == job_id
    assert response.input_hash == "hash123"
    assert response.llm_model == "claude-3"


@pytest.mark.asyncio
async def test_get_job_audit_not_found() -> None:
    """Test get_job_audit raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_job_audit(job_id, session)

    assert exc_info.value.status_code == 404


# ─── download_job ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_job_not_found() -> None:
    """Test download_job raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await download_job(job_id, session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_download_job_not_complete() -> None:
    """Test download_job raises 409 when job is not complete."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="queued")
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await download_job(job_id, session)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_download_job_success() -> None:
    """Test download_job returns StreamingResponse with zip."""
    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        status="done",
        python_code="x = 1",
        report={"checks": [{"status": "pass"}]},
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await download_job(job_id, session)

    assert response.media_type == "application/zip"


@pytest.mark.parametrize("status", ["proposed", "accepted", "done"])
@pytest.mark.asyncio
async def test_download_job_success_all_complete_statuses(status: str) -> None:
    """Test download_job works for all complete statuses."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status=status)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await download_job(job_id, session)

    assert response.media_type == "application/zip"


# ─── get_job_lineage ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_lineage_not_computed() -> None:
    """Test get_job_lineage returns 202 when lineage not computed."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), lineage=None)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_lineage(job_id, session)

    # Should return JSONResponse with 202
    from starlette.responses import JSONResponse as _JSONResponse

    assert isinstance(response, _JSONResponse) and response.status_code == 202


@pytest.mark.asyncio
async def test_get_job_lineage_available() -> None:
    """Test get_job_lineage returns data when available."""
    job_id = uuid.uuid4()
    lineage_data = {
        "nodes": [{"id": "n1", "label": "Block 1"}],
        "edges": [{"source": "n1", "target": "n2", "dataset": "ds1"}],
        "column_flows": [],
    }
    job = _make_job(str(job_id), lineage=lineage_data)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_lineage(job_id, session)

    from src.backend.api.schemas import JobLineageResponse

    assert isinstance(response, JobLineageResponse)
    assert response.job_id == job_id
    assert len(response.nodes) == 1


@pytest.mark.asyncio
async def test_get_job_lineage_not_found() -> None:
    """Test get_job_lineage raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_job_lineage(job_id, session)

    assert exc_info.value.status_code == 404


# ─── get_job_doc ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_doc_no_doc() -> None:
    """Test get_job_doc when no doc is available."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), doc=None, report={})
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_doc(job_id, session)

    assert response.job_id == job_id
    assert response.doc is None


@pytest.mark.asyncio
async def test_get_job_doc_with_technical_and_nontechnical() -> None:
    """Test get_job_doc with both doc and non_technical_doc."""
    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        doc="Technical doc",
        report={"non_technical_doc": "Non-tech doc"},
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_doc(job_id, session)

    assert response.doc == "Technical doc"
    assert response.non_technical_doc == "Non-tech doc"


@pytest.mark.asyncio
async def test_get_job_doc_not_found() -> None:
    """Test get_job_doc raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_job_doc(job_id, session)

    assert exc_info.value.status_code == 404


# ─── get_job_plan ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_plan_not_complete() -> None:
    """Test get_job_plan returns 202 when job not complete."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="running")
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_plan(job_id, session)

    from starlette.responses import JSONResponse as _JSONResponse

    assert isinstance(response, _JSONResponse) and response.status_code == 202


@pytest.mark.asyncio
async def test_get_job_plan_no_plan_generated() -> None:
    """Test get_job_plan returns 202 when plan failed to generate."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="done", migration_plan=None)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_plan(job_id, session)

    from starlette.responses import JSONResponse as _JSONResponse

    assert isinstance(response, _JSONResponse) and response.status_code == 202


@pytest.mark.asyncio
async def test_get_job_plan_available() -> None:
    """Test get_job_plan returns plan when available."""
    job_id = uuid.uuid4()
    plan_data = {
        "summary": "Plan summary",
        "overall_risk": "low",
        "block_plans": [],
        "recommended_review_blocks": [],
        "cross_file_dependencies": [],
    }
    job = _make_job(str(job_id), status="done", migration_plan=plan_data)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await get_job_plan(job_id, session)

    from src.backend.api.schemas import JobPlanResponse

    assert isinstance(response, JobPlanResponse)
    assert response.summary == "Plan summary"


@pytest.mark.asyncio
async def test_get_job_plan_not_found() -> None:
    """Test get_job_plan raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_job_plan(job_id, session)

    assert exc_info.value.status_code == 404


# ─── accept_job ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_job_success() -> None:
    """Test accept_job successfully accepts a job."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="proposed")
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    from src.backend.api.schemas import AcceptJobRequest

    request = AcceptJobRequest(notes="Looks good")

    # Mock: 1st = select (scalar_one_or_none), 2nd = update, 3rd = select (scalar_one)
    updated_job = _make_job(str(job_id), status="accepted")
    update_result = MagicMock()
    result_mock2 = MagicMock()
    result_mock2.scalar_one.return_value = updated_job
    session.execute.side_effect = [result_mock, update_result, result_mock2]

    response = await accept_job(job_id, request, session)

    assert response.status == "accepted"


@pytest.mark.asyncio
async def test_accept_job_not_found() -> None:
    """Test accept_job raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        from src.backend.api.schemas import AcceptJobRequest

        await accept_job(job_id, AcceptJobRequest(), session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_accept_job_invalid_status() -> None:
    """Test accept_job raises 409 when job is in invalid status."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="queued")
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    from fastapi import HTTPException
    from src.backend.api.schemas import AcceptJobRequest

    with pytest.raises(HTTPException) as exc_info:
        await accept_job(job_id, AcceptJobRequest(), session)

    assert exc_info.value.status_code == 409


# ─── patch_job_plan ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_job_plan_not_found() -> None:
    """Test patch_job_plan raises 404 when job doesn't exist."""
    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    from fastapi import HTTPException
    from src.backend.api.schemas import PatchPlanRequest

    with pytest.raises(HTTPException) as exc_info:
        await patch_job_plan(job_id, PatchPlanRequest(block_overrides=[]), session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_patch_job_plan_invalid_status() -> None:
    """Test patch_job_plan raises 409 when job is in invalid status."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="done")
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    from fastapi import HTTPException
    from src.backend.api.schemas import PatchPlanRequest

    with pytest.raises(HTTPException) as exc_info:
        await patch_job_plan(job_id, PatchPlanRequest(block_overrides=[]), session)

    assert exc_info.value.status_code == 409


# ─── refine_job (POST /jobs/{id}/refine) — 409 when accepted ─────────────────


@pytest.mark.asyncio
async def test_refine_job_409_when_accepted() -> None:
    """POST /jobs/{id}/refine returns 409 when job has been accepted."""
    from datetime import UTC, datetime

    from fastapi import HTTPException
    from src.backend.api.routes.jobs import refine_job
    from src.backend.api.schemas import RefineRequest

    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="accepted", accepted_at=datetime.now(UTC))
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    with pytest.raises(HTTPException) as exc_info:
        await refine_job(job_id, RefineRequest(hint="try again"), session)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_refine_job_404_when_missing() -> None:
    """POST /jobs/{id}/refine returns 404 when job not found."""
    from fastapi import HTTPException
    from src.backend.api.routes.jobs import refine_job
    from src.backend.api.schemas import RefineRequest

    job_id = uuid.uuid4()
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    with pytest.raises(HTTPException) as exc_info:
        await refine_job(job_id, RefineRequest(hint="try again"), session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_refine_job_creates_child_job() -> None:
    """POST /jobs/{id}/refine creates a child job with refine_context."""
    import json as _json

    from src.backend.api.routes.jobs import refine_job
    from src.backend.api.schemas import RefineRequest

    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        status="proposed",
        python_code="df = pd.read_csv('in.csv')",
        accepted_at=None,
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    response = await refine_job(job_id, RefineRequest(hint="fix the join"), session)

    assert session.add.called
    assert session.commit.called
    new_job_arg = session.add.call_args[0][0]
    assert new_job_arg.trigger == "human-refine"
    ctx = _json.loads(new_job_arg.files["__refine_context__"])
    assert ctx["hint"] == "fix the join"
    assert response.job_id is not None


# ─── F68 post-acceptance immutability ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_job_stamps_accepted_by_anonymous() -> None:
    """First accept writes accepted_by='anonymous' alongside accepted_at."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="proposed", accepted_at=None)
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    _now = datetime.now(UTC)
    updated_job = _make_job(
        str(job_id), status="accepted", accepted_at=_now, accepted_by="anonymous"
    )
    update_result = MagicMock()
    result_mock2 = MagicMock()
    result_mock2.scalar_one.return_value = updated_job
    session.execute.side_effect = [result_mock, update_result, result_mock2]

    from src.backend.api.schemas import AcceptJobRequest

    response = await accept_job(job_id, AcceptJobRequest(), session)

    assert response.status == "accepted"
    assert response.accepted_by == "anonymous"
    assert response.accepted_at is not None


@pytest.mark.asyncio
async def test_accept_job_already_accepted_returns_409() -> None:
    """Second accept on an already-accepted job must return 409."""
    from fastapi import HTTPException
    from src.backend.api.schemas import AcceptJobRequest

    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        status="accepted",
        accepted_at=datetime.now(UTC),
        accepted_by="anonymous",
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    with pytest.raises(HTTPException) as exc_info:
        await accept_job(job_id, AcceptJobRequest(), session)

    assert exc_info.value.status_code == 409
    assert "already been accepted" in exc_info.value.detail


@pytest.mark.asyncio
async def test_update_python_code_on_accepted_job_returns_409() -> None:
    """PUT /python_code on an accepted job must return 409."""
    from fastapi import HTTPException
    from src.backend.api.schemas import UpdatePythonCodeRequest

    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        status="accepted",
        accepted_at=datetime.now(UTC),
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    with pytest.raises(HTTPException) as exc_info:
        await update_python_code(job_id, UpdatePythonCodeRequest(python_code="x=1"), session)

    assert exc_info.value.status_code == 409
    assert "accepted" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_save_block_python_on_accepted_job_returns_409() -> None:
    """PATCH /blocks/{id}/python on an accepted job must return 409."""
    from fastapi import HTTPException
    from src.backend.api.schemas import BlockPythonEditRequest

    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        status="accepted",
        accepted_at=datetime.now(UTC),
    )
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = job
    session.execute.return_value = result_mock

    with pytest.raises(HTTPException) as exc_info:
        await save_block_python(
            job_id,
            "step.sas:1",
            BlockPythonEditRequest(python_code="x = 1"),
            session,
        )

    assert exc_info.value.status_code == 409
    assert "accepted" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_download_job_returns_zip_for_proposed_status() -> None:
    """download_job returns a zip for a job in 'proposed' status."""
    job_id = uuid.uuid4()
    job = _make_job(str(job_id), status="proposed", python_code="x = 1")
    session = AsyncMock()

    # First execute: select(Job) → job
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job

    # Second execute: select(BlockRevision) → no revisions
    rev_result = MagicMock()
    rev_result.scalars.return_value.all.return_value = []

    session.execute.side_effect = [job_result, rev_result]

    response = await download_job(job_id, session)

    assert response.media_type == "application/zip"
    content_disposition = response.headers.get("Content-Disposition", "")
    assert f"rosetta-{job_id}.zip" in content_disposition


@pytest.mark.asyncio
async def test_download_job_returns_zip_for_accepted_status() -> None:
    """download_job returns a zip for an already-accepted job."""
    job_id = uuid.uuid4()
    job = _make_job(
        str(job_id),
        status="accepted",
        python_code="import pandas as pd\n",
        accepted_at=datetime.now(UTC),
        accepted_by="anonymous",
    )
    session = AsyncMock()

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job

    rev_result = MagicMock()
    rev_result.scalars.return_value.all.return_value = []

    session.execute.side_effect = [job_result, rev_result]

    response = await download_job(job_id, session)

    assert response.media_type == "application/zip"
