import { getJobLineage } from "@/api/jobs";
import type { JobLineageResponse, LineageNode } from "@/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import dagre from "dagre";
import { useEffect, useState } from "react";
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

type FlowNodeType = "intermediate" | "output" | "step";

// ── Dataset node data ─────────────────────────────────────────────────────────

interface StepRef {
  stepIndex: number;
  stepName: string;
}

interface DatasetNodeData {
  kind: "dataset";
  label: string;
  nodeType: "intermediate" | "output";
  isSelected: boolean;
  onDatasetClick: (name: string) => void;
  onSelectNode: (id: string) => void;
  nodeId: string;
  producedBy: StepRef | null;
  consumedBy: StepRef[];
}

// ── Step node data ────────────────────────────────────────────────────────────

interface StepNodeData {
  kind: "step";
  stepIndex: number;
  name: string;
  description: string;
  inputs: string[];
  outputs: string[];
  pythonFile: string | null;
  isSelected: boolean;
  onSelectNode: (id: string) => void;
  nodeId: string;
}

type FlowNodeData = DatasetNodeData | StepNodeData;

// ── Dimensions ────────────────────────────────────────────────────────────────

const TABLE_W = 160;
const NODE_H = 64;
const STEP_W = 140;
const STEP_H = 48;

// ── IntermediateNode ──────────────────────────────────────────────────────────

function IntermediateNode({ data }: { data: FlowNodeData }): React.ReactElement {
  if (data.kind !== "dataset") return <></>;
  const d = data as DatasetNodeData;
  return (
    <div
      onClick={() => {
        d.onDatasetClick(d.label);
        d.onSelectNode(d.nodeId);
      }}
      style={{
        width: TABLE_W,
        minHeight: NODE_H,
        background: d.isSelected ? "#fde68a" : "#fef9c3",
        border: d.isSelected ? "2px solid #ca8a04" : "1.5px solid #fcd34d",
        borderRadius: 8,
        padding: "8px 12px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: "pointer",
        boxShadow: d.isSelected
          ? "0 0 0 2px rgba(202,138,4,0.2)"
          : "0 1px 3px rgba(0,0,0,0.08)",
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
          title={d.label}
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
          {d.label}
        </div>
        <div style={{ fontSize: 10, color: "#ca8a04", marginTop: 2, fontWeight: 500 }}>intermediate</div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "transparent", border: "none" }} />
    </div>
  );
}

// ── OutputNode ────────────────────────────────────────────────────────────────

function OutputNode({ data }: { data: FlowNodeData }): React.ReactElement {
  if (data.kind !== "dataset") return <></>;
  const d = data as DatasetNodeData;
  return (
    <div
      onClick={() => {
        d.onDatasetClick(d.label);
        d.onSelectNode(d.nodeId);
      }}
      style={{
        width: TABLE_W,
        minHeight: NODE_H,
        background: d.isSelected ? "#a7f3d0" : "#d1fae5",
        border: d.isSelected ? "2px solid #10b981" : "1.5px solid #6ee7b7",
        borderRadius: 8,
        padding: "8px 12px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: "pointer",
        boxShadow: d.isSelected
          ? "0 0 0 2px rgba(16,185,129,0.25)"
          : "0 1px 3px rgba(0,0,0,0.08)",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: "transparent", border: "none" }} />
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
          title={d.label}
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
          {d.label}
        </div>
        <div style={{ fontSize: 10, color: "#10b981", marginTop: 2, fontWeight: 500 }}>output table</div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "transparent", border: "none" }} />
    </div>
  );
}

// ── StepNode ──────────────────────────────────────────────────────────────────

function StepNode({ data }: { data: FlowNodeData }): React.ReactElement {
  if (data.kind !== "step") return <></>;
  const d = data as StepNodeData;
  return (
    <div
      onClick={() => d.onSelectNode(d.nodeId)}
      style={{
        width: STEP_W,
        height: STEP_H,
        background: d.isSelected ? "#e2e8f0" : "#f8fafc",
        border: d.isSelected ? "2px solid #64748b" : "1.5px solid #cbd5e1",
        borderRadius: 6,
        padding: "6px 10px",
        display: "flex",
        alignItems: "center",
        gap: 7,
        cursor: "pointer",
        boxShadow: d.isSelected
          ? "0 0 0 2px rgba(100,116,139,0.2)"
          : "0 1px 2px rgba(0,0,0,0.06)",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: "transparent", border: "none" }} />
      <svg
        width={14}
        height={14}
        viewBox="0 0 24 24"
        fill="none"
        stroke="#475569"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ flexShrink: 0 }}
      >
        <circle cx={12} cy={12} r={3} />
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14" />
      </svg>
      <div style={{ overflow: "hidden", flex: 1 }}>
        <div
          style={{
            fontSize: 10,
            color: "#94a3b8",
            fontWeight: 600,
            lineHeight: "1.2",
          }}
        >
          Step {d.stepIndex + 1}
        </div>
        <div
          title={d.name}
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "#334155",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {d.name}
        </div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: "transparent", border: "none" }} />
    </div>
  );
}

