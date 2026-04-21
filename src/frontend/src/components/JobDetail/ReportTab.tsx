import TiptapEditor from "@/components/TiptapEditor";
import { marked } from "marked";
import { useMemo } from "react";
import { extractMarkdown } from "./utils";

export default function ReportTab({
  isDone,
  doc,
  onDocChange,
  restoreKey = 0,
}: {
  isDone: boolean;
  doc: string | null;
  onDocChange?: (doc: string) => void;
  restoreKey?: number;
}): React.ReactElement {
  const initialHtml = useMemo(
    () => (doc ? String(marked.parse(extractMarkdown(doc))) : ""),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [restoreKey],
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
      <h3 className="text-sm font-semibold mb-2 shrink-0">Migration summary</h3>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {doc !== null ? (
          <TiptapEditor
            key={restoreKey}
            content={initialHtml}
            readOnly={false}
            onChange={onDocChange}
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            Summary not yet generated.
          </p>
        )}
      </div>
    </div>
  );
}
