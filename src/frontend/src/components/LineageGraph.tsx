import type {
  BlockPlan,
  FileEdge,
  FileNode,
  JobLineageResponse,
  LineageNode,
  PipelineStep,
  TrustReportBlock,
  TrustReportFile,
} from "@/api/types";
import {
  FileNodeCard,
  type FileNodeData,
} from "@/components/JobDetail/FileNodeCard";
import { LineageDetailPanel } from "@/components/JobDetail/LineageDetailPanel";
import {
  PipelineStepCard,
  type PipelineStepData,
} from "@/components/JobDetail/PipelineStepCard";
import dagre from "dagre";
import { RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  getBezierPath,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type EdgeChange,
  type EdgeProps,
  type Node,
  type NodeChange,
} from "reactflow";
import "reactflow/dist/style.css";

interface LineageGraphProps {
  lineage: JobLineageResponse;
  blockPlans?: BlockPlan[];
  onFileNodeClick?: (file: FileNode) => void;
  onPipelineStepClick?: (step: PipelineStep) => void;
  trustFiles?: TrustReportFile[];
  trustBlocks?: Record<string, TrustReportBlock>;
  initialView?: "blocks" | "files" | "pipeline";
  selectedFilePath?: string | null;
  humanVerifiedBlocks?: Set<string>;
}

type NodeData = {
  label: React.ReactNode;
  status: LineageNode["status"];
  block_type: string;
  rawLabel: string;
};

// ---------------------------------------------------------------------------
// Status styles
// ---------------------------------------------------------------------------

const STATUS_STYLE: Record<
  LineageNode["status"],
  { background: string; border: string; color: string }
> = {
  migrated: { background: "#f5f5f5", border: "#22c55e", color: "#1a1a1a" },
  manual_review: { background: "#f5f5f5", border: "#f59e0b", color: "#1a1a1a" },
  unrecognized: {
    background: "#f5f5f5",
    border: "#ef4444",
    color: "#1a1a1a",
  },
};

const STATUS_LABEL: Record<LineageNode["status"], string> = {
  migrated: "Migrated",
  manual_review: "Needs review",
  unrecognized: "Manual required",
};

const STATUS_SYMBOL: Record<
  LineageNode["status"],
  { symbol: string; color: string }
> = {
  migrated: { symbol: "✓", color: "#22c55e" },
  manual_review: { symbol: "⚠", color: "#f59e0b" },
  unrecognized: { symbol: "✗", color: "#ef4444" },
};

function abbrevBlockType(bt: string): string {
  const map: Record<string, string> = {
    DATA_STEP: "DATA",
    PROC_SQL: "PROC SQL",
    PROC_SORT: "PROC SORT",
    PROC_MEANS: "PROC MEANS",
    PROC_FREQ: "PROC FREQ",
    PROC_PRINT: "PROC PRINT",
    PROC_TRANSPOSE: "PROC TRANSPOSE",
    PROC_IMPORT: "PROC IMPORT",
    PROC_EXPORT: "PROC EXPORT",
    PROC_LOGISTIC: "PROC LOGISTIC",
    PROC_REG: "PROC REG",
  };
  return map[bt] ?? bt.replace(/_/g, " ");
}

const NODE_W = 210;
const NODE_H = 72;
const NODE_FILE_W = 220;
const NODE_FILE_H = 96;
const NODE_PIPELINE_W = 240;
const NODE_PIPELINE_H = 86;

// ---------------------------------------------------------------------------
// Edge reason colors — files view
// ---------------------------------------------------------------------------

const REASON_COLORS: Record<string, string> = {
  reads_dataset: "#3b82f6",
  writes_dataset: "#ef4444",
  include: "#8b5cf6",
  macro_call: "#f59e0b",
};

// Distinct dash patterns per edge reason so type is readable even in greyscale
const REASON_DASH: Record<string, string | undefined> = {
  reads_dataset: undefined,     // solid
  writes_dataset: "8 4",        // long-dash
  include: "6 3",               // dashed
  macro_call: "2 3",            // dotted
};

function reasonColor(reason: string): string {
  return REASON_COLORS[normalizeReason(reason)] ?? "#64748b";
}

function reasonDash(reason: string): string | undefined {
  return REASON_DASH[normalizeReason(reason)];
}

// ---------------------------------------------------------------------------
// HoverLabelEdge — shows label only on hover, fades when not hovered
// ---------------------------------------------------------------------------

