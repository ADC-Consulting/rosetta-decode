import type { RelationshipSchema, TableSchema } from "@/api/types";
import dagre from "dagre";
import { useEffect } from "react";
import {
  Background,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";

interface DataStorageERDProps {
  tables: TableSchema[];
  relationships: Array<RelationshipSchema>;
  selectedTable?: string | null;
  onTableSelect?: (tableName: string) => void;
}

const NODE_W = 180;
const NODE_H = 64;

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 100, marginx: 20, marginy: 20 });
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

function buildNodes(tables: TableSchema[], selectedTable: string | null | undefined): Node[] {
  return tables.map((t) => {
    const isSelected = t.dataset_name === selectedTable;
    return {
      id: t.dataset_name,
      type: "default",
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: true,
      data: { label: null },
      style: {
        background: isSelected ? "rgba(var(--primary-rgb, 59,130,246), 0.08)" : "#f8fafc",
        border: isSelected ? "2px solid hsl(var(--primary))" : "1.5px solid #e2e8f0",
        borderRadius: 8,
        padding: "8px 12px",
        width: NODE_W,
        minHeight: NODE_H,
        boxShadow: isSelected ? "0 0 0 2px hsl(var(--primary) / 0.25)" : "0 1px 3px rgba(0,0,0,0.08)",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      },
      // React Flow renders `data.label` inside the node — use the label to render content
    };
  }).map((n, i) => ({
    ...n,
    data: {
      label: (
        <div style={{ lineHeight: 1.4 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: "#111827",
              fontFamily: "ui-monospace, monospace",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {tables[i].dataset_name}
          </div>
          <div
            style={{
              fontSize: 10,
              color: "#6b7280",
              marginTop: 3,
              fontWeight: 500,
            }}
          >
            {tables[i].columns.length} cols
          </div>
        </div>
      ),
    },
  }));
}

function buildEdges(relationships: RelationshipSchema[]): Edge[] {
  return relationships.map((r, idx) => ({
    id: `erd-edge-${idx}`,
    source: r.left_table,
    target: r.right_table,
    label: r.key_column,
    labelStyle: { fontSize: 10, fill: "#6b7280", fontFamily: "ui-monospace, monospace" },
    labelBgStyle: { fill: "rgba(255,255,255,0.9)" },
    labelBgPadding: [4, 6] as [number, number],
    type: "smoothstep",
    style: {
      stroke: "#94a3b8",
      strokeWidth: 1.5,
      strokeDasharray: r.relationship_type === "join" ? "5 4" : undefined,
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
  }));
}

// CRITICAL: module-scope — never inside a component (React Flow warning #002)
const NODE_TYPES = {};
const EDGE_TYPES = {};

function DataStorageERDInner({
  tables,
  relationships,
  selectedTable,
  onTableSelect,
}: DataStorageERDProps): React.ReactElement {
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    if (tables.length === 0) return;
    const rawNodes = buildNodes(tables, selectedTable);
    const rawEdges = buildEdges(relationships);
    const laidOut = applyDagreLayout(rawNodes, rawEdges);
    setNodes(laidOut);
    setEdges(rawEdges);
    setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50);
  }, [tables, relationships]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-apply selection highlight without full re-layout
  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const isSelected = n.id === selectedTable;
        return {
          ...n,
          style: {
            ...n.style,
            background: isSelected ? "rgba(59,130,246,0.08)" : "#f8fafc",
            border: isSelected ? "2px solid hsl(var(--primary))" : "1.5px solid #e2e8f0",
            boxShadow: isSelected
              ? "0 0 0 2px hsl(var(--primary) / 0.25)"
              : "0 1px 3px rgba(0,0,0,0.08)",
          },
        };
      }),
    );
  }, [selectedTable, setNodes]);

  if (relationships.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        No relationships detected — MERGE BY or JOIN ON keys needed
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border overflow-hidden" style={{ width: "100%", height: 480 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodeClick={(_, node) => onTableSelect?.(node.id)}
        nodesDraggable
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <Controls />
        <Background />
      </ReactFlow>
    </div>
  );
}

export default function DataStorageERD(props: DataStorageERDProps): React.ReactElement {
  return (
    <ReactFlowProvider>
      <DataStorageERDInner {...props} />
    </ReactFlowProvider>
  );
}
