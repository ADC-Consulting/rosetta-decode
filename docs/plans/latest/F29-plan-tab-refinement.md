# F29 — Plan Tab Refinement

**Phase:** 3
**Area:** Frontend
**Status:** complete
**GitHub issue:** #41

## Goal

Make the Plan tab the single place where a user gets everything they need to make a confident accept/reject decision on a SAS migration. This means absorbing the decision-relevant content from EvaluationTab (summary cards, full review queue, per-file breakdown, confidence explanation) and adding the Report and Migration history panels so the user never needs to leave the tab to understand the migration.

## Acceptance Criteria

- [x] Scope summary ("N files · M blocks") shown as subtitle in job header
- [x] Description text renders **above** the verdict strip (context before conclusion)
- [x] Verdict strip renders in three states: green (no issues), red (manual_todo > 0), amber (everything else); each with icon + headline + consequence sentence
- [x] Confidence bar is labelled "LLM confidence"; stat cards show "N of total" denominators
- [x] Stat cards are clickable; clicking filters the block table, auto-expands Blocks, and scrolls it into view; clicking again clears the filter
- [x] Confidence info dialog (ℹ️) opens with explanation of confidence bands, criticality, and blast radius
- [x] Amber notice shown when lineage is unavailable (blast radius column suppressed)
- [x] "Needs attention" section has Cards/Table toggle; Cards view shows explicit strategy label, rationale fallback, "View code →" link per card, manual-block action hint when manual_todo > 0; green success state (visible) when all blocks pass
- [x] "Re-translate all failed blocks" button in Needs attention header; fires `refineBlock` sequentially; disabled while in flight
- [x] Report section expanded by default when doc is available; collapsed with placeholder message when not
- [x] Section order: Blocks → Report → By file → Migration history
- [x] Sticky accept footer: button label varies by verdict state; shares existing `showAcceptConfirm` dialog; `pb-16` padding prevents overlap; hidden when accepted
- [x] `make test` exits 0
- [x] ruff and mypy pass

## Subtasks

### S-A: Fix review queue default state
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `reviewCollapsed` initialises to `false` so the review queue is expanded on load
- [x] done

### S-B: Replace stat pills with clickable summary cards + stat filter
**Files:**
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
**Depends on:** none
**Done when:** The four metrics render as large summary cards (big number + label, styled by status colour); each card shows the count as a large number with a secondary "of N" denominator in smaller text derived from `trustReport.total_blocks` (e.g. "6" with "of 26" beneath); clicking a card sets `activeStatFilter` in PlanTab, filters the block table, auto-expands the Blocks section, AND scrolls the Blocks section into view; clicking the active card clears the filter; `BlockPlanTable` accepts `activeStatFilter` prop and applies it after the existing strategy filter using `trustBlocks[bp.block_id]` to categorise rows
- [x] done

### S-C: Upgrade review queue to full columns
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-A
**Done when:** Review queue table renders 8 columns (9 when lineage available): Block ID, Source file, Strategy, Self confidence, Verified confidence, Reconciliation, Criticality, Human review required, Blast radius; secondary sort by blast_radius descending within criticality tier; blast radius column and value suppressed when `!trustReport.lineage_available`
- [x] done

### S-D: Add confidence info dialog
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** An ℹ️ icon button sits next to the confidence bar in the summary card; clicking opens a Dialog with the `CONFIDENCE_HELP` text from `EvaluationTab.tsx` (explaining confidence bands, criticality definition, and blast radius)
- [x] done

### S-E: Add lineage unavailable notice
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** When `trustReport.lineage_available === false`, an amber notice banner is shown below the summary card reading "Blast radius unavailable — lineage enrichment did not run for this job"
- [x] done

### S-F: Add per-file breakdown section
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** A collapsible "By file" section (collapsed by default) renders one `FileSection` per `trustReport.files` entry, each showing total_blocks / auto_verified / needs_review / manual_todo / failed_reconciliation for that source file; section hidden when `trustReport.files` is empty; section appears after Report (order: Blocks → Report → By file → Migration history)
- [x] done

### S-G: Bulk re-translate button
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** A "Re-translate all failed blocks" button is visible when `trustReport.failed_reconciliation > 0` and job is not accepted; clicking fires `refineBlock` sequentially for each block where `reconciliation_status === "fail"`; button is disabled and shows a loading state while `isRefiningAll === true`; calls `onBlockRefineSuccess()` once after all calls complete
- [x] done

