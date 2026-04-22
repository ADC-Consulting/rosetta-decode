import { explainFiles, explainJob } from "@/api/explain";
import { listJobs } from "@/api/jobs";
import type { ExplainResponse, JobSummary } from "@/api/types";
import ChatInput from "@/components/Explain/ChatInput";
import ContextBanner from "@/components/Explain/ContextBanner";
import type { ChatMessage } from "@/components/Explain/MessageList";
import MessageList from "@/components/Explain/MessageList";
import MigrationPanel from "@/components/Explain/MigrationPanel";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useReducer, useRef } from "react";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

type ExplainMode = "migration" | "upload";

interface ExplainState {
  mode: ExplainMode;
  messages: ChatMessage[];
  attachedFiles: File[];
  selectedJobId: string | null;
  selectedJobName: string | null;
  jobSearchQuery: string;
  panelOpen: boolean;
  drawerOpen: boolean;
  inputValue: string;
  confirmSwitch: boolean;
  pendingSwitchMode: ExplainMode | null;
}

type ExplainAction =
  | { type: "SET_MODE"; mode: ExplainMode }
  | { type: "ADD_MESSAGE"; message: ChatMessage }
  | { type: "UPDATE_LAST_ASSISTANT"; content: string }
  | { type: "ATTACH_FILES"; files: File[] }
  | { type: "REMOVE_FILE"; name: string }
  | { type: "SELECT_JOB"; job: JobSummary }
  | { type: "CLEAR_CONTEXT" }
  | { type: "SET_JOB_SEARCH"; query: string }
  | { type: "TOGGLE_PANEL" }
  | { type: "SET_DRAWER_OPEN"; open: boolean }
  | { type: "SET_INPUT"; value: string }
  | { type: "CONFIRM_SWITCH" }
  | { type: "CANCEL_SWITCH" }
  | { type: "REQUEST_SWITCH"; mode: ExplainMode };

function reducer(state: ExplainState, action: ExplainAction): ExplainState {
  switch (action.type) {
    case "SET_MODE":
      return {
        ...state,
        mode: action.mode,
        messages: [],
        attachedFiles: [],
        selectedJobId: null,
        selectedJobName: null,
        confirmSwitch: false,
        pendingSwitchMode: null,
      };
    case "ADD_MESSAGE":
      return { ...state, messages: [...state.messages, action.message] };
    case "UPDATE_LAST_ASSISTANT": {
      const msgs = [...state.messages];
      const lastIdx = msgs.map((m) => m.role).lastIndexOf("assistant");
      if (lastIdx !== -1) {
        msgs[lastIdx] = { ...msgs[lastIdx], content: action.content, isLoading: false };
      }
      return { ...state, messages: msgs };
    }
    case "ATTACH_FILES":
      return {
        ...state,
        attachedFiles: [
          ...state.attachedFiles,
          ...action.files.filter(
            (f) => !state.attachedFiles.some((a) => a.name === f.name),
          ),
        ],
      };
    case "REMOVE_FILE":
      return {
        ...state,
        attachedFiles: state.attachedFiles.filter((f) => f.name !== action.name),
      };
    case "SELECT_JOB":
      return {
        ...state,
        selectedJobId: action.job.job_id,
        selectedJobName: action.job.name ?? `Job ${action.job.job_id.slice(0, 8)}`,
        drawerOpen: false,
      };
    case "CLEAR_CONTEXT":
      return {
        ...state,
        selectedJobId: null,
        selectedJobName: null,
        attachedFiles: [],
        messages: [],
      };
    case "SET_JOB_SEARCH":
      return { ...state, jobSearchQuery: action.query };
    case "TOGGLE_PANEL":
      return { ...state, panelOpen: !state.panelOpen };
    case "SET_DRAWER_OPEN":
      return { ...state, drawerOpen: action.open };
    case "SET_INPUT":
      return { ...state, inputValue: action.value };
    case "REQUEST_SWITCH":
      if (state.messages.length > 0) {
        return { ...state, confirmSwitch: true, pendingSwitchMode: action.mode };
      }
      return {
        ...state,
        mode: action.mode,
        messages: [],
        attachedFiles: [],
        selectedJobId: null,
        selectedJobName: null,
      };
    case "CONFIRM_SWITCH":
      return {
        ...state,
        mode: state.pendingSwitchMode ?? state.mode,
        messages: [],
        attachedFiles: [],
        selectedJobId: null,
        selectedJobName: null,
        confirmSwitch: false,
        pendingSwitchMode: null,
      };
    case "CANCEL_SWITCH":
      return { ...state, confirmSwitch: false, pendingSwitchMode: null };
    default:
      return state;
  }
}

