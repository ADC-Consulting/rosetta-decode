# F5 — Per-Tab Version History + Unified Save Button

**Status: in-progress**  
**Branch: feat/F5-tab-versions**  
**Created: 2026-04-20**

## Goal

One Save button in the page header works across Plan, Editor, and Report tabs (not Lineage). Each tab has its own independent version history shown in the right-side rail. Saving creates a new version; clicking an old version previews and restores that tab's content.

## DB Schema

```sql
CREATE TABLE job_versions (
    id          VARCHAR(36)  PRIMARY KEY,
    job_id      VARCHAR(36)  NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    tab         VARCHAR(16)  NOT NULL CHECK (tab IN ('plan', 'editor', 'report')),
    content     JSONB        NOT NULL,
    trigger     VARCHAR(32)  NOT NULL DEFAULT 'human-save',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_job_versions_job_id_tab ON job_versions (job_id, tab);
```

Content shapes:
- plan: `{ "block_overrides": [...] }`
- editor: `{ "python_code": "...", "generated_files": {...} }`
- report: `{ "doc": "..." }`

## New Endpoints

- `POST /jobs/:id/versions?tab=` — create version row (write-through to existing job fields)
- `GET /jobs/:id/versions?tab=` — list versions (NO content field, ordered newest-first)
- `GET /jobs/:id/versions/:versionId` — fetch full content for one version

**DO NOT touch `GET /jobs/:id/history`** — that endpoint walks the parent_job_id chain and must remain unchanged.

## Subtasks

- [x] 1. Alembic migration 010: `job_versions` table
- [x] 2. `JobVersion` SQLAlchemy model in `src/worker/db/models.py`
- [x] 3. Pydantic schemas: `JobVersionSummary`, `JobVersionDetail`, `SaveVersionRequest`, `SaveVersionResponse`
- [x] 4. `POST /jobs/:id/versions?tab=` endpoint
- [x] 5. `GET /jobs/:id/versions?tab=` endpoint
- [x] 6. `GET /jobs/:id/versions/:versionId` endpoint
- [x] 7. Tests for new endpoints (tests/test_job_versions.py)
- [x] 8. TypeScript types + API client functions
- [x] 9. Lift plan + report save handlers into `JobDetailPage`; unified header Save button
- [x] 10. Lift `reportDoc` state into `JobDetailPage`; wire Report tab as controlled
- [x] 11. Update `VersionHistoryRail` to accept `tab` prop; switch to `getJobVersions`
- [x] 12. Version preview `Dialog` with Restore button
- [ ] 13. `make test` full pass + commit gate (pending — delete `src/frontend/@/` artefact first)

## Key Risks

- `GET /jobs/:id/history` MUST NOT be modified
- `PUT /python_code` kept alive until FE switches to new save path
- Plan save must MERGE block overrides (not overwrite entire plan)
- List responses MUST NOT include `content` field
