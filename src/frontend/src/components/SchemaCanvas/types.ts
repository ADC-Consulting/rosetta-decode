export type CanvasColumn = {
  name: string;
  type: string;
  nullable: boolean;
  isPrimaryKey: boolean;
  isForeignKey?: boolean;
  isUnique?: boolean;
  defaultValue?: string | null;
  constraints?: string[];
  comment?: string | null;
};

export type TableNodeData = {
  label: string;
  columns: CanvasColumn[];
  primary_key: string[];
  comment?: string | null;
};

export type CanvasEdgeData = {
  description: string;
  fromColumn?: string | null;
  toColumn?: string | null;
  relationType?: "fk" | "relation";
};
