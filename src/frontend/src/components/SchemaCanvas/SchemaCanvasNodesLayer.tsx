import type { MouseEvent as ReactMouseEvent } from "react";

import type { GraphNode } from "./graph-types";
import { DATA_MODEL_NODE_WIDTH } from "./layout-constants";
import { getNodeFocusRole, type FocusContext } from "./schema-canvas-focus";
import { getNodeHeight } from "./schema-canvas-geometry";
import type { TableNodeData } from "./types";

type SelectedField = { nodeId: string; columnName: string } | null;

type SchemaCanvasNodesLayerProps = {
  nodes: GraphNode<TableNodeData>[];
  selectedNodeId: string | null;
  selectedField: SelectedField;
  collapsedNodeIds: Set<string>;
  focusContext: FocusContext | null;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onSelectField: (field: SelectedField) => void;
  onToggleNodeCollapsed: (nodeId: string) => void;
  onStartNodeDrag: (event: ReactMouseEvent<HTMLDivElement>, node: GraphNode<TableNodeData>) => void;
};

export function SchemaCanvasNodesLayer({
  nodes,
  selectedNodeId,
  selectedField,
  collapsedNodeIds,
  focusContext,
  onSelectNode,
  onSelectEdge,
  onSelectField,
  onToggleNodeCollapsed,
  onStartNodeDrag,
}: SchemaCanvasNodesLayerProps) {
  return (
    <>
      {nodes.map((node) => {
        const selected = selectedNodeId === node.id;
        const collapsed = collapsedNodeIds.has(node.id);
        const nodeHeight = getNodeHeight(node, collapsed);
        const focusRole = focusContext ? getNodeFocusRole(node.id, focusContext) : "none";
        const nodeClassName = [
          "table-node",
          selected ? "table-node-selected" : "",
          collapsed ? "table-node-collapsed" : "",
          focusRole === "selected" ? "table-node-focus-selected" : "",
          focusRole === "upstream" ? "table-node-focus-upstream" : "",
          focusRole === "downstream" ? "table-node-focus-downstream" : "",
          focusRole === "dim" ? "table-node-dim" : "",
        ]
          .filter(Boolean)
          .join(" ");

        return (
          <div
            key={node.id}
            className={nodeClassName}
            style={{
              width: DATA_MODEL_NODE_WIDTH,
              left: node.position.x,
              top: node.position.y,
              height: nodeHeight,
            }}
            onMouseDown={(event) => {
              event.stopPropagation();
              onSelectNode(node.id);
              onSelectEdge(null);
              onSelectField(null);
            }}
          >
            <div
              className="table-node-title table-node-drag-handle"
              onMouseDown={(event) => {
                event.stopPropagation();
                onSelectNode(node.id);
                onSelectEdge(null);
                onSelectField(null);
                onStartNodeDrag(event, node);
              }}
            >
              <div className="table-node-title-main">
                <span className="table-node-title-text">{node.data.label}</span>
              </div>
              <button
                type="button"
                className="table-node-collapse-btn"
                onMouseDown={(event) => {
                  event.stopPropagation();
                }}
                onClick={(event) => {
                  event.stopPropagation();
                  onToggleNodeCollapsed(node.id);
                }}
              >
                {collapsed ? "expand" : "collapse"}
              </button>
            </div>
            {!collapsed ? (
              <ul className="table-node-columns">
                {node.data.columns.map((column) => {
                  const fieldSelected =
                    selectedField?.nodeId === node.id && selectedField?.columnName === column.name;
                  return (
                    <li
                      key={`${node.id}_${column.name}`}
                      className={`table-node-column-row ${fieldSelected ? "table-node-column-row-selected" : ""}`}
                      onMouseDown={(event) => {
                        event.stopPropagation();
                        onSelectNode(node.id);
                        onSelectEdge(null);
                        onSelectField({ nodeId: node.id, columnName: column.name });
                      }}
                    >
                      <span className="col-name">{column.name}</span>
                      <span className="col-type">{column.type}</span>
                      <span className="col-flags" style={{ display: "flex", gap: 2, alignItems: "center" }}>
                        {column.isPrimaryKey && (
                          <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 3, padding: "1px 4px", fontSize: 10, fontWeight: 600, background: "#fef9c3", color: "#854d0e" }}>PK</span>
                        )}
                        {column.isForeignKey && (
                          <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 3, padding: "1px 4px", fontSize: 10, fontWeight: 600, background: "#dbeafe", color: "#1e40af" }}>FK</span>
                        )}
                        {column.isUnique && !column.isPrimaryKey && (
                          <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 3, padding: "1px 4px", fontSize: 10, fontWeight: 600, background: "#f3e8ff", color: "#6b21a8" }}>UQ</span>
                        )}
                        {!column.nullable && !column.isPrimaryKey && (
                          <span style={{ display: "inline-flex", alignItems: "center", borderRadius: 3, padding: "1px 4px", fontSize: 10, fontWeight: 600, background: "#f1f5f9", color: "#475569" }}>NN</span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div className="table-node-collapsed-summary">{node.data.columns.length} fields</div>
            )}
          </div>
        );
      })}
    </>
  );
}
