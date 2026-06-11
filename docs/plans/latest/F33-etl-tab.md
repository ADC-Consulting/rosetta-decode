# F33 — ETL Tab: Proposed Migration Orchestration View

**Phase:** 3
**Area:** Both (Backend / API + Frontend)
**Status:** in-progress
**GitHub issue:** #42

## Goal

Replace the current EditorTab+LineageTab stack on the ETL tab with a three-state proposed migration review flow:

1. **Files overview** — LineageGraph in files view, nodes coloured by aggregate migration status (green/amber/red from trustReport). User sees the full pipeline at a glance.
2. **Block list panel** — clicking a file node opens a side panel listing all blocks within that file with type, line, and status. Graph stays visible behind it.
3. **Code popup** — clicking a block opens a modal with SAS source (read-only, SAS Studio theme) on the left and proposed Python (editable for needs-review/manual blocks) on the right. User can verify or edit the translation.

Verification (Option A+): clicking "Mark as verified" calls the existing `PATCH /blocks/{block_id}/python` with `trigger="human-verify"`. This creates a `BlockRevision` even when code is unchanged, and the verified state propagates back to the Plan tab's Needs attention section.

## Acceptance Criteria

- [ ] ETL tab default view renders LineageGraph in files view; file nodes coloured by aggregate trustReport status
- [ ] Clicking a file node opens a block list panel alongside the graph (graph stays visible)
- [ ] Block list shows type, line number, and status badge per block; nodes with manual/needs-review blocks visually marked
- [ ] Clicking a block opens a code popup with SAS (read-only, SAS Studio Monaco theme) + proposed Python (editable for needs-review and manual blocks only)
- [ ] "Mark as verified" button fires `PATCH /python` with `trigger="human-verify"` and closes the popup
- [ ] Verified blocks update their node status to "human verified" (distinct visual state from auto-verified)
- [ ] Upstream risk shading: file nodes with unverified manual blocks downstream are dimmed/marked
- [ ] Summary bar at top: "N files · M blocks · X verified · Y review · Z manual"
- [ ] `make test` exits 0

## Subtasks

### S-A: Backend Option A+ — add trigger field to BlockPythonEditRequest
**Files:**
- `src/backend/api/schemas.py`
- `src/backend/api/routes/jobs.py`
**Depends on:** none
**Done when:** `BlockPythonEditRequest` has `trigger: str = "human"` field; handler at `save_block_python` uses `request.trigger` instead of hardcoded `"human"` when constructing `BlockRevision`; `trigger` value validated to allowlist `{"human", "human-verify", "human-refine"}`; no Alembic migration needed (existing `trigger` column already accepts strings)
- [ ] done

### S-B: Extend LineageGraph with onFileNodeClick callback and trustFiles status override
**File:** `src/frontend/src/components/LineageGraph.tsx`
**Depends on:** none
**Done when:** `LineageGraphProps` accepts two new optional props: `onFileNodeClick?: (file: FileNode) => void` which fires when a file node is clicked in files view (instead of setting internal `selectedFile` state — or in addition to it, since LineageDetailPanel inside the graph may still be needed for the lineage-only page); `trustFiles?: TrustReportFile[]` which overrides `FileNode.status`-based colouring with trustReport-derived aggregate status (`failed_reconciliation > 0` → red, `manual_todo > 0 || needs_review > 0` → amber, else green); `TrustReportFile` already imported from `@/api/types`; existing `LineageTab` usage is unaffected (props are optional with defaults)
- [ ] done

### S-C: Update saveBlockPython API client to accept trigger
**File:** `src/frontend/src/api/jobs.ts`
**Depends on:** S-A
**Done when:** `saveBlockPython(jobId, blockId, pythonCode, options?)` accepts an optional `trigger?: string` param and includes it in the request body; default remains `"human"` if not supplied; TypeScript types updated in `types.ts`
- [ ] done

