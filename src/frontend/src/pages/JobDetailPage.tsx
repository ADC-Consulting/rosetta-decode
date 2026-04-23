import {
  acceptJob,
  getJob,
  getJobDoc,
  getJobPlan,
  refineJob,
  saveVersion,
} from "@/api/jobs";
import type { BlockOverride, JobStatusValue } from "@/api/types";
// import ChangelogFeed from "@/components/JobDetail/ChangelogFeed";
import EditorTab from "@/components/JobDetail/EditorTab";
import LineageTab from "@/components/JobDetail/LineageTab";
import PlanTab from "@/components/JobDetail/PlanTab";
import ReportTab from "@/components/JobDetail/ReportTab";
import { StatusBadge } from "@/components/JobDetail/StatusBadge";
// import TrustReportTab from "@/components/JobDetail/TrustReportTab";
import {
  POLLING_STATUSES,
  TAB_CONTENT_HEIGHT,
} from "@/components/JobDetail/constants";
import VersionHistoryRail from "@/components/VersionHistoryRail";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
export { StatusBadge } from "@/components/JobDetail/StatusBadge";
export { STATUS_LABEL } from "@/components/JobDetail/constants";

export default function JobDetailPage(): React.ReactElement {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("plan");
  const [editorCode, setEditorCode] = useState<string | null>(null);
  const [editorRestoreKey, setEditorRestoreKey] = useState(0);
  const [reportRestoreKey, setReportRestoreKey] = useState(0);
  const [savedVersionId, setSavedVersionId] = useState<string | null>(null);
  const [overrideGeneratedFiles, setOverrideGeneratedFiles] = useState<Record<
    string,
    string
  > | null>(null);
  const [overrideDoc, setOverrideDoc] = useState<string | null>(null);
  const [planOverrides, setPlanOverrides] = useState<
    Record<string, BlockOverride>
  >({});

  // Confirmation / input dialogs
  const [showAcceptConfirm, setShowAcceptConfirm] = useState(false);
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

  const displayedEditorCode = editorCode ?? job?.python_code ?? "";

  const { data: docData } = useQuery({
    queryKey: ["job", id, "doc"],
    queryFn: () => getJobDoc(id),
    enabled: !!id && (job?.status === "proposed" || job?.status === "accepted"),
  });

  const currentDoc = overrideDoc ?? docData?.doc ?? null;

  const saveVersionMutation = useMutation({
    mutationFn: async () => {
      if (activeTab === "plan") {
        return saveVersion(id, "plan", {
          content: { block_overrides: Object.values(planOverrides) },
        });
      } else if (activeTab === "editor") {
        return saveVersion(id, "editor", {
          content: {
            python_code: displayedEditorCode,
            generated_files:
              overrideGeneratedFiles ?? job?.generated_files ?? {},
          },
        });
      } else if (activeTab === "report") {
        return saveVersion(id, "report", {
          content: { doc: currentDoc ?? "" },
        });
      }
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({
        queryKey: ["job", id, "versions", activeTab],
      });
      if (result?.id) setSavedVersionId(result.id);
      toast.success("Version saved.");
    },
    onError: (err) => {
      toast.error(
        err instanceof Error ? err.message : "Could not save changes.",
      );
    },
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
    mutationFn: () => acceptJob(id),
    onSuccess: () => {
      setShowAcceptConfirm(false);
      void queryClient.invalidateQueries({ queryKey: ["job", id] });
      toast.success("Migration accepted.");
    },
    onError: () => toast.error("Could not accept migration. Please try again."),
  });

  function handleRestore(content: Record<string, unknown>): void {
    setSavedVersionId(null);
    if (activeTab === "plan" && Array.isArray(content.block_overrides)) {
      const arr = content.block_overrides as BlockOverride[];
      setPlanOverrides(Object.fromEntries(arr.map((o) => [o.block_id, o])));
    } else if (
      activeTab === "editor" &&
      typeof content.python_code === "string"
    ) {
      setEditorCode(content.python_code);
      const gf = content.generated_files;
      setOverrideGeneratedFiles(
        gf && typeof gf === "object" && !Array.isArray(gf)
          ? (gf as Record<string, string>)
          : {},
      );
      setEditorRestoreKey((k) => k + 1);
    } else if (activeTab === "report" && typeof content.doc === "string") {
      setOverrideDoc(content.doc);
      setReportRestoreKey((k) => k + 1);
    }
  }

  const shortId = id.length >= 8 ? `${id.slice(0, 8)}…` : id;

  const isReviewable = job?.status === "proposed" || job?.status === "accepted";

  const { data: planData } = useQuery({
    queryKey: ["job", id, "plan"],
    queryFn: () => getJobPlan(id),
    enabled: !!id && isReviewable,
  });

  return (
    <div className="px-6 py-8 overflow-y-auto flex-1 h-full">
      <Tabs
        value={activeTab}
        onValueChange={(v) => {
          setActiveTab(v);
          setSavedVersionId(null);
        }}
      >
        <div className="sticky top-0 z-20 bg-background border-border border-b pb-2">
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

          {/* Row 2: tabs bar + right-aligned action cluster */}
          <div className="flex items-center">
            <TabsList>
              <TabsTrigger value="plan" className="cursor-pointer">
                Plan
              </TabsTrigger>
              <TabsTrigger value="editor" className="cursor-pointer">
                Editor
              </TabsTrigger>
              <TabsTrigger value="report" className="cursor-pointer">
                Report
              </TabsTrigger>
              <TabsTrigger value="lineage" className="cursor-pointer">
                Lineage
              </TabsTrigger>
              {/* <TabsTrigger value="trust" className="cursor-pointer">
              Trust Report
            </TabsTrigger> */}
              {/* <TabsTrigger value="history" className="cursor-pointer">
              History
            </TabsTrigger> */}
            </TabsList>

            <div className="ml-auto flex items-center gap-2">
              {activeTab !== "lineage" &&
                activeTab !== "trust" &&
                activeTab !== "history" && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => saveVersionMutation.mutate()}
                    disabled={saveVersionMutation.isPending}
                    className="cursor-pointer"
                  >
                    {saveVersionMutation.isPending ? "Saving" : "Save Changes"}
                  </Button>
                )}

              {isReviewable && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowRefineDialog(true)}
                  disabled={refineMutation.isPending}
                  className="cursor-pointer"
                >
                  Refine
                </Button>
              )}

              {job?.status === "proposed" && (
                <Button
                  size="sm"
                  onClick={() => setShowAcceptConfirm(true)}
                  disabled={acceptMutation.isPending}
                  className="cursor-pointer"
                >
                  Accept migration
                </Button>
              )}

              {job?.status === "accepted" && (
                <span className="text-sm text-emerald-600 font-medium">
                  ✓ Accepted
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Shared-height content box */}
        <div
          className="flex gap-3 items-stretch pt-4"
          style={{ height: TAB_CONTENT_HEIGHT }}
        >
          <div className="flex-1 min-w-0 flex flex-col min-h-0">
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
              />
            </TabsContent>

            <TabsContent value="editor" className="mt-0 flex-1 min-h-0">
              <EditorTab
                key={editorRestoreKey}
                jobId={id}
                generatedFiles={
                  overrideGeneratedFiles ?? job?.generated_files ?? null
                }
                onGeneratedFilesChange={setOverrideGeneratedFiles}
                code={displayedEditorCode}
                setCode={(v) => setEditorCode(v)}
              />
            </TabsContent>

            <TabsContent value="report" className="mt-0 flex-1 min-h-0">
              <ReportTab
                isDone={isReviewable}
                doc={currentDoc}
                onDocChange={setOverrideDoc}
                restoreKey={reportRestoreKey}
                nonTechnicalDoc={docData?.non_technical_doc ?? null}
              />
            </TabsContent>

            <TabsContent value="lineage" className="mt-0 flex-1 min-h-0">
              <LineageTab jobId={id} blockPlans={planData?.block_plans} />
            </TabsContent>

            {/* <TabsContent value="trust" className="mt-0 flex-1 min-h-0">
            <TrustReportTab jobId={id} jobStatus={job?.status ?? "queued"} />
          </TabsContent> */}

            {/* <TabsContent value="history" className="mt-0 flex-1 min-h-0 overflow-y-auto">
            <div className="px-4 py-4">
              <h2 className="text-sm font-semibold text-foreground mb-4">Refinement History</h2>
              <ChangelogFeed jobId={id} />
            </div>
          </TabsContent> */}
          </div>

          {(activeTab === "editor" || activeTab === "report") && (
            <VersionHistoryRail
              jobId={id}
              tab={activeTab as "editor" | "report"}
              className="shrink-0 overflow-y-auto"
              selectedVersionId={savedVersionId}
              onRestore={handleRestore}
            />
          )}
        </div>

        {/* Accept-migration confirmation */}
        <Dialog open={showAcceptConfirm} onOpenChange={setShowAcceptConfirm}>
          <DialogContent className="max-w-md">
            <div className="space-y-2">
              <h2 className="text-base font-semibold">Accept migration</h2>
              <p className="text-sm text-muted-foreground">
                Are you sure you want to finalize the migration? This will mark
                the job as accepted.
              </p>
            </div>
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
