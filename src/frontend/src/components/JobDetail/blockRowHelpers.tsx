import type { BlockRowProps } from "./blockStatusHelpers";
import { getBlockStatus, STATUS_CONFIG } from "./blockStatusHelpers";

// ---------------------------------------------------------------------------
// BlockRow — shared clickable row used by BlockInspectorPanel and
// PipelineStepPanel. Only the component is exported from this file so the
// react-refresh/only-export-components rule is satisfied.
// ---------------------------------------------------------------------------

export function BlockRow({
  bp,
  trustBlock,
  isHumanVerified,
  onClick,
}: BlockRowProps): React.ReactElement {
  const statusKind = getBlockStatus(bp, trustBlock, isHumanVerified);
  const statusCfg = STATUS_CONFIG[statusKind];

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "w-full flex flex-col px-3 py-2 text-left",
        "hover:bg-muted/50 transition-colors cursor-pointer",
        "border-b border-border last:border-b-0",
      ].join(" ")}
      aria-label={`Inspect block ${bp.block_id}`}
    >
      {/* Top row: block type pill + line number + status badge */}
      <div className="flex items-center gap-2">
        {/* Block type pill */}
        <span
          className={[
            "shrink-0 inline-flex items-center rounded px-1.5 py-0.5",
            "text-[11px] font-medium font-mono",
            "bg-slate-100 text-slate-700 border border-slate-200",
          ].join(" ")}
        >
          {bp.block_type}
        </span>

        {/* Line number */}
        <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
          :{bp.start_line}
        </span>

        {/* Spacer */}
        <span className="flex-1 min-w-0" />

        {/* Status badge */}
        <span
          className={[
            "shrink-0 inline-flex items-center rounded px-1.5 py-0.5",
            "text-[11px] font-medium",
            statusCfg.className,
          ].join(" ")}
          aria-label={`Status: ${statusCfg.label}`}
        >
          {statusCfg.label}
        </span>
      </div>

      {/* Rationale — only shown when non-empty */}
      {bp.rationale && (
        <p className="text-xs text-muted-foreground truncate mt-0.5 pr-2">
          {bp.rationale}
        </p>
      )}
    </button>
  );
}
