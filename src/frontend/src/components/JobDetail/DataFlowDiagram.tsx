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
  useReactFlow,
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
}

type FlowNodeType = "source" | "step" | "output";

interface FlowNodeData {
  label: string;
  nodeType: FlowNodeType;
  isSelected: boolean;
  onClick: () => void;
}

const SOURCE_W = 160;
const STEP_W = 180;
const OUTPUT_W = 160;
const NODE_H = 64;

function SourceNode({ data }: { data: FlowNodeData }): React.ReactElement {
  return (
    <div
      onClick={data.onClick}
      style={{
        width: SOURCE_W,
        minHeight: NODE_H,
        background: data.isSelected ? "#bfdbfe" : "#e0f2fe",
        border: data.isSelected ? "2px solid #3b82f6" : "1.5px solid #93c5fd",
        borderRadius: 8,
        padding: "8px 12px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: "pointer",
        boxShadow: data.isSelected ? "0 0 0 2px rgba(59,130,246,0.25)" : "0 1px 3px rgba(0,0,0,0.08)",
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
        stroke="#1d4ed8"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ flexShrink: 0 }}
      >
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
      <div style={{ overflow: "hidden" }}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "#1e3a5f",
            fontFamily: "ui-monospace, monospace",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {data.label}
        </div>
        <div style={{ fontSize: 10, color: "#3b82f6", marginTop: 2, fontWeight: 500 }}>source</div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: "transparent", border: "none" }}
      />
    </div>
  );
}

function StepNode({ data }: { data: FlowNodeData }): React.ReactElement {
  return (
    <div
      style={{
        width: STEP_W,
        minHeight: NODE_H,
        background: "#f0f4ff",
        border: "1.5px solid #c7d2fe",
        borderRadius: 8,
        padding: "8px 12px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: "default",
        boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
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
        stroke="hsl(var(--primary))"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ flexShrink: 0 }}
      >
        <circle cx={12} cy={12} r={3} />
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14" />
        <path d="M12 2v2M12 20v2M2 12H4M20 12h2" />
      </svg>
      <div style={{ overflow: "hidden" }}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "hsl(var(--primary))",
            fontFamily: "ui-monospace, monospace",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {data.label}
        </div>
        <div
          style={{ fontSize: 10, color: "hsl(var(--primary) / 0.7)", marginTop: 2, fontWeight: 500 }}
        >
          step
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: "transparent", border: "none" }}
      />
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
        <div style={{ fontSize: 10, color: "#10b981", marginTop: 2, fontWeight: 500 }}>output</div>
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
  source: SourceNode as React.ComponentType<{ data: FlowNodeData }>,
  step: StepNode as React.ComponentType<{ data: FlowNodeData }>,
  output: OutputNode as React.ComponentType<{ data: FlowNodeData }>,
};