// ── Node type registry ────────────────────────────────────────────────────────

const NODE_TYPES: NodeTypes = {
  intermediate: IntermediateNode as React.ComponentType<{ data: FlowNodeData }>,
  output: OutputNode as React.ComponentType<{ data: FlowNodeData }>,
  step: StepNode as React.ComponentType<{ data: FlowNodeData }>,
};

// ── Dagre layout ──────────────────────────────────────────────────────────────

function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120, marginx: 20, marginy: 20 });
  nodes.forEach((n) => {
    const w = n.type === "step" ? STEP_W : TABLE_W;
    const h = n.type === "step" ? STEP_H : NODE_H;
    g.setNode(n.id, { width: w, height: h });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const w = n.type === "step" ? STEP_W : TABLE_W;
    const h = n.type === "step" ? STEP_H : NODE_H;
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - w / 2, y: pos.y - h / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });
}

// ── Build nodes + edges ───────────────────────────────────────────────────────

interface BuildResult {
  nodes: Node[];
  edges: Edge[];
}

function buildNodesAndEdges(
  lineage: JobLineageResponse,
  selectedTable: string | null,
  selectedNodeId: string | null,
  onTableSelect: (name: string) => void,
  onSelectNode: (id: string) => void,
  outputTableNames: string[],
): BuildResult {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  if (lineage.pipeline_steps && lineage.pipeline_steps.length > 0) {
    const steps = lineage.pipeline_steps;
    const outputNamesSet = new Set(outputTableNames);

    // Build lookup: dataset → which steps produce / consume it
    const producedByStep = new Map<string, StepRef>();
    const consumedByStep = new Map<string, StepRef[]>();

    steps.forEach((step, idx) => {
      const ref: StepRef = { stepIndex: idx, stepName: step.name };
      step.outputs.forEach((ds) => {
        producedByStep.set(ds, ref);
      });
      step.inputs.forEach((ds) => {
        const existing = consumedByStep.get(ds) ?? [];
        existing.push(ref);
        consumedByStep.set(ds, existing);
      });
    });

    const allDatasets = new Set([
      ...steps.flatMap((s) => s.outputs),
      ...steps.flatMap((s) => s.inputs).filter((inp) => producedByStep.has(inp)),
    ]);

    // Dataset nodes
    allDatasets.forEach((ds) => {
      const isFinal = outputNamesSet.has(ds);
      const nodeId = `ds-${ds}`;
      nodes.push({
        id: nodeId,
        type: isFinal ? "output" : "intermediate",
        position: { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          kind: "dataset",
          label: ds,
          nodeType: (isFinal ? "output" : "intermediate") as "intermediate" | "output",
          isSelected: ds === selectedTable || nodeId === selectedNodeId,
          onDatasetClick: onTableSelect,
          onSelectNode,
          nodeId,
          producedBy: producedByStep.get(ds) ?? null,
          consumedBy: consumedByStep.get(ds) ?? [],
        } satisfies DatasetNodeData,
      });
    });

    // Step nodes
    steps.forEach((step, idx) => {
      const nodeId = `step-${step.step_id}`;
      nodes.push({
        id: nodeId,
        type: "step" as FlowNodeType,
        position: { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          kind: "step",
          stepIndex: idx,
          name: step.name,
          description: step.description,
          inputs: step.inputs,
          outputs: step.outputs,
          pythonFile: step.files.length > 0 ? step.files[0] : null,
          isSelected: nodeId === selectedNodeId,
          onSelectNode,
          nodeId,
        } satisfies StepNodeData,
      });
    });

    // Edges: dataset → step, step → dataset (N+M per step, not N×M)
    const seenEdges = new Set<string>();
    steps.forEach((step) => {
      const stepNodeId = `step-${step.step_id}`;

      step.inputs.forEach((inp) => {
        if (!allDatasets.has(inp)) return;
        const key = `ds-${inp}→${stepNodeId}`;
        if (seenEdges.has(key)) return;
        seenEdges.add(key);
        edges.push({
          id: `e-${inp}-to-${step.step_id}`,
          source: `ds-${inp}`,
          target: stepNodeId,
          type: "smoothstep",
          style: { stroke: "#94a3b8", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
        });
      });

      step.outputs.forEach((out) => {
        const key = `${stepNodeId}→ds-${out}`;
        if (seenEdges.has(key)) return;
        seenEdges.add(key);
        edges.push({
          id: `e-${step.step_id}-to-${out}`,
          source: stepNodeId,
          target: `ds-${out}`,
          type: "smoothstep",
          style: { stroke: "#94a3b8", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
        });
      });
    });

    return { nodes, edges };
  }

  // ── Legacy lineage fallback (unchanged logic, no step nodes) ─────────────────

  const lineageNodes: LineageNode[] = lineage.nodes ?? [];
  const lineageEdges = lineage.edges ?? [];

  const producerNodeIds = new Set(lineageNodes.map((ln) => ln.id));
  const outputTableNamesSet = new Set(outputTableNames);
  const allLegacyProduced = new Set(
    lineageEdges.filter((e) => producerNodeIds.has(e.source)).map((e) => e.dataset),
  );

  allLegacyProduced.forEach((ds) => {
    if (nodes.find((n) => n.id === `ds-${ds}`)) return;
    const isFinal = outputTableNamesSet.has(ds);
    const nodeId = `ds-${ds}`;
    nodes.push({
      id: nodeId,
      type: isFinal ? "output" : "intermediate",
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        kind: "dataset",
        label: ds,
        nodeType: (isFinal ? "output" : "intermediate") as "intermediate" | "output",
        isSelected: ds === selectedTable || nodeId === selectedNodeId,
        onDatasetClick: onTableSelect,
        onSelectNode,
        nodeId,
        producedBy: null,
        consumedBy: [],
      } satisfies DatasetNodeData,
    });
  });

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
        const edgeKey = `ds-${inp}→ds-${out}`;
        if (seenEdges.has(edgeKey)) return;
        seenEdges.add(edgeKey);
        edges.push({
          id: `e-${inp}-${out}`,
          source: `ds-${inp}`,
          target: `ds-${out}`,
          type: "smoothstep",
          style: { stroke: "#94a3b8", strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
        });
      });
    });
  });

  return { nodes, edges };
}

