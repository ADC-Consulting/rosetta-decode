"""Tests for the POST /migrate route — sas7bdat reference dataset handling."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_MINIMAL_SAS = b"data out; set in; run;"
_FAKE_SAS7BDAT = b"\x00" * 16


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


@pytest.mark.asyncio
async def test_upload_sas7bdat_stores_path_in_files(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.post(
        "/migrate",
        files=[
            ("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain")),
            ("ref_dataset", ("ref.sas7bdat", _FAKE_SAS7BDAT, "application/octet-stream")),
        ],
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    from sqlalchemy import select
    from src.backend.db.models import Job

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    assert "__ref_sas7bdat__" in job.files
    assert job.files["__ref_sas7bdat__"].endswith(".sas7bdat")


@pytest.mark.asyncio
async def test_upload_invalid_ref_dataset_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/migrate",
        files=[
            ("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain")),
            ("ref_dataset", ("notes.txt", b"not a dataset", "text/plain")),
        ],
    )
    assert response.status_code == 400


# ── ref_csv upload ────────────────────────────────────────────────────────────

_FAKE_CSV = b"col_a,col_b\n1,2\n3,4\n"


@pytest.mark.asyncio
async def test_upload_ref_csv_stores_path_in_files(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.post(
        "/migrate",
        files=[
            ("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain")),
            ("ref_csv", ("reference.csv", _FAKE_CSV, "text/csv")),
        ],
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    from sqlalchemy import select
    from src.backend.db.models import Job

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    assert "__ref_csv__" in job.files
    assert job.files["__ref_csv__"].endswith(".csv")


@pytest.mark.asyncio
async def test_upload_invalid_ref_csv_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/migrate",
        files=[
            ("sas_files", ("script.sas", _MINIMAL_SAS, "text/plain")),
            ("ref_csv", ("data.xlsx", b"not a csv", "application/octet-stream")),
        ],
    )
    assert response.status_code == 400
    assert "ref_csv must be a .csv file" in response.json()["detail"]
