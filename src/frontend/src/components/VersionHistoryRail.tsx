import { getJobVersion, getJobVersions } from "@/api/jobs";
import type { JobVersionSummary } from "@/api/types";
import { cn } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { Bot, Clock, User } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Rail
// ---------------------------------------------------------------------------

interface VersionHistoryRailProps {
  jobId: string;
  tab: "plan" | "editor" | "report";
  className?: string;
  selectedVersionId?: string | null;
  onRestore?: (content: Record<string, unknown>) => void;
}

export default function VersionHistoryRail({
  jobId,
  tab,
  className,
  selectedVersionId: controlledSelected,
  onRestore,
}: VersionHistoryRailProps): React.ReactElement {
  const [localSelected, setLocalSelected] = useState<string | null>(null);
  const [prevTab, setPrevTab] = useState(tab);
  const [restoring, setRestoring] = useState(false);

  // Reset selection when the tab prop changes.
  if (tab !== prevTab) {
    setPrevTab(tab);
    setLocalSelected(null);
  }

  // Parent-controlled selection takes priority; fall back to local click state.
  const selectedVersionId = controlledSelected ?? localSelected;

  const { data } = useQuery({
    queryKey: ["job", jobId, "versions", tab],
    queryFn: () => getJobVersions(jobId, tab),
    enabled: !!jobId,
    staleTime: 0,
  });

  const versions: JobVersionSummary[] = data ?? [];

  const sorted = [...versions].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );

  const versionLabel = new Map<string, number>(
    sorted.map((v, idx) => [v.id, idx + 1]),
  );

  const displayed = [...sorted].reverse();

  async function handleCardClick(versionId: string): Promise<void> {
    if (restoring) return;
    setLocalSelected(versionId);
    setRestoring(true);
    try {
      const versionData = await getJobVersion(jobId, versionId);
      onRestore?.(versionData.content);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Could not restore version.",
      );
      setLocalSelected(null);
    } finally {
      setRestoring(false);
    }
  }

  return (
    <div className={cn("w-32 flex flex-col gap-1", className)}>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium px-1">
        <Clock size={12} />
        <span>History</span>
        {versions.length > 0 && (
          <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-semibold">
            {versions.length}
          </span>
        )}
      </div>

      <div className="relative flex flex-col gap-1 items-center">
        <div className="absolute left-0 top-0 bottom-0 w-px bg-border" />

        {displayed.length === 0 ? (
          <p className="pl-4 text-xs text-muted-foreground">No history.</p>
        ) : (
          displayed.map((v: JobVersionSummary, idx: number) => {
            const version = versionLabel.get(v.id) ?? 1;
            const dateStr = new Date(v.created_at).toLocaleDateString("en-GB", {
              day: "numeric",
              month: "short",
            });
            const isSelected = selectedVersionId === v.id;
            const isLatest = idx === 0;
            const hasSelection = !!selectedVersionId;

            return (
              <div
                key={v.id}
                className={cn(
                  "w-29 rounded-md border px-1 py-0.5 transition-colors bg-[#f5f5f5]",
                  isSelected
                    ? "border-primary ring-1 ring-primary cursor-default"
                    : isLatest && !hasSelection
                      ? "border-primary cursor-pointer"
                      : "border-border hover:border-muted-foreground cursor-pointer",
                  restoring && !isSelected && "opacity-50 pointer-events-none",
                )}
                onClick={() => {
                  void handleCardClick(v.id);
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    void handleCardClick(v.id);
                  }
                }}
                aria-label={`Restore v${version}`}
                aria-pressed={isSelected}
              >
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-[10px] font-bold">
                    v{version}
                  </span>
                  {v.trigger === "agent" ? (
                    <Bot size={10} className="text-blue-500 shrink-0" />
                  ) : (
                    <User size={10} className="text-violet-500 shrink-0" />
                  )}
                  <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">
                    {dateStr}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
