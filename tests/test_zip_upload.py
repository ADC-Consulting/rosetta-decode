"""Tests for POST /migrate with zip archive support."""

import io
import uuid
import zipfile
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.core.config import backend_settings as _backend_settings
from src.backend.db.models import Base
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Fresh in-memory database for each test."""
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
    """AsyncClient wired to the FastAPI app with an in-memory test database."""

    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _make_zip(files: dict[str, bytes]) -> bytes:
    """Build an in-memory zip archive from a filename-to-bytes mapping.

    Args:
        files: Mapping of filename to raw file bytes.

    Returns:
        Raw bytes of the zip archive.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_zip_accepted_sas(client: AsyncClient) -> None:
    """A zip with a single .sas file is accepted and a job is created."""
    zip_bytes = _make_zip({"script.sas": b"data out; set in; run;"})
    response = await client.post(
        "/migrate",
        files={"zip_file": ("archive.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert "script.sas" in body["accepted"]
    assert body["rejected"] == []
    assert uuid.UUID(body["job_id"])


@pytest.mark.asyncio
async def test_zip_rejected_unknown_ext(client: AsyncClient) -> None:
    """A zip with only an unsupported extension returns 200 with the file in rejected."""
    zip_bytes = _make_zip({"data.parquet": b"PAR1some_parquet_data"})
    response = await client.post(
        "/migrate",
        files={"zip_file": ("archive.zip", zip_bytes, "application/zip")},
    )
    # Zip contained no supported files — expect 400
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_zip_mixed(client: AsyncClient) -> None:
    """A zip with mixed content reports accepted and rejected correctly."""
    zip_bytes = _make_zip(
        {
            "a.sas": b"data x; run;",
            "b.xlsx": b"PK fake excel bytes",
            "c.parquet": b"PAR1 fake parquet",
        }
    )
    response = await client.post(
        "/migrate",
        files={"zip_file": ("archive.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["accepted"]) == 2
    assert len(body["rejected"]) == 1
    rejected_names = [r["filename"] for r in body["rejected"]]
    assert "c.parquet" in rejected_names


@pytest.mark.asyncio
async def test_zip_oversized(client: AsyncClient) -> None:
    """A zip exceeding max_zip_bytes returns 413."""
    zip_bytes = _make_zip({"script.sas": b"data x; run;"})
    with patch.object(_backend_settings, "max_zip_bytes", 10):
        response = await client.post(
            "/migrate",
            files={"zip_file": ("archive.zip", zip_bytes, "application/zip")},
        )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_zip_and_sas_both_error(client: AsyncClient) -> None:
    """Providing both sas_files and zip_file returns 400."""
    zip_bytes = _make_zip({"script.sas": b"data x; run;"})
    response = await client.post(
        "/migrate",
        files=[
            ("sas_files", ("script.sas", b"data x; run;", "text/plain")),
            ("zip_file", ("archive.zip", zip_bytes, "application/zip")),
        ],
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_sas_files_accepted_list(client: AsyncClient) -> None:
    """Posting two .sas files without zip returns accepted list and empty rejected."""
    response = await client.post(
        "/migrate",
        files=[
            ("sas_files", ("first.sas", b"data a; run;", "text/plain")),
            ("sas_files", ("second.sas", b"data b; run;", "text/plain")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body["accepted"]) == {"first.sas", "second.sas"}
    assert body["rejected"] == []
