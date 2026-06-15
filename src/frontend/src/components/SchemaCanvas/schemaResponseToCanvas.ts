import { GraphNode, GraphEdge } from "./graph-types";
import { TableNodeData, CanvasColumn, CanvasEdgeData } from "./types";
import {
  DATA_MODEL_LAYOUT_BASE_X,
  DATA_MODEL_LAYOUT_BASE_Y,
  DATA_MODEL_LAYOUT_COLUMN_GAP,
  DATA_MODEL_LAYOUT_GRID_COLS,
  DATA_MODEL_LAYOUT_VERTICAL_GAP,
  getDataModelNodeHeight,
} from "./layout-constants";
import { JobSchemaResponse, ColumnSchema } from "../../api/types";

export type CanvasData = {
  nodes: GraphNode<TableNodeData>[];
  edges: GraphEdge<CanvasEdgeData>[];
};

function mapColumn(col: ColumnSchema): CanvasColumn {
  return {
    name: col.name,
    type: col.sql_type ?? col.semantic_type ?? "TEXT",
    nullable: true,
    isPrimaryKey: col.is_pk,
    isForeignKey: col.is_fk,
  };
}

export function schemaResponseToCanvas(schema: JobSchemaResponse): CanvasData {
  const { tables, relationships } = schema;

  const rowHeights: number[] = [];
  for (let i = 0; i < tables.length; i++) {
    const row = Math.floor(i / DATA_MODEL_LAYOUT_GRID_COLS);
    const table = tables[i];
    const displayCols =
      table.target_columns.length > 0 ? table.target_columns : table.columns;
    const h = getDataModelNodeHeight(displayCols.length);
    rowHeights[row] = Math.max(rowHeights[row] ?? 0, h);
  }

  const maxRow = rowHeights.length;
  const cumYOffset: number[] = new Array(Math.max(maxRow, 1)).fill(0);
  cumYOffset[0] = DATA_MODEL_LAYOUT_BASE_Y;
  for (let r = 1; r < maxRow; r++) {
    cumYOffset[r] = cumYOffset[r - 1] + rowHeights[r - 1] + DATA_MODEL_LAYOUT_VERTICAL_GAP;
  }

  const nodes: GraphNode<TableNodeData>[] = [];
  const nodeIds = new Set<string>();

  for (let i = 0; i < tables.length; i++) {
    const table = tables[i];
    const col = i % DATA_MODEL_LAYOUT_GRID_COLS;
    const row = Math.floor(i / DATA_MODEL_LAYOUT_GRID_COLS);

    const displayCols: ColumnSchema[] =
      table.target_columns.length > 0 ? table.target_columns : table.columns;

    const id = table.dataset_name;
    nodeIds.add(id);

    nodes.push({
      id,
      position: {
        x: DATA_MODEL_LAYOUT_BASE_X + col * DATA_MODEL_LAYOUT_COLUMN_GAP,
        y: cumYOffset[row],
      },
      data: {
        label: table.dataset_name,
        columns: displayCols.map(mapColumn),
        primary_key: displayCols.filter((c) => c.is_pk).map((c) => c.name),
      },
    });
  }

  const edges: GraphEdge<CanvasEdgeData>[] = [];
  const seenEdgeKeys = new Set<string>();
  let edgeCount = 0;

  for (const rel of relationships) {
    if (!nodeIds.has(rel.left_table) || !nodeIds.has(rel.right_table)) {
      continue;
    }
    const fromColumn = rel.key_column.toLowerCase();
    const toColumn = rel.key_column.toLowerCase();
    const key = `${rel.left_table}:${fromColumn}→${rel.right_table}:${toColumn}`;
    if (seenEdgeKeys.has(key)) continue;
    seenEdgeKeys.add(key);

    edges.push({
      id: `edge-${edgeCount++}`,
      source: rel.left_table,
      target: rel.right_table,
      sourceHandle: `col:${fromColumn}:right`,
      targetHandle: `col:${toColumn}:left`,
      data: {
        description: rel.relationship_type,
        fromColumn,
        toColumn,
        relationType: "relation",
      },
    });
  }

  for (const table of tables) {
    const displayCols: ColumnSchema[] =
      table.target_columns.length > 0 ? table.target_columns : table.columns;

    for (const col of displayCols) {
      if (!col.fk_ref) continue;
      const dotIndex = col.fk_ref.indexOf(".");
      if (dotIndex === -1) continue;
      const targetTable = col.fk_ref.slice(0, dotIndex);
      const targetCol = col.fk_ref.slice(dotIndex + 1);

      if (!nodeIds.has(targetTable)) continue;

      const key = `${table.dataset_name}:${col.name}→${targetTable}:${targetCol}`;
      if (seenEdgeKeys.has(key)) continue;
      seenEdgeKeys.add(key);

      edges.push({
        id: `edge-${edgeCount++}`,
        source: table.dataset_name,
        target: targetTable,
        sourceHandle: `col:${col.name}:right`,
        targetHandle: `col:${targetCol}:left`,
        data: {
          description: "fk",
          fromColumn: col.name,
          toColumn: targetCol,
          relationType: "fk",
        },
      });
    }
  }

  return { nodes, edges };
}
