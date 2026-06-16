import type { GraphEdge } from "./graph-types";
import type { CanvasEdgeData } from "./types";

export type FocusContext = {
  selectedNodeId: string;
  upstreamNodes: Set<string>;
  downstreamNodes: Set<string>;
  upstreamEdgeIds: Set<string>;
  downstreamEdgeIds: Set<string>;
};

export type NodeFocusRole = "selected" | "upstream" | "downstream" | "dim" | "none";
export type EdgeFocusRole = "upstream" | "downstream" | "dim" | "none";

export function buildFocusContext(
  selectedNodeId: string | null,
  edges: GraphEdge<CanvasEdgeData>[],
): FocusContext | null {
  if (!selectedNodeId) {
    return null;
  }

  const outgoing = new Map<string, GraphEdge<CanvasEdgeData>[]>();
  const incoming = new Map<string, GraphEdge<CanvasEdgeData>[]>();
  for (const edge of edges) {
    const outbound = outgoing.get(edge.source);
    if (outbound) {
      outbound.push(edge);
    } else {
      outgoing.set(edge.source, [edge]);
    }
    const inbound = incoming.get(edge.target);
    if (inbound) {
      inbound.push(edge);
    } else {
      incoming.set(edge.target, [edge]);
    }
  }

  const downstreamNodes = new Set<string>();
  const upstreamNodes = new Set<string>();
  const downstreamEdgeIds = new Set<string>();
  const upstreamEdgeIds = new Set<string>();

  const downstreamQueue = [selectedNodeId];
  const seenDownstream = new Set<string>([selectedNodeId]);
  while (downstreamQueue.length > 0) {
    const current = downstreamQueue.shift();
    if (!current) {
      continue;
    }
    for (const edge of outgoing.get(current) ?? []) {
      downstreamEdgeIds.add(edge.id);
      if (!seenDownstream.has(edge.target)) {
        seenDownstream.add(edge.target);
        downstreamNodes.add(edge.target);
        downstreamQueue.push(edge.target);
      }
    }
  }

  const upstreamQueue = [selectedNodeId];
  const seenUpstream = new Set<string>([selectedNodeId]);
  while (upstreamQueue.length > 0) {
    const current = upstreamQueue.shift();
    if (!current) {
      continue;
    }
    for (const edge of incoming.get(current) ?? []) {
      upstreamEdgeIds.add(edge.id);
      if (!seenUpstream.has(edge.source)) {
        seenUpstream.add(edge.source);
        upstreamNodes.add(edge.source);
        upstreamQueue.push(edge.source);
      }
    }
  }

  downstreamNodes.delete(selectedNodeId);
  upstreamNodes.delete(selectedNodeId);

  return {
    selectedNodeId,
    upstreamNodes,
    downstreamNodes,
    upstreamEdgeIds,
    downstreamEdgeIds,
  };
}

export function getNodeFocusRole(nodeId: string, focusContext: FocusContext): NodeFocusRole {
  if (nodeId === focusContext.selectedNodeId) {
    return "selected";
  }
  if (focusContext.upstreamNodes.has(nodeId)) {
    return "upstream";
  }
  if (focusContext.downstreamNodes.has(nodeId)) {
    return "downstream";
  }
  return "dim";
}

export function getEdgeFocusRole(edgeId: string, focusContext: FocusContext): EdgeFocusRole {
  if (focusContext.downstreamEdgeIds.has(edgeId)) {
    return "downstream";
  }
  if (focusContext.upstreamEdgeIds.has(edgeId)) {
    return "upstream";
  }
  return "dim";
}
