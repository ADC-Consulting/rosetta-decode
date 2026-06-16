import type { BlockPlan, JobLineageResponse, TrustReportFile } from "@/api/types";
import {
  FileNodeCard,
  type FileNodeData,
} from "@/components/JobDetail/FileNodeCard";
import {
  pyFileToSasFiles,
  sasFileToPyFile,
} from "@/lib/sas-python-file-map";
import dagre from "dagre";
import { useMemo } from "react";
import {
  Background,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TargetGraphProps {
  lineage: JobLineageResponse;
  generatedFiles: Record<string, string>;
  blockPlans: BlockPlan[];
  trustFiles?: TrustReportFile[];
  onFileClick: (sasSourceFiles: string[]) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NODE_FILE_W = 220;
const NODE_FILE_H = 96;

// CRITICAL: module-level, never inside a component
const NODE_TYPES = { fileNode: FileNodeCard };

// ---------------------------------------------------------------------------
// Layout helper
// ---------------------------------------------------------------------------

function layoutNodes(
  nodes: Node<FileNodeData>[],
  edges: Edge[],
  nodeW: number,
  nodeH: number,
): Node<FileNodeData>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 75, ranksep: 160, marginx: 20, marginy: 20 });
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
// Status aggregation
// ---------------------------------------------------------------------------

function aggregateStatus(
  pyFile: string,
  blockPlans: BlockPlan[],
  trustFiles: TrustReportFile[] | undefined,
): FileNodeData["status"] {
  if (!trustFiles || trustFiles.length === 0) return null;

  const sasFiles = pyFileToSasFiles(pyFile, blockPlans);
  if (sasFiles.length === 0) return null;

  const matchingEntries = sasFiles
    .map((sf) => trustFiles.find((tf) => tf.source_file === sf))
    .filter((tf): tf is TrustReportFile => tf !== undefined);

  if (matchingEntries.length === 0) return null;

  if (matchingEntries.some((tf) => tf.failed_reconciliation > 0)) {
    return "UNRECOGNIZED";
  }
  if (matchingEntries.some((tf) => tf.needs_review > 0 || tf.manual_todo > 0)) {
    return "ERROR_PRONE";
  }
  return "OK";
}

// ---------------------------------------------------------------------------
// Inner component
// ---------------------------------------------------------------------------

function TargetGraphInner({
  lineage,
  generatedFiles,
  blockPlans,
  trustFiles,
  onFileClick,
}: TargetGraphProps): React.ReactElement {
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(() => {
    const pyFiles = Object.keys(generatedFiles).filter((f) => f !== "pipeline.py");

    if (pyFiles.length === 0) {
      return { nodes: [], edges: [] };
    }

    // Build edges first so we can compute connection counts per node
    const nodeIds = new Set(pyFiles);
    const seenEdges = new Set<string>();
    const rawEdges: Edge[] = [];

    for (const fe of lineage.file_edges ?? []) {
      const src = sasFileToPyFile(fe.source_file);
      const tgt = sasFileToPyFile(fe.target_file);
      if (src === "pipeline.py" || tgt === "pipeline.py") continue;
      if (!nodeIds.has(src) || !nodeIds.has(tgt)) continue;
      if (src === tgt) continue;
      const key = `${src}||${tgt}`;
      if (seenEdges.has(key)) continue;
      seenEdges.add(key);
      rawEdges.push({
        id: `te-${src}-${tgt}`,
        source: src,
        target: tgt,
        type: "smoothstep",
        markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
        style: { stroke: "#94a3b8", strokeWidth: 1.5 },
      });
    }

    // Count edge connections per node id
    const connectionCount = new Map<string, number>();
    for (const e of rawEdges) {
      connectionCount.set(e.source, (connectionCount.get(e.source) ?? 0) + 1);
      connectionCount.set(e.target, (connectionCount.get(e.target) ?? 0) + 1);
    }

    // Build nodes
    const rawNodes: Node<FileNodeData>[] = pyFiles.map((pyFile) => {
      const stem = pyFile.endsWith(".py") ? pyFile.slice(0, -3) : pyFile;

      const blockCount = blockPlans.filter(
        (bp) => sasFileToPyFile(bp.source_file) === pyFile,
      ).length;

      return {
        id: pyFile,
        type: "fileNode",
        position: { x: 0, y: 0 },
        data: {
          filename: stem,
          fullPath: pyFile,
          file_type: "PROGRAM",
          status: aggregateStatus(pyFile, blockPlans, trustFiles),
          blockCount,
          connectionCount: connectionCount.get(pyFile) ?? 0,
          isSelected: false,
        },
      };
    });

    const laid = layoutNodes(rawNodes, rawEdges, NODE_FILE_W, NODE_FILE_H);
    return { nodes: laid, edges: rawEdges };
  }, [lineage, generatedFiles, blockPlans, trustFiles]);

  const [nodes, , onNodesChange] = useNodesState<FileNodeData>(layoutedNodes);
  const [edges, , onEdgesChange] = useEdgesState(layoutedEdges);

  if (layoutedNodes.length === 0) {
    return (
      <div className="flex items-center justify-center w-full h-full text-sm text-muted-foreground">
        No Python modules generated for this job.
      </div>
    );
  }

  return (
    <div className="relative w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        onNodeClick={(_evt, node) => {
          const sasFiles = pyFileToSasFiles(node.id, blockPlans);
          if (sasFiles.length > 0) onFileClick(sasFiles);
        }}
      >
        <Controls />
        <Background />
      </ReactFlow>

      {/* Legend */}
      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: 12,
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
        <div
          style={{
            fontSize: 9,
            fontWeight: 700,
            color: "#94a3b8",
            letterSpacing: "0.07em",
            textTransform: "uppercase",
            marginBottom: 2,
          }}
        >
          Python modules
        </div>
        {(
          [
            { color: "#22c55e", label: "All migrated" },
            { color: "#f59e0b", label: "Needs review" },
            { color: "#ef4444", label: "Has failures" },
          ] as const
        ).map(({ color, label }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: color,
                flexShrink: 0,
              }}
            />
            <span style={{ fontSize: 11, color: "#444", fontWeight: 500 }}>{label}</span>
          </div>
        ))}
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
