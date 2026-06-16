export const DATA_MODEL_NODE_WIDTH = 400;
export const DATA_MODEL_NODE_HEADER_HEIGHT = 46;
export const DATA_MODEL_NODE_BODY_PADDING_TOP = 6;
export const DATA_MODEL_NODE_ROW_HEIGHT = 34;
export const DATA_MODEL_NODE_BODY_PADDING_BOTTOM = 10;

export const DATA_MODEL_LAYOUT_BASE_X = 100;
export const DATA_MODEL_LAYOUT_BASE_Y = 80;
export const DATA_MODEL_LAYOUT_COLUMN_GAP = 480;
export const DATA_MODEL_LAYOUT_VERTICAL_GAP = 44;
export const DATA_MODEL_LAYOUT_GRID_COLS = 4;

export function getDataModelNodeHeight(columnCount: number): number {
  return (
    DATA_MODEL_NODE_HEADER_HEIGHT
    + DATA_MODEL_NODE_BODY_PADDING_TOP
    + Math.max(columnCount, 1) * DATA_MODEL_NODE_ROW_HEIGHT
    + DATA_MODEL_NODE_BODY_PADDING_BOTTOM
  );
}
