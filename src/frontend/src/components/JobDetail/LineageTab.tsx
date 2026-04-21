import { getJobLineage } from "@/api/jobs";
import LineageGraph from "@/components/LineageGraph";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

export default function LineageTab({ jobId }: { jobId: string }): React.ReactElement {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["job", jobId, "lineage"],
    queryFn: () => getJobLineage(jobId),
    enabled: !!jobId,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading lineage…
      </div>
    );
  }

  if (isError) {
    const msg = error instanceof Error ? error.message : "Unknown error";
    if (msg.includes("202") || msg.toLowerCase().includes("not ready")) {
      return (
        <p className="text-sm text-muted-foreground">
          Lineage not yet available.
        </p>
      );
    }
    toast.error("Lineage data could not be loaded. Please try again later.");
    return (
      <p className="text-sm text-muted-foreground">Could not load lineage.</p>
    );
  }

  if (!data) {
    return (
      <p className="text-sm text-muted-foreground">
        Lineage not yet available.
      </p>
    );
  }

  return (
    <div className="h-full min-h-0 pb-6">
      <LineageGraph lineage={data} />
    </div>
  );
}
