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
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "reactflow";
import "reactflow/dist/style.css";
import { useCallback, useEffect, useState } from "react";
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
        bottom: 12,
        right: 12,
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
  const [nodes, setNodes, onNodesChange] = useNodesState<NodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [focusedId, setFocusedId] = useState<string | null>(null);

  useEffect(() => {
    if (lineage.nodes.length === 0) return;
    const rawNodes = buildInitialNodes(lineage.nodes);
    const rawEdges = buildInitialEdges(lineage.edges);
    const laid = applyDagreLayout(rawNodes, rawEdges);
    setNodes(laid);
    setEdges(rawEdges);
    setFocusedId(null); // eslint-disable-line react-hooks/set-state-in-effect
  }, [lineage, setNodes, setEdges]);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => onNodesChange(changes),
    [onNodesChange],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => onEdgesChange(changes),
    [onEdgesChange],
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node<NodeData>) => {
      const related = getRelated(node.id, edges);
      setFocusedId(node.id);
      setNodes((prev) =>
        prev.map((n) => ({ ...n, style: { ...n.style, opacity: related.has(n.id) ? 1 : 0.2 } })),
      );
    },
    [edges, setNodes],
  );

  const handlePaneClick = useCallback(() => {
    if (!focusedId) return;
    setFocusedId(null);
    setNodes((prev) => prev.map((n) => ({ ...n, style: { ...n.style, opacity: 1 } })));
  }, [focusedId, setNodes]);

  if (lineage.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-150 text-sm text-muted-foreground">
        No lineage data available
      </div>
    );
  }

  return (
    <div
      className="rounded-md border border-border overflow-hidden"
      style={{ width: "100%", height: 600, position: "relative" }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onNodeClick={handleNodeClick}
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
