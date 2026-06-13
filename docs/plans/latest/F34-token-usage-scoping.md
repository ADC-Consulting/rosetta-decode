# F34 — Token Usage & Bill-of-Materials / Scoping Summary (#25)

**Phase:** 3
**Area:** Both (Worker + Backend / API + Frontend)
**Status:** complete

## Goal

Surface LLM token usage and cost per migration job, and generate a bill-of-materials / scoping summary for client proposals. Today all `result.usage()` data is discarded. This feature captures per-phase token counts (parse_analysis, migration_planning, translation, assembly_recon, enrichment), stores them on the job, exposes them via a new `/scoping` endpoint, and renders a collapsible "Scoping summary" panel on the Plan tab with a Copy as Markdown button.

## Acceptance Criteria

- [x] Per-project stats for token usage and approximate model cost
- [x] BOM summary: count of DATA steps and PROCs, risk/evaluation buckets per group
- [x] Output easy to copy into client proposals (Copy as Markdown)
- [x] `make test` exits 0

## Subtasks

### S-A: Migration 018 + Job model column
**Files:** `alembic/versions/018_add_job_token_usage.py` (new), `src/backend/db/models.py`
**Depends on:** none
**Done when:** nullable JSON column `token_usage` on `jobs` table; `Job.token_usage: Mapped[dict | None]`
- [x] done

### S-B: UsageTracker + contextvars
**File:** `src/worker/engine/usage.py` (new)
**Depends on:** none
**Done when:** `UsageTracker`, `activate()`, `set_phase()`, `record_usage()`, `snapshot()` all exist and are exported
- [x] done

### S-C: Tracker unit tests
**File:** `tests/test_usage_tracker.py` (new)
**Depends on:** S-B
**Done when:** tests cover no-op (no tracker), phase attribution, asyncio.to_thread propagation
- [x] done

### S-D: Instrument 12 LLM call sites
**Files:** 10 agent modules + `src/worker/engine/llm_client.py`
**Depends on:** S-B
**Done when:** every `await agent.run()` / `run_sync()` is followed by `record_usage(result.usage())`
- [x] done

### S-E: Orchestrator activate/set_phase/persist
**File:** `src/worker/main.py`
**Depends on:** S-A, S-B, S-D
**Done when:** tracker activated at start of `_execute()`; phase set at each of the 5 phase boundaries; snapshot persisted on success AND failure/cancel
- [x] done

### S-F: Worker integration test
**File:** `tests/test_worker_main_comprehensive.py` (extend)
**Depends on:** S-E
**Done when:** fake-LLM pipeline run results in non-null `token_usage` on the job record
- [x] done

### S-G: Pricing module
**File:** `src/backend/core/pricing.py` (new)
**Depends on:** none
**Done when:** `compute_cost()` returns USD estimate from LiteLLM JSON (24h cache) or static fallback; `None` for unknown models
- [x] done

### S-H: Pricing unit tests
**File:** `tests/test_pricing.py` (new)
**Depends on:** S-G
**Done when:** tests cover mocked httpx fetch, timeout fallback, unknown model → None, cache hit, prefix stripping
- [x] done

### S-I: API schemas
**File:** `src/backend/api/schemas.py`
**Depends on:** none
**Done when:** `PhaseTokens`, `TokenUsageStats`, `CostEstimate`, `BomSummary`, `ScopingSummaryResponse` all defined
- [x] done

### S-J: Extract _build_trust_blocks() helper
**File:** `src/backend/api/routes/jobs.py`
**Depends on:** none
**Done when:** criticality-aggregation logic extracted into a module-level helper; existing trust-report route and tests still pass
- [x] done

### S-K: Markdown renderer + tests
**Files:** `src/backend/core/scoping_markdown.py` (new), `tests/test_scoping_markdown.py` (new)
**Depends on:** S-G, S-I
**Done when:** `render_scoping_markdown()` produces header → BOM table → Risk & Review Effort → LLM Usage & Cost sections; unit tested
- [x] done

### S-L: GET /jobs/{id}/scoping route
**File:** `src/backend/api/routes/jobs.py`
**Depends on:** S-A, S-G, S-I, S-J, S-K
**Done when:** route returns `ScopingSummaryResponse`; 404 on unknown job; graceful nulls when token_usage missing or model unpriced
- [x] done

### S-M: Route tests
**File:** `tests/test_scoping_route.py` (new)
**Depends on:** S-L
**Done when:** tests cover full response, null usage, unknown model, markdown content, empty plan
- [x] done

### S-N: Frontend API client
**Files:** `src/frontend/src/api/types.ts`, `src/frontend/src/api/jobs.ts`
**Depends on:** S-L
**Done when:** `ScopingSummaryResponse` type and `getJobScopingSummary(jobId)` function exist
- [x] done

### S-O: ScopingSummaryPanel component
**File:** `src/frontend/src/components/JobDetail/ScopingSummaryPanel.tsx` (new)
**Depends on:** S-N
**Done when:** collapsible panel renders BOM, risk, usage/cost; Copy as Markdown button writes to clipboard + sonner toast
- [x] done

### S-P: Wire panel into PlanTab
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-O
**Done when:** ScopingSummaryPanel appears collapsed by default alongside existing collapsible sections
- [x] done

### S-Q: make test exits 0 + close-out
**Depends on:** all
**Done when:** `make test` green; plan subtasks checked off; BACKLOG updated
- [x] done

## Dependencies on other features

- F33 ETL tab (#42) — plan tab collapsible pattern reused (already merged)

## Out of scope

- Per-block token attribution
- chatbot (`explain_agent`) token tracking
- Historical backfill for old jobs
- Per-block ad-hoc refine token tracking (each refine spawns a child job → tracked there)
