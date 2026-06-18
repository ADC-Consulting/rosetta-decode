# F70 — Target ETL sub-views: Steps / Modules / Blocks

**Phase:** 3
**Area:** Frontend
**Status:** complete
**Branch:** `feat/F69-target-view-polish` (same branch — extends F69)

## Goal

The Source ETL view has three sub-views (`Pipeline | Files | Blocks`) inside the
LineageGraph canvas. The Target ETL view has none. This feature adds a matching
`Steps | Modules | Blocks` sub-toggle to the summary bar when Target is active,
with three Python-based views. Labels differ from Source to avoid confusion:
Source's "Pipeline/Files/Blocks" describes SAS artefacts; Target's
"Steps/Modules/Blocks" describes the generated Python side.

---

## Revised layouts

### Summary bar — toggle placement

Sub-toggle lives in the summary bar, **only visible when Target is active**.
This keeps the ReactFlow canvas free of toolbar clutter and is visually
parallel to the Source/Target toggle already in the bar.

```
Source active:
  files: 9  blocks: 26  ✓ verified: 8  ⚠ review: 13  ✗ manual: 5    Source▼  Target

Target active:
  modules: 9  ✓ verified: 8  ⚠ review: 13  ✗ manual: 5   Steps▼  Modules  Blocks  |  Source  Target▼
```

---

### Target — Steps view (default, replaces "Pipeline")

Top-to-bottom (TB) dagre layout. Rank depth = visual execution order.
No step-index numbers — column depth communicates sequence.
Node arrows flow **downward**. Parallel branches at the same rank sit side-by-side.

```
modules: 9  ✓ 8  ⚠ 13  ✗ 5    Steps▼  Modules  Blocks  |  Source  Target▼
┌──────────────────────────────────────────────────────┬──────────────────────┐
│                                                       │ 02_build_sdtm_ex.py ×│
│  ┌─────────────────┐ ┌──────────────────┐ ┌────────┐ │ ─────────────────── │
│  │02_build_sdtm_ex │ │m_derive_age_group│ │m_first │ │ 02_build_sdtm_ex.sas│
│  │.py  ▲ review    │ │.py  ▲ review     │ │_dose.py│ │ ─────────────────── │
│  │3 blocks         │ │1 block           │ │1 block │ │ PROC_IMPORT     :3  │
│  │deps: 0  → 1     │ │deps: 0  → 1      │ │deps:0  │ │ CSV import…  Review │
│  └────────┬────────┘ └────────┬─────────┘ └───┬────┘ │ ─────────────────── │
│           └──────────────────▼────────────────┘      │ PROC_SORT       :9  │
│                   ┌──────────────────────┐            │ NODUPKEY…     Pass  │
│                   │05_build_adam_adsl.py │            │ ─────────────────── │
│                   │ .py  ▲ review        │            │ DATA_STEP      :13  │
│                   │ 7 blocks             │            │ Derivation… Review  │
│                   │ deps: 3  → 2         │            │                     │
│                   └──────────┬───────────┘            │                     │
│                 ┌────────────┴────────────┐           │                     │
│          ┌──────▼───────┐  ┌─────────────▼─┐         │                     │
│          │01_build_     │  │03_build_stm_ae │         │                     │
│          │sdtm_dm.py    │  │.py  ✗ failures │         │                     │
│          │ .py  ✓ pass  │  │ 2 blocks       │         │                     │
│          │ 20 blocks    │  │ deps: 1  → 0   │         │                     │
│          │ deps: 1  → 0 │  └───────────────┘         │                     │
│          └──────────────┘                             │                     │
│  ── ── ── No data dependencies detected ── ── ──      │                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │                     │
│  │pharma_   │  │m_merge_  │  │04_build_ │            │                     │
│  │formats   │  │check.py  │  │sdtm_lb   │            │                     │
│  └──────────┘  └──────────┘  └──────────┘            │                     │
└──────────────────────────────────────────────────────┴──────────────────────┘
```

Node card fields: filename · `.py` badge · trust colour bar · block count ·
`deps: N` (modules this depends on) · `→ N` (modules downstream).

---

### Target — Modules view (renamed from "Files")

Unchanged dagre LR layout (current TargetGraph). Same node card as Steps view.
Clicking a node opens PythonModulePanel in the right slot.