// ── Click info panel ──────────────────────────────────────────────────────────

interface ClickPanelProps {
  selectedNodeId: string | null;
  nodes: Node[];
}

function ClickPanel({ selectedNodeId, nodes }: ClickPanelProps): React.ReactElement {
  if (!selectedNodeId) {
    return (
      <div
        className="shrink-0 border-t border-border bg-muted/10 px-3 py-2 text-xs"
        style={{ minHeight: 100, display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <span className="text-muted-foreground">Click a table or step to see details</span>
      </div>
    );
  }

  const node = nodes.find((n) => n.id === selectedNodeId);
  if (!node) {
    return (
      <div
        className="shrink-0 border-t border-border bg-muted/10 px-3 py-2 text-xs"
        style={{ minHeight: 100, display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <span className="text-muted-foreground">Click a table or step to see details</span>
      </div>
    );
  }

  const d = node.data as FlowNodeData;

  if (d.kind === "step") {
    const s = d as StepNodeData;
    return (
      <div
        className="shrink-0 border-t border-border bg-muted/10 px-3 py-2 text-xs"
        style={{ minHeight: 100 }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
          <span style={{ fontWeight: 700, color: "var(--foreground)", fontSize: 13 }}>{s.name}</span>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: "#64748b",
              background: "#f1f5f9",
              border: "1px solid #e2e8f0",
              borderRadius: 4,
              padding: "1px 5px",
            }}
          >
            Step {s.stepIndex + 1}
          </span>
        </div>
        {s.description && (
          <div className="text-muted-foreground" style={{ marginBottom: 4 }}>{s.description}</div>
        )}
        <div style={{ display: "flex", gap: 20 }}>
          <div>
            <span className="text-muted-foreground">Inputs: </span>
            <span style={{ fontFamily: "ui-monospace, monospace" }}>
              {s.inputs.length > 0 ? s.inputs.join(", ") : "—"}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Outputs: </span>
            <span style={{ fontFamily: "ui-monospace, monospace" }}>
              {s.outputs.length > 0 ? s.outputs.join(", ") : "—"}
            </span>
          </div>
          {s.pythonFile && (
            <div>
              <span className="text-muted-foreground">Python file: </span>
              <span style={{ fontFamily: "ui-monospace, monospace" }}>{s.pythonFile}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Dataset node
  const ds = d as DatasetNodeData;
  const badgeColor = ds.nodeType === "output" ? "#10b981" : "#ca8a04";
  const badgeBg = ds.nodeType === "output" ? "#d1fae5" : "#fef9c3";
  const badgeBorder = ds.nodeType === "output" ? "#6ee7b7" : "#fcd34d";

  return (
    <div
      className="shrink-0 border-t border-border bg-muted/10 px-3 py-2 text-xs"
      style={{ minHeight: 100 }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
        <span
          style={{
            fontWeight: 700,
            fontFamily: "ui-monospace, monospace",
            color: "var(--foreground)",
            fontSize: 13,
          }}
        >
          {ds.label}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            color: badgeColor,
            background: badgeBg,
            border: `1px solid ${badgeBorder}`,
            borderRadius: 4,
            padding: "1px 5px",
          }}
        >
          {ds.nodeType}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div>
          <span className="text-muted-foreground">Produced by: </span>
          {ds.producedBy ? (
            <span>
              Step {ds.producedBy.stepIndex + 1} — {ds.producedBy.stepName}
            </span>
          ) : (
            <span className="text-muted-foreground">unknown</span>
          )}
        </div>
        <div>
          <span className="text-muted-foreground">Consumed by: </span>
          {ds.consumedBy.length > 0 ? (
            <span>
              {ds.consumedBy
                .map((ref) => `Step ${ref.stepIndex + 1} — ${ref.stepName}`)
                .join(", ")}
            </span>
          ) : (
            <span className="text-muted-foreground">Final output — not consumed by any step</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── DataFlowDiagramInner ──────────────────────────────────────────────────────

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
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const handleSelectNode = (id: string) => {
    setSelectedNodeId(id);
  };

  // Full rebuild when lineage changes
  useEffect(() => {
    const { nodes: rawNodes, edges: rawEdges } = buildNodesAndEdges(
      lineage,
      selectedTable,
      selectedNodeId,
      onTableSelect,
      handleSelectNode,
      outputTableNames,
    );
    if (rawNodes.length === 0) return;
    const laidOut = applyDagreLayout(rawNodes, rawEdges);
    setNodes(laidOut);
    setEdges(rawEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lineage]);

  // Sync isSelected flags without re-running layout
  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const d = n.data as FlowNodeData;
        if (d.kind === "dataset") {
          const ds = d as DatasetNodeData;
          return {
            ...n,
            data: {
              ...ds,
              isSelected: ds.label === selectedTable || n.id === selectedNodeId,
              onDatasetClick: onTableSelect,
              onSelectNode: handleSelectNode,
            },
          };
        }
        if (d.kind === "step") {
          const s = d as StepNodeData;
          return {
            ...n,
            data: {
              ...s,
              isSelected: n.id === selectedNodeId,
              onSelectNode: handleSelectNode,
            },
          };
        }
        return n;
      }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTable, selectedNodeId, onTableSelect]);

  const datasetNodes = nodes.filter((n) => {
    const d = n.data as FlowNodeData;
    return d.kind === "dataset";
  });
  const stepNodes = nodes.filter((n) => {
    const d = n.data as FlowNodeData;
    return d.kind === "step";
  });

  const intermediateCount = datasetNodes.filter((n) => {
    const d = n.data as DatasetNodeData;
    return d.nodeType === "intermediate";
  }).length;
  const finalCount = datasetNodes.filter((n) => {
    const d = n.data as DatasetNodeData;
    return d.nodeType === "output";
  }).length;

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
        <span className="font-medium" style={{ color: "#ca8a04" }}>
          {intermediateCount} intermediate
        </span>
        <span className="text-muted-foreground/40">·</span>
        <span className="font-medium text-emerald-600">{finalCount} output</span>
        {stepNodes.length > 0 && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span className="font-medium text-slate-500">{stepNodes.length} steps</span>
          </>
        )}
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
      <ClickPanel selectedNodeId={selectedNodeId} nodes={nodes} />
    </div>
  );
}

// ── DataFlowDiagramLoader ─────────────────────────────────────────────────────

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

// ── Default export ────────────────────────────────────────────────────────────

export default function DataFlowDiagram(props: DataFlowDiagramProps): React.ReactElement {
  return (
    <ReactFlowProvider>
      <DataFlowDiagramLoader {...props} />
    </ReactFlowProvider>
  );
}
