import type {
  BlockPlan,
  FileNode,
  JobLineageResponse,
  PipelineStep,
  TrustReportBlock,
  TrustReportFile,
} from "@/api/types";
import { FileNodeCard, type FileNodeData } from "@/components/JobDetail/FileNodeCard";
import {
  buildPyFileToSasFilesMap,
  buildSasFileToPyFilesMap,
  pyFileToSasFiles,
  pyFileToStepTitle,
  sasFileToPyFile,
} from "@/lib/sas-python-file-map";
import { deriveTargetPipelineSteps } from "@/lib/target-steps";
import dagre from "dagre";
import { ChevronRight, RotateCcw } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  getBezierPath,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  type XYPosition,
} from "reactflow";
import "reactflow/dist/style.css";
import { getBlockStatus, STATUS_CONFIG } from "./blockStatusHelpers";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TargetGraphProps {
  lineage: JobLineageResponse;
  generatedFiles: Record<string, string>; // keys are authoritative node list
  blockPlans: BlockPlan[];
  trustFiles?: TrustReportFile[];
  trustBlocks?: Record<string, TrustReportBlock>;
  view?: "pipeline" | "files" | "blocks";
  onViewChange?: (v: "pipeline" | "files" | "blocks") => void;
  onFileClick: (sasSourceFiles: string[]) => void;
  onModuleClick?: (pyFile: string) => void;
  onBlockClick?: (blockId: string) => void;
  onBlocksFileClick?: (pyFile: string) => void;
  onPipelineStepClick?: (step: PipelineStep) => void;
  selectedBlockId?: string | null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NODE_FILE_W = 220;
const NODE_FILE_H = 96;
const NODE_STEP_W = 220;
const ISOLATED_SPACING = 240; // horizontal step between isolated nodes
const ISOLATED_GAP = 60;      // vertical gap between connected cluster and isolated row

// ---------------------------------------------------------------------------
// Status aggregation
// ---------------------------------------------------------------------------

function aggregateStatus(
  pyFile: string,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
  pyToSasMap: Map<string, string[]>,
): FileNode["status"] {
  if (!trustFiles) return null;
  const sasFiles = pyToSasMap.get(pyFile) ?? pyFileToSasFiles(pyFile, blockPlans);
  if (sasFiles.length === 0) return null;
  const entries = sasFiles
    .map((sf) => trustFiles.find((tf) => tf.source_file === sf))
    .filter((tf): tf is TrustReportFile => tf !== undefined);
  if (entries.length === 0) return null;
  if (entries.some((tf) => tf.failed_reconciliation > 0)) return "UNRECOGNIZED";
  if (entries.some((tf) => tf.needs_review > 0 || tf.manual_todo > 0)) return "ERROR_PRONE";
  return "OK";
}

// ---------------------------------------------------------------------------
// Dagre layout helpers
// ---------------------------------------------------------------------------

interface DagreOptions {
  rankdir?: "LR" | "TB";
  ranksep?: number;
  nodesep?: number;
}

function applyDagreLayout<T extends object>(
  nodes: Node<T>[],
  edges: Edge[],
  nodeW: number,
  nodeH: number | ((nodeId: string) => number),
  opts?: DagreOptions,
): Node<T>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: opts?.rankdir ?? "LR",
    nodesep: opts?.nodesep ?? 50,
    ranksep: opts?.ranksep ?? 90,
    marginx: 20,
    marginy: 20,
  });
  nodes.forEach((n) => {
    const h = typeof nodeH === "function" ? nodeH(n.id) : nodeH;
    g.setNode(n.id, { width: nodeW, height: h });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    const h = typeof nodeH === "function" ? nodeH(n.id) : nodeH;
    const isVertical = (opts?.rankdir ?? "LR") === "TB";
    return {
      ...n,
      position: { x: pos.x - nodeW / 2, y: pos.y - h / 2 },
      sourcePosition: isVertical ? Position.Bottom : Position.Right,
      targetPosition: isVertical ? Position.Top : Position.Left,
    };
  });
}

// ---------------------------------------------------------------------------
// HoverLabelEdge
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

// ---------------------------------------------------------------------------
// SectionLabelNode — CRITICAL: module-level, never inside a component
// ---------------------------------------------------------------------------