### S-D: Build BlockInspectorPanel component
**File:** `src/frontend/src/components/JobDetail/BlockInspectorPanel.tsx` (new)
**Depends on:** none
**Done when:** A panel component that takes `sourceFile: string`, `blockPlans: BlockPlan[]`, `trustBlocks: Record<string, TrustReportBlock>`, `humanVerifiedBlocks: Set<string>`, `onBlockClick: (blockId: string) => void`, `onClose: () => void`; renders a header with the source file basename and a close button; lists all blocks filtered by `bp.source_file === sourceFile`, each showing block type badge, line number, and status badge (auto-verified=green, human-verified=teal, needs-review=amber, manual=red, not-run=grey); clicking a row fires `onBlockClick(bp.block_id)`; note: check if `LineageDetailPanel` can be adapted before building from scratch
- [ ] done

### S-E: Build BlockCodePopup component
**File:** `src/frontend/src/components/JobDetail/BlockCodePopup.tsx` (new)
**Depends on:** S-C
**Done when:** A modal Dialog that takes `jobId`, `blockId`, `sourceFile`, `blockType`, `status` (needs-review/manual/verified/auto-verified), `onClose`, `onVerified`; fetches SAS source via `getJobSources` (one call per ETLTab mount, passed as prop) and Python via `getBlockRevisions` (falls back to extracting from `job.python_code` using `# SAS: <file>:<line>` provenance marker if no revisions); left pane: SAS source Monaco editor with `sas-light`/`sas-dark` theme (read-only, highlights the block's start–end lines); right pane: Python Monaco editor (read-only for auto-verified/human-verified, editable for needs-review and manual); footer: "Mark as verified" button visible for needs-review and manual blocks, fires `saveBlockPython(jobId, blockId, pythonCode, {trigger: "human-verify"})` then calls `onVerified(blockId)`; status context banner shown between panes when recon failed
- [ ] done

### S-F: Build ETLTab component
**File:** `src/frontend/src/components/JobDetail/ETLTab.tsx` (new)
**Depends on:** S-B, S-D, S-E
**Done when:** Component takes `jobId`, `blockPlans`, `trustReport`, `jobSources` (pre-fetched SAS source map); manages three states: `selectedFile: string | null`, `selectedBlock: string | null`; derives `humanVerifiedBlocks: Set<string>` from `getJobChangelog` filtering entries where `trigger === "human-verify"`; renders: (1) summary bar ("N files · M blocks · X verified · Y review · Z manual"), (2) `LineageGraph` with `onFileNodeClick` and `trustFiles` props, (3) `BlockInspectorPanel` as a side panel when `selectedFile` is set, (4) `BlockCodePopup` as a modal when `selectedBlock` is set; `onVerified` callback adds the block to `humanVerifiedBlocks` and invalidates trust-report + changelog queries; upstream risk shading: pass a `riskHighlight` set to LineageGraph marking file nodes whose blocks include unverified manual blocks
- [ ] done

### S-G: Wire ETLTab into JobDetailPage and add jobSources query
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** S-F
**Done when:** ETL `TabsContent` replaces the `EditorTab + LineageTab` stack with `<ETLTab>`; a `useQuery` for `getJobSources(id)` is added at JobDetailPage level (enabled when `isReviewable`); `EditorTab` and `LineageTab` imports retained until #46 removes legacy components; `isEditorFullScreen` state and related props may be simplified or removed
- [ ] done

### S-H: make test exits 0
**Depends on:** S-A through S-G
**Done when:** All 7 gates green
- [ ] done

## Dependencies on other features

- F29 (Plan tab) — complete; `trustReport` data already fetched at JobDetailPage level
- F28 (chevron tab shell) — complete; `?tab=etl` routing in place
- PRs #63/#64/#65 (F30/F31/F32) — should merge before F33 to avoid conflicts on shared files

## Out of scope

- Data Storage tab content (#43) — separate feature
- Legacy EditorTab / LineageTab deletion (#46) — blocked on all five tabs being complete
- Live migration execution (Run migration button) — future feature; ETL tab is review-only
- Pipeline stage execution timeline — ETL tab shows proposed migration state, not execution history
- Full-page editor entry point from ETL tab — the existing `/jobs/:id/editor` route is kept; entry point change deferred