function nodeWidthFor(type: FlowNodeType): number {
  if (type === "step") return STEP_W;
  return SOURCE_W;
}

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120, marginx: 20, marginy: 20 });
  nodes.forEach((n) => {
    const w = nodeWidthFor((n.data as FlowNodeData).nodeType);
    g.setNode(n.id, { width: w, height: NODE_H });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    const w = nodeWidthFor((n.data as FlowNodeData).nodeType);
    return {
      ...n,
      position: { x: pos.x - w / 2, y: pos.y - NODE_H / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

function buildNodesAndEdges(
  lineage: JobLineageResponse,
  selectedTable: string | null,
  onTableSelect: (name: string) => void,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  if (lineage.pipeline_steps && lineage.pipeline_steps.length > 0) {
    const steps = lineage.pipeline_steps;
    const inputSets = new Set(steps.flatMap((s) => s.inputs));
    const outputSets = new Set(steps.flatMap((s) => s.outputs));
    const pureInputs = [...inputSets].filter((ds) => !outputSets.has(ds));
    const pureOutputs = [...outputSets].filter((ds) => !inputSets.has(ds));

    // Source nodes: only true external sources (not produced by any step)
    pureInputs.forEach((ds) => {
      nodes.push({
        id: `src-${ds}`,
        type: "source",
        position: { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: ds,
          nodeType: "source" as FlowNodeType,
          isSelected: ds === selectedTable,
          onClick: () => onTableSelect(ds),
        } satisfies FlowNodeData,
      });
    });

    // Step nodes
    steps.forEach((step) => {
      nodes.push({
        id: `step-${step.step_id}`,
        type: "step",
        position: { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: step.name,
          nodeType: "step" as FlowNodeType,
          isSelected: false,
          onClick: () => {},
        } satisfies FlowNodeData,
      });

      // Source → step edges (external inputs only)
      step.inputs
        .filter((inp) => pureInputs.includes(inp))
        .forEach((inp, idx) => {
          edges.push({
            id: `e-src-${step.step_id}-${inp}-${idx}`,
            source: `src-${inp}`,
            target: `step-${step.step_id}`,
            type: "smoothstep",
            style: { stroke: "#94a3b8", strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
          });
        });
    });

    // Step → step edges (intermediate datasets connect steps)
    const seenStepEdges = new Set<string>();
    steps.forEach((stepA) => {
      steps.forEach((stepB) => {
        if (stepA.step_id === stepB.step_id) return;
        const shared = stepA.outputs.filter((out) => stepB.inputs.includes(out));
        if (shared.length === 0) return;
        const key = `${stepA.step_id}→${stepB.step_id}`;
        if (seenStepEdges.has(key)) return;
        seenStepEdges.add(key);
        edges.push({
          id: `e-step-${stepA.step_id}-${stepB.step_id}`,
          source: `step-${stepA.step_id}`,
          target: `step-${stepB.step_id}`,
          type: "smoothstep",
          label: shared.join(", "),
          style: { stroke: "#94a3b8", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
        });
      });
    });

    // Output nodes: only pure outputs (not consumed by any step)
    pureOutputs.forEach((ds) => {
      nodes.push({
        id: `out-${ds}`,
        type: "output",
        position: { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: ds,
          nodeType: "output" as FlowNodeType,
          isSelected: ds === selectedTable,
          onClick: () => onTableSelect(ds),
        } satisfies FlowNodeData,
      });
    });

    // Step → pure output edges
    steps.forEach((step) => {
      step.outputs
        .filter((out) => pureOutputs.includes(out))
        .forEach((out, idx) => {
          edges.push({
            id: `e-out-${step.step_id}-${out}-${idx}`,
            source: `step-${step.step_id}`,
            target: `out-${out}`,
            type: "smoothstep",
            style: { stroke: "#6ee7b7", strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#6ee7b7" },
          });
        });
    });

    // Remove step nodes that have no edges (no data flow connections)
    const connectedNodeIds = new Set(edges.flatMap((e) => [e.source, e.target]));
    const filteredNodes = nodes.filter(
      (n) => (n.data as FlowNodeData).nodeType !== "step" || connectedNodeIds.has(n.id),
    );
    return { nodes: filteredNodes, edges };
  }

  const lineageNodes: LineageNode[] = lineage.nodes ?? [];
  const lineageEdges = lineage.edges ?? [];

  const writtenDatasets = new Set(lineageEdges.map((e) => e.dataset));
  const targetDatasets = new Set(lineageEdges.map((e) => e.target));
  const outputDatasets = [...writtenDatasets].filter((ds) => !targetDatasets.has(ds));

  lineageNodes.forEach((ln) => {
    const inputDatasetsForNode = lineageEdges
      .filter((e) => e.target === ln.id)
      .map((e) => e.dataset);

    inputDatasetsForNode.forEach((ds, idx) => {
      const srcId = `src-${ds}`;
      if (!nodes.find((n) => n.id === srcId)) {
        nodes.push({
          id: srcId,
          type: "source",
          position: { x: 0, y: 0 },
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          data: {
            label: ds,
            nodeType: "source" as FlowNodeType,
            isSelected: ds === selectedTable,
            onClick: () => onTableSelect(ds),
          } satisfies FlowNodeData,
        });
      }

      edges.push({
        id: `e-src-${ln.id}-${ds}-${idx}`,
        source: srcId,
        target: `step-${ln.id}`,
        type: "smoothstep",
        style: { stroke: "#94a3b8", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
      });
    });

    nodes.push({
      id: `step-${ln.id}`,
      type: "step",
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        label: ln.label,
        nodeType: "step" as FlowNodeType,
        isSelected: false,
        onClick: () => {},
      } satisfies FlowNodeData,
    });

    const outputDatasetsForNode = lineageEdges
      .filter((e) => e.source === ln.id)
      .map((e) => e.dataset);

    outputDatasetsForNode.forEach((ds, idx) => {
      const outId = `out-${ds}`;
      if (!nodes.find((n) => n.id === outId)) {
        const isOutput = outputDatasets.includes(ds);
        nodes.push({
          id: outId,
          type: isOutput ? "output" : "source",
          position: { x: 0, y: 0 },
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          data: {
            label: ds,
            nodeType: (isOutput ? "output" : "source") as FlowNodeType,
            isSelected: ds === selectedTable,
            onClick: () => onTableSelect(ds),
          } satisfies FlowNodeData,
        });
      }

      edges.push({
        id: `e-out-${ln.id}-${ds}-${idx}`,
        source: `step-${ln.id}`,
        target: `out-${ds}`,
        type: "smoothstep",
        style: { stroke: "#6ee7b7", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#6ee7b7" },
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
}: InnerProps): React.ReactElement {
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    const { nodes: rawNodes, edges: rawEdges } = buildNodesAndEdges(
      lineage,
      selectedTable,
      onTableSelect,
    );
    if (rawNodes.length === 0) return;
    const laidOut = applyDagreLayout(rawNodes, rawEdges);
    setNodes(laidOut);
    setEdges(rawEdges);
    setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50);
  }, [lineage]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const d = n.data as FlowNodeData;
        if (d.nodeType === "step") return n;
        const isSelected = d.label === selectedTable;
        return {
          ...n,
          data: {
            ...d,
            isSelected,
            onClick: () => onTableSelect(d.label),
          },
        };
      }),
    );
  }, [selectedTable, onTableSelect, setNodes]);

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        No flow data available — run a migration to generate lineage.
      </div>
    );
  }

  return (
    <div
      className="rounded-md border border-border overflow-hidden w-full h-full"
      style={{ position: "relative" }}
    >
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
      <div
        style={{
          position: "absolute",
          bottom: 12,
          right: 12,
          background: "rgba(255,255,255,0.92)",
          border: "1px solid #e2e8f0",
          borderRadius: 6,
          padding: "6px 10px",
          display: "flex",
          flexDirection: "column",
          gap: 4,
          fontSize: 11,
          zIndex: 10,
          pointerEvents: "none",
        }}
      >
        {[
          { bg: "#e0f2fe", border: "#93c5fd", label: "Source" },
          { bg: "#f0f4ff", border: "#c7d2fe", label: "Step" },
          { bg: "#d1fae5", border: "#6ee7b7", label: "Output" },
        ].map(({ bg, border, label }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: 3,
                background: bg,
                border: `1.5px solid ${border}`,
                flexShrink: 0,
              }}
            />
            <span style={{ color: "#475569", fontWeight: 500 }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DataFlowDiagramLoader({
  jobId,
  selectedTable,
  onTableSelect,
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
