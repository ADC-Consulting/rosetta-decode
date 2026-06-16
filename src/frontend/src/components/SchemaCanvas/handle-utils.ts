export type HandleSide = "handle-left" | "handle-right";

const MODERN_HANDLE_ID_PATTERN = /^col:([^:]+):(left|right)$/;

export function inferHorizontalHandleSides(
  sourceX: number,
  targetX: number,
): { sourceSide: HandleSide; targetSide: HandleSide } {
  const sourceSide: HandleSide = sourceX > targetX ? "handle-left" : "handle-right";
  return {
    sourceSide,
    targetSide: sourceSide === "handle-right" ? "handle-left" : "handle-right",
  };
}

export function parseColumnHandleId(
  handleId: string | null | undefined,
): { columnName: string; side: HandleSide } | null {
  if (!handleId) {
    return null;
  }
  const match = handleId.match(MODERN_HANDLE_ID_PATTERN);
  if (!match) {
    return null;
  }
  return {
    columnName: match[1],
    side: match[2] === "left" ? "handle-left" : "handle-right",
  };
}

export function parseColumnNameFromHandleId(handleId: string | null | undefined): string | null {
  const parsed = parseColumnHandleId(handleId);
  if (parsed) {
    return parsed.columnName;
  }
  if (!handleId || !handleId.includes("-col-")) {
    return null;
  }

  const [, remainder] = handleId.split("-col-", 2);
  if (!remainder) {
    return null;
  }
  const [token] = remainder.split("-");
  return token || null;
}
