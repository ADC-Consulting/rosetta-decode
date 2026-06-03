import { getJobLineage } from "@/api/jobs";
import type { BlockPlan } from "@/api/types";
import LineageGraph from "@/components/LineageGraph";
import { useQuery } from "@tanstack/react-query";

export default function LineageTab({
  jobId,
  blockPlans,
}: {
  jobId: string;
  blockPlans?: BlockPlan[];
}): React.ReactElement {
  const { data, isLoading, isError } = useQuery({
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
    return (
      <p className="text-sm text-muted-foreground">
        Lineage not yet available.
      </p>
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
      <LineageGraph lineage={data} blockPlans={blockPlans} />
    </div>
  );
}
