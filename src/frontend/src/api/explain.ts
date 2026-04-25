import { extractApiError } from "./errors";
import type {
    CreateExplainSessionRequest,
    ExplainMessage,
    ExplainSessionResponse,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ── SSE streaming helpers ──────────────────────────────────────────────────

async function* parseSseStream(response: Response): AsyncGenerator<string> {
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") return;
        try {
          const parsed = JSON.parse(payload) as { chunk?: string; tokens_used?: number | null };
          if (parsed.chunk !== undefined) yield parsed.chunk;
        } catch {
          // ignore malformed lines
        }
      }
    }
  }
}

export async function* explainFilesStream(
  question: string,
  files: File[],
  messages: ExplainMessage[],
  audience: "tech" | "non_tech",
  sessionId: string | null,
  mode: "migration" | "sas_general" = "sas_general",
): AsyncGenerator<string> {
  const form = new FormData();
  form.append("question", question);
  form.append("messages", JSON.stringify(messages));
  form.append("audience", audience);
  form.append("mode", mode);
  if (sessionId) form.append("session_id", sessionId);
  for (const file of files) form.append("files", file);

  const res = await fetch(`${BASE}/explain`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await extractApiError(res));
  yield* parseSseStream(res);
}

export async function* explainJobStream(
  jobId: string,
  question: string,
  messages: ExplainMessage[],
  audience: "tech" | "non_tech",
  sessionId: string | null,
): AsyncGenerator<string> {
  const res = await fetch(`${BASE}/explain/job`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, question, messages, audience, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
  yield* parseSseStream(res);
}

// ── Session CRUD ───────────────────────────────────────────────────────────

export async function createExplainSession(
  req: CreateExplainSessionRequest,
): Promise<ExplainSessionResponse> {
  const res = await fetch(`${BASE}/explain/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<ExplainSessionResponse>;
}

export async function listExplainSessions(): Promise<ExplainSessionResponse[]> {
  const res = await fetch(`${BASE}/explain/sessions`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<ExplainSessionResponse[]>;
}

export async function getExplainSession(id: string): Promise<ExplainSessionResponse> {
  const res = await fetch(`${BASE}/explain/sessions/${id}`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<ExplainSessionResponse>;
}
