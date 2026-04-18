# F-UI — Upload & Results Page

**Status:** complete  
**Branch:** feat/F-UI  
**Depends on:** F1-pipeline-generation, F-LLM, F-sas7bdat (all complete)

## Goal

Single-page React UI covering the full migration workflow: upload SAS files, poll job status, view generated Python + reconciliation report, download artefacts, and browse all past/active jobs.

At session end, `docker compose up` must start all four services and the app must be fully interactive at `http://localhost:5173`.

## Subtasks

- [x] S1 — Backend: CORS + `GET /jobs` + `.env.example`
  - [x] `cors_origins` setting in `src/backend/core/config.py`
  - [x] `CORSMiddleware` in `src/backend/main.py`
  - [x] `JobSummary` + `JobListResponse` schemas in `src/backend/api/schemas.py`
  - [x] `GET /jobs` route in `src/backend/api/routes/jobs.py`
  - [x] `.env.example` — full env var documentation
- [x] S2 — Frontend: install `react-router-dom` + `@tanstack/react-query`; routing scaffold in `App.tsx` / `main.tsx`
- [x] S3 — Frontend: typed API client (`src/api/types.ts`, `src/api/migrate.ts`, `src/api/jobs.ts`)
- [x] S4 — Frontend: `UploadPage` (`src/pages/UploadPage.tsx`)
- [x] S5 — Frontend: `JobsPage` + `JobResult` (`src/pages/JobsPage.tsx`, `src/components/JobResult.tsx`)
- [x] S6 — `make test` (84 tests, 90.65% coverage, tsc-check, frontend-lint, frontend-build) + `make docker-build`

## Key constraints

- CORS `allow_origins=["*"]` for dev (env-driven via `CORS_ORIGINS`)
- API client lives in `src/frontend/src/api/` — never inline in components
- React Query for all server state; `useState` only for local UI state
- No `any` in TypeScript — strict mode throughout
- `package-lock.json` must be committed alongside `package.json` for `npm ci` in Dockerfile to work
- After any frontend package changes, `make docker-build` must pass before commit
