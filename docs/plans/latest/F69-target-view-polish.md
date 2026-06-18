# F69 — Target View Polish

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

Fix 11 issues identified during a browser review of the F67 Target ETL pipeline view. All changes are purely frontend across three files: `TargetGraph.tsx`, `FileNodeCard.tsx`, and `ETLTab.tsx`. No new API endpoints or backend changes needed.

Issues are ordered P0 (correctness bug) → P1 (signal corruption) → P2 (noise/missing context) → P3 (minor UX). Subtasks are grouped by logical area rather than strict priority so related file changes are batched.

## Acceptance Criteria

- [ ] Inspector panel opened from a Target node shows the `.py` filename in the header, not `.sas`
- [ ] No phantom arrow or dangling handle indicator appears on nodes with no incoming edges
- [ ] Connection count uses neutral color only — amber is reserved for trust status
- [ ] Summary bar shows `modules: N` when Target view is active
- [ ] Python module nodes show a `.py` badge instead of `PROGRAM`
- [ ] Isolated node row has a visible divider and label explaining why those nodes have no edges
- [ ] Handle dots are hidden on nodes with no connections in that direction
- [ ] Node names in Target view include the `.py` extension
- [ ] Legend uses rectangle swatches matching the accent bar shape, not circles
- [ ] Source / Target toggle buttons have `title` tooltips
- [ ] `make test` exits 0 (all 7 gates)

## Subtasks

### S-A: Inspector panel header — `.sas` → `.py` in Target view
**Files:** `src/frontend/src/components/JobDetail/BlockInspectorPanel.tsx`, `src/frontend/src/components/JobDetail/ETLTab.tsx`
**Depends on:** none
**Done when:** Clicking a Target node opens `BlockInspectorPanel` with the `.py` filename in the header, not the underlying SAS source file.

`BlockInspectorPanel` derives the header from `sourceFile` (the SAS path). Add an optional `displayTitle?: string` prop — when provided it replaces the header text without affecting `sourceFile` (which still drives block filtering).

```ts
// BlockInspectorPanel.tsx — new prop
interface BlockInspectorPanelProps {
  sourceFile: string;
  displayTitle?: string;   // overrides header display only
  // ...existing props
}
// In the header: use displayTitle ?? basename
```

In `ETLTab.tsx`, when `graphView === "target"`, pass `displayTitle` to the panel:
```tsx
<BlockInspectorPanel
  sourceFile={selectedFile}
  displayTitle={graphView === "target" ? sasFileToPyFile(selectedFile) : undefined}
  // ...
/>
```

`sasFileToPyFile` is already imported in `ETLTab.tsx`.

- [x] done

### S-B: Handle visibility — hide handles on nodes with no edges in that direction
**Files:** `src/frontend/src/components/JobDetail/FileNodeCard.tsx`, `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** none
**Done when:** The target handle (left dot) is hidden for nodes with no incoming edges; the source handle (right dot) is hidden for nodes with no outgoing edges. This eliminates both the phantom arrow on the root node and the misleading dots on the isolated zero-edge nodes.

Add two optional boolean fields to `FileNodeData` (both default to `true` so existing `LineageGraph` usage is unchanged without any modification):

```ts
// FileNodeCard.tsx
export type FileNodeData = {
  // ...existing fields
  hasIncoming?: boolean;  // default true — show target handle
  hasOutgoing?: boolean;  // default true — show source handle
};
```

In `FileNodeCard`, render each `Handle` conditionally:
```tsx
{(data.hasIncoming ?? true) && (
  <Handle type="target" position={Position.Left} style={...} />
)}
// ... node card div ...
{(data.hasOutgoing ?? true) && (
  <Handle type="source" position={Position.Right} style={...} />
)}
```

In `TargetGraph.tsx`, compute `hasIncoming` / `hasOutgoing` per node from `rawEdges` after they are built:
```ts
const incomingIds = new Set(rawEdges.map((e) => e.target));
const outgoingIds = new Set(rawEdges.map((e) => e.source));

// in the rawNodes map:
data: {
  // ...
  hasIncoming: incomingIds.has(pyFile),
  hasOutgoing: outgoingIds.has(pyFile),
}
```

- [x] done

### S-C: FileNodeCard — fix connection count color and symbol
**Files:** `src/frontend/src/components/JobDetail/FileNodeCard.tsx`
**Depends on:** none
**Done when:** Connection count never renders in amber (amber is reserved for trust status), and the symbol is `↔` (standard bidirectional arrow) rather than `⇔` (logical biconditional).

Two changes, both in the connection count `<span>`:

1. Color: remove the amber threshold entirely. Use `color: "#64748b"` (neutral slate-500) always, with `fontWeight: data.connectionCount >= 4 ? 700 : 400` to retain the emphasis for highly-connected nodes without stealing trust colors.

2. Symbol: change `⇔` to `↔`. Update the tooltip to: `${data.connectionCount} file connections (in + out)`.

```tsx
<span
  style={{
    fontSize: 10,
    fontFamily: "ui-monospace, monospace",
    fontWeight: data.connectionCount >= 4 ? 700 : 400,
    color: "#64748b",
  }}
  title={`${data.connectionCount} file connections (in + out)`}
>
  {data.connectionCount}↔
</span>
```

- [x] done

### S-D: Summary bar — show Target context stats
**Files:** `src/frontend/src/components/JobDetail/ETLTab.tsx`
**Depends on:** none
**Done when:** The summary bar shows `modules: N` when `graphView === "target"`, where N is the count of non-`pipeline.py` keys in `generatedFiles`.

Derive the count once:
```ts
const pyModuleCount = generatedFiles
  ? Object.keys(generatedFiles).filter((f) => f !== "pipeline.py").length
  : 0;
