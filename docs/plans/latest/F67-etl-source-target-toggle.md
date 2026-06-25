# F67 — ETL Tab: Source / Target Toggle

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

The ETL tab currently shows only the SAS-side pipeline — source files, lineage graph, and block-level review. Users also need to see what the **target Python pipeline looks like**: which Python modules are produced, how data flows between them, and which modules still need attention.

Add a **Source / Target** two-state toggle at the top of the ETL tab canvas. "Source" is the existing SAS lineage graph (no behaviour change). "Target" is a new Python pipeline graph where nodes are the actual generated `.py` files (keyed from `JobStatus.generated_files`), edges are the SAS file-level data flow remapped to Python filenames, and nodes are coloured by the same trust-report verification status used in the Source view. Clicking a Target node opens the existing `BlockInspectorPanel` for that file's blocks. The full review workflow (inspector → `BlockCodePopup` → mark verified) works from either view.

## Acceptance Criteria

- [ ] A "Source / Target" two-state toggle appears right-aligned in the ETL tab summary bar
- [ ] "Source" renders the existing `LineageGraph` with its Pipeline / Files / Blocks sub-views unchanged
- [ ] "Target" is disabled (greyed out) when `generatedFiles` is null, empty, or contains only `pipeline.py`
- [ ] "Target" renders a Python module graph: nodes are keys of `generatedFiles` excluding `pipeline.py`, coloured by trust-report aggregate status
- [ ] Edges in Target view are `file_edges` remapped to Python filenames; self-loops, edges involving `pipeline.py`, and edges where either endpoint has no corresponding node are silently dropped
- [ ] Target nodes are coloured green / amber / red using the same trust-report logic as the Files view
- [ ] Clicking a Target node opens `BlockInspectorPanel` for all SAS source files that contributed to that Python module (handles the many-SAS-to-one-Python case)
- [ ] Toggling Source ↔ Target clears `selectedFile` and `selectedStep` (side panel resets)
- [ ] Block review flow (BlockInspectorPanel → BlockCodePopup → mark verified) works identically from Target view
- [ ] Toggle resets to "Source" on tab re-mount (no persistence)
- [ ] `make test` exits 0

## Subtasks

### S-A: SAS → Python filename utility
**File:** `src/frontend/src/lib/sas-python-file-map.ts`
**Depends on:** none
**Done when:** Two pure TS functions exist and are exported: `sasFileToPyFile` and `pyFileToSasFiles`.

```ts
import type { BlockPlan } from "@/api/types";

// Mirrors backend _sas_to_module_name exactly:
// strips directory components, then strips everything after the last dot.
// "subdir/01_build_sdtm_dm.sas" → "01_build_sdtm_dm.py"
// "utils.sas7bdat" → "utils.py"   (matches os.path.splitext behaviour)
export function sasFileToPyFile(sourceFile: string): string {
  const basename = sourceFile.split("/").pop() ?? sourceFile;
  const lastDot = basename.lastIndexOf(".");
  const stem = lastDot > 0 ? basename.slice(0, lastDot) : basename;
  return `${stem}.py`;
}

// Returns all SAS source files in blockPlans that map to a given Python filename.
// When the result has >1 entry, those SAS files were merged into one Python module.
export function pyFileToSasFiles(pyFile: string, blockPlans: BlockPlan[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const bp of blockPlans) {
    if (sasFileToPyFile(bp.source_file) === pyFile && !seen.has(bp.source_file)) {
      seen.add(bp.source_file);
      result.push(bp.source_file);
    }
  }
  return result;
}
```

- [x] done

### S-B: TargetGraph component
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** S-A
**Done when:** A `TargetGraph` React component renders a ReactFlow graph of Python module nodes, trust-coloured, with remapped and filtered edges, a sticky legend, and fires `onFileClick` with the list of contributing SAS source files when a node is clicked.

**Props:**
```ts
interface TargetGraphProps {
  lineage: JobLineageResponse;
  generatedFiles: Record<string, string>; // keys are authoritative node list
  blockPlans: BlockPlan[];
  trustFiles?: TrustReportFile[];
  onFileClick: (sasSourceFiles: string[]) => void;
}
```

**Node derivation:**
- Node set = `Object.keys(generatedFiles).filter(f => f !== "pipeline.py")`
- Each node uses `FileNodeCard` (same component as Files view in `LineageGraph`)
- `filename` displayed = stem without `.py` extension (e.g. `01_build_sdtm_dm`)
- `fullPath` = the `.py` filename (used as node ID)
- Status: for each `.py` file, call `pyFileToSasFiles(pyFile, blockPlans)` to get contributing SAS files, find their `TrustReportFile` entries, aggregate:
  - any `failed_reconciliation > 0` → `"UNRECOGNIZED"` (red)
  - else any `needs_review > 0 || manual_todo > 0` → `"ERROR_PRONE"` (amber)
  - else → `"OK"` (green)
  - no trust data → `null` (neutral)

