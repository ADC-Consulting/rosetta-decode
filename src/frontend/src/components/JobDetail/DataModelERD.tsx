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

function DataModelERDCanvas({
  schema,
  selectedTable,
  onTableSelect,
}: DataModelERDProps) {
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
    <div className="w-full h-full min-h-0 flex flex-col">
      <div className="shrink-0 flex items-center gap-2 px-3 py-1.5 border-b border-border text-xs text-muted-foreground bg-muted/10">
        <span className="font-medium text-foreground">
          {nodes.length} output {nodes.length === 1 ? "table" : "tables"}
        </span>
        {canvasData.edges.length > 0 && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span>
              {canvasData.edges.length} inferred {canvasData.edges.length === 1 ? "relationship" : "relationships"} — lines connect tables that share a column name
            </span>
          </>
        )}
      </div>
      <div className="flex-1 min-h-0 relative">
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
    </div>
  );
}

export default function DataModelERD({ schema, selectedTable, onTableSelect }: DataModelERDProps) {
  const outputTables = schema.tables.filter((t) => t.libname === null);

  if (outputTables.length === 0) {
    const message =
      schema.tables.length === 0
        ? "No tables found — run a migration to extract table metadata."
        : "No output tables yet — run the migration to see the output schema.";
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        {message}
      </div>
    );
  }

  const filteredSchema = { ...schema, tables: outputTables };
  const schemaKey = outputTables.map((t) => t.dataset_name).sort().join(",");

  return (
    <DataModelERDCanvas
      key={schemaKey}
      schema={filteredSchema}
      selectedTable={selectedTable}
      onTableSelect={onTableSelect}
    />
  );
}