```

In the summary bar JSX, branch on `graphView`:
```tsx
{graphView === "source" ? (
  <>
    <span>files: {new Set(blockPlans.map((b) => b.source_file)).size}</span>
    <span>blocks: {blockPlans.length}</span>
  </>
) : (
  <span>modules: {pyModuleCount}</span>
)}
```

Keep the verified / review / manual counts unconditionally — they remain meaningful in Target view as they describe the migration quality of those modules.

- [x] done

### S-E: Python module badge — replace `PROGRAM` with `.py`
**Files:** `src/frontend/src/components/JobDetail/FileNodeCard.tsx`, `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** none
**Done when:** Target nodes show a green `.py` badge instead of the blue `PROGRAM` badge. Source nodes are unaffected.

Widen `FileNodeData.file_type` to accept an additional value without touching the API type:
```ts
export type FileNodeData = {
  file_type: FileNode["file_type"] | "MODULE";
  // ...
};
```

Add a `MODULE` entry to `FILE_TYPE_PILL` in `FileNodeCard.tsx`:
```ts
MODULE: {
  bg: "#f0fdf4",
  color: "#15803d",
  label: ".py",
  icon: <FileCode2 size={10} />,
},
```

`FILE_TYPE_PILL` key type must also be widened:
```ts
const FILE_TYPE_PILL: Record<FileNode["file_type"] | "MODULE", PillStyle> = { ... }
```

In `TargetGraph.tsx`, pass `file_type: "MODULE"` when building raw nodes:
```ts
data: {
  file_type: "MODULE",
  // ...
}
```

- [x] done

### S-F: Isolated row — divider and label
**Files:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** S-B (needs `isolatedNodes` split already in place)
**Done when:** A thin horizontal rule and the label "No data dependencies detected" appear between the connected graph and the isolated node row, visible within the ReactFlow canvas and included in `fitView`.

Add a custom ReactFlow node type `sectionLabel`. It renders a full-width label with a dividing line. The node is positioned at `y = connectedBottom + ISOLATED_GAP / 2 - 12` (vertically centred in the gap) and `x = connectedLeft`, with a width matching the span of the connected graph.

```tsx
// Module-level — outside component
const SectionLabelNode = () => (
  <div style={{
    display: "flex",
    alignItems: "center",
    gap: 8,
    pointerEvents: "none",
    userSelect: "none",
    width: "100%",
  }}>
    <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
    <span style={{ fontSize: 10, color: "#94a3b8", whiteSpace: "nowrap", fontWeight: 500 }}>
      No data dependencies detected
    </span>
    <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
  </div>
);

const NODE_TYPES = {
  fileNode: FileNodeCard,
  sectionLabel: SectionLabelNode,
};
```

When `isolatedNodes.length > 0`, push a divider node into `laid`:
```ts
if (isolatedNodes.length > 0) {
  const labelW = Math.max(
    ...laidConnected.map((n) => n.position.x + NODE_FILE_W),
    connectedLeft + isolatedNodes.length * ISOLATED_SPACING,
  ) - connectedLeft;

  laid.push({
    id: "__section-label__",
    type: "sectionLabel",
    position: { x: connectedLeft, y: connectedBottom + ISOLATED_GAP / 2 - 12 },
    data: {},
    selectable: false,
    draggable: false,
    style: { width: labelW, background: "transparent", border: "none" },
  });
}
```

- [x] done

### S-G: Node names — add `.py` extension in Target view
**Files:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** none
**Done when:** Target node card shows `01_build_sdtm_dm.py` rather than `01_build_sdtm_dm`.

One-line change in the raw node builder — pass `pyFile` directly as `filename` instead of the stripped `stem`:
```ts
data: {
  filename: pyFile,   // was: stem
  // ...
}
```

- [x] done

### S-H: Legend — use rectangle swatches instead of circles
**Files:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** none
**Done when:** The legend colour swatches are thin rectangles (matching the 3px accent bar on nodes) rather than filled circles.

In the legend JSX, change the swatch `<div>` style:
```tsx
// before
{ width: 10, height: 10, borderRadius: "50%", background: color }

// after
{ width: 18, height: 3, borderRadius: 2, background: color }
```

- [x] done

### S-I: Toggle button tooltips
**Files:** `src/frontend/src/components/JobDetail/ETLTab.tsx`
**Depends on:** none
**Done when:** Hovering "Source" shows `"SAS source pipeline"` and hovering "Target" shows `"Generated Python modules"`.

Add a `title` attribute to each toggle button:
```tsx
title={v === "source" ? "SAS source pipeline" : "Generated Python modules"}
```

- [x] done

### S-J: Tests green
**File:** n/a
**Depends on:** S-A through S-I
**Done when:** `make test` exits 0 — all 7 gates pass (tsc and frontend-build are the critical gates for these changes).

- [x] done

## Dependencies on other features

- F67 (ETL Source/Target toggle) — complete; all three files modified here were created or extended by F67

## Out of scope for this feature

- Composite block list in `BlockInspectorPanel` when a Python module aggregates multiple SAS source files (tracked separately, noted in F67)
- Column-level lineage in Target view
- Changing `⇔` to separate in/out counts (would require splitting `connectionCount: number` into `{ in: number; out: number }` and updating LineageGraph — too large for a polish pass)