function initialState(): ExplainState {
  return {
    mode: "migration",
    messages: [],
    attachedFiles: [],
    selectedJobId: null,
    selectedJobName: null,
    jobSearchQuery: "",
    panelOpen: window.innerWidth > 768,
    drawerOpen: false,
    inputValue: "",
    confirmSwitch: false,
    pendingSwitchMode: null,
  };
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ExplainPage(): React.ReactElement {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const messageListRef = useRef<HTMLDivElement>(null);

  const { data: allJobs, isLoading: jobsLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    staleTime: 30_000,
  });

  const usableJobs = allJobs?.filter((j) =>
    ["proposed", "accepted", "done"].includes(j.status),
  );

  const explainMutation = useMutation<
    ExplainResponse,
    Error,
    {
      question: string;
      jobId: string | null;
      files: File[];
      priorMessages: ChatMessage[];
    }
  >({
    mutationFn: async ({ question, jobId, files, priorMessages }) => {
      const msgs = priorMessages.map((m) => ({ role: m.role, content: m.content }));
      if (jobId) return explainJob({ job_id: jobId, question, messages: msgs });
      return explainFiles(question, files, msgs);
    },
    onSuccess: (data) => {
      dispatch({ type: "UPDATE_LAST_ASSISTANT", content: data.answer });
    },
    onError: (err) => {
      dispatch({
        type: "UPDATE_LAST_ASSISTANT",
        content: "Sorry, something went wrong. Please try again.",
      });
      toast.error(err instanceof Error ? err.message : "Could not get an answer.");
    },
  });

  // Auto-scroll on new messages
  useEffect(() => {
    const el = messageListRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [state.messages.length]);

  function handleSend() {
    if (explainMutation.isPending) return;
    if (state.inputValue.trim() === "") return;

    const hasContext =
      state.mode === "migration"
        ? state.selectedJobId !== null
        : state.attachedFiles.length > 0;

    if (!hasContext) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: state.inputValue.trim(),
    };
    const loadingMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      isLoading: true,
    };

    dispatch({ type: "ADD_MESSAGE", message: userMsg });
    dispatch({ type: "ADD_MESSAGE", message: loadingMsg });
    dispatch({ type: "SET_INPUT", value: "" });

    const priorMessages = state.messages.filter((m) => !m.isLoading);

    explainMutation.mutate({
      question: userMsg.content,
      jobId: state.selectedJobId,
      files: state.attachedFiles,
      priorMessages,
    });
  }

  function handleSuggest(prompt: string) {
    dispatch({ type: "SET_INPUT", value: prompt });
  }

  const hasContext =
    state.mode === "migration"
      ? state.selectedJobId !== null
      : state.attachedFiles.length > 0;

  const inputDisabled = !hasContext;

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 128px)" }}>
      {/* Heading */}
      <div className="mb-4 flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Explain</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Ask questions about your SAS code and migrations.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="md:hidden"
          onClick={() => dispatch({ type: "SET_DRAWER_OPEN", open: true })}
        >
          Migrations
        </Button>
      </div>

      {/* Two-column layout */}
      <div className="flex flex-1 overflow-hidden gap-0 min-h-0">
        {/* Chat column */}
        <div className="flex flex-col flex-1 overflow-hidden min-w-0">
          <ContextBanner
            mode={state.mode}
            jobName={state.selectedJobName}
            fileCount={state.attachedFiles.length}
            onClear={() => dispatch({ type: "CLEAR_CONTEXT" })}
          />
          <MessageList
            messages={state.messages}
            listRef={messageListRef}
            mode={state.mode}
            hasContext={hasContext}
            onSuggest={handleSuggest}
          />
          <ChatInput
            value={state.inputValue}
            onChange={(v) => dispatch({ type: "SET_INPUT", value: v })}
            onSend={handleSend}
            onFilesAttached={(files) => {
              if (state.mode !== "upload") {
                dispatch({ type: "REQUEST_SWITCH", mode: "upload" });
              }
              dispatch({ type: "ATTACH_FILES", files });
            }}
            isLoading={explainMutation.isPending}
            disabled={inputDisabled}
            attachedFiles={state.attachedFiles}
            onRemoveFile={(name) => dispatch({ type: "REMOVE_FILE", name })}
          />
        </div>

        {/* Migration panel — desktop */}
        {state.panelOpen && (
          <div className="hidden md:flex flex-col w-70 shrink-0 border-l border-border ml-4 pl-4 overflow-hidden">
            <MigrationPanel
              jobs={usableJobs}
              isLoading={jobsLoading}
              selectedJobId={state.selectedJobId}
              searchQuery={state.jobSearchQuery}
              onSearchChange={(q) => dispatch({ type: "SET_JOB_SEARCH", query: q })}
              onSelectJob={(job) => {
                if (state.mode !== "migration") {
                  dispatch({ type: "REQUEST_SWITCH", mode: "migration" });
                }
                dispatch({ type: "SELECT_JOB", job });
              }}
              onSwitchToUpload={() => dispatch({ type: "REQUEST_SWITCH", mode: "upload" })}
            />
          </div>
        )}
      </div>

      {/* Mobile drawer */}
      {state.drawerOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden bg-black/40"
          onClick={() => dispatch({ type: "SET_DRAWER_OPEN", open: false })}
        >
          <div
            className="absolute inset-y-0 right-0 w-72 bg-background border-l border-border shadow-xl flex flex-col p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <MigrationPanel
              jobs={usableJobs}
              isLoading={jobsLoading}
              selectedJobId={state.selectedJobId}
              searchQuery={state.jobSearchQuery}
              onSearchChange={(q) => dispatch({ type: "SET_JOB_SEARCH", query: q })}
              onSelectJob={(job) => {
                if (state.mode !== "migration") {
                  dispatch({ type: "REQUEST_SWITCH", mode: "migration" });
                }
                dispatch({ type: "SELECT_JOB", job });
              }}
              onSwitchToUpload={() => dispatch({ type: "REQUEST_SWITCH", mode: "upload" })}
              onClose={() => dispatch({ type: "SET_DRAWER_OPEN", open: false })}
            />
          </div>
        </div>
      )}

      {/* Mode switch confirmation dialog */}
      <Dialog
        open={state.confirmSwitch}
        onOpenChange={(open) => {
          if (!open) dispatch({ type: "CANCEL_SWITCH" });
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Switch context?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Switching will clear the current conversation.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => dispatch({ type: "CANCEL_SWITCH" })}>
              Cancel
            </Button>
            <Button onClick={() => dispatch({ type: "CONFIRM_SWITCH" })}>Switch</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