```
modules: 9  ✓ 8  ⚠ 13  ✗ 5    Steps  Modules▼  Blocks  |  Source  Target▼
┌──────────────────────────────────────────────────────┬──────────────────────┐
│                                                       │ (same PythonModule-  │
│  [existing dagre LR module dependency graph]          │  Panel as Steps)     │
│                                                       │                     │
└──────────────────────────────────────────────────────┴──────────────────────┘
```

---

### Target — Blocks view

Same dagre LR dependency graph but **all node cards are pre-expanded** to show
their block rows inline. No accordion collapse — the full block list is always
visible inside the card. dagre layout is re-run with heights computed from block
count (`80px base + 36px × blockCount`). Clicking a block row opens the
block-detail right panel.

```
modules: 9  ✓ 8  ⚠ 13  ✗ 5    Steps  Modules  Blocks▼  |  Source  Target▼
┌──────────────────────────────────────────────────────┬──────────────────────┐
│                                                       │ DATA_STEP         ×  │
│  ┌────────────────────┐    ┌──────────────────────┐  │ m_derive_age_group   │
│  │02_build_sdtm_ex.py │    │05_build_adam_adsl.py │  │ .sas  :24–61         │
│  │────────────────────│    │──────────────────────│  │ ──────────────────── │
│  │PROC_IMPORT  :3  ⚠  │    │DATA_STEP    :5   ✓   │  │ Strategy  Translated │
│  │PROC_SORT    :9  ✓  ├───▶│DATA_STEP   :24   ⚠   │  │ Confidence  87%  ███ │
│  │DATA_STEP   :13  ⚠  │    │DATA_STEP   :32   ✓   │  │ Recon  Pass  ✓       │
│  └────────────────────┘    │PROC_SORT   :41   ✓   │  │ ──────────────────── │
│                             │DATA_STEP   :55   ⚠  ├─▶│ Age and baseline     │
│  ┌────────────────────┐    │DATA_STEP   :67   ✓   │  │ flag derivation ⓘ    │
│  │m_derive_age_group  │    │PROC_SORT   :78   ✓   │  │                      │
│  │────────────────────│    └──────────────────────┘  │ ┌──────────────────┐ │
│  │DATA_STEP  :24  ⚠◀─┼──────────── (selected)        │ │    View Code     │ │
│  └────────────────────┘                              │ └──────────────────┘ │
│                                                       │                     │
└──────────────────────────────────────────────────────┴──────────────────────┘
```

The selected block row is highlighted (subtle bg tint). No rationale text in the
right panel — only a `ⓘ` icon that shows a tooltip/popover on hover (same
pattern as Plan tab).

---

### Right panel — PythonModulePanel (single SAS source)

```
┌─────────────────────────────────┐
│ 02_build_sdtm_ex.py        [3] ×│
├─────────────────────────────────┤
│                                 │
│  02_build_sdtm_ex.sas           │  ← muted source label
│  ─────────────────────────────  │
│  PROC_IMPORT          :3  ⚠     │
│  PROC_SORT            :9  ✓     │
│  DATA_STEP           :13  ⚠     │
│                                 │
└─────────────────────────────────┘
```

Compact block rows: type · line · status icon. Clicking a row opens block-detail.
No rationale in this panel — keeps it scannable.

---

### Right panel — PythonModulePanel (multiple SAS sources)

SAS source groups use a light tinted background strip (`bg-slate-50`) on the
header row so group boundaries are scannable, not just readable.

```
┌─────────────────────────────────┐
│ 05_build_adam_adsl.py      [7] ×│
├─────────────────────────────────┤
│▓▓ 02_build_sdtm_ex.sas ▓▓▓▓▓▓▓▓│  ← tinted group header
│  DATA_STEP              :5  ✓   │
│                                 │
│▓▓ m_derive_age_group.sas ▓▓▓▓▓▓│  ← tinted group header
│  DATA_STEP             :24  ⚠   │
│                                 │
│▓▓ m_first_dose.sas ▓▓▓▓▓▓▓▓▓▓▓▓│  ← tinted group header
│  PROC_SORT              :9  ✓   │
│  DATA_STEP             :32  ✓   │
└─────────────────────────────────┘
```

---

### Right panel — Block detail (from Blocks view row click)

`ⓘ` rationale icon opens a popover rather than inline text — keeps the panel
compact. "Back" link shows the parent `.py` module name.