function HoverLabelEdge({
  id,
  sourceX,
  sourceY,
  sourcePosition,
  targetX,
  targetY,
  targetPosition,
  data,
  markerEnd,
  style,
}: EdgeProps<{ label?: string }>) {
  const [hovered, setHovered] = useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          ...style,
          strokeWidth: hovered ? 2.5 : 1.5,
          opacity: hovered ? 1 : (style?.opacity ?? 0.45),
          transition: "stroke-width 0.1s ease, opacity 0.1s ease",
        }}
      />
      {/* Invisible wide hit-area so hovering is easy */}
      <path
        d={edgePath}
        fill="none"
        strokeWidth={14}
        stroke="transparent"
        style={{ cursor: "pointer" }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {hovered && data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              background: "#1e293b",
              color: "#e2e8f0",
              fontSize: 10,
              fontWeight: 500,
              borderRadius: 4,
              padding: "2px 8px",
              pointerEvents: "none",
              whiteSpace: "nowrap",
              border: "1px solid #334155",
              boxShadow: "0 2px 8px rgba(0,0,0,0.35)",
              fontFamily: "ui-monospace, monospace",
              zIndex: 1000,
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

// CRITICAL: module-level, never inside a component
const NODE_TYPES = {
  fileNode: FileNodeCard,
  pipelineNode: PipelineStepCard,
};
const EDGE_TYPES = { hover: HoverLabelEdge };

// ---------------------------------------------------------------------------
// Dagre layout
// ---------------------------------------------------------------------------

function applyDagreLayout<T extends object>(
  nodes: Node<T>[],
  edges: Edge[],
  nodeW: number,
  nodeH: number,
  opts?: { ranksep?: number; nodesep?: number },
): Node<T>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: "LR",
    nodesep: opts?.nodesep ?? 50,
    ranksep: opts?.ranksep ?? 90,
    marginx: 20,
    marginy: 20,
  });
  nodes.forEach((n) => g.setNode(n.id, { width: nodeW, height: nodeH }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - nodeW / 2, y: pos.y - nodeH / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

// ---------------------------------------------------------------------------
// Builders — blocks view
// ---------------------------------------------------------------------------

function buildDataFileNode(n: LineageNode): Node<NodeData> {
  const ext = (n.extension ?? "").replace(".", "").toUpperCase() || "FILE";
  return {
    id: n.id,
    type: "default",
    data: {
      rawLabel: n.label,
      block_type: "DATA_FILE",
      status: "migrated",
      label: (
        <div style={{ lineHeight: 1.35 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#0369a1", fontFamily: "monospace" }}>
            {ext}
          </div>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "#111",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {n.label}
          </div>
          {n.columns && n.columns.length > 0 && (
            <div style={{ fontSize: 9, color: "#9ca3af", marginTop: 2, fontFamily: "monospace" }}>
              {n.columns.slice(0, 4).join(", ")}
              {n.columns.length > 4 ? ` +${n.columns.length - 4}` : ""}
            </div>
          )}
        </div>
      ),
    },
    position: { x: 0, y: 0 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    draggable: true,
    style: {
      background: "rgba(240,249,255,0.95)",
      borderWidth: "1.5px",
      borderStyle: "dashed",
      borderColor: "#0ea5e9",
      borderBottomWidth: "3px",
      color: "#333",
      borderRadius: 8,
      padding: "8px 12px",
      boxShadow: "0 1px 4px rgba(0,0,0,0.1)",
      width: NODE_W,
      minHeight: NODE_H,
      transition: "opacity 0.18s ease",
    },
  };
}

function buildInitialNodes(
  lineageNodes: LineageNode[],
  blockPlanMap?: Map<string, BlockPlan>,
  trustBlocks?: Record<string, TrustReportBlock>,
  humanVerifiedBlocks?: Set<string>,
): Node<NodeData>[] {
  return lineageNodes.map((n) => {
    if (n.node_type === "DATA_FILE") return buildDataFileNode(n);

    // Derive status from plan + trust data; lineage node status is a fallback
    let resolvedStatus = n.status;
    if (blockPlanMap) {
      const bp = blockPlanMap.get(n.id);
      if (bp?.strategy === "manual") resolvedStatus = "unrecognized";
    }
    if (trustBlocks && resolvedStatus !== "unrecognized") {
      // block_id in trustBlocks uses single ":" but node id uses "::"
      const singleColonId = n.id.replace("::", ":");
      const tb = trustBlocks[singleColonId];
      if (tb?.needs_attention) resolvedStatus = "manual_review";
    }

    const singleColonId = n.id.replace("::", ":");
    const isHumanVerified = humanVerifiedBlocks?.has(singleColonId) ?? false;
    const style = isHumanVerified
      ? { background: "#f0fdfa", border: "#0d9488", color: "#1a1a1a" }
      : STATUS_STYLE[resolvedStatus] ?? STATUS_STYLE["manual_review"];
    const sym = isHumanVerified
      ? { symbol: "✓", color: "#0d9488" }
      : STATUS_SYMBOL[resolvedStatus] ?? STATUS_SYMBOL["unrecognized"];
    return {
      id: n.id,
      type: "default",
      data: {
        rawLabel: n.label,
        block_type: n.block_type ?? "",
        status: resolvedStatus,
        label: (
          <div
            style={{ position: "relative", lineHeight: 1.35, paddingRight: 14 }}
          >
            {/* Status badge — top-right */}
            <span
              style={{
                position: "absolute",
                top: -2,
                right: -8,
                fontSize: 10,
                fontWeight: 700,
                color: sym.color,
                lineHeight: 1,
              }}
            >
              {sym.symbol}
            </span>
            {/* Label */}
            <div
              style={{
                fontSize: 14,
                fontWeight: 700,
                color: "#111",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {n.label}
            </div>
            {/* block_type abbreviated */}
            <div
              style={{
                fontSize: 10,
                fontFamily: "monospace",
                color: "#9ca3af",
                marginTop: 3,
              }}
            >
              {abbrevBlockType(n.block_type ?? "")}
            </div>
            {/* source_file — filename only */}
            <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 1 }}>
              {(n.source_file ?? "").split("/").pop() ?? n.source_file}
            </div>
          </div>
        ),
      },
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: true,
      style: {
        background: "rgba(245,245,245,0.92)",
        borderWidth: "1.5px",
        borderStyle: "solid",
        borderColor: style.border,
        borderBottomWidth: "3px",
        color: "#333",
        borderRadius: 8,
        padding: "8px 12px",
        boxShadow: "0  1px 4px rgba(0,0,0,0.15)",
        width: NODE_W,
        minHeight: NODE_H,
        transition: "opacity 0.18s ease",
      },
    };
  });
}

function buildInitialEdges(
  lineageEdges: JobLineageResponse["edges"],
  columnFlows: JobLineageResponse["column_flows"],
): Edge[] {
  return lineageEdges.map((e) => {
    const colCount = columnFlows
      ? columnFlows.filter((cf) => cf.via_block_id === e.source).length
      : 0;
    return {
      id: `e-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      animated: false,
      label: colCount > 0 ? `${colCount} cols` : undefined,
      labelStyle: { fontSize: 10, fill: "#6b7280" },
      labelBgStyle: { fill: "rgba(255,255,255,0.8)" },
      style: {
        stroke: "#94a3b8",
        strokeWidth: 1.5,
        ...(e.inferred ? { strokeDasharray: "5 5" } : {}),
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
    };
  });
}

// ---------------------------------------------------------------------------
// Builders — file view
// ---------------------------------------------------------------------------

function buildFileNodes(
  fileNodes: FileNode[],
  fileEdges: FileEdge[],
  selectedPath: string | null,
  trustFiles?: TrustReportFile[],
): Node<FileNodeData>[] {
  const degree = new Map<string, number>();
  for (const fe of fileEdges) {
    degree.set(fe.source_file, (degree.get(fe.source_file) ?? 0) + 1);
    degree.set(fe.target_file, (degree.get(fe.target_file) ?? 0) + 1);
  }
  return fileNodes.map((fn) => {
    const basename = fn.filename.split("/").pop() ?? fn.filename;

    let status = fn.status;

    // If trustFiles provided, override status with trustReport-derived aggregate
    if (trustFiles) {
      const tf = trustFiles.find((f) => f.source_file === fn.filename);
      if (tf) {
        let overrideStatus: FileNode["status"];
        if (tf.failed_reconciliation > 0) {
          // red — use existing UNRECOGNIZED colour
          overrideStatus = "UNRECOGNIZED";
        } else if (tf.needs_review > 0 || tf.manual_todo > 0) {
          // amber
          overrideStatus = "ERROR_PRONE";
        } else {
          // green
          overrideStatus = "OK";
        }
        status = overrideStatus;
      }
    }

    return {
      id: `file-${fn.filename}`,
      type: "fileNode",
      position: { x: 0, y: 0 },
      data: {
        filename: basename,
        fullPath: fn.filename,
        file_type: fn.file_type,
        status,
        blockCount: fn.blocks.length,
        connectionCount: degree.get(fn.filename) ?? 0,
        isSelected: fn.filename === selectedPath,
      },
    };
  });
}

function normalizeReason(r: string): string {
  return r.toLowerCase().replace(/ /g, "_");
}

function humanizeReason(r: string): string {
  return normalizeReason(r).replace(/_/g, " ");
}

function buildFileEdges(fileEdges: FileEdge[]): Edge[] {
  const grouped = new Map<string, string[]>();
  for (const fe of fileEdges) {
    const key = `${fe.source_file}||${fe.target_file}`;
    const reasons = grouped.get(key) ?? [];
    reasons.push(humanizeReason(fe.reason));
    grouped.set(key, reasons);
  }
  return Array.from(grouped.entries()).map(([key, reasons]) => {
    const [src, tgt] = key.split("||");
    const color = reasonColor(reasons[0]);
    const dash = reasonDash(reasons[0]);
    return {
      id: `fe-${src}-${tgt}`,
      source: `file-${src}`,
      target: `file-${tgt}`,
      type: "hover",
      data: { label: reasons.join(", ") },
      style: { stroke: color, strokeWidth: 1.5, ...(dash ? { strokeDasharray: dash } : {}) },
      markerEnd: { type: MarkerType.ArrowClosed, color },
    };
  });
}

// ---------------------------------------------------------------------------
// Builders — pipeline view
// ---------------------------------------------------------------------------

function buildPipelineNodes(steps: PipelineStep[]): Node<PipelineStepData>[] {
  return steps.map((s, i) => ({
    id: `step-${s.step_id}`,
    type: "pipelineNode",
    position: { x: 0, y: 0 },
    data: {
      stepNumber: i + 1,
      name: s.name,
      description: s.description,
      inputCount: s.inputs.length,
      outputCount: s.outputs.length,
    },
  }));
}

function buildPipelineEdges(steps: PipelineStep[]): Edge[] {
  const edges: Edge[] = [];
  for (let i = 0; i < steps.length; i++) {
    for (let j = i + 1; j < steps.length; j++) {
      const shared = steps[i].outputs.filter((o) =>
        steps[j].inputs.includes(o),
      );
      if (shared.length > 0) {
        edges.push({
          id: `pe-${steps[i].step_id}-${steps[j].step_id}`,
          source: `step-${steps[i].step_id}`,
          target: `step-${steps[j].step_id}`,
          type: "hover",
          data: { label: shared.join(", ") },
          style: { stroke: "#a5b4fc", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#a5b4fc" },
        });
      }
    }
  }
  return edges;
}

// ---------------------------------------------------------------------------
// Ancestor/descendant closure
// ---------------------------------------------------------------------------

function getRelated(nodeId: string, edges: Edge[]): Set<string> {
  const related = new Set<string>([nodeId]);
  const visitUp = (id: string) => {
    edges.forEach((e) => {
      if (e.target === id && !related.has(e.source)) {
        related.add(e.source);
        visitUp(e.source);
      }
    });
  };
  const visitDown = (id: string) => {
    edges.forEach((e) => {
      if (e.source === id && !related.has(e.target)) {
        related.add(e.target);
        visitDown(e.target);
      }
    });
  };
  visitUp(nodeId);
  visitDown(nodeId);
  return related;
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------

const LEGEND_BOX_STYLE: React.CSSProperties = {
  background: "rgba(245,245,245,0.92)",
  backdropFilter: "blur(6px)",
  borderRadius: 8,
  border: "1px solid rgba(0,0,0,0.1)",
  padding: "8px 12px",
  display: "flex",
  flexDirection: "column",
  gap: 5,
};

function Legend(): React.ReactElement {
  return (
    <div style={LEGEND_BOX_STYLE}>
      {(Object.keys(STATUS_STYLE) as LineageNode["status"][]).map((s) => (
        <div key={s} style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div
            style={{
              width: 20,
              height: 14,
              borderRadius: 3,
              background: "#e8e8e8",
              borderWidth: "1.5px",
              borderStyle: "solid",
              borderColor: STATUS_STYLE[s].border,
              borderBottomWidth: "3px",
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: 11, color: "#444", fontWeight: 500 }}>
            {STATUS_LABEL[s]}
          </span>
        </div>
      ))}
      {/* Human-verified indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <div
          style={{
            width: 20,
            height: 14,
            borderRadius: 3,
            background: "#f0fdfa",
            borderWidth: "1.5px",
            borderStyle: "solid",
            borderColor: "#0d9488",
            borderBottomWidth: "3px",
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: 11, color: "#444", fontWeight: 500 }}>Human verified</span>
      </div>
    </div>
  );
}

const SECTION_LABEL_STYLE: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  color: "#94a3b8",
  letterSpacing: "0.07em",
  textTransform: "uppercase",
  marginBottom: 4,
  marginTop: 2,
};

const FILE_STATUS_ENTRIES: { color: string; label: string }[] = [
  { color: "#22c55e", label: "All migrated" },
  { color: "#f59e0b", label: "Needs review" },
  { color: "#ef4444", label: "Has failures" },
];

const EDGE_ENTRIES: { reason: string; color: string; dash?: string }[] = [
  ...Object.entries(REASON_COLORS).map(([reason, color]) => ({
    reason,
    color,
    dash: REASON_DASH[reason],
  })),
];

function FilesLegend(): React.ReactElement {
  return (
    <div style={LEGEND_BOX_STYLE}>
      {/* Files section */}
      <div style={SECTION_LABEL_STYLE}>Files</div>
      {FILE_STATUS_ENTRIES.map(({ color, label }) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div
            style={{
              width: 20,
              height: 14,
              borderRadius: 3,
              background: "#e8e8e8",
              borderTop: "1.5px solid transparent",
              borderLeft: "1.5px solid transparent",
              borderRight: "1.5px solid transparent",
              borderBottom: `3px solid ${color}`,
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: 11, color: "#444", fontWeight: 500 }}>
            {label}
          </span>
        </div>
      ))}

      {/* Divider */}
      <div style={{ height: 1, background: "rgba(0,0,0,0.08)", margin: "5px 0" }} />

      {/* Connections section */}
      <div style={SECTION_LABEL_STYLE}>Connections</div>
      {EDGE_ENTRIES.map(({ reason, color, dash }) => (
        <div key={reason} style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <svg width={20} height={10} style={{ flexShrink: 0 }}>
            <line
              x1={0} y1={5} x2={20} y2={5}
              stroke={color}
              strokeWidth={2}
              strokeDasharray={dash}
            />
          </svg>
          <span style={{ fontSize: 11, color: "#444", fontWeight: 500 }}>
            {reason.replace(/_/g, " ")}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner graph
// ---------------------------------------------------------------------------

type ViewMode = "blocks" | "files" | "pipeline";

function LineageGraphInner({
  lineage,
  blockPlans = [],
  onFileNodeClick,
  onPipelineStepClick,
  trustFiles,
  trustBlocks,
  initialView,
  selectedFilePath,
  humanVerifiedBlocks,
}: LineageGraphProps): React.ReactElement {
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<NodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const hoveredIdRef = useRef<string | null>(null);
  const trackHoveredId = (id: string | null) => {
    hoveredIdRef.current = id;
  };

  const [view, setView] = useState<ViewMode>(initialView ?? "blocks");
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);

  // Undo/redo history — store {id → position} maps only
  type PosSnapshot = Record<string, { x: number; y: number }>;
  const historyRef = useRef<PosSnapshot[]>([]);
  const historyIdxRef = useRef<number>(-1);
  const [historyState, setHistoryState] = useState<{
    idx: number;
    len: number;
  }>({ idx: -1, len: 0 });

  // Initial layout ref for reset
  const initialLayoutRef = useRef<Node<NodeData>[]>([]);

  // Mirror of current nodes
  const nodesRef = useRef<Node<NodeData>[]>([]);
  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  // Hover debounce timer
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Suppress ReactFlow change events during programmatic position restores
  const suppressChangesRef = useRef(false);

  useEffect(() => {
    let newNodes: Node[];
    let newEdges: Edge[];

    if (view === "files" && lineage.file_nodes?.length) {
      const fEdges = buildFileEdges(lineage.file_edges ?? []);
      newNodes = applyDagreLayout(
        buildFileNodes(
          lineage.file_nodes,
          lineage.file_edges ?? [],
          selectedFilePath ?? selectedFile?.filename ?? null,
          trustFiles,
        ),
        fEdges,
        NODE_FILE_W,
        NODE_FILE_H,
        { ranksep: 160, nodesep: 75 },
      );
      newEdges = fEdges;
    } else if (view === "pipeline" && lineage.pipeline_steps?.length) {
      const pEdges = buildPipelineEdges(lineage.pipeline_steps);
      newNodes = applyDagreLayout(
        buildPipelineNodes(lineage.pipeline_steps),
        pEdges,
        NODE_PIPELINE_W,
        NODE_PIPELINE_H,
        { ranksep: 145, nodesep: 65 },
      );
      newEdges = pEdges;
    } else {
      // blocks view (default)
      if (lineage.nodes.length === 0) return;
      // Lineage node IDs use "::" separator; BlockPlan.block_id uses ":"
      const bpMap = blockPlans.length
        ? new Map(blockPlans.map((bp) => [bp.block_id.replace(":", "::"), bp]))
        : undefined;
      const rawNodes = buildInitialNodes(lineage.nodes, bpMap, trustBlocks, humanVerifiedBlocks);
      const rawEdges = buildInitialEdges(lineage.edges, lineage.column_flows);
      newNodes = applyDagreLayout(rawNodes, rawEdges, NODE_W, NODE_H);
      newEdges = rawEdges;
    }

    suppressChangesRef.current = true;
    setNodes(newNodes);
    setEdges(newEdges);
    initialLayoutRef.current = newNodes as Node<NodeData>[];
    historyRef.current = [
      Object.fromEntries(
        newNodes.map((n) => [n.id, { x: n.position.x, y: n.position.y }]),
      ),
    ];
    historyIdxRef.current = 0;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional
    setHistoryState({ idx: 0, len: 1 });
    setSelectedFile(null);
    setTimeout(() => {
      suppressChangesRef.current = false;
    }, 50);
  }, [lineage, view, selectedFilePath, humanVerifiedBlocks]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      if (suppressChangesRef.current) return;
      onNodesChange(changes);
    },
    [onNodesChange],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => onEdgesChange(changes),
    [onEdgesChange],
  );

  const handleNodeMouseEnter = useCallback(
    (_: React.MouseEvent, node: Node<NodeData>) => {
      if (leaveTimerRef.current !== null) {
        clearTimeout(leaveTimerRef.current);
        leaveTimerRef.current = null;
      }
      const related = getRelated(node.id, edges);
      trackHoveredId(node.id);
      setNodes((prev) =>
        prev.map((n) => ({
          ...n,
          style: { ...n.style, opacity: related.has(n.id) ? 1 : 0.2 },
        })),
      );
      setEdges((prev) =>
        prev.map((e) => ({
          ...e,
          style: {
            ...e.style,
            opacity: related.has(e.source) && related.has(e.target) ? 1 : 0.08,
          },
        })),
      );
    },
    [edges, setNodes, setEdges],
  );

  const handleNodeMouseLeave = useCallback(() => {
    if (leaveTimerRef.current !== null) clearTimeout(leaveTimerRef.current);
    leaveTimerRef.current = setTimeout(() => {
      trackHoveredId(null);
      setNodes((prev) =>
        prev.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } })),
      );
      setEdges((prev) =>
        prev.map((e) => ({ ...e, style: { ...e.style, opacity: 1 } })),
      );
      leaveTimerRef.current = null;
    }, 80);
  }, [setNodes, setEdges]);

  const handlePaneClick = useCallback(() => {
    if (leaveTimerRef.current !== null) {
      clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
    trackHoveredId(null);
    setNodes((prev) =>
      prev.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } })),
    );
    setEdges((prev) =>
      prev.map((e) => ({ ...e, style: { ...e.style, opacity: 1 } })),
    );
  }, [setNodes, setEdges]);

  const handleNodeDragStop = useCallback(() => {
    const all = nodesRef.current;
    const posSnapshot: PosSnapshot = Object.fromEntries(
      all.map((n) => [n.id, { x: n.position.x, y: n.position.y }]),
    );
    const sliced = historyRef.current.slice(0, historyIdxRef.current + 1);
    const next = [...sliced, posSnapshot].slice(-50);
    historyRef.current = next;
    historyIdxRef.current = next.length - 1;
    setHistoryState({ idx: next.length - 1, len: next.length });
  }, []);

  const handleUndo = useCallback(() => {
    if (historyIdxRef.current <= 0) return;
    historyIdxRef.current -= 1;
    const snap = historyRef.current[historyIdxRef.current];
    trackHoveredId(null);
    suppressChangesRef.current = true;
    setNodes((prev) =>
      prev.map((n) => {
        const p = snap[n.id];
        if (!p) return { ...n, style: { ...n.style, opacity: 1 } };
        return {
          ...n,
          position: { x: p.x, y: p.y },
          positionAbsolute: { x: p.x, y: p.y },
          dragging: false,
          style: { ...n.style, opacity: 1 },
        };
      }),
    );
    requestAnimationFrame(() => {
      suppressChangesRef.current = false;
    });
    setHistoryState({
      idx: historyIdxRef.current,
      len: historyRef.current.length,
    });
  }, [setNodes]);

  const handleRedo = useCallback(() => {
    if (historyIdxRef.current >= historyRef.current.length - 1) return;
    historyIdxRef.current += 1;
    const snap = historyRef.current[historyIdxRef.current];
    trackHoveredId(null);
    suppressChangesRef.current = true;
    setNodes((prev) =>
      prev.map((n) => {
        const p = snap[n.id];
        if (!p) return { ...n, style: { ...n.style, opacity: 1 } };
        return {
          ...n,
          position: { x: p.x, y: p.y },
          positionAbsolute: { x: p.x, y: p.y },
          dragging: false,
          style: { ...n.style, opacity: 1 },
        };
      }),
    );
    requestAnimationFrame(() => {
      suppressChangesRef.current = false;
    });
    setHistoryState({
      idx: historyIdxRef.current,
      len: historyRef.current.length,
    });
  }, [setNodes]);

  const handleReset = useCallback(() => {
    const initial = initialLayoutRef.current;
    trackHoveredId(null);
    suppressChangesRef.current = true;
    setNodes(
      initial.map((n) => ({
        ...n,
        position: { x: n.position.x, y: n.position.y },
        positionAbsolute: { x: n.position.x, y: n.position.y },
        dragging: false,
        style: { ...n.style, opacity: 1 },
      })),
    );
    requestAnimationFrame(() => {
      suppressChangesRef.current = false;
    });
    historyRef.current = [
      Object.fromEntries(
        initial.map((n) => [n.id, { x: n.position.x, y: n.position.y }]),
      ),
    ];
    historyIdxRef.current = 0;
    setHistoryState({ idx: 0, len: 1 });
    requestAnimationFrame(() => fitView({ padding: 0.2, duration: 300 }));
  }, [setNodes, fitView]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (view === "pipeline") {
        const step = lineage.pipeline_steps?.find(
          (s) => `step-${s.step_id}` === node.id,
        ) ?? null;
        if (step && onPipelineStepClick) {
          onPipelineStepClick(step);
        }
        return;
      }
      if (view !== "files") return;
      const fileNode =
        lineage.file_nodes?.find((fn) => `file-${fn.filename}` === node.id) ?? null;

      if (onFileNodeClick && fileNode) {
        // External handler provided — fire callback only, don't open internal panel
        onFileNodeClick(fileNode);
        setNodes((prev) =>
          prev.map((n) => ({
            ...n,
            data: { ...n.data, isSelected: n.id === node.id },
          })),
        );
      } else {
        // No external handler — use internal panel as before
        setSelectedFile(fileNode);
        setNodes((prev) =>
          prev.map((n) => ({
            ...n,
            data: { ...n.data, isSelected: n.id === node.id },
          })),
        );
      }
    },
    [view, lineage.pipeline_steps, lineage.file_nodes, setNodes, onFileNodeClick, onPipelineStepClick],
  );

  if (lineage.nodes.length === 0 && view === "blocks") {
    return (
      <div className="flex items-center justify-center h-150 text-sm text-muted-foreground">
        No lineage data available
      </div>
    );
  }

  const btnBase: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 500,
    color: "#475569",
    background: "transparent",
    border: "1px solid #e2e8f0",
    borderRadius: 5,
    padding: "3px 9px",
    cursor: "pointer",
  };
  const btnDisabled: React.CSSProperties = {
    opacity: 0.4,
    cursor: "not-allowed",
  };

  return (
    <div
      className="rounded-md border border-border overflow-hidden w-full h-full relative"
    >
      {/* Toolbar */}
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 10,
          zIndex: 10,
          background: "rgba(255,255,255,0.85)",
          backdropFilter: "blur(6px)",
          borderRadius: 8,
          border: "1px solid #e2e8f0",
          padding: "4px 6px",
          display: "flex",
          gap: 4,
          alignItems: "center",
        }}
      >
        <button
          style={
            historyState.idx <= 0 ? { ...btnBase, ...btnDisabled } : btnBase
          }
          disabled={historyState.idx <= 0}
          onClick={handleUndo}
          title="Undo"
        >
          ↩ Undo
        </button>
        <button
          style={
            historyState.idx >= historyState.len - 1
              ? { ...btnBase, ...btnDisabled }
              : btnBase
          }
          disabled={historyState.idx >= historyState.len - 1}
          onClick={handleRedo}
          title="Redo"
        >
          ↪ Redo
        </button>
        <button
          style={{
            ...btnBase,
            background: "rgba(255,255,255,0.18)",
            borderColor: "#94a3b8",
            color: "#1e293b",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}
          onClick={handleReset}
          title="Reset layout"
        >
          <RotateCcw size={12} /> Reset
        </button>

        {/* Divider */}
        <div
          style={{
            width: 1,
            height: 20,
            background: "#e2e8f0",
            margin: "0 6px",
          }}
        />

        {(["pipeline", "files", "blocks"] as ViewMode[]).map((v) => {
          const disabled =
            (v === "files" && !lineage.file_nodes?.length) ||
            (v === "pipeline" && !lineage.pipeline_steps?.length);
          const label = v.charAt(0).toUpperCase() + v.slice(1);
          return (
            <button
              key={v}
              onClick={() => setView(v)}
              disabled={disabled}
              style={{
                ...btnBase,
                ...(view === v
                  ? {
                      background: "#1e293b",
                      color: "#fff",
                      borderColor: "#1e293b",
                    }
                  : {}),
                ...(disabled ? btnDisabled : {}),
                fontSize: 11,
                padding: "2px 8px",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Empty state overlays */}
      {view === "files" && !lineage.file_nodes?.length && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm">
          No file-level lineage data available
        </div>
      )}
      {view === "pipeline" && !lineage.pipeline_steps?.length && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm">
          No pipeline step data available
        </div>
      )}

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        onNodeDragStop={handleNodeDragStop}
        onPaneClick={handlePaneClick}
        onNodeClick={handleNodeClick}
        nodesDraggable={true}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <Controls />
        <Background />
        {nodes.length > 15 && <MiniMap />}
      </ReactFlow>
      {/* Sticky legend — bottom-left of canvas */}
      {view === "blocks" && (
        <div style={{ position: "absolute", bottom: 12, left: 12, zIndex: 10 }}>
          <Legend />
        </div>
      )}
      {view === "files" && (
        <div style={{ position: "absolute", bottom: 12, left: 12, zIndex: 10 }}>
          <FilesLegend />
        </div>
      )}
      {view === "pipeline" && (
        <div style={{ position: "absolute", bottom: 12, left: 12, zIndex: 10 }}>
          <div style={LEGEND_BOX_STYLE}>
            <div style={SECTION_LABEL_STYLE}>Pipeline steps</div>
            {[
              { color: "#bfdbfe", border: "#93c5fd", label: "Source data" },
              { color: "#e0e7ff", border: "#c7d2fe", label: "Processing step" },
              { color: "#d1fae5", border: "#6ee7b7", label: "Output data" },
            ].map(({ color, border, label }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <div
                  style={{
                    width: 20,
                    height: 14,
                    borderRadius: 3,
                    background: color,
                    borderWidth: "1.5px",
                    borderStyle: "solid",
                    borderColor: border,
                    borderBottomWidth: "3px",
                    flexShrink: 0,
                  }}
                />
                <span style={{ fontSize: 11, color: "#444", fontWeight: 500 }}>{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <LineageDetailPanel
        file={selectedFile}
        blockStatuses={lineage.block_status ?? []}
        logLinks={lineage.log_links ?? []}
        blockPlans={blockPlans}
        onClose={() => {
          setSelectedFile(null);
          setNodes((prev) =>
            prev.map((n) => ({ ...n, data: { ...n.data, isSelected: false } })),
          );
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export default function LineageGraph({
  lineage,
  blockPlans,
  onFileNodeClick,
  onPipelineStepClick,
  trustFiles,
  trustBlocks,
  initialView,
  selectedFilePath,
  humanVerifiedBlocks,
}: LineageGraphProps): React.ReactElement {
  return (
    <ReactFlowProvider>
      <LineageGraphInner
        lineage={lineage}
        blockPlans={blockPlans}
        onFileNodeClick={onFileNodeClick}
        onPipelineStepClick={onPipelineStepClick}
        trustFiles={trustFiles}
        trustBlocks={trustBlocks}
        initialView={initialView}
        selectedFilePath={selectedFilePath}
        humanVerifiedBlocks={humanVerifiedBlocks}
      />
    </ReactFlowProvider>
  );
}
