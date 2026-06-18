import type {
  BlockPlan,
  FileNode,
  JobLineageResponse,
  TrustReportBlock,
  TrustReportFile,
} from "@/api/types";
import { FileNodeCard, type FileNodeData } from "@/components/JobDetail/FileNodeCard";
import { pyFileToSasFiles, sasFileToPyFile } from "@/lib/sas-python-file-map";
import dagre from "dagre";
import { RotateCcw } from "lucide-react";
import { useCallback, useRef, useState } from "react";
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
  view?: "steps" | "modules" | "blocks";
  onViewChange?: (v: "steps" | "modules" | "blocks") => void;
  onFileClick: (sasSourceFiles: string[]) => void;
  onModuleClick?: (pyFile: string) => void;
  onBlockClick?: (blockId: string) => void;
  selectedBlockId?: string | null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NODE_FILE_W = 220;
const NODE_FILE_H = 96;
const NODE_STEP_W = 220;
const NODE_STEP_H = 96;
const BLOCKS_BASE_H = 80;
const BLOCK_ROW_H = 36;
const ISOLATED_SPACING = 240; // horizontal step between isolated nodes
const ISOLATED_GAP = 60;      // vertical gap between connected cluster and isolated row

// ---------------------------------------------------------------------------
// Status aggregation
// ---------------------------------------------------------------------------

