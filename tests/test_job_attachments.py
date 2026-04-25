"""Tests for GET /jobs/{job_id}/attachments and GET /jobs/{job_id}/attachments/{path_key}."""

import os
import tempfile
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, Job
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_job(job_id: str, files: dict[str, str]) -> Job:
    """Create a minimal Job instance with the given files dict."""
    return Job(id=job_id, status="done", input_hash="abc", files=files)


# ── GET /jobs/{job_id}/attachments ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_attachments_job_not_found(client: AsyncClient) -> None:
    """Returns 404 when the job does not exist."""
    resp = await client.get(f"/jobs/{uuid.uuid4()}/attachments")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_attachments_empty_when_no_sentinel_keys(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Returns an empty attachment list when job.files has no sentinel keys."""
    job_id = str(uuid.uuid4())
    db_session.add(_make_job(job_id, {"myfile.sas": "data step; run;"}))
    await db_session.commit()

    resp = await client.get(f"/jobs/{job_id}/attachments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["attachments"] == []


@pytest.mark.asyncio
async def test_get_attachments_skips_missing_disk_file(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Silently skips sentinel keys whose disk paths do not exist."""
    job_id = str(uuid.uuid4())
    files = {"__ref_log_output.log__": "/tmp/does-not-exist-at-all.log"}
    db_session.add(_make_job(job_id, files))
    await db_session.commit()

    resp = await client.get(f"/jobs/{job_id}/attachments")
    assert resp.status_code == 200
    assert resp.json()["attachments"] == []


@pytest.mark.asyncio
async def test_get_attachments_classifies_log_extension(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Classifies .log files as category 'log'."""
    job_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
        f.write(b"log content")
        tmp_path = f.name
    try:
        files = {f"__ref_log_{os.path.basename(tmp_path)}__": tmp_path}
        db_session.add(_make_job(job_id, files))
        await db_session.commit()

        resp = await client.get(f"/jobs/{job_id}/attachments")
        assert resp.status_code == 200
        attachments = resp.json()["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["category"] == "log"
        assert attachments[0]["extension"] == ".log"
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_get_attachments_classifies_lst_extension(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Classifies .lst files as category 'log'."""
    job_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile(suffix=".lst", delete=False) as f:
        f.write(b"listing content")
        tmp_path = f.name
    try:
        files = {f"__ref_lst_{os.path.basename(tmp_path)}__": tmp_path}
        db_session.add(_make_job(job_id, files))
        await db_session.commit()

        resp = await client.get(f"/jobs/{job_id}/attachments")
        assert resp.status_code == 200
        attachments = resp.json()["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["category"] == "log"
        assert attachments[0]["extension"] == ".lst"
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_get_attachments_classifies_csv_extension(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Classifies .csv files as category 'output'."""
    job_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"col1,col2\n1,2\n")
        tmp_path = f.name
    try:
        files = {f"__ref_csv_{os.path.basename(tmp_path)}__": tmp_path}
        db_session.add(_make_job(job_id, files))
        await db_session.commit()

        resp = await client.get(f"/jobs/{job_id}/attachments")
        assert resp.status_code == 200
        attachments = resp.json()["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["category"] == "output"
        assert attachments[0]["extension"] == ".csv"
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_get_attachments_classifies_xlsx_extension(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Classifies .xlsx files as category 'output'."""
    job_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(b"xlsx bytes")
        tmp_path = f.name
    try:
        files = {f"__ref_xlsx_{os.path.basename(tmp_path)}__": tmp_path}
        db_session.add(_make_job(job_id, files))
        await db_session.commit()

        resp = await client.get(f"/jobs/{job_id}/attachments")
        assert resp.status_code == 200
        attachments = resp.json()["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["category"] == "output"
        assert attachments[0]["extension"] == ".xlsx"
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_get_attachments_classifies_sas7bdat_extension(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Classifies .sas7bdat files as category 'output'."""
    job_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile(suffix=".sas7bdat", delete=False) as f:
        f.write(b"sas data bytes")
        tmp_path = f.name
    try:
        files = {f"__ref_sas7bdat_{os.path.basename(tmp_path)}__": tmp_path}
        db_session.add(_make_job(job_id, files))
        await db_session.commit()

        resp = await client.get(f"/jobs/{job_id}/attachments")
        assert resp.status_code == 200
        attachments = resp.json()["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["category"] == "output"
        assert attachments[0]["extension"] == ".sas7bdat"
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_get_attachments_classifies_unknown_extension(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Classifies unknown extensions as category 'other'."""
    job_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        f.write(b"some bytes")
        tmp_path = f.name
    try:
        files = {f"__ref_xyz_{os.path.basename(tmp_path)}__": tmp_path}
        db_session.add(_make_job(job_id, files))
        await db_session.commit()

        resp = await client.get(f"/jobs/{job_id}/attachments")
        assert resp.status_code == 200
        attachments = resp.json()["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["category"] == "other"
        assert attachments[0]["extension"] == ".xyz"
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_get_attachments_returns_correct_metadata(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Returns correct filename, size_bytes, and extension for a real temp file."""
    job_id = str(uuid.uuid4())
    content = b"hello attachment"
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        basename = os.path.basename(tmp_path)
        key = f"__ref_log_{basename}__"
        db_session.add(_make_job(job_id, {key: tmp_path}))
        await db_session.commit()

        resp = await client.get(f"/jobs/{job_id}/attachments")
        assert resp.status_code == 200
        attachments = resp.json()["attachments"]
        assert len(attachments) == 1
        item = attachments[0]
        assert item["filename"] == basename
        assert item["size_bytes"] == len(content)
        assert item["extension"] == ".log"
        assert item["path_key"] == key
    finally:
        os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_get_attachments_skips_malformed_sentinel_no_trailing_dunder(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Silently skips sentinel keys that don't end with '__'."""
    job_id = str(uuid.uuid4())
    # This key starts with __ref_ but doesn't end with __ — malformed
    files = {"__ref_log_no_trailing": "/tmp/irrelevant.log"}
    db_session.add(_make_job(job_id, files))
    await db_session.commit()

    resp = await client.get(f"/jobs/{job_id}/attachments")
    assert resp.status_code == 200
    assert resp.json()["attachments"] == []


@pytest.mark.asyncio
async def test_get_attachments_skips_malformed_sentinel_no_underscore_separator(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Silently skips sentinel keys with no '_' separator after the ext prefix."""
    job_id = str(uuid.uuid4())
    # Strip the trailing __ so inner becomes "nounderscore", find("_") == -1
    files = {"__ref_nounderscore__": "/tmp/irrelevant.log"}
    db_session.add(_make_job(job_id, files))
    await db_session.commit()

    resp = await client.get(f"/jobs/{job_id}/attachments")
    assert resp.status_code == 200
    assert resp.json()["attachments"] == []


# ── GET /jobs/{job_id}/attachments/{path_key} ─────────────────────────────────


@pytest.mark.asyncio
async def test_download_attachment_job_not_found(client: AsyncClient) -> None:
    """Returns 404 when the job does not exist."""
    resp = await client.get(f"/jobs/{uuid.uuid4()}/attachments/__ref_log_test.log__")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_attachment_key_not_in_files(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Returns 404 when the path_key is absent from job.files."""
    job_id = str(uuid.uuid4())
    db_session.add(_make_job(job_id, {}))
    await db_session.commit()

    resp = await client.get(f"/jobs/{job_id}/attachments/__ref_log_missing.log__")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_attachment_disk_file_missing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Returns 404 when the sentinel key exists but the disk file is gone."""
    job_id = str(uuid.uuid4())
    key = "__ref_log_gone.log__"
    files = {key: "/tmp/absolutely-does-not-exist-rosetta.log"}
    db_session.add(_make_job(job_id, files))
    await db_session.commit()

    resp = await client.get(f"/jobs/{job_id}/attachments/{key}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_attachment_streams_file_content(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Returns 200 with correct file content when the attachment exists on disk."""
    job_id = str(uuid.uuid4())
    content = b"SAS log line 1\nSAS log line 2\n"
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        key = f"__ref_log_{os.path.basename(tmp_path)}__"
        db_session.add(_make_job(job_id, {key: tmp_path}))
        await db_session.commit()

        resp = await client.get(f"/jobs/{job_id}/attachments/{key}")
        assert resp.status_code == 200
        assert resp.content == content
    finally:
        os.unlink(tmp_path)
