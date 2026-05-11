# F22 — Pre-Migration Assessment UX improvements

**Phase:** 2
**Area:** Frontend
**Status:** complete (S-A through S-Y)

## Goal

The F21 pre-migration assessment page surfaces all the right data but is organised for an engineer, not the non-technical code owner who must sign off before a migration runs. This feature reshapes `MigrationPreviewPage.tsx` to lead with the most decision-critical information: a single RED/AMBER/GREEN headline card, an elevated PII alert, blocks sorted by downstream impact, manager-readable tier labels, blast radius visible on high-impact translatable blocks, a plain "what you need to do" action summary split by timing, a risk-coloured lineage graph, and reordered/collapsed sections so the riskiest content comes first. No backend changes are required — all data is already present in `AnalyseResponse`.

Done looks like: a manager opening the assessment page immediately sees their overall readiness verdict and effort estimate, gets a PII alert above the fold if relevant, can read the risk tiers with the highest-impact blocks at the top, sees the lineage graph with risky stages highlighted in red/amber, understands exactly what needs to happen before vs after migration, and reaches the acknowledgment gate without having scrolled past irrelevant technical sections.

## Acceptance Criteria

- [ ] Top of page shows a headline card with RED/AMBER/GREEN verdict, effort estimate range, an explicit recommendation sentence, and a critical issue callout covering `needs_manual > 0` (with stub-behaviour explanation), missing deps, and circular deps
- [ ] When `sensitive_data_findings` is non-empty, a PII alert banner renders immediately below the headline card — before Scope and Risk sections
- [ ] Effort estimate no longer appears as a standalone section (it lives only in the headline card)
- [ ] Blocks within each tier are sorted descending by `blast_radius.length` (highest downstream impact first)
- [ ] Blast radius is shown on 🟡 (review) blocks, not only on 🔴 (manual) blocks
- [ ] Tier label copy is manager-facing: "Cannot auto-convert", "High-impact — developer review", "Will attempt — verify output"
- [ ] "What you need to do" summary section appears between Migration Risk and Acknowledgments, split into pre-migration and post-migration actions, grouped by `importance_reason`, each bullet listing affected `output_datasets`
- [ ] Pipeline Lineage section appears after Migration Risk; SAS file nodes are coloured by their highest risk tier (red/amber/blue/green border)
- [ ] Configuration values and Validation coverage sections are collapsed by default with an expand toggle
- [ ] `make test` exits 0

## Section order after this feature

1. Headline card (verdict + effort + critical issue)
2. PII banner (conditional)
3. Parser warning banner (existing, conditional)
4. Blockers — missing/circular deps (conditional)
5. Scope — file count, AI description, inputs/outputs
6. Migration Risk — 4 tier sections (blocks sorted by blast radius within each tier)
7. Pipeline Lineage graph (risk-tier coloured; moved from between Scope and Risk)
8. What you need to do — action summary (pre/post split)
9. Validation coverage (collapsed by default)
10. Configuration values (collapsed by default)
11. Acknowledgments + Start Migration

## Subtasks

---

### S-A: Headline verdict card
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** An `AssessmentHeadline` inline component renders at the very top of the assessment (replacing the current `StatPill` row) showing:
- One of three verdict states with coloured background: 🔴 RED (`needs_manual > 0`), 🟡 AMBER (`review_recommended > 0 || best_effort > 0`, no manual blocks), 🟢 GREEN (all auto-converts)
- A one-line summary: "N block(s) cannot auto-convert · X–Y hr manual effort" (RED), or "N block(s) need developer review · X–Y hr" (AMBER), or "All blocks convert automatically · X–Y hr review" (GREEN)
- An explicit recommendation sentence below the summary line:
  - RED: "Proceed only if your team is ready to implement N manual block(s) — the pipeline will run but those steps will produce placeholder code until implemented."
  - AMBER: "Migration can proceed — a developer should review the N high-impact block(s) after the run completes."
  - GREEN: "This migration can proceed automatically. Review the output against your reference data after the run."
- A critical issue callout line when any of: `needs_manual > 0` ("N block(s) will generate placeholder code — pipeline will be incomplete until implemented"), `missing_dependencies.length > 0` ("N missing dependency/ies will block the run"), or `circular_dependencies.length > 0` ("Circular dependency detected — execution order cannot be resolved")
- The four pill counts (needs manual / recommend review / best-effort / auto) preserved as a secondary row within the same card
- The standalone "Post-migration effort estimate" section (currently section 7) is removed — effort data now lives only in this card
- [x] done

---

### S-B: PII alert banner above the fold
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** When `assessment.sensitive_data_findings.length > 0`, a destructive-red alert banner renders immediately after the headline card and before the Scope section. The banner lists every detected pattern inline (e.g. "DOB, SSN, EMAIL detected in customers.sas7bdat"). The existing "Sensitive data detected" section at the bottom of the page is removed to avoid duplication — the PII acknowledgment checkbox in the Acknowledgments section is retained.
- [x] done