### S-H: Restore doc state in JobDetailPage and add Report panel to PlanTab
**Files:**
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `getJobDoc` import, `docData` query, `overrideDoc`, `reportRestoreKey` state are restored in JobDetailPage (all have "restored in #41" stub comments); new props `doc`, `nonTechnicalDoc`, `isDone`, `onDocChange`, `onSave`, `isSaving`, `restoreKey` added to PlanTab and passed from JobDetailPage; `ReportTab` rendered inside a collapsible section in PlanTab; section is **expanded by default when `doc` is non-null** (the PM's primary question after reading the verdict is "what does this pipeline produce?" — the report answers it); collapsed with "No documentation generated yet" message when `doc` is null; Report section appears immediately after Blocks (order: Blocks → Report → By file → Migration history)
- [x] done

### S-I: Migration history collapsible panel
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `ChangelogFeed` rendered inside a collapsible section below Report, collapsed by default; `jobId` passed (already in scope)
- [x] done

### S-J: Verdict strip
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** A full-width strip below the scope summary shows one of three states derived from `trustReport`; state logic: green = `needs_review === 0 && failed_reconciliation === 0 && manual_todo === 0`; red = `manual_todo > 0` (pipeline is structurally incomplete regardless of recon); amber = everything else (recon failures or needs_review without manual gaps); each state has icon + headline + one plain-English consequence sentence (green: "All blocks verified — safe to accept"; amber: "N blocks need review before accepting"; red: "N blocks cannot be auto-converted — manual implementation required before this pipeline will run"); strip has a coloured left border (green/amber/red) matching the state
- [x] done

### S-K: Scope summary in page header
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** none
**Done when:** The job header row shows "N files · M blocks" as a subtitle below the job name, derived from `planData.block_plans` (unique source files count + total block count); hidden when plan data is not yet loaded
- [x] done

### S-L: Merge attention cards + review queue into single section with card/table toggle
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-A, S-C
**Done when:** The separate "Review queue" section is replaced by a single "Needs attention" section with a Cards/Table segmented toggle; Cards view shows top 5 blocks (manual first, then by criticality desc); each card shows: block ID + source file, explicit strategy label in text ("Manual — cannot auto-convert" or "Reconciliation failed" or "Needs review"), plain-English rationale (fallback: "A {block_type} block that {failed reconciliation/requires manual implementation}" if `rationale` is empty), affected downstream datasets if available, and a "View code →" subtle link that opens the View Code dialog for that block directly; when `manual_todo > 0` an amber info line appears at the top of the cards view: "Manual blocks require code edits in the ETL tab before this pipeline will run"; "N more · Show all" link at the bottom switches to table view; Table view shows the full 9-column review table from S-C; "Re-translate failed blocks" button (S-G) lives in this section header (only visible when `failed_reconciliation > 0`); section expanded by default; when no blocks need attention, section stays visible but renders a green "✓ All N blocks verified — nothing needs attention" state (not hidden)
- [x] done

### S-M: Description text above verdict strip + label confidence bar
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `planData.summary` text renders as a plain paragraph **above** the verdict strip (not between verdict and metrics); this ensures users read what the pipeline does before reading the verdict — context before conclusion; metrics card contains only confidence bar + risk bar + stat cards; the confidence bar label reads "LLM confidence" (not just "Confidence") to distinguish it from the reconciliation-based stat cards
- [x] done

### S-N: Sticky accept footer
**Files:**
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** S-J
**Done when:** A sticky bar is pinned to the bottom of the Plan tab content area (not the full page — scoped to the plan tab scroll container so it doesn't overlap other tabs); left side shows verdict summary text styled by state (green/amber/red); right side shows Accept button with label that varies by verdict state: green → "Accept migration", amber → "Accept anyway", red → "Accept (not recommended)"; clicking triggers the existing `showAcceptConfirm` dialog already wired in `JobDetailPage` — the footer button must share this state, not open a second dialog; the existing Accept button in the page header remains; entire footer hidden when `job.status === "accepted"`; content area has `pb-16` padding so collapsed sections are not obscured by the sticky bar
- [x] done

### S-O: make test exits 0
**Depends on:** S-A through S-N
**Done when:** All 7 gates green
- [x] done

## Dependencies on other features

- F28 (chevron tab shell) — complete; `?tab=plan` routing in place
- PR #34 (F22 assessment UX) — NOT merged; verdict strip, attention cards, and scope summary are repurposed from its design into F29; pre-migration assessment page is superseded and will not be implemented

## Out of scope for this feature

- Pre-migration assessment page (MigrationPreviewPage from PR #34) — superseded
- Reads / Produces row — requires `input_datasets`/`output_datasets` on `BlockPlanResponse`; backend schema change deferred
- Missing dependencies callout — requires new backend analysis; deferred
- PII / sensitive data warning — requires new backend analysis; deferred
- Stat card filtering on EvaluationTab (unused in chevron shell; deletion tracked in #46)
- Any ETL, Lineage, or other tab changes
- New API endpoints or schema migrations
