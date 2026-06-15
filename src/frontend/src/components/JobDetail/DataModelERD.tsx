import { useMemo, useState } from "react";
import { SchemaCanvas } from "@/components/SchemaCanvas";
import type { GraphNode } from "@/components/SchemaCanvas";
import type { TableNodeData } from "@/components/SchemaCanvas";
import { schemaResponseToCanvas } from "@/components/SchemaCanvas/schemaResponseToCanvas";
import type { JobSchemaResponse } from "@/api/types";

interface DataModelERDProps {
  schema: JobSchemaResponse;
  selectedTable: string | null;
  onTableSelect: (datasetName: string) => void;
}

function DataModelERDCanvas({ schema, selectedTable, onTableSelect }: DataModelERDProps) {
  const canvasData = useMemo(() => schemaResponseToCanvas(schema), [schema]);
  const [nodes, setNodes] = useState<GraphNode<TableNodeData>[]>(canvasData.nodes);
  const [localSelectedNode, setLocalSelectedNode] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [selectedField, setSelectedField] = useState<{ nodeId: string; columnName: string } | null>(
    null,
  );

  const selectedNodeId = localSelectedNode ?? selectedTable;

  function handleSelectNode(nodeId: string | null) {
    setLocalSelectedNode(nodeId);
    if (nodeId) onTableSelect(nodeId);
  }

  return (
    <div className="w-full h-full min-h-0 relative">
      <SchemaCanvas
        nodes={nodes}
        edges={canvasData.edges}
        setNodes={setNodes}
        selectedNodeId={selectedNodeId}
        selectedEdgeId={selectedEdgeId}
        selectedField={selectedField}
        onSelectNode={handleSelectNode}
        onSelectEdge={setSelectedEdgeId}
        onSelectField={setSelectedField}
      />
    </div>
  );
}

export default function DataModelERD({ schema, selectedTable, onTableSelect }: DataModelERDProps) {
  if (schema.tables.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        No tables found — run a migration to extract table metadata.
      </div>
    );
  }

  const schemaKey = schema.tables
    .map((t) => t.dataset_name)
    .sort()
    .join(",");

  return (
    <DataModelERDCanvas
      key={schemaKey}
      schema={schema}
      selectedTable={selectedTable}
      onTableSelect={onTableSelect}
    />
  );
}
