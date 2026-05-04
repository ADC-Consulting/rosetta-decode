import { getAttachmentUrl } from "@/api/jobs";
import type { AttachmentInfo } from "@/api/types";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

interface LogViewProps {
  jobId: string;
  attachments: AttachmentInfo[];
}

function classifyLine(line: string): string {
  if (/^NOTE:/i.test(line)) return "text-blue-600";
  if (/^WARNING:/i.test(line)) return "text-amber-600 font-medium";
  if (/^ERROR:/i.test(line)) return "text-red-600 font-bold";
  return "text-muted-foreground";
}

export default function LogView({ jobId, attachments }: LogViewProps): React.ReactElement {
  const [selectedKey, setSelectedKey] = useState<string>(attachments[0]?.path_key ?? "");
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (attachments.length > 0 && !selectedKey) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedKey(attachments[0].path_key);
    }
  }, [attachments, selectedKey]);

  useEffect(() => {
    if (!selectedKey) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    setContent(null);
    fetch(getAttachmentUrl(jobId, selectedKey))
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load log (${res.status})`);
        return res.text();
      })
      .then(setContent)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [jobId, selectedKey]);

  if (attachments.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-muted-foreground px-6 text-center">
        No log files uploaded. Include .log or .lst files in your zip to view them here.
      </div>
    );
  }

  const lines = content ? content.split("\n") : [];

  return (
    <div className="flex flex-col h-full min-h-0">
      {attachments.length > 1 && (
        <div className="flex gap-1 px-3 py-2 border-b border-border shrink-0 flex-wrap">
          {attachments.map((a) => (
            <button
              key={a.path_key}
              onClick={() => setSelectedKey(a.path_key)}
              className={cn(
                "px-2.5 py-1 text-xs rounded border transition-colors cursor-pointer",
                selectedKey === a.path_key
                  ? "border-primary bg-primary/10 text-primary font-medium"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30",
              )}
            >
              {a.filename}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
          Loading log…
        </div>
      )}

      {error && (
        <div className="flex items-center justify-center h-32 text-sm text-red-600 px-4 text-center">
          {error}
        </div>
      )}

      {!loading && !error && content !== null && (
        <pre
          className="flex-1 min-h-0 overflow-y-auto overflow-x-auto font-mono text-[12px] leading-relaxed p-4"
          style={{ maxHeight: "60vh" }}
        >
          {lines.map((line, i) => (
            <span key={i} className={cn("block whitespace-pre", classifyLine(line))}>
              {line || " "}
            </span>
          ))}
        </pre>
      )}
    </div>
  );
}