---

### S-C: Manager-friendly tier label copy
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** The four `TierSection` label strings are updated to:
- `"🔴 Cannot auto-convert — manual implementation required"`
- `"🟡 High-impact — developer review recommended"`
- `"🔵 Will attempt — unknown patterns, verify output"`
- `"✅ Converts automatically"` (unchanged)
- [x] done

---

### S-D: Blast radius on review blocks + block sort within tiers
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:**
- `showBlastRadius` prop in `BlockCard` is `true` for both `"manual"` and `"review"` tiers (currently only `"manual"`)
- Within each tier, blocks are sorted descending by `blast_radius.length` before rendering — highest downstream impact shown first. Ties retain parse order.
- [x] done

---

### S-E: "What you need to do" action summary
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** A new `ActionSummary` inline component renders between the Migration Risk tiers and the Acknowledgments section. It contains two labelled subsections:

**Before migration starts:**
- Groups 🔴 blocks by `importance_reason` and emits one bullet per group. Each bullet includes the union of `output_datasets` across all blocks in that group, e.g.:
  - "2 × terminal output blocks — manual implementation required · produces `FINAL_CLAIMS_REPORT`, `AUDIT_TRAIL`"
  - "1 × pipeline entry block — manual implementation required · reads `customers.csv`"
- If no 🔴 blocks: "No manual implementation required before migration"

**After migration runs:**
- Groups 🔵 blocks by `importance_reason` (if any), including their output datasets, e.g.: "3 best-effort blocks — verify output matches expected results · produces `SUMMARY_TABLE`"
- Groups 🟡 blocks (if any), including their output datasets: "2 high-impact blocks translated — developer should review generated code · produces `REVENUE_REPORT`"
- If neither: "No post-migration review required"
- [x] done

---

### S-F: Section reorder
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** S-A, S-B (so the full new section order can be set in one pass)
**Done when:** JSX section order matches the target order in the Goal section. The lineage graph `<section>` moves from its current position (between Scope and Migration Risk) to after Migration Risk. The standalone "Post-migration effort estimate" section is absent (removed in S-A). `PreviewLineageGraph` receives a new `fileRiskTiers` prop (computed in this subtask: a `Record<string, "manual" | "review" | "best-effort" | "auto">` keyed by `source_file`, taking the worst tier across all blocks for that file).
- [x] done

---

### S-G: Risk-tier colouring in PreviewLineageGraph
**File:** `src/frontend/src/components/PreviewLineageGraph.tsx`
**Depends on:** S-F (so `fileRiskTiers` prop contract is settled)
**Done when:** `PreviewLineageGraph` accepts a new optional prop `fileRiskTiers?: Record<string, "manual" | "review" | "best-effort" | "auto">`. When provided, SAS file nodes use a risk-tier border colour instead of the default blue:
- `"manual"` → `#ef4444` (red-500)
- `"review"` → `#f59e0b` (amber-500)
- `"best-effort"` → `#3b82f6` (blue-500, unchanged)
- `"auto"` or absent → `#22c55e` (green-500)

The legend overlay is updated to reflect this: SAS file node legend entry replaced by four coloured swatches (🔴 Cannot auto-convert / 🟡 Needs review / 🔵 Best-effort / 🟢 All auto).
- [x] done

---

### S-H: Collapse configuration values and validation coverage by default
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** Both the "Validation coverage" and "Configuration values" sections render collapsed by default. Each has a `[Show / Hide]` toggle using the same `useState(false)` + chevron pattern already used by `TierSection`. Content is unchanged when expanded.
- [x] done

---

### S-I: `make test` exits 0
**Depends on:** S-A through S-H
**Done when:** `make test` green with no ruff, mypy, tsc, or eslint errors.
- [x] done

---

### S-J: Deduplicate missing dependencies
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** `uniqueMissingDeps` useMemo deduplicates `assessment.missing_dependencies` by `dep.name`; headline and Blockers section use the deduplicated count.
- [x] done

---

### S-K: Improve missing dep path display
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** S-J
**Done when:** Blockers section shows basename (last path segment) per unique dep, with "(referenced by N files)" when N > 1; unresolved macro prefixes no longer shown.
- [x] done

---

### S-L: Fix headline recommendation sentence when missing deps present
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** S-J
**Done when:** `AssessmentHeadline` overrides the recommendation text when `missingDeps > 0` to accurately describe the macro-context gap rather than saying "Migration can proceed".
- [x] done

---

### S-M: Missing deps acknowledgment checkbox + gate fix
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** S-J
**Done when:** `missingDepsConfirmed` state added; acknowledgment checkbox renders when `uniqueMissingDeps.length > 0`; `allAcked` gates on it; "No acknowledgments required" text only shown when all three gates are empty.
- [x] done

