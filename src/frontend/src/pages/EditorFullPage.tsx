import { getJob, getJobPlan } from "@/api/jobs";
import type { JobStatusValue } from "@/api/types";
import EditorTab from "@/components/JobDetail/EditorTab";
import { POLLING_STATUSES } from "@/components/JobDetail/constants";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

export default function EditorFullPage(): React.ReactElement {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: job } = useQuery({
    queryKey: ["job", id],
    queryFn: () => getJob(id),
    enabled: !!id,
    refetchInterval: (q) =>
      q.state.data?.status !== undefined &&
      POLLING_STATUSES.includes(q.state.data.status as JobStatusValue)
        ? 3000
        : false,
  });

  const { data: planData } = useQuery({
    queryKey: ["job", id, "plan"],
    queryFn: () => getJobPlan(id),
    enabled: !!id,
  });

  return (
    <div className="h-screen flex flex-col">
      <div className="flex-1 min-h-0 p-2">
        <EditorTab
          jobId={id}
          generatedFiles={job?.generated_files ?? null}
          code={job?.python_code ?? ""}
          setCode={() => {}}
          blockPlans={planData?.block_plans ?? []}
          isFullPage
          onExpand={() => navigate(`/jobs/${id}?tab=editor`)}
        />
      </div>
    </div>
  );
}
