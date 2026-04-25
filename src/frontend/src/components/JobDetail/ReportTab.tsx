import TiptapEditor from "@/components/TiptapEditor";
import { Lock, Pencil, Save } from "lucide-react";
import { marked } from "marked";
import { useMemo, useState } from "react";
import { extractMarkdown } from "./utils";

export default function ReportTab({
  isDone,
  doc,
  onDocChange,
  restoreKey = 0,
  nonTechnicalDoc = null,
  onSave,
  isSaving = false,
}: {
  isDone: boolean;
  doc: string | null;
  onDocChange?: (doc: string) => void;
  restoreKey?: number;
  nonTechnicalDoc?: string | null;
  onSave?: () => void;
  isSaving?: boolean;
}): React.ReactElement {
  const [readOnly, setReadOnly] = useState(true);
  const [showTechnical, setShowTechnical] = useState(true);

  const initialHtml = useMemo(
    () => (doc ? String(marked.parse(extractMarkdown(doc))) : ""),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [restoreKey],
  );

  const nonTechHtml = useMemo(
    () =>
      nonTechnicalDoc ? String(marked.parse(extractMarkdown(nonTechnicalDoc))) : "",
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [restoreKey, nonTechnicalDoc],
  );

  if (!isDone) {
    return (
      <p className="text-sm text-muted-foreground">
        Report available once migration completes.
      </p>
    );
  }

  return (
    <div className="h-full min-h-0 flex flex-col pb-6">
      {/* Header — always visible */}
      <div className="flex items-center gap-2 px-3 py-2 mb-2 shrink-0 rounded-md bg-muted/40 border border-border">
        <h3 className="text-sm font-semibold">Migration summary</h3>

        {/* Technical / Plain English toggle */}
        <div className="flex items-center rounded-md border border-border overflow-hidden ml-2">
          <button
            onClick={() => setShowTechnical(true)}
            className={
              "px-2.5 py-1 text-xs transition-colors cursor-pointer " +
              (showTechnical
                ? "bg-foreground text-background"
                : "bg-background text-muted-foreground hover:text-foreground")
            }
          >
            Technical
          </button>
          <button
            onClick={() => setShowTechnical(false)}
            className={
              "px-2.5 py-1 text-xs transition-colors cursor-pointer " +
              (!showTechnical
                ? "bg-foreground text-background"
                : "bg-background text-muted-foreground hover:text-foreground")
            }
          >
            Plain English
          </button>
        </div>

        {/* Right-side actions */}
        <div className="ml-auto flex items-center gap-1.5">
          {!readOnly && onSave && (
            <button
              onClick={onSave}
              disabled={isSaving}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border border-border bg-background hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
            >
              <Save size={12} />
              {isSaving ? "Saving…" : "Save"}
            </button>
          )}
          <button
            onClick={() => setReadOnly((v) => !v)}
            aria-label={readOnly ? "Enable editing" : "Lock editing"}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border border-border bg-background hover:bg-muted transition-colors cursor-pointer"
          >
            {readOnly ? (
              <>
                <Pencil size={12} /> Edit
              </>
            ) : (
              <>
                <Lock size={12} /> Read-only
              </>
            )}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {showTechnical ? (
          doc !== null ? (
            <TiptapEditor
              key={restoreKey}
              content={initialHtml}
              readOnly={readOnly}
              onChange={readOnly ? undefined : onDocChange}
            />
          ) : (
            <p className="text-sm text-muted-foreground">Summary not yet generated.</p>
          )
        ) : nonTechnicalDoc ? (
          <TiptapEditor
            key={`plain-${restoreKey}`}
            content={nonTechHtml}
            readOnly={readOnly}
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            Plain English summary not yet generated — run a new job to generate this report.
          </p>
        )}
      </div>
    </div>
  );
}
