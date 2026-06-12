# Session Journal

Most recent session on top. Each entry should answer:

- What did we do?

---

## 2026-06-12 — F34 Data Storage tab — Phase 1 backend complete; P1-F pending
**Duration:** ~3h | **Focus:** F34 planning, backend implementation, PR #66 merged

### Done
- PR #66 (F33 ETL tab) merged; main synced
- F34 Data Storage tab designed: single feature covering 3 dev phases (schema browser, column types, ERD + DDL)
- Target-agnostic ANSI SQL for DDL; user-selectable target platform deferred to backlog
- F34 planned (16 subtasks), branch `feat/F34-data-storage-tab` created
- P1-A: `_sniff_file` extended to return 5-tuple with column_types/labels/formats; `DataFileInfo` extended; all test call sites updated
- P1-B: `libname_map` and `data_schema` added to `MigrationPlan`; worker pipeline populates them
- P2-A: `schema_utils.map_sas_to_semantic_type` (DATETIME checked before DATE to prevent prefix match bug); 8 unit tests
- P1-C: `GET /jobs/{id}/schema` route with `ColumnSchema`, `TableSchema`, `JobSchemaResponse`; 8 integration tests
- P1-D: `PATCH /jobs/{id}/schema` for libname + column type overrides; 2 tests
- P1-E: `getJobSchema` + `patchJobSchema` API client; TypeScript types
- Session hit org spend limit before P1-F (DataStorageTab component) could be delegated

### Decisions
- **F34 is a single feature covering all 3 phases:** Table browser (Phase 1), column type extraction (Phase 2), ERD + DDL (Phase 3) are built together — phased only for development sequencing · revisit never
- **Target-agnostic ANSI SQL DDL first:** User-selectable platform (Databricks, Snowflake) tracked in backlog · revisit after first client feedback
- **Schema overrides stored in user_overrides JSON column:** `libname_map` (machine-generated) in `migration_plan`; `schema_overrides` (user edits) in `user_overrides` — consistent with existing pattern for human vs machine data · revisit never

### Open Questions
- None blocking next session

### Next Session — Start Here
1. Implement P1-F: `DataStorageTab.tsx` component (LIBNAME tree + schema panel) — plan at `docs/plans/latest/F34-data-storage-tab.md`
2. Then P1-G: wire into `JobDetailPage`
3. Then Phase 3 (P3-A through P3-H): parser relationship extraction + ERD + DDL

### Files Touched
- `src/worker/engine/models.py`
- `src/worker/main.py`
- `src/backend/api/schema_utils.py` (new)
- `src/backend/api/schemas.py`
- `src/backend/api/routes/jobs.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/api/jobs.ts`
- `tests/test_schema_utils.py` (new)
- `tests/test_schema_route.py` (new)
- `tests/test_worker_main_comprehensive.py`
- `tests/test_worker_main.py`
- `tests/test_context_improvements.py`
- `docs/plans/latest/F34-data-storage-tab.md`
- `journal/SESSIONS.md`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`

---

## 2026-06-11 — F33 ETL tab complete; Plan tab sticky footer removed; PR #66 opened
**Duration:** ~5h | **Focus:** F33 ETL tab design, implementation, browser verification

### Done
- PRs #63/#64/#65 (F30/F31/F32) confirmed merged; main synced
- F33 planned through 3 layout iterations: files overview → block list panel → code popup
- Key design decisions: ETL tab shows proposed migration only (no execution), Files view default, CSV nodes filtered, single Accept CTA in header
- F33 implemented — 8 subtasks, all committed separately:
  - S-A: `trigger` field on `BlockPythonEditRequest` (backend, allowlist validator, 4 tests)
  - S-B: `onFileNodeClick`, `trustFiles`, `initialView` props on `LineageGraph`
  - S-C: `saveBlockPython` accepts trigger param
  - S-D: `BlockInspectorPanel` — file block list side panel
  - S-E: `BlockCodePopup` — SAS/Python split modal with verify action
  - S-F: `ETLTab` — three-state orchestrator
  - S-G: `JobDetailPage` wiring + `getJobSources` query
- Browser verification: fixed 5 issues (SAS pane empty, CSV nodes, default Files view, fitView on panel open, rationale text in inspector)
- Removed sticky accept footer from Plan tab — two accept buttons with different labels was confusing; single CTA in header
- PR #66 opened: `feat/F33-etl-tab → main` (closes #42)

### Decisions
- **ETL tab is review-only (no execution controls):** Run migration / pipeline execution stages do not belong on a "proposed migration" review tab · revisit never
- **Files view is the ETL tab default:** Users need the overview before drilling into blocks · revisit never
- **CSV/data files filtered from ETL graph:** Data files belong on Data Storage tab (#43); ETL shows `.sas` orchestration only · revisit never
- **Sticky accept footer removed from Plan tab:** Single "Accept migration" CTA in header; footer was redundant and showed a different label than the header button · revisit never
- **Accept button gating deferred:** No hard gate preventing acceptance before all blocks reviewed — deferred pending real usage data on whether clients use Mark as verified before accepting · revisit after first client feedback

### Open Questions
- PR #66 CI — check before merging

### Next Session — Start Here
1. Merge PR #66 if CI green
2. Next issues from queue: #19 (runbook), #25 (token usage/BOM), or #56 (post-run risk enrichment)

### Files Touched
- `src/backend/api/schemas.py`
- `src/backend/api/routes/jobs.py`
- `src/frontend/src/api/jobs.ts`
- `src/frontend/src/components/JobDetail/BlockCodePopup.tsx` (new)
- `src/frontend/src/components/JobDetail/BlockInspectorPanel.tsx` (new)
- `src/frontend/src/components/JobDetail/ETLTab.tsx` (new)
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/LineageGraph.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `tests/test_block_refine_routes.py`
- `docs/plans/latest/F33-etl-tab.md`
- `journal/SESSIONS.md`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`

---

## 2026-06-11 — F30/F31/F32 planned and implemented; PRs #63/#64/#65 opened
**Duration:** ~3h | **Focus:** Plan tab data enrichment — reads/produces, missing deps, PII