```
┌─────────────────────────────────┐
│ ← 05_build_adam_adsl.py      ×  │  ← back + close
├─────────────────────────────────┤
│  DATA_STEP                      │
│  m_derive_age_group.sas :24–61  │
│                                 │
│  Strategy    Translated         │
│  Confidence  87%  ████████░     │
│  Recon       Pass  ✓            │
│                             ⓘ   │  ← rationale popover on hover
│                                 │
│  ┌─────────────────────────┐    │
│  │       View Code         │    │
│  └─────────────────────────┘    │
└─────────────────────────────────┘
```

---

## Acceptance Criteria

- [x] Summary bar shows `Steps | Modules | Blocks` toggle when Target is active, hidden when Source is active; default = Steps
- [x] Steps view: dagre TB layout; modules positioned by topological rank depth; node cards show filename, `.py` badge, trust colour bar, block count, `deps: N`, `→ N`; clicking a node opens PythonModulePanel
- [x] Modules view: existing dagre LR graph (current TargetGraph); clicking a node opens PythonModulePanel
- [x] Blocks view: dagre LR graph; node heights computed from block count; block rows visible inline; selected block row highlighted; clicking a row opens block-detail right panel
- [x] PythonModulePanel: `.py` header + block count + close; single-source = flat block list; multi-source = tinted group headers per SAS source; clicking a row opens block-detail
- [x] Block-detail panel: back link + close; block type, file:lines, strategy, confidence bar, recon status; `ⓘ` rationale popover; "View Code" → BlockCodePopup
- [x] Sub-view selection persists when toggling Source ↔ Target
- [x] `make test` exits 0

---

## Subtasks

### S-A: Summary bar sub-toggle + state in ETLTab
**File:** `src/frontend/src/components/JobDetail/ETLTab.tsx`
**Depends on:** none
**Done when:** `targetView: "steps" | "modules" | "blocks"` state added to ETLTab, defaults to `"steps"`. `Steps | Modules | Blocks` button group renders in the summary bar **only when `graphView === "target"`**. Passed as `view={targetView}` and `onViewChange={setTargetView}` props into `TargetGraph`. Switching to Source hides the toggle but preserves the selected `targetView` for when the user returns to Target.

- [x] done

### S-B: TargetGraph view prop + layout switching
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** S-A
**Done when:** `TargetGraph` accepts `view: "steps" | "modules" | "blocks"` and `onModuleClick: (pyFile: string) => void` and `onBlockClick: (blockId: string) => void`. Internal `useMemo` branches on `view` to build the correct node set, edge set, and dagre config before passing to ReactFlow. The three branches share the `rawEdges` derivation; only layout direction and node type differ.

- [x] done

### S-C: Steps view — TB layout + PipelineStepNode
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** S-B
**Done when:** When `view === "steps"`, dagre uses `rankdir: "TB", nodesep: 60, ranksep: 140`. A new module-scope `PipelineStepNode` renders: filename (mono), `.py` badge (green), trust colour bar (left border), block count, `deps: N  → N`. No step-index numbers. `NODE_TYPES` extended with `pipelineStep: PipelineStepNode`. `hasIncoming`/`hasOutgoing` logic reused to hide handles on sources/sinks. Isolated nodes placed in a row below the connected cluster with existing `SectionLabelNode` divider (horizontal offset instead of vertical since layout is now TB).

- [x] done

### S-D: Modules view — existing graph gated behind view branch
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** S-B
**Done when:** Existing `FileNodeCard`-based LR graph is unchanged, now rendered only when `view === "modules"`. Node click calls `onModuleClick(pyFile)`. No other changes.

- [x] done

### S-E: Blocks view — expanded node cards with inline block rows
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** S-B
**Done when:** When `view === "blocks"`, node heights are computed as `BLOCKS_BASE_H + BLOCK_ROW_H * blockCount` (e.g. 80 + 36 × N) and passed to dagre. A new module-scope `BlocksFileNode` renders the filename header + a list of block rows (type badge, `:line`, status icon). Clicking a block row calls `onBlockClick(blockId)`. The currently-selected block row gets a subtle `bg-slate-50` highlight. `hasIncoming`/`hasOutgoing` handle hiding reused.

- [x] done

### S-F: PythonModulePanel component
**File:** `src/frontend/src/components/JobDetail/PythonModulePanel.tsx` (new)
**Depends on:** none
**Done when:** Component renders the right panel for a clicked Python module.

