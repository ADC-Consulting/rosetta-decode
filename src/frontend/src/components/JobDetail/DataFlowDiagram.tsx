import { getJobLineage } from "@/api/jobs";
import type { JobLineageResponse, LineageNode } from "@/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import dagre from "dagre";
import { useEffect } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import { useQuery } from "@tanstack/react-query";

interface DataFlowDiagramProps {
  jobId: string;
  selectedTable: string | null;
  onTableSelect: (datasetName: string) => void;
  outputTableNames: string[];
}

type FlowNodeType = "intermediate" | "output";

interface FlowNodeData {
  label: string;
  nodeType: FlowNodeType;
  isSelected: boolean;
  onClick: () => void;
  inputs?: string[];
  outputs?: string[];
}

const TABLE_W = 160;
const OUTPUT_W = 160;
const NODE_H = 64;

function IntermediateNode({ data }: { data: FlowNodeData }): React.ReactElement {
  return (
    <div
      onClick={data.onClick}
      style={{
        width: TABLE_W,
        minHeight: NODE_H,
        background: data.isSelected ? "#fde68a" : "#fef9c3",
        border: data.isSelected ? "2px solid #ca8a04" : "1.5px solid #fcd34d",
        borderRadius: 8,
        padding: "8px 12px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: "pointer",
        boxShadow: data.isSelected ? "0 0 0 2px rgba(202,138,4,0.2)" : "0 1px 3px rgba(0,0,0,0.08)",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: "transparent", border: "none" }} />
      <svg
        width={16}
        height={16}
        viewBox="0 0 24 24"
        fill="none"
        stroke="#92400e"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ flexShrink: 0 }}
      >
        <rect x={3} y={3} width={18} height={18} rx={2} ry={2} />
        <line x1={3} y1={9} x2={21} y2={9} />
        <line x1={3} y1={15} x2={21} y2={15} />
        <line x1={9} y1={3} x2={9} y2={21} />
        <line x1={15} y1={3} x2={15} y2={21} />
      </svg>
      <div style={{ overflow: "hidden" }}>
        <div
          title={data.label}
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "#78350f",
            fontFamily: "ui-monospace, monospace",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {data.label}
        </div>
        <div style={{ fontSize: 10, color: "#ca8a04", marginTop: 2, fontWeight: 500 }}>intermediate</div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "transparent", border: "none" }} />
    </div>
  );
}

function OutputNode({ data }: { data: FlowNodeData }): React.ReactElement {
  return (
    <div
      onClick={data.onClick}
      style={{
        width: OUTPUT_W,
        minHeight: NODE_H,
        background: data.isSelected ? "#a7f3d0" : "#d1fae5",
        border: data.isSelected ? "2px solid #10b981" : "1.5px solid #6ee7b7",
        borderRadius: 8,
        padding: "8px 12px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: "pointer",
        boxShadow: data.isSelected
          ? "0 0 0 2px rgba(16,185,129,0.25)"
          : "0 1px 3px rgba(0,0,0,0.08)",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: "transparent", border: "none" }}
      />
      <svg
        width={16}
        height={16}
        viewBox="0 0 24 24"
        fill="none"
        stroke="#065f46"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ flexShrink: 0 }}
      >
        <rect x={3} y={3} width={18} height={18} rx={2} ry={2} />
        <line x1={3} y1={9} x2={21} y2={9} />
        <line x1={3} y1={15} x2={21} y2={15} />
        <line x1={9} y1={3} x2={9} y2={21} />
        <line x1={15} y1={3} x2={15} y2={21} />
      </svg>
      <div style={{ overflow: "hidden" }}>
        <div
          title={data.label}
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "#065f46",
            fontFamily: "ui-monospace, monospace",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {data.label}
        </div>
        <div style={{ fontSize: 10, color: "#10b981", marginTop: 2, fontWeight: 500 }}>output table</div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: "transparent", border: "none" }}
      />
    </div>
  );
}

