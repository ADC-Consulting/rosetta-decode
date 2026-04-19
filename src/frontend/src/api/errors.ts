/**
 * Parse an HTTP error response body into a human-readable message.
 * FastAPI returns {"detail": "..."} — extract that field when present.
 * Falls back to a plain message or a generic fallback string.
 */
export async function extractApiError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const json = JSON.parse(text) as unknown;
    if (json && typeof json === "object") {
      const obj = json as Record<string, unknown>;
      if (typeof obj.detail === "string" && obj.detail.trim()) {
        return obj.detail;
      }
      // FastAPI validation error: detail is an array of error objects
      if (Array.isArray(obj.detail)) {
        const msgs = obj.detail
          .map((d) => (typeof d === "object" && d && "msg" in d ? String((d as Record<string, unknown>).msg) : null))
          .filter(Boolean);
        if (msgs.length > 0) return msgs.join("; ");
      }
    }
  } catch {
    // not JSON — use plain text if it looks human-readable
    if (text.trim() && !text.trim().startsWith("{") && !text.trim().startsWith("[")) {
      return text.trim();
    }
  }
  // Generic fallback keyed on status
  switch (res.status) {
    case 400: return "The request was invalid. Please check your input and try again.";
    case 401: return "You are not authorised to perform this action.";
    case 403: return "Access denied.";
    case 404: return "The requested resource could not be found.";
    case 409: return "This operation conflicts with the current state. Please try again.";
    case 413: return "The file is too large to process.";
    case 422: return "The server could not process your request. Please check your input.";
    case 500: return "Something went wrong on the server. Please try again later.";
    case 503: return "The service is temporarily unavailable. Please try again shortly.";
    default:  return `An unexpected error occurred (${res.status}). Please try again.`;
  }
}
