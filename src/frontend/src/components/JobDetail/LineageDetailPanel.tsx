import type { BlockPlan, BlockStatus, FileNode, LogLink } from "@/api/types";
import { X } from "lucide-react";
import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

interface LineageDetailPanelProps {
  file: FileNode | null;
  blockStatuses: BlockStatus[];
  logLinks: LogLink[];
  onClose: () => void;
  blockPlans?: BlockPlan[];
}

const STRATEGY_COLOR: Record<string, string> = {
  translate: "text-blue-700 bg-blue-50 border border-blue-200",
  translate_with_review: "text-amber-700 bg-amber-50 border border-amber-200",
  translate_best_effort: "text-orange-700 bg-orange-50 border border-orange-200",
  manual: "text-red-700 bg-red-50 border border-red-200",
  manual_ingestion: "text-red-700 bg-red-50 border border-red-200",
  skip: "text-muted-foreground bg-muted border border-border",
};

const RISK_COLOR: Record<string, string> = {
  low: "text-green-700 bg-green-50 border border-green-200",
  medium: "text-amber-700 bg-amber-50 border border-amber-200",
  high: "text-red-700 bg-red-50 border border-red-200",
};

const FILE_TYPE_STYLE: Record<FileNode["file_type"], { bg: string; text: string }> = {
  PROGRAM: { bg: "bg-blue-100", text: "text-blue-700" },
  MACRO: { bg: "bg-purple-100", text: "text-purple-700" },
  AUTOEXEC: { bg: "bg-orange-100", text: "text-orange-700" },
  LOG: { bg: "bg-slate-100", text: "text-slate-600" },
  OTHER: { bg: "bg-gray-100", text: "text-gray-600" },
};

const FILE_STATUS_STYLE: Record<
  NonNullable<FileNode["status"]>,
  { bg: string; text: string; label: string }
> = {
  OK: { bg: "bg-green-100", text: "text-green-700", label: "OK" },
  UNTRANSLATABLE: { bg: "bg-red-100", text: "text-red-700", label: "Untranslatable" },
  ERROR_PRONE: { bg: "bg-amber-100", text: "text-amber-700", label: "Error Prone" },
};

const SEVERITY_STYLE: Record<LogLink["severity"], { bg: string; text: string }> = {
  INFO: { bg: "bg-blue-100", text: "text-blue-700" },
  WARNING: { bg: "bg-amber-100", text: "text-amber-700" },
  ERROR: { bg: "bg-red-100", text: "text-red-700" },
};

function BlockStatusIcon({ status }: { status: BlockStatus["status"] }): React.ReactElement | null {
  if (status === "OK") return <CheckCircle2 size={12} className="text-green-500 shrink-0" />;
  if (status === "ERROR_PRONE") return <AlertTriangle size={12} className="text-amber-500 shrink-0" />;
  if (status === "UNTRANSLATABLE") return <XCircle size={12} className="text-red-500 shrink-0" />;
  return null;
}

export function LineageDetailPanel({
  file,
  blockStatuses,
  logLinks,
  onClose,
  blockPlans = [],
}: LineageDetailPanelProps): React.ReactElement {
  const planByBlockId = Object.fromEntries(blockPlans.map((p) => [p.block_id, p]));
  const isOpen = file !== null;
  const filename = file ? (file.filename.split("/").pop() ?? file.filename) : "";
  const typeStyle = file ? FILE_TYPE_STYLE[file.file_type] : null;
  const statusStyle = file?.status ? FILE_STATUS_STYLE[file.status] : null;

  const matchingLogLinks = file
    ? logLinks.filter((ll) => ll.related_files.includes(file.filename))
    : [];

  return (
    <div
      className={`absolute top-0 right-0 h-full w-72 z-20 bg-white border-l border-slate-200 shadow-xl flex flex-col transition-transform duration-200 ease-in-out${
        isOpen ? " translate-x-0" : " translate-x-full pointer-events-none"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 shrink-0">
        <span className="text-sm font-semibold text-slate-800 truncate pr-2">{filename}</span>
        <button
          onClick={onClose}
          className="shrink-0 p-1 rounded hover:bg-slate-100 text-slate-500 hover:text-slate-700"
          aria-label="Close panel"
        >
          <X size={14} />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="overflow-y-auto flex-1 px-4 py-2">
        {file && (
          <>
            {/* File type badge */}
            {typeStyle && (
              <div className="mt-2">
                <span
                  className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${typeStyle.bg} ${typeStyle.text}`}
                >
                  {file.file_type}
                </span>
              </div>
            )}

            {/* Status */}
            {statusStyle && (
              <div className="mt-3">
                <span
                  className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${statusStyle.bg} ${statusStyle.text}`}
                >
                  {statusStyle.label}
                </span>
                {file.status_reason && (
                  <p className="text-xs text-slate-500 mt-1">{file.status_reason}</p>
                )}
              </div>
            )}

            <hr className="my-3 border-slate-100" />

            {/* Blocks */}
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide pt-1 pb-2">
              Blocks
            </div>
            {file.blocks.length === 0 ? (
              <p className="text-xs text-slate-400">No blocks</p>
            ) : (
              <ul className="space-y-3">
                {file.blocks.map((blockId) => {
                  const bs = blockStatuses.find((b) => b.block_id === blockId);
                  const plan = planByBlockId[blockId];
                  return (
                    <li key={blockId} className="space-y-1">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-xs text-slate-700 truncate">{blockId}</span>
                        {bs && <BlockStatusIcon status={bs.status} />}
                      </div>
                      {plan && (
                        <div className="pl-1 space-y-1">
                          <div className="flex flex-wrap gap-1">
                            <span
                              className={`text-[10px] font-medium px-1 py-0.5 rounded border ${STRATEGY_COLOR[plan.strategy] ?? ""}`}
                            >
                              {plan.strategy}
                            </span>
                            <span
                              className={`text-[10px] font-medium px-1 py-0.5 rounded border ${RISK_COLOR[plan.risk] ?? ""}`}
                            >
                              {plan.risk} risk
                            </span>
                            {plan.confidence_band && (
                              <span className="text-[10px] font-medium px-1 py-0.5 rounded border bg-muted text-muted-foreground border-border">
                                {(plan.confidence_score * 100).toFixed(0)}% ({plan.confidence_band})
                              </span>
                            )}
                          </div>
                          {plan.rationale && (
                            <p className="text-[10px] text-slate-500 leading-snug">
                              {plan.rationale}
                            </p>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}

            {/* Log links */}
            {matchingLogLinks.length > 0 && (
              <>
                <hr className="my-3 border-slate-100" />
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide pb-2">
                  Log Links
                </div>
                <ul className="space-y-2">
                  {matchingLogLinks.map((ll, i) => {
                    const sev = SEVERITY_STYLE[ll.severity];
                    return (
                      <li key={i} className="flex items-center gap-2">
                        <span className="font-mono text-xs text-slate-700 truncate">
                          {ll.log_file}
                        </span>
                        <span
                          className={`text-xs font-medium px-1.5 py-0.5 rounded-full shrink-0 ${sev.bg} ${sev.text}`}
                        >
                          {ll.severity}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
