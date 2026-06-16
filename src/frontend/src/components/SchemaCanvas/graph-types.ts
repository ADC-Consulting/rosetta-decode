export type GraphNode<TData> = {
  id: string;
  type?: string;
  position: {
    x: number;
    y: number;
  };
  data: TData;
};

export type GraphEdge<TData> = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  label?: string;
  data?: TData;
  updatable?: boolean;
  animated?: boolean;
};