---

### S-N: Remove "+N more" truncation from action summary datasets
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** All three `datasets.slice(0, 3)` patterns in `ActionSummary` replaced with `datasets.join(", ")`.
- [x] done

---

### S-O: Validation/Config section count labels
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** Section headers read "N datasets" and "N values" instead of bare "(N)".
- [x] done

---

### S-P: Lineage graph fitView padding
**File:** `src/frontend/src/components/PreviewLineageGraph.tsx`
**Depends on:** none
**Done when:** `fitViewOptions.padding` changed from 0.25 to 0.4 to reduce right-side clipping on initial render.
- [x] done

---

### S-Q: `make test` exits 0 (post bug-fix pass)
**Depends on:** S-J through S-P
**Done when:** `make test` green with no ruff, mypy, tsc, or eslint errors.
- [x] done

---

### S-R: Navigate to `/jobs/{id}` after submit
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`
**Depends on:** none
**Done when:** After a successful POST /migrate, `navigate(\`/jobs/${result.job_id}\`)` is called instead of `navigate("/jobs")`, so the user lands directly on the new job's detail page.
- [x] done

---

### S-S: Persist assessment in Plan tab
**Files:** `src/frontend/src/pages/MigrationPreviewPage.tsx`, `src/backend/api/routes/jobs.py`, `src/frontend/src/api/jobs.ts`, `src/frontend/src/components/JobDetail/PlanTab.tsx`, `tests/test_analyse_route.py`
**Depends on:** none
**Done when:** Full `AnalyseResponse` is persisted in `job.assessment.analyse_response` at submit time; `GET /jobs/{id}/assessment` endpoint returns it (204 if absent); `getJobAssessment()` API client fetches it; `AssessmentPanel` in PlanTab displays verdict, effort, blockers, and expandable details above the migration plan.
- [x] done

---

### S-T: Plan tab AssessmentPanel UX polish
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-S
**Done when:**
- Effort estimate shows `"< 1 hr"` floor (not `"0–0.1 hr"`) when high estimate < 1 hr
- Summary line includes all tier counts inline (e.g. "3 need review · 2 auto-convert · < 1 hr"), removing the need for a tile grid
- 4-tile tier count grid removed from expanded section (data now in summary line)
- Expand/collapse toggle hidden when there is no expandable detail (no PII findings and no unique missing deps)
- Section labels show temporal subtitles: "Pre-migration assessment · predicted before run" and "Migration plan · actual results after run"
- Blocks row in the plan card shows "· N need attention" hint when `needs_review + manual_todo > 0`
- [x] done

---

### S-U: Remove "actual results after run" subtitle from Migration plan label
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-T
**Done when:** The "actual results after run" subtitle is removed from the Migration plan section label — it was misleading because the plan is shown pre-accept with an "Accept migration" button.
- [x] done

---

### S-V: Plan tab 7 UX fixes
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-U
**Done when:** All 7 issues fixed: (1) redundant needs_manual blocker row removed; (2) "Migration plan" label always renders regardless of assessment; (3) stats row left-aligned; (4) "Show details" replaced with chevron icon; (5) missing dep list no longer truncated at 5; (6) confidence bar hidden until trust report loads; (7) Blocks toggle nested inside plan card to show ownership.
- [x] done

---

### S-W: Collapse pre-migration assessment into plan card callouts
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-V
**Done when:** The separate `AssessmentPanel` section is removed from PlanTab. A slim `AssessmentCallouts` row inside the plan card surfaces only the two items that remain relevant post-run — missing macro/include files and detected PII patterns. Assessment verdict/tier counts/effort are no longer shown separately since they duplicated (and contradicted) the trust report stats.
- [x] done

---

### S-X: Restore effort estimate and circular dependency warning
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-W
**Done when:** Effort estimate (from `assessmentData.stats`) added to the stats row alongside Confidence and Risk. Circular dependency warning added to `AssessmentCallouts`. Both were unique-value items dropped when the full assessment panel was removed.
- [x] done

---

### S-Y: PM-facing attention block summary
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-X
**Done when:** `AttentionBlocksSummary` component renders between the plan card and the Blocks toggle when `needs_review + manual_todo > 0`. One card per attention block showing: status badge (Manual implementation required / Review recommended), source file + line, block type, confidence %, and plain-language rationale. Blocks toggle moves back outside the plan card and is labelled "· developer detail" when attention blocks are visible.
- [x] done

## Dependencies on other features

- F21 (complete) — all data fields sourced from `AnalyseResponse`; `PreviewLineageGraph` component already exists at `src/frontend/src/components/PreviewLineageGraph.tsx`

## Out of scope for this feature

- Any new backend fields or endpoints
- Click-through / anchor links from the action summary to individual block cards
- Persisting collapse state of coverage/config sections across sessions
- PDF export
- Per-block type icons in the action summary
