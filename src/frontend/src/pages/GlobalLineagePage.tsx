import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getJobLineage, listJobs } from "@/api/jobs";
import type { JobLineageResponse, JobStatusValue } from "@/api/types";
import LineageGraph from "@/components/LineageGraph";
import { mergePipelineLineages } from "@/lib/lineage-merge";
import RightSidebar from "@/components/RightSidebar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const VISIBLE_STATUSES: JobStatusValue[] = ["proposed", "accepted", "done"];

type TabValue = "pipeline" | "datasets" | "columns";

export default function GlobalLineagePage(): React.ReactElement {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mergedLineage, setMergedLineage] = useState<JobLineageResponse | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabValue>("pipeline");

  const { data: jobs } = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
  });

  const filteredJobs = (jobs ?? []).filter((j) =>
    VISIBLE_STATUSES.includes(j.status),
  );

  function toggleJob(jobId: string): void {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  }

  async function handleConnect(): Promise<void> {
    if (selected.size === 0) return;
    setIsConnecting(true);
    setConnectError(null);
    try {
      const results = await Promise.all(
        Array.from(selected).map(async (jobId) => ({
          jobId,
          lineage: await getJobLineage(jobId),
        })),
      );
      setMergedLineage(mergePipelineLineages(results));
    } catch (err) {
      setConnectError(err instanceof Error ? err.message : "Failed to load lineage data.");
    } finally {
      setIsConnecting(false);
    }
  }

  return (
    <div className="flex -mx-4 -mb-8" style={{ height: "calc(100vh - 64px)" }}>
      {/* Main area — tabs + graph */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <div className="flex border-b border-border shrink-0">
          {(["pipeline", "datasets", "columns"] as TabValue[]).map((tab) => {
            const disabled = tab !== "pipeline";
            return (
              <button
                key={tab}
                type="button"
                disabled={disabled}
                onClick={() => !disabled && setActiveTab(tab)}
                className={cn(
                  "h-10 px-4 text-sm capitalize transition-colors",
                  disabled && "opacity-40 cursor-not-allowed",
                  !disabled && activeTab === tab
                    ? "border-b-2 border-foreground font-medium text-foreground"
                    : !disabled
                      ? "text-muted-foreground hover:text-foreground"
                      : "",
                )}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            );
          })}
        </div>

        <div className="flex-1 min-h-0 overflow-hidden">
          {activeTab === "pipeline" && (
            <>
              {isConnecting && (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  Loading lineage data…
                </div>
              )}
              {!isConnecting && mergedLineage && (
                <LineageGraph lineage={mergedLineage} />
              )}
              {!isConnecting && !mergedLineage && (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  Select migrations and click Connect to visualise the pipeline.
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Right panel — same RightSidebar as Explain page */}
      <RightSidebar
        title="Migrations"
        items={filteredJobs.map((job) => ({
          id: job.job_id,
          label: job.name ?? job.job_id,
          isSelected: selected.has(job.job_id),
          onClick: () => toggleJob(job.job_id),
        }))}
        footer={
          <div className="p-3">
            <Button
              onClick={() => void handleConnect()}
              disabled={selected.size === 0 || isConnecting}
              className="w-full"
              size="sm"
            >
              {isConnecting ? "Connecting…" : "Connect"}
            </Button>
            {connectError && (
              <p className="text-xs text-destructive mt-2">{connectError}</p>
            )}
          </div>
        }
      />
    </div>
  );
}
