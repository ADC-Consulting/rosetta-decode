# F77 — Scoping / Assessment Mode (fast static parse → client scoping report, no LLM)

**Phase:** new feature
**Area:** Backend (sync) + Worker-parser extensions + Frontend + Docs
**Status:** complete (pending commit + PR)
**Depends on:** parser (done), `detect_missing_dependencies` (done)
**Branch:** `feat/F77-scoping-assessment-mode`
**GitHub:** ADC-Consulting/rosetta-decode#76

> **Numbering note:** `F76` was already taken by the Databricks *delivery-format* bundle
> work (DLT vs Classic Spark Job, part of the F74/F75 line, already committed). This
> scoping feature is therefore **F77 internally = GitHub issue #76**. See the DECISIONS.md
> note dated 2026-06-19.

---

## Context

Pre-sales / discovery needs a **fast, cost-free, LLM-free** assessment of a client SAS
file set to scope an engagement and produce an effort estimate *before* committing to a
full migration run. The migration pipeline (parse → LLM → codegen → reconcile) takes
minutes–hours and costs tokens; scoping must run in **under 60s for 50 files** with zero
LLM calls. F77 is mostly **assembly + presentation** over existing parser output, plus
three additive parser detectors, a synchronous scope path, a report endpoint, and UI.

### Decisions (locked, after stress-testing the original plan)
- **Execution: synchronous in the backend.** `POST /migrate` with `mode=scope` parses
  in-request (`run_in_threadpool`), creates the job already `done`, stores
  `scoping_report`, and returns immediately. *Rationale:* the backend already imports and
  runs `SASParser` synchronously — no service boundary to cross — and the worker is only
  DB-polled every 1–5s, so a worker job would only add latency. No worker `main.py` change.
- **Parser fidelity: full**, but **additive only — no new `BlockType`** (would perturb the
  translation router/agents). ODS / INFILE / LIBNAME-engine captured as data fields.
- **Effort estimate: provisional** rate table, clearly flagged. See
  `docs/context/estimation-model.md`.
- **Endpoint:** `GET /jobs/{id}/assessment` (avoids collision with the F34 `/scoping` BOM).

---

## Subtasks

### S-A — Parser: LIBNAME engine, ODS, INFILE/FILE *(done)*
- `ParseResult.libname_engines`, `ParseResult.ods_targets`, `ParseResult.external_file_paths`,
  `SASBlock.infile_paths` (all additive). New `_extract_libname_engines`, `_extract_ods`,
  `_extract_infile_paths`, `_collect_external_paths`, `_resolve_fileref` in `parser.py`.
- `libname_map` and `_extract_libnames` left untouched. **No new `BlockType`.**
- Tests: `tests/test_parser_scoping_detectors.py` (incl. regression guard asserting block
  output is unchanged). ✅
- [X] done

### S-B — Scoping engine module *(done)*
- `src/worker/engine/scoping.py` (`build_scoping_report`), `src/worker/engine/estimation_model.py`
  (`RATE_TABLE`, `estimate_effort`). Report models in `models.py`: `ScopingReport`,
  `FileInventoryItem`, `BlockBreakdown`, `RiskFlag`, `DataAssetInventory`, `EffortEstimate`,
  `ComplexityTier`, `TranslationCategory`.
- Reuses `detect_missing_dependencies` + `_extract_macro_invocations`. Exhaustive
  category-by-`BlockType` map (a new BlockType fails a test rather than silently defaulting).
  Engine-only libref gotcha handled (known if in `libname_map` OR `libname_engines`).
- Tests: `tests/test_scoping_engine.py`. ✅
- [X] done

### S-C — Synchronous scope path + persistence *(done)*
- `Job.mode` (default `"migrate"`) + `Job.scoping_report` (JSON) columns; migration
  `alembic/versions/021_add_job_mode_scoping_report.py` (down_revision `020`).
- `POST /migrate` gains `mode` form field; `mode=scope` parses off the event loop and
  persists a `done` job with the report. No worker involvement, no LLM/token usage.
- Tests: `tests/test_migrate_route.py` (scope success, invalid-mode 400, migrate regression). ✅
- [X] done

### S-D — Assessment endpoint + markdown *(done)*
- `GET /jobs/{id}/assessment` → `AssessmentReportResponse` `{job_id, job_name, report, markdown}`;
  404 when no report. Markdown rendered at request time (run timestamp injected, not stored).
- New `src/backend/core/scoping_report_markdown.py`; `AssessmentReportResponse` in `schemas.py`.
- Tests: `tests/test_assessment_route.py`, `tests/test_scoping_report_markdown.py`. ✅
- [X] done

### S-E — Frontend toggle + report panel *(done)*
- `scopeOnly` in `UploadStateContext`; "Scope only" checkbox in `UploadPage`; `submitMigration`
  appends `mode=scope`; `getJobAssessment` in `api/jobs.ts`; TS types in `api/types.ts`;
  `downloadMarkdown` in `lib/utils.ts`; new `AssessmentReportPanel.tsx` (5 sections + provisional
  badge + copy/download); `JobDetailPage` renders it when `job.mode === "scope"`.
- Backend: `mode` added to `JobStatusResponse` so the UI knows to show the assessment view.
- Frontend has no unit-test harness; type safety enforced via `tsc`/lint/build in `make test`. ✅
- [X] done

### S-F — Docs, journal *(done)*
- `docs/context/estimation-model.md` (provisional rates, marked draft); this plan; journal
  (SESSIONS/BACKLOG/DECISIONS) updated. Numbered F77 to avoid the committed `F76` delivery-format label.
- [X] done

---

## Out of scope
- Discovery questionnaire (companion doc) — informs inputs, not an AC deliverable; future.
- PDF export — Markdown only for MVP.
- Calibrating estimation rates to real data — ships provisional, flagged.

## Verification
- `make test` exits 0 across all gates (ruff, mypy strict, pytest+coverage, tsc, frontend
  lint/build). Manual: "Scope only" upload returns a report in one request (<60s), no token
  usage, all 5 sections render, Markdown download works. Normal migration job unchanged.
