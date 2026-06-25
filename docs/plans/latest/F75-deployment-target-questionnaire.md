# F75 — Accept-time deployment questionnaire + cloud-aware Databricks bundle

**Phase:** 4 (builds directly on F74 — the DLT handoff bundle)
**Area:** Backend (packaging / bundle generator) + Frontend (accept dialog) + Docs
**Status:** proposed
**Depends on:** F74 (`bbcf81a feat(F74): Databricks DLT handoff bundle + deployment guide`)
**Branch:** `feat/F75-deployment-target-questionnaire` (cut fresh from `main` after F74 merges)

---

## Context

F74 shipped a real, deployable Databricks Asset Bundle in every job's handoff zip
(`databricks.yml`, `transformations/*_dlt.py`, `DEPLOYMENT_GUIDE.md`). It works, but
it **guesses** three things the client must actually decide, and it **hardcodes
Azure**:

- `src/backend/api/databricks_bundle.py:283` — `DATABRICKS_DATA_ROOT` defaults to
  `abfss://data@<storage>.dfs.core.windows.net/`.
- `src/backend/api/databricks_bundle.py:422` — the `storage_root` DAB variable, same
  ABFSS literal.
- `src/backend/api/templates/databricks_deployment_guide.md.j2` — ABFSS placeholders
  and an `azuredatabricks.net` auth-host example.

It also assumes serverless compute, a fixed daily cron, and carries **no
data-ingestion strategy** — yet the Databricks SAS-migration guide (§8 Technology
Mapping, §9 Data Migration) defines concrete, choosable approaches (historical load
vs staging; PROC EXPORT→CSV/Parquet vs direct `.sas7bdat` ingestion; Lakeflow
Connect / Spark JDBC / Auto Loader `cloudFiles`; UC Volumes for persistence).

**The idea (user-confirmed):** when the user clicks **Accept migration**, show a
short button-select dialog whose answers parameterise the generated bundle. Ask,
don't guess.

## Reproducibility note (non-negotiable, inherited from F74)

The questionnaire answers are persisted on the job (`user_overrides`) and are
therefore *deterministic inputs* to generation. Same answers → byte-identical zip.
No timestamps, no `Math.random`, sorted members — the F74 guarantee is preserved.
Absent answers (old jobs, pre-accept download) deterministically fall back to
**Azure / serverless / catalog=`main` / schema=Data-tab default** — i.e. exactly
today's output. Zero behaviour change for existing jobs.

---

## The questionnaire (button selects, defaults pre-selected)

| # | Question | Options (default first) | Drives |
|---|---|---|---|
| 1 | Cloud provider | Azure / AWS / GCP | Storage URI scheme + guide auth host + Auto Loader notes |
| 2 | Data ingestion approach | Historical load (one-time) / Staging (ongoing) | Guide "Data migration" section + root-table read TODOs |
| 3 | Compute | Serverless / Classic cluster | `serverless: true` vs `node_type_id`/`autoscale` in the pipeline resource |
| 4 | Unity Catalog target | `catalog` (default `main`) + `schema` (default Data-tab `target_schema`) | DAB variables, pre-filled & editable |

Storage scheme per provider (single source of truth in the generator):

- **AWS** → `s3://<bucket>/`
- **Azure** → `abfss://<container>@<account>.dfs.core.windows.net/`
- **GCP** → `gs://<bucket>/`

Question 2's finer sub-choice (PROC EXPORT, direct `.sas7bdat`, JDBC, Auto Loader)
is surfaced as guidance **in the deployment guide only** — it does not alter the
`@dlt.table` transform logic, only the documented root-data on-ramp.

---

## Subtasks

### S-A: Persist questionnaire answers on accept (no migration)
**File:** `src/backend/api/schemas.py` + `src/backend/api/routes/jobs.py`
**Done when:** `AcceptJobRequest` gains an optional `deployment_target` model
(`provider`, `ingestion_approach`, `compute_mode`, `catalog`, `schema`, all
optional with documented defaults); `accept_job` merges it into
`user_overrides["deployment_target"]` next to the existing `acceptance_note` merge
(`routes/jobs.py:765-779`). No Alembic migration (lives in existing JSON column).
F68 immutability guard unchanged.