const NODE_TYPES: NodeTypes = {
  intermediate: IntermediateNode as React.ComponentType<{ data: FlowNodeData }>,
  output: OutputNode as React.ComponentType<{ data: FlowNodeData }>,
};

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120, marginx: 20, marginy: 20 });
  nodes.forEach((n) => {
    g.setNode(n.id, { width: TABLE_W, height: NODE_H });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - TABLE_W / 2, y: pos.y - NODE_H / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

function buildNodesAndEdges(
  lineage: JobLineageResponse,
  selectedTable: string | null,
  onTableSelect: (name: string) => void,
  outputTableNames: string[],
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  if (lineage.pipeline_steps && lineage.pipeline_steps.length > 0) {
    const steps = lineage.pipeline_steps;

    const producedByAnyStep = new Set(steps.flatMap((s) => s.outputs));
    const outputNamesSet = new Set(outputTableNames);

    // All produced datasets as nodes — final or intermediate
    producedByAnyStep.forEach((ds) => {
      const isFinal = outputNamesSet.has(ds);
      nodes.push({
        id: `out-${ds}`,
        type: isFinal ? "output" : "intermediate",
        position: { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: ds,
          nodeType: (isFinal ? "output" : "intermediate") as FlowNodeType,
          isSelected: ds === selectedTable,
          onClick: () => onTableSelect(ds),
        } satisfies FlowNodeData,
      });
    });

    // Edges: whenever a step consumes a produced dataset and emits another produced dataset
    const seenEdges = new Set<string>();
    steps.forEach((step) => {
      const inProduced = step.inputs.filter((inp) => producedByAnyStep.has(inp));
      const outProduced = step.outputs; // always in producedByAnyStep
      inProduced.forEach((inp) => {
        outProduced.forEach((out) => {
          const key = `out-${inp}→out-${out}`;
          if (seenEdges.has(key)) return;
          seenEdges.add(key);
          edges.push({
            id: `e-${inp}-${out}`,
            source: `out-${inp}`,
            target: `out-${out}`,
            type: "smoothstep",
            style: { stroke: "#94a3b8", strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
          });
        });
      });
    });

    return { nodes, edges };
  }

  const lineageNodes: LineageNode[] = lineage.nodes ?? [];
  const lineageEdges = lineage.edges ?? [];

  // All datasets produced by any lineage node
  const producerNodeIds = new Set(lineageNodes.map((ln) => ln.id));
  const outputTableNamesSet = new Set(outputTableNames);
  const allLegacyProduced = new Set(
    lineageEdges.filter((e) => producerNodeIds.has(e.source)).map((e) => e.dataset),
  );

  allLegacyProduced.forEach((ds) => {
    if (!nodes.find((n) => n.id === `out-${ds}`)) {
      const isFinal = outputTableNamesSet.has(ds);
      nodes.push({
        id: `out-${ds}`,
        type: isFinal ? "output" : "intermediate",
        position: { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: ds,
          nodeType: (isFinal ? "output" : "intermediate") as FlowNodeType,
          isSelected: ds === selectedTable,
          onClick: () => onTableSelect(ds),
        } satisfies FlowNodeData,
      });
    }
  });

  // For each lineage node, find its input datasets and output datasets that are
  // both in allLegacyProduced, then add dataset-node → dataset-node edges.
  const seenEdges = new Set<string>();
  lineageNodes.forEach((ln) => {
    const inProduced = lineageEdges
      .filter((e) => e.target === ln.id && allLegacyProduced.has(e.dataset))
      .map((e) => e.dataset);
    const outProduced = lineageEdges
      .filter((e) => e.source === ln.id && allLegacyProduced.has(e.dataset))
      .map((e) => e.dataset);
    inProduced.forEach((inp) => {
      outProduced.forEach((out) => {
        const edgeKey = `out-${inp}→out-${out}`;
        if (seenEdges.has(edgeKey)) return;
        seenEdges.add(edgeKey);
        edges.push({
          id: `e-${inp}-${out}`,
          source: `out-${inp}`,
          target: `out-${out}`,
          type: "smoothstep",
          style: { stroke: "#94a3b8", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
        });
      });
    });
  });

  return { nodes, edges };
}

interface InnerProps extends DataFlowDiagramProps {
  lineage: JobLineageResponse;
}

function DataFlowDiagramInner({
  lineage,
  selectedTable,
  onTableSelect,
  outputTableNames,
}: InnerProps): React.ReactElement {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    const { nodes: rawNodes, edges: rawEdges } = buildNodesAndEdges(
      lineage,
      selectedTable,
      onTableSelect,
      outputTableNames,
    );
    if (rawNodes.length === 0) return;
    const laidOut = applyDagreLayout(rawNodes, rawEdges);
    setNodes(laidOut);
    setEdges(rawEdges);
  }, [lineage]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const d = n.data as FlowNodeData;
        return {
          ...n,
          data: {
            ...d,
            isSelected: d.label === selectedTable,
            onClick: () => onTableSelect(d.label),
          },
        };
      }),
    );
  }, [selectedTable, onTableSelect, setNodes]);

  const intermediateCount = nodes.filter(
    (n) => (n.data as FlowNodeData).nodeType === "intermediate",
  ).length;
  const finalCount = nodes.filter((n) => (n.data as FlowNodeData).nodeType === "output").length;

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        No flow data available — run a migration to generate lineage.
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full h-full min-h-0">
      <div className="shrink-0 flex items-center gap-2 px-3 py-1.5 border-b border-border text-xs text-muted-foreground bg-muted/10">
        <span>ETL tables</span>
        <span className="text-muted-foreground/40">·</span>
        <span className="font-medium" style={{ color: "#ca8a04" }}>{intermediateCount} intermediate</span>
        <span className="text-muted-foreground/40">·</span>
        <span className="font-medium text-emerald-600">{finalCount} output</span>
      </div>
      <div className="flex-1 min-h-0 rounded-md border border-border overflow-hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={NODE_TYPES}
          nodesDraggable
          fitView
          fitViewOptions={{ padding: 0.2 }}
        >
          <Controls />
          <Background />
        </ReactFlow>
      </div>
    </div>
  );
}

function DataFlowDiagramLoader({
  jobId,
  selectedTable,
  onTableSelect,
  outputTableNames,
}: DataFlowDiagramProps): React.ReactElement {
  const { data: lineage, isLoading } = useQuery({
    queryKey: ["job-lineage", jobId],
    queryFn: () => getJobLineage(jobId),
    staleTime: 60_000,
  });

  if (isLoading) {
    return <Skeleton className="h-full w-full" />;
  }

  if (!lineage) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Lineage data unavailable.
      </div>
    );
  }

  return (
    <DataFlowDiagramInner
      jobId={jobId}
      lineage={lineage}
      selectedTable={selectedTable}
      onTableSelect={onTableSelect}
      outputTableNames={outputTableNames}
    />
  );
}

export default function DataFlowDiagram(props: DataFlowDiagramProps): React.ReactElement {
  return (
    <ReactFlowProvider>
      <DataFlowDiagramLoader {...props} />
    </ReactFlowProvider>
  );
}
