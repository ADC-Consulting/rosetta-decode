import { getBlockRevisions, saveBlockPython } from "@/api/jobs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Editor } from "@monaco-editor/react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Suspense, useMemo, useState } from "react";
import { registerSasLanguage } from "./registerSasLanguage";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type BlockStatus =
  | "auto-verified"
  | "needs-review"
  | "manual"
  | "human-verified"
  | "pending";

export interface BlockCodePopupProps {
  jobId: string;
  blockId: string;
  sourceFile: string;
  blockType: string;
  status: BlockStatus;
  sasSource: string;
  startLine: number;
  endLine: number;
  onClose: () => void;
  onVerified: (blockId: string) => void;
  jobAccepted?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Derive a display-friendly basename: filename + line, e.g. "05_build_adam_adsl.sas:42". */
function blockDisplayId(sourceFile: string, startLine: number): string {
  const basename = sourceFile.split("/").pop() ?? sourceFile;
  return startLine > 0 ? `${basename}:${startLine}` : basename;
}

// ---------------------------------------------------------------------------
// Status badge colours — consistent with BlockInspectorPanel (if it exists)
// or derived from the plan's description of the statuses.
// ---------------------------------------------------------------------------

interface StatusConfig {
  label: string;
  className: string;
}

const STATUS_CONFIG: Record<BlockStatus, StatusConfig> = {
  "auto-verified": {
    label: "Auto-verified",
    className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  },
  "human-verified": {
    label: "Human-verified",
    className: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300",
  },
  "needs-review": {
    label: "Needs review",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
  },
  manual: {
    label: "Manual",
    className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
  },
  pending: {
    label: "Pending",
    className: "bg-muted text-muted-foreground",
  },
};

// ---------------------------------------------------------------------------
// BlockCodePopup
// ---------------------------------------------------------------------------

export default function BlockCodePopup({
  jobId,
  blockId,
  sourceFile,
  blockType,
  status,
  sasSource,
  startLine,
  endLine,
  onClose,
  onVerified,
  jobAccepted = false,
}: BlockCodePopupProps): React.ReactElement {
  const [localPython, setLocalPython] = useState<string>("");
  const [isSaving, setIsSaving] = useState(false);
  const [isVerified, setIsVerified] = useState(false);

  const {
    data: revisionHistory,
    isLoading: isLoadingRevisions,
    isError: isRevisionError,
  } = useQuery({
    queryKey: ["job", jobId, "blocks", blockId, "revisions"],
    queryFn: () => getBlockRevisions(jobId, blockId),
    enabled: !!jobId && !!blockId,
  });

  // Derived values
  const extractedSas = useMemo(() => {
    if (!sasSource) return "";
    const lines = sasSource.split('\n');
    return lines.slice(Math.max(0, startLine - 1), endLine).join('\n');
  }, [sasSource, startLine, endLine]);

  const displayId = blockDisplayId(sourceFile, startLine);
  const statusConfig = STATUS_CONFIG[status];

  const latestPythonCode = revisionHistory?.revisions[0]?.python_code ?? null;

  // Initialise localPython once revision data arrives (runs once per stable key)
  // The Python editor uses `defaultValue` + stable `key` to avoid cursor repositioning,
  // so we pass localPython only for display and fall back to initialising from revision.
  const pythonEditorKey = `block-py-${blockId}-${latestPythonCode !== null ? "loaded" : "empty"}`;
  const pythonDefaultValue =
    latestPythonCode ?? "# No Python translation available yet.";

  // Force read-only when job is accepted, regardless of block status.
  const isReadOnly = jobAccepted || status === "auto-verified" || status === "human-verified";
  const canVerify = !jobAccepted && (status === "needs-review" || status === "manual");

  const handleMarkVerified = async () => {
    if (isSaving) return;
    setIsSaving(true);
    try {
      await saveBlockPython(jobId, blockId, localPython || pythonDefaultValue, {
        trigger: "human-verify",
      });
      onVerified(blockId);
      setIsVerified(true);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        className="flex flex-col gap-0 p-0 overflow-hidden"
        style={{ width: "80vw", maxWidth: "80vw", height: "80vh", maxHeight: "80vh" }}
        aria-label={`Block code: ${displayId}`}
      >
        {/* ----------------------------------------------------------------- */}
        {/* Header */}
        {/* ----------------------------------------------------------------- */}
        <DialogHeader className="flex flex-row items-center gap-3 px-4 py-3 border-b border-border shrink-0">
          <DialogTitle className="font-mono text-sm font-semibold truncate">
            {displayId}
          </DialogTitle>
          <Badge className={`text-[11px] px-2 py-0 border-0 ${statusConfig.className}`}>
            {blockType}
          </Badge>
          <Badge className={`text-[11px] px-2 py-0 border-0 ${statusConfig.className}`}>
            {statusConfig.label}
          </Badge>
        </DialogHeader>

        {/* ----------------------------------------------------------------- */}
        {/* Status context banner */}
        {/* ----------------------------------------------------------------- */}
        {status === "needs-review" && (
          <div
            role="status"
            className="flex items-start gap-2 px-4 py-2 text-xs bg-amber-50 border-b border-amber-200
              dark:bg-amber-950/30 dark:border-amber-800 text-amber-800 dark:text-amber-300 shrink-0"
          >
            <span className="font-medium">Reconciliation flagged differences</span>
            <span className="text-amber-700 dark:text-amber-400">
              — review the proposed Python before verifying.
            </span>
          </div>
        )}
        {status === "manual" && (
          <div
            role="status"
            className="flex items-start gap-2 px-4 py-2 text-xs bg-red-50 border-b border-red-200
              dark:bg-red-950/30 dark:border-red-800 text-red-800 dark:text-red-300 shrink-0"
          >
            <span className="font-medium">This block requires manual Python implementation.</span>
          </div>
        )}
        {isVerified && !isReadOnly && (
          <div
            role="status"
            className="flex items-center gap-2 px-4 py-2 text-xs bg-green-50 border-b border-green-200
              dark:bg-green-950/30 dark:border-green-800 text-green-800 dark:text-green-300 shrink-0"
          >
            <span className="font-medium">Block marked as verified.</span>
            <span className="text-green-700 dark:text-green-400">You can close this panel.</span>
          </div>
        )}

        {/* ----------------------------------------------------------------- */}
        {/* Two-column editor body */}
        {/* ----------------------------------------------------------------- */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Left — SAS source (read-only) */}
          <div className="flex flex-col flex-1 min-w-0 border-r border-border">
            <div className="h-8 flex items-center gap-2 px-3 shrink-0 border-b border-border bg-muted/30">
              <img src="/sas.svg" className="h-4 w-4 shrink-0" alt="SAS" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                SAS
              </span>
              {startLine > 0 && (
                <span className="ml-auto text-[11px] text-muted-foreground/60 font-mono">
                  lines {startLine}–{endLine}
                </span>
              )}
            </div>
            <div className="flex-1 min-h-0">
              {extractedSas ? (
                <Suspense
                  fallback={
                    <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                      Loading…
                    </div>
                  }
                >
                  <Editor
                    key={`block-sas-${blockId}`}
                    height="100%"
                    defaultValue={extractedSas}
                    language="sas"
                    theme="sas-light"
                    beforeMount={registerSasLanguage}
                    loading={
                      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                        Loading…
                      </div>
                    }
                    options={{
                      readOnly: true,
                      fontSize: 13,
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      lineNumbers: "on",
                    }}
                  />
                </Suspense>
              ) : (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  SAS source not available
                </div>
              )}
            </div>
          </div>

          {/* Right — Python (editable for needs-review/manual) */}
          <div className="flex flex-col flex-1 min-w-0">
            <div className="h-8 flex items-center gap-2 px-3 shrink-0 border-b border-border bg-muted/30">
              <img src="/python.svg" className="h-4 w-4 shrink-0" alt="Python" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Python
              </span>
              {isReadOnly && (
                <span className="ml-auto text-[11px] text-muted-foreground/60 italic">
                  read-only
                </span>
              )}
            </div>
            <div className="flex-1 min-h-0">
              {isLoadingRevisions ? (
                <div className="flex items-center justify-center h-full gap-2 text-sm text-muted-foreground">
                  <Loader2 size={16} className="animate-spin" />
                  Loading translation…
                </div>
              ) : isRevisionError ? (
                <div className="flex items-center justify-center h-full text-sm text-destructive">
                  Failed to load revision data.
                </div>
              ) : (
                <Suspense
                  fallback={
                    <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                      Loading…
                    </div>
                  }
                >
                  <Editor
                    key={pythonEditorKey}
                    height="100%"
                    defaultValue={pythonDefaultValue}
                    language="python"
                    theme="vs"
                    loading={
                      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                        Loading…
                      </div>
                    }
                    onChange={(value) => {
                      if (!isReadOnly) setLocalPython(value ?? "");
                    }}
                    options={{
                      readOnly: isReadOnly,
                      fontSize: 13,
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      lineNumbers: "on",
                    }}
                  />
                </Suspense>
              )}
            </div>
          </div>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* Footer */}
        {/* ----------------------------------------------------------------- */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border bg-muted/30 shrink-0">
          {canVerify && !isVerified && (
            <Button
              variant="default"
              size="sm"
              disabled={isSaving || isLoadingRevisions}
              onClick={() => { void handleMarkVerified(); }}
              aria-label="Mark block as verified"
            >
              {isSaving ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Saving…
                </>
              ) : (
                "Mark as verified"
              )}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            aria-label="Close block code popup"
          >
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