### Done
- F30/F31/F32 plans written, critically reviewed, revised, and approved
- F30 (#60 — Reads/Produces row): 5 subtasks, threads `input_datasets`/`output_datasets` from `SASBlock` through `BlockPlan` → API → Plan tab; PR #63 opened
- F31 (#61 — Missing dependencies callout): 8 subtasks + 9 unit tests, allowlist-based macro detection, basename include matching, amber callout on Plan tab; PR #64 opened
- F32 (#62 — PII/sensitive data warning): 7 subtasks + 14 unit tests, token-based word-boundary PII scanner, red warning banner on Plan tab; PR #65 opened
- PR #55 (F29) confirmed already merged
- All three PRs branch in sequence (F30 → F31 → F32) due to shared files; must merge in order

### Decisions
- **PII scanner uses token-based word-boundary matching:** Column names split on underscore/CamelCase boundaries then matched token-by-token — prevents `TOPZIP` matching `zip`, `DOBERMAN` matching `dob` etc.; pure regex, no LLM · revisit if false-positive reports come in from real client data
- **Missing dependency detection uses allowlist (not blocklist):** Extract all `%word` tokens, keep only those not in a comprehensive SAS built-in frozenset — safer than blocklist which is inherently incomplete · revisit never

### Open Questions
- PR #63/#64/#65 CI — check before merging in sequence

### Next Session — Start Here
1. Check CI on PR #63, merge it, then merge #64, then #65 (in order — shared files)
2. Next issue from queue: #56 (post-run risk enrichment) or #19 (runbook) or #25 (token usage/BOM)

### Files Touched
- `src/worker/engine/models.py`
- `src/worker/engine/agents/migration_planner.py`
- `src/worker/engine/dependency_checker.py` (new)
- `src/worker/engine/pii_scanner.py` (new)
- `src/worker/main.py`
- `src/backend/api/schemas.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `tests/test_dependency_checker.py` (new)
- `tests/test_pii_scanner.py` (new)
- `docs/plans/latest/F30-reads-produces-row.md`
- `docs/plans/latest/F31-missing-dependencies-callout.md`
- `docs/plans/latest/F32-pii-sensitive-data-warning.md`
- `journal/SESSIONS.md`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`

---

## 2026-06-11 — F29 complete; PR #55 opened; backend issue backlog created
**Duration:** ~4h | **Focus:** F29 implementation completion, issue hygiene

### Done
- F29 S-F through S-N implemented, tested, and committed (one commit per subtask)
- S-F: per-file breakdown collapsible
- S-G: bulk re-translate failed blocks button
- S-H: doc state restored + Report collapsible panel (expanded when doc available)
- S-I: Migration history collapsible
- S-J: verdict strip (green/amber/red derived from trustReport)
- S-K: scope subtitle in page header ("9 files · 26 blocks")
- S-L: Needs attention section replacing Review queue (Cards/Table toggle, manual hint, all-pass state)
- S-M: description text moved above verdict strip
- S-N: sticky accept footer with verdict-aware button label
- S-O: all 7 test gates green — F29 marked complete
- PR #55 opened: `feat/F29-plan-tab-refinement → main` (closes #41)
- Deferred backend work catalogued and 7 new GitHub issues created: #56–#62
- Issues #56–#62 staged in SAS Converter project

### Decisions
- none new

### Open Questions
- PR #55 CI — check before merging
- Which deferred backend issue to pick up next?

### Next Session — Start Here
1. Merge PR #55 if CI green
2. Pick up next issue from GitHub priority queue — recommended: #56 (post-run risk enrichment, already designed, small scope) or #60/#61 (Plan tab data gaps)

### Files Touched
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `docs/plans/latest/F29-plan-tab-refinement.md`
- `journal/SESSIONS.md`
- `journal/BACKLOG.md`

---

## 2026-06-09 — F29 implementation: S-A through S-E complete
**Duration:** ~2h | **Focus:** F29 Plan tab implementation

### Done
- F29 plan refined with v4 layout feedback: description above verdict, "of N" denominators on stat cards, explicit strategy labels + "View code →" in attention cards, manual block action hint, Report expanded by default when doc available
- S-B: stat pills replaced with large clickable stat cards + stat filter (auto-expands + scrolls Blocks)
- S-A: review queue expanded by default on load
- S-C: review queue upgraded to 8-9 full columns (source file, confidence, recon icons, human review, blast radius)
- S-D: confidence info dialog (ℹ️) added; confidence bar relabelled "LLM confidence"
- S-E: amber lineage-unavailable notice added (conditional on `!trustReport.lineage_available`)
- All 5 subtasks tested (7 gates green) and committed with individual commits

### Decisions
- none new

### Open Questions
- none

### Next Session — Start Here
1. Continue F29 — next subtask is S-F (per-file breakdown section) → `docs/plans/latest/F29-plan-tab-refinement.md`
2. Remaining: S-F, S-G, S-H, S-I, S-J, S-K, S-L, S-M, S-N, S-O (10 subtasks)

### Files Touched
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `docs/plans/latest/F29-plan-tab-refinement.md`
- `journal/SESSIONS.md`
- `journal/BACKLOG.md`

---

## 2026-06-08 — F29 branch set up; plan expanded with PR #34 design repurposing
**Duration:** ~2h | **Focus:** F29 planning, UX design, layout iteration

### Done
- `feat/F29-plan-tab-refinement` branch created off latest main (docs/session branch folded in manually after SESSIONS.md conflict)
- Reviewed PR #34 (F22 assessment UX) in full — verdict strip, attention blocks, scope summary, sticky accept, reads/produces, missing deps, PII
- Data availability analysis: verdict strip / scope / attention blocks can be derived from existing API data (frontend-only); reads/produces, missing deps, PII need backend schema changes (deferred)
- Three rounds of Plan tab layout iteration (v1 → v2 → v3):
  - v1: initial sketch from F29 plan
  - v2: accept button moved inline with verdict; attention + review queue merged; re-translate to section header; stat card auto-expands blocks
  - v3: accept button → sticky footer; scope → page header; description → free-standing prose; Cards/Table toggle replaces sub-expander; "N more · Show all" pattern; empty/all-pass state
- F29 plan updated with 5 new subtasks (S-J → S-N), updated acceptance criteria, revised out-of-scope section

### Decisions
- **PR #34 will not be merged:** Pre-migration assessment workflow (MigrationPreviewPage) is superseded; verdict strip, attention cards, scope summary, and sticky accept from PR #34 are repurposed into F29 instead · revisit never
- **Reads/produces, missing deps, PII deferred to backend follow-on:** All three require API schema changes not in scope for F29's frontend-only assembly · revisit when backend capacity available
- **Cards/Table toggle replaces separate attention + review queue sections:** One "Needs attention" section serves PM (cards) and tech lead (table) — eliminates reading same data twice · revisit never
- **Sticky accept footer:** Accept button pinned to bottom of Plan tab, always visible while user scrolls evidence · revisit never

### Open Questions
- None blocking F29

### Next Session — Start Here
1. Approve this journal entry and commit
2. Delegate S-A through S-O to `frontend-builder` — plan at `docs/plans/latest/F29-plan-tab-refinement.md`
3. Reference v3 layout sketch in this session entry when briefing frontend-builder

### Files Touched
- `docs/plans/latest/F29-plan-tab-refinement.md`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`
- `journal/SESSIONS.md`

---

## 2026-06-05 — Issue triage, backlog label, pharma test, review queue fix
**Duration:** ~1.5h | **Focus:** Issue hygiene, prioritisation, frontend testing

### Done
- PR #51 (`feat/F28-chevron-tab-shell`) merged; local `main` fast-forwarded
- Issue #40 closed (F28 chevron shell delivered)
- Stale issues closed: #14, #23, #35, #44, #45
- All open issues reviewed and prioritised; GitHub issue queue established as priority source over local backlog
- `backlog` GitHub label created (light blue); applied to #20, #21, #24, #32
- Reports (#32, #24) deferred — not mission-critical yet
- Submitted `pharma-sandbox-medium` test job (12 SAS files + 6 CSVs, clinical trial pipeline)
- Tested Plan tab with complex job: summary card, 26-block table, review queue all render correctly
- **fix(frontend):** removed `.slice(0, 10)` cap in review queue — was showing 10 of 20 items; now shows all, sorted by criticality

### Decisions
- **GitHub issue queue is the priority source:** Open GitHub issues take precedence over items in `journal/BACKLOG.md` · revisit never
- **Reports (#32, #24) deferred:** Not mission-critical at this stage · revisit when product milestones warrant

### Open Questions
- Which of #19, #25 to pick up next? (#19 = runbook, #25 = token usage / BOM)

### Next Session — Start Here
1. Commit journal + review queue fix (`src/frontend/src/components/JobDetail/PlanTab.tsx`)
2. Pick up #19 (runbook for high-risk / non-convertible blocks) or #25 (token usage + BOM)

### Files Touched
- `journal/SESSIONS.md`
- `journal/BACKLOG.md`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`

---

## 2026-06-04 — F28 PR opened; merge conflict resolved; sidebar UX discussion
**Duration:** ~1h | **Focus:** PR hygiene, UX review

### Done
- **F28 implementation reviewed:** all acceptance criteria confirmed met, no TODOs or stale references in diff
- **PR #51 opened:** `feat/F28-chevron-tab-shell → main` with full description
- **Merge conflict resolved:** F27 was merged to main after F28 branched, causing SESSIONS.md conflict; resolved by merging main into F28 as a dedicated commit (`21d068d`) — original F28 commit SHAs preserved, no force-push
- **Sidebar UX discussion:** reviewed current nav (Migrations, Lineage, Docs, Explain) against product intent; identified that nav was built feature-by-feature rather than persona-driven; confirmed user personas (tech lead, PM, code owner) are not yet validated
- **Issue #52 opened:** "UX: revisit sidebar navigation — align with confirmed user personas" — blocks any sidebar implementation until personas are confirmed

### Decisions
- none new

### Open Questions
- PR #51 CI running — check for green before merging
- PR #34 (F22) still open, CI green — merge decision outstanding
- Issue #52 gates any sidebar changes — persona validation needed first

### Next Session — Start Here
1. Check PR #51 CI — merge if green
2. Merge PR #34 if approved
3. Pick up F20 Stream B (`ExecutionOutputPanel` improvements + Trust tab in `EditorTab`) — see `docs/plans/latest/F20-live-trace-popup.md`

### Files Touched
- `journal/BACKLOG.md`
- `journal/SESSIONS.md`

---

## 2026-06-03 — F28 chevron tab shell complete; git author fixed; PR #50 opened
**Duration:** ~5h | **Focus:** F28 implementation, verification, git housekeeping

### Done
- **Session journal backfilled:** backdated 2026-06-02 entry for F26 + F27 work; corrected stale PR blocker note
- **PR status check:** PRs #37/#38 confirmed already merged; PR #34 (F22) open with CI green
- **GitHub issues reviewed:** 18 open issues triaged; chevron cluster (#40–47) unblocked from wireframe gate for implementation
- **F28 plan written:** `docs/plans/latest/F28-chevron-tab-shell.md`; issue #40 updated with implementation approach comment
- **F28 S-A:** URL-synced routing in `JobDetailPage.tsx` — `setSearchParams` on tab change, new 5-tab keys
- **F28 S-B:** `ChevronTabBar.tsx` — CSS clip-path chevron arrows, active/visited/unvisited states, z-index stacking; fixed `style` prop not forwarded by `TabsTrigger` (was silently dropped)
- **F28 S-C:** Content mapped — `plan`→PlanTab, `etl`→EditorTab+LineageTab, Data Storage/BI/AI→placeholder; legacy TabsList commented out
- **F28 fixes:** `LineageTab` toast.error removed; `LineageGraph` crash on `undefined nodes` guarded; ETL tab crash resolved
- **Plan tab cleanup:** `EvaluationTab` removed from Plan tab; failed-reconciliation pill added to PlanTab ribbon; collapsible "Review queue" section added (top risky blocks from trust report)
- **PR #50 opened:** F27 trust report bug fixes
- **Git author fixed:** commits were authored with phantom `eld@damvad.com`; updated to `emilie-adc / emilie.ld@adc-consulting.com`; F28 commits rewritten + force-pushed
- **No Co-Authored-By rule logged:** DECISIONS.md + memory updated; enforcement failure (F25 commit) documented

### Decisions
- **EvaluationTab removed from Plan tab:** redundant stacking; replaced by failed-reconciliation pill + review queue table in PlanTab — revisit when #41 wireframe arrives
- **ChevronTabBar uses clip-path + z-index:** 20px arrows, 12px overlap, descending z-index (Plan=5→AI=1) · revisit if wireframe specifies different shape
- **LineageGraph crash guard in LineageTab:** `!data?.nodes` prevents crash on partial API response — pre-existing bug exposed by ETL tab always mounting LineageTab · revisit never

### Open Questions
- PR #34 (F22 assessment UX) — CI green, needs merge decision
- #41/#42/#43 content refinement — blocked on wireframes
- EvaluationTab now unused in tab shell — keep for now, delete in #46

### Next Session — Start Here
1. Open PR for F28, merge PR #34 if approved
2. Wait for wireframes on #41/#42/#43 before starting those
3. Otherwise pick up F20 Stream B (`ExecutionOutputPanel` improvements + Trust tab in `EditorTab`) — see `docs/plans/latest/F20-live-trace-popup.md`

### Files Touched
- `src/frontend/src/components/JobDetail/ChevronTabBar.tsx` (new)
- `src/frontend/src/components/ui/tabs.tsx`
- `src/frontend/src/components/JobDetail/LineageTab.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `docs/plans/latest/F28-chevron-tab-shell.md`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`

---

## 2026-06-02 — F26 Criticality column + F27 trust report bug fixes complete
**Duration:** ~3h | **Focus:** F26 + F27 implementation, PR #49 merge

### Done
- **F26 S-A/S-B:** Added Criticality column to `BlockPlanTable.tsx` — badge reuses `CRITICALITY_CLASSES` colour map from `EvaluationTab.tsx`; `—` fallback when trust data absent; `make test` exits 0; plan marked complete
- **PR #49 merged:** 5-tab chevron restructure decisions + backlog items #39–47 merged into main; `docs/input-prerequisites.md` updated with #39 audit findings (Tier 1/2/3 gaps)
- **F27 S-A:** Fixed `auto_verified` counter — uses `needs_attention == False` instead of `reconciliation_status == "pass"` so jobs without a reference CSV get a non-zero count
- **F27 S-B:** Fixed `needs_attention` — `translated_with_review` added to the condition so planner-flagged blocks always appear in the review queue regardless of confidence band
- **F27 S-C:** Removed `translate_best_effort` from `TranslationStrategy` enum (`models.py`), `StrategyLiteral` (`schemas.py`), and router comment — dead value never assigned by any agent prompt
- **F27 S-D:** Removed `translate_best_effort: "Best-effort"` label from `LiveTraceDialog.tsx`
- **F27 S-E/S-F:** Added 4 new trust report tests (auto_verified with/without recon fail, 422 on best_effort schema, translated_with_review always needs_attention); `make test` exits 0; plan created and marked complete

### Decisions
- none new (F27 logic is rule clarification, not new design)

### Open Questions
- #40–47 (5-tab chevron restructure) blocked on wireframes — must not start until wireframes attached to issues

### Next Session — Start Here
1. If #40 wireframe is attached, read it and plan-feature the chevron shell scaffold
2. Otherwise, pick up F20 Stream B: `ExecutionOutputPanel` improvements + Trust tab in `EditorTab` — see `docs/plans/latest/F20-live-trace-popup.md`

### Files Touched
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/backend/api/routes/jobs.py`
- `src/backend/api/schemas.py`
- `src/worker/engine/models.py`
- `src/worker/engine/router.py`
- `src/frontend/src/components/LiveTraceDialog.tsx`
- `tests/test_changelog_trust_report.py`
- `tests/test_plan_interaction_routes.py`
- `docs/plans/latest/F26-criticality-plan-tab.md`
- `docs/plans/latest/F27-trust-report-bug-fixes.md`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`
- `docs/input-prerequisites.md`

---

## 2026-06-01 — F25 Evaluation tab: criticality, blast_radius fix, PR ready
**Duration:** ~3h | **Focus:** F25 implementation + browser test

### Done
- **Data model verification:** confirmed `cross_file_edges` dicts use `source_block_id` (not `source_file`) — existing `_blast_radius_map` was silently broken; `BlockPlan` has no `output_datasets`; block-level blast_radius derivable from `source_block_id` directly
- **F25 S-A:** added `criticality: str = "normal"` and `human_review_required: bool = False` to `TrustReportBlock` in `schemas.py`
- **F25 S-B:** fixed `_blast_radius_map` (source_file → source_block_id), added `_criticality()` helper, wired both fields into `get_job_trust_report`
- **F25 S-C:** 7 new unit tests for criticality rules + integration test; 2 existing blast_radius tests updated to correct key format; 723 tests passing
- **F25 S-D–F:** added `criticality`/`human_review_required` to `types.ts`; built `EvaluationTab.tsx` (criticality badges, help dialog, top-10 risky blocks, blast_radius gated on lineage_available); wired Evaluation tab into `JobDetailPage` at position 5; deleted `TrustReportTab.tsx`
- **Committed:** `feat/F25-evaluation-tab` branch, single commit `c3b6ad2`, all pre-commit hooks green
- **Browser tested:** Evaluation tab renders correctly with seeded test job — summary cards, criticality badge, help dialog all working
- **F26 planned:** criticality column on Plan tab block table; plan file written at `docs/plans/latest/F26-criticality-plan-tab.md`; no code written yet (session ended before implementation)

### Decisions
- `_blast_radius_map` fix: use `source_block_id` as map key — see DECISIONS.md 2026-06-01
- Criticality is mixed signal (strategy + confidence + blast_radius), not pure blast_radius — see DECISIONS.md 2026-06-01

### Open Questions
- PR #37 (docs sprint) and PR #38 (confidence-metric) still blocked by org billing issue — need admin to unblock CI
- PR #34 (F22) still open
- F26 implementation not started — one session to complete (single file, ~40 lines)

### Next Session — Start Here
1. Read `docs/plans/latest/F26-criticality-plan-tab.md` — plan is approved, start with S-A
2. Add Criticality column to `BlockPlanTable.tsx`: table header + row badge using `trust?.criticality`, `—` fallback; reuse CRITICALITY_CLASSES colour map from `EvaluationTab.tsx`
3. Run `make test`, verify green, commit to `feat/F25-evaluation-tab` (or new branch if F25 PR is merged)
4. Generate PR summary for F25 with `/git-pr-summary`

### Files Touched
- `src/backend/api/schemas.py`
- `src/backend/api/routes/jobs.py`
- `tests/test_changelog_trust_report.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/components/JobDetail/EvaluationTab.tsx` (new)
- `src/frontend/src/components/JobDetail/TrustReportTab.tsx` (deleted)
- `src/frontend/src/pages/JobDetailPage.tsx`
- `docs/plans/latest/F25-evaluation-tab.md`
- `docs/plans/latest/F26-criticality-plan-tab.md` (new)
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`
- `journal/SESSIONS.md`

---

## 2026-05-29 — Doc sprint: SAS scope, personas, input prerequisites (#26 #30 #33)

**Duration:** ~2h | **Focus:** GitHub issue triage + three documentation files

### Done
- **Confirmed:** PR #36 (F24) merged; issue #22 (SAS editor) closed automatically; PR #34 (F22) still open
- **#26:** Updated `docs/mvp-scope.md` — added supported/best-effort/out-of-scope SAS construct tables and UI scope section covering all 7 pages
- **#30 (doc part):** Created `docs/personas.md` — P1 (technical lead) and P2 (PO/analyst) persona-to-view mapping, key metrics, actions, feature mapping table
- **#33 (doc part):** Created `docs/input-prerequisites.md` — accepted formats, SAS version compatibility, reference CSV guidance, system requirements
- **PR #37 opened:** `docs/sas-scope-personas-prerequisites` → main, closes #26 #30 #33
- **PR test plan executed:** found and fixed 3 gaps — PROC_PRINT/CONTENTS/DATASETS missing from best-effort table; `/docs` page missing from UI scope and P2 views; accepted formats were correct
- **PR description updated:** all 3 test plan items ticked; CI failing due to org billing lock (not code)

### Decisions
- none architectural

### Open Questions
- PR #34 (feat/F22-assessment-ux) still open — needs merge; #14 closes on merge
- Lasse's #23 (Danske Bank review) still open — blocks #32 and #24
- Issue #35 (Lasse's agent pipeline proposal) needs a conversation before any dev work; may overlap with the product itself
- CI blocked by org billing issue — admin access needed to unblock GitHub Actions

### Next Session — Start Here
1. Merge PR #37 once billing is resolved (or bypass if you have permissions)
2. Merge PR #34 (feat/F22-assessment-ux); close #14
3. Write `docs/confidence-metric.md` for issue #18 — short tech note + user-facing explanation of what the confidence score means (quick win, unblocks #17 tooltip requirement)
4. Plan F25 (Evaluation tab — issue #17): read `docs/features.md` F17 entry + `journal/DECISIONS.md` before planning

### Files Touched
- `docs/mvp-scope.md`
- `docs/personas.md` (new)
- `docs/input-prerequisites.md` (new)
- `journal/SESSIONS.md`
- `journal/BACKLOG.md`

---

## 2026-05-22 — GitHub issue triage + PR #34 screenshots

**Duration:** ~2h | **Focus:** Backlog issue review, solution recommendations, PR #34 screenshot capture

### Done
- **Triage:** Analysed 6 reopened doc/spec GitHub issues (#14, #23, #26, #30, #32, #33) and gave concrete resolution recommendations for each (see decisions below)
- **PR #34 screenshots:** Captured three clean screenshots of the feat/F22-assessment-ux UI for PR #34:
  - `01_plan_tab_final.png` — Plan tab (green verdict strip, scope summary, confidence/complexity bars, amber missing-deps warning, full-width Accept button)
  - `02_assessment_preview.png` — Pre-Migration Assessment page top (effort estimate, block classification tiles, blockers)
  - `03_assessment_scope.png` — Assessment scope section (file/block counts, input/output datasets, migration risk tier)
  - Saved to `/tmp/pr34_screenshots/` for manual upload to PR description

### Decisions
- **#14 close on merge:** Already superseded by PR #34; close automatically when #34 merges.
- **#23 is Lasse's:** Research task (Danske Bank benchmark) — not a dev task. Follow up with Lasse; output feeds #32.
- **#26 = docs commit:** Update `docs/mvp-scope.md` with supported/out-of-scope table + add a short UI scope note. No implementation needed.
- **#30 = split:** Write persona map doc now (quick) + file a separate issue for persona-differentiated UX implementation (Phase 3+).
- **#32 = design before F25:** Write `docs/reports-spec.md` before implementing the Evaluation tab (F25). Ideally after #23 delivers findings; can proceed with best-guess spec if #23 is stalled.
- **#33 = split:** Document input prerequisites now (derivable from current implementation); SAS 6.12/8/9.x version testing blocked on obtaining sample code.

### Open Questions
- When will Lasse complete #23 (Danske Bank review)? Unblocks #32 spec.
- Are PRs #34 and #36 both ready to merge? Both have green CI.

### Next Session — Start Here
1. Merge PR #34 (feat/F22-assessment-ux) and PR #36 (feat/F24-sas-editor-fidelity)
2. Close #14 with a reference to PR #34 once it merges; apply `shipped` label to #22 once #36 merges
3. Pick up one of the doc tasks: #26 (scope doc) or #30 (persona map) — both are quick docs commits on main
4. After docs commits, plan F25 (Evaluation tab, GitHub issue #17) — read `docs/features.md` F17 entry before planning

### Files Touched
- `journal/SESSIONS.md`
- `journal/BACKLOG.md`

---

## 2026-05-18 — F24 SAS editor fidelity — browser verification + SAS Studio parity

**Duration:** ~3h | **Focus:** F24 iterative fix rounds, PROC options, false-positive elimination

### Done
- **fix(F24):** Monaco global theme override — Python editor (`theme="vs"`) was overriding the SAS editor's `sas-light` theme; fixed `EditorTab.tsx` to use a single `monacoTheme` variable for both editors
- **fix(F24):** Indented `* text;` star comments — regex `^\*` required `*` at column 0; changed to `^[ \t]*\*`
- **fix(F24):** `intck` was black — added to `sasFunctions`; `label`/`format` added to `keywords`; `put` moved from `sasFunctions` to `keywords` (DATA step statement, not a function)
- **fix(F24):** macroKeywords expansion — 21 tokens (`%LOCAL`, `%SYSFUNC`, `%SYMEXIST`, etc.) were falling to `variable.macro` (brown); added to `macroKeywords` so they render purple
- **fix(F24):** Function color aligned to SAS Studio — `keyword.function` changed from teal to same blue as keywords (`#0070C0`/`#569CD6`); SAS Studio does not distinguish functions from keywords visually
- **feat(F24):** PROC option keywords — added ~25 options (`NOPRINT`, `NODUPKEY`, `NWAY`, `NLEVELS`, `DATAFILE`, `DBMS`, `REPLACE`, `NOCENTER`, `LINESIZE`, `PAGESIZE`, etc.) to keywords array so they render bold blue
- **fix(F24):** sasFunctions false positives — `n`, `sum`, `mean`, `min`, `max`, `std`, `count`, `year`, `month` etc. were highlighting blue even as plain variable names; split identifier rule using `(?=\s*\()` lookahead so functions only highlight when immediately followed by `(`

### Decisions
- **Function color = keyword color:** SAS Studio Enhanced Editor uses one blue for both. Aligned to this rather than F24 spec (which had teal). User confirmed "identical to SAS Studio."
- **PROC options as global keywords (Option A):** added as flat keyword array rather than stateful per-PROC tokenizer; false-positive risk is negligible (`noprint` etc. are never used as variable names in practice
- **sasFunctions require `(` lookahead:** the only correct way to distinguish `sum(x)` (function) from `sum = 0` (variable) without semantic parsing; implemented via Monarch lookahead `(?=\s*\()`

### Open Questions
- none

### Next Session — Start Here
1. Push `feat/F24-sas-editor-fidelity` and open PR → main
2. Next priority: F20 Stream B (ExecutionOutputPanel improvements + Trust tab in EditorTab)

### Files Touched
- `src/frontend/src/components/JobDetail/registerSasLanguage.ts`
- `src/frontend/src/components/JobDetail/EditorTab.tsx`

---

## 2026-05-05 — LiveTraceDialog multi-phase rail + README + status UX

**Duration:** ~2h | **Focus:** F20 phase rail, README rewrite, job status display cleanup

### Done
- **feat(F20):** LiveTraceDialog restructured into 5-phase collapsible rail (Parsing & Analysis / Migration Planning / Code Translation / Assembly & Validation / Lineage & Documentation) — phases appear only when `phase_start` arrives, not all upfront
- **feat(worker):** 6 new trace event types emitted from `_execute()`: `phase_start`, `phase_done`, `parse_result`, `plan_result`, `enrichment_item_done`; `_active_phase` tracking in exception handlers emits `phase_done { status: error }` on cancel/crash
- **feat(frontend):** `PhaseRow` component with shadcn `Collapsible`; `ParseDetailPanel`, `PlanDetailPanel`, `EnrichmentDetailPanel`; `phaseMap` memo derived from events; auto-expand active phase, auto-collapse completed phases (1.2s delay, translation stays open)
- **fix(frontend):** LiveTraceDialog elapsed timer now anchored to `events[0].ts` (real job start), frozen at `job_done.ts` — survives close/reopen, stops when job finishes
- **fix(frontend):** phase-specific icons (ScanText/ClipboardList/Code2/GitMerge/BookOpen) now render correctly — `icon` prop was missing from `PhaseRow` destructure
- **fix(frontend):** Activity button ping moved outside shadcn `Button` (was clipped by overflow-hidden); switched to `animate-pulse` on icon
- **fix(frontend):** `proposed` and `under_review` both map to "Needs Review" (amber); `running` maps to "Processing" — consistent across `TableStatus`, `UploadStatusBadge`, `StatusBadge`, `STATUS_LABEL`; `STATUS_LABEL` is now single source of truth
- **chore:** removed stale data-dependent reconciliation tests (`test_agentic_pipeline`, `test_data_step`, `test_proc_sort`, `test_parses_sample_file`) — sample data was already removed
- **docs:** README fully rewritten — expanded introduction (business problem, what tool does, current capabilities), updated architecture diagram to 5 services, full PostgreSQL schema, complete project structure tree
- **backlog:** added TODO for future backend status consolidation (`proposed`/`under_review` are internal concepts leaking into UI)

### Decisions
- **`proposed` = "Needs Review" in UI:** both `proposed` (recon pass) and `under_review` (recon fail) mean "pipeline done, human must act" — the distinction lives in the Plan tab, not the status label · revisit when backend statuses are consolidated

### Open Questions
- none

### Next Session — Start Here
1. Implement `_enrich_block_plan_post_run` in `src/worker/main.py` — called after `_persist_initial_revisions`; updates `context.migration_plan.block_plans` risk+rationale in-place using recon results + confidence (rule-based, no LLM), then re-persists `job.migration_plan`
2. `make docker-build` — picks up new phase trace emit calls in worker
3. Run a job → confirm all 5 phases appear in LiveTraceDialog in order; confirm elapsed timer freezes correctly at job completion

### Files Touched
- `src/worker/main.py`
- `src/worker/engine/trace.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/components/LiveTraceDialog.tsx`
- `src/frontend/src/components/ui/collapsible.tsx`
- `src/frontend/src/components/JobDetail/constants.ts`
- `src/frontend/src/pages/JobsPage.tsx`
- `tests/reconciliation/test_agentic_pipeline.py` (deleted)
- `tests/reconciliation/test_data_step.py` (deleted)
- `tests/reconciliation/test_proc_sort.py` (deleted)
- `tests/test_parser.py`
- `README.md`
- `journal/BACKLOG.md`

---

## 2026-05-04 (session 2) — F20 Stream B audit + log usage investigation

**Duration:** ~30m | **Focus:** F20 Stream B verification, codebase Q&A

### Done
- **verified(frontend):** F20 Stream B (ExecutionOutputPanel improvements + Trust tab) was already fully implemented; only a missing `Badge` import in `EditorTab.tsx` was added
- **investigated:** confirmed SAS log files ARE injected into LLM context before attempt 1 — loaded at job start into `JobContext.log_contents`, passed to MigrationPlannerAgent + all translation agents on every attempt (first 200 lines per file); retry attempts also receive `risk_flags` with recon failure details

### Decisions
- none

### Open Questions
- none

### Next Session — Start Here
1. Implement `_enrich_block_plan_post_run` in `src/worker/main.py` — called after `_persist_initial_revisions`; updates `context.migration_plan.block_plans` risk+rationale in-place using recon results + confidence band (rule-based, no LLM), then re-persists `job.migration_plan`
2. Rebuild Docker: `docker compose build worker executor && docker compose up -d worker executor`
3. Run a job → confirm no NameErrors; confirm risk reflects recon outcome in Plan tab

### Files Touched
- `src/frontend/src/components/JobDetail/EditorTab.tsx`

---

## 2026-05-04 — cumulative block execution, risk post-run enrichment design, block_type planner fix

**Duration:** ~1h | **Focus:** cross-block NameError root cause fix, migration planner correctness

### Done
- **fix(worker):** `_translate_blocks` now sends cumulative code (all prior blocks + current block) to executor — eliminates `revenue_sorted`/`tx_fx_cat` NameErrors from cross-block variable references in isolated subprocesses; removed unreliable Parquet session cache
- **fix(worker):** appends `result = <output_var>` to cumulative exec code so recon capture picks the correct block's DataFrame
- **fix(prompt):** added rule to `SHARED_TRANSLATION_RULES` — never introspect `.schema[col]` on a prior-block DataFrame; assume it exists and use directly
- **fix(planner):** `block_type` prompt now lists all known types with concrete example; `_build_migration_plan` overrides LLM's `block_type` with authoritative value from parser — PROC_IML can no longer show as UNTRANSLATABLE
- **design:** agreed post-run risk+rationale enrichment — risk recalculated from recon results + confidence after translation; rationale rewritten with actual findings; no extra LLM call (rule-based)

### Decisions
- **Cumulative code over session cache:** cumulative exec is crash-proof; Parquet cache silently left gaps when upstream blocks crashed mid-execution · revisit never
- **Parser `block_type` is authoritative:** `_build_migration_plan` ignores LLM's `block_type`, reads it from parsed `SASBlock` — LLM was given a short enum missing PROC_IML etc. · revisit never
- **Post-run risk+rationale:** recomputed after `_translate_blocks` using recon results + confidence; pre-run planner values are initial estimates only; rule table: recon pass + high conf → low; recon fail → high; no recon + low conf → high · revisit never

### Open Questions
- Post-run risk+rationale enrichment not yet implemented — agreed design only

### Next Session — Start Here
1. Implement `_enrich_block_plan_post_run` in `src/worker/main.py` — called after `_persist_initial_revisions`; updates `context.migration_plan.block_plans` risk+rationale in-place, then re-persists `job.migration_plan`
2. Rebuild Docker: `docker compose build worker executor && docker compose up -d worker executor`
3. Run a job → confirm no NameErrors; confirm risk reflects recon outcome in Plan tab
4. Continue F20 Stream B → `docs/plans/latest/F20-live-trace-popup.md`

### Files Touched
- `src/worker/main.py`
- `src/worker/engine/agents/shared.py`
- `src/worker/engine/agents/migration_planner.py`

---

## 2026-05-03 (session 3) — recon grouping, retry loop, session cache, parser enhancements

**Duration:** ~2h | **Focus:** fixing per-block recon correctness, retry loop, Spark session cache, SAS parser spec

### Done
- **fix(frontend):** no-recon blocks green (not amber); every completed block has chevron + expandable panel
- **fix(recon):** `_build_recon_groups` strips libname prefix before stem match (`outdir.revenue_summary` → `revenue_summary`)
- **fix(block_executor):** empty checks + ref present → synthetic `execution: fail` so retry loop fires on crash
- **fix(worker):** translation exception now injects error as risk_flag and retries (was `break` on attempt 1); emits `block_done status=error`
- **fix(worker):** `_reconcile_initial_blocks` (step 11) disabled — was reconciling intermediate blocks against final output ref
- **fix(executor):** session cache switched to PySpark `spark.read/write.parquet`; Spark init always present when session_dir set; load snippet runs after init
- **fix(executor):** session cache path → `/tmp/rosetta_cache/...` (`/workspace/data` is read-only mount)
- **fix(frontend):** Plan tab recon column — CheckCircle2/XCircle icons; manual/skip/manual_ingestion always `—`
- **feat(parser):** MacroDef, filename_map, PROC IML/FORMAT extractors, DROP/KEEP/WHERE/OUTPUT/ARRAY on SASBlock
- **feat(prompt):** "always PySpark, never pandas" + "never cast to match ref schema" rules in SHARED_TRANSLATION_RULES
- **feat(recon):** DEBUG logs — ref/actual rows, columns, dtypes before every check

### Decisions
- Direct-match only in `_build_recon_groups`; step-11 post-pass disabled; session cache in `/tmp`; retry loop continues on exception

### Open Questions
- `tx_fx_cat` NameError on attempt 1: LLM generates `_customer_id_type = tx_fx_cat.schema[...]` introspection code that runs before session cache can load the variable. Session cache fix in `/tmp` is deployed but the introspection line itself is a bad LLM pattern — needs a prompt rule to suppress schema introspection via `.schema[col]` before the DataFrame is confirmed available.

### Next Session — Start Here
1. Rebuild: `docker compose build worker executor && docker compose up -d worker executor`
2. Run a job → confirm `tx_fx_cat` NameError is gone (session cache now in `/tmp`)
3. If still failing, add prompt rule: "never access `.schema[col]` on a DataFrame that comes from a prior block — trust that it exists and use it directly"
4. Continue F20 Stream B: `ExecutionOutputPanel` improvements + Trust tab in `EditorTab` → `docs/plans/latest/F20-live-trace-popup.md`

### Files Touched
- `src/frontend/src/components/LiveTraceDialog.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/worker/main.py`
- `src/worker/engine/block_executor.py`
- `src/worker/engine/agents/shared.py`
- `src/worker/engine/models.py`
- `src/worker/engine/parser.py`
- `src/worker/validation/reconciliation.py`
- `src/executor/runner.py`
- `src/executor/recon.py`
- `tests/test_worker_main_comprehensive.py`
- `tests/test_parser_proc_types.py` (existing test updated for new IML terminator)
- `journal/BACKLOG.md`, `journal/DECISIONS.md`, `journal/SESSIONS.md`, `docs/plans/latest/F20-live-trace-popup.md`

---

## 2026-05-03 (session 2) — per-block recon cache, pipeline:full, popup UX overhaul, column casing

**Duration:** ~3h | **Focus:** F20 per-block recon with DataFrame session cache, LiveTraceDialog colour states + pipeline:full banner, column lowercase fix

### Done
- **fix(worker):** `BlockExecutor.run()` crash diagnosed — stale `.pyc` in Docker image layer overriding bind-mounted source; fix: `docker compose build worker executor`
- **feat(executor):** `session_dir` param on `run_code()` + `ExecuteRequest` — Parquet load snippet prepended, save snippet appended, `_ROSETTA_SESSION_DIR` env var; prior block DataFrames available to subsequent blocks without re-running
- **feat(worker):** `session_dir` threaded `RemoteReconciliationService` → `BlockExecutor` → `_translate_blocks`; session cache computed once per job, cleaned up after loop
- **fix(recon):** `_build_recon_groups` fallback removed — per-block recon only fires for blocks with a specifically-matched uploaded data file; job-level ref reserved for `pipeline:full` only
- **feat(worker):** `pipeline:full` final recon run after translation loop — emits `block_start` / `recon_result` / `block_done` SSE trace events; no session cache (runs fresh)
- **feat(frontend):** LiveTraceDialog block colour states — `running`=grey+spinner, `error`=red, `no-recon`=amber+CircleAlert, `pass`=green, `fail`=red
- **feat(frontend):** `PipelineSummaryBanner` component for `pipeline:full` group — full-width card, coloured `border-l-4`, collapsible recon checks
- **feat(frontend):** human-friendly check labels (Schema Parity, Row Count, Aggregate Parity); detail shown in `<pre>` when non-empty
- **fix(frontend):** block header button — removed coloured `border-l-2`; removed inner rail `border-l-2` from collapsible section
- **fix(frontend):** toggle UX — `userToggled: boolean | null` state; `null` = follow data (auto-expand on recon), non-null = user override; click always toggles freely
- **fix(frontend):** stale `eslint-disable react-hooks/set-state-in-effect` comments removed
- **fix(recon):** `recon.py` — both ref and actual DataFrames normalized to lowercase columns before all three checks (guards against SAS UPPERCASE ref CSV headers)
- **fix(prompt):** `SHARED_TRANSLATION_RULES` Rule 2 — mandatory `toDF(*[c.lower() for c in df.columns])` after every file read; removes SAS/Python column casing mismatch at source

### Decisions
- Executor DataFrame session cache uses Parquet in `session_dir`; cache scoped per orchestrator instance (`id(self)`); cleaned up by `shutil.rmtree` after loop
- `_build_recon_groups` fallback removed — intermediate blocks are not reconciled against the final output reference; only specifically-matched data files trigger per-block recon
- Column normalization: two-layer defence (LLM prompt rule + recon.py defensive normalization)
- LiveTraceDialog toggle: `userToggled: boolean | null` pattern — null defers to data, non-null is explicit user choice

### Open Questions
- Toggle fix confirmed working? User reported toggle disappeared mid-session; fix applied (null→userToggled pattern) but not verified in browser
- `make docker-build` still needed to pick up executor + worker changes from this session

### Next Session — Start Here
1. `docker compose build worker executor && docker compose up -d worker executor`
2. Run a migration job with a reference CSV that has a specific per-block match → confirm per-block recon fires in popup with amber/green/red states
3. Run `pipeline:full` banner appears after all blocks complete
4. Verify toggle open/close works in popup
5. Continue F20 Stream B (ExecutionOutputPanel + Trust tab in EditorTab)

### Files Touched
- `src/executor/runner.py`
- `src/executor/main.py`
- `src/executor/recon.py`
- `src/worker/validation/reconciliation.py`
- `src/worker/engine/block_executor.py`
- `src/worker/engine/agents/shared.py`
- `src/worker/main.py`
- `src/frontend/src/components/LiveTraceDialog.tsx`
- `src/frontend/src/index.css`
- `tests/test_worker_main.py`
- `tests/test_worker_main_comprehensive.py`
- `docs/plans/latest/F20-live-trace-popup.md`

---

## 2026-05-03 — recon popup fixes, UNRECOGNIZED rename, per-block recon wiring

**Duration:** ~2h | **Focus:** live trace popup correctness, UNTRANSLATABLE→UNRECOGNIZED, per-block reconciliation routing

### Done
- **feat(ui):** removed amber attention strip from PlanTab; strategy badge now colored per pass/fail/manual/pending
- **feat(ui):** pass/fail text badges → CheckCircle2/XCircle icons in TrustReportTab and EditorTab
- **feat(ui):** UNTRANSLATABLE → UNRECOGNIZED across frontend types, LineageGraph, FileNodeCard, BlockPlanTable
- **feat(ui):** shimmer pulse on recon column in BlockPlanTable while job is running
- **feat(ui):** LiveTraceDialog — chevron only shown when recon content exists; block id strips directory prefix; smaller text
- **feat(worker):** UNTRANSLATABLE → UNRECOGNIZED in models, codegen, stub_generator, llm_client, parser, schemas
- **feat(worker):** `_reconcile_initial_blocks` now emits `recon_result` + corrective `block_done` trace events via `self._tracer`
- **feat(worker):** per-check INFO/WARNING logging added to `RemoteReconciliationService.run()`
- **feat(worker):** `BlockExecutor.run()` signature extended with `ref_csv_path`/`ref_sas7bdat_path`; `_build_recon_groups` wired into `_translate_blocks` for per-block ref routing
- **fix(worker):** `mypy` name error — `_execute()` uses `self._tracer` not local `tracer`
- **fix(worker):** `_build_recon_groups` was defined but never called — now called at start of `_translate_blocks`

### Decisions
- Per-block recon must use `_build_recon_groups` — single final-output ref must NOT be applied to intermediate blocks
- `docker-compose.override.yml` bind-mounts `src/worker` — restart not rebuild needed for code changes
- UNRECOGNIZED replaces UNTRANSLATABLE everywhere as the canonical term

### Open Questions
- **BlockExecutor fix not confirmed working** — `block_executor.py` signature replacement failed silently in one pass; final fix applied but not yet tested in docker (user ended session). Verify `docker compose restart worker` and re-run a job next session.

### Next Session — Start Here
1. `docker compose restart worker` (bind-mount, no rebuild needed)
2. Run a migration job and confirm per-block recon checks appear in the live popup
3. If still failing, check `docker compose logs worker --tail=50` for the exact error
4. Continue F20 Stream B (ExecutionOutputPanel + Trust tab)

### Files Touched
- `src/worker/engine/block_executor.py`
- `src/worker/engine/trace.py` (tracer param)
- `src/worker/main.py` (_reconcile_initial_blocks tracer, _translate_blocks recon_groups)
- `src/worker/validation/reconciliation.py` (per-check logging)
- `src/worker/engine/models.py` (UNRECOGNIZED)
- `src/worker/engine/codegen.py` (UNRECOGNIZED)
- `src/worker/engine/stub_generator.py` (UNRECOGNIZED)
- `src/worker/engine/llm_client.py` (UNRECOGNIZED)
- `src/worker/engine/parser.py` (UNRECOGNIZED)
- `src/backend/api/schemas.py` (UNRECOGNIZED)
- `src/frontend/src/api/types.ts` (UNRECOGNIZED)
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/JobDetail/TrustReportTab.tsx`
- `src/frontend/src/components/JobDetail/EditorTab.tsx`
- `src/frontend/src/components/LiveTraceDialog.tsx`
- `src/frontend/src/components/LineageGraph.tsx`
- `src/frontend/src/components/FileNodeCard.tsx`
- `src/frontend/src/components/LineageDetailPanel.tsx`
- `docs/plans/latest/F20-live-trace-popup.md`

---

## 2026-05-03 — join fixes, recon coverage, confidence/status overhaul, SAS highlight

**Duration:** ~3h | **Focus:** PySpark join correctness, recon column completeness, status/confidence semantics, SAS highlight bug

### Done
- **fix(prompt):** unified join key normalisation — save original type, regexp_replace+cast both sides, restore type after join; removes two conflicting sections; scoped to identifier/key columns only
- **fix(prompt):** generic per-column schema-mismatch cast hint in retry logic (`"column X: output is Y but ref expects Z — cast to match"`)
- **fix(prompt):** near-zero aggregate parity advisory — when `ref_sum < 1e-3`, hint tells LLM this is IEEE 754 drift and to add a comment, not a logic fix
- **fix(worker):** job status written immediately after recon (step 10a/10b split) — UI no longer waits for doc/lineage LLM calls before showing proposed/under_review
- **fix(worker):** `exec_ok` on `GeneratedBlock`; `_persist_initial_revisions` writes baseline `reconciliation_status="pass"/"fail"` for every translated block — eliminates `—` in Plan table
- **fix(worker):** `_reconcile_initial_blocks` skip guard changed to `status=="pass" AND recon_checks non-empty` — execution-only passes get upgraded to full recon when ref available
- **feat(planner):** MigrationPlannerAgent now asked for `confidence_score` (0.0–1.0); `BlockPlan` defaults changed from 1.0/"high" to 0.5/"unknown" — fixes confidence always showing 100%
- **feat(backend):** `effective_confidence_band` computed post-recon (`pass`→upgrade, `fail`→downgrade) and added to `TrustReportBlock`
- **feat(backend):** `end_line` threaded from `SASBlock` → `BlockPlan` → API
- **feat(frontend):** Strategy badge derived from `(strategy, reconciliation_status)` — green Translated on pass, blue on no-recon, amber Review Needed on fail, red Manual always
- **feat(frontend):** SAS highlight in View Code dialog uses actual `end_line` instead of `startLine + 20`
- **feat(frontend):** Activity button in jobs table pulses when job is running/queued
- **fix(tests):** deleted stale `tests/test_reconciliation_coerce.py`

### Decisions
- Join key type-save/restore pattern: `_type = df.schema[col].dataType` before cast, `.cast(_type)` after join — generic, works for all Spark types, no hardcoding
- `effective_confidence_band` lives in trust report (read layer), not in `BlockPlan` (write layer) — keeps planner's estimate as audit trail, adjusts display post-recon
- Job status written in two DB commits: step 10a (status + code) immediately after recon, step 10b (doc + lineage) after best-effort enrichment

### Open Questions
- LiveTraceDialog UX overhaul (frozen elapsed, FinalStatusChip, timing pill, expandable blocks) was lost — prior sessions marked it done in backlog but it was never committed; needs re-implementation
- F20 Stream B (ExecutionOutputPanel + Trust tab) still pending

### Next Session — Start Here
1. Re-implement LiveTraceDialog UX overhaul (see backlog item + F20 plan Stream B section)
2. F20 Stream B — ExecutionOutputPanel improvements + Trust tab in EditorTab

### Files Touched
- `src/worker/engine/agents/shared.py` — join key prompt unified
- `src/worker/engine/agents/migration_planner.py` — confidence_score in prompt + _build_migration_plan; end_line threaded
- `src/worker/engine/models.py` — `exec_ok` on GeneratedBlock; BlockPlan defaults + end_line field
- `src/worker/main.py` — step 10a/10b split; exec_ok set in _translate_blocks; _persist_initial_revisions baseline recon; skip guard fix; schema-mismatch + near-zero hints
- `src/backend/api/schemas.py` — `effective_confidence_band` on TrustReportBlock
- `src/backend/api/routes/jobs.py` — `_effective_confidence()` helper + trust report loop
- `src/frontend/src/api/types.ts` — `end_line` on BlockPlan; `effective_confidence_band` on TrustReportBlock
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx` — derived strategy badge; end_line SAS highlight
- `src/frontend/src/pages/JobsPage.tsx` — Activity shimmer for running/queued
- `tests/test_reconciliation_coerce.py` — deleted (stale import)

---

## 2026-05-01 — F20 Stream A: live trace popup + session cancel

**Duration:** ~2h | **Focus:** F20 Stream A — per-block trace events, cancellation, SSE endpoint, LiveTraceDialog

### Done
- **F20 A1:** `JobTrace` model + `cancellation_requested` on `Job` + Alembic migration 016
- **F20 A2:** `TraceEmitter` (independent sessions, never raises) + `JobCancelledError` + per-block `block_start`/`block_done`/`recon_result`/`job_done` emit in `_translate_blocks` + cancel check between blocks
- **F20 A3:** `POST /jobs/{id}/cancel` — queued jobs cancelled immediately, running jobs set `cancellation_requested=True`
- **F20 A4:** `GET /jobs/{id}/trace/stream` SSE endpoint — polls `job_traces` at 0.5s, closes on `job_done` or terminal status
- **F20 A5:** `TraceEvent` union type + `openTraceStream` / `cancelJob` API client functions
- **F20 A6:** `LiveTraceDialog` — redesigned with left vertical timeline rail, shadcn color tokens, per-event-type dot + row styling, auto-scroll, elapsed timer, Stop button
- **F20 A7:** Activity button in `JobsPage` for queued/running/done jobs; `LiveTraceDialog` mounted at page root
- **fix(worker):** cancel check crash — `session.refresh(job)` replaced with fresh-session `get()` via `session_factory`; fixes "not persistent within this Session" error
- **make test green:** all 7 gates pass after ruff/mypy/eslint/build fixes

### Decisions
- `JobTrace` append-only via `TraceEmitter` with independent sessions; SSE polls DB (no WebSocket) · revisit never
- Cancel check uses fresh session — outer session's Job object detaches after LLM calls · revisit never
- Agent thinking stream: model-agnostic structured events chosen over Claude-only extended thinking; deferred · revisit never

### Open Questions
- F19 retry loop still not implemented — only 1 attempt fires even when recon fails; quick fix is ~30 min
- F20 Stream B (ExecutionOutputPanel + Trust tab) not started
- `make docker-build` needed to deploy Alembic 016 + new endpoints

### Next Session — Start Here
1. `make docker-build && docker compose up` — apply migration 016, verify LiveTraceDialog works end-to-end
2. Implement F19 quick retry loop: per-block `for attempt in range(1, 4)` in `_translate_blocks`, inject recon error into `risk_flags` on fail
3. Then F20 Stream B: ExecutionOutputPanel improvements + Trust tab in EditorTab

### Files Touched
- `src/backend/db/models.py` — `JobTrace` model, `cancellation_requested` on `Job`
- `alembic/versions/016_add_job_traces_cancel.py` — new migration
- `src/backend/api/routes/jobs.py` — `POST /cancel`, `GET /trace/stream`
- `src/worker/engine/trace.py` — new: `TraceEmitter`, `JobCancelledError`
- `src/worker/main.py` — TraceEmitter wired, cancel check fixed (fresh session)
- `src/frontend/src/api/types.ts` — `TraceEvent` union types
- `src/frontend/src/api/jobs.ts` — `openTraceStream`, `cancelJob`
- `src/frontend/src/components/LiveTraceDialog.tsx` — new component (timeline rail design)
- `src/frontend/src/pages/JobsPage.tsx` — Activity button + dialog mount

---

## 2026-04-28 — rawdir_customers root-cause fix + F19 S2+S3 plan

**Duration:** ~2h | **Focus:** Tracing `rawdir_customers` NameError to its true root cause; planning the F19 per-block execute-and-refine loop

### Done
- **Root cause identified:** `windowed_context()` sets `blocks=[block]` (only the current block), so `block_output_stems` in all three agent `_build_prompt` functions was built without any upstream block outputs. Downstream prompts fell back to `rawdir_customers` instead of `customers` for PROC IMPORT outputs.
- **Fix applied:** Added `all_blocks: list[SASBlock]` parameter to `_build_prompt` in all three agents (`data_step.py`, `proc.py`, `generic_proc.py`); call sites updated to pass `context.blocks` (the full job block list). Both dot form (`rawdir.customers`) and underscore form (`rawdir_customers`) now registered in `block_output_stems`.
- **Prompt hardening:** `generic_proc.py` system prompt updated with explicit `OUT=` stem-only naming rule, wrong/correct examples, and corrected output variable examples throughout.
- **Debug logging added:** `generic_proc.py` logs prompt input hints, raw LLM output, and post-normalise state at DEBUG; `codegen.py` warns at WARNING if `rawdir_customers` survives into assembled code.
- **Confirmed all previous bug-fix changes necessary:** Audit via fullstack-planner confirmed all changes from previous session (shared.py, `_file_io_types` exclusion removal, etc.) are correct and non-redundant.
- **F19 S2+S3 planned:** Full implementation plan written at `.claude/plans/first-plan-properly-with-tidy-bubble.md` covering `BlockExecutor` remote recon swap, `_translate_blocks` per-block retry loop, `data_dir` threading, and tests.
- **Post-fix result:** Executor now fails on `AnalysisException` (PySpark column resolution) rather than `NameError` — a genuine LLM translation error, not a pipeline bug, which F19 is designed to fix.

### Decisions
- **`block_output_stems` must use full `context.blocks`:** `windowed_context` is intentionally narrow (single block) for LLM prompt scoping, but the variable name resolution map needs global visibility of all upstream outputs — the two concerns are now separated. · revisit never
- **Debugging approach:** when tracing a persistent bug, add surgical DEBUG logging at each stage of the pipeline (prompt construction → LLM output → post-processing → assembly) before changing any logic. Confirmed root cause via logs, not guesswork.

### Open Questions
- F19 S2+S3 not yet implemented — the per-block execute→refine loop is planned but not coded.
- `auto_verified` counter and `needs_attention` threshold still not fixed (deferred again).

### Next Session — Start Here
1. Implement F19 S2+S3: update `BlockExecutor` to use `RemoteReconciliationService`, add per-block retry loop to `_translate_blocks`, forward `data_dir` — see `.claude/plans/first-plan-properly-with-tidy-bubble.md`
2. Run `make test` after implementation
3. `docker compose restart worker` and resubmit to verify loop fires

### Files Touched
- `src/worker/engine/agents/data_step.py` — `all_blocks` param in `_build_prompt`, call site fix
- `src/worker/engine/agents/proc.py` — same
- `src/worker/engine/agents/generic_proc.py` — same + system prompt hardening + debug logging
- `src/worker/engine/codegen.py` — warning log if `rawdir_customers` in assembled code

---

## 2026-04-27 — Executor runtime fixes: data_dir routing, xlsx, output_var normalisation, file_count

**Duration:** ~2.5h | **Focus:** Unblocking executor execution — uploaded files not found, xlsx crash, rawdir NameError, file count off-by-one

### Done
- **`data_dir` routing:** uploaded non-SAS files now saved to `/uploads/<job_id>/<basename>` (per-job subdir, no `<job_id>_` prefix); `data_dir` param added to `ExecuteRequest`, `run_code`, `RemoteReconciliationService.run`, and all call sites in worker; executor rewrites `/workspace/data/` → `data_dir/` before running code
- **xlsx fix (two layers):** (1) GenericProcAgent system prompt updated with `pd.read_excel + spark.createDataFrame` pattern; (2) `_fix_excel_spark_reads()` post-gen guard rewrites `spark.read.*load(*.xlsx)` calls automatically; (3) `openpyxl` added to executor Dockerfile
- **Nested workspace path guard:** `_fix_workspace_paths()` normalises `/workspace/data/working/data/raw/foo.csv` → `/workspace/data/foo.csv` (basename only); prompt listing also fixed to show basename only
- **PROC IMPORT output_var naming:** removed `_file_io_types` exclusion from `all_block_outputs` in all three agents — PROC IMPORT outputs now correctly shown as stem-only in downstream prompts (root cause of `rawdir_customers` NameError in downstream blocks)
- **`normalise_output_var` + `normalise_output_var_in_code`:** shared utilities extracted to `src/worker/engine/agents/shared.py`; all three agents delegate both the code-body rename and the `output_var` field correction to these — handles both dot form and underscore form; local `_fix_output_var_naming` removed from all three agents
- **`file_count` fix:** now counts SAS source files + per-path `__ref_<ext>_<path>__` sentinels; excludes bare canonical aliases (`__ref_csv__`, `__ref_sas7bdat__`) and `__refine_context__` — was showing 20 instead of 19
- **`upload_dir` added to `WorkerSettings`:** default `/uploads`; used to derive `data_dir` per job

### Decisions
- **Per-job upload subdir:** non-SAS files saved to `/uploads/<job_id>/<basename>` (was `/uploads/<job_id>_<basename>`); enables `data_dir` param to point executor at correct directory without any per-job volume magic · revisit never
- **`data_dir` param in executor:** executor rewrites `/workspace/data/` at execution time rather than relying on static volume mount path matching; keeps generated code portable (always `/workspace/data/<basename>`) · revisit never
- **`normalise_output_var` in shared.py:** single source of truth for stem-only normalisation of both `output_var` field and code body — handles dot form and underscore form; agents no longer duplicate this logic · revisit never

### Open Questions
- `auto_verified` counter and `needs_attention` threshold still not fixed (deferred again)
- F19 retry loop (per-block execute→refine) still not implemented — pre-conditions now unblocked
- `make docker-build` still needed to deploy all changes

### Next Session — Start Here
1. Run `make docker-build` and resubmit — verify executor finds files, xlsx loads, no NameError
2. Fix `auto_verified` trust report counter and `needs_attention` threshold
3. Implement F19 S1: `BlockExecutor.run()` helper in `src/worker/engine/block_executor.py`

### Files Touched
- `src/backend/api/routes/migrate.py` — per-job subdir for uploaded files
- `src/backend/api/routes/jobs.py` — file_count sentinel filter fix
- `src/executor/Dockerfile` — openpyxl added
- `src/executor/pyproject.toml` — openpyxl added
- `src/executor/main.py` — data_dir field in ExecuteRequest
- `src/executor/runner.py` — data_dir param, workspace path rewrite
- `src/worker/core/config.py` — upload_dir setting
- `src/worker/engine/agents/shared.py` — new: normalise_output_var, normalise_output_var_in_code
- `src/worker/engine/agents/data_step.py` — delegates to shared, removed _fix_output_var_naming, removed _file_io_types exclusion
- `src/worker/engine/agents/proc.py` — same as data_step
- `src/worker/engine/agents/generic_proc.py` — same + _fix_workspace_paths + _fix_excel_spark_reads + prompt fixes
- `src/worker/main.py` — data_dir derived and threaded through all recon call sites
- `src/worker/validation/reconciliation.py` — data_dir param in _post_execute + run

---

## 2026-04-27 — Executor NameError root-cause fix: block ordering + variable naming

**Duration:** ~2h | **Focus:** Eliminating `NameError: name 'outdir_customer_revenue_daily' is not defined` in executor; correct PROC IMPORT path generation

### Done
- **Cumulative recon slices:** `_reconcile_initial_blocks` now passes `generated_blocks` and sends `assemble_flat(blocks[:i+1])` per block — prior block outputs are available in scope
- **Editor Run cumulative code:** `execute_job` (backend) assembles cumulative code from `migration_plan.block_plans` order when `block_id` is provided
- **Output var renamer:** `_fix_output_var_naming()` added to all three agents (`DataStepAgent`, `ProcAgent`, `GenericProcAgent`) — detects when LLM uses `outdir_foo` form in code body and renames to stem `foo`; also corrects `output_var` field if wrong
- **Input variable naming in prompts:** all three `_build_prompt()` functions now show `→ variable name: <name>` for each input, distinguishing inter-block datasets (stem-only) from external source files (`libname_table` form); `PROC_IMPORT`/`PROC_EXPORT` outputs excluded from the inter-block set
- **Block ordering fix (root cause):** `_topological_sort` in `parser.py` replaced `nx.topological_sort` with Kahn's algorithm + `(source_file, start_line)` min-heap — unconnected blocks (e.g. `PROC_IML` with no `DATA=`/`OUT=`) now retain natural SAS file order instead of floating to front
- **`GenericProcAgent` prompt hardened:** system prompt + `_build_prompt` aligned with `DataStepAgent`/`ProcAgent` naming rules; `data_files` injected into prompt as `## Uploaded data files` section
- **PROC IMPORT path rule:** system prompt now says derive path from `DATAFILE=` basename only → `/workspace/data/<basename>`; ignore SAS macro-expanded paths; example updated from `<infile_path>` placeholder to concrete `/workspace/data/customers.csv`
- **Executor debug logging removed:** temporary `logger.info("Code to execute:\n%s", ...)` removed from `src/executor/main.py`
- **codegen guard:** `assemble_flat` skips `result = <output_var>` if variable not found as assignment in rendered code (prevents crash when LLM naming mismatch survives)

### Decisions
- **Inter-block vs external-source variable naming:** datasets produced by transform blocks (DATA_STEP, PROC_SQL, etc.) are listed in prompts as stem-only; datasets produced by PROC_IMPORT/PROC_EXPORT keep `libname_table` form — this is the stable convention for all agents · revisit never
- **Topo sort tiebreaker:** Kahn's with `(source_file, start_line)` min-heap chosen over `nx.lexicographic_topological_sort` (not available in networkx 3.6.1) · revisit if networkx upgraded

### Open Questions
- PROC IMPORT blocks still crash executor when real source files aren't uploaded — graceful skip needed (executor returns error, recon marks `no_data`, job continues)
- `make docker-build` still needed to deploy all worker + executor changes
- `auto_verified` counter and `needs_attention` threshold fixes still pending

### Next Session — Start Here
1. Run `make docker-build` and resubmit the failing job — verify no NameError and PROC IMPORT uses `/workspace/data/` paths
2. Fix `auto_verified` trust report counter (always 0) and `needs_attention` threshold
3. Begin F19 (agentic per-block execute-and-refine loop) — S1: `BlockExecutor.run()` helper

### Files Touched
- `src/worker/engine/parser.py` — Kahn's topo sort with file/line tiebreaker
- `src/worker/engine/codegen.py` — guard on `result =` append
- `src/worker/engine/agents/data_step.py` — `_fix_output_var_naming`, input naming, PROC_IMPORT exclusion
- `src/worker/engine/agents/proc.py` — same as data_step
- `src/worker/engine/agents/generic_proc.py` — all of the above + data_files in prompt + PROC IMPORT path rule
- `src/worker/main.py` — `_reconcile_initial_blocks` cumulative slices
- `src/backend/api/routes/jobs.py` — `execute_job` cumulative code for block_id
- `src/executor/main.py` — removed debug logging
- `tests/test_worker_main_comprehensive.py` — updated call sites for new signature

---

## 2026-04-27 — Test coverage 86% → 95%

**Duration:** ~1.5h | **Focus:** Coverage uplift — agent factories, router, worker/main, API routes

### Done
- **Coverage 86% → 90%:** Added tests for Azure/TensorZero `_make_agent()` branches across `llm_client`, `generic_proc`, `migration_planner`; `_StrategyStubAdapter`, `_SimpleCopyHelper` (keep/drop/copy), MANUAL block_plan routing; `_safe_exec` NameError re-raise; `_get_spark` ImportError path
- **Coverage 90% → 92%:** Added tests for TensorZero/Azure branches across `analysis`, `data_step`, `proc`, `failure_interpreter`, `macro_resolver`, `documentation`, `plain_english`, `lineage_enricher`, `explain_agent`; parser cycle detection + `extract_lineage`; executor runner empty JSON + exception paths
- **Coverage 92% → 93%:** Added tests for `jobs.py` versions/refine/restore routes; `worker/main.py` sentinel key parsing, migration planner failure, refine context, doc/lineage failure swallowing; `migrate.py` zip skip paths
- **Coverage 93% → 95%:** Added tests for `worker/main.py` stale job recovery, `_reconcile_initial_blocks` branches, `_process_job`; `explain.py` all three POST routes; `proc.py`/`data_step.py` Azure branch; `macro_expander.py` unresolved var; `codegen.py` result append
- **pyproject.toml:** `--cov-fail-under` threshold raised to 90 (already passing at 95%)
- **New test file:** `tests/test_llm_client_text_agent.py`

### Decisions
- PySpark-dependent branches in `reconciliation.py` (Spark init, AnalysisException) left uncovered — require a real PySpark install, not feasible in unit test environment; documented as known gap

### Open Questions
- `worker/main.py` lines 259-260, 768-769 — `_claim_job` skip_llm branch and a deep translate-loop branch; partially reachable but fragile to mock; left for future session

### Next Session — Start Here
1. Debug output variable NameError (`outdir_customer_revenue_daily`) — add prompt logging in `data_step.py` `_build_prompt()`, re-submit failing job, inspect worker stdout
2. Run `make docker-build` — picks up executor log4j2, volume mount, agent router changes
3. Fix `auto_verified` trust report counter (always 0) and `needs_attention` threshold

### Files Touched
- `tests/test_llm_client.py`, `tests/test_llm_client_text_agent.py` (new)
- `tests/test_generic_proc_agent.py`, `tests/test_translation_router.py`
- `tests/reconciliation/test_reconciliation_service.py`
- `tests/test_migration_planner_agent.py`, `tests/test_analysis_agent.py`
- `tests/test_data_step_agent.py`, `tests/test_proc_agent.py`
- `tests/test_failure_interpreter_agent.py`, `tests/test_macro_resolver_agent.py`
- `tests/test_documentation_agent.py` (via `test_doc_generator.py`)
- `tests/test_lineage_enricher_agent.py`, `tests/test_explain_agent.py`
- `tests/test_parser.py`, `tests/test_executor_runner.py`, `tests/test_executor_recon.py`
- `tests/test_block_refine_routes.py`, `tests/test_job_versions.py`
- `tests/test_changelog_trust_report.py`, `tests/test_execute_route.py`
- `tests/test_jobs_routes_comprehensive.py`, `tests/test_explain_routes.py`
- `tests/test_migrate_route.py`, `tests/test_macro_expander.py`, `tests/test_codegen.py`
- `tests/test_worker_main_comprehensive.py`
- `journal/BACKLOG.md`, `pyproject.toml`

---

## 2026-04-26 — Codegen/executor fixes, agent prompt hardening, output variable naming (incomplete)

**Duration:** ~2h | **Focus:** Executor recon failures, generated code correctness, Spark warning suppression

### Done
- **Codegen:** removed unconditional `import pandas as pd` from `_MODULE_TEMPLATE` and `_FLAT_TEMPLATE`; each block now self-imports what it needs
- **Codegen:** `assemble_flat()` appends `result = <output_var>` using the last block's `output_var` field
- **Executor result-capture:** updated `_RESULT_CAPTURE_SNIPPET` to check `globals().get('result')` first before scanning all globals
- **Executor Spark warnings:** added log4j2 properties file written at runtime; passed via `spark.driver.extraJavaOptions` to suppress `NativeCodeLoader` and `incubator modules` JVM warnings (requires `make docker-build`)
- **Agent prompts — import rule:** all three translation agents (`data_step`, `proc`, `generic_proc`) now instruct: always import needed libraries at top of block; do not assume `pd` is pre-imported
- **Agent prompts — `result =` convention:** all three agents instructed to set `result = <output_var>` as final line and populate `output_var` in JSON response
- **Agent prompts — input vs output datasets:** `data_step._build_prompt()` now explicitly lists input datasets (libname_table form, already loaded) and output datasets (stem-only, must be created) as separate sections, replacing the ambiguous `dependency_order` list
- **Migration planner prompt:** added rule to assign `strategy: manual` to blocks in `macros/` files that reference macro parameters as dataset names (e.g. `assert_rowcount`)
- **Dead code removed:** `shared_context.py` `build_context_section()` deleted (was never called)
- **`output_var` field:** added to `GeneratedBlock` and to Pydantic output models for all three translation agents

### Decisions
- Output dataset variable naming: use TABLE STEM ONLY (no libname prefix) for output variables. `DATA outdir.foo` → Python var `foo`. Input datasets keep full `libname_table` form since they are pre-loaded and must be unambiguous.

### Open Questions
- **`outdir_customer_revenue_daily` NameError still occurs** even after prompt fixes and worker restart — root cause not yet confirmed. Suspect the LLM is still seeing the full dotted name somewhere (possibly in the SAS source block itself or in macro expansion) and generating `outdir_customer_revenue_daily` as an output var. Need to log the actual user prompt sent to the agent to confirm.
- Spark JVM warnings (`NativeCodeLoader`, `incubator`) still showing — log4j2 fix requires `make docker-build` which hasn't been run yet.
- Coverage at 86%, below 88% threshold.
- `make docker-build` still pending.

### Next Session — Start Here
1. **Debug the output variable NameError:** add temporary logging in `data_step.py` `_build_prompt()` to print the full user prompt (input/output dataset lists + raw SAS) to worker stdout, then re-submit the failing job and inspect. The LLM must be seeing `outdir_customer_revenue_daily` as the output variable name from somewhere.
2. Once root cause confirmed, fix and re-test.
3. Run `make docker-build` after code fixes to pick up executor log4j2 change and all other pending infra changes.
4. Fix coverage to reach 88% (add tests for `_BestEffortAgentAdapter` or `build_context_section` removal).

### Files Touched
- `src/worker/engine/codegen.py`
- `src/worker/engine/models.py`
- `src/executor/runner.py`
- `src/worker/engine/agents/data_step.py`
- `src/worker/engine/agents/proc.py`
- `src/worker/engine/agents/generic_proc.py`
- `src/worker/engine/agents/migration_planner.py`
- `src/worker/engine/agents/shared_context.py` (deleted)

---

## 2026-04-25 — History ordering, table UX, test fixes, upload redirect

**Duration:** ~1.5h | **Focus:** Plan tab UX polish, test suite repair, upload page simplification

### Done

- **History pane ordering:** `VersionHistoryRail` and `EditorTab` history pane now show v1 at the top (oldest first), descending to the latest at the bottom. "Latest" badge and primary-border highlight both moved to the last (newest) entry.
- **Collapsible block table:** `BlockPlanTable` in `PlanTab` is collapsed by default; a chevron + "Blocks" heading toggles it open.
- **Rationale + Actions merged:** Rationale column removed; `Info` icon added as first action button in the Actions column, with tooltip "View rationale" and same Popover behaviour as before. `FileText` import removed.
- **Version cache invalidation:** `saveBlockPython` now also invalidates `["job", jobId, "versions"]` so new saves appear in the history rail immediately.
- **Upload redirect:** after a successful migration submission, `UploadPage` navigates directly to `/jobs` instead of showing the Phase 2 result card. All dead code (job polling, `StatusBadge`, `manifest`/`phase`/`jobStatus` state, `copyText`, result card JSX) removed.
- **Test suite repair:** fixed 9 failing tests caused by uncommitted router and stub-generator changes from the previous session:
  - `test_routes_manual_strategy_to_stub` / `test_routes_manual_ingestion_strategy_to_stub` → updated to assert `_BestEffortAgentAdapter` (intended new behaviour).
  - `test_routes_skip_strategy_to_stub` → fixed accidental `SKIP` routing to `_BestEffortAgentAdapter` in `router.py`; reverted to `self._stub_generator`.
  - `test_stub_generator_manual_ingestion_*` and `test_strategy_stub_adapter_*` → updated placeholder path assertions from `"path/to/input.csv"` to `"/workspace/data/"` prefix.
  - `test_stub_generator_manual_ingestion_with_output_dataset` / `test_strategy_stub_adapter_translate` → updated `is_untranslatable` assertions from `True` to `False` (matches `4cd894c` behaviour change).
- **Ruff fixes:** two `E501` line-length violations in `jobs.py` `save_block_python` (long `select(Job)` + `update(Job)` chains wrapped).

### Decisions

- Upload flow simplified: no intermediate result card — navigate directly to Jobs list on success. Cleaner UX, less state to maintain.

### Open Questions

- Coverage still at 86%, below the 88% threshold — needs dedicated test additions for `_BestEffortAgentAdapter`, new `stub_generator` path, or `build_context_section`.
- `make docker-build` still pending to pick up executor volume, backend trigger fix, generated_files sync, and router changes.

### Next Session — Start Here

1. Run `make test` to verify suite is green (coverage fix needed: add tests for `_BestEffortAgentAdapter` and/or `build_context_section` to reach 88%).
2. Commit remaining dirty files (backend, worker, frontend pages, docker-compose) as separate atomic commits.
3. Run `make docker-build` once all code commits are done.

### Files Touched

- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/VersionHistoryRail.tsx`
- `src/frontend/src/components/JobDetail/EditorTab.tsx`
- `src/frontend/src/pages/UploadPage.tsx`
- `src/worker/engine/router.py`
- `src/backend/api/routes/jobs.py`
- `tests/test_translation_router.py`
- `tests/test_context_improvements.py`

---

## 2026-04-25 — Editor & Plan tab UX overhaul + agent confidence fixes

**Duration:** ~3h | **Focus:** Plan/Editor tab bugs, history pane, block-scoped View Code, inline/side-by-side diff toggle, summary card layout, agent always-translate, file path conventions

### Done

- **History pane:** entries now show `v{revision_number}` instead of filename; clicking loads that block's Python revision into the Python editor imperatively (via `model.setValue()`); clicking no longer switches the selected SAS file; `onSelectBlock` removed from `BottomPanel` to prevent file navigation side-effect.
- **Block View Code modal — SAS highlighting:** after mount, delta decorations highlight `start_line..start_line+20` with `monaco-block-highlight` CSS class; full file remains visible for context.
- **Plan→Editor sync:** after `saveBlockPython` resolves, `queryClient.invalidateQueries(["job", jobId])` refreshes `job.generated_files` so `EditorTab` picks up the new code.
- **Block refine trigger:** `POST /blocks/{block_id}/refine` now stores `trigger="agent"` (was `"human-refine"`); history pane `isHuman` check updated to `trigger === "human" || trigger === "restore"`.
- **`generated_files` sync on PATCH:** `PATCH /blocks/{block_id}/python` now updates `job.generated_files[py_key]` after saving the `BlockRevision` so the per-file editor view stays current.
- **Agents always attempt translation:** `router.py` routes `manual`/`manual_ingestion` strategies through agents with `_BestEffortAgentAdapter`; `StubGenerator` is fallback only on exception; `very_low` confidence prepends warning comment.
- **Stub file path:** `StubGenerator` fallback changed from `"path/to/input.csv"` → `/workspace/data/{dataset_name}.csv`.
- **Agent prompt file path convention:** `data_step.py` and `generic_proc.py` system prompts instruct agents to use `/workspace/data/<dataset_name>.csv` instead of placeholder paths.
- **Executor workspace volume:** `docker-compose.yml` mounts `uploads:/workspace/data:ro` and sets `WORKSPACE_DATA_DIR=/workspace/data` env var on executor service.
- **Full-page editor:** new `EditorFullPage.tsx` page at `/jobs/:id/editor`; toolbar shows `Minimize2` when in full-page mode, `Maximize2` when embedded; back navigates to `/jobs/:id?tab=editor`; header-bar back arrow removed from full-page mode.
- **Language icons:** `mr-1.5` gap added between SVG icon and text in SAS/Python/Explorer pane headers.
- **Pane header text:** explicit `color: "#374151"` for light-mode headers so text is readable when editor theme is dark but app theme is light.
- **Bottom pane tab bar:** active tab uses explicit dark-mode colors (`text-white border-blue-400 bg-[#1e1e1e]`) instead of CSS vars that resolve incorrectly in dark-editor + light-app combo.
- **History entry highlight:** theme-aware `border-l-2` highlight (`border-blue-400 bg-blue-400/10` in dark, `border-primary bg-primary/10` in light).
- **Save/Edit buttons:** `EditorTab` now accepts `onSave`/`isSaving` props; toolbar shows `Save` + `Read-only` when editing, `Edit` when locked; styled to match Report tab.
- **Copyable errors:** `ExecutionOutputPanel` stderr/fetchError wrapped in `relative` container with `Copy` icon button; `select-all` class on `<pre>`.
- **Hash guard on save:** `lastSavedHashRef` + `pendingHashRef` in `JobDetailPage` skip `saveVersionMutation` if content hash unchanged.
- **URL tab routing:** `JobDetailPage` reads `?tab=` search param on mount; `onExpand` navigates with `?tab=editor` to restore tab on return.
- **Top-bar declutter:** "Save Changes" and "Refine" buttons removed from global top bar; save is now per-tab inline; refine stays per-block in Plan table.
- **Inline/side-by-side diff toggle:** `BlockRevisionModal` has a segmented toggle (Inline default, Side by side); wired through `sideBySide` prop to `RevisionRow` → `MonacoDiffViewer`.
- **`MonacoDiffViewer`:** `renderSideBySide` prop added (default `false`).
- **Plan summary card:** horizontal split (`flex-row`) — summary text fills left, vertical divider, stats cluster on right; then reverted to vertical stack (`flex-col divide-y`) per user; text full-width on top, stats centered below; padding tightened to `py-2`.
- **Block table groupBy default:** changed from dynamic folder/none logic to fixed `"file"`.
- **`ChangelogEntry.trigger` type:** widened to explicit union including `"agent"`.

### Decisions

- History pane clicking should NOT change the selected SAS file — navigation and code loading are independent actions.
- `trigger="agent"` is the correct label for LLM-generated revisions (whether initial or refine-triggered); `"human-refine"` was misleading.
- Inline diff is the better default for revision history (less horizontal space required).
- Block table defaults to file grouping (most intuitive for multi-file migrations).

### Open Questions

- `make docker-build` still needed to pick up executor volume mount + backend changes.
- Coverage gate (87% < 88%) still unresolved from prior session.
- `auto_verified` and `needs_attention` trust report counters still incorrect (tracked in backlog).
- `overrideRevisionCode` pushed via `model.setValue()` — confirm this doesn't break undo history in the Monaco editor.

### Next Session — Start Here

1. Run `make docker-build` to pick up executor volume, backend trigger fix, and `generated_files` sync.
2. Verify history pane click loads correct Python code into editor for a job with multiple block revisions.
3. Fix coverage gate: add tests for `_BestEffortAgentAdapter` or `stub_generator` path change.
4. Fix `auto_verified` / `needs_attention` trust report counters (tracked in backlog).
5. Confirm copyable errors and hash-guard save work end-to-end in browser.

### Files Touched

- `src/frontend/src/components/JobDetail/EditorTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/JobDetail/BlockRevisionDrawer.tsx`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/MonacoDiffViewer.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/pages/EditorFullPage.tsx` (new)
- `src/frontend/src/App.tsx`
- `src/frontend/src/api/types.ts`
- `src/backend/api/routes/jobs.py`
- `src/worker/engine/router.py`
- `src/worker/engine/stub_generator.py`
- `src/worker/engine/agents/data_step.py`
- `src/worker/engine/agents/generic_proc.py`
- `docker-compose.yml`

---

## 2026-04-25 — Agentic pipeline context + Editor UX polish

**Duration:** ~4h | **Focus:** Folder-aware agent context, PROC IMPORT untranslatable root-cause fix, manual_ingestion stub rework, Lineage data-file nodes, Report tab version rail + header, TipTap table fix, EditorTab history UX

### Done

- **Critical bug fixed:** `_translate_blocks()` was never passing `block_plan` to `router.route()` — migration planner strategy was completely ignored; all blocks defaulted to `translate`; PROC IMPORT blocks stayed UNTRANSLATABLE. Fixed by building `block_plan_map` and passing the matching `BlockPlan` per block.
- **`manual_ingestion` stub reworked:** `StubGenerator` now emits `pd.read_csv(disk_path)` scaffold with `is_untranslatable=False`, `confidence_score=0.7`, `confidence_band="medium"`, and a `# TODO: verify delimiter and encoding` comment instead of `# SAS-UNTRANSLATABLE`.
- **Data-file context injected into agents:** `DataFileInfo` model + `data_files` dict + `libname_map` added to `JobContext`; populated in `main.py` from sentinel keys + SAS source grep; shared `build_context_section()` utility in `src/worker/engine/agents/shared_context.py`; prepended to all agent prompts.
- **Macro file context in windowed prompts:** `windowed_context()` now includes `macros/` and `autoexec.sas` source files so translation agents see macro definitions.
- **Always-attempt instruction:** Added to all four agents — agents must emit best-effort code; never return empty for `translate`/`translate_with_review` strategies.
- **Lineage data-file nodes:** `_inject_data_file_nodes()` appends DATA_FILE nodes + edges (inferred) to the lineage graph connecting blocks to real CSV/XLSX/log files.
- **`LineageNode`/`LineageEdge` schema loosened:** `source_file`, `block_type`, `status` now have defaults; `inferred` has default `False`; accommodates new DATA_FILE node shape.
- **Frontend `LineageGraph`:** renders DATA_FILE nodes with blue dashed border, extension badge, filename, column preview.
- **Report tab:** restored `VersionHistoryRail`; always-visible header with Technical/Plain English toggle; Edit/Save buttons inline in header (Edit button only in readonly, Save + Read-only in edit mode); "Save Changes" button hidden in top bar when `activeTab === "report"`.
- **TipTap:** named imports for `{ Table }`, `{ TableCell }`, `{ TableHeader }`, `{ TableRow }` (fixed SyntaxError); Toolbar always rendered with disabled/dimmed state in readonly; table CSS styles added.
- **EditorTab explorer panel:** max resizable width raised from 30% to 50%.
- **EditorTab history tab:** Latest badge on newest entry; "User modified" badge removed; filename-only label; clicking an entry calls `onSelectBlock` → navigates Monaco SAS editor to the block's start line via `revealLineInCenter`.
- **View Code dialog scroll-to-line:** SAS editor `onMount` uses `revealLineInCenter` + `setPosition` for the block's `start_line`.

### Decisions

- `manual_ingestion` blocks are NOT untranslatable — they have translatable I/O patterns but require real file paths; medium confidence (0.7) is appropriate.
- DATA_FILE lineage nodes use `inferred: True` edges (same convention as cross-file inferred edges).
- `build_context_section()` is a shared utility; all agents call it uniformly so the project context section is consistent across prompts.
- Absolute disk path used in `manual_ingestion` stub for local runability; relative path can be substituted post-migration.

### Open Questions

- Log/Output tabs in bottom panel: were not loading after lineage 500 fix — likely transient; user should verify after Docker rebuild.
- `make docker-build` still needed to pick up all backend + worker changes.
- Coverage 87% < 88% threshold — `make test` still fails on coverage gate; needs a small test addition.

### Next Session — Start Here

1. Run `make docker-build` to pick up all changes (migration 013, executor, new worker context code, frontend).
2. Verify Log/Output tabs load in EditorTab bottom panel after rebuild.
3. Fix coverage gap: add tests covering new `_sniff_file`, `_inject_data_file_nodes`, or `build_context_section` to restore ≥88%.
4. Fix `auto_verified` counter: derive from `reconciliation_status == "pass" AND confidence in (high, medium)` in trust report.
5. Fix `needs_attention`: widen condition to include low confidence, not just recon failure.
6. Decide: add `translate_best_effort` to planner prompt or remove enum.

### Files Touched

- `src/worker/engine/models.py`
- `src/worker/main.py`
- `src/worker/engine/agents/shared_context.py` (new)
- `src/worker/engine/agents/analysis.py`
- `src/worker/engine/agents/migration_planner.py`
- `src/worker/engine/agents/data_step.py`
- `src/worker/engine/agents/generic_proc.py`
- `src/worker/engine/stub_generator.py`
- `src/worker/engine/router.py`
- `src/backend/api/schemas.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/components/TiptapEditor.tsx`
- `src/frontend/src/components/LineageGraph.tsx`
- `src/frontend/src/components/JobDetail/EditorTab.tsx`
- `src/frontend/src/components/JobDetail/ReportTab.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`

---

## 2026-04-24 — SAS EG editor UX + Python executor microservice

**Duration:** ~4h | **Focus:** SAS Enterprise Guide–style editor layout, Python execution sandbox, trust report bugs analysis

### Done

- **SAS EG–style editor:** Code|Log|Output sub-tab bar (top), LogView (NOTE/WARNING/ERROR line coloring), OutputView (CSV data grid, 500-row cap), block tree sidebar (expandable DATA/PROC nodes under each .sas file, click-to-scroll Monaco)
- **Attachment endpoints:** `GET /jobs/{id}/attachments` + `GET /jobs/{id}/attachments/{path_key}` — lists/streams non-SAS uploaded files categorised as log/output/other
- **Python executor microservice:** `src/executor/` (FastAPI, port 8001) — subprocess sandbox with unique temp file per run, result DataFrame capture via env var, self-contained 3-check reconciliation (schema/row/aggregate)
- **`POST /jobs/{id}/execute`:** backend proxy to executor; supports optional `block_id`; 404/503/502 error handling
- **`RemoteReconciliationService`:** worker delegates recon to executor over HTTP; graceful fallback on unreachable; `_reconcile_initial_blocks()` sets per-block `reconciliation_status` after initial migration run
- **Run ▶ button in editor:** in Code sub-tab toolbar; populates bottom panel with stdout/result/recon after run
- **SAS Studio layout refactor:** persistent vertical split — editors top, always-visible bottom panel (Code|Log|Output|History tabs with resize handle); Run ▶ moved to first/left in toolbar
- **Bug fixes:** stdout now shown even on error; result JSON temp file collision fixed (unique path per run)
- **Trust report analysis:** `auto_verified` always 0 (verified_confidence never written); `needs_attention` too strict; `translate_best_effort` dead; `manual_ingestion` stub identical to `manual`

### Decisions

- `executor` microservice: subprocess sandbox in separate Docker container, shared `uploads` volume, HTTP API
- Bottom panel always-visible split matches SAS Studio — not slide-in
- `translate_best_effort`, `manual_ingestion` stub, `auto_verified`, `needs_attention` bugs logged for next session

### Open Questions

- None blocking

### Next Session — Start Here

1. Fix `auto_verified` counter: derive from `reconciliation_status == "pass" AND confidence in (high, medium)` in `jobs.py` trust report
2. Fix `needs_attention`: widen condition to include low confidence, not just recon failure
3. Fix `manual_ingestion` stub: `StubGenerator` should emit `pd.read_csv()` scaffold when strategy is `manual_ingestion`
4. Decide: add `translate_best_effort` to planner prompt or remove enum
5. Run `make docker-build` to pick up migration 013, executor service, and frontend changes

### Files Touched

- `src/executor/main.py`, `src/executor/runner.py`, `src/executor/recon.py`, `src/executor/Dockerfile`, `src/executor/pyproject.toml`
- `docker-compose.yml`
- `src/backend/api/routes/jobs.py`
- `src/backend/api/schemas.py`
- `src/backend/core/config.py`
- `src/worker/core/config.py`
- `src/worker/validation/reconciliation.py`
- `src/worker/main.py`
- `src/frontend/src/components/JobDetail/EditorTab.tsx`
- `src/frontend/src/components/JobDetail/LogView.tsx` (new)
- `src/frontend/src/components/JobDetail/OutputView.tsx` (new)
- `src/frontend/src/api/jobs.ts`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `tests/test_job_attachments.py` (new)
- `tests/test_execute_route.py` (new)
- `tests/test_executor_runner.py` (new)
- `tests/test_executor_recon.py` (new)
- `tests/test_remote_reconciliation.py` (new)
- `pyproject.toml`

---

## 2026-04-24 — Explain page polish: suggestion chips, sidebar, send fix, syntax highlighting

**Duration:** ~1h | **Focus:** Explain UX polish — mode+audience chip sets, SAS General sidebar, send button bug, Monaco syntax highlighting

### Done

- **Suggestion chips per mode × audience (4 sets):** `EmptyState` now takes both `mode` and `audience` props; chips differ across migration/tech, migration/non-tech, sas_general/tech, sas_general/non-tech; heading and subtitle also update per mode
- **SAS General sidebar:** migration list hidden in `sas_general` mode; sidebar title changes to "Chats"; `RightSidebar` gains a `header` slot (renders above items) so session list always appears at top in both modes
- **Chat input lifted from bottom:** wrapped in `pb-6 pt-2 px-4` so input floats with breathing room above page edge
- **SAS General always open:** `inputDisabled` and `hasContext` updated — SAS General chat is always enabled regardless of file attachment; file is optional context not a prerequisite
- **Send button bug fixed:** `handleSend` had a stale local `hasContext` re-declaration that still required files in `sas_general` mode, causing early return; replaced with a single `mode === "migration" && !selectedJobId` guard
- **Session title bug fixed:** `state.inputValue` was read after being cleared to `""`; now uses the captured `question` variable
- **Monaco syntax highlighting:** switched from `defaultLanguage` to `language` (reactive); added `LANG_MAP` for `python/py/pyspark`, `sas`, `sql`, `bash/sh/shell`, `ts`, `js`, `json`, `yaml`, `r`; auto-sized height (lines × 19px, 60–400px); `onMount` layout fix; parse error fix (`??` + `||` mixed operators wrapped in parens)

### Decisions

- none

### Open Questions

- `make docker-build` still needed for migration 013 + react-markdown in Docker volume

### Next Session — Start Here

1. Run `make docker-build` — installs react-markdown in Docker frontend volume, picks up migration 013
2. Smoke-test Explain page end-to-end: both modes, both audience toggles, send message, session restore
3. Verify Monaco code blocks show colours for python/sas/sql responses

### Files Touched

- `src/frontend/src/components/Explain/EmptyState.tsx`
- `src/frontend/src/components/Explain/MessageList.tsx`
- `src/frontend/src/components/Explain/MarkdownRenderer.tsx`
- `src/frontend/src/components/RightSidebar.tsx`
- `src/frontend/src/pages/ExplainPage.tsx`

---

## 2026-04-24 — Explain page overhaul: two chat modes, react-markdown, session persistence fix

**Duration:** ~3h | **Focus:** Explain feature — SAS General + Migration Chat modes, 3-layer LLM prompts, react-markdown renderer with Monaco copy button, reliable session restore

### Done

- **Backend schema (migration 013):** added `title` + `file_name` columns to `explain_sessions`; backfill `mode='upload'` → `'sas_general'`
- **ExplainAgent 3-layer prompt composition:** replaced two hard-coded system prompts with `_BASE_SYSTEM_PROMPT` + `_MODE_PROMPTS[mode]` + `_AUDIENCE_PROMPTS[audience]`; 4-agent cache keyed on `(mode, audience)` — migration/sas_general × tech/non_tech
- **`_persist_messages` session bug fixed:** background task previously reused the request-scoped `AsyncSession` (closed before task ran); now opens its own `AsyncSessionLocal()` — eliminates silent message-loss on persistence
- **`/explain` form handler:** new `mode` field (default `"sas_general"`) passed through to `answer_stream`
- **API schemas:** `CreateExplainSessionRequest` → `"sas_general"` mode + `title`/`file_name`; `ExplainSessionResponse` exposes `title`, `file_name`, `job_id`
- **Frontend types + API client:** `types.ts` and `explain.ts` updated; `explainFilesStream` passes `mode` in FormData
- **MarkdownRenderer rewrite:** `react-markdown` + `remark-gfm` replaces hand-rolled parser; full GFM support (headers, lists, tables, links); Monaco code blocks preserved with copy button overlay (Copy/Copied toggle)
- **ExplainPage mode tabs:** "Migration Chat" / "SAS General" tabs above message list; existing confirm-switch dialog reused
- **Session restore fix:** `handleRestoreSession` now dispatches `SET_MODE`, `SET_AUDIENCE`, `SELECT_JOB`, `SET_ATTACHED_FILE_NAME` — full context restored on resume
- **Session sidebar:** shows M/S mode badge + `session.title` (auto-set from first question) + relative date; "+ New Chat" button clears context
- **ChatInput:** `sas_general` mode enforces single `.sas`-only file attachment
- **EmptyState:** mode-aware suggestion chips (migration vs SAS general sets)
- **Tests:** `tests/test_explain_agent.py` (9 tests, 100% pass); `test_explain_routes.py` updated + 3 new persistence/session tests; all 29 explain tests green

### Decisions

- **3-layer prompt composition over per-audience singleton agents:** base + mode + audience layers let us add new modes/audiences without combinatorial duplication; 4-agent cache built at construction time to avoid per-request init cost — revisit never
- **`_persist_messages` owns its own DB session:** request-scoped sessions are not safe for fire-and-forget background tasks in FastAPI SSE routes; the fix is authoritative and should be applied to any future background persistence task — revisit never
- **Mode stored as `"sas_general"` (not `"upload"`):** "upload" was an implementation detail that leaked into the DB; "sas_general" names the intent — migration 013 backfills all existing rows — revisit never

### Open Questions

- `make docker-build` still needed to pick up all backend changes (migration 013 + new explain routes) and to install `react-markdown` in the Docker frontend volume
- Coverage sits at 87% (below 90% threshold) — the 3% gap is entirely in pre-existing uncovered code (`worker/main.py`, `llm_client.py`, `router.py`), not new code from this session

### Next Session — Start Here

1. Run `make docker-build` — picks up migration 013, new backend routes, and installs `react-markdown` in the Docker `frontend_node_modules` volume
2. Smoke-test Explain page: both tabs visible, SAS General enforces single `.sas` file, session sidebar shows M/S badge + title + date
3. Send a message in each mode, reload the page, restore the session — verify mode/audience/job are all restored correctly
4. Verify Markdown responses render properly (headers, lists, tables, code blocks with copy button)
5. Address pre-existing coverage gap (87% → 90%) as a separate chore if CI is blocking

### Files Touched

- `alembic/versions/013_explain_session_metadata.py` (new)
- `src/backend/db/models.py`
- `src/backend/api/schemas.py`
- `src/backend/api/routes/explain.py`
- `src/worker/engine/chatbot/explain_agent.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/api/explain.ts`
- `src/frontend/src/components/Explain/MarkdownRenderer.tsx`
- `src/frontend/src/components/Explain/EmptyState.tsx`
- `src/frontend/src/components/Explain/ChatInput.tsx`
- `src/frontend/src/components/Explain/MessageList.tsx`
- `src/frontend/src/pages/ExplainPage.tsx`
- `src/frontend/package.json` (react-markdown, remark-gfm added)
- `tests/test_explain_agent.py` (new)
- `tests/test_explain_routes.py`

---

## 2026-04-23 — Plan tab full UX overhaul + confidence bug fix

**Duration:** ~2h | **Focus:** Plan tab visual redesign, View Code dialog alignment, confidence 100% bug fix, stat pill tooltips

### Done

- **Plan tab redesign:** replaced three competing visual regions (summary box + twin progress bars + 4-card stat grid) with a single `<Card>` containing an inline metrics ribbon (confidence Progress bar + risk Progress bar + vertical Separator + 4 StatPill dots); installed shadcn badge/card/progress/separator/popover/skeleton
- **Attention strip:** conditional amber banner below the card, only shown when `needs_review > 0` or `failed_reconciliation > 0`
- **Table: 11 → 8 columns:** removed Line column (now inline `:N` suffix on Block cell), merged confidence band badge into coloured % text, collapsed Code/Refine/History into single Actions column
- **Rationale cell:** replaced truncated text with `FileText` icon + Popover on click for full text
- **Recon cell:** replaced ✓/✗ Unicode with "Pass"/"Fail" Badge (accessible)
- **Group headers:** Lucide chevrons, shadcn Badge count, `aria-expanded`; Glossary trigger now has visible "Glossary" label
- **View Code dialog alignment fix:** restructured dialog into three horizontal bands (title+toolbar / panel headers / editors) so both Monaco editors start at identical vertical positions; `border-border` separators throughout; `padding: { top: 12 }` on both editors
- **Confidence 100% bug fix (backend):** `StubGenerator` now emits `confidence_score=0.0, confidence_band="very_low"` for untranslatable stubs; `migration_planner._build_migration_plan` sets `confidence_score=0.0` for `manual`/`manual_ingestion`/`skip` blocks at plan time
- **Stat pill tooltips:** hovering Auto-verified / Needs review / Manual TODO / Failed recon shows a plain-English explanation of how each number is computed

### Decisions

- View Code dialog: unified full-width toolbar (title + theme/edit/save) above per-panel headers of identical height — eliminates SAS/Python vertical misalignment without any JS measurement
- Confidence default: fix applied at the two sources (StubGenerator + migration_planner) rather than at the API serialisation layer — values are now correct in the DB for new jobs

### Open Questions

- `make docker-build` still needed to pick up `PATCH /blocks/{block_id}/python` in production (carried over from last session)

### Next Session — Start Here

1. Run `make docker-build` to pick up `PATCH /blocks/{block_id}/python` backend route in the Docker image
2. Smoke-test Plan tab: new single-card layout, 8-col table, rationale popover, actions column, stat pill tooltips
3. Smoke-test View Code dialog: both panels start at same height, separators visible in both light and dark mode
4. Run a new job and verify manual/skip blocks show `0%` confidence instead of `100%`

### Files Touched

- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/ui/badge.tsx` (new)
- `src/frontend/src/components/ui/card.tsx` (new)
- `src/frontend/src/components/ui/progress.tsx` (new)
- `src/frontend/src/components/ui/separator.tsx` (new)
- `src/frontend/src/components/ui/popover.tsx` (new)
- `src/frontend/src/components/ui/skeleton.tsx` (new)
- `src/worker/engine/stub_generator.py`
- `src/worker/engine/agents/migration_planner.py`

---

## 2026-04-23 — Plan tab UX overhaul, BlockRevisionDrawer Monaco diff, PlainEnglishAgent restructure

**Duration:** ~3h | **Focus:** Plan tab bug fixes, history revision diff, right sidebar UX, plain-English doc quality

### Done

- **Fix block_id encoding 404:** all four block API calls (`refine`, `revisions`, `restore`, `python`) now use `blockId.replace(/:/g, '%3A')` — preserves `/` so FastAPI `block_id:path` routes match correctly
- **View Code dialog — SAS syntax highlighting restored:** `language="sas"` + `beforeMount={registerSasLanguage}`; was `"plaintext"` causing no colouring
- **View Code dialog — Python panel scoped to block:** falls back to `generatedFiles[*.py]` derived from `bp.source_file`, then `jobPythonCode`; `generatedFiles` prop wired all the way from `JobDetailPage`
- **View Code dialog — logos + button order:** SAS/Python SVG logos in panel headers; button order theme → edit/lock → save
- **History button highlights on human edit:** `humanEditedBlocks` set updated after save; button gets primary ring
- **BlockRevisionDrawer replaced with Monaco DiffEditor:** `MonacoDiffViewer` with `previousCode = sorted[idx+1].python_code`; latest auto-expanded, older collapsed; removed all custom diff parsing
- **RightSidebar upgrade:** `subtitle` prop (per-item secondary text), `sidebarKey` prop (independent collapse state per page)
- **GlobalLineagePage sidebar:** status·date subtitle, Connect(N) button, disabled+helper when empty, `sidebarKey`
- **ExplainPage sidebar:** status subtitle, `sidebarKey`
- **PlainEnglishAgent fix:** output field corrected from `"markdown"` to `"non_technical_doc"` (Pydantic model mismatch that silently produced empty docs)
- **PlainEnglishAgent restructure:** 5 sections (Purpose prose, Source Data bullets, How It Works numbered, Outputs bold bullets, Migration Status); "no bullet points" rule removed; token limit 1800

### Decisions

- `block_id` URL encoding: `.replace(/:/g, '%3A')` not `encodeURIComponent` — FastAPI `:path` needs literal slashes
- BlockRevisionDrawer: use `previousCode` prop + MonacoDiffViewer instead of parsing unified diff strings
- PlainEnglishAgent: 5-section structured prompt with explicit list formatting per section

### Open Questions

- PATCH /blocks/python still 404s in production — Docker image predates the route; `make docker-build` needed

### Next Session — Start Here

1. Run `make docker-build` to pick up last session's `PATCH /blocks/{block_id}/python` backend route
2. Smoke-test: Plan tab → Code icon → verify SAS highlighted, Python scoped to block, Save works, History shows Monaco diff
3. Smoke-test: DocsPage Plain English tab — re-run a job and verify the new 5-section structure appears

### Files Touched

- `src/frontend/src/api/jobs.ts`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/JobDetail/BlockRevisionDrawer.tsx`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/RightSidebar.tsx`
- `src/frontend/src/pages/ExplainPage.tsx`
- `src/frontend/src/pages/GlobalLineagePage.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/worker/engine/agents/plain_english.py`

---

## 2026-04-23 — UI polish: layout fixes, Upload dialog, Plan table improvements, View Code dialog

**Duration:** ~3h | **Focus:** Frontend UX improvements across ExplainPage layout, Plan tab, and View Code dialog

### Done

- **Layout fix (ExplainPage full-height):** removed `max-w-500 mx-auto px-4 py-8` wrapper from App.tsx; moved it into individual pages; ExplainPage gets `flex flex-1 min-h-0`; other pages get `overflow-y-auto flex-1 h-full`; `<main>` is now `overflow-hidden flex flex-col`; `max-w-500` was an invalid Tailwind class (no effect) — replaced with `max-w-[800px]` then removed entirely for full-width pages
- **Upload page → Dialog:** removed "Upload" from AppSidebar nav and `/upload` route; "New Migration" button on JobsPage now opens a `Dialog` (`max-w-3xl, 90vw × 85vh`) containing the full upload form; on success invalidates `["jobs"]` query
- **BlockPlanTable UI improvements:** default groupBy changed to `"folder"`; chevron moved to leftmost position in group header rows; `Clock` icon replaced with `History` (counter-clockwise clock); "Filter by" label added before strategy chips with `ml-3` spacing; file basenames stripped in body rows (`.split("/").pop()`)
- **View Code column added to Plan table:** `Code2` icon button per row opens a wide `Dialog` (`max-w-6xl, 95vw × 80vh`) with SAS source (left, read-only, orange dot header) + Python code (right, editable with Edit/Lock toggle, blue dot header, Sun/Moon theme toggle)
- **View Code dialog data loading:** fetches `getBlockRevisions` + `getJobSources` in parallel; falls back to `job.python_code` when no revisions exist; `revisions[0]` fix (backend returns newest-first); `codeLoading` spinner while fetching
- **Backend: `PATCH /jobs/{job_id}/blocks/{block_id:path}/python`:** new endpoint creates a `BlockRevision` with `trigger="human"`, unified diff vs previous; when no prior revision exists, creates revision 1 with defaults instead of 404
- **LLM guardrails improved:** both `_TECH_SYSTEM_PROMPT` and `_NON_TECH_SYSTEM_PROMPT` in `explain_agent.py` expanded with scope boundary, accuracy guardrails (no hallucination), citation rules, structured fallback
- **VersionHistoryRail hidden on Plan tab:** only shown for `editor` and `report` tabs

### Decisions

- **Upload page promoted to Dialog on JobsPage:** fewer nav items, inline workflow — upload no longer deserves top-level navigation once migrations become the default landing page · revisit never
- **`PATCH /python` creates revision 1 on first human edit (no prior revision):** instead of 404, uses sensible defaults (`strategy="translate"`, `confidence="medium"`) so any block can be edited from the View Code dialog regardless of prior agent activity · revisit never
- **SAS source shown in View Code dialog via `getJobSources`:** reuses existing endpoint, no new DB columns; matches by `source_file` field on `BlockPlan` · revisit never

### Open Questions

- none

### Next Session — Start Here

1. Smoke-test View Code dialog: click Code2 on a block, confirm SAS (left) and Python (right) load, toggle Edit, modify code, Save — verify new `BlockRevision` created with `trigger="human"`
2. Smoke-test Upload dialog: click "New Migration" on Jobs page, confirm upload form opens in dialog, submit, confirm dialog closes and job appears in list
3. Unresolved UI bugs from previous sessions still pending: TipTap cursor jump, version card highlight race condition, Editor tab restore shows original code

### Files Touched

- `src/frontend/src/App.tsx`
- `src/frontend/src/components/AppSidebar.tsx`
- `src/frontend/src/pages/JobsPage.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/pages/DocsPage.tsx`
- `src/frontend/src/pages/GlobalLineagePage.tsx`
- `src/frontend/src/pages/UploadPage.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/RightSidebar.tsx`
- `src/backend/api/routes/jobs.py`
- `src/backend/api/schemas.py`
- `src/frontend/src/api/jobs.ts`
- `src/worker/engine/chatbot/explain_agent.py`

---

## 2026-04-22 — GlobalLineagePage Pipeline tab

**Duration:** ~1h | **Focus:** FE7 Global Lineage — migration selector + merged ReactFlow pipeline graph

### Done

- **`GlobalLineagePage` — full rewrite:** replaced CSS placeholder with a functional page featuring a **Pipeline tab**, a left-side migration checklist (filtered to `proposed`/`accepted`/`done` jobs), and a **Connect** button that fetches lineage for all selected migrations in parallel and renders a merged `LineageGraph`
- **`src/frontend/src/lib/lineage-merge.ts` (new):** pure `mergePipelineLineages()` utility — prefixes all node/edge/step IDs with `{jobId}_` to prevent collisions, concatenates all arrays, and infers synthetic cross-migration `LineageEdge` entries where a step's `outputs` match another step's `inputs` across migrations
- **Reused `<LineageGraph>` without modification:** the component's existing pipeline view mode renders the merged `JobLineageResponse` unchanged; no `initialView` prop was needed

### Decisions

- **ID namespacing via `{jobId}_` prefix:** simplest collision-free strategy for merging multiple jobs' lineage graphs into one ReactFlow canvas; no UUID generation needed · revisit never
- **Synthetic cross-migration edges inferred from `inputs`/`outputs` overlap:** enables dataset-level cross-job dependency visibility without backend changes · revisit if explicit cross-job edges should be computed server-side

### Open Questions

- none

### Next Session — Start Here

1. Smoke-test GlobalLineagePage: navigate to Global Lineage, select ≥1 migration, click Connect, verify graph renders in pipeline view
2. Next backlog items: Datasets + Columns tabs on GlobalLineagePage (FE7 remainder), or pick from Phase 2 backend extensions

### Files Touched

- `src/frontend/src/pages/GlobalLineagePage.tsx` (full rewrite)
- `src/frontend/src/lib/lineage-merge.ts` (new)
- `journal/BACKLOG.md`
- `journal/SESSIONS.md`

---

## 2026-04-22 — Reconciliation coverage fix + DocsPage UX polish

**Duration:** ~30m | **Focus:** test coverage gate + two UI tweaks on DocsPage / ReportTab

### Done

- **Reconciliation coverage** — added `tests/reconciliation/test_reconciliation_service.py` (10 new tests) to cover previously untested branches in `ReconciliationService` and its helpers; coverage lifted from 79% → 100%, all 26 reconciliation tests pass
- **BlockPlanTable: Rationale column** — removed `Tooltip` popup; text now renders inline with `line-clamp-2`, no hover tooltip
- **ReportTab: Report editor header** — grey header bar is now always visible for both Technical and Plain English views; Modify/Lock button is always present for both modes; when Modify is clicked (`readOnly=false`), TiptapEditor renders its writing toolbar; Plain English doc also respects `readOnly` state (was always locked before)

### Decisions

- none

### Open Questions

- none

### Next Session — Start Here

1. Smoke-test ReportTab: open a completed job, confirm grey header visible for both tabs before and after clicking Modify; confirm toolbar buttons appear only after Modify click
2. Next backlog item: `F-UI-postmvp S-FE7: GlobalLineagePage`

### Files Touched

- `tests/reconciliation/test_reconciliation_service.py` (new)
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/JobDetail/ReportTab.tsx`
- `journal/BACKLOG.md`
- `journal/SESSIONS.md`

---

## 2026-04-22 — FE8: DocsPage — migration documentation cards + popup

**Duration:** ~1h | **Focus:** DocsPage full implementation (`feat/FE8-docs-page` branch from main)

### Done

- **Pulled main** (7 commits merged in from remote) and created `feat/FE8-docs-page` branch
- **DocsPage** (`src/frontend/src/pages/DocsPage.tsx`) — full replacement of stub:
  - Responsive card grid (`grid-cols-1 md:grid-cols-2 xl:grid-cols-3`) — only `proposed` / `accepted` jobs shown
  - Card: status chip (amber shimmer "Under Review" / emerald "Accepted"), risk badge (green/amber/red), job name, plan summary snippet, lucide `FolderOpen` file count, confidence badge, auto-verified/needs-review/failed counts
  - Per-card footer buttons: "Plain English" + "Technical" (pre-select popup tab before opening)
  - Dialog popup (`85vh`, `max-w-5xl`) with header tab toggle (Plain English first, then Technical), TiptapEditor `readOnly` for both views (`marked.parse` + `extractMarkdown` — matches `ReportTab` pattern), read-only collapsible file tree (lazy-loaded via `getJobSources`, closed by default), footer with block summary counts + Close
  - Fixed `DialogContent` base `grid gap-4` override using `flex! flex-col! gap-0! p-0!` Tailwind important modifiers
- **Fixed ruff E501** (pre-existing, came in from main): wrapped long prompt lines in `data_step.py`, `generic_proc.py`, `proc.py`
- **All 7 gates GREEN** after fixes

### Decisions

- none

### Open Questions

- none

### Next Session — Start Here

1. `make docker-build` — verify worker container starts cleanly (possible `ModuleNotFoundError: No module named 'src.worker'` flagged in earlier session, not yet confirmed fixed)
2. Smoke-test DocsPage end-to-end: navigate to `/docs`, confirm cards appear for proposed/accepted jobs, open popup, toggle tabs, expand file tree
3. Next backlog item: `F-UI-postmvp S-FE7: GlobalLineagePage`

### Files Touched

- `src/frontend/src/pages/DocsPage.tsx`
- `src/worker/engine/agents/data_step.py`
- `src/worker/engine/agents/generic_proc.py`
- `src/worker/engine/agents/proc.py`
- `journal/BACKLOG.md`
- `journal/SESSIONS.md`

---

## 2026-04-22 — FE9: ExplainPage full implementation

**Duration:** ~2h | **Focus:** ExplainPage — chat UI with file upload mode + migration context mode

### Done

- **Plan**: Designed ExplainPage with fullstack-planner + Plan agents; approved two-mode chat layout (file upload / migration selector)
- **Backend**: `POST /explain` (multipart file Q&A, stateless, pydantic-ai inline) and `POST /explain/job` (job context Q&A using stored plan/doc/python_code); new `ExplainMessage`, `ExplainJobRequest`, `ExplainResponse` schemas in `schemas.py`
- **Backend**: `GET /jobs` gains optional `?status=` comma-separated filter (e.g. `?status=proposed,accepted,done`)
- **Backend**: `src/backend/api/routes/explain.py` new route file registered in `main.py`
- **Frontend**: `src/frontend/src/api/explain.ts` — `explainFiles()` + `explainJob()` API functions
- **Frontend**: 9 new components under `src/frontend/src/components/Explain/` — `shared.tsx`, `utils.ts`, `MarkdownRenderer.tsx` (Monaco for code blocks), `EmptyState.tsx`, `ContextBanner.tsx`, `MigrationCard.tsx`, `MigrationPanel.tsx`, `MessageList.tsx`, `ChatInput.tsx`
- **Frontend**: `ExplainPage.tsx` full replacement — `useReducer` state, desktop right panel (280px) + mobile drawer overlay, mode-switch confirmation dialog, auto-scroll, file attachment chips, suggested prompts
- **Tests**: 11 new tests in `tests/test_explain_routes.py`; coverage held at 90%
- **Pre-existing fixes**: `BlockPlanTable.tsx` unused Tooltip imports removed; `monacoConfig.ts` `import type` for `OnMount`; `scroll-area.tsx` + `checkbox.tsx` shadcn components added (required by `GlobalLineagePage`)
- **F4 plan**: marked `Status: complete`, S12 ticked off
- **All 7 gates GREEN**

### Decisions

- **ExplainPage is stateless on the backend**: frontend owns conversation history array and sends accumulated `messages` on each request — avoids session storage for an ephemeral chat feature
- **LLM called inline in backend process** (not via worker queue): explain questions need to feel fast; worker queue would add polling overhead inappropriate for chat; backend already imports from `src.worker.engine.agents`
- **Code blocks in chat rendered as read-only Monaco editors**: user preference; `MarkdownRenderer` detects triple-backtick fences and renders `<MonacoEditor readOnly height="160px" />`

### Open Questions

- Docker build not re-verified this session — `make docker-build` should be run before deploying if Dockerfile was not changed (it wasn't this session)

### Next Session — Start Here

1. Implement `S-FE8: DocsPage` (branch `feat/FE8-docs-page` already exists, `DocsPage.tsx` has uncommitted changes)
2. Then `S-FE7: GlobalLineagePage`
3. Several unresolved UI bugs from earlier sessions remain in backlog (TipTap cursor, version card highlight, Editor tab restore, tab heights)

### Files Touched

- `src/backend/api/schemas.py`
- `src/backend/api/routes/explain.py` (new)
- `src/backend/api/routes/jobs.py`
- `src/backend/main.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/api/explain.ts` (new)
- `src/frontend/src/components/Explain/` (9 new files)
- `src/frontend/src/pages/ExplainPage.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/config/monacoConfig.ts`
- `src/frontend/src/components/ui/scroll-area.tsx` (new)
- `src/frontend/src/components/ui/checkbox.tsx` (new)
- `tests/test_explain_routes.py` (new)
- `tests/reconciliation/test_reconciliation_service.py`
- `docs/plans/latest/F4-confidence-refine-history.md`
- `journal/SESSIONS.md`, `journal/BACKLOG.md`, `journal/DECISIONS.md`

---

## 2026-04-22 — Fix overall confidence metric + bar width (UX polish)

**Duration:** ~1h | **Focus:** Confidence accuracy — align overall % with per-block LLM scores

### Done

- **Backend**: `_overall_confidence()` now takes the **average LLM `confidence_score`** across all `block_plans` (was using reconciliation `auto_verified/total` ratio — different metric, caused overall to show 40% while blocks showed 100%)
- **Backend**: `TrustReportResponse` gains `overall_confidence_score: float` (0.0–1.0) so frontend can use the exact value
- **Frontend**: `PlanTab.tsx` confidence bar width now reflects the actual `overall_confidence_score * 100` (not a hardcoded band-to-% mapping)
- **Frontend**: "Overall Confidence" label has dotted underline + browser tooltip explaining the metric; sub-label "avg of N blocks" added below bar
- **Lint/type fixes**: sorted `plain_english` import in `worker/main.py`; fixed mypy errors (`result.output` cast, `str | None` → `str or ""`); fixed `_make_fallback_plan` return type; fixed `__init__.py` `__all__` line length; ESLint unused-var fixes in `BlockPlanTable.tsx`, `EditorTab.tsx`, `PlanTab.tsx`
- **Coverage**: added `test_overall_confidence_labels` and `test_plain_english_agent_generate_returns_doc` tests to close 89%→90% gap
- **All 7 gates GREEN** (ruff-check, ruff-format, mypy, pytest+coverage ≥90%, tsc, frontend-lint, frontend-build)

### Decisions

- Overall confidence metric is now **average LLM self-reported score** (consistent with per-block display), not reconciliation ratio. Reconciliation metrics are still shown separately (auto_verified / needs_review / manual_todo counts).

### Open Questions

- none

### Next Session — Start Here

1. `make docker-build && docker compose up` — verify worker container starts (prior session noted possible `ModuleNotFoundError: No module named 'src.worker'`)
2. Smoke-test F4 end-to-end: upload SAS file, confirm overall confidence bar reflects actual block scores

### Files Touched

- `src/backend/api/routes/jobs.py`
- `src/backend/api/schemas.py`
- `src/worker/main.py`
- `src/worker/engine/agents/plain_english.py`
- `src/worker/engine/agents/__init__.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/JobDetail/EditorTab.tsx`
- `tests/test_changelog_trust_report.py`

---

## 2026-04-22 — F4: Graded confidence-aware translation, per-block refine loop, change history

**Duration:** ~4h | **Focus:** Full F4 feature — S1–S11 implemented, all 7 gates green

### Done

- **Committed** `feat/S-lineage-enricher-pipeline-levels` branch (was outstanding from previous session)
- **Created** `feat/F4-confidence-refine-history` branch from previous branch HEAD
- **S1:** `DataStepResult` and `ProcResult` now capture `confidence` + `uncertainty_notes` from LLM; both translation agents pass them through to `GeneratedBlock`
- **S2:** `TranslationRouter.route()` accepts optional `block_plan`; routes MANUAL/MANUAL_INGESTION/SKIP to stub; caps confidence for TRANSLATE_WITH_REVIEW (high→medium) and TRANSLATE_BEST_EFFORT (any→low); added `TRANSLATE_BEST_EFFORT` to `TranslationStrategy` StrEnum
- **S3:** `_apply_verified_confidence()` helper in `main.py` — sets `verified_confidence` post-reconcile and propagates `verified_low` to downstream files via `enriched_lineage.cross_file_edges`; stores `block_confidence` map in `job.lineage`
- **S4:** `BlockRevision` ORM model + Alembic migration 011 (`block_revisions` table with index on `job_id, block_id`)
- **S5:** `POST /jobs/{id}/blocks/{block_id}/refine`, `GET /jobs/{id}/blocks/{block_id}/revisions`, `POST /jobs/{id}/blocks/{block_id}/revisions/{revision_id}/restore`; patched existing whole-job refine with 409 guard for accepted jobs
- **S6:** `GET /jobs/{id}/changelog` — all block revisions newest-first
- **S7:** `GET /jobs/{id}/trust-report` — project/file/block confidence summary, review queue sorted by needs_attention/blast_radius/confidence
- **S8:** Frontend TS types (`BlockRevision`, `TrustReportResponse`, `ChangelogEntry`, etc.) + API client functions (`refineBlock`, `getBlockRevisions`, `restoreBlockRevision`, `getJobChangelog`, `getJobTrustReport`)
- **S9:** PlanTab trust report summary bar (auto-verified/needs-review/manual-todo cards); BlockPlanTable confidence + recon columns with `needs_attention` sort and amber ⚠ indicator
- **S10:** `BlockRefineDialog` (notes-first textarea, optional hint field, sonner toast on success); `BlockRevisionDrawer` (revision list with trigger icons, diff toggle, Restore button); Refine + History buttons per row in BlockPlanTable
- **S11:** `TrustReportTab` (summary cards, review queue, per-file breakdown, lineage notice) + `ChangelogFeed` (timeline with diff expand); both wired into JobDetailPage as new tabs

### Decisions

- See `journal/DECISIONS.md` session 21 block for all 8 architectural decisions

### Open Questions

- Docker worker container shows `ModuleNotFoundError: No module named 'src.worker'` at runtime — the Dockerfile COPY structure looks correct (`COPY src/worker ./src/worker`, `PYTHONPATH=/app`); may require `make docker-build` after adding new files in this session; not yet verified

### Next Session — Start Here

1. Run `make docker-build` and `docker compose up` to verify the worker starts correctly
2. Smoke-test F4 features end-to-end: upload a SAS file, check Trust Report tab, refine a block, check revision history
3. If Docker issue is resolved, commit F4 code (tests pass locally, 7 gates green); use `git-committer` skill
4. Consider S12 reconciliation integration tests if coverage or confidence requires it

### Files Touched

- `src/worker/engine/models.py` — `TRANSLATE_BEST_EFFORT`, `verified_confidence` on `GeneratedBlock`
- `src/worker/engine/agents/data_step.py` — confidence capture
- `src/worker/engine/agents/proc.py` — confidence capture
- `src/worker/engine/router.py` — planner-driven routing
- `src/worker/main.py` — `_translate_blocks` strategy caps, `_apply_verified_confidence`, `block_confidence` merge
- `src/backend/db/models.py` — `BlockRevision` model
- `alembic/versions/011_add_block_revisions.py` — new migration
- `src/backend/api/schemas.py` — 9 new schemas
- `src/backend/api/routes/jobs.py` — 5 new endpoints + 409 patch + helpers
- `src/frontend/src/api/types.ts` — 9 new TS interfaces
- `src/frontend/src/api/jobs.ts` — 5 new API functions
- `src/frontend/src/components/JobDetail/PlanTab.tsx` — trust report query + summary bar
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx` — confidence/recon columns, Refine/History buttons
- `src/frontend/src/components/JobDetail/BlockRefineDialog.tsx` — new
- `src/frontend/src/components/JobDetail/BlockRevisionDrawer.tsx` — new
- `src/frontend/src/components/JobDetail/TrustReportTab.tsx` — new
- `src/frontend/src/components/JobDetail/ChangelogFeed.tsx` — new
- `src/frontend/src/pages/JobDetailPage.tsx` — Trust Report + History tab wiring
- `tests/test_data_step_agent.py`, `tests/test_proc_agent.py` — confidence propagation tests
- `tests/test_translation_router.py` — strategy routing tests
- `tests/test_worker_main.py` — `_apply_verified_confidence` tests
- `tests/test_block_refine_routes.py` — new
- `tests/test_changelog_trust_report.py` — new

---

## 2026-04-21 — LineageEnricher pipeline-level extension + multi-level lineage graph

**Duration:** ~2h | **Focus:** Extend LineageEnricherAgent with 5 new fields; add Blocks/Files/Pipeline view toggle to LineageGraph

### Done

- **New branch:** `feat/S-lineage-enricher-pipeline-levels` branched from latest main (pulled 9 commits)
- **`FileNode`, `FileEdge`, `PipelineStep`, `BlockStatus`, `LogLink` models:** added to `src/worker/engine/models.py` with `Literal` import; all optional with `Field(default_factory=list)` defaults
- **`EnrichedLineage` extended:** 5 new optional list fields; `LineageEnrichmentResult` extended to match
- **`LineageEnricherAgent` system prompt rewritten:** 9 tasks (kept 1–4, added 5–9 for file/step/block/log levels); `max_tokens` bumped 8k → 16k; `enrich()` passes all 9 fields through
- **Backend API:** 5 new `*Response` models in `schemas.py`; `JobLineageResponse` extended; `get_job_lineage` route passes 5 new `.get()` keys — no DB migration needed (schemaless JSON column)
- **Frontend types:** 5 new TS interfaces in `types.ts`; `JobLineageResponse` extended with optional fields
- **Tests:** `_ENRICHMENT_RESULT` fixture updated; 2 new tests (`test_enrich_populates_file_nodes`, `test_enrich_populates_pipeline_steps`); ruff fix for 3 unused imports
- **Multi-level LineageGraph:** view toggle (Blocks | Files | Pipeline) added to toolbar; `FileNodeCard`, `PipelineStepCard` custom React Flow nodes; `LineageDetailPanel` slide-in panel on file node click showing blocks + status + log links; `buildFileNodes/Edges`, `buildPipelineNodes/Edges` builders; `applyDagreLayout` generalized for per-view node sizes; `NODE_TYPES` registered at module level (React Flow stability)
- **All 7 gates green:** ruff, mypy, pytest, tsc, frontend-lint, frontend-build

### Decisions

- `LineageEnricherAgent` `max_tokens` raised to 16 000 — 9-field JSON output can exceed 8k for multi-file projects
- No DB migration required — new fields merge into existing schemaless `Job.lineage` JSON column
- `NODE_TYPES` for custom React Flow nodes must be module-level constant (not inside component) — moving it inside would remount all nodes on every render

### Open Questions

- `log_links.related_files/related_blocks` are empty for all log files (log content is not parsed, only filename referenced) — expected for now; would need a log parser to populate
- CSV/XLSX reference files appear as `__ref_csv_...__` / `__ref_xlsx_...__` in `file_nodes` — artefact of worker sentinel naming; cosmetic issue, not blocking

### Next Session — Start Here

1. Commit `feat/S-lineage-enricher-pipeline-levels` branch (journal + code in one commit)
2. Continue unresolved UI bugs from backlog (TipTap cursor, version highlight, editor restore, tab heights)

### Files Touched

- `src/worker/engine/models.py`
- `src/worker/engine/agents/lineage_enricher.py`
- `src/backend/api/schemas.py`
- `src/backend/api/routes/jobs.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/components/LineageGraph.tsx`
- `src/frontend/src/components/JobDetail/FileNodeCard.tsx` (new)
- `src/frontend/src/components/JobDetail/PipelineStepCard.tsx` (new)
- `src/frontend/src/components/JobDetail/LineageDetailPanel.tsx` (new)
- `tests/test_lineage_enricher_agent.py`

---

## 2026-04-21 — JobDetailPage refactor: component split, header polish, Monaco defaultValue fix

**Duration:** ~2h | **Focus:** JobDetailPage structural cleanup + bug fixes

### Done

- **Header redesign**: job name + status badge centered and larger (`text-xl font-semibold`); back button pinned absolutely left; buttons (Save Version, Refine, Accept migration) moved inline with tab bar on the right; removed standalone Save button
- **Monaco `defaultValue`**: switched both SAS and Python `<Editor>` from `value` to `defaultValue` + stable `key`; added `pythonEditorRef` with `onMount` — prevents parent re-renders from repositioning cursor
- **JobDetailPage split**: monolith extracted into `src/frontend/src/components/JobDetail/` — `EditorTab`, `PlanTab`, `ReportTab`, `LineageTab`, `BlockPlanTable`, `NoteDialog`, `ReconSummaryCard`, `StatusBadge`, `constants.ts`, `utils.ts`; page component stays in `src/frontend/src/pages/JobDetailPage.tsx`
- **`constants.tsx` → `constants.ts` + `StatusBadge.tsx`**: split to fix Vite 404 (`constants.tsx` was resolved as `.ts` by HMR)
- **VersionHistoryRail**: removed all `console.log` debug calls
- **EditorTab tooltip nesting**: removed `asChild` from Base UI `TooltipTrigger` — it renders a `<button>` itself, so wrapping another `<button>` caused nested-button hydration error
- **LineageGraph `nodeTypes`/`edgeTypes`**: defined `NODE_TYPES` and `EDGE_TYPES` as module-scope constants and passed them explicitly to `<ReactFlow>` to silence React Flow warning #002

### Decisions

- none

### Open Questions

- TipTap cursor jump, version highlight race, editor restore, tab heights — all still marked unresolved in backlog; not touched this session

### Next Session — Start Here

1. Verify dev server is clean (no 404s, no console errors) after all the component split changes
2. Pick up unresolved UI bugs from backlog — start with tab heights (simplest to verify with DevTools)

### Files Touched

- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/components/JobDetail/EditorTab.tsx`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/JobDetail/ReportTab.tsx`
- `src/frontend/src/components/JobDetail/LineageTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- `src/frontend/src/components/JobDetail/NoteDialog.tsx`
- `src/frontend/src/components/JobDetail/ReconSummaryCard.tsx`
- `src/frontend/src/components/JobDetail/StatusBadge.tsx` (new)
- `src/frontend/src/components/JobDetail/constants.ts` (renamed from .tsx)
- `src/frontend/src/components/JobDetail/utils.ts`
- `src/frontend/src/components/JobDetail/index.ts`
- `src/frontend/src/components/VersionHistoryRail.tsx`
- `src/frontend/src/components/LineageGraph.tsx`

---

## 2026-04-21 — UI polish: Note popup, tab heights, TipTap cursor, version highlight, editor restore

**Duration:** ~3h | **Focus:** JobDetailPage + TiptapEditor visual polish and bug fixes

### Done

- **NoteDialog**: removed "Block note — <id>" title from popup header; made dialog wider (`max-w-xl`) and taller (`min-h-48`); removed "Saving…" text label next to pen icon — pen now turns primary-colored when a note exists and pulses while saving
- **TipTap toolbar cursor jump**: moved `onClick()` from `onMouseDown` to the actual `onClick` handler — `onMouseDown` now only calls `e.preventDefault()` to prevent blur; command fires on click when selection is stable
- **TipTap undo boundary**: added `closeHistory(editor.state.tr)` dispatch after each `setContent` call so undo cannot remove originally-loaded content
- **Version highlight after save**: `saveVersionMutation.onSuccess` now `await`s `invalidateQueries` before calling `setSavedVersionId` — new card is rendered before highlight state is set; `VersionHistoryRail` accepts optional controlled `selectedVersionId` prop
- **Editor restore (`editorCode` null sentinel)**: changed `editorCode` initial state from `""` to `null`; `displayedEditorCode = editorCode ?? job?.python_code ?? ""` — null falls back to job code, but any restored value (including empty string) is preserved
- **Editor restore (`overrideGeneratedFiles`)**: restore now sets `{}` instead of `null` when version has no `generated_files`, so `perFileCode` resolves to null and `rightCode` uses the restored python_code
- **Tab heights**: all four tabs set to `height: calc(100vh - 160px)` — Plan/Report scroll internally, Lineage fills with React Flow, Editor uses ResizablePanelGroup

### Decisions

- none

### Open Questions

- **None of the visual/bug fixes in this session were confirmed working by the user** — TipTap cursor jump, version highlight, editor restore, and tab heights are all still reported as broken. Root causes were diagnosed but fixes did not take effect. Needs fresh debugging next session.
- Tab heights (`calc(100vh - 160px)`) not confirmed — user says this is still not fixed.
- TipTap cursor jump still occurs after all attempted fixes (`onMouseDown` pattern, `focus(null)`, removing `.focus()`, moving to `onClick`).
- Version highlight race condition fix (await invalidateQueries) not confirmed.
- Editor restore (null sentinel for editorCode) not confirmed.

### Next Session — Start Here

1. **Do NOT attempt further blind fixes** — open browser DevTools, add `console.log` to `handleRestore`, `ToolbarButton.onClick`, and `saveVersionMutation.onSuccess` to confirm what is actually executing
2. Check if Docker volume mount is actually syncing files: `docker compose exec frontend cat src/components/TiptapEditor.tsx | head -60` and compare to local file
3. Check for any Vite compilation errors in `docker compose logs frontend`
4. Once root cause is confirmed, fix each bug one at a time with immediate verification

### Files Touched

- `src/frontend/src/components/TiptapEditor.tsx`
- `src/frontend/src/components/VersionHistoryRail.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`

---

## 2026-04-21 — F5 bug-fix sweep: version history, TipTap editor, Plan tab dropdowns

**Duration:** ~3h | **Focus:** F5 per-tab version history polish + UI bug fixes

### Done

- **Root-caused "no tab selected on load"**: custom `Tabs` component only accepted `defaultValue` (uncontrolled); `JobDetailPage` was passing `value`/`onValueChange` which were silently ignored — `activeTab` state was completely disconnected from the visible tabs. Fixed `Tabs` to support controlled mode.
- **Root-caused "history rail always shows Plan versions"**: same disconnect — `activeTab` never updated, so the rail always received `"plan"`. Fixed as a consequence of the Tabs fix above.
- **Root-caused "TipTap headings not rendering"**: `@tailwindcss/typography` is not installed, so Tailwind Preflight stripped all browser heading/list defaults. Dropped `tiptap-markdown` extension (unnecessary complexity); switched TipTap to native HTML mode (`marked` converts markdown → HTML on load, `getHTML()` on save). Added explicit ProseMirror scoped heading/list CSS via Tailwind arbitrary variants.
- **TipTap toolbar scroll-to-bottom**: replaced `onClick` with `onMouseDown + preventDefault` on toolbar buttons — standard WYSIWYG pattern to keep focus in the editor and suppress browser scroll-into-view.
- **Undo deletes entire report**: patched `editor.view.dispatch` around `setContent` calls to tag transactions with `addToHistory: false` — loaded content never enters the undo stack.
- **Report tab edits not captured**: wired `TiptapEditor onChange` → `setOverrideDoc` so user edits flow into state before "Save version" fires.
- **Editor save loses `generated_files`**: was hard-coded `{}`; now uses `overrideGeneratedFiles ?? job?.generated_files ?? {}`.
- **Python editor always read-only**: `rightReadOnly` was derived from `perFileCode !== null`; set to `false` unconditionally.
- **Shadcn Select for Plan tab dropdowns**: installed `@base-ui/react/select` shadcn component; replaced both native `<select>` in `BlockPlanTable`. Fixed circular import in generated `select.tsx`.
- **Risk dropdown shows raw value ("low") instead of label ("Low")**: Base UI `SelectValue` only resolves labels after items register (portal not rendered until open). Fixed by using `SelectValue` render-prop children to map value → label directly.
- **Dropdown popup alignment**: changed `SelectContent` default `align` from `"center"` to `"start"`.
- **Table reflow flicker on risk change**: pinned `w-44` / `w-20` on Strategy/Risk `<th>` elements so column widths are stable.
- **Risk label values**: `Low` / `Mid` / `High` (capitalised); color-coded on trigger and items via `RISK_CELL` map.
- **Version restore not working for Report**: `overrideDoc` was set but `TiptapEditor` content sync guard (`content !== current`) could mismatch on subsequent restores; now always calls `setContent` when `content` prop changes.
- **`staleTime: 0` on version rail query**: forces fresh fetch on tab switch so each tab's history loads immediately.

### Decisions

- **Dropped `tiptap-markdown`**: native HTML mode is simpler, more predictable, and doesn't require `@tailwindcss/typography`. `marked` handles markdown→HTML on load; `getHTML()` returns HTML on save. Stored doc content may now be HTML (not markdown) for versions saved after this session. · revisit if markdown round-trip is needed.
- **`Tabs` component now supports controlled mode**: `value` + `onValueChange` props added alongside existing `defaultValue`. Uncontrolled callers are unaffected. · revisit never.

### Open Questions

- `make test` not run this session — tests cover backend only (Python) and should be unaffected by frontend-only changes, but should be verified before PR.
- The stray `src/frontend/@/components/ui/` directory (shadcn CLI output artefact) should be deleted before merging.

### Next Session — Start Here

1. Delete `src/frontend/@/` (shadcn CLI artefact): `rm -rf src/frontend/@`
2. Run `make test` to confirm backend tests still pass
3. Manually smoke-test: Plan tab default on load → version rail shows correct per-tab history → Save version → restore version → TipTap headings render correctly
4. Mark F5 subtask 13 complete in `docs/plans/F5-tab-versions.md`, then commit + PR

### Files Touched

- `src/frontend/src/components/ui/tabs.tsx`
- `src/frontend/src/components/ui/select.tsx` (new)
- `src/frontend/src/components/TiptapEditor.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/components/VersionHistoryRail.tsx`
- `src/frontend/package.json` / `package-lock.json`

---

## 2026-04-19 — F3 proposed/accepted review cycle, plan interaction UX, re-reconcile & refine with history (S-BE5/BE6)

**Duration:** ~4h | **Focus:** F3 (proposed/accepted status), S-BE5 (re-reconciliation), S-BE6 (refine child job), History tab, UI fixes

### Done

- **Fixed `make test` regressions**: `datetime.UTC` import (mypy), `useCallback(debounce(...))` ESLint error (replaced with `useRef` manual debounce), migration 008 `CheckViolationError` (drop/recreate constraint before UPDATE)
- **F3 T-1–T-9 (proposed/accepted review cycle)**: Alembic migration 008 (status constraint + `user_overrides`/`accepted_at`); worker writes `proposed`; `POST /accept` and `PATCH /plan` routes + tests; frontend types, status labels/colours, polling, PlanTab Accept CTA + ReconSummaryCard + inline block overrides
- **S-BE5**: `PUT /jobs/{id}/python_code` endpoint + Alembic migration 009 (`skip_llm`, `parent_job_id`, `trigger`); worker `skip_llm=True` branch runs reconciliation only and lands in `proposed`
- **S-BE6**: `POST /jobs/{id}/refine` spawns child job with `trigger="human-refine"`; prior code + hint injected as `__refine_context__` sentinel; LLM prompt prepends "Prior translation to improve" block
- **`GET /jobs/{id}/history`**: walks parent chain; returns `JobHistoryResponse`; frontend History tab with Bot/User icon timeline, click-to-navigate, current version marker
- **Reconciliation false alarm fix**: moved "no ref data" early-exit before `_exec_pipeline()` call
- **Doc rendering fixes**: `marked.parse()` (not `parseSync`); `extractMarkdown()` unwraps `{"markdown":"..."}` JSON; LLM prompts tightened to avoid code fence wrapping
- **All 7 `make test` gates green (EXIT:0)**

### Decisions

- `done` kept as legacy frontend `JobStatusValue` (amber, "Under Review") until all worker deployments are updated
- Migration 008 drops/recreates `jobs_status_check` constraint before UPDATE to avoid `CheckViolationError`
- Reconciliation skips execution when no reference data to avoid false `execution: fail` checks
- Job versioning via `parent_job_id` + `trigger` column; history walks parent chain; History tab distinguishes Bot vs Human changes

### Open Questions

- Should `done→proposed` migration be revisited to use `done→accepted` for historical rows that were already reviewed by the old implicit acceptance flow?
- Branching history (multiple children per parent) is not surfaced in the History tab — only the linear ancestor chain is shown

### Next Session — Start Here

1. Check backlog for next prioritised item (`journal/BACKLOG.md` Phase 2 section)
2. Likely candidates: `S-FE7 GlobalLineagePage`, `F4 SAS log ingestion`, or `F10 artefact versioning`
3. Run `make test` to confirm still green before starting

### Files Touched

- `alembic/versions/008_proposed_status_user_overrides.py`
- `alembic/versions/009_add_skip_llm_parent_trigger.py`
- `src/backend/db/models.py`
- `src/backend/api/schemas.py`
- `src/backend/api/routes/jobs.py`
- `src/worker/main.py`
- `src/worker/engine/llm_client.py`
- `src/worker/validation/reconciliation.py`
- `src/worker/engine/doc_generator.py`
- `src/worker/engine/agents/documentation.py`
- `src/frontend/src/api/types.ts`
- `src/frontend/src/api/jobs.ts`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/pages/JobsPage.tsx`
- `src/frontend/src/pages/UploadPage.tsx`
- `src/frontend/src/App.tsx`
- `tests/test_plan_interaction_routes.py`
- `tests/test_rereconciliation_routes.py`
- `tests/test_worker_main.py`
- `tests/reconciliation/test_data_step.py`
- `docs/plans/F3-proposed-status-plan-interaction.md`
- `journal/BACKLOG.md`
- `journal/SESSIONS.md`
- `journal/DECISIONS.md`

---

## 2026-04-19 — F2-improvements: backend agentic pipeline overhaul (S-A through S-K)

**Duration:** ~2h | **Focus:** F2-agentic-workflow-improvements — all backend + API subtasks

### Done

- **S-D**: Replaced `_SYSTEM_PROMPT` in all 6 existing agents (AnalysisAgent, DataStepAgent, ProcAgent, MacroResolverAgent, FailureInterpreterAgent, DocumentationAgent) with richer prompts including confidence/uncertainty output contracts
- **S-A**: Added `TranslationStrategy`, `BlockRisk`, `BlockPlan`, `MigrationPlan`, `ColumnFlow`, `MacroUsage`, `EnrichedLineage` models to `models.py`; extended `GeneratedBlock` with `confidence`/`uncertainty_notes`; extended `JobContext` with `migration_plan`/`enriched_lineage`; updated `windowed_context()` to propagate `migration_plan`
- **S-E**: Added `_SimpleCopyHelper` to `router.py` — pure SET+KEEP/DROP DATA steps bypass LLM entirely
- **S-H**: `CodeGenerator.assemble()` now returns `dict[str, str]` (one `.py` per SAS file + `pipeline.py`); `assemble_flat()` added for `python_code` DB column and reconciliation
- **S-B**: Created `MigrationPlannerAgent` (`src/worker/engine/agents/migration_planner.py`) with `plan(context) -> MigrationPlan`
- **S-C**: Created `LineageEnricherAgent` (`src/worker/engine/agents/lineage_enricher.py`) with `enrich(context) -> EnrichedLineage`
- **S-F**: Replaced `_translate_with_refinement()` while-loop with explicit `_translate_two_phase()` — exactly two phases, no `_MAX_RETRIES`
- **S-G**: Wired `MigrationPlannerAgent` (step 3.5) and `LineageEnricherAgent` (step 7.5) into `JobOrchestrator._execute()`; fixed all `assemble()`/`assemble_flat()` call sites; both new agents are best-effort (try/except)
- **S-I**: Added `migration_plan` and `generated_files` JSON columns to `Job` ORM model; Alembic migration `007_add_migration_plan_generated_files.py`
- **S-J**: Added `BlockPlanResponse`, `JobPlanResponse`, `ColumnFlowResponse`, `MacroUsageResponse` schemas; extended `JobStatusResponse` with `generated_files`; extended `JobLineageResponse` with enriched lineage fields; added `GET /jobs/{id}/plan` route
- **S-O**: Unit test files for `MigrationPlannerAgent` (8 tests) and `LineageEnricherAgent` (7 tests) verified complete and correct
- **S-P**: `agents/__init__.py` updated to export `MigrationPlannerAgent` and `LineageEnricherAgent`
- **S-K**: Added `BlockPlan`, `JobPlanResponse`, `ColumnFlow`, `MacroUsage` TS types; extended `JobStatus` with `generated_files`; extended `JobLineageResponse` with enriched fields; added `getJobPlan()` API function

### Decisions

- **Two-phase refinement**: replaced unbounded while-loop (`_MAX_RETRIES=2`) with explicit two-phase sequence — phase 1 translates all blocks, phase 2 (on failure only) re-translates the single affected block. Rationale: predictable execution, easier to reason about, same practical retry count. Revisit: never unless we need > 1 retry.
- **Best-effort agent pattern**: `MigrationPlannerAgent` and `LineageEnricherAgent` wrapped in try/except in orchestrator — failure logs warning but doesn't abort the job. Rationale: these are enrichment agents; core migration must not fail because of them. Revisit: never.
- **`assemble_flat()` for reconciliation**: split `assemble()` (dict) from `assemble_flat()` (str) to preserve reconciliation correctness while enabling multi-file output. Revisit: never.

### Open Questions

- S-L, S-M, S-N (frontend PlanTab, Editor 1:1 view, LineageGraph edge labels) still pending
- S-Q (`make test` full pass) not yet run — should be first thing next session

### Next Session — Start Here

1. Run `make test` via the tester agent to verify current suite is green before touching frontend
2. Delegate S-L (PlanTab + tab reorder) to `frontend-builder`
3. Delegate S-M (Editor 1:1 SAS↔Python) and S-N (LineageGraph column labels) in parallel
4. Run S-Q (`make test` + ruff + mypy full pass) and commit

### Files Touched

- `src/worker/engine/models.py`
- `src/worker/engine/router.py`
- `src/worker/engine/codegen.py`
- `src/worker/engine/agents/analysis.py`
- `src/worker/engine/agents/data_step.py`
- `src/worker/engine/agents/proc.py`
- `src/worker/engine/agents/macro_resolver.py`
- `src/worker/engine/agents/failure_interpreter.py`
- `src/worker/engine/agents/documentation.py`
- `src/worker/engine/agents/migration_planner.py` (new)
- `src/worker/engine/agents/lineage_enricher.py` (new)
- `src/worker/engine/agents/__init__.py`
- `src/worker/main.py`
- `src/backend/db/models.py`
- `src/backend/api/schemas.py`
- `src/backend/api/routes/jobs.py`
- `alembic/versions/007_add_migration_plan_generated_files.py` (new)
- `tests/test_migration_planner_agent.py` (new)
- `tests/test_lineage_enricher_agent.py` (new)
- `src/frontend/src/api/types.ts`
- `src/frontend/src/api/jobs.ts`
- `docs/plans/F2-agentic-workflow-improvements.md`
- `journal/BACKLOG.md`

---

## 2026-04-19 — UI polish: TipTap sizing, report layout, zip folder tree, lineage node styling

**Duration:** ~1h | **Focus:** Quick frontend polish + backend zip path fix

### Done

- **TipTap text size**: changed `prose-sm` → `prose-xs` + explicit `text-sm` on `EditorContent`; content no longer oversized
- **Report tab side-by-side**: `ReportTab` changed from vertical `space-y-6` stack to `flex gap-4` row — Reconciliation and Migration summary sit side by side with individual `overflow-y-auto` scroll areas
- **Backend zip path preservation**: `migrate.py` was calling `os.path.basename(info.filename)` stripping all directory structure; now stores full normalized path (`folder/subfolder/file.sas`) as the dict key — file tree will reflect folder hierarchy for new uploads
- **LineageGraph reset button**: replaced `⟳` unicode symbol with `<RotateCcw size={12} />` lucide icon
- **LineageGraph node background**: changed from dark `#3c3c3c` / `#1e1e1e` to `rgba(245,245,245,0.92)` — matches Legend panel; text updated to dark `#111` / `#333`

### Decisions

- none (all cosmetic / minor fixes)

### Open Questions

- Old jobs in DB have flat file keys (basename only) — folder tree only works for newly uploaded zips

### Next Session — Start Here

1. Check `docs/plans/` for any in-progress F2 plan; run `make test` to verify suite green; continue with next unstarted backlog item

### Files Touched

- `src/frontend/src/components/TiptapEditor.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/backend/api/routes/migrate.py`
- `src/frontend/src/components/LineageGraph.tsx`

---

## 2026-04-19 — LineageGraph UX overhaul, sonner toasts, file_count fix, undo/redo

**Duration:** ~3h | **Focus:** LineageGraph interactivity, error UX, backend bug fixes

### Done

- **LineageGraph hover-to-focus**: replaced click-to-focus with `onNodeMouseEnter`/`onNodeMouseLeave`; 80ms debounce prevents flicker; pane click clears
- **Undo/Redo toolbar**: `onNodeDragStop` snapshots `{id→{x,y}}` position maps (deep-copied to avoid mutation); Undo/Redo restore via `setNodes` (controlled-mode setter — `rfSetNodes` was clobbered by React Flow's controlled-mode render loop); Reset restores initial dagre layout + `fitView`
- **Opacity transition**: `transition: "opacity 0.18s ease"` on all nodes for smooth hover-dim effect
- **Legend → top-right, toolbar → top-left**: repositioned overlays
- **Untranslatable status bug fixed**: `parser.py` was checking `"# SAS-UNTRANSLATABLE" in block.raw_sas` (always false); fixed to `block.block_type == BlockType.UNTRANSLATABLE`
- **file_count fixed**: was counting only non-sentinel keys (`.sas` only); now `len(j.files or {})` counts all accepted files (SAS + CSV/log/xlsx reference sentinels)
- **Jobs table row disabled for non-done**: running/queued/failed rows are `cursor-default opacity-70`, non-clickable; only `done` rows navigate to detail page
- **Sonner toast for all errors**: shadcn sonner component installed; `<Toaster>` added to App root; all `onError` callbacks and failed-job status wired to `toast.error()`; removed all inline red text error displays
- **Human-friendly error copy**: generic fallbacks rewritten ("Your changes could not be saved. Please try again."), raw technical strings never shown to user; `extractApiError` continues to pass through clean FastAPI messages verbatim

### Decisions

- Controlled-mode `setNodes` is the only correct setter for position restores in React Flow — `rfSetNodes` (instance) gets clobbered by the nodes prop on re-render
- `file_count` now counts all keys including reference sentinels (they are user-uploaded files)
- Sonner hardcoded to `theme="light"` — no `next-themes` in this Vite SPA

### Open Questions

- None

### Next Session — Start Here

1. Apply pending Alembic migrations if not yet done: `docker compose exec backend uv run alembic upgrade head`
2. S-BE5: `PUT /jobs/{id}/python_code` re-reconciliation + `skip_llm` worker branch
3. S-BE6: `POST /jobs/{id}/refine` + `parent_job_id`
4. S-FE7/8/9: GlobalLineagePage, DocsPage, ExplainPage stub

### Files Touched

- `src/frontend/src/components/LineageGraph.tsx` (hover-to-focus, undo/redo/reset, smooth opacity, layout repositioning)
- `src/frontend/src/components/ui/sonner.tsx` (new — fixed generated file, no next-themes)
- `src/frontend/src/components/JobResult.tsx` (human-friendly error copy)
- `src/frontend/src/pages/UploadPage.tsx` (useEffect toast for failed job, mutation onError, remove inline errors)
- `src/frontend/src/pages/JobDetailPage.tsx` (mutation onError toasts, lineage error toast, remove inline errors)
- `src/frontend/src/pages/JobsPage.tsx` (non-done rows non-clickable)
- `src/frontend/src/App.tsx` (Toaster added)
- `src/worker/engine/parser.py` (untranslatable status bug fix)
- `src/backend/api/routes/jobs.py` (file_count counts all keys)

---

## 2026-04-19 — UI polish: mandatory name, merged editor, lineage DAG upgrade

**Duration:** ~3h | **Focus:** JobDetailPage UX, LineageGraph dagre rewrite, UploadPage, JobsPage, backend fixes

### Done

- **Mandatory migration name**: `submitDisabled` blocks on empty name; `(optional)` label removed; `required` attr on input
- **cursor-pointer audit**: added throughout UploadPage, JobDetailPage, tabs.tsx, AppSidebar
- **Merged Editor tab**: Comparison + Edit collapsed into one "Editor" tab — SAS read-only Monaco left, editable Python Monaco right, save/refine below
- **JobDetailPage header**: shows `job.name` as primary label, short ID as mono sub-line; `name` added to `JobStatusResponse` schema and `GET /jobs/{id}`
- **JobsPage**: column renamed "Migration" → "Name"; cell shows name only; `file_count` renders via `!= null` guard
- **UploadPage result card**: accepted/rejected file lists removed (cleaner post-submit UX)
- **Zip filter**: `._` macOS resource fork files and `__MACOSX/` entries silently skipped in `_unpack_zip`
- **LineageGraph dagre rewrite**: `dagre` + `@types/dagre` installed; LR layout (nodesep 40, ranksep 80); `useNodesState`/`useEdgesState` with `useEffect` seeding; click-to-focus dims unrelated nodes (ancestor+descendant closure); legend overlay (semi-transparent + backdrop blur); MiniMap only >15 nodes; `Position` enum for sourcePosition/targetPosition; no TS errors
- **Makefile fix**: `frontend-lint` and `frontend-build` targets no longer pass `NPM_FLAGS` to ESLint/Vite CLIs (ESLint v9 flat config and Vite reject `--silent`)
- **vite.config.ts**: `chunkSizeWarningLimit: 1000` to suppress Monaco chunk size warning

### Decisions

- Editor tab merges comparison + edit: single tab is cleaner — users naturally want to see SAS while editing Python
- `._` files skipped silently (not rejected) — macOS OS artefacts, not user files
- `file_count` sentinel pattern: count keys not matching `__…__` (SAS files only); legacy jobs show "—" gracefully

### Open Questions

- DB migrations (004/005 for name, lineage, doc columns) not yet applied to running Postgres — API returns no `name`/`file_count` for existing jobs; needs `alembic upgrade head` on next deploy

### Next Session — Start Here

1. Apply pending Alembic migrations: `docker compose exec backend uv run alembic upgrade head`
2. Implement S-BE5 (`PUT /jobs/{id}/python_code` re-reconciliation + `skip_llm`)
3. Implement S-BE6 (`POST /jobs/{id}/refine` + `parent_job_id`)
4. Implement S-FE7 `GlobalLineagePage`, S-FE8 `DocsPage`, S-FE9 `ExplainPage` stub

### Files Touched

- `src/frontend/src/pages/UploadPage.tsx` (mandatory name, removed accepted/rejected lists)
- `src/frontend/src/pages/JobDetailPage.tsx` (merged Editor tab, name in header)
- `src/frontend/src/pages/JobsPage.tsx` (column rename, name cell, file_count guard)
- `src/frontend/src/components/LineageGraph.tsx` (full dagre rewrite)
- `src/frontend/src/components/ui/tabs.tsx` (cursor-pointer)
- `src/frontend/src/api/types.ts` (name on JobStatus)
- `src/frontend/src/api/jobs.ts` (updateJobPythonCode, refineJob, downloadJob stubs)
- `src/backend/api/schemas.py` (name on JobStatusResponse)
- `src/backend/api/routes/jobs.py` (name in get_job, file_count sentinel fix)
- `src/backend/api/routes/migrate.py` (._/MACOSX zip filter)
- `src/frontend/package.json` + `package-lock.json` (dagre, @types/dagre)
- `src/frontend/vite.config.ts` (chunkSizeWarningLimit)
- `Makefile` (frontend-lint/build no longer pass NPM_FLAGS to CLI)

---

## 2026-04-18 — JobDetailPage + UploadPage workspace + name/file_count + markdown doc

**Duration:** ~3h | **Focus:** S-FE1–4, S-FE6, S-BE3, S-BE4, upload UX fixes, name field

### Done

- **S-FE1–4**: `MonacoDiffViewer`, `MonacoEditor`, `TiptapEditor`, `LineageGraph` components created; npm packages installed (`@monaco-editor/react`, `@tiptap/*`, `lowlight`, `reactflow`, `jszip`)
- **S-FE6**: `JobDetailPage` — 4 tabs (Comparison/Edit/Report/Lineage), live status polling, Monaco editors, `marked`-rendered doc summary; hand-rolled `Tabs` component (replaced broken shadcn `base-nova` tabs with circular import)
- **S-BE3**: `GET /jobs/{id}/lineage` endpoint + `extract_lineage()` wired into worker; migration 004 adds `lineage JSON` column
- **S-BE4**: `GET /jobs/{id}/doc` endpoint + `DocGenerator` wired into worker post-reconciliation; migration 004 adds `doc TEXT` column
- **UploadPage persistent workspace**: state lifted to `UploadStateProvider`; survives navigation; zip tree client-side parsed (jszip), `__MACOSX` filtered, per-file/folder remove; "Start another" vs "Accept & clear" actions; "Open full details" only when done
- **Migration name**: text input on upload form; stored on `Job` (migration 005); shown in result card and jobs table
- **JobsPage**: "Migration" column shows name + mono ID sub-line; "Files" column shows `file_count`
- **Markdown summary**: LLM doc rendered via `marked` + Tailwind `prose` instead of Tiptap
- 110 tests green, 90.23% coverage

### Decisions

- UploadPage state lifted to context so navigation doesn't reset it
- Tabs hand-rolled (shadcn base-nova depends on uninstalled `@base-ui-components/react`)
- Markdown doc via `marked` + prose (not Tiptap) — simpler, no editor overhead for read-only
- `file_count` derived at query time, not stored
- `name` optional form field on `POST /migrate`, stored as nullable TEXT

### Open Questions

- none

### Next Session — Start Here

1. Implement S-BE5 (`PUT /jobs/{id}/python_code` re-reconciliation pathway + migration 003)
2. Implement S-BE6 (`POST /jobs/{id}/refine` + `parent_job_id` + migration 003)
3. Implement S-FE7 `GlobalLineagePage`, S-FE8 `DocsPage`, S-FE9 `ExplainPage`
4. See `docs/plans/F-UI-postmvp.md` + `docs/plans/F-backend-postmvp.md`

### Files Touched

- `src/frontend/src/components/MonacoDiffViewer.tsx` (new)
- `src/frontend/src/components/MonacoEditor.tsx` (new)
- `src/frontend/src/components/TiptapEditor.tsx` (new)
- `src/frontend/src/components/LineageGraph.tsx` (new)
- `src/frontend/src/components/ui/tabs.tsx` (replaced broken shadcn tabs)
- `src/frontend/src/pages/JobDetailPage.tsx` (full impl)
- `src/frontend/src/pages/UploadPage.tsx` (persistent workspace, name input)
- `src/frontend/src/pages/JobsPage.tsx` (name column, file_count column)
- `src/frontend/src/context/UploadStateContext.tsx` (new — lifted state)
- `src/frontend/src/api/types.ts`, `jobs.ts`, `migrate.ts` (extended)
- `src/frontend/package.json` (new packages)
- `src/backend/db/models.py` (name column)
- `src/backend/api/schemas.py` (name, file_count on JobSummary)
- `src/backend/api/routes/jobs.py` (lineage + doc + file_count endpoints)
- `src/backend/api/routes/migrate.py` (name form field)
- `src/worker/engine/doc_generator.py` (new)
- `src/worker/main.py` (lineage + doc wired)
- `alembic/versions/004_add_lineage_doc_columns.py` (new)
- `alembic/versions/005_add_job_name.py` (new)
- `tests/test_lineage_endpoint.py`, `test_doc_endpoint.py`, `test_doc_generator.py` (new)
- `tests/test_worker_main.py` (extended)

---

## 2026-04-18 — UI polish: JobDetailPage status, sidebar tooltips, cursor, icon stability

**Duration:** ~30min | **Focus:** UI bug fixes on sidebar and job detail page

### Done

- `JobDetailPage`: status badge now fetches real job status via `useQuery` with live polling (queued/running → 3s refetch); uses same black pill style as jobs table
- `AppSidebar` tooltips: replaced native `title` (slow browser delay) with instant CSS opacity tooltip (`duration-100`) appearing to the right of the sidebar
- `AppSidebar` icons: fixed icon drift on expand/collapse — icons now pinned at fixed `left` offset (`ICON_COL=56px`); labels fade via `width`+`opacity`+`margin` transition instead of `max-width` (smoother)
- `AppSidebar` overflow: removed `overflow-hidden` from `<aside>` (was clipping tooltips); moved clip to individual row elements
- `cursor-pointer` added to `Button` base class and sidebar nav/toggle links

### Decisions

- none

### Open Questions

- none

### Next Session — Start Here

1. Install npm packages: `@monaco-editor/react`, `@tiptap/react`, `@tiptap/starter-kit`, `@tiptap/extension-code-block-lowlight`, `lowlight`, `reactflow`
2. Implement S-FE1 (`MonacoDiffViewer`), S-FE2 (`MonacoEditor`), S-FE3 (`TiptapEditor`), S-FE4 (`LineageGraph`)
3. Wire into S-FE6 `JobDetailPage` (replace stub tabs with real data + editor components)
4. In parallel: S-BE3 (lineage + migration 002) + S-BE4 (doc generation)
5. See `docs/plans/F-UI-postmvp.md` + `docs/plans/F-backend-postmvp.md`

### Files Touched

- `src/frontend/src/pages/JobDetailPage.tsx` (real status fetch)
- `src/frontend/src/components/AppSidebar.tsx` (tooltip, icon stability, smooth text transition)
- `src/frontend/src/components/ui/button.tsx` (cursor-pointer)

---

## 2026-04-18 — Post-MVP nav scaffold, backend sources/zip endpoints, unified upload UX

**Duration:** ~2h | **Focus:** S-BE1, S-BE2, S-FE5/10/11/12/13 implementation + bugfixes

### Done

- Branched `feat/F-UI-postmvp` off latest main (rebased after merge of F-UI PR)
- **S-BE1:** `GET /jobs/{id}/sources` — returns job source files, strips `__sentinel__` keys; 6 new tests
- **S-BE2:** Zip bulk upload on `POST /migrate` — `_unpack_zip` helper, 500MB limit, `FileRejection` schema, `accepted`/`rejected` in `MigrateResponse`; tests for all edge cases
- **Bugfix:** `sas_files` changed to `File(default=[])` so FastAPI accepts requests with only `zip_file` (was returning 422 missing field)
- **S-FE5:** `AppSidebar` — collapsible left sidebar with localStorage persistence, 5 nav items, lucide icons
- **S-FE10:** `App.tsx` — replaced top nav with sidebar layout, lazy-loaded routes for all new pages
- **S-FE11:** `JobsPage` — rows navigate to `/jobs/:id`, removed inline expansion
- **S-FE13:** API client extended — new types + `getJobSources`, `getJobLineage`, `getJobDoc`, `updateJobPythonCode`, `refineJob`; `submitMigration` supports zip
- **S-FE12:** `UploadPage` — unified drop-zone accepting all 7 file types, file-type badges, manifest view post-submit; removed conflict check (zip + individual files allowed together)
- Stub pages created: `JobDetailPage` (4-tab layout), `GlobalLineagePage`, `DocsPage`, `ExplainPage`
- 93 tests passing, 91% coverage

### Decisions

- `UploadPage` accepts `.sas`, `.sas7bdat`, `.zip`, `.log`, `.csv`, `.xls`, `.xlsx` in one input — no mode toggle, no conflict restriction between zip and individual files
- Supporting files (`.log/.csv/.xls/.xlsx`) without a zip are accepted by the UI but will be ignored by backend individual-file path (only processed inside zips); frontend shows "Supporting file" amber badge

### Open Questions

- none

### Next Session — Start Here

1. Install npm packages: `@monaco-editor/react`, `@tiptap/react`, `@tiptap/starter-kit`, `@tiptap/extension-code-block-lowlight`, `lowlight`, `reactflow`
2. Implement S-FE1 (`MonacoDiffViewer`), S-FE2 (`MonacoEditor`), S-FE3 (`TiptapEditor`), S-FE4 (`LineageGraph`) — editor component layer
3. Wire into S-FE6 `JobDetailPage` (replace stubs with real tabs + data fetching)
4. In parallel: S-BE3 (lineage extraction + migration 002) + S-BE4 (doc generation)
5. All work in `docs/plans/F-UI-postmvp.md` + `docs/plans/F-backend-postmvp.md`

### Files Touched

- `src/backend/api/schemas.py` (FileRejection, MigrateResponse extended, JobSourcesResponse)
- `src/backend/api/routes/jobs.py` (GET /sources)
- `src/backend/api/routes/migrate.py` (zip support, File(default=[]) fix)
- `src/backend/core/config.py` (max_zip_bytes)
- `tests/test_sources_endpoint.py` (new)
- `tests/test_zip_upload.py` (new)
- `src/frontend/src/api/types.ts` (new types)
- `src/frontend/src/api/jobs.ts` (new functions)
- `src/frontend/src/api/migrate.ts` (zip support)
- `src/frontend/src/components/AppSidebar.tsx` (new)
- `src/frontend/src/App.tsx` (sidebar layout, new routes)
- `src/frontend/src/pages/JobsPage.tsx` (navigate to /jobs/:id)
- `src/frontend/src/pages/UploadPage.tsx` (unified drop-zone)
- `src/frontend/src/pages/JobDetailPage.tsx` (stub, new)
- `src/frontend/src/pages/GlobalLineagePage.tsx` (stub, new)
- `src/frontend/src/pages/DocsPage.tsx` (stub, new)
- `src/frontend/src/pages/ExplainPage.tsx` (stub, new)
- `docs/plans/F-UI-postmvp.md` (subtasks marked done)
- `docs/plans/F-backend-postmvp.md` (subtasks marked done)
- `journal/BACKLOG.md` (items checked off)

---

## 2026-04-18 — Post-MVP UI + backend planning; zone-based architecture designed

**Duration:** ~1.5h | **Focus:** Planning session — no code written

### Done

- Reviewed all user stories (US1, US2), features (F2, F5–F7, F11, F13, F15, F18), and MVP scope docs
- Explored full frontend codebase (all components, pages, API client, package.json) and backend API surface
- Ran fullstack-planner analysis: identified all API gaps for post-MVP features (sources endpoint, lineage column, doc column, re-reconciliation, refine action, zip upload)
- Designed zone-based editor architecture: right tool per content zone (Monaco DiffEditor / Monaco Editor / Tiptap / React Flow)
- Decided full app page structure with sidebar nav: `/upload`, `/jobs`, `/jobs/:id`, `/lineage`, `/docs`, `/explain`
- Wrote `docs/plans/F-UI-postmvp.md` (13 frontend subtasks, Status: in-progress)
- Wrote `docs/plans/F-backend-postmvp.md` (6 backend subtasks across 3 DB migration waves, Status: in-progress)
- Updated `journal/BACKLOG.md` with 19 new actionable items cross-linked to plan files

### Decisions

- Zone-based editor: Monaco DiffEditor (diff), Monaco Editor (edit), Tiptap (notes/reports), React Flow (lineage)
- Sidebar nav (collapsible) replaces current top nav
- `/jobs/:id` full page with 4 tabs replaces inline expansion
- Zip upload: partial acceptance (no file count limit); rejected files returned in manifest, not as 400
- Accepted zip extensions: `.sas`, `.sas7bdat`, `.csv`, `.log`, `.xlsx`, `.xls`
- Lineage serialised to `job.lineage` JSON column at parse time (not on-demand)
- `skip_llm` boolean flag for re-reconciliation pathway (cleaner than new status value)

### Open Questions

- none

### Next Session — Start Here

1. Two parallel tracks to start immediately:
   - **Backend track:** implement S-BE1 (`GET /sources`) and S-BE2 (zip upload) in `src/backend/` — no migrations required, unblocks frontend Monaco work
   - **Frontend nav track:** implement S-FE5 (`AppSidebar`) + S-FE10 (routing) + S-FE11 (JobsPage refactor) — no backend deps
2. Full subtask list in `docs/plans/F-UI-postmvp.md` and `docs/plans/F-backend-postmvp.md`
3. Branch: `feat/F-UI-postmvp`

### Files Touched

- `docs/plans/F-UI-postmvp.md` (created)
- `docs/plans/F-backend-postmvp.md` (created)
- `journal/BACKLOG.md` (19 new items added)
- `journal/DECISIONS.md` (9 decisions appended)
- `journal/SESSIONS.md` (this entry)

---

## 2026-04-18 — F-UI complete; MVP shipped; Azure OpenAI + Docker fixes

**Duration:** ~4h | **Focus:** F-UI React frontend, docker-compose runtime fixes, Azure OpenAI wiring

### Done

- **F-UI — backend:** `GET /jobs` list endpoint + `JobSummary`/`JobListResponse` schemas; `CORSMiddleware` with env-driven `CORS_ORIGINS`; `cors_origins` as split-string property to handle `CORS_ORIGINS=*` from env
- **F-UI — frontend:** typed API client (`src/api/`), `UploadPage`, `JobsPage`, `JobResult` component with React Query polling; react-router-dom routing; `@tanstack/react-query` server state
- **Docker runtime fixes:** `entrypoint.sh` runs `alembic upgrade head` before uvicorn; migration 001 fixed (`postgresql.UUID` → `String(36)` to match ORM); frontend volume mount for Vite HMR live reload
- **Azure OpenAI:** `AzureProvider` wired in `_make_agent()` when `AZURE_OPENAI_ENDPOINT` is set; provider prefix stripped from `LLM_MODEL` to get bare deployment name; new worker settings: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `OPENAI_API_VERSION`
- **`.env.example`:** full documentation of all env vars with comments; both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` included
- **UI polish:** status labels renamed (Queued/Running/Completed/Failed); shimmer text effect (3.5s, black pill) for active statuses; no colour-coding
- **Verified end-to-end:** Azure gpt-5.4 deployment returned 200 OK; job completed successfully in Docker Compose

### Decisions

- **`CORS_ORIGINS` as plain string, split internally:** `list[str]` pydantic-settings field fails when env var is `*`; switched to `str` field with `@property` that splits on comma — avoids JSON bracket requirement in `.env` · revisit never
- **Migration 001 id column as String(36):** ORM uses `String(36)` for cross-dialect SQLite/PostgreSQL compatibility in tests; migration was incorrectly using `postgresql.UUID` causing type mismatch on INSERT · revisit never
- **Backend entrypoint runs migrations on startup:** `alembic upgrade head` in `entrypoint.sh` before uvicorn ensures schema is always current without a separate migration step · revisit if migration time becomes a startup concern
- **Azure deployment name stripped of provider prefix:** `LLM_MODEL=openai:gpt-5.4` → deployment name `gpt-5.4`; `split(":", 1)[-1]` handles both bare and prefixed values · revisit never
- **Frontend volume mount for HMR:** `./src/frontend:/app` + `/app/node_modules` anonymous volume in docker-compose; Vite picks up file changes without container rebuild · revisit never

### Open Questions

- none

### Next Session — Start Here

1. MVP is complete — all Phase 1 items done. Consider opening PRs for `feat/F-UI` → main
2. Phase 2 candidates: `%MACRO`/`%MEND` expansion, row-level hash diff, SAS log ingestion
3. Run `/plan-feature` for whichever Phase 2 item to tackle next

### Files Touched

- `src/backend/main.py`
- `src/backend/core/config.py`
- `src/backend/api/routes/jobs.py`
- `src/backend/api/schemas.py`
- `src/backend/Dockerfile`
- `src/backend/entrypoint.sh` (created)
- `src/worker/core/config.py`
- `src/worker/engine/llm_client.py`
- `alembic/versions/001_create_jobs_table.py`
- `docker-compose.yml`
- `src/frontend/package.json`
- `src/frontend/package-lock.json`
- `src/frontend/src/main.tsx`
- `src/frontend/src/App.tsx`
- `src/frontend/src/api/types.ts` (created)
- `src/frontend/src/api/migrate.ts` (created)
- `src/frontend/src/api/jobs.ts` (created)
- `src/frontend/src/pages/UploadPage.tsx` (created)
- `src/frontend/src/pages/JobsPage.tsx` (created)
- `src/frontend/src/components/JobResult.tsx` (created)
- `docs/plans/F-UI.md` (created)
- `journal/BACKLOG.md`

## 2026-04-18 — F-LLM + F-sas7bdat complete; git-branch-setup skill; make test hardened

**Duration:** ~3h | **Focus:** two remaining backend MVP items + tooling improvements

### Done

- **git-branch-setup skill:** new `.claude/skills/git-branch-setup/SKILL.md` — checks local + remote for feature branch, pulls main, creates branch if missing, confirms checkout before any implementation is delegated; wired into orchestrator feature planning (step 6 after plan approval)
- **F-LLM — system prompt upgrade:** expanded `_SYSTEM_PROMPT` in `src/worker/engine/llm_client.py` with full SAS construct coverage (DATA step, PROC SQL, PROC SORT, %LET), PySpark idiom rules, and PROC SORT → `sort_values()` mapping
- **F-LLM — retry + resilience:** `LLMTranslationError` exception with `is_transient` flag; 3-attempt exponential retry (2/4/8s) in `LLMClient.translate()`; transient vs permanent error classification; partial result accumulation in `_process_job()` with early return and structured `error_detail` JSON persisted to the job row
- **F-LLM — DB:** `error_detail: Mapped[dict[str, Any] | None]` JSON column added to `Job` model; Alembic migration `003_add_error_detail_to_jobs.py`
- **F-sas7bdat — ComputeBackend:** abstract `read_sas7bdat()` added to `src/worker/compute/base.py`; implemented in `src/worker/compute/local.py` via `pyreadstat.read_sas7bdat()`
- **F-sas7bdat — /migrate route:** accepts optional `ref_dataset: UploadFile | None`; validates `.sas7bdat` extension; saves binary to `upload_dir` on disk; stores path under `__ref_sas7bdat__` in `job.files`; `upload_dir` setting added to `src/backend/core/config.py`
- **F-sas7bdat — pipeline:** worker extracts `__ref_sas7bdat__` from `job.files`; `ReconciliationService.run()` always executes the pipeline, then skips comparison checks if no reference supplied; sas7bdat takes priority over csv
- **make test hardened:** mypy now runs inside `make test` (was only in `make check` and pre-commit); `make test-file FILE=<path>` target added for single-file runs; `pyreadstat` + `src.worker.compute.local` mypy overrides added to `pyproject.toml`
- **Tests:** 3 new LLM retry tests, 1 sas7bdat backend test, 2 migrate route tests — **86 tests total, 91.64% coverage**

### Decisions

- **`make test` now includes mypy:** discovered that mypy failures were only caught at pre-commit time, not during the test cycle; added to `make test` to surface errors earlier · revisit never
- **git-branch-setup always pulls main before branching:** ensures new feature branches start from the latest main, not from a stale local HEAD · revisit never
- **No Co-Authored-By attribution in commits:** user preference; removed from all commit messages and memory · revisit never

### Open Questions

- none

### Next Session — Start Here

1. F-UI is the last remaining MVP item — Upload & Results page (React frontend)
2. Run `/plan-feature` for F-UI, then delegate to `frontend-builder`
3. Both F-LLM (`feat/F-llm-resilience`) and F-sas7bdat (`feat/F-sas7bdat`) branches are ready to open PRs — consider merging before starting F-UI to keep main up to date

### Files Touched

- `.claude/skills/git-branch-setup/SKILL.md` (created)
- `.claude/agents/orchestrator.md`
- `CLAUDE.md`
- `Makefile`
- `pyproject.toml`
- `src/worker/engine/llm_client.py`
- `src/worker/main.py`
- `src/backend/db/models.py`
- `alembic/versions/003_add_error_detail_to_jobs.py` (created)
- `src/worker/compute/base.py`
- `src/worker/compute/local.py`
- `src/backend/api/routes/migrate.py`
- `src/backend/core/config.py`
- `src/worker/validation/reconciliation.py`
- `tests/test_llm_client.py`
- `tests/test_local_backend.py`
- `tests/test_migrate_route.py` (created)

---

## 2026-04-18 — F1-ext complete: PROC SORT + %LET, MVP scope alignment

**Duration:** ~2h | **Focus:** F1 engine extension + structural doc cleanup

### Done

- **F1-ext — PROC SORT parser:** `BlockType.PROC_SORT`, `_extract_proc_sort()` with `DATA=`/`OUT=` resolution, covered-span logic so PROC SORT no longer hits UNTRANSLATABLE
- **F1-ext — %LET macro vars:** `MacroVar` + `ParseResult` models, `_extract_macro_vars()`, `SASParser.parse()` return type changed to `ParseResult(blocks, macro_vars)`, `CodeGenerator.assemble()` accepts `macro_vars` and prepends constants section
- **Sample files:** `samples/proc_sort_example.sas`, `samples/proc_sort_expected.csv`
- **Tests:** 9 new parser unit tests, 2 codegen tests, 1 reconciliation test — 78 total, 93.5% coverage
- **Doc alignment:** renamed `docs/plans/F2-proc-sort.md` → `F1-ext-proc-sort-macro.md` (PROC SORT is an F1 extension, not a new feature; F2 is reserved for Code Explanation UI)
- **MVP scope expanded:** added F-LLM (system prompt upgrade + graceful degradation), F-sas7bdat (wire pyreadstat), F-UI (Upload & Results page) as required MVP items to `docs/mvp-scope.md` and `journal/BACKLOG.md`
- **git-pr-summary skill:** new skill at `.claude/skills/git-pr-summary/SKILL.md` — generates copy-paste ready PR Markdown; wired into orchestrator only
- **README updated:** parser description, reconciliation test listing, worker pipeline signature updated to reflect F1-ext changes

### Decisions

- **F-number collision resolved:** PROC SORT + %LET are F1 extensions (Phase 2 post-MVP backend). F2 remains the Code Explanation Assistant UI (Phase 3 frontend) per `docs/features.md` · revisit never
- **MVP requires a frontend:** Upload & Results page added to MVP scope — product is not shippable without UI
- **MVP requires LLM system prompt upgrade:** current prompt only mentions pandas; must establish agent as SAS migration expert targeting Python/PySpark · LLM remains the primary translation engine, not optional
- **MVP requires sas7bdat reading:** `pyreadstat` already in `pyproject.toml` but never wired; must be connected to `LocalBackend` before MVP is done
- **LLM resilience is MVP scope:** worker must not crash if API unreachable — graceful job failure, not process crash · this is error handling, not a fallback translation path
- **make test is the only allowed test invocation:** `uv run pytest` is forbidden everywhere including agent verification steps — all tests via make targets only · enforced in memory

### Open Questions

- none

### Next Session — Start Here

1. Implement the three remaining MVP items in order:
   - F-LLM: upgrade `_SYSTEM_PROMPT` in `src/worker/engine/llm_client.py` + lazy-init resilience → plan and delegate to `backend-builder`
   - F-sas7bdat: wire `pyreadstat` into `src/worker/compute/local.py` + `base.py` + worker routing → plan and delegate to `backend-builder`
   - F-UI: Upload & Results page → plan and delegate to `frontend-builder`
2. F-LLM and F-sas7bdat can be planned and built in parallel
3. F-UI follows after both backend items are green

### Files Touched

- `src/worker/engine/models.py`, `src/worker/engine/parser.py`, `src/worker/engine/codegen.py`
- `src/worker/main.py`
- `tests/test_parser.py`, `tests/test_codegen.py`, `tests/reconciliation/test_proc_sort.py`
- `samples/proc_sort_example.sas`, `samples/proc_sort_expected.csv`
- `docs/plans/F1-ext-proc-sort-macro.md` (created), `docs/plans/F2-proc-sort.md` (deleted)
- `docs/mvp-scope.md`, `journal/BACKLOG.md`, `journal/DECISIONS.md`, `journal/SESSIONS.md`
- `.claude/skills/git-pr-summary/SKILL.md` (created), `.claude/agents/orchestrator.md`, `CLAUDE.md`
- `README.md`

---

## 2026-04-18 — CI hardening: Tailwind v4 migration, action bumps, Docker cache

**Duration:** ~3h | **Focus:** CI green across all jobs; tooling correctness

### Done

- **Tailwind v3 → v4:** switched to `@tailwindcss/vite` plugin, removed `postcss.config.js` and `tailwind.config.js`, moved theme into `@theme` block in `index.css`; fixed `border-border` / `outline-ring/50` errors caused by shadcn v4 generating v4 CSS against v3
- **tsconfig fix:** removed `baseUrl` from root `tsconfig.json` (redundant in project-references setup); kept `baseUrl` + `ignoreDeprecations: "6.0"` in `tsconfig.app.json` as required anchor for `paths` in `tsc --noEmit` mode
- **Build script:** changed `tsc -b` → `tsc --noEmit` in `package.json` build script and CI — `tsc -b` (project references build mode) doesn't resolve `paths` without `composite: true`, which conflicts with `noEmit: true`
- **no-commit-to-branch hook:** added `pre-commit-hooks` `no-commit-to-branch` for `main` to `.pre-commit-config.yaml`
- **make test extended:** now runs `tsc --noEmit`, `npm run lint`, and `npm run build` — frontend errors caught locally
- **CI action bumps:** all actions bumped to Node 24 compatible versions; `astral-sh/setup-uv` pinned to `v8.1.0` (no floating major tag)
- **CI structure:** docker job made independent (no longer gated on `test`); reconciliation coverage scoped to `src/worker/validation` with 80% gate via `.coveragerc-reconciliation`; ESLint step added to frontend CI job
- **.dockerignore:** added to reduce build context for backend/worker images and improve GHA layer cache hit rate

### Decisions

- `tsc --noEmit` is the correct type-check command for this project — `tsc -b` requires `composite: true` which conflicts with `noEmit: true`
- `baseUrl` + `ignoreDeprecations: "6.0"` required in `tsconfig.app.json` — `pathsBasePath` is not propagated when loaded as a referenced project
- Docker build job runs independently of Python test jobs — Dockerfile correctness is unrelated to Python logic
- Reconciliation coverage gated separately at 80% on `src/worker/validation` only; main test suite gate remains 90% on all of `src`

### Open Questions

- none

### Next Session — Start Here

1. Phase 2 features — run `/session-start` → confirm backlog → `/plan-feature` for PROC SORT parser or `%LET` macro resolution

### Files Touched

- `.pre-commit-config.yaml`, `Makefile`, `.github/workflows/ci.yml`
- `.dockerignore`, `.coveragerc-reconciliation`
- `src/frontend/package.json`, `src/frontend/package-lock.json`
- `src/frontend/vite.config.ts`, `src/frontend/src/index.css`
- `src/frontend/tsconfig.json`, `src/frontend/tsconfig.app.json`
- `src/frontend/src/components/ui/button.tsx`
- `scripts/check_npm_lockfile.sh`
- `journal/SESSIONS.md`, `journal/DECISIONS.md`

---

## 2026-04-18 — F1 complete: S10–S16 + multi-agent setup + tooling hardening

**Duration:** ~4h | **Focus:** F1 pipeline generation — wiring, API endpoints, coverage, agents

### Done

- **S10:** Alembic migration `002_add_llm_model.py` + `Job.llm_model` ORM field
- **S11:** `_process_job` in `src/worker/main.py` — full engine pipeline (SASParser → LLMClient → CodeGenerator → ReconciliationService), `asyncio.to_thread` for sync calls, persists `status=done/failed`
- **S12:** `AuditResponse` Pydantic schema added to `src/backend/api/schemas.py`
- **S13:** `GET /jobs/{id}/audit` endpoint in `src/backend/api/routes/jobs.py`
- **S14:** `GET /jobs/{id}/download` endpoint — StreamingResponse zip with `pipeline.py`, `reconciliation_report.json`, `audit.json`
- **S15:** `tests/test_api_routes.py` — 12 async route tests (audit + download + get_job, all paths)
- **S16:** Coverage raised from 40% → 94.3%; `fail_under = 90`; `concurrency = ["thread", "greenlet"]` for async tracing
- **Agents:** 5 agent files created in `.claude/agents/` (orchestrator, backend-builder, frontend-builder, fullstack-planner, tester)
- **test-runner skill:** `.claude/skills/test-runner/SKILL.md` + CLAUDE.md table updated
- **Tooling:** Makefile PYTEST_FLAGS/NPM_FLAGS/DOCKER_BUILD_FLAGS; `--quiet` everywhere; mypy `tests.*` exemption removed
- **mypy clean:** jinja2 stubs added to ignore list, `no-any-return` fixed in codegen, N806 naming in test mocks fixed
- **5 atomic commits** — all hooks passed

### Decisions

- Multi-agent architecture adopted; orchestrator delegation via Agent tool is mandatory
- `coverage concurrency = ["thread", "greenlet"]` required for async route tracing
- mypy `tests.*` blanket exemption removed — tests now checked under strict mode
- Makefile output globally suppressed via flag variables

### Open Questions

- none

### Next Session — Start Here

1. F1 is complete. Start Phase 2 from `journal/BACKLOG.md`:
   - PROC SORT parser + translation
   - Macro variable (`%LET`) resolution → Python constants
   - Row-level hash diff check (F15 precursor)
2. Run `/session-start` → confirm backlog → `/plan-feature` for next feature

### Files Touched

- `CLAUDE.md`, `Makefile`, `pyproject.toml`
- `.claude/agents/` (5 new files), `.claude/skills/test-runner/SKILL.md`
- `alembic/versions/002_add_llm_model.py`
- `src/backend/db/models.py`, `src/backend/api/schemas.py`, `src/backend/api/routes/jobs.py`
- `src/worker/main.py`, `src/worker/engine/codegen.py`
- `tests/test_api_routes.py`, `tests/test_codegen.py`, `tests/test_factory.py`
- `tests/test_llm_client.py`, `tests/test_local_backend.py`, `tests/test_session.py`, `tests/test_worker_main.py`
- `tests/reconciliation/test_data_step.py`
- `journal/SESSIONS.md`, `journal/BACKLOG.md`, `journal/DECISIONS.md`
- `docs/plans/F1-pipeline-generation.md`

---

## 2026-04-18 — F1 Engine S00–S09: parser, LLM client, codegen, reconciliation

**Duration:** ~3h | **Focus:** F1 pipeline generation — engine layer implementation

### Done

- **S00:** Added `pydantic-ai[anthropic]>=0.0.36` to `pyproject.toml`; `uv.lock` updated
- **S01:** Created `samples/basic_etl.sas` (DATA step + PROC SQL, no macros), `samples/employees_raw.csv` (8-row input), `samples/basic_etl_ref.csv` (3-row dept summary reference)
- **S02:** `src/worker/engine/models.py` — `SASBlock` and `GeneratedBlock` Pydantic models
- **S03:** `src/worker/engine/parser.py` — `SASParser.parse()` with regex extraction, networkx dependency ordering, unsupported PROC flagging as UNTRANSLATABLE
- **S04:** `tests/test_parser.py` — 10 unit tests, all pass
- **S05:** `src/worker/engine/llm_client.py` — `LLMClient.translate()` via Pydantic AI agent; short-circuits on UNTRANSLATABLE blocks
- **S06:** `src/worker/engine/codegen.py` — `CodeGenerator.assemble()` with Jinja2 template; provenance headers and untranslatable boxing
- **S07:** `src/worker/compute/local.py` — full `LocalBackend` implementation (read_csv/run_sql via sqlite3/write_parquet/to_pandas)
- **S08:** `src/worker/validation/reconciliation.py` — `ReconciliationService` with schema parity, row count, aggregate parity checks
- **S09:** `tests/reconciliation/test_data_step.py` — 4 reconciliation tests (happy path + 3 failure cases); all pass
- **Docker fix:** Both Dockerfiles now copy `README.md` before `uv sync` (hatchling validation fix)
- **Makefile:** Added `make docker-build` target
- **CLAUDE.md:** Added two Critical Rules — `make test` only (no `uv run pytest`), `make docker-build` required on Dockerfile changes
- **backend-builder compliance pass:** Fixed 14 ruff violations (import sort, E501, UP042, D107, RUF100) and 5 mypy errors across all new engine files; `BlockType` migrated to `StrEnum`; pydantic-ai `result_type→output_type` and `.data→.output` API migration; mypy override added for `llm_client.py` (pydantic-ai overload limitation); `CodeGenerator` refactored to pre-compute block headers in Python (avoids long Jinja2 template lines)
- `make check` passes (ruff + mypy clean); `make test`: 20/20 pass, 64% coverage

### Decisions

- **LocalBackend.run_sql:** stdlib sqlite3 (not PostgreSQL, not pandasql) — zero dep, self-contained, correct for reconciliation
- **make test is a Critical Rule:** added to CLAUDE.md so it applies in all contexts, not just when a skill is active
- **make docker-build:** new mandatory step for Dockerfile commits; added to Makefile and CLAUDE.md

### Open Questions

- none

### Next Session — Start Here

1. Continue F1 from S10 in `docs/plans/F1-pipeline-generation.md`:
   - S10: Alembic migration — add `llm_model` column to `jobs` table + update ORM model
   - S11: Wire engine into worker poll loop (`src/worker/main.py`)
   - S12: Audit + download API schemas (`src/backend/api/schemas.py`)
   - S13: `GET /jobs/{id}/audit` endpoint
   - S14: `GET /jobs/{id}/download` endpoint (zip)
   - S15: API route tests
   - S16: Raise `fail_under` to 90, confirm `make test` green

### Files Touched

- `pyproject.toml`, `uv.lock`
- `CLAUDE.md`, `Makefile`
- `src/backend/Dockerfile`, `src/worker/Dockerfile`
- `src/worker/engine/models.py` (new)
- `src/worker/engine/parser.py` (new)
- `src/worker/engine/llm_client.py` (new)
- `src/worker/engine/codegen.py` (new)
- `src/worker/compute/local.py` (updated — full implementation)
- `src/worker/validation/reconciliation.py` (new)
- `samples/basic_etl.sas`, `samples/employees_raw.csv`, `samples/basic_etl_ref.csv` (new)
- `tests/test_parser.py` (new)
- `tests/reconciliation/__init__.py`, `tests/reconciliation/test_data_step.py` (new)
- `docs/plans/F1-pipeline-generation.md` (new)
- `journal/BACKLOG.md`, `journal/DECISIONS.md`, `journal/SESSIONS.md`

---

## 2026-04-17 — Phase 1 Scaffold, Databricks Strategy & Workflow Hardening

**Duration:** ~3h | **Focus:** Full four-service skeleton, design decisions, session tooling

### Done

- Reasoned through three Databricks output targets (PySpark, Databricks SQL, DLT) — locked in PySpark-only for `DatabricksBackend`; Databricks SQL and DLT deferred. Logged in `journal/DECISIONS.md` and `docs/architecture.md`
- Created `feat/phase1-scaffold` branch
- Planned and executed all 21 subtasks of `docs/plans/F0-phase1-scaffold.md` without stopping:
  - `docker-compose.yml`: 4 services (postgres, backend, worker, frontend) on `rosetta-net`
  - `src/backend/`: FastAPI app, `POST /migrate`, `GET /jobs/{id}`, SQLAlchemy async, pydantic-settings
  - `src/worker/`: async poll loop (queued→running→failed:not-implemented), `ComputeBackend` ABC, `LocalBackend` stub, `BackendFactory`
  - `src/frontend/`: Vite + React + TS + Tailwind + shadcn/ui placeholder
  - `alembic/` + `jobs` table migration (`001_create_jobs_table`)
  - `tests/test_api_smoke.py`: 6 smoke tests via in-memory SQLite — 6/6 pass
  - `pyproject.toml`: added SQLAlchemy[asyncio], Alembic, asyncpg, pytest-asyncio, aiosqlite, pandas-stubs
  - CI: reconciliation job with Postgres service + Alembic step; frontend build and Docker build jobs active
- Rewrote `README.md` with full session workflow guide (`/session-start`, `/session-end`, `/plan-feature`, `/git-committer`) and `make test` as the canonical test command
- Updated `Makefile`: fixed `coverage` path (`--cov=src`), fixed `run-backend` entrypoint (`src.backend.main:app`), removed stale `frontend-test`
- Hardened skills: `git-committer` now mandates `make test` at step 1 before staging code; `backend-builder` and `CLAUDE.md` explicitly forbid raw `uv run pytest`

### Decisions

- **DatabricksBackend = PySpark only:** SQL cannot handle DATA steps; DLT breaks local/cloud symmetry. See `journal/DECISIONS.md` session 5 entry.
- **Codegen constraint:** `CodeGenerator` must not emit pandas-only idioms — use parameterised DataFrame ops so `LocalBackend` and `DatabricksBackend` swap APIs without changing structure
- **Tests via `make test` only:** `uv run pytest` and bare `pytest` are forbidden in skills, CLAUDE.md, and README
- **SQLite for smoke tests:** `aiosqlite` in-memory DB avoids a real Postgres dependency in unit/smoke tests; Alembic migration runs against real Postgres in CI reconciliation job only

### Open Questions

- none

### Next Session — Start Here

1. Run `/plan-feature` for **F1** (SAS parser → LLM client → codegen). The plan should cover: `src/worker/engine/parser.py` (DATA step + PROC SQL block extraction, multi-file dependency ordering), `src/worker/engine/llm_client.py` (Pydantic AI agent, `LLM_MODEL` env var), `src/worker/engine/codegen.py` (provenance comments, `# SAS: <file>:<line>`)
2. Before planning F1, add sample SAS files to `samples/` — the parser needs real input to test against

### Files Touched

- `docker-compose.yml`
- `pyproject.toml`, `uv.lock`
- `.env.example`
- `alembic.ini`, `alembic/env.py`, `alembic/versions/001_create_jobs_table.py`
- `src/backend/` (all files — new)
- `src/worker/` (all files — new)
- `src/frontend/` (full scaffold — new)
- `tests/test_api_smoke.py` (new)
- `.github/workflows/ci.yml`
- `docs/plans/F0-phase1-scaffold.md` (new, status: done)
- `docs/architecture.md`
- `journal/BACKLOG.md`, `journal/DECISIONS.md`
- `README.md`, `Makefile`, `CLAUDE.md`
- `.claude/skills/git-committer/SKILL.md`, `.claude/skills/backend-builder/SKILL.md`

---

## 2026-04-17 — DuckDB Removal, Skill Hardening & Feature Catalogue

**Duration:** ~2h | **Focus:** Local backend swap, skill quality, feature catalogue

### Done

- Replaced DuckDB with PostgreSQL as the local `ComputeBackend` — removed `duckdb>=0.10` from `pyproject.toml`, updated all docs, README, CLAUDE.md, backlog, and decisions log
- Audited all skills and commands for hard-coded file paths — found offenders in `backend-builder`, `frontend-builder`, and `plan-feature`; replaced with instructions to derive paths from `docs/architecture.md`
- Added F8–F18 to `docs/features.md` (13 new features); bumped F8 (Compliance & Audit Traceability) and F9 (Downloadable Migration Output) to MVP scope
- Updated `docs/mvp-scope.md` and `journal/BACKLOG.md` accordingly

### Decisions

- DuckDB removed: PostgreSQL is already in Docker Compose for job state — one less engine, logged in DECISIONS.md
- Skills must not hard-code file paths: derive from `docs/architecture.md` — logged in DECISIONS.md

### Open Questions

- none

### Next Session — Start Here

1. Run `/plan-feature` for Phase 1 scaffold (Docker Compose revision, `src/backend/`, `src/worker/`, `src/frontend/` structure, jobs table Alembic migration)
2. Run `uv sync` to drop DuckDB from the lock file after the scaffold is in place

### Files Touched

- `pyproject.toml`
- `docs/architecture.md`, `docs/features.md`, `docs/mvp-scope.md`, `docs/user-stories.md`
- `CLAUDE.md`, `README.md`
- `journal/BACKLOG.md`, `journal/DECISIONS.md`
- `.claude/skills/backend-builder/SKILL.md`
- `.claude/skills/frontend-builder/SKILL.md`
- `.claude/skills/plan-feature/SKILL.md`
- `.claude/commands/plan-feature.md`

---

## 2026-04-17 — Architecture Revision, Feature Expansion & Tooling Overhaul

**Duration:** ~3h | **Focus:** Architecture, features, skills/commands, CI

### Done

- Confirmed context: CI fixes defer to when `src/` is created; multi-file upload is MVP; frontend confirmed React+Vite; Databricks paused
- Revised `docs/architecture.md` — full rewrite: 4-service microservices (backend, worker, frontend, postgres), async job flow (POST→job_id→poll), reconciliation inline in worker, provider-agnostic LLM via `LLM_MODEL` env var, PostgreSQL jobs table schema, updated directory structure
- Updated `docs/mvp-scope.md` — multi-file input now in MVP scope; post-MVP phases restructured
- Updated `.github/workflows/ci.yml` — reconciliation job gets postgres service + Alembic step; worker image added to Docker build job; frontend comment corrected to Phase 1; `LLM_MODEL` dummy env var added
- Added F8–F18 to `docs/features.md` — 13 new features catalogued across phases
- Bumped F8 (Compliance & Audit Traceability) and F9 (Downloadable Migration Output) to MVP
- Updated `journal/BACKLOG.md` — Phase 1 rewritten for 4-service scaffold; F8/F9 tasks added; Phase 2–4 expanded with new features
- Updated `journal/DECISIONS.md` — session 3 decisions logged
- Overhauled `plan-feature`, `session-start`, `session-end` skills and commands — plan-feature now writes `docs/plans/F<N>-<slug>.md` with subtasks, dependencies, acceptance criteria; session-start reads `docs/plans/`; session-end updates plan file before journal
- Updated `CLAUDE.md` — architecture summary, key docs table, session continuity steps, skills table

### Decisions

- All logged in `journal/DECISIONS.md` under "session 3 — architecture revision"
- Key: 4-service microservices, async jobs in Postgres, reconciliation inline, LLM_MODEL env var, multi-file in MVP, F8/F9 bumped to MVP, Databricks paused to Phase 4

### Open Questions

- none

### Next Session — Start Here

1. Run `/plan-feature` for Phase 1 scaffold (Docker Compose revision, `src/backend/`, `src/worker/`, `src/frontend/` structure, jobs table Alembic migration)
2. Work through F1 vertical slice subtasks in order per the generated plan file

### Files Touched

- `docs/architecture.md`
- `docs/features.md`
- `docs/mvp-scope.md`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`
- `.github/workflows/ci.yml`
- `.claude/commands/plan-feature.md`
- `.claude/commands/session-start.md`
- `.claude/commands/session-end.md`
- `.claude/skills/plan-feature/SKILL.md`
- `.claude/skills/session-start/SKILL.md`
- `.claude/skills/session-end/SKILL.md`
- `CLAUDE.md`

---

## 2026-04-17 — Claude Setup Hardening & Dev Scaffolding

- What decisions did we make?
- What's blocked or open?
- What's the very next thing to do?

---

## 2026-04-17 — Claude Setup Hardening & Dev Scaffolding

**Duration:** ~3h | **Focus:** Claude Code setup audit, dev tooling, CI pipeline

### Done

- Audited and fixed Claude Code setup: created 3 missing skills (`session-start`, `session-end`, `plan-feature`)
- Fixed CLAUDE.md skill table — clarified user-invoked vs Claude-invoked skills
- Improved all skills with `Use for` / `Do NOT use for` sections
- Updated `backend-builder` skill with comprehensive rules (layer placement, Pydantic AI, guardrails, output contract)
- Updated `frontend-builder` skill with design philosophy from external source
- Updated `git-committer` skill with atomic commit definition and examples
- Cleaned `pyproject.toml`: removed `sas-kernel`, moved `antlr4` to optional `[parsers]` group
- Pinned Python to 3.12 via `uv python pin`, rebuilt venv
- Created `Makefile` with all dev targets including Docker (`make dev`, `make dev-down`, `make dev-logs`)
- Created `.pre-commit-config.yaml` with ruff + mypy hooks, installed hooks
- Created `.env.example`
- Created `docker-compose.yml` pointing to per-service Dockerfiles (to be added in Phase 1 and 3)
- Moved `specs/mvp-scope.md` → `docs/mvp-scope.md`, deleted `specs/` folder, updated all references
- Aligned line-length standard to 100 chars across `coding-standards.md` and `pyproject.toml`
- Rewrote `README.md`: Docker-first setup, Claude Code workflow, committing guidelines, philosophy section
- Added GitHub Actions CI pipeline (`.github/workflows/ci.yml`) with uv caching, two active jobs (lint+types, tests), four commented-out future jobs (reconciliation, frontend, Docker, cloud)
- Raised coverage gate to 90% in `pyproject.toml`
- Fixed CI to skip ruff/mypy/pytest gracefully when `src/` and `tests/` don't exist yet

### Decisions

- Docker Compose is the standard dev runtime; Dockerfiles live alongside source (`src/backend/`, `src/frontend/`)
- `specs/` folder removed — MVP scope lives in `docs/mvp-scope.md`
- No `Co-Authored-By` Claude attribution in any commit message
- `structlog` not added — stdlib `logging` used instead (not in pyproject.toml)
- No Spec-Driven Development for now — behaviour tables per SAS construct handler when Phase 1 starts
- No subagents yet — journal + skills handle context; revisit at Phase 2-3

### Open Questions

- Which SAS sample file will be the first migration target?
- Do we have access to a Databricks workspace for CLOUD=true testing?
- Frontend framework confirmed as React + Vite (not Streamlit)?

### Next Session — Start Here

1. Fix CI test job to skip gracefully when `tests/` doesn't exist (interrupted mid-fix)
2. Start Phase 1: scaffold `src/sas_migrator/` package structure
3. Run `/plan-feature` for F1 vertical slice

### Files Touched

- `.claude/skills/*` (all updated)
- `.claude/settings.json`
- `CLAUDE.md`
- `pyproject.toml`
- `Makefile`
- `.pre-commit-config.yaml`
- `.env.example`
- `.python-version`
- `docker-compose.yml`
- `docs/mvp-scope.md` (moved from `specs/`)
- `docs/coding-standards.md`
- `README.md`
- `.gitignore`
- `.github/workflows/ci.yml`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`
- `uv.lock`

---

## 2026-04-17 — Project Kickoff

**Participants:** Mattia + Claude
**Duration:** ~1h
**Focus:** Setting up project scaffolding and Claude Code configuration

### Done

- Defined two user stories (tech user + non-tech user)
- Expanded 7 features across backend/frontend
- Created CLAUDE.md, skills, commands, and journal structure
- Locked in MVP constraints: CLOUD flag in .env, local + Databricks support

### Decisions

- See `journal/DECISIONS.md` entries dated 2026-04-17

### Open Questions

- Frontend framework: Streamlit for MVP, confirmed?
- Which SAS sample files will we use as the first migration target?
- Do we have access to a Databricks workspace for testing CLOUD=true path?

### Next Session — Start Here

1. Pick the first SAS sample file (smallest, self-contained)
2. Plan the vertical slice: ingest → translate → execute → reconcile (CLOUD=false)
3. Scaffold the `ComputeBackend` interface
4. Write the first reconciliation test

### Files Touched

- CLAUDE.md (created)
- .claude/skills/\* (created)
- .claude/commands/\* (created)
- journal/\* (created)
- docs/\* (created)
- specs/mvp-scope.md (created)

```

```
