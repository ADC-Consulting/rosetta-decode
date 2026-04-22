import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getJobLineage, listJobs } from "@/api/jobs";
import type { JobLineageResponse, JobStatusValue } from "@/api/types";
import LineageGraph from "@/components/LineageGraph";
import { mergePipelineLineages } from "@/lib/lineage-merge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const VISIBLE_STATUSES: JobStatusValue[] = ["proposed", "accepted", "done"];

const STATUS_LABEL: Record<string, string> = {
  proposed: "Proposed",
  accepted: "Accepted",
  done: "Done",
};

export default function GlobalLineagePage(): React.ReactElement {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mergedLineage, setMergedLineage] = useState<JobLineageResponse | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const { data: jobs, isLoading: jobsLoading } = useQuery({
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
    <div className="flex flex-col h-full space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Global Lineage</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Merge lineage graphs across migrations to visualise cross-job data flow.
        </p>
      </div>

      <Tabs defaultValue="pipeline" className="flex flex-col flex-1 min-h-0">
        <TabsList className="w-fit">
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="datasets" disabled>Datasets</TabsTrigger>
          <TabsTrigger value="columns" disabled>Columns</TabsTrigger>
        </TabsList>

        <TabsContent value="pipeline" className="flex flex-1 min-h-0 gap-4 mt-4">
          <div className="w-72 shrink-0 flex flex-col gap-3">
            <p className="text-sm font-medium text-foreground">Migrations</p>
            {jobsLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : filteredJobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No completed migrations found.</p>
            ) : (
              <ScrollArea className="flex-1 rounded-md border border-border">
                <div className="p-2 space-y-1">
                  {filteredJobs.map((job) => (
                    <label
                      key={job.job_id}
                      className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-muted cursor-pointer"
                    >
                      <Checkbox
                        checked={selected.has(job.job_id)}
                        onCheckedChange={() => toggleJob(job.job_id)}
                        aria-label={`Select migration ${job.name ?? job.job_id}`}
                      />
                      <span className="flex-1 text-sm text-foreground truncate">
                        {job.name ?? job.job_id}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {STATUS_LABEL[job.status] ?? job.status}
                      </span>
                    </label>
                  ))}
                </div>
              </ScrollArea>
            )}

            <Button
              onClick={() => void handleConnect()}
              disabled={selected.size === 0 || isConnecting}
              className="w-full"
            >
              {isConnecting ? "Connecting…" : "Connect"}
            </Button>

            {connectError && (
              <p className="text-xs text-destructive">{connectError}</p>
            )}
          </div>

          <div className="flex-1 min-h-0 rounded-md border border-border overflow-hidden">
            {isConnecting ? (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                Loading lineage data…
              </div>
            ) : mergedLineage ? (
              <LineageGraph lineage={mergedLineage} />
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                Select migrations and click Connect to visualise the pipeline.
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
