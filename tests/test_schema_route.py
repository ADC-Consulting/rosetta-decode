"""Tests for GET /jobs/{id}/schema route."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Base, Job
from src.backend.db.session import get_async_session
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Fresh in-memory SQLite database for each test."""
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


async def _insert_job(
    session: AsyncSession,
    *,
    status: str = "proposed",
    migration_plan: dict[str, Any] | None = None,
    user_overrides: dict[str, Any] | None = None,
) -> str:
    """Insert a minimal Job row and return its ID string."""
    job_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    job = Job(
        id=job_id,
        status=status,
        input_hash="abc123",
        files={"test.sas": "data out; set in; run;"},
        migration_plan=migration_plan,
        user_overrides=user_overrides,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job_id


# ── GET /jobs/{id}/schema ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_route_not_found(client: AsyncClient) -> None:
    """Unknown job UUID returns 404."""
    response = await client.get(f"/jobs/{uuid.uuid4()}/schema")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_schema_route_empty_plan(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with no migration_plan returns 200 with empty tables list."""
    job_id = await _insert_job(db_session, migration_plan=None)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["tables"] == []
    assert body["libname_map"] == {}
    assert body["relationships"] == []


@pytest.mark.asyncio
async def test_schema_route_empty_data_schema(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Job with migration_plan but no data_schema key returns empty tables."""
    job_id = await _insert_job(
        db_session, migration_plan={"summary": "test", "block_plans": [], "libname_map": {}}
    )
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["tables"] == []


@pytest.mark.asyncio
async def test_schema_route_single_table(client: AsyncClient, db_session: AsyncSession) -> None:
    """Job with one data_schema entry returns one table with correct columns."""
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {"/data/raw": "rawdir"},
        "data_schema": {
            "/data/raw/patients.sas7bdat": {
                "columns": ["id", "dob", "amount"],
                "column_types": {"id": "double", "dob": "double", "amount": "double"},
                "column_labels": {"id": "Patient ID", "dob": "Date of Birth", "amount": None},
                "column_formats": {"id": "", "dob": "DATE9.", "amount": "COMMA12.2"},
                "row_count": 500,
            }
        },
        "relationships": [],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()
    assert len(body["tables"]) == 1

    table = body["tables"][0]
    assert table["dataset_name"] == "patients"
    assert table["libname"] == "rawdir"
    assert table["target_schema"] == "rawdir"
    assert table["row_count"] == 500

    cols_by_name = {c["name"]: c for c in table["columns"]}
    assert cols_by_name["id"]["semantic_type"] == "Number"
    assert cols_by_name["dob"]["semantic_type"] == "Date"
    assert cols_by_name["amount"]["semantic_type"] == "Decimal"
    assert cols_by_name["id"]["label"] == "Patient ID"


@pytest.mark.asyncio
async def test_schema_route_column_type_override(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User column_type_overrides in schema_overrides are exposed on the column."""
    path = "/data/raw/items.sas7bdat"
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {
            path: {
                "columns": ["code"],
                "column_types": {"code": "double"},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            }
        },
        "relationships": [],
    }
    user_overrides: dict[str, Any] = {
        "schema_overrides": {
            path: {
                "column_type_overrides": {"code": "String"},
                "target_schema": "staging",
            }
        }
    }
    job_id = await _insert_job(
        db_session, migration_plan=migration_plan, user_overrides=user_overrides
    )
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()
    table = body["tables"][0]
    assert table["target_schema"] == "staging"
    col = table["columns"][0]
    assert col["override_type"] == "String"
    assert col["semantic_type"] == "Number"  # semantic type unaffected by override_type


@pytest.mark.asyncio
async def test_schema_route_relationships(client: AsyncClient, db_session: AsyncSession) -> None:
    """Valid relationships are returned; incomplete entries are filtered out."""
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {},
        "relationships": [
            {
                "left_table": "patients",
                "right_table": "visits",
                "key_column": "patient_id",
                "via_block_id": "main.sas:10",
                "relationship_type": "merge",
            },
            # Incomplete entry — missing relationship_type
            {
                "left_table": "a",
                "right_table": "b",
                "key_column": "id",
            },
        ],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()
    assert len(body["relationships"]) == 1
    rel = body["relationships"][0]
    assert rel["left_table"] == "patients"
    assert rel["relationship_type"] == "merge"


@pytest.mark.asyncio
async def test_schema_route_character_column(client: AsyncClient, db_session: AsyncSession) -> None:
    """Character-typed column maps to semantic_type=String regardless of format."""
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {
            "/data/raw/names.sas7bdat": {
                "columns": ["name"],
                "column_types": {"name": "character"},
                "column_labels": {},
                "column_formats": {"name": "$50."},
                "row_count": 10,
            }
        },
        "relationships": [],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    col = response.json()["tables"][0]["columns"][0]
    assert col["semantic_type"] == "String"
    assert col["sas_format"] == "$50."


# ── PATCH /jobs/{id}/schema ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_schema_libname_override_reflected_in_get(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH libname_overrides persists and is reflected in subsequent GET."""
    path = "/data/raw/patients.sas7bdat"
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {"/data/raw": "rawdir"},
        "data_schema": {
            path: {
                "columns": ["id"],
                "column_types": {"id": "double"},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            }
        },
        "relationships": [],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)

    # Confirm default target_schema before patch
    pre = await client.get(f"/jobs/{job_id}/schema")
    assert pre.status_code == 200
    assert pre.json()["tables"][0]["target_schema"] == "rawdir"

    # PATCH with libname override
    patch_resp = await client.patch(
        f"/jobs/{job_id}/schema",
        json={"libname_overrides": {"rawdir": "raw_data"}, "column_type_overrides": {}},
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    # The updated GET response must reflect the new target_schema
    assert body["tables"][0]["target_schema"] == "raw_data"

    # Independent GET should also return the updated value
    get_resp = await client.get(f"/jobs/{job_id}/schema")
    assert get_resp.status_code == 200
    assert get_resp.json()["tables"][0]["target_schema"] == "raw_data"


@pytest.mark.asyncio
async def test_patch_schema_column_type_override_reflected_in_get(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH column_type_overrides persists and override_type appears in GET response."""
    path = "/data/raw/subjects.sas7bdat"
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {
            path: {
                "columns": ["AGE"],
                "column_types": {"AGE": "double"},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            }
        },
        "relationships": [],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)

    # Confirm no override_type before patch
    pre = await client.get(f"/jobs/{job_id}/schema")
    assert pre.status_code == 200
    assert pre.json()["tables"][0]["columns"][0]["override_type"] is None

    # PATCH with column type override
    patch_resp = await client.patch(
        f"/jobs/{job_id}/schema",
        json={"libname_overrides": {}, "column_type_overrides": {path: {"AGE": "Integer"}}},
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    col = body["tables"][0]["columns"][0]
    assert col["override_type"] == "Integer"
    # semantic_type is unaffected — still derived from sas_type/sas_format
    assert col["semantic_type"] == "Number"

    # Independent GET confirms persistence
    get_resp = await client.get(f"/jobs/{job_id}/schema")
    assert get_resp.status_code == 200
    assert get_resp.json()["tables"][0]["columns"][0]["override_type"] == "Integer"
