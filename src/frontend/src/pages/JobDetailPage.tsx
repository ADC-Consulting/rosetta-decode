import {
  acceptJob,
  downloadJob,
  getJob,
  getJobPlan,
  getJobSources,
  getJobTrustReport,
  refineJob,
} from "@/api/jobs";
import type {
  BlockOverride,
  DeploymentTarget,
  JobStatusValue,
} from "@/api/types";
// import ChangelogFeed from "@/components/JobDetail/ChangelogFeed";
import ChevronTabBar from "@/components/JobDetail/ChevronTabBar";
import DeploymentTargetFields from "@/components/JobDetail/DeploymentTargetFields";
import DataStorageTab from "@/components/JobDetail/DataStorageTab";
import ETLTab from "@/components/JobDetail/ETLTab";
import PlanTab from "@/components/JobDetail/PlanTab";
// import ReportTab from "@/components/JobDetail/ReportTab"; // restored in #41
import { StatusBadge } from "@/components/JobDetail/StatusBadge";
// import VersionHistoryRail from "@/components/VersionHistoryRail"; // restored in #41
import {
  POLLING_STATUSES,
  TAB_CONTENT_HEIGHT,
} from "@/components/JobDetail/constants";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Download } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
export { STATUS_LABEL } from "@/components/JobDetail/constants";
export { StatusBadge } from "@/components/JobDetail/StatusBadge";

