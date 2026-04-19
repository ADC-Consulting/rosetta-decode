import dagre from "dagre";
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
import { useCallback, useEffect, useRef, useState } from "react";
import type { JobLineageResponse, LineageNode } from "@/api/types";

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
  migrated: { background: "#d1fae5", border: "#10b981", color: "#065f46" },
  manual_review: { background: "#fef3c7", border: "#f59e0b", color: "#92400e" },
  untranslatable: { background: "#fee2e2", border: "#ef4444", color: "#991b1b" },
};

const STATUS_LABEL: Record<LineageNode["status"], string> = {
  migrated: "Migrated",
  manual_review: "Manual review",
  untranslatable: "Untranslatable",
};

const NODE_W = 180;
const NODE_H = 56;

// ---------------------------------------------------------------------------
// Dagre layout
// ---------------------------------------------------------------------------

function applyDagreLayout(nodes: Node<NodeData>[], edges: Edge[]): Node<NodeData>[] {
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
    return {
      id: n.id,
      type: "default",
      data: {
        rawLabel: n.label,
        block_type: n.block_type,
        status: n.status,
        label: (
          <div style={{ lineHeight: 1.3 }}>
            <div style={{ fontWeight: 600, fontSize: 12 }}>{n.label}</div>
            <div style={{ fontFamily: "monospace", fontSize: 10, opacity: 0.65, marginTop: 2 }}>
              {n.block_type}
            </div>
          </div>
        ),
      },
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: true,
      style: {
        background: style.background,
        border: `2px solid ${style.border}`,
        color: style.color,
        borderRadius: 8,
        padding: "8px 14px",
        boxShadow: "0 1px 4px rgba(0,0,0,0.10)",
        width: NODE_W,
        minHeight: NODE_H,
        transition: "opacity 0.18s ease",
      },
    };
  });
}

function buildInitialEdges(lineageEdges: JobLineageResponse["edges"]): Edge[] {
  return lineageEdges.map((e) => ({
    id: `e-${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    animated: false,
    style: {
      stroke: "#94a3b8",
      strokeWidth: 1.5,
      ...(e.inferred ? { strokeDasharray: "5 5" } : {}),
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
  }));
}

// ---------------------------------------------------------------------------
// Ancestor/descendant closure
// ---------------------------------------------------------------------------

function getRelated(nodeId: string, edges: Edge[]): Set<string> {
  const related = new Set<string>([nodeId]);
  const visitUp = (id: string) => {
    edges.forEach((e) => { if (e.target === id && !related.has(e.source)) { related.add(e.source); visitUp(e.source); } });
  };
  const visitDown = (id: string) => {
    edges.forEach((e) => { if (e.source === id && !related.has(e.target)) { related.add(e.target); visitDown(e.target); } });
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
        background: "rgba(255,255,255,0.78)",
        backdropFilter: "blur(6px)",
        borderRadius: 8,
        border: "1px solid #e2e8f0",
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
              width: 12,
              height: 12,
              borderRadius: 3,
              background: STATUS_STYLE[s].background,
              border: `2px solid ${STATUS_STYLE[s].border}`,
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: 11, color: "#475569", fontWeight: 500 }}>
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
  const trackHoveredId = (id: string | null) => { hoveredIdRef.current = id; };

  // Undo/redo history — store {id → position} maps only; merging back preserves ReactFlow's internal state
  type PosSnapshot = Record<string, { x: number; y: number }>;
  const historyRef = useRef<PosSnapshot[]>([]);
  const historyIdxRef = useRef<number>(-1);
  const [historyState, setHistoryState] = useState<{ idx: number; len: number }>({ idx: -1, len: 0 });

  // Initial layout ref for reset
  const initialLayoutRef = useRef<Node<NodeData>[]>([]);

  // Mirror of current nodes — always up-to-date, readable from stable callbacks
  const nodesRef = useRef<Node<NodeData>[]>([]);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);

  // Hover debounce timer
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // When true, onNodesChange is suppressed for one frame so undo/redo/reset
  // position restores are not overwritten by RF's own queued change events.
  const suppressChangesRef = useRef(false);

  useEffect(() => {
    if (lineage.nodes.length === 0) return;
    const rawNodes = buildInitialNodes(lineage.nodes);
    const rawEdges = buildInitialEdges(lineage.edges);
    const laid = applyDagreLayout(rawNodes, rawEdges);
    setNodes(laid);
    setEdges(rawEdges);
    trackHoveredId(null);
    initialLayoutRef.current = laid;
    historyRef.current = [Object.fromEntries(laid.map((n) => [n.id, { x: n.position.x, y: n.position.y }]))];
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
        prev.map((n) => ({ ...n, style: { ...n.style, opacity: related.has(n.id) ? 1 : 0.2 } })),
      );
    },
    [edges, setNodes],
  );

  const handleNodeMouseLeave = useCallback(() => {
    if (leaveTimerRef.current !== null) clearTimeout(leaveTimerRef.current);
    leaveTimerRef.current = setTimeout(() => {
      trackHoveredId(null);
      setNodes((prev) => prev.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } })));
      leaveTimerRef.current = null;
    }, 80);
  }, [setNodes]);

  const handlePaneClick = useCallback(() => {
    if (leaveTimerRef.current !== null) {
      clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
    trackHoveredId(null);
    setNodes((prev) => prev.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } })));
  }, [setNodes]);

  const handleNodeDragStop = useCallback(
    () => {
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
    },
    [],
  );

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
        return { ...n, position: { x: p.x, y: p.y }, positionAbsolute: { x: p.x, y: p.y }, dragging: false, style: { ...n.style, opacity: 1 } };
      }),
    );
    requestAnimationFrame(() => { suppressChangesRef.current = false; });
    setHistoryState({ idx: historyIdxRef.current, len: historyRef.current.length });
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
        return { ...n, position: { x: p.x, y: p.y }, positionAbsolute: { x: p.x, y: p.y }, dragging: false, style: { ...n.style, opacity: 1 } };
      }),
    );
    requestAnimationFrame(() => { suppressChangesRef.current = false; });
    setHistoryState({ idx: historyIdxRef.current, len: historyRef.current.length });
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
    requestAnimationFrame(() => { suppressChangesRef.current = false; });
    historyRef.current = [Object.fromEntries(initial.map((n) => [n.id, { x: n.position.x, y: n.position.y }]))];
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
  const btnDisabled: React.CSSProperties = { opacity: 0.4, cursor: "not-allowed" };

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
          style={historyState.idx <= 0 ? { ...btnBase, ...btnDisabled } : btnBase}
          disabled={historyState.idx <= 0}
          onClick={handleUndo}
          title="Undo"
        >
          ↩ Undo
        </button>
        <button
          style={historyState.idx >= historyState.len - 1 ? { ...btnBase, ...btnDisabled } : btnBase}
          disabled={historyState.idx >= historyState.len - 1}
          onClick={handleRedo}
          title="Redo"
        >
          ↪ Redo
        </button>
        <button style={btnBase} onClick={handleReset} title="Reset layout">
          ⟳ Reset
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

export default function LineageGraph({ lineage }: LineageGraphProps): React.ReactElement {
  return (
    <ReactFlowProvider>
      <LineageGraphInner lineage={lineage} />
    </ReactFlowProvider>
  );
}
