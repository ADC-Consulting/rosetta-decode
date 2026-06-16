import type { GraphNode } from "./graph-types";
import { parseColumnHandleId, type HandleSide } from "./handle-utils";
import {
  DATA_MODEL_NODE_BODY_PADDING_TOP,
  DATA_MODEL_NODE_HEADER_HEIGHT,
  DATA_MODEL_NODE_ROW_HEIGHT,
  DATA_MODEL_NODE_WIDTH,
  getDataModelNodeHeight,
} from "./layout-constants";
import type { TableNodeData } from "./types";

const PORT_SIDE_INSET = 8;
const DEFAULT_DROP_RADIUS = 24;

export type CanvasPoint = { x: number; y: number };

export type PortRef = {
  nodeId: string;
  columnName: string;
  side: HandleSide;
};

export function computeCanvasStageSize(
  nodes: GraphNode<TableNodeData>[],
  collapsedNodeIds: Set<string>,
): { width: number; height: number } {
  let maxX = 1200;
  let maxY = 760;
  for (const node of nodes) {
    maxX = Math.max(maxX, node.position.x + DATA_MODEL_NODE_WIDTH + 260);
    maxY = Math.max(maxY, node.position.y + getNodeHeight(node, collapsedNodeIds.has(node.id)) + 220);
  }
  return { width: maxX, height: maxY };
}

export function getNodeHeight(node: GraphNode<TableNodeData>, collapsed = false): number {
  if (collapsed) {
    return DATA_MODEL_NODE_HEADER_HEIGHT;
  }
  return getDataModelNodeHeight(node.data.columns.length);
}

export function getColumnCenterY(node: GraphNode<TableNodeData>, columnName: string): number {
  const index = Math.max(
    0,
    node.data.columns.findIndex((column) => column.name === columnName),
  );
  return node.position.y
    + DATA_MODEL_NODE_HEADER_HEIGHT
    + DATA_MODEL_NODE_BODY_PADDING_TOP
    + index * DATA_MODEL_NODE_ROW_HEIGHT
    + DATA_MODEL_NODE_ROW_HEIGHT / 2;
}

export function getColumnPortPoint(
  node: GraphNode<TableNodeData>,
  columnName: string,
  side: HandleSide,
): CanvasPoint {
  const y = getColumnCenterY(node, columnName);
  const x = side === "handle-left"
    ? node.position.x + PORT_SIDE_INSET
    : node.position.x + DATA_MODEL_NODE_WIDTH - PORT_SIDE_INSET;
  return { x, y };
}

export function getEdgeHandlePoint(
  node: GraphNode<TableNodeData>,
  handleId: string | null | undefined,
  role: "source" | "target",
  fallbackColumn?: string | null,
  collapsed = false,
): CanvasPoint {
  if (collapsed) {
    const parsed = parseColumnHandleId(handleId);
    const side = parsed?.side ?? (role === "source" ? "handle-right" : "handle-left");
    return {
      x: side === "handle-left"
        ? node.position.x + PORT_SIDE_INSET
        : node.position.x + DATA_MODEL_NODE_WIDTH - PORT_SIDE_INSET,
      y: node.position.y + DATA_MODEL_NODE_HEADER_HEIGHT / 2,
    };
  }
  const parsed = parseColumnHandleId(handleId);
  if (parsed) {
    return getColumnPortPoint(node, parsed.columnName, parsed.side);
  }
  if (fallbackColumn) {
    return getColumnPortPoint(node, fallbackColumn, role === "source" ? "handle-right" : "handle-left");
  }
  return {
    x: role === "source" ? node.position.x + DATA_MODEL_NODE_WIDTH - PORT_SIDE_INSET : node.position.x + PORT_SIDE_INSET,
    y: node.position.y + getNodeHeight(node) / 2,
  };
}

export function parseColumnFromHandle(handleId: string | null | undefined): string | null {
  return parseColumnHandleId(handleId)?.columnName ?? null;
}

export function pathFromPoints(x1: number, y1: number, x2: number, y2: number): string {
  const dx = Math.abs(x2 - x1);
  const dy = Math.abs(y2 - y1);
  const distance = Math.sqrt(dx * dx + dy * dy);
  const bend = Math.max(60, Math.min(250, distance * 0.4));
  const direction = x2 >= x1 ? 1 : -1;
  const c1x = x1 + bend * direction;
  const c2x = x2 - bend * direction;
  return `M ${x1} ${y1} C ${c1x} ${y1}, ${c2x} ${y2}, ${x2} ${y2}`;
}

export function findClosestColumnPort(
  nodes: GraphNode<TableNodeData>[],
  point: CanvasPoint,
  role: "source" | "target" | "either",
  zoom = 1,
  collapsedNodeIds?: Set<string>,
  dropRadius = DEFAULT_DROP_RADIUS,
): PortRef | null {
  const candidateSides: HandleSide[] =
    role === "source" ? ["handle-right"] : role === "target" ? ["handle-left"] : ["handle-left", "handle-right"];
  const effectiveDropRadius = dropRadius / zoom;
  let best: (PortRef & { distance: number }) | null = null;

  for (const node of nodes) {
    if (collapsedNodeIds?.has(node.id)) {
      continue;
    }
    for (const column of node.data.columns) {
      for (const side of candidateSides) {
        const handlePoint = getColumnPortPoint(node, column.name, side);
        const distance = Math.hypot(point.x - handlePoint.x, point.y - handlePoint.y);
        if (distance > effectiveDropRadius) {
          continue;
        }
        if (!best || distance < best.distance) {
          best = {
            nodeId: node.id,
            columnName: column.name,
            side,
            distance,
          };
        }
      }
    }
  }

  return best
    ? {
      nodeId: best.nodeId,
      columnName: best.columnName,
      side: best.side,
    }
    : null;
}