**Edge derivation:**
- Iterate `lineage.file_edges ?? []`
- Map both `source_file` and `target_file` through `sasFileToPyFile`
- Drop the edge if:
  - either endpoint is `"pipeline.py"`
  - either endpoint is not in the node set (missing node guard)
  - source === target (self-loop guard)
- Deduplicate by `(pySource, pyTarget)` — multiple SAS edges can collapse to the same Python edge
- Render using `HoverLabelEdge` with reason colour, same as Files view

**Layout:** `applyDagreLayout` with `ranksep: 160, nodesep: 75` (same as Files view).

**On node click:** call `onFileClick(pyFileToSasFiles(node.id, blockPlans))` — passes the full list of contributing SAS source files, not just `[0]`.

**Legend:** sticky bottom-left, reuse `FilesLegend` from `LineageGraph`. Label the legend section "Python modules".

**Empty state:** if `Object.keys(generatedFiles).filter(f => f !== "pipeline.py").length === 0`, render a centred message: "No Python modules generated for this job."

Wrap in `ReactFlowProvider`. Include `Controls`, `Background`, `fitView`.

- [x] done

### S-C: Source / Target toggle in ETLTab + prop plumbing
**File:** `src/frontend/src/components/JobDetail/ETLTab.tsx`
**Depends on:** S-B
**Done when:** The toggle is visible in the summary bar, Source/Target switch correctly, side panel resets on toggle, and `generatedFiles` prop is threaded through.

**New prop on ETLTab:**
```ts
interface ETLTabProps {
  // ... existing props ...
  generatedFiles: Record<string, string> | null; // from JobStatus.generated_files
}
```

**State:**
```ts
const [graphView, setGraphView] = useState<"source" | "target">("source");
```

**Toggle handler** — clears side panel state on switch:
```ts
function handleToggle(next: "source" | "target") {
  setGraphView(next);
  setSelectedFile(null);
  setSelectedStep(null);
}
```

**Toggle button** — right-aligned in the summary bar row, two buttons styled like the Pipeline/Files/Blocks switcher in `LineageGraph`:

```tsx
<div className="ml-auto flex items-center gap-1">
  {(["source", "target"] as const).map((v) => {
    const disabled = v === "target" && !hasTargetNodes;
    return (
      <button
        key={v}
        onClick={() => handleToggle(v)}
        disabled={disabled}
        className={[
          "px-2 py-0.5 rounded text-[11px] font-medium border transition-colors",
          graphView === v
            ? "bg-foreground text-background border-foreground"
            : "bg-transparent text-muted-foreground border-border hover:border-foreground/40",
          disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer",
        ].join(" ")}
      >
        {v.charAt(0).toUpperCase() + v.slice(1)}
      </button>
    );
  })}
</div>
```

Where:
```ts
const hasTargetNodes = !!generatedFiles &&
  Object.keys(generatedFiles).some(f => f !== "pipeline.py");
```

**Graph rendering:**
```tsx
{graphView === "source" ? (
  <LineageGraph ... />  // unchanged
) : (
  <TargetGraph
    lineage={etlLineage}
    generatedFiles={generatedFiles ?? {}}
    blockPlans={blockPlans}
    trustFiles={trustReport?.files}
    onFileClick={(sasFiles) => {
      setSelectedFile(sasFiles[0] ?? null);
      setSelectedStep(null);
    }}
  />
)}
```

`key` prop includes `graphView` to force remount on toggle.

**BlockInspectorPanel — multi-file case:** `BlockInspectorPanel` currently filters by a single `sourceFile`. For the Target view, a Python node can correspond to multiple SAS source files. For now: pass `sasFiles[0]` (the first contributing SAS file) and add a note comment `// TODO F67: show composite block list for merged modules`. This is an explicit acknowledged limitation, not a silent data loss.

**Caller (JobDetailPage or equivalent):** add `generatedFiles={jobStatus?.generated_files ?? null}` when rendering `<ETLTab>`.

- [x] done

### S-D: Tests green
**File:** n/a
**Depends on:** S-C
**Done when:** `make test` exits 0 — all 7 gates pass.

- [x] done

## Known limitations (in-scope for follow-up, not this feature)

- `BlockInspectorPanel` shows only `sasFiles[0]` when a Python module aggregates multiple SAS source files — a composite block list is needed but deferred
- Column-level lineage is not shown in Target view

## Dependencies on other features

- F33 (ETL tab scaffold) — complete
- F35 (trust report) — complete; `TrustReportFile`, `TrustReportResponse` already in ETLTab
- `fix/etl-tab-navigation-polish` — must be merged (or this feature branched from it) before implementation starts

## Out of scope for this feature

- Databricks / Airflow DAG export
- Column-level lineage in Target view
- Persisting the Source/Target toggle across tab navigation
- Showing `pipeline.py` as a node
- Any new backend API endpoints
- Composite block list for merged Python modules (deferred, noted above)
