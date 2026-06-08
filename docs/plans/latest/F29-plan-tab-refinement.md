# F29 — Plan Tab Refinement

**Phase:** 3
**Area:** Frontend
**Status:** in-progress
**GitHub issue:** #41

## Goal

Make the Plan tab the single place where a user gets everything they need to make a confident accept/reject decision on a SAS migration. This means absorbing the decision-relevant content from EvaluationTab (summary cards, full review queue, per-file breakdown, confidence explanation) and adding the Report and Migration history panels so the user never needs to leave the tab to understand the migration.

## Acceptance Criteria

- [ ] Review queue expanded by default on page load
- [ ] Stat pills replaced by large clickable summary cards; clicking filters the block table; clicking again clears the filter
- [ ] Review queue table shows full columns: Block ID, Source file, Strategy, Self confidence, Verified confidence, Reconciliation, Criticality, Human review required, Blast radius (when lineage available)
- [ ] Confidence info dialog (ℹ️) opens with explanation of confidence bands, criticality, and blast radius
- [ ] Amber notice shown when lineage is unavailable (blast radius column suppressed)
- [ ] Per-file breakdown section present, collapsible, collapsed by default
- [ ] "Re-translate all failed blocks" button visible when `failed_reconciliation > 0` and job not accepted; fires `refineBlock` sequentially; disabled while in flight
- [ ] Report collapsible panel present, collapsed by default, renders full ReportTab content
- [ ] Migration history collapsible panel present, collapsed by default, renders ChangelogFeed
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

## Subtasks

### S-A: Fix review queue default state
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `reviewCollapsed` initialises to `false` so the review queue is expanded on load
- [ ] done

### S-B: Replace stat pills with clickable summary cards + stat filter
**Files:**
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
**Depends on:** none
**Done when:** The four metrics render as large summary cards (big number + label, styled by status colour); clicking a card sets `activeStatFilter` in PlanTab and filters the block table; clicking the active card clears the filter; `BlockPlanTable` accepts `activeStatFilter` prop and applies it after the existing strategy filter using `trustBlocks[bp.block_id]` to categorise rows
- [ ] done

### S-C: Upgrade review queue to full columns
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-A
**Done when:** Review queue table renders 8 columns (9 when lineage available): Block ID, Source file, Strategy, Self confidence, Verified confidence, Reconciliation, Criticality, Human review required, Blast radius; secondary sort by blast_radius descending within criticality tier; blast radius column and value suppressed when `!trustReport.lineage_available`
- [ ] done

### S-D: Add confidence info dialog
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** An ℹ️ icon button sits next to the confidence bar in the summary card; clicking opens a Dialog with the `CONFIDENCE_HELP` text from `EvaluationTab.tsx` (explaining confidence bands, criticality definition, and blast radius)
- [ ] done

### S-E: Add lineage unavailable notice
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** When `trustReport.lineage_available === false`, an amber notice banner is shown below the summary card reading "Blast radius unavailable — lineage enrichment did not run for this job"
- [ ] done

### S-F: Add per-file breakdown section
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** A collapsible "By file" section (collapsed by default) renders one `FileSection` per `trustReport.files` entry, each showing total_blocks / auto_verified / needs_review / manual_todo / failed_reconciliation for that source file; section hidden when `trustReport.files` is empty
- [ ] done

### S-G: Bulk re-translate button
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** A "Re-translate all failed blocks" button is visible when `trustReport.failed_reconciliation > 0` and job is not accepted; clicking fires `refineBlock` sequentially for each block where `reconciliation_status === "fail"`; button is disabled and shows a loading state while `isRefiningAll === true`; calls `onBlockRefineSuccess()` once after all calls complete
- [ ] done

### S-H: Restore doc state in JobDetailPage and add Report panel to PlanTab
**Files:**
- `src/frontend/src/pages/JobDetailPage.tsx`
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `getJobDoc` import, `docData` query, `overrideDoc`, `reportRestoreKey` state are restored in JobDetailPage (all have "restored in #41" stub comments); new props `doc`, `nonTechnicalDoc`, `isDone`, `onDocChange`, `onSave`, `isSaving`, `restoreKey` added to PlanTab and passed from JobDetailPage; `ReportTab` rendered inside a collapsible section in PlanTab, collapsed by default
- [ ] done

### S-I: Migration history collapsible panel
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `ChangelogFeed` rendered inside a collapsible section below Report, collapsed by default; `jobId` passed (already in scope)
- [ ] done

### S-J: make test exits 0
**Depends on:** S-A through S-I
**Done when:** All 7 gates green
- [ ] done

## Dependencies on other features

- F28 (chevron tab shell) — complete; `?tab=plan` routing in place

## Out of scope for this feature

- Stat card filtering on EvaluationTab (it is unused in the chevron shell; deletion tracked in #46)
- "Re-translate all failed blocks" backend endpoint — uses existing per-block `refineBlock` client function
- Any ETL, Lineage, or other tab changes
- New API endpoints or schema migrations