export default function JobDetailPage(): React.ReactElement {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(searchParams.get("tab") ?? "plan");
  const [, setEditorCode] = useState<string | null>(null);
  const [planOverrides, setPlanOverrides] = useState<
    Record<string, BlockOverride>
  >({});

  // Confirmation / input dialogs
  const [showAcceptConfirm, setShowAcceptConfirm] = useState(false);
  const [deploymentTarget, setDeploymentTarget] = useState<DeploymentTarget>({
    delivery_format: "dlt",
    provider: "azure",
    ingestion_approach: "historical",
    compute_mode: "serverless",
  });
  const [showRefineDialog, setShowRefineDialog] = useState(false);
  const [refineHint, setRefineHint] = useState("");

  const queryClient = useQueryClient();

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

  const refineMutation = useMutation({
    mutationFn: () => refineJob(id, refineHint.trim() || undefined),
    onSuccess: (data) => {
      setShowRefineDialog(false);
      setRefineHint("");
      navigate(`/jobs/${data.job_id}`);
    },
    onError: (err) => {
      toast.error(
        err instanceof Error
          ? err.message
          : "The refinement request could not be submitted. Please try again.",
      );
    },
  });

  const acceptMutation = useMutation({
    mutationFn: () => acceptJob(id, deploymentTarget),
    onSuccess: () => {
      setShowAcceptConfirm(false);
      void queryClient.invalidateQueries({ queryKey: ["job", id] });
      toast.success("Migration accepted.");
    },
    onError: () => toast.error("Could not accept migration. Please try again."),
  });

  const shortId = id.length >= 8 ? `${id.slice(0, 8)}…` : id;

  const isAccepted = job?.status === "accepted";
  const isReviewable = job?.status === "proposed" || job?.status === "accepted" || job?.status === "under_review";

  const handleDownload = async () => {
    try {
      const blob = await downloadJob(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `rosetta-${id}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Download failed");
    }
  };

  const { data: planData } = useQuery({
    queryKey: ["job", id, "plan"],
    queryFn: () => getJobPlan(id),
    enabled: !!id && isReviewable,
  });

  const { data: trustReportData } = useQuery({
    queryKey: ["job", id, "trust-report"],
    queryFn: () => getJobTrustReport(id),
    enabled: !!id && isReviewable,
  });

  const { data: jobSourcesData } = useQuery({
    queryKey: ["job", id, "sources"],
    queryFn: () => getJobSources(id),
    enabled: !!id && isReviewable,
  });
  const jobSources = jobSourcesData?.sources ?? undefined;

  return (
    <div className="px-6 py-2 overflow-y-auto flex-1 h-full">
      <Tabs
        value={activeTab}
        onValueChange={(v) => {
          setActiveTab(v);
          setSearchParams({ tab: v });
        }}
      >
        <div
          className={cn(
            "brand-manifest sticky top-0 z-20 bg-background border-border border-b pb-2",
            // F89 margin fix: the outer JobDetailPage scroll container already applies `px-6`
            // (24px). Plan tab needs a ~40px total inset to match PlanTab.tsx's content root, so
            // add 16px more here, scoped to the Plan tab only — ETL/Data/BI/AI keep the shared 24px.
            activeTab === "plan" && "px-4",
          )}
        >
          {/* Row 1: back button left, name + status centered */}
          <div className="relative flex items-center justify-center py-3">
            <button
              type="button"
              onClick={() => navigate("/jobs")}
              className="absolute left-0 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              aria-label="Back to migrations list"
            >
              <ArrowLeft size={18} />
            </button>
            <div className="flex items-center gap-3">
              <span className="text-xl font-semibold text-foreground truncate">
                {job?.name ?? shortId}
              </span>
              {job && <StatusBadge status={job.status} />}
            </div>
          </div>

          {/* Row 2: files/steps subtitle left, action cluster right */}
          <div className="flex items-center justify-between pb-2">
            <span className="text-xs text-muted-foreground">
              {planData && (
                <>
                  {new Set(planData.block_plans.map((b) => b.source_file)).size} files
                  {" · "}
                  {planData.block_plans.length} steps
                </>
              )}
            </span>

            <div className="flex items-center gap-2">
              {isAccepted ? (
                <>
                  <Badge
                    variant="outline"
                    className="flex items-center gap-1.5 border-emerald-300 bg-emerald-50 text-emerald-700 px-2.5 py-1 text-xs font-medium"
                    aria-label="Migration accepted"
                  >
                    <CheckCircle2 size={12} className="shrink-0" />
                    Accepted
                    {job?.accepted_at && (
                      <span className="ml-1 text-emerald-600 font-normal">
                        {new Date(job.accepted_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </span>
                    )}
                  </Badge>
                  <Button
                    size="sm"
                    onClick={() => { void handleDownload(); }}
                    className="cursor-pointer flex items-center gap-1.5 bg-[var(--primary)] text-[var(--primary-foreground)]"
                    aria-label="Download migration package"
                  >
                    <Download size={14} />
                    Download migration package
                  </Button>
                </>
              ) : (
                <>
                  {(job?.status === "proposed" || job?.status === "under_review") && (
                    <>
                      {job?.status === "under_review" && (
                        <span className="text-sm text-amber-600 font-medium px-2 py-1 bg-amber-50 rounded border border-amber-200">
                          Under review — reconciliation failed
                        </span>
                      )}
                      <Button
                        size="sm"
                        onClick={() => setShowAcceptConfirm(true)}
                        disabled={acceptMutation.isPending}
                        className="cursor-pointer bg-[var(--primary)] text-[var(--primary-foreground)]"
                      >
                        Accept migration
                      </Button>
                    </>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Row 3: tab bar alone */}
          <div className="flex items-center">
            <ChevronTabBar activeTab={activeTab} />
          </div>
        </div>

        {/* Shared-height content box */}
        <div
          className="flex gap-3 items-stretch pt-4"
          style={{ height: TAB_CONTENT_HEIGHT }}
        >
          <div className="flex-1 min-w-0 flex flex-col min-h-0">
            {/* plan tab */}
            <TabsContent value="plan" className="mt-0 flex-1 min-h-0">
              <PlanTab
                jobId={id}
                isReviewable={isReviewable}
                jobStatus={job?.status ?? "queued"}
                report={job?.report ?? null}
                overrides={planOverrides}
                setOverrides={setPlanOverrides}
                onBlockRefineSuccess={() => setEditorCode(null)}
                jobPythonCode={job?.python_code ?? undefined}
                generatedFiles={job?.generated_files ?? undefined}
                isAccepted={isAccepted}
                acceptedAt={job?.accepted_at ?? null}
                onSwitchToEtlTab={() => {
                  setActiveTab("etl");
                  setSearchParams({ tab: "etl" });
                }}
              />
            </TabsContent>

            {/* etl tab: ETL orchestration review */}
            <TabsContent value="etl" className="mt-0 flex-1 min-h-0 flex flex-col">
              <ETLTab
                jobId={id}
                blockPlans={planData?.block_plans ?? []}
                trustReport={trustReportData}
                jobSources={jobSources}
                isReviewable={isReviewable}
                isAccepted={isAccepted}
                generatedFiles={job?.generated_files ?? null}
              />
            </TabsContent>

            {/* report tab: commented out — will be restored in #41 */}
            {/* <TabsContent value="report" className="mt-0 flex-1 min-h-0">
              <div className="flex gap-3 h-full min-h-0">
                <div className="flex-1 min-w-0 min-h-0">
                  <ReportTab
                    isDone={isReviewable}
                    doc={currentDoc}
                    onDocChange={setOverrideDoc}
                    restoreKey={reportRestoreKey}
                    nonTechnicalDoc={docData?.non_technical_doc ?? null}
                    onSave={() => saveVersionMutation.mutate()}
                    isSaving={saveVersionMutation.isPending}
                  />
                </div>
                {isReviewable && (
                  <VersionHistoryRail
                    jobId={id}
                    tab="report"
                    className="shrink-0"
                    onRestore={(content) => {
                      const restored = content as Record<string, unknown>;
                      if (typeof restored.doc === "string") {
                        setOverrideDoc(restored.doc);
                        setReportRestoreKey((k) => k + 1);
                      }
                    }}
                  />
                )}
              </div>
            </TabsContent> */}

            {/* data-storage tab */}
            <TabsContent value="data-storage" className="mt-0 flex-1 min-h-0">
              <DataStorageTab jobId={id} isReviewable={isReviewable} />
            </TabsContent>

            {/* bi tab: placeholder */}
            <TabsContent value="bi" className="mt-0 flex-1 min-h-0">
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
                <span className="text-sm font-medium">BI</span>
                <span className="text-xs">Coming soon</span>
              </div>
            </TabsContent>

            {/* ai tab: placeholder */}
            <TabsContent value="ai" className="mt-0 flex-1 min-h-0">
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
                <span className="text-sm font-medium">AI</span>
                <span className="text-xs">Coming soon</span>
              </div>
            </TabsContent>

            {/* <TabsContent value="history" className="mt-0 flex-1 min-h-0 overflow-y-auto">
            <div className="px-4 py-4">
              <h2 className="text-sm font-semibold text-foreground mb-4">Refinement History</h2>
              <ChangelogFeed jobId={id} />
            </div>
          </TabsContent> */}
          </div>
        </div>

        {/* Accept-migration confirmation */}
        <Dialog open={showAcceptConfirm} onOpenChange={setShowAcceptConfirm}>
          <DialogContent className="max-w-lg">
            <div className="space-y-2">
              <h2 className="text-base font-semibold">Accept migration</h2>
              <p className="text-sm text-muted-foreground">
                Finalizing marks the job as accepted. Choose the deployment
                target for the generated Databricks bundle.
              </p>
            </div>
            <DeploymentTargetFields
              value={deploymentTarget}
              onChange={setDeploymentTarget}
              disabled={acceptMutation.isPending}
            />
            <DialogFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowAcceptConfirm(false)}
                className="cursor-pointer"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => acceptMutation.mutate()}
                disabled={acceptMutation.isPending}
                className="cursor-pointer"
              >
                {acceptMutation.isPending ? "Accepting…" : "Yes, accept"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Refine-migration dialog (input + confirm) */}
        <Dialog
          open={showRefineDialog}
          onOpenChange={(o) => {
            setShowRefineDialog(o);
            if (!o) setRefineHint("");
          }}
        >
          <DialogContent className="max-w-xl">
            <div className="space-y-2">
              <h2 className="text-base font-semibold">Refine migration</h2>
              <p className="text-sm text-muted-foreground">
                Are you sure you want the agent to refine this migration based
                on your input? You can optionally provide a hint below.
              </p>
            </div>
            <textarea
              value={refineHint}
              onChange={(e) => setRefineHint(e.target.value)}
              placeholder="Describe what should be improved…"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-y min-h-28 focus:outline-none focus:ring-1 focus:ring-ring"
              autoFocus
            />
            <DialogFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowRefineDialog(false)}
                className="cursor-pointer"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => refineMutation.mutate()}
                disabled={refineMutation.isPending}
                className="cursor-pointer"
              >
                {refineMutation.isPending ? "Submitting…" : "Yes, refine"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </Tabs>
    </div>
  );
}