function SectionLabelNode(): React.ReactElement {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        pointerEvents: "none",
        userSelect: "none",
        width: "100%",
      }}
    >
      <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
      <span
        style={{
          fontSize: 10,
          color: "#94a3b8",
          whiteSpace: "nowrap",
          fontWeight: 500,
        }}
      >
        No data dependencies detected
      </span>
      <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// PipelineStepNode — Steps view, module-level
// ---------------------------------------------------------------------------

const STATUS_COLOR_MAP: Record<NonNullable<FileNode["status"]>, string> = {
  OK: "#137a52",
  UNRECOGNIZED: "#b3261e",
  ERROR_PRONE: "#b5680d",
};

interface PipelineStepNodeData {
  filename: string;
  status: FileNode["status"];
  blockCount: number;
  inCount: number;  // number of incoming edges (deps)
  outCount: number; // number of outgoing edges
  hasIncoming?: boolean;
  hasOutgoing?: boolean;
}

function PipelineStepNode({ data }: NodeProps<PipelineStepNodeData>): React.ReactElement {
  const accentColor = data.status ? STATUS_COLOR_MAP[data.status] : "#94a3b8";

  const statusIcon =
    data.status === "OK" ? "✓"
      : data.status === "ERROR_PRONE" ? "⚠"
        : data.status === "UNRECOGNIZED" ? "✗"
          : null;

  const statusLabel =
    data.status === "OK" ? "pass"
      : data.status === "ERROR_PRONE" ? "review"
        : data.status === "UNRECOGNIZED" ? "failures"
          : null;

  return (
    <>
      {(data.hasIncoming ?? true) && (
        <Handle
          type="target"
          position={Position.Top}
          style={{
            background: accentColor,
            width: 8,
            height: 8,
            border: "2px solid #fff",
          }}
        />
      )}
      <div
        style={{
          width: NODE_STEP_W,
          background: "#fff",
          borderRadius: 10,
          border: "1px solid #e2e8f0",
          borderLeft: `4px solid ${accentColor}`,
          boxShadow: "0 1px 5px rgba(0,0,0,0.09)",
          overflow: "hidden",
          cursor: "pointer",
        }}
      >
        <div style={{ padding: "8px 10px 9px" }}>
          {/* Row 1: filename + status icon */}
          <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: "#0f172a",
                lineHeight: 1.35,
                flex: 1,
                minWidth: 0,
                overflowWrap: "break-word",
                wordBreak: "break-all",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {data.filename}
            </span>
          </div>

          {/* Row 2: .py badge + status label */}
          <div style={{ marginTop: 5, display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 3,
                background: "#f0fdf4",
                color: "#15803d",
                fontSize: 9.5,
                fontWeight: 700,
                fontFamily: "ui-monospace, monospace",
                padding: "2px 6px",
                borderRadius: 4,
                letterSpacing: "0.03em",
              }}
            >
              .py
            </span>
            {statusIcon && statusLabel && (
              <span
                style={{
                  fontSize: 10,
                  color: accentColor,
                  fontWeight: 600,
                }}
              >
                {statusIcon} {statusLabel}
              </span>
            )}
          </div>

          {/* Row 3: block count + deps info */}
          <div
            style={{
              marginTop: 4,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: 10, color: "#94a3b8", fontFamily: "ui-monospace, monospace" }}>
              {data.blockCount} {data.blockCount === 1 ? "step" : "steps"}
            </span>
            <span style={{ fontSize: 10, color: "#64748b", fontFamily: "ui-monospace, monospace" }}>
              deps: {data.inCount}{"  →"} {data.outCount}
            </span>
          </div>
        </div>
      </div>
      {(data.hasOutgoing ?? true) && (
        <Handle
          type="source"
          position={Position.Bottom}
          style={{
            background: accentColor,
            width: 8,
            height: 8,
            border: "2px solid #fff",
          }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// PipelineTargetStepNode — Pipeline view, module-level
// ---------------------------------------------------------------------------

interface PipelineTargetStepData {
  stepNumber: number;       // 1-based index (Python file order)
  stepName: string;
  description: string;
  status: FileNode["status"];
  step: PipelineStep;       // synthetic step (one per .py file) for click handler / side panel
}

function PipelineTargetStepNode({ data }: NodeProps<PipelineTargetStepData>): React.ReactElement {
  const accentColor = data.status ? STATUS_COLOR_MAP[data.status] : "#94a3b8";

  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        style={{
          background: accentColor,
          width: 8,
          height: 8,
          border: "2px solid #fff",
        }}
      />
      <div
        style={{
          width: 260,
          background: "#fff",
          borderRadius: 10,
          border: "1px solid #e2e8f0",
          borderLeft: `4px solid ${accentColor}`,
          boxShadow: "0 1px 5px rgba(0,0,0,0.09)",
          overflow: "hidden",
          cursor: "pointer",
        }}
      >
        <div style={{ padding: "8px 10px 9px" }}>
          {/* Row 1: step number badge + step name */}
          <div style={{ display: "flex", alignItems: "flex-start", gap: 7 }}>
            <span
              style={{
                flexShrink: 0,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 20,
                height: 20,
                borderRadius: "50%",
                background: "#f1f5f9",
                color: "#64748b",
                fontSize: 10,
                fontWeight: 700,
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {data.stepNumber}
            </span>
            <span
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#0f172a",
                lineHeight: 1.35,
                flex: 1,
                minWidth: 0,
                overflowWrap: "break-word",
                wordBreak: "break-word",
              }}
            >
              {data.stepName}
            </span>
          </div>

          {/* Row 2: description (muted, max 2 lines) */}
          {data.description && (
            <div
              style={{
                marginTop: 5,
                fontSize: 10,
                color: "#94a3b8",
                overflow: "hidden",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                lineHeight: 1.4,
              }}
            >
              {data.description}
            </div>
          )}

          {/* Row 3: input/output dataset counts */}
          <div
            style={{
              marginTop: 5,
              display: "flex",
              gap: 8,
              fontSize: 10,
              color: "#94a3b8",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            <span>↑ {data.step.inputs.length} in</span>
            <span>↓ {data.step.outputs.length} out</span>
          </div>

          {/* View steps hint */}
          <div style={{
            marginTop: 5, display: "flex",
            alignItems: "center", gap: 3,
          }}>
            <ChevronRight size={11} style={{ color: "#94a3b8" }} />
            <span style={{ fontSize: 10, color: "#94a3b8", fontFamily: "ui-monospace, monospace" }}>
              View steps
            </span>
          </div>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: accentColor,
          width: 8,
          height: 8,
          border: "2px solid #fff",
        }}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// BlocksFileNode — Blocks view, module-level (compact card)
// ---------------------------------------------------------------------------

interface BlocksFileNodeData {
  filename: string;
  status: FileNode["status"];
  passCount: number;
  reviewCount: number;
  failCount: number;
  totalCount: number;
  hasIncoming?: boolean;
  hasOutgoing?: boolean;
}

const BLOCKS_COMPACT_H = 88;

function BlocksFileNode({ data }: NodeProps<BlocksFileNodeData>): React.ReactElement {
  const accentColor = data.status ? STATUS_COLOR_MAP[data.status] : "#94a3b8";
  const [hovered, setHovered] = useState(false);

  const total = data.totalCount || 1;
  const passW  = (data.passCount  / total) * 100;
  const reviewW = (data.reviewCount / total) * 100;
  const failW  = (data.failCount  / total) * 100;

  return (
    <>
      {(data.hasIncoming ?? true) && (
        <Handle type="target" position={Position.Left}
          style={{ background: accentColor, width: 8, height: 8, border: "2px solid #fff" }} />
      )}
      <div
        style={{
          width: NODE_FILE_W,
          background: hovered ? "#f8fafc" : "#fff",
          borderRadius: 10,
          border: "1px solid #e2e8f0",
          borderLeft: `4px solid ${accentColor}`,
          boxShadow: "0 1px 5px rgba(0,0,0,0.09)",
          overflow: "hidden",
          cursor: "pointer",
          transition: "background 0.12s ease",
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {/* Filename */}
        <div style={{ padding: "8px 10px 3px" }}>
          <span style={{
            fontSize: 12, fontWeight: 700, color: "#0f172a",
            fontFamily: "ui-monospace, monospace",
            display: "block", overflow: "hidden",
            textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {data.filename}
          </span>
        </div>
        {/* Block count */}
        <div style={{ padding: "0 10px 5px" }}>
          <span style={{ fontSize: 10, color: "#94a3b8", fontFamily: "ui-monospace, monospace" }}>
            {data.totalCount} {data.totalCount === 1 ? "step" : "steps"}
          </span>
        </div>
        {/* Segmented bar */}
        <div style={{
          margin: "0 10px 8px", height: 5, borderRadius: 3,
          background: "#f1f5f9", overflow: "hidden", display: "flex",
        }}>
          {passW  > 0 && <div style={{ width: `${passW}%`,  background: "#137a52", flexShrink: 0 }} />}
          {reviewW > 0 && <div style={{ width: `${reviewW}%`, background: "#b5680d", flexShrink: 0 }} />}
          {failW  > 0 && <div style={{ width: `${failW}%`,  background: "#b3261e", flexShrink: 0 }} />}
        </div>
        {/* View blocks hint */}
        <div style={{
          padding: "0 10px 8px", display: "flex",
          alignItems: "center", gap: 3,
        }}>
          <ChevronRight size={11} style={{ color: "#94a3b8" }} />
          <span style={{ fontSize: 10, color: "#94a3b8", fontFamily: "ui-monospace, monospace" }}>
            View blocks
          </span>
        </div>
      </div>
      {(data.hasOutgoing ?? true) && (
        <Handle type="source" position={Position.Right}
          style={{ background: accentColor, width: 8, height: 8, border: "2px solid #fff" }} />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// NODE_TYPES — module-level constant (CRITICAL: never inside a component)
// ---------------------------------------------------------------------------

const NODE_TYPES = {
  fileNode: FileNodeCard,
  sectionLabel: SectionLabelNode,
  pipelineStep: PipelineStepNode,
  pipelineTargetStep: PipelineTargetStepNode,
  blocksFile: BlocksFileNode,
};
const EDGE_TYPES = { hover: HoverLabelEdge };

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
  { color: "#137a52", label: "All migrated" },
  { color: "#b5680d", label: "Needs review" },
  { color: "#b3261e", label: "Has failures" },
];

function TargetLegend(): React.ReactElement {
  return (
    <div style={LEGEND_BOX_STYLE}>
      <div style={SECTION_LABEL_STYLE}>Status</div>
      {FILE_STATUS_ENTRIES.map(({ color, label }) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div
            style={{
              width: 18,
              height: 3,
              borderRadius: 2,
              background: color,
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: 11, color: "#444", fontWeight: 500 }}>
            {label}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared edge derivation
// ---------------------------------------------------------------------------

function buildRawEdges(
  lineage: JobLineageResponse,
  nodeSet: Set<string>,
  sasToPyMap: Map<string, string[]>,
): Edge[] {
  const rawEdges: Edge[] = [];
  const seenEdgeKeys = new Set<string>();

  for (const fe of lineage.file_edges ?? []) {
    const srcPyFiles = sasToPyMap.get(fe.source_file) ?? [sasFileToPyFile(fe.source_file)];
    const tgtPyFiles = sasToPyMap.get(fe.target_file) ?? [sasFileToPyFile(fe.target_file)];
    for (const src of srcPyFiles) {
      for (const tgt of tgtPyFiles) {
        if (src === "pipeline.py" || tgt === "pipeline.py") continue;
        if (!nodeSet.has(src) || !nodeSet.has(tgt)) continue;
        if (src === tgt) continue;
        const key = `${src}||${tgt}`;
        if (seenEdgeKeys.has(key)) continue;
        seenEdgeKeys.add(key);
        rawEdges.push({
          id: `te-${src}-${tgt}`,
          source: src,
          target: tgt,
          type: "hover",
          data: { label: fe.reason.toLowerCase().replace(/_/g, " ") },
          style: { stroke: "#3b82f6", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#3b82f6" },
        });
      }
    }
  }
  return rawEdges;
}

// ---------------------------------------------------------------------------
// Graph builders per view
// ---------------------------------------------------------------------------

function buildModulesGraph(
  pyFiles: string[],
  lineage: JobLineageResponse,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
  pyToSasMap: Map<string, string[]>,
  sasToPyMap: Map<string, string[]>,
  rankdir: "LR" | "TB" = "LR",
): { layoutNodes: Node[]; edges: Edge[] } {
  const nodeSet = new Set(pyFiles);
  const rawEdges = buildRawEdges(lineage, nodeSet, sasToPyMap);

  const incomingIds = new Set(rawEdges.map((e) => e.target));
  const outgoingIds = new Set(rawEdges.map((e) => e.source));

  const connectionCount = new Map<string, number>();
  for (const e of rawEdges) {
    connectionCount.set(e.source, (connectionCount.get(e.source) ?? 0) + 1);
    connectionCount.set(e.target, (connectionCount.get(e.target) ?? 0) + 1);
  }

  const rawNodes: Node<FileNodeData>[] = pyFiles.map((pyFile) => {
    const sasFiles = pyToSasMap.get(pyFile) ?? pyFileToSasFiles(pyFile, blockPlans);
    const blockCount = blockPlans.filter((bp) => sasFiles.includes(bp.source_file)).length;
    return {
      id: pyFile,
      type: "fileNode",
      position: { x: 0, y: 0 },
      data: {
        filename: pyFile,
        fullPath: pyFile,
        file_type: "MODULE",
        status: aggregateStatus(pyFile, blockPlans, trustFiles, pyToSasMap),
        blockCount,
        connectionCount: connectionCount.get(pyFile) ?? 0,
        isSelected: false,
        hasIncoming: incomingIds.has(pyFile),
        hasOutgoing: outgoingIds.has(pyFile),
      },
    };
  });

  const connectedIds = new Set<string>();
  for (const e of rawEdges) {
    connectedIds.add(e.source);
    connectedIds.add(e.target);
  }
  const connectedNodes = rawNodes.filter((n) => connectedIds.has(n.id));
  const isolatedNodes = rawNodes.filter((n) => !connectedIds.has(n.id));

  const laidConnected: Node<FileNodeData>[] =
    connectedNodes.length > 0
      ? applyDagreLayout(connectedNodes, rawEdges, NODE_FILE_W, NODE_FILE_H, {
          rankdir,
          ranksep: 160,
          nodesep: 75,
        })
      : [];

  const connectedLeft =
    laidConnected.length > 0
      ? Math.min(...laidConnected.map((n) => n.position.x))
      : 0;
  const connectedBottom =
    laidConnected.length > 0
      ? Math.max(...laidConnected.map((n) => n.position.y + NODE_FILE_H))
      : 0;

  const isolatedTopY = connectedBottom + ISOLATED_GAP + (laidConnected.length > 0 ? 12 : 0);
  const positionedIsolated: Node<FileNodeData>[] = isolatedNodes.map((n, i) => ({
    ...n,
    position: {
      x: connectedLeft + i * ISOLATED_SPACING,
      y: isolatedTopY,
    },
  }));

  const allLayoutNodes: Node[] = [...laidConnected, ...positionedIsolated];

  if (isolatedNodes.length > 0) {
    const connectedRight =
      laidConnected.length > 0
        ? Math.max(...laidConnected.map((n) => n.position.x + NODE_FILE_W))
        : connectedLeft + NODE_FILE_W;
    const isolatedRight = connectedLeft + isolatedNodes.length * ISOLATED_SPACING;
    const labelW = Math.max(connectedRight, isolatedRight) - connectedLeft;

    allLayoutNodes.push({
      id: "__section-label__",
      type: "sectionLabel",
      position: {
        x: connectedLeft,
        y: connectedBottom + ISOLATED_GAP / 2 - 12,
      },
      data: {},
      selectable: false,
      draggable: false,
      style: { width: labelW, background: "transparent", border: "none", padding: 0 },
    } as Node);
  }

  return { layoutNodes: allLayoutNodes, edges: rawEdges };
}

// Step-to-step edges via dataset-name matching between each step's derived
// inputs/outputs — the same method Source's Pipeline view uses (buildPipelineEdges
// in LineageGraph.tsx), which works regardless of file boundaries (unlike a
// file_edges projection, which produces zero edges whenever every step lives in
// a single SAS/generated-Python file — the common case this fix targets).
function buildStepDatasetEdges(
  steps: { step_id: string; inputs: string[]; outputs: string[] }[],
): Edge[] {
  const edges: Edge[] = [];
  for (let i = 0; i < steps.length; i++) {
    for (let j = 0; j < steps.length; j++) {
      if (i === j) continue;
      const shared = steps[i].outputs.filter((o) => steps[j].inputs.includes(o));
      if (shared.length > 0) {
        edges.push({
          id: `pse-${steps[i].step_id}-${steps[j].step_id}`,
          source: steps[i].step_id,
          target: steps[j].step_id,
          type: "hover",
          data: { label: shared.join(", ").toLowerCase() },
          style: { stroke: "#3b82f6", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#3b82f6" },
        });
      }
    }
  }
  return edges;
}

// Same aggregation as aggregateStatus, but keyed directly off a set of SAS
// source files instead of derived from a single generated Python file.
function aggregateStatusForFiles(
  sasFiles: string[],
  trustFiles: TrustReportFile[] | undefined,
): FileNode["status"] {
  if (!trustFiles || sasFiles.length === 0) return null;
  const entries = sasFiles
    .map((sf) => trustFiles.find((tf) => tf.source_file === sf))
    .filter((tf): tf is TrustReportFile => tf !== undefined);
  if (entries.length === 0) return null;
  if (entries.some((tf) => tf.failed_reconciliation > 0)) return "UNRECOGNIZED";
  if (entries.some((tf) => tf.needs_review > 0 || tf.manual_todo > 0)) return "ERROR_PRONE";
  return "OK";
}

function buildPipelineStepsGraph(
  lineage: JobLineageResponse,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
  sasToPyMap: Map<string, string[]>,
): { layoutNodes: Node[]; edges: Edge[] } {
  const steps = lineage.pipeline_steps ?? [];

  const NODE_W = 260;
  const NODE_H = 158; // +18 vs. base 140 to fit the "View steps" hint row (same treatment as BLOCKS_COMPACT_H's 72->88 bump)

  // Synthetic (Python-oriented) steps — name/description/files re-derived from
  // Python filenames + block rationale, while step_id/blocks/inputs/outputs
  // mirror the real step. Shared with ETLTab.tsx so the pipeline graph and the
  // PipelineStepPanel side panel always agree on step identity and dataset flow.
  const syntheticSteps = deriveTargetPipelineSteps(steps, blockPlans, sasToPyMap);

  // Edges via dataset-name matching on the synthesized inputs/outputs — this
  // correctly finds transitions even when every step lives in a single
  // generated Python file (see buildStepDatasetEdges for why file-level edges
  // can't represent that case).
  const edges = buildStepDatasetEdges(syntheticSteps);

  const rawNodes: Node<PipelineTargetStepData>[] = syntheticSteps.map((syntheticStep, i) => ({
    id: syntheticStep.step_id,
    type: "pipelineTargetStep",
    position: { x: 0, y: 0 },
    width: NODE_W,
    height: NODE_H,
    data: {
      stepNumber: i + 1,
      stepName: syntheticStep.name,
      description: syntheticStep.description,
      status: aggregateStatusForFiles(steps[i].files, trustFiles),
      step: syntheticStep,
    },
  }));

  const layoutNodes = applyDagreLayout(rawNodes, edges, NODE_W, NODE_H, {
    rankdir: "LR",
    ranksep: 80,
    nodesep: 40,
  });

  return { layoutNodes, edges };
}

// Groups by pipeline step (not by generated Python file) for the same reason
// buildPipelineStepsGraph does — a step's blocks may all compile into one
// file, which would otherwise collapse this view to a single node.
function buildBlocksGraph(
  lineage: JobLineageResponse,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
  trustBlocks: Record<string, TrustReportBlock> | undefined,
  sasToPyMap: Map<string, string[]>,
): { layoutNodes: Node[]; edges: Edge[] } {
  const steps = lineage.pipeline_steps ?? [];

  // Same per-step derivation as buildPipelineStepsGraph, kept local (rather
  // than shared) since the two views' node shapes differ enough that a
  // shared helper would need its own indirection to stay readable.
  const synthesized = steps.map((step, i) => {
    const stepBlocks = blockPlans.filter((bp) => step.blocks.includes(bp.block_id));
    const pyFilesForStep = [
      ...new Set(
        stepBlocks.flatMap(
          (bp) => sasToPyMap.get(bp.source_file) ?? [sasFileToPyFile(bp.source_file)],
        ),
      ),
    ].filter((f) => f !== "pipeline.py");
    const title =
      pyFilesForStep.length > 0
        ? pyFilesForStep.map(pyFileToStepTitle).join(" / ")
        : `Step ${i + 1}`;
    return {
      stepId: step.step_id,
      title,
      blocks: stepBlocks,
      inputs: [...new Set(stepBlocks.flatMap((bp) => bp.input_datasets))],
      outputs: [...new Set(stepBlocks.flatMap((bp) => bp.output_datasets))],
      status: aggregateStatusForFiles(step.files, trustFiles),
    };
  });

  const rawEdges = buildStepDatasetEdges(
    synthesized.map((s) => ({ step_id: s.stepId, inputs: s.inputs, outputs: s.outputs })),
  );

  const incomingIds = new Set(rawEdges.map((e) => e.target));
  const outgoingIds = new Set(rawEdges.map((e) => e.source));

  const rawNodes: Node<BlocksFileNodeData>[] = synthesized.map((s) => {
    let passCount = 0;
    let reviewCount = 0;
    let failCount = 0;
    for (const bp of s.blocks) {
      const tb = trustBlocks?.[bp.block_id];
      const kind = getBlockStatus(bp, tb, false);
      const label = STATUS_CONFIG[kind].label;
      if (label === "Pass" || label === "Verified") {
        passCount++;
      } else if (label === "Manual" || label === "Failed") {
        failCount++;
      } else {
        reviewCount++;
      }
    }

    return {
      id: s.stepId,
      type: "blocksFile",
      position: { x: 0, y: 0 },
      data: {
        filename: s.title,
        status: s.status,
        passCount,
        reviewCount,
        failCount,
        totalCount: s.blocks.length,
        hasIncoming: incomingIds.has(s.stepId),
        hasOutgoing: outgoingIds.has(s.stepId),
      },
    };
  });

  const laidNodes = applyDagreLayout(
    rawNodes,
    rawEdges,
    NODE_FILE_W,
    BLOCKS_COMPACT_H,
    { ranksep: 160, nodesep: 75 },
  );

  return { layoutNodes: laidNodes, edges: rawEdges };
}

// ---------------------------------------------------------------------------
// Inner component
// ---------------------------------------------------------------------------

function TargetGraphInner({
  lineage,
  generatedFiles,
  blockPlans,
  trustFiles,
  trustBlocks,
  view = "files",
  onViewChange,
  onFileClick,
  onModuleClick,
  onBlocksFileClick,
  onPipelineStepClick,
}: TargetGraphProps): React.ReactElement {
  const { fitView } = useReactFlow();
  const pyFiles = Object.keys(generatedFiles).filter((f) => f !== "pipeline.py");
  const isEmpty = pyFiles.length === 0;

  // Build accurate Python↔SAS maps by parsing provenance comments in generated files.
  // This resolves the filename mismatch between sasFileToPyFile() and demo seed keys.
  const pyToSasMap = useMemo(
    () => buildPyFileToSasFilesMap(generatedFiles),
    [generatedFiles],
  );
  const sasToPyMap = useMemo(
    () => buildSasFileToPyFilesMap(generatedFiles),
    [generatedFiles],
  );

  // Build the correct graph based on view.
  // "pipeline" → top-to-bottom execution flow of Python modules (TB layout)
  // "files"    → module dependency graph, left-to-right (LR layout)
  // "blocks"   → Python modules with inline block rows
  const { layoutNodes: builtNodes, edges: builtEdges } = isEmpty
    ? { layoutNodes: [], edges: [] }
    : view === "pipeline"
      ? buildPipelineStepsGraph(lineage, blockPlans, trustFiles, sasToPyMap)
      : view === "blocks"
        ? buildBlocksGraph(lineage, blockPlans, trustFiles, trustBlocks, sasToPyMap)
        : buildModulesGraph(pyFiles, lineage, blockPlans, trustFiles, pyToSasMap, sasToPyMap, "LR");

  const [nodes, setNodes, onNodesChange] = useNodesState(builtNodes);
  const [edges, , onEdgesChange] = useEdgesState(builtEdges);


  // Undo/redo history
  const historyRef = useRef<{ positions: Record<string, XYPosition>[]; idx: number }>({
    positions: [{}],
    idx: 0,
  });
  const [historyState, setHistoryState] = useState<{ idx: number; len: number }>({
    idx: 0,
    len: 1,
  });

  const handleUndo = useCallback(() => {
    if (historyRef.current.idx <= 0) return;
    historyRef.current.idx--;
    const pos = historyRef.current.positions[historyRef.current.idx];
    setNodes((ns) => ns.map((n) => (pos[n.id] ? { ...n, position: pos[n.id] } : n)));
    setHistoryState({ idx: historyRef.current.idx, len: historyRef.current.positions.length });
  }, [setNodes]);

  const handleRedo = useCallback(() => {
    if (historyRef.current.idx >= historyRef.current.positions.length - 1) return;
    historyRef.current.idx++;
    const pos = historyRef.current.positions[historyRef.current.idx];
    setNodes((ns) => ns.map((n) => (pos[n.id] ? { ...n, position: pos[n.id] } : n)));
    setHistoryState({ idx: historyRef.current.idx, len: historyRef.current.positions.length });
  }, [setNodes]);

  const handleReset = useCallback(() => {
    fitView({ padding: 0.1, duration: 300 });
  }, [fitView]);

  const handleNodeDragStop = useCallback(
    (_: React.MouseEvent, _node: Node, allNodes: Node[]) => {
      const pos: Record<string, XYPosition> = {};
      allNodes.forEach((n) => {
        pos[n.id] = n.position;
      });
      const h = historyRef.current;
      h.positions = h.positions.slice(0, h.idx + 1);
      h.positions.push(pos);
      h.idx = h.positions.length - 1;
      setHistoryState({ idx: h.idx, len: h.positions.length });
    },
    [],
  );

  const handleNodeClick = (_: React.MouseEvent, node: Node) => {
    if (node.id === "__section-label__") return;

    if (node.type === "pipelineTargetStep" && onPipelineStepClick) {
      onPipelineStepClick((node.data as PipelineTargetStepData).step);
      return;
    }

    if (view === "blocks") {
      onBlocksFileClick?.(node.id);
      return;
    }

    if (view === "files") {
      if (onModuleClick) {
        onModuleClick(node.id);
      } else {
        const sasFiles = pyToSasMap.get(node.id) ?? pyFileToSasFiles(node.id, blockPlans);
        onFileClick(sasFiles);
      }
    }
  };

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
  const btnDisabled: React.CSSProperties = { opacity: 0.4, cursor: "not-allowed" };

  if (isEmpty) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        No Python modules generated for this job.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border overflow-hidden w-full h-full relative">
      {/* Floating toolbar — Undo / Redo / Reset | Steps / Modules / Blocks */}
      {onViewChange && (
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
            style={historyState.idx <= 0 ? { ...btnBase, ...btnDisabled } : btnBase}
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
          <div style={{ width: 1, height: 20, background: "#e2e8f0", margin: "0 6px" }} />

          {(["pipeline", "files", "blocks"] as const).map((v) => {
            const VIEW_LABELS: Record<"pipeline" | "files" | "blocks", string> = {
              pipeline: "Pipeline",
              files: "Files",
              blocks: "Steps",
            };
            return (
              <button
                key={v}
                onClick={() => onViewChange(v)}
                style={{
                  ...btnBase,
                  fontSize: 11,
                  padding: "2px 8px",
                  ...(view === v
                    ? { background: "#1e293b", color: "#fff", borderColor: "#1e293b" }
                    : {}),
                }}
              >
                {VIEW_LABELS[v]}
              </button>
            );
          })}
        </div>
      )}
      <>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          onNodeDragStop={handleNodeDragStop}
          nodesDraggable
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.12, maxZoom: 0.8 }}
        >
          <Controls />
          <Background />
        </ReactFlow>
        <div style={{ position: "absolute", bottom: 12, right: 12, zIndex: 10 }}>
          <TargetLegend />
        </div>
      </>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export default function TargetGraph(props: TargetGraphProps): React.ReactElement {
  return (
    <ReactFlowProvider>
      <TargetGraphInner {...props} />
    </ReactFlowProvider>
  );
}
