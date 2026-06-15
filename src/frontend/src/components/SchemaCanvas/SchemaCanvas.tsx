/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";

import { SchemaCanvasNodesLayer } from "./SchemaCanvasNodesLayer";
import type { GraphEdge, GraphNode } from "./graph-types";
import {
  buildFocusContext,
  getEdgeFocusRole,
} from "./schema-canvas-focus";
import {
  computeCanvasStageSize,
  getEdgeHandlePoint,
  pathFromPoints,
} from "./schema-canvas-geometry";
import type { CanvasEdgeData, TableNodeData } from "./types";

import "./schema-canvas.css";

type SchemaCanvasProps = {
  nodes: GraphNode<TableNodeData>[];
  edges: GraphEdge<CanvasEdgeData>[];
  setNodes: (nodes: GraphNode<TableNodeData>[]) => void;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  selectedField: { nodeId: string; columnName: string } | null;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onSelectField: (field: { nodeId: string; columnName: string } | null) => void;
};

type NodeDragState = {
  nodeId: string;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
};

const MIN_ZOOM = 0.55;
const MAX_ZOOM = 2.2;
const ZOOM_SENSITIVITY = 0.0015;

export function SchemaCanvas({
  nodes,
  edges,
  setNodes,
  selectedNodeId,
  selectedEdgeId,
  selectedField,
  onSelectNode,
  onSelectEdge,
  onSelectField,
}: SchemaCanvasProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [nodeDrag, setNodeDrag] = useState<NodeDragState | null>(null);
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);

  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const stageSize = useMemo(() => computeCanvasStageSize(nodes, collapsedNodeIds), [nodes, collapsedNodeIds]);
  const focusContext = useMemo(() => buildFocusContext(selectedNodeId, edges), [selectedNodeId, edges]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    if (vw === 0 || vh === 0) return;
    const fz = Math.min(vw / stageSize.width, vh / stageSize.height, 1) * 0.9;
    setZoom(Math.max(fz, MIN_ZOOM));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function startNodeDrag(event: ReactMouseEvent<HTMLDivElement>, node: GraphNode<TableNodeData>) {
    event.stopPropagation();
    onSelectNode(node.id);
    onSelectEdge(null);
    onSelectField(null);
    const point = toCanvasPoint(event, viewportRef.current, zoom);
    setNodeDrag({
      nodeId: node.id,
      startX: point.x,
      startY: point.y,
      originX: node.position.x,
      originY: node.position.y,
    });
  }

  function toggleNodeCollapsed(nodeId: string) {
    setCollapsedNodeIds((previous) => {
      const next = new Set(previous);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
    if (selectedField?.nodeId === nodeId) {
      onSelectField(null);
    }
  }

  useEffect(() => {
    const nodeIdSet = new Set(nodes.map((node) => node.id));
    setCollapsedNodeIds((previous) => {
      const next = new Set<string>();
      for (const nodeId of previous) {
        if (nodeIdSet.has(nodeId)) {
          next.add(nodeId);
        }
      }
      if (next.size === previous.size) {
        return previous;
      }
      return next;
    });
  }, [nodes]);

  useEffect(() => {
    const preventBrowserZoom = (event: WheelEvent) => {
      if (!event.metaKey && !event.ctrlKey) {
        return;
      }

      const viewport = viewportRef.current;
      if (!viewport) {
        return;
      }
      const studioSurface = viewport.closest(".panel-canvas-single");

      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (studioSurface) {
        if (!studioSurface.contains(target)) {
          return;
        }
      } else if (!viewport.contains(target)) {
        return;
      }

      event.preventDefault();
    };

    // Use a native capture listener so cmd/ctrl + wheel inside the canvas never triggers browser page zoom.
    window.addEventListener("wheel", preventBrowserZoom, { capture: true, passive: false });
    return () => {
      window.removeEventListener("wheel", preventBrowserZoom, { capture: true });
    };
  }, []);

  useEffect(() => {
    function onMouseMove(event: MouseEvent) {
      if (nodeDrag) {
        const point = toCanvasPoint(event, viewportRef.current, zoom);
        const deltaX = point.x - nodeDrag.startX;
        const deltaY = point.y - nodeDrag.startY;
        setNodes(
          nodes.map((node) =>
            node.id === nodeDrag.nodeId
              ? {
                ...node,
                position: {
                  x: Math.max(20, Math.round(nodeDrag.originX + deltaX)),
                  y: Math.max(20, Math.round(nodeDrag.originY + deltaY)),
                },
              }
              : node,
          ),
        );
      }
    }

    function onMouseUp() {
      if (nodeDrag) {
        setNodeDrag(null);
      }
    }

    if (!nodeDrag) {
      return;
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [nodeDrag, nodes, setNodes, zoom]);

  return (
    <div
      ref={viewportRef}
      className={`rosetta-schema-canvas canvas-shell ${focusContext ? "canvas-shell-has-focus" : ""}`}
      onWheel={(event) => {
        const viewport = viewportRef.current;
        if (!viewport) {
          return;
        }

        if (!event.metaKey && !event.ctrlKey) {
          const shiftHorizontal = event.shiftKey && Math.abs(event.deltaX) < 0.001;
          const horizontalDelta = shiftHorizontal ? event.deltaY : event.deltaX;
          const verticalDelta = shiftHorizontal ? 0 : event.deltaY;
          if (Math.abs(horizontalDelta) < 0.001 && Math.abs(verticalDelta) < 0.001) {
            return;
          }
          event.preventDefault();
          viewport.scrollLeft += horizontalDelta;
          viewport.scrollTop += verticalDelta;
          return;
        }

        event.preventDefault();
        const oldZoom = zoom;
        const scaleFactor = Math.exp(-event.deltaY * ZOOM_SENSITIVITY);
        const nextZoom = clamp(oldZoom * scaleFactor, MIN_ZOOM, MAX_ZOOM);
        if (Math.abs(nextZoom - oldZoom) < 0.0001) {
          return;
        }

        const rect = viewport.getBoundingClientRect();
        const pointerX = event.clientX - rect.left;
        const pointerY = event.clientY - rect.top;
        const worldX = (viewport.scrollLeft + pointerX) / oldZoom;
        const worldY = (viewport.scrollTop + pointerY) / oldZoom;

        setZoom(nextZoom);
        requestAnimationFrame(() => {
          const current = viewportRef.current;
          if (!current) {
            return;
          }
          current.scrollLeft = worldX * nextZoom - pointerX;
          current.scrollTop = worldY * nextZoom - pointerY;
        });
      }}
      onMouseDown={() => {
        onSelectNode(null);
        onSelectEdge(null);
        onSelectField(null);
      }}
    >
      <div className="canvas-zoom-layer" style={{ width: stageSize.width * zoom, height: stageSize.height * zoom }}>
        <div
          className="canvas-stage"
          style={{
            width: stageSize.width,
            height: stageSize.height,
            transform: `scale(${zoom})`,
            transformOrigin: "top left",
          }}
        >
          <svg className="canvas-links" width={stageSize.width} height={stageSize.height}>
            <defs>
              <marker id="canvas-arrow" markerWidth="10" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,1 L8,4 L0,7 z" fill="color-mix(in srgb, var(--text-secondary) 42%, transparent)" />
              </marker>
              <marker id="canvas-arrow-selected" markerWidth="10" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,1 L8,4 L0,7 z" fill="var(--brand-primary)" />
              </marker>
              <marker id="canvas-arrow-upstream" markerWidth="10" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,1 L8,4 L0,7 z" fill="var(--brand-primary-hover)" />
              </marker>
              <marker id="canvas-arrow-downstream" markerWidth="10" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,1 L8,4 L0,7 z" fill="var(--brand-primary)" />
              </marker>
              <marker id="canvas-arrow-muted" markerWidth="10" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,1 L8,4 L0,7 z" fill="color-mix(in srgb, var(--text-primary) 10%, transparent)" />
              </marker>
            </defs>
            {edges.map((edge) => {
              const sourceNode = nodeById.get(edge.source);
              const targetNode = nodeById.get(edge.target);
              if (!sourceNode || !targetNode) {
                return null;
              }

              const sourcePoint = getEdgeHandlePoint(
                sourceNode,
                edge.sourceHandle,
                "source",
                edge.data?.fromColumn,
                collapsedNodeIds.has(sourceNode.id),
              );
              const targetPoint = getEdgeHandlePoint(
                targetNode,
                edge.targetHandle,
                "target",
                edge.data?.toColumn,
                collapsedNodeIds.has(targetNode.id),
              );
              const path = pathFromPoints(sourcePoint.x, sourcePoint.y, targetPoint.x, targetPoint.y);
              const selected = selectedEdgeId === edge.id;
              const edgeFocusRole = focusContext ? getEdgeFocusRole(edge.id, focusContext) : "none";
              const lineClassName = [
                "canvas-link",
                selected ? "canvas-link-selected" : "",
                !selected && edgeFocusRole === "upstream" ? "canvas-link-focus-upstream" : "",
                !selected && edgeFocusRole === "downstream" ? "canvas-link-focus-downstream" : "",
                !selected && edgeFocusRole === "dim" ? "canvas-link-dim" : "",
              ]
                .filter(Boolean)
                .join(" ");
              const labelClassName = [
                "canvas-link-label",
                edgeFocusRole === "upstream" ? "canvas-link-label-upstream" : "",
                edgeFocusRole === "downstream" ? "canvas-link-label-downstream" : "",
                edgeFocusRole === "dim" ? "canvas-link-label-dim" : "",
              ]
                .filter(Boolean)
                .join(" ");
              const markerEnd = selected
                ? "url(#canvas-arrow-selected)"
                : edgeFocusRole === "upstream"
                  ? "url(#canvas-arrow-upstream)"
                  : edgeFocusRole === "downstream"
                    ? "url(#canvas-arrow-downstream)"
                    : edgeFocusRole === "dim"
                      ? "url(#canvas-arrow-muted)"
                      : "url(#canvas-arrow)";

              return (
                <g key={edge.id}>
                  <path
                    d={path}
                    className={lineClassName}
                    markerEnd={markerEnd}
                  />
                  <path
                    d={path}
                    className="canvas-link-hitbox"
                    onMouseDown={(event) => {
                      event.stopPropagation();
                      onSelectEdge(edge.id);
                      onSelectNode(null);
                      onSelectField(null);
                    }}
                  />
                  <text
                    x={(sourcePoint.x + targetPoint.x) / 2}
                    y={(sourcePoint.y + targetPoint.y) / 2 - 10}
                    className={labelClassName}
                    textAnchor="middle"
                    onMouseDown={(event) => {
                      event.stopPropagation();
                      onSelectEdge(edge.id);
                      onSelectNode(null);
                      onSelectField(null);
                    }}
                  >
                    {edge.data?.description ?? (typeof edge.label === "string" ? edge.label : "related_to")}
                  </text>
                </g>
              );
            })}
          </svg>

          <SchemaCanvasNodesLayer
            nodes={nodes}
            selectedNodeId={selectedNodeId}
            selectedField={selectedField}
            collapsedNodeIds={collapsedNodeIds}
            focusContext={focusContext}
            onSelectNode={onSelectNode}
            onSelectEdge={onSelectEdge}
            onSelectField={onSelectField}
            onToggleNodeCollapsed={toggleNodeCollapsed}
            onStartNodeDrag={startNodeDrag}
          />
        </div>
      </div>
    </div>
  );
}

function toCanvasPoint(
  event: { clientX: number; clientY: number },
  viewport: HTMLDivElement | null,
  zoom = 1,
): { x: number; y: number } {
  if (!viewport) {
    return { x: 0, y: 0 };
  }
  const rect = viewport.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left + viewport.scrollLeft) / zoom,
    y: (event.clientY - rect.top + viewport.scrollTop) / zoom,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
