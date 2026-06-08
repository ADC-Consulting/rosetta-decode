# F29 — Plan Tab Refinement

**Phase:** 3
**Area:** Frontend
**Status:** in-progress
**GitHub issue:** #41

## Goal

Make the Plan tab the single place where a user gets everything they need to make a confident accept/reject decision on a SAS migration. This means absorbing the decision-relevant content from EvaluationTab (summary cards, full review queue, per-file breakdown, confidence explanation) and adding the Report and Migration history panels so the user never needs to leave the tab to understand the migration.

## Acceptance Criteria

- [ ] Scope summary ("N files · M blocks") shown as subtitle in job header
- [ ] Verdict strip renders in three states (green/amber/red) with plain-English consequence text derived from trustReport
- [ ] Description text is free-standing prose between verdict and metrics card
- [ ] Stat cards are large and clickable; clicking filters the block table and auto-expands the Blocks section; clicking again clears the filter
- [ ] Confidence info dialog (ℹ️) opens with explanation of confidence bands, criticality, and blast radius
- [ ] Amber notice shown when lineage is unavailable (blast radius column suppressed)
- [ ] "Needs attention" section replaces separate attention cards + review queue; has Cards/Table toggle; Cards view shows top 5 plain-English items with "N more · Show all"; Table view shows full 9-column review table; section hidden when no blocks need attention
- [ ] "Re-translate all failed blocks" button in Needs attention header; fires `refineBlock` sequentially; disabled while in flight
- [ ] Per-file breakdown section present, collapsible, collapsed by default
- [ ] Report collapsible panel present, collapsed by default, renders full ReportTab content
- [ ] Migration history collapsible panel present, collapsed by default, renders ChangelogFeed
- [ ] Sticky accept footer pinned to bottom of Plan tab; shows verdict summary + Accept button; hidden when accepted
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

### S-J: Verdict strip
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** A full-width strip below the scope summary shows one of three states derived from `trustReport` — green "✓ Ready to accept" (all blocks auto-verified), amber "⚠ Review recommended" (needs_review > 0 or failed_reconciliation > 0), red "⚠ Not ready to accept" (manual_todo > 0 and failed_reconciliation > 0); each state has a plain-English consequence sentence; strip has a coloured left border matching the state
- [ ] done

### S-K: Scope summary in page header
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** none
**Done when:** The job header row shows "N files · M blocks" as a subtitle below the job name, derived from `planData.block_plans` (unique source files count + total block count); hidden when plan data is not yet loaded
- [ ] done

### S-L: Merge attention cards + review queue into single section with card/table toggle
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-A, S-C
**Done when:** The separate "Review queue" section is replaced by a single "Needs attention" section with a Cards/Table segmented toggle; Cards view shows plain-English cards (top 5, manual first then critical, with "N more · Show all" link that switches to table view); Table view shows the full 9-column review table from S-C; "Re-translate failed blocks" button (S-G) lives in this section header; section is expanded by default; hidden entirely when no blocks need attention (renders green "All blocks verified" message instead)
- [ ] done

### S-M: Description text as free-standing prose
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `planData.summary` text renders as a plain paragraph between the verdict strip and the metrics card — not inside the metrics card; metrics card contains only confidence bar + risk bar + stat cards
- [ ] done

### S-N: Sticky accept footer
**Files:**
- `src/frontend/src/components/JobDetail/PlanTab.tsx`
- `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** S-J
**Done when:** A sticky bar is pinned to the bottom of the Plan tab content area showing the verdict summary text on the left and the Accept migration button on the right; bar state mirrors the verdict strip (green/amber/red text); hidden when job is already accepted; the existing Accept button in the page header remains for discoverability
- [ ] done

### S-O: make test exits 0
**Depends on:** S-A through S-N
**Done when:** All 7 gates green
- [ ] done

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
