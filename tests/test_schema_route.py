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
    lineage: dict[str, Any] | None = None,
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
        lineage=lineage,
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
        "libname_map": {"rawdir": "/data/raw"},
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
        "libname_map": {"rawdir": "/data/raw"},
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
async def test_schema_route_derived_dataset_source_columns(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Derived dataset populated by P2-C _merge_source_column_schema returns columns in response.

    Simulates a data_schema entry for a derived output (e.g. sdtm_dm) that has no
    uploaded .sas7bdat file but was populated from LENGTH/FORMAT/ATTRIB declarations
    by the worker pipeline. The route must serialise these columns exactly like
    file-backed datasets — no special handling needed or skipped.

    Column type mapping follows map_sas_to_semantic_type:
    - character → String (regardless of format)
    - double + DATE9. format → Date
    - double + no format → Number
    """
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {"outdir": "/data/out"},
        "data_schema": {
            # Derived dataset — key is a plain stem (no extension), as written by
            # _merge_source_column_schema when no uploaded file sentinel is present.
            "sdtm_dm": {
                "columns": ["USUBJID", "AGE", "STARTDT"],
                "column_types": {
                    "USUBJID": "character",
                    "AGE": "double",
                    "STARTDT": "double",
                },
                "column_labels": {
                    "USUBJID": "Unique Subject Identifier",
                    "AGE": "Age",
                    "STARTDT": "Start Date",
                },
                # STARTDT is a numeric date stored with DATE9. format — maps to "Date"
                "column_formats": {"STARTDT": "DATE9.", "AGE": ""},
                "row_count": None,
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
    assert table["dataset_name"] == "sdtm_dm"
    assert table["row_count"] is None

    cols_by_name = {c["name"]: c for c in table["columns"]}
    assert set(cols_by_name.keys()) == {"USUBJID", "AGE", "STARTDT"}

    # Character column → String semantic type regardless of any format
    assert cols_by_name["USUBJID"]["sas_type"] == "character"
    assert cols_by_name["USUBJID"]["semantic_type"] == "String"
    assert cols_by_name["USUBJID"]["label"] == "Unique Subject Identifier"

    # Numeric column with DATE9. format → Date semantic type
    assert cols_by_name["STARTDT"]["sas_type"] == "double"
    assert cols_by_name["STARTDT"]["semantic_type"] == "Date"
    assert cols_by_name["STARTDT"]["sas_format"] == "DATE9."
    assert cols_by_name["STARTDT"]["label"] == "Start Date"

    # Plain numeric (no format) → Number semantic type
    assert cols_by_name["AGE"]["sas_type"] == "double"
    assert cols_by_name["AGE"]["semantic_type"] == "Number"


@pytest.mark.asyncio
async def test_schema_route_dataset_no_columns_returns_empty_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Dataset with no column info at all returns an entry with columns=[].

    This covers the UI empty-state path: the API must include the table in the
    response (so the left-hand tree still shows the dataset name) but with
    columns=[] so the frontend renders the fallback message.
    """
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {
            "work_temp": {
                "columns": [],
                "column_types": {},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            }
        },
        "relationships": [],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()

    # The table IS present in the response (UI can show it in the tree)
    assert len(body["tables"]) == 1
    table = body["tables"][0]
    assert table["dataset_name"] == "work_temp"
    # columns is empty — frontend renders the fallback message
    assert table["columns"] == []
    assert table["row_count"] is None


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


# ── DDL generation (P3-E) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_route_ddl_populated_for_table_with_columns(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TableSchema.ddl is generated for a table that has columns.

    The DDL must contain a CREATE TABLE statement qualified with the target_schema
    and dataset_name, and include a column definition for each column.
    """
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {"rawdir": "/data/raw"},
        "data_schema": {
            "/data/raw/subjects.sas7bdat": {
                "columns": ["subject_id", "visit_date"],
                "column_types": {"subject_id": "character", "visit_date": "double"},
                "column_labels": {},
                "column_formats": {"visit_date": "DATE9."},
                "row_count": 100,
            }
        },
        "relationships": [],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()

    table = body["tables"][0]
    ddl: str = table["ddl"]

    # Must be a non-empty CREATE TABLE statement
    assert ddl.startswith("CREATE TABLE")
    # Qualified with target_schema (= libname "rawdir") and dataset_name
    assert "rawdir.subjects" in ddl
    # Both columns must appear
    assert "subject_id" in ddl
    assert "visit_date" in ddl
    # SQL types: character → TEXT, double + DATE9. → DATE
    assert "TEXT" in ddl
    assert "DATE" in ddl


@pytest.mark.asyncio
async def test_schema_route_ddl_stub_for_table_with_no_columns(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TableSchema.ddl is a stub comment for a table with no columns.

    generate_create_table returns a stub DDL (with '-- no columns extracted')
    when the column list is empty.  The route must propagate that stub rather
    than an empty string.
    """
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {
            "work_empty": {
                "columns": [],
                "column_types": {},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            }
        },
        "relationships": [],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()

    table = body["tables"][0]
    ddl: str = table["ddl"]

    # Must still be a CREATE TABLE stub, not an empty string
    assert ddl.startswith("CREATE TABLE")
    assert "no columns extracted" in ddl


@pytest.mark.asyncio
async def test_schema_route_relationships_from_migration_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Route returns all valid relationships from migration_plan.relationships."""
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {},
        "relationships": [
            {
                "left_table": "patients",
                "right_table": "labs",
                "key_column": "patient_id",
                "via_block_id": "analysis.sas:20",
                "relationship_type": "join",
            },
            {
                "left_table": "patients",
                "right_table": "demographics",
                "key_column": "subject_id",
                "via_block_id": "demographics.sas:5",
                "relationship_type": "merge",
            },
        ],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()

    rels = body["relationships"]
    assert len(rels) == 2

    rel_types = {r["relationship_type"] for r in rels}
    assert "join" in rel_types
    assert "merge" in rel_types

    left_tables = {r["left_table"] for r in rels}
    assert "patients" in left_tables


@pytest.mark.asyncio
async def test_schema_route_relationships_empty_when_plan_has_none(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Route returns empty relationships list when migration_plan has no relationships key."""
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {},
        # No 'relationships' key at all
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()

    assert body["relationships"] == []


# ── Lineage enrichment — pure pipeline outputs ────────────────────────────────


@pytest.mark.asyncio
async def test_schema_route_lineage_pure_outputs_added(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pure pipeline outputs absent from data_schema are added as stub TableSchema entries.

    Step 1 produces 'dose' from 'dm'; step 2 produces 'adsl_age' from 'dose'.
    'dose' is both an output (step 1) and an input (step 2), so it is NOT a pure output.
    'adsl_age' is only an output and never consumed, so it IS a pure output and must be
    appended as a stub entry with path='output/adsl_age', libname=None, columns=[],
    target_columns=[], ddl_source='source_estimated', schema_status='not_run'.
    """
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {
            "/raw/dm.sas7bdat": {
                "columns": ["USUBJID", "AGE"],
                "column_types": {"USUBJID": "character", "AGE": "double"},
                "column_labels": {},
                "column_formats": {},
                "row_count": 100,
            }
        },
        "relationships": [],
    }
    lineage: dict[str, Any] = {
        "pipeline_steps": [
            {"inputs": ["dm"], "outputs": ["dose"]},
            {"inputs": ["dose"], "outputs": ["adsl_age"]},
        ]
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan, lineage=lineage)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()

    # dm (from data_schema) + adsl_age (pure output); dose is input to step 2 so not pure
    assert len(body["tables"]) == 2

    tables_by_name = {t["dataset_name"]: t for t in body["tables"]}
    assert "dm" in tables_by_name
    assert "adsl_age" in tables_by_name
    assert "dose" not in tables_by_name

    stub = tables_by_name["adsl_age"]
    assert stub["libname"] is None
    assert stub["columns"] == []
    assert stub["target_columns"] == []
    assert stub["schema_status"] == "not_run"
    assert stub["ddl_source"] == "source_estimated"
    assert stub["path"] == "output/adsl_age"


@pytest.mark.asyncio
async def test_schema_route_lineage_no_duplicate_if_already_in_data_schema(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A pure pipeline output already present in data_schema is not added a second time.

    data_schema contains both '/raw/dm.sas7bdat' and '/raw/dose.sas7bdat'.
    The single pipeline step produces 'dose' from 'dm', making 'dose' a pure output.
    Because 'dose' already appears in data_schema, no duplicate entry must be inserted.
    """
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {
            "/raw/dm.sas7bdat": {
                "columns": ["USUBJID"],
                "column_types": {"USUBJID": "character"},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            },
            "/raw/dose.sas7bdat": {
                "columns": ["DOSE"],
                "column_types": {"DOSE": "double"},
                "column_labels": {},
                "column_formats": {},
                "row_count": None,
            },
        },
        "relationships": [],
    }
    lineage: dict[str, Any] = {
        "pipeline_steps": [
            {"inputs": ["dm"], "outputs": ["dose"]},
        ]
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan, lineage=lineage)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()

    # Exactly 2 tables — no duplicate 'dose' entry
    assert len(body["tables"]) == 2
    dataset_names = [t["dataset_name"] for t in body["tables"]]
    assert dataset_names.count("dose") == 1


@pytest.mark.asyncio
async def test_schema_route_lineage_none_adds_no_tables(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """When job.lineage is None the route must not crash and must return only data_schema tables."""
    migration_plan: dict[str, Any] = {
        "summary": "test",
        "block_plans": [],
        "libname_map": {},
        "data_schema": {
            "/raw/ae.sas7bdat": {
                "columns": ["AETERM"],
                "column_types": {"AETERM": "character"},
                "column_labels": {},
                "column_formats": {},
                "row_count": 50,
            }
        },
        "relationships": [],
    }
    job_id = await _insert_job(db_session, migration_plan=migration_plan, lineage=None)
    response = await client.get(f"/jobs/{job_id}/schema")
    assert response.status_code == 200
    body = response.json()

    # Only the one table from data_schema — no extra stubs injected
    assert len(body["tables"]) == 1
    assert body["tables"][0]["dataset_name"] == "ae"
