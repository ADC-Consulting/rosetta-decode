/** Unwrap `{"markdown":"..."}` responses from older LLM calls. */
export function extractMarkdown(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (
      parsed &&
      typeof parsed === "object" &&
      "markdown" in parsed &&
      typeof (parsed as Record<string, unknown>).markdown === "string"
    ) {
      return (parsed as { markdown: string }).markdown;
    }
  } catch {
    // not JSON — use as-is
  }
  return raw;
}
