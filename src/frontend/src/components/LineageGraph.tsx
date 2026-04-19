import type { JobLineageResponse, LineageNode } from "@/api/types";
import dagre from "dagre";
import { RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  Controls,
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
  type Node,
  type NodeChange,
} from "reactflow";
import "reactflow/dist/style.css";

interface LineageGraphProps {
  lineage: JobLineageResponse;
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
  untranslatable: {
    background: "#f5f5f5",
    border: "#ef4444",
    color: "#1a1a1a",
  },
};

const STATUS_LABEL: Record<LineageNode["status"], string> = {
  migrated: "Migrated",
  manual_review: "Manual review",
  untranslatable: "Untranslatable",
};

const STATUS_SYMBOL: Record<
  LineageNode["status"],
  { symbol: string; color: string }
> = {
  migrated: { symbol: "✓", color: "#22c55e" },
  manual_review: { symbol: "⚠", color: "#f59e0b" },
  untranslatable: { symbol: "✗", color: "#ef4444" },
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

// ---------------------------------------------------------------------------
// Dagre layout
// ---------------------------------------------------------------------------

function applyDagreLayout(
  nodes: Node<NodeData>[],
  edges: Edge[],
): Node<NodeData>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 40, ranksep: 80 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

// ---------------------------------------------------------------------------
// Builders
// ---------------------------------------------------------------------------

function buildInitialNodes(lineageNodes: LineageNode[]): Node<NodeData>[] {
  return lineageNodes.map((n) => {
    const style = STATUS_STYLE[n.status];
    const sym = STATUS_SYMBOL[n.status];
    return {
      id: n.id,
      type: "default",
      data: {
        rawLabel: n.label,
        block_type: n.block_type,
        status: n.status,
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
              {abbrevBlockType(n.block_type)}
            </div>
            {/* source_file — filename only */}
            <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 1 }}>
              {n.source_file.split("/").pop() ?? n.source_file}
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
        border: `1.5px solid ${style.border}`,
        borderBottom: `3px solid ${style.border}`,
        color: "#333",
        borderRadius: 8,
        padding: "8px 12px",
        boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
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

function Legend(): React.ReactElement {
  return (
    <div
      style={{
        position: "absolute",
        top: 10,
        right: 10,
        zIndex: 10,
        background: "rgba(245,245,245,0.92)",
        backdropFilter: "blur(6px)",
        borderRadius: 8,
        border: "1px solid rgba(0,0,0,0.1)",
        padding: "8px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 5,
      }}
    >
      {(Object.keys(STATUS_STYLE) as LineageNode["status"][]).map((s) => (
        <div key={s} style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div
            style={{
              width: 20,
              height: 14,
              borderRadius: 3,
              background: "#e8e8e8",
              border: `1.5px solid ${STATUS_STYLE[s].border}`,
              borderBottom: `3px solid ${STATUS_STYLE[s].border}`,
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: 11, color: "#444", fontWeight: 500 }}>
            {STATUS_LABEL[s]}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner graph
// ---------------------------------------------------------------------------

function LineageGraphInner({ lineage }: LineageGraphProps): React.ReactElement {
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<NodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const hoveredIdRef = useRef<string | null>(null);
  const trackHoveredId = (id: string | null) => {
    hoveredIdRef.current = id;
  };

  // Undo/redo history — store {id → position} maps only; merging back preserves ReactFlow's internal state
  type PosSnapshot = Record<string, { x: number; y: number }>;
  const historyRef = useRef<PosSnapshot[]>([]);
  const historyIdxRef = useRef<number>(-1);
  const [historyState, setHistoryState] = useState<{
    idx: number;
    len: number;
  }>({ idx: -1, len: 0 });

  // Initial layout ref for reset
  const initialLayoutRef = useRef<Node<NodeData>[]>([]);

  // Mirror of current nodes — always up-to-date, readable from stable callbacks
  const nodesRef = useRef<Node<NodeData>[]>([]);
  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  // Hover debounce timer
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // When true, onNodesChange is suppressed for one frame so undo/redo/reset
  // position restores are not overwritten by RF's own queued change events.
  const suppressChangesRef = useRef(false);

  useEffect(() => {
    if (lineage.nodes.length === 0) return;
    const rawNodes = buildInitialNodes(lineage.nodes);
    const rawEdges = buildInitialEdges(lineage.edges, lineage.column_flows);
    const laid = applyDagreLayout(rawNodes, rawEdges);
    setNodes(laid);
    setEdges(rawEdges);
    trackHoveredId(null);
    initialLayoutRef.current = laid;
    historyRef.current = [
      Object.fromEntries(
        laid.map((n) => [n.id, { x: n.position.x, y: n.position.y }]),
      ),
    ];
    historyIdxRef.current = 0;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: re-init derived state on lineage change
    setHistoryState({ idx: 0, len: 1 });
  }, [lineage, setNodes, setEdges]);

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
    },
    [edges, setNodes],
  );

  const handleNodeMouseLeave = useCallback(() => {
    if (leaveTimerRef.current !== null) clearTimeout(leaveTimerRef.current);
    leaveTimerRef.current = setTimeout(() => {
      trackHoveredId(null);
      setNodes((prev) =>
        prev.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } })),
      );
      leaveTimerRef.current = null;
    }, 80);
  }, [setNodes]);

  const handlePaneClick = useCallback(() => {
    if (leaveTimerRef.current !== null) {
      clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
    trackHoveredId(null);
    setNodes((prev) =>
      prev.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } })),
    );
  }, [setNodes]);

  const handleNodeDragStop = useCallback(() => {
    // Snapshot ALL current nodes (not just the dragged one — RF only passes dragged nodes)
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

  if (lineage.nodes.length === 0) {
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
      className="rounded-md border border-border overflow-hidden"
      style={{ width: "100%", height: 600, position: "relative" }}
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
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        onNodeDragStop={handleNodeDragStop}
        onPaneClick={handlePaneClick}
        nodesDraggable={true}
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <Controls />
        <Background />
        {nodes.length > 15 && <MiniMap />}
      </ReactFlow>
      <Legend />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export default function LineageGraph({
  lineage,
}: LineageGraphProps): React.ReactElement {
  return (
    <ReactFlowProvider>
      <LineageGraphInner lineage={lineage} />
    </ReactFlowProvider>
  );
}