```tsx
interface PythonModulePanelProps {
  pyFile: string;
  sasSourceFiles: string[];          // pyFileToSasFiles(pyFile, blockPlans)
  blockPlans: BlockPlan[];
  trustBlocks: Record<string, TrustReportBlock>;
  humanVerifiedBlocks: Set<string>;
  onBlockClick: (blockId: string) => void;
  onClose: () => void;
}
```

- Header: `pyFile` mono semibold + block count badge + close button
- When `sasSourceFiles.length === 1`: flat block list sorted by `start_line`, each row via `<BlockRow>` (reuse from `BlockInspectorPanel`)
- When `sasSourceFiles.length > 1`: a tinted header row (`bg-slate-50 px-3 py-1 text-xs text-muted-foreground`) per SAS source, with its blocks below
- Empty state: "No blocks found for this module."
- Clicking any block row calls `onBlockClick(blockId)`

- [x] done

### S-G: Block-detail right panel state in ETLTab
**File:** `src/frontend/src/components/JobDetail/ETLTab.tsx`
**Depends on:** S-A, S-F
**Done when:** `selectedPyModule: string | null` state added. `selectedBlock: string | null` already exists (used for BlockCodePopup). When `graphView === "target"`:
- Module node click → `setSelectedPyModule(pyFile)`, clear `selectedBlock`
- Block row click (from Blocks view or PythonModulePanel) → `setSelectedBlock(blockId)` only; if called from Blocks view, also set `selectedPyModule` (for the back-link)
- Right slot renders `<PythonModulePanel>` when `selectedPyModule` is set and no block-detail mode is active
- Right slot renders `<BlockDetailPanel>` when a block is selected in Target mode (see S-H)
- Switching Source ↔ Target clears `selectedPyModule`

- [x] done

### S-H: BlockDetailPanel component
**File:** `src/frontend/src/components/JobDetail/BlockDetailPanel.tsx` (new)
**Depends on:** S-F
**Done when:** Compact right panel showing one block's metadata.

```tsx
interface BlockDetailPanelProps {
  blockId: string;
  blockPlan: BlockPlan;
  trustBlock: TrustReportBlock | undefined;
  isHumanVerified: boolean;
  parentPyFile: string;              // for the back link label
  onBack: () => void;                // returns to PythonModulePanel
  onViewCode: (blockId: string) => void;
  onClose: () => void;
}
```

Renders:
- Header: `← {parentPyFile}` back link + close button
- Block type (bold mono) + `{sourceFile} :{startLine}–{endLine}`
- Strategy badge, confidence % with inline bar (`████░`), recon status icon
- `ⓘ` icon button that opens a `Tooltip`/`Popover` with the rationale text (same shadcn `Popover` pattern used in Plan tab)
- "View Code" button → `onViewCode(blockId)` → ETLTab opens `BlockCodePopup`

- [x] done

### S-I: `make test` exits 0
**File:** n/a
**Depends on:** S-A through S-H
**Done when:** All 7 gates pass — tsc, eslint, and frontend-build are critical for this feature.

- [x] done

---

## Key design decisions

| Decision | Rationale |
|---|---|
| Sub-toggle in summary bar, not in canvas | Avoids conflicting with ReactFlow controls; consistent with Source/Target toggle position |
| Names: Steps/Modules/Blocks not Pipeline/Files/Blocks | Source uses Pipeline/Files/Blocks for SAS artefacts; different names prevent confusion about which side you're viewing |
| Steps view uses TB layout | Top-to-bottom reads as execution order; LR (Modules view) reads as dependency graph — distinct visual language for distinct purposes |
| No step-index numbers in Steps view | Rank depth column position communicates sequence; numbers imply strict linear order but the graph is a DAG with parallel branches |
| `deps: N  → N` not `↑ N in ↓ N out` | "deps" and "→" are unambiguous about direction in a Python module context |
| Blocks view expands nodes in-place | Preserves spatial dependency context; avoids jarring switch from graph to list |
| Rationale as `ⓘ` popover in block-detail | Keeps the panel compact; rationale is secondary info; matches Plan tab pattern |
| Tinted group headers in multi-source panel | Scannable at a glance; muted text alone is insufficient when 7+ blocks span 3 groups |

## Dependencies on other features

- F69 (Target view polish) — complete; same branch

## Out of scope

- Undo/Redo/Reset toolbar in Target view
- Editing Python code from right panel (BlockCodePopup handles this)
- Source sub-views moved to summary bar (out of scope; Source toolbar stays in canvas)
