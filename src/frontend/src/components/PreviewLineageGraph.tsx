import type { AssessedBlock } from "@/api/types";
import dagre from "dagre";
import { Position, ReactFlow, ReactFlowProvider, Controls, MiniMap, MarkerType } from "reactflow";
import type { Edge, Node } from "reactflow";
import "reactflow/dist/style.css";

// ── Props ─────────────────────────────────────────────────────────────────────

interface PreviewLineageGraphProps {
  blocks: AssessedBlock[];
  outputDatasets: string[];
}

// ── Node types ────────────────────────────────────────────────────────────────

type NodeKind = "sas_file" | "dataset" | "output_dataset" | "external_input";

interface PreviewNodeData {
  label: string;
  kind: NodeKind;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DATASET_W = 160;
const DATASET_H = 48;
const FILE_W = 180;
const FILE_H = 56;

const NODE_STYLES: Record<NodeKind, React.CSSProperties> = {
  sas_file: {
    background: "#ffffff",
    border: "2px solid #3b82f6",
    borderRadius: 8,
    padding: "6px 12px",
    fontSize: 12,
    fontWeight: 600,
    color: "#1e3a5f",
    width: FILE_W,
    height: FILE_H,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    boxSizing: "border-box",
    boxShadow: "0 1px 4px rgba(59,130,246,0.15)",
  },
  dataset: {
    background: "#f8fafc",
    border: "1.5px solid #94a3b8",
    borderRadius: 6,
    padding: "4px 10px",
    fontSize: 11,
    fontWeight: 500,
    color: "#475569",
    width: DATASET_W,
    height: DATASET_H,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    boxSizing: "border-box",
  },
  output_dataset: {
    background: "#f0fdf4",
    border: "1.5px solid #22c55e",
    borderRadius: 6,
    padding: "4px 10px",
    fontSize: 11,
    fontWeight: 500,
    color: "#166534",
    width: DATASET_W,
    height: DATASET_H,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    boxSizing: "border-box",
  },
  external_input: {
    background: "#f8fafc",
    border: "1.5px dashed #94a3b8",
    borderRadius: 6,
    padding: "4px 10px",
    fontSize: 11,
    fontWeight: 400,
    color: "#94a3b8",
    width: DATASET_W,
    height: DATASET_H,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    boxSizing: "border-box",
  },
};

// ── Dagre layout ──────────────────────────────────────────────────────────────

function applyDagreLayout(
  nodes: Node<PreviewNodeData>[],
  edges: Edge[],
): Node<PreviewNodeData>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: "LR",
    nodesep: 40,
    ranksep: 80,
    marginx: 20,
    marginy: 20,
  });

  nodes.forEach((n) => {
    const isFile = n.data.kind === "sas_file";
    g.setNode(n.id, { width: isFile ? FILE_W : DATASET_W, height: isFile ? FILE_H : DATASET_H });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  return nodes.map((n) => {
    const isFile = n.data.kind === "sas_file";
    const w = isFile ? FILE_W : DATASET_W;
    const h = isFile ? FILE_H : DATASET_H;
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - w / 2, y: pos.y - h / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

// ── Graph builder ─────────────────────────────────────────────────────────────

function buildGraph(
  blocks: AssessedBlock[],
  outputDatasets: string[],
): { nodes: Node<PreviewNodeData>[]; edges: Edge[] } {
  const outputSet = new Set(outputDatasets.map((d) => d.toLowerCase()));

  // Collect all datasets produced by any block
  const producedDatasets = new Set<string>();
  for (const block of blocks) {
    for (const ds of block.output_datasets) {
      producedDatasets.add(ds.toLowerCase());
    }
  }

  // Collect all datasets consumed by any block
  const consumedDatasets = new Set<string>();
  for (const block of blocks) {
    for (const ds of block.input_datasets) {
      consumedDatasets.add(ds.toLowerCase());
    }
  }

  // Classify datasets
  const intermediateDatasets = new Set<string>();
  const externalInputDatasets = new Set<string>();
  const terminalOutputDatasets = new Set<string>();

  for (const ds of producedDatasets) {
    if (outputSet.has(ds)) {
      terminalOutputDatasets.add(ds);
    } else if (consumedDatasets.has(ds)) {
      intermediateDatasets.add(ds);
    } else {
      // Produced but not consumed and not declared as output — treat as terminal
      terminalOutputDatasets.add(ds);
    }
  }

  for (const ds of consumedDatasets) {
    if (!producedDatasets.has(ds)) {
      externalInputDatasets.add(ds);
    }
  }

  // Build nodes
  const nodes: Node<PreviewNodeData>[] = [];
  const nodeIds = new Set<string>();

  // Unique source files
  const sourceFiles = new Set<string>();
  for (const block of blocks) {
    if (block.source_file) sourceFiles.add(block.source_file);
  }

  const fileNodeId = (file: string) => `file:${file}`;
  const dsNodeId = (ds: string) => `ds:${ds.toLowerCase()}`;

  for (const file of sourceFiles) {
    const id = fileNodeId(file);
    if (!nodeIds.has(id)) {
      nodeIds.add(id);
      const basename = file.split("/").pop() ?? file;
      nodes.push({
        id,
        type: "default",
        position: { x: 0, y: 0 },
        data: { label: basename, kind: "sas_file" },
        style: NODE_STYLES.sas_file,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        draggable: false,
        selectable: false,
        connectable: false,
      });
    }
  }

  for (const ds of intermediateDatasets) {
    const id = dsNodeId(ds);
    if (!nodeIds.has(id)) {
      nodeIds.add(id);
      nodes.push({
        id,
        type: "default",
        position: { x: 0, y: 0 },
        data: { label: ds, kind: "dataset" },
        style: NODE_STYLES.dataset,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        draggable: false,
        selectable: false,
        connectable: false,
      });
    }
  }

  for (const ds of terminalOutputDatasets) {
    const id = dsNodeId(ds);
    if (!nodeIds.has(id)) {
      nodeIds.add(id);
      nodes.push({
        id,
        type: "default",
        position: { x: 0, y: 0 },
        data: { label: ds, kind: "output_dataset" },
        style: NODE_STYLES.output_dataset,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        draggable: false,
        selectable: false,
        connectable: false,
      });
    }
  }

  for (const ds of externalInputDatasets) {
    const id = dsNodeId(ds);
    if (!nodeIds.has(id)) {
      nodeIds.add(id);
      nodes.push({
        id,
        type: "default",
        position: { x: 0, y: 0 },
        data: { label: ds, kind: "external_input" },
        style: NODE_STYLES.external_input,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        draggable: false,
        selectable: false,
        connectable: false,
      });
    }
  }

  // Build edges (deduplicated)
  const edgeSet = new Set<string>();
  const edges: Edge[] = [];

  const addEdge = (source: string, target: string) => {
    const key = `${source}→${target}`;
    if (edgeSet.has(key)) return;
    if (!nodeIds.has(source) || !nodeIds.has(target)) return;
    edgeSet.add(key);
    edges.push({
      id: `e-${edgeSet.size}`,
      source,
      target,
      animated: true,
      style: { stroke: "#94a3b8", strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
    });
  };

  for (const block of blocks) {
    if (!block.source_file) continue;
    const fileId = fileNodeId(block.source_file);

    // file → output dataset (file produces this dataset)
    for (const ds of block.output_datasets) {
      addEdge(fileId, dsNodeId(ds));
    }

    // input dataset → file (dataset is consumed by this file)
    for (const ds of block.input_datasets) {
      addEdge(dsNodeId(ds), fileId);
    }
  }

  const laidOut = applyDagreLayout(nodes, edges);
  return { nodes: laidOut, edges };
}

// ── Inner component (needs ReactFlowProvider ancestor) ───────────────────────

function PreviewLineageGraphInner({
  blocks,
  outputDatasets,
}: PreviewLineageGraphProps): React.ReactElement | null {
  if (blocks.length === 0) return null;

  const { nodes, edges } = buildGraph(blocks, outputDatasets);

  if (nodes.length === 0) return null;

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      fitView
      fitViewOptions={{ padding: 0.25 }}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      panOnScroll
      zoomOnScroll
      style={{ width: "100%", height: "100%" }}
    >
      <Controls showInteractive={false} />
      <MiniMap
        nodeColor={(n) => {
          const kind = (n.data as PreviewNodeData).kind;
          if (kind === "sas_file") return "#3b82f6";
          if (kind === "output_dataset") return "#22c55e";
          if (kind === "external_input") return "#e2e8f0";
          return "#94a3b8";
        }}
        maskColor="rgba(255,255,255,0.6)"
      />
    </ReactFlow>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────

function LineageLegend(): React.ReactElement {
  const items: { label: string; style: React.CSSProperties }[] = [
    {
      label: "SAS file",
      style: { background: "#ffffff", border: "2px solid #3b82f6", borderRadius: 3 },
    },
    {
      label: "Intermediate dataset",
      style: { background: "#f8fafc", border: "1.5px solid #94a3b8", borderRadius: 3 },
    },
    {
      label: "Output dataset",
      style: { background: "#f0fdf4", border: "1.5px solid #22c55e", borderRadius: 3 },
    },
    {
      label: "External input",
      style: {
        background: "#f8fafc",
        border: "1.5px dashed #94a3b8",
        borderRadius: 3,
        opacity: 0.8,
      },
    },
  ];

  return (
    <div
      style={{
        position: "absolute",
        top: 8,
        right: 8,
        zIndex: 10,
        background: "rgba(255,255,255,0.92)",
        backdropFilter: "blur(4px)",
        borderRadius: 6,
        border: "1px solid #e2e8f0",
        padding: "6px 10px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
        pointerEvents: "none",
      }}
    >
      {items.map((item) => (
        <div key={item.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 16, height: 10, flexShrink: 0, ...item.style }} />
          <span style={{ fontSize: 10, color: "#475569", fontWeight: 500 }}>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Public export ─────────────────────────────────────────────────────────────

export default function PreviewLineageGraph(
  props: PreviewLineageGraphProps,
): React.ReactElement | null {
  if (props.blocks.length === 0) return null;

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <ReactFlowProvider>
        <PreviewLineageGraphInner {...props} />
      </ReactFlowProvider>
      <LineageLegend />
    </div>
  );
}