function aggregateStatus(
  pyFile: string,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
): FileNode["status"] {
  if (!trustFiles) return null;
  const sasFiles = pyFileToSasFiles(pyFile, blockPlans);
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
  OK: "#22c55e",
  UNRECOGNIZED: "#ef4444",
  ERROR_PRONE: "#f59e0b",
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
              {data.blockCount} {data.blockCount === 1 ? "block" : "blocks"}
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
// BlocksFileNode — Blocks view, module-level
// ---------------------------------------------------------------------------

interface BlockRowEntry {
  blockId: string;
  blockType: string;
  startLine: number;
  statusLabel: string;
  statusClassName: string;
}

interface BlocksFileNodeData {
  filename: string;
  status: FileNode["status"];
  blockRows: BlockRowEntry[];
  hasIncoming?: boolean;
  hasOutgoing?: boolean;
  selectedBlockId?: string;
  onBlockClick?: (blockId: string) => void;
}

function BlocksFileNode({ data }: NodeProps<BlocksFileNodeData>): React.ReactElement {
  const accentColor = data.status ? STATUS_COLOR_MAP[data.status] : "#94a3b8";

  return (
    <>
      {(data.hasIncoming ?? true) && (
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
      )}
      <div
        style={{
          width: NODE_FILE_W,
          background: "#fff",
          borderRadius: 10,
          border: "1px solid #e2e8f0",
          boxShadow: "0 1px 5px rgba(0,0,0,0.09)",
          overflow: "hidden",
          cursor: "default",
        }}
      >
        {/* Accent bar */}
        <div style={{ height: 3, background: accentColor }} />

        {/* Header */}
        <div
          style={{
            padding: "6px 10px 5px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: "#0f172a",
              fontFamily: "ui-monospace, monospace",
              flex: 1,
              minWidth: 0,
              overflowWrap: "break-word",
              wordBreak: "break-all",
            }}
          >
            {data.filename}
          </span>
        </div>

        {/* Block rows */}
        {data.blockRows.length === 0 ? (
          <div style={{ padding: "6px 10px", fontSize: 10, color: "#94a3b8" }}>
            No blocks
          </div>
        ) : (
          data.blockRows.map((row) => {
            const isSelected = data.selectedBlockId === row.blockId;
            return (
              <button
                key={row.blockId}
                type="button"
                onClick={() => data.onBlockClick?.(row.blockId)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  width: "100%",
                  padding: "4px 10px",
                  borderBottom: "1px solid #f1f5f9",
                  background: isSelected ? "#f8fafc" : "transparent",
                  cursor: "pointer",
                  textAlign: "left",
                  border: "none",
                  borderBottomWidth: 1,
                  borderBottomStyle: "solid",
                  borderBottomColor: "#f1f5f9",
                }}
              >
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    fontFamily: "ui-monospace, monospace",
                    color: "#475569",
                    background: "#f1f5f9",
                    borderRadius: 3,
                    padding: "1px 4px",
                    flexShrink: 0,
                  }}
                >
                  {row.blockType}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontFamily: "ui-monospace, monospace",
                    color: "#94a3b8",
                    flexShrink: 0,
                  }}
                >
                  :{row.startLine}
                </span>
                <span style={{ flex: 1 }} />
                <span
                  className={[
                    "inline-flex items-center rounded px-1.5 py-0.5",
                    "text-[10px] font-medium",
                    row.statusClassName,
                  ].join(" ")}
                  style={{ flexShrink: 0 }}
                >
                  {row.statusLabel}
                </span>
              </button>
            );
          })
        )}
      </div>
      {(data.hasOutgoing ?? true) && (
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
  { color: "#22c55e", label: "All migrated" },
  { color: "#f59e0b", label: "Needs review" },
  { color: "#ef4444", label: "Has failures" },
];

function TargetLegend(): React.ReactElement {
  return (
    <div style={LEGEND_BOX_STYLE}>
      <div style={SECTION_LABEL_STYLE}>Python modules</div>
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
): Edge[] {
  const rawEdges: Edge[] = [];
  const seenEdgeKeys = new Set<string>();

  for (const fe of lineage.file_edges ?? []) {
    const src = sasFileToPyFile(fe.source_file);
    const tgt = sasFileToPyFile(fe.target_file);
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
  return rawEdges;
}

// ---------------------------------------------------------------------------
// Graph builders per view
// ---------------------------------------------------------------------------

function buildStepsGraph(
  pyFiles: string[],
  lineage: JobLineageResponse,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
): { layoutNodes: Node[]; edges: Edge[] } {
  const nodeSet = new Set(pyFiles);
  const rawEdges = buildRawEdges(lineage, nodeSet);

  const incomingIds = new Set(rawEdges.map((e) => e.target));
  const outgoingIds = new Set(rawEdges.map((e) => e.source));

  // Count per-node in/out degrees
  const inDegree = new Map<string, number>();
  const outDegree = new Map<string, number>();
  for (const e of rawEdges) {
    outDegree.set(e.source, (outDegree.get(e.source) ?? 0) + 1);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  }

  const connectedIds = new Set<string>();
  for (const e of rawEdges) {
    connectedIds.add(e.source);
    connectedIds.add(e.target);
  }

  const rawNodes: Node<PipelineStepNodeData>[] = pyFiles.map((pyFile) => {
    const sasFiles = pyFileToSasFiles(pyFile, blockPlans);
    const blockCount = blockPlans.filter((bp) => sasFiles.includes(bp.source_file)).length;
    return {
      id: pyFile,
      type: "pipelineStep",
      position: { x: 0, y: 0 },
      data: {
        filename: pyFile,
        status: aggregateStatus(pyFile, blockPlans, trustFiles),
        blockCount,
        inCount: inDegree.get(pyFile) ?? 0,
        outCount: outDegree.get(pyFile) ?? 0,
        hasIncoming: incomingIds.has(pyFile),
        hasOutgoing: outgoingIds.has(pyFile),
      },
    };
  });

  const connectedNodes = rawNodes.filter((n) => connectedIds.has(n.id));
  const isolatedNodes = rawNodes.filter((n) => !connectedIds.has(n.id));

  const laidConnected: Node<PipelineStepNodeData>[] =
    connectedNodes.length > 0
      ? applyDagreLayout(connectedNodes, rawEdges, NODE_STEP_W, NODE_STEP_H, {
          rankdir: "TB",
          nodesep: 60,
          ranksep: 140,
        })
      : [];

  const connectedLeft =
    laidConnected.length > 0
      ? Math.min(...laidConnected.map((n) => n.position.x))
      : 0;
  const connectedBottom =
    laidConnected.length > 0
      ? Math.max(...laidConnected.map((n) => n.position.y + NODE_STEP_H))
      : 0;

  // Isolated nodes: horizontal row below connected cluster
  const isolatedTopY = connectedBottom + ISOLATED_GAP + (laidConnected.length > 0 ? 12 : 0);
  const positionedIsolated: Node<PipelineStepNodeData>[] = isolatedNodes.map((n, i) => ({
    ...n,
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    position: {
      x: connectedLeft + i * ISOLATED_SPACING,
      y: isolatedTopY,
    },
  }));

  const allLayoutNodes: Node[] = [...laidConnected, ...positionedIsolated];

  if (isolatedNodes.length > 0) {
    const connectedRight =
      laidConnected.length > 0
        ? Math.max(...laidConnected.map((n) => n.position.x + NODE_STEP_W))
        : connectedLeft + NODE_STEP_W;
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

function buildModulesGraph(
  pyFiles: string[],
  lineage: JobLineageResponse,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
): { layoutNodes: Node[]; edges: Edge[] } {
  const nodeSet = new Set(pyFiles);
  const rawEdges = buildRawEdges(lineage, nodeSet);

  const incomingIds = new Set(rawEdges.map((e) => e.target));
  const outgoingIds = new Set(rawEdges.map((e) => e.source));

  const connectionCount = new Map<string, number>();
  for (const e of rawEdges) {
    connectionCount.set(e.source, (connectionCount.get(e.source) ?? 0) + 1);
    connectionCount.set(e.target, (connectionCount.get(e.target) ?? 0) + 1);
  }

  const rawNodes: Node<FileNodeData>[] = pyFiles.map((pyFile) => {
    const sasFiles = pyFileToSasFiles(pyFile, blockPlans);
    const blockCount = blockPlans.filter((bp) => sasFiles.includes(bp.source_file)).length;
    return {
      id: pyFile,
      type: "fileNode",
      position: { x: 0, y: 0 },
      data: {
        filename: pyFile,
        fullPath: pyFile,
        file_type: "MODULE",
        status: aggregateStatus(pyFile, blockPlans, trustFiles),
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

function buildBlocksGraph(
  pyFiles: string[],
  lineage: JobLineageResponse,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
  trustBlocks: Record<string, TrustReportBlock> | undefined,
  humanVerifiedBlocks: Set<string>,
  selectedBlockId: string | null | undefined,
  onBlockClick: ((blockId: string) => void) | undefined,
): { layoutNodes: Node[]; edges: Edge[] } {
  const nodeSet = new Set(pyFiles);
  const rawEdges = buildRawEdges(lineage, nodeSet);

  const incomingIds = new Set(rawEdges.map((e) => e.target));
  const outgoingIds = new Set(rawEdges.map((e) => e.source));

  // Compute block rows per pyFile
  const nodeHeightMap = new Map<string, number>();
  const rawNodes: Node<BlocksFileNodeData>[] = pyFiles.map((pyFile) => {
    const sasFiles = pyFileToSasFiles(pyFile, blockPlans);
    const fileBlocks = blockPlans
      .filter((bp) => sasFiles.includes(bp.source_file))
      .sort((a, b) => a.start_line - b.start_line);

    const blockRows: BlockRowEntry[] = fileBlocks.map((bp) => {
      const tb = trustBlocks?.[bp.block_id];
      const kind = getBlockStatus(bp, tb, humanVerifiedBlocks.has(bp.block_id));
      const cfg = STATUS_CONFIG[kind];
      return {
        blockId: bp.block_id,
        blockType: bp.block_type,
        startLine: bp.start_line,
        statusLabel: cfg.label,
        statusClassName: cfg.className,
      };
    });

    const nodeH = BLOCKS_BASE_H + BLOCK_ROW_H * fileBlocks.length;
    nodeHeightMap.set(pyFile, nodeH);

    return {
      id: pyFile,
      type: "blocksFile",
      position: { x: 0, y: 0 },
      data: {
        filename: pyFile,
        status: aggregateStatus(pyFile, blockPlans, trustFiles),
        blockRows,
        hasIncoming: incomingIds.has(pyFile),
        hasOutgoing: outgoingIds.has(pyFile),
        selectedBlockId: selectedBlockId ?? undefined,
        onBlockClick,
      },
    };
  });

  const laidNodes = applyDagreLayout(
    rawNodes,
    rawEdges,
    NODE_FILE_W,
    (nodeId) => nodeHeightMap.get(nodeId) ?? BLOCKS_BASE_H,
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
  view = "modules",
  onViewChange,
  onFileClick,
  onModuleClick,
  onBlockClick,
  selectedBlockId,
}: TargetGraphProps): React.ReactElement {
  const { fitView } = useReactFlow();
  const pyFiles = Object.keys(generatedFiles).filter((f) => f !== "pipeline.py");
  const isEmpty = pyFiles.length === 0;

  // humanVerifiedBlocks is not passed in but we can reconstruct an empty set
  // (verification status is already reflected in trustBlocks)
  const humanVerifiedBlocks = new Set<string>();

  // Build the correct graph based on view
  const { layoutNodes: builtNodes, edges: builtEdges } = isEmpty
    ? { layoutNodes: [], edges: [] }
    : view === "steps"
      ? buildStepsGraph(pyFiles, lineage, blockPlans, trustFiles)
      : view === "blocks"
        ? buildBlocksGraph(
            pyFiles,
            lineage,
            blockPlans,
            trustFiles,
            trustBlocks,
            humanVerifiedBlocks,
            selectedBlockId,
            onBlockClick,
          )
        : buildModulesGraph(pyFiles, lineage, blockPlans, trustFiles);

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
    if (view === "steps" || view === "modules") {
      if (onModuleClick) {
        onModuleClick(node.id);
      } else {
        const sasFiles = pyFileToSasFiles(node.id, blockPlans);
        onFileClick(sasFiles);
      }
    }
    // blocks view: row clicks handle their own click via data.onBlockClick
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

          {(["steps", "modules", "blocks"] as const).map((v) => (
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
              {v.charAt(0).toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
      )}
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
        fitViewOptions={{ padding: 0.2 }}
      >
        <Controls />
        <Background />
      </ReactFlow>
      <div style={{ position: "absolute", bottom: 12, right: 12, zIndex: 10 }}>
        <TargetLegend />
      </div>
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
