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
import { Loader2, Moon, Sun } from "lucide-react";
import { Suspense, useMemo, useState } from "react";
import { toast } from "sonner";
import { useBrandManifestContainer } from "@/lib/useBrandManifestContainer";
import { registerSasLanguage } from "./registerSasLanguage";
import { TONE_CHIP_CLASS, type BlockStatus } from "./status-colors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Key under which the last-used reviewer name is remembered between verifications. */
const REVIEWER_NAME_STORAGE_KEY = "rosetta.reviewerName";

export interface BlockCodePopupProps {
  jobId: string;
  blockId: string;
  sourceFile: string;
  blockType: string;
  status: BlockStatus;
  sasSource: string;
  startLine: number;
  endLine: number;
  /**
   * Fallback Python content to show when no `block_revisions` row exists yet for this block
   * (e.g. a block the worker hasn't persisted a revision for). Ignored once a revision loads —
   * `getBlockRevisions` is always preferred when it has data.
   */
  fallbackPythonCode?: string | null;
  /** Generated Python filename this block was emitted into, shown next to the Python header. */
  pythonFile?: string | null;
  /**
   * Reviewer name for a block that was already verified before this popup opened (sourced from
   * the job's changelog by the caller). Used only until a verification happens in this session —
   * once that happens, the just-submitted name takes over for display.
   */
  verifiedBy?: string | null;
  onClose: () => void;
  /** Fired only after a "Mark as verified" save succeeds — never after a plain "Save". */
  onVerified: (blockId: string) => void;
  /** Fired after a plain "Save" succeeds. Does not imply verification. */
  onSaved?: (blockId: string) => void;
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
    className: TONE_CHIP_CLASS.success,
  },
  // "human-verified" stays teal, deliberately distinct from the amber/green/red status tones —
  // not part of the Tone system (out of scope for this cleanup, same as blue interactive links).
  "human-verified": {
    label: "Human-verified",
    className: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300",
  },
  "needs-review": {
    label: "Needs review",
    className: TONE_CHIP_CLASS.warning,
  },
  manual: {
    label: "Manual",
    className: TONE_CHIP_CLASS.danger,
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
  fallbackPythonCode,
  pythonFile,
  verifiedBy,
  onClose,
  onVerified,
  onSaved,
  jobAccepted = false,
}: BlockCodePopupProps): React.ReactElement {
  const [localPython, setLocalPython] = useState<string>("");
  const [pendingAction, setPendingAction] = useState<"save" | "verify" | null>(null);
  const isSaving = pendingAction !== null;
  const [isVerified, setIsVerified] = useState(false);
  // Name used by the verification that just completed in this session — takes priority over the
  // `verifiedBy` prop (which reflects whatever the changelog said when this popup opened).
  const [submittedVerifiedBy, setSubmittedVerifiedBy] = useState<string | null>(null);
  const [showVerifyInput, setShowVerifyInput] = useState(false);
  const [reviewerName, setReviewerName] = useState<string>(() => {
    try {
      return localStorage.getItem(REVIEWER_NAME_STORAGE_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const [codeEditorDark, setCodeEditorDark] = useState(false);
  const container = useBrandManifestContainer();

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
    latestPythonCode ?? fallbackPythonCode ?? "# No Python translation available yet.";

  // Force read-only when job is accepted, regardless of block status.
  const isReadOnly = jobAccepted || status === "auto-verified" || status === "human-verified";
  const canVerify = !jobAccepted && (status === "needs-review" || status === "manual");

  // Name used right after a "Mark as verified" in this session wins; otherwise fall back to
  // whatever the caller already knew from the changelog for a block verified before this popup
  // opened.
  const displayVerifiedBy = submittedVerifiedBy ?? verifiedBy ?? null;
  // Covers both "just verified in this session" (isVerified) and "already verified before this
  // popup opened" (status === "human-verified", sourced from the changelog by the caller) — not
  // gated on !isReadOnly, since a loaded human-verified block IS read-only and should still show
  // who verified it.
  const showVerifiedBanner = isVerified || status === "human-verified";

  const handleSave = async () => {
    if (isSaving) return;
    setPendingAction("save");
    try {
      await saveBlockPython(jobId, blockId, localPython || pythonDefaultValue, {
        trigger: "human",
      });
      onSaved?.(blockId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save code.");
    } finally {
      setPendingAction(null);
    }
  };

  const handleConfirmVerify = async () => {
    const trimmedName = reviewerName.trim();
    if (isSaving || !trimmedName) return;
    setPendingAction("verify");
    try {
      await saveBlockPython(jobId, blockId, localPython || pythonDefaultValue, {
        trigger: "human-verify",
        verified_by: trimmedName,
      });
      try {
        localStorage.setItem(REVIEWER_NAME_STORAGE_KEY, trimmedName);
      } catch {
        // Storage can be unavailable (private browsing, quota) — verification itself still
        // succeeded, so there's nothing to surface to the user here.
      }
      setSubmittedVerifiedBy(trimmedName);
      setShowVerifyInput(false);
      onVerified(blockId);
      setIsVerified(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save verification.");
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        container={container}
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
          <button
            onClick={() => setCodeEditorDark((d) => !d)}
            aria-label={codeEditorDark ? "Switch to light theme" : "Switch to dark theme"}
            className="ml-auto inline-flex items-center justify-center rounded p-1.5 text-muted-foreground border border-border hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            {codeEditorDark ? <Sun size={14} /> : <Moon size={14} />}
          </button>
        </DialogHeader>

        {/* ----------------------------------------------------------------- */}
        {/* Status context banner */}
        {/* ----------------------------------------------------------------- */}
        {status === "needs-review" && (
          <div
            role="status"
            className="flex items-start gap-2 px-4 py-2 text-xs bg-[var(--tone-warning-bg)]
              border-b border-[var(--tone-warning)]/20 text-[var(--tone-warning)] shrink-0"
          >
            <span className="font-medium">Reconciliation flagged differences</span>
            <span className="text-[var(--tone-warning)]/80">
              — review the proposed Python before verifying.
            </span>
          </div>
        )}
        {status === "manual" && (
          <div
            role="status"
            className="flex items-start gap-2 px-4 py-2 text-xs bg-[var(--tone-danger-bg)]
              border-b border-[var(--tone-danger)]/20 text-[var(--tone-danger)] shrink-0"
          >
            <span className="font-medium">This block requires manual Python implementation.</span>
          </div>
        )}
        {showVerifiedBanner && (
          <div
            role="status"
            className="flex items-center gap-2 px-4 py-2 text-xs bg-[var(--tone-success-bg)]
              border-b border-[var(--tone-success)]/20 text-[var(--tone-success)] shrink-0"
          >
            <span className="font-medium">
              {displayVerifiedBy ? `Verified by ${displayVerifiedBy}` : "Block marked as verified."}
            </span>
            <span className="text-[var(--tone-success)]/80">— you can close this panel.</span>
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
                    theme={codeEditorDark ? "sas-dark" : "sas-light"}
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
              {pythonFile && (
                <span className="text-[11px] font-mono text-muted-foreground/70">
                  {pythonFile}
                </span>
              )}
              {startLine > 0 && (
                <span className="ml-auto text-[11px] text-muted-foreground/60 font-mono">
                  lines {startLine}–{endLine}
                </span>
              )}
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
                    theme={codeEditorDark ? "vs-dark" : "vs"}
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
          {canVerify && !isVerified && showVerifyInput && (
            <div className="flex items-center gap-1.5 mr-auto">
              <label htmlFor="block-code-reviewer-name" className="text-xs text-muted-foreground">
                Reviewer name
              </label>
              <input
                id="block-code-reviewer-name"
                type="text"
                autoFocus
                value={reviewerName}
                onChange={(e) => setReviewerName(e.target.value)}
                placeholder="Your name"
                disabled={isSaving}
                className="h-7 w-40 px-2 text-xs rounded border border-border bg-background
                  focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
              />
              {!reviewerName.trim() && (
                <span className="text-[11px] text-[var(--tone-danger)]">Required</span>
              )}
            </div>
          )}
          {canVerify && !isVerified && (
            <>
              {showVerifyInput ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isSaving}
                    onClick={() => setShowVerifyInput(false)}
                    aria-label="Cancel verification"
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="default"
                    size="sm"
                    disabled={isSaving || isLoadingRevisions || !reviewerName.trim()}
                    onClick={() => { void handleConfirmVerify(); }}
                    aria-label="Confirm block verification"
                  >
                    {pendingAction === "verify" ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        Saving…
                      </>
                    ) : (
                      "Confirm"
                    )}
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isSaving || isLoadingRevisions}
                    onClick={() => { void handleSave(); }}
                    aria-label="Save block code"
                  >
                    {pendingAction === "save" ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        Saving…
                      </>
                    ) : (
                      "Save"
                    )}
                  </Button>
                  <Button
                    variant="default"
                    size="sm"
                    disabled={isSaving || isLoadingRevisions}
                    onClick={() => setShowVerifyInput(true)}
                    aria-label="Mark block as verified"
                  >
                    Mark as verified
                  </Button>
                </>
              )}
            </>
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