### S-B: `DeploymentTarget` value object + scheme resolver
**File:** `src/backend/api/databricks_bundle.py`
**Depends on:** none
**Done when:** a small pure helper resolves `provider → storage scheme/default
root` and `compute_mode → pipeline compute block`. Unit-tested in isolation.

### S-C: Make the generator cloud-aware
**File:** `src/backend/api/databricks_bundle.py`
**Depends on:** S-B
**Done when:** `render_dlt_pipeline` and `render_databricks_yml` accept a
`DeploymentTarget` and replace all three hardcoded ABFSS literals with
scheme-derived defaults; `serverless`/classic-cluster toggle honoured; catalog &
schema sourced from answers (falling back to Data-tab `target_schema`). Output
still byte-deterministic.

### S-D: Thread answers through packaging
**File:** `src/backend/api/packaging.py`
**Depends on:** S-A, S-C
**Done when:** `build_migration_package` reads
`job.user_overrides["deployment_target"]`, constructs the `DeploymentTarget`
(default Azure/serverless when absent), and passes it to the generator + guide
render. No new DB query.

### S-E: Cloud-aware deployment guide
**File:** `src/backend/api/templates/databricks_deployment_guide.md.j2` +
`docs/service-delivery/databricks-deployment-guide.md`
**Depends on:** S-A
**Done when:** the template takes `provider` / `ingestion_approach` /
`compute_mode`; the storage-paths and auth-host examples switch on provider; a new
provider-switched **"Data migration"** section reflects the Databricks guide §9
patterns for the chosen approach. Canonical doc kept in sync (note the sync
requirement, as in F74 S-F).

### S-F: Accept dialog (frontend)
**File:** `src/frontend/src/components/JobDetail/AcceptMigrationDialog.tsx` (new)
+ `JobDetailPage.tsx` + `src/frontend/src/api/jobs.ts` + `types.ts`
**Depends on:** S-A
**Done when:** the Accept CTA opens a shadcn `Dialog` with segmented button selects
(defaults pre-selected so one click still accepts); answers POST with the existing
accept call. Read-only/accepted states from F68 unchanged.

### S-G: Tests
**File:** `tests/test_databricks_bundle.py` (extend) + `tests/test_packaging.py`
(extend) + route test for accept-with-target
**Depends on:** S-A..S-D
**Done when:** unit tests cover each provider's scheme in both generated files,
classic-vs-serverless compute, catalog/schema override, **absent-answers fallback
== current F74 bytes** (regression lock), and byte-reproducibility. Accept route
test asserts `deployment_target` round-trips into `user_overrides`.

### S-H: `make test` green
**Depends on:** all
**Done when:** `make test` exits 0 (all 7 gates: ruff, mypy, pytest+coverage, tsc,
eslint, build).

---

## Critical files (reuse, don't reinvent)
- `src/backend/api/databricks_bundle.py` — `render_dlt_pipeline`,
  `render_databricks_yml`, `build_dataset_graph` (F74).
- `src/backend/api/packaging.py` — `build_migration_package`, `_write_zip_member`,
  `_ZIP_EPOCH`, `_RUNTIME_PINS`, `infer_requirements`.
- `src/backend/api/routes/jobs.py:729-797` — `accept_job` (merge point).
- `src/backend/api/schemas.py` — `AcceptJobRequest`.
- `src/backend/api/templates/databricks_deployment_guide.md.j2` (F74).
- `src/frontend/src/pages/JobDetailPage.tsx` — Accept CTA / accepted badge (F68).

## Out of scope
- Executing any ingestion path or validating against a live workspace.
- Per-table ingestion overrides (one approach per job).
- Activating `DatabricksBackend` (`CLOUD=true` stays `NotImplementedError`).
- Any new Alembic migration.

## Open decision for the user
- Ship **AWS + Azure only** first (user's stated pair), or include **GCP** now?
  Proposed default: include GCP (one extra scheme string; covered by Databricks
  guide §9) — trivially droppable if not wanted.
