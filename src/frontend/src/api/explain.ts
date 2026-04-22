import { extractApiError } from "./errors";
import type { ExplainJobRequest, ExplainMessage, ExplainResponse } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function explainFiles(
  question: string,
  files: File[],
  messages: ExplainMessage[],
): Promise<ExplainResponse> {
  const form = new FormData();
  form.append("question", question);
  form.append("messages", JSON.stringify(messages));
  for (const file of files) {
    form.append("files", file);
  }
  const res = await fetch(`${BASE}/explain`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<ExplainResponse>;
}

export async function explainJob(req: ExplainJobRequest): Promise<ExplainResponse> {
  const res = await fetch(`${BASE}/explain/job`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<ExplainResponse>;
}
