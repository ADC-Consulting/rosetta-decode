import {
  createExplainSession,
  explainFilesStream,
  explainJobStream,
  getExplainSession,
  listExplainSessions,
} from "@/api/explain";
import { listJobs } from "@/api/jobs";
import type { ExplainSessionResponse, JobSummary } from "@/api/types";
import ChatInput from "@/components/Explain/ChatInput";
import type { ChatMessage } from "@/components/Explain/MessageList";
import MessageList from "@/components/Explain/MessageList";
import RightSidebar from "@/components/RightSidebar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useReducer, useRef, useState } from "react";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

type ExplainMode = "migration" | "sas_general";

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
  sessionId: string | null;
  audience: "tech" | "non_tech";
  isLoading: boolean;
  attachedFileName: string | null;
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
  | { type: "REQUEST_SWITCH"; mode: ExplainMode }
  | { type: "SET_SESSION"; sessionId: string }
  | { type: "SET_AUDIENCE"; audience: "tech" | "non_tech" }
  | { type: "SET_LOADING"; value: boolean }
  | { type: "SET_ATTACHED_FILE_NAME"; payload: string | null }
  | { type: "SET_RECENT_SESSIONS"; payload: ExplainSessionResponse[] };

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
        sessionId: null,
      };
    case "ADD_MESSAGE":
      return { ...state, messages: [...state.messages, action.message] };
    case "UPDATE_LAST_ASSISTANT": {
      const msgs = [...state.messages];
      const lastIdx = msgs.map((m) => m.role).lastIndexOf("assistant");
      if (lastIdx !== -1) {
        msgs[lastIdx] = {
          ...msgs[lastIdx],
          content: action.content,
          isLoading: false,
        };
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
        attachedFiles: state.attachedFiles.filter(
          (f) => f.name !== action.name,
        ),
      };
    case "SELECT_JOB":
      return {
        ...state,
        selectedJobId: action.job.job_id,
        selectedJobName:
          action.job.name ?? `Job ${action.job.job_id.slice(0, 8)}`,
        drawerOpen: false,
      };
    case "CLEAR_CONTEXT":
      return {
        ...state,
        selectedJobId: null,
        selectedJobName: null,
        attachedFiles: [],
        messages: [],
        sessionId: null,
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
        return {
          ...state,
          confirmSwitch: true,
          pendingSwitchMode: action.mode,
        };
      }
      return {
        ...state,
        mode: action.mode,
        messages: [],
        attachedFiles: [],
        selectedJobId: null,
        selectedJobName: null,
        sessionId: null,
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
        sessionId: null,
      };
    case "CANCEL_SWITCH":
      return { ...state, confirmSwitch: false, pendingSwitchMode: null };
    case "SET_SESSION":
      return { ...state, sessionId: action.sessionId };
    case "SET_AUDIENCE":
      return { ...state, audience: action.audience };
    case "SET_LOADING":
      return { ...state, isLoading: action.value };
    case "SET_ATTACHED_FILE_NAME":
      return { ...state, attachedFileName: action.payload };
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
    sessionId: null,
    audience: "tech",
    isLoading: false,
    attachedFileName: null,
  };
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ExplainPage(): React.ReactElement {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const messageListRef = useRef<HTMLDivElement>(null);
  const [recentSessions, setRecentSessions] = useState<
    ExplainSessionResponse[]
  >([]);

  const { data: allJobs } = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    staleTime: 30_000,
  });

  const usableJobs = allJobs?.filter((j) =>
    ["proposed", "accepted", "done"].includes(j.status),
  );

  // Load recent sessions on mount
  useEffect(() => {
    listExplainSessions()
      .then((sessions) => setRecentSessions(sessions.slice(0, 5)))
      .catch(() => {
        // non-critical — ignore
      });
  }, []);

  // Auto-scroll on new messages
  useEffect(() => {
    const el = messageListRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [state.messages.length]);

  async function handleSend() {
    if (state.isLoading) return;
    if (state.inputValue.trim() === "") return;

    if (state.mode === "migration" && !state.selectedJobId) return;

    const question = state.inputValue.trim();
    dispatch({ type: "SET_INPUT", value: "" });

    // Create session on first message
    let currentSessionId = state.sessionId;
    if (!currentSessionId) {
      try {
        const session = await createExplainSession({
          mode: state.mode,
          job_id: state.selectedJobId ?? undefined,
          audience: state.audience,
          title: question.slice(0, 60),
          file_name:
            state.mode === "sas_general"
              ? (state.attachedFiles[0]?.name ?? null)
              : null,
        });
        currentSessionId = session.session_id;
        dispatch({ type: "SET_SESSION", sessionId: session.session_id });
        // Refetch sessions after creation
        listExplainSessions()
          .then((sessions) => setRecentSessions(sessions.slice(0, 5)))
          .catch(() => {});
      } catch {
        // non-critical — proceed without session
      }
    }

    // Optimistic user bubble
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
      timestamp: new Date().toISOString(),
    };
    const loadingMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      isLoading: true,
      timestamp: new Date().toISOString(),
    };
    dispatch({ type: "ADD_MESSAGE", message: userMsg });
    dispatch({ type: "ADD_MESSAGE", message: loadingMsg });
    dispatch({ type: "SET_LOADING", value: true });

    const priorMessages = state.messages
      .filter((m) => !m.isLoading)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      let full = "";
      const gen =
        state.mode === "migration" && state.selectedJobId
          ? explainJobStream(
              state.selectedJobId,
              question,
              priorMessages,
              state.audience,
              currentSessionId,
            )
          : explainFilesStream(
              question,
              state.attachedFiles,
              priorMessages,
              state.audience,
              currentSessionId,
              state.mode,
            );

      for await (const chunk of gen) {
        full += chunk;
        dispatch({ type: "UPDATE_LAST_ASSISTANT", content: full });
      }
      if (!full) {
        dispatch({ type: "UPDATE_LAST_ASSISTANT", content: "_(no response)_" });
      }
    } catch (err) {
      dispatch({
        type: "UPDATE_LAST_ASSISTANT",
        content: "Sorry, something went wrong. Please try again.",
      });
      toast.error(
        err instanceof Error ? err.message : "Could not get an answer.",
      );
    } finally {
      dispatch({ type: "SET_LOADING", value: false });
    }
  }

  async function handleRestoreSession(session: ExplainSessionResponse) {
    try {
      const full = await getExplainSession(session.session_id);
      dispatch({ type: "CONFIRM_SWITCH" }); // clear current state
      dispatch({ type: "SET_SESSION", sessionId: full.session_id });
      dispatch({ type: "SET_AUDIENCE", audience: full.audience as "tech" | "non_tech" });
      dispatch({ type: "SET_MODE", mode: full.mode });
      if (full.job_id) {
        dispatch({
          type: "SELECT_JOB",
          job: {
            job_id: full.job_id,
            name: full.title ?? full.job_id,
            status: "done",
            created_at: "",
            updated_at: "",
            error: null,
            file_count: 0,
          },
        });
      }
      if (full.file_name) {
        dispatch({ type: "SET_ATTACHED_FILE_NAME", payload: full.file_name });
      }
      for (const msg of full.messages) {
        dispatch({
          type: "ADD_MESSAGE",
          message: {
            id: crypto.randomUUID(),
            role: msg.role,
            content: msg.content,
          },
        });
      }
    } catch {
      toast.error("Could not restore session.");
    }
  }

  function handleSuggest(prompt: string) {
    dispatch({ type: "SET_INPUT", value: prompt });
  }

  const hasContext =
    state.mode === "migration"
      ? state.selectedJobId !== null
      : true; // sas_general: file is optional, chat is always open

  const inputDisabled = state.mode === "migration" && !state.selectedJobId;

  const contextLabel =
    state.mode === "migration" && state.selectedJobName
      ? `Asking about: ${state.selectedJobName}`
      : state.mode === "sas_general" && state.attachedFiles.length > 0
        ? `Asking about ${state.attachedFiles.length} file${state.attachedFiles.length !== 1 ? "s" : ""}`
        : null;

  const sessionFooter = (
    <div className="px-3 py-2 space-y-1">
      <button
        type="button"
        onClick={() => dispatch({ type: "CLEAR_CONTEXT" })}
        className="w-full text-left text-xs font-medium text-primary hover:opacity-80 py-0.5 mb-1"
      >
        + New Chat
      </button>
      {recentSessions.length > 0 && (
        <>
          <p className="text-xs font-medium text-muted-foreground mb-1">Recent sessions</p>
          {recentSessions.map((s) => {
            const modeBadge = s.mode === "migration" ? "M" : "S";
            const title = s.title ?? "Untitled";
            return (
              <button
                key={s.session_id}
                type="button"
                onClick={() => void handleRestoreSession(s)}
                className="w-full text-left text-xs text-muted-foreground hover:text-foreground truncate flex items-center gap-1 py-0.5"
              >
                <span className="shrink-0 inline-flex items-center justify-center size-4 rounded-sm bg-muted text-[10px] font-semibold text-muted-foreground">
                  {modeBadge}
                </span>
                <span className="truncate">{title}</span>
              </button>
            );
          })}
        </>
      )}
    </div>
  );

  const migrationItems = (usableJobs ?? []).map((job) => ({
    id: job.job_id,
    label: job.name ?? `Job ${job.job_id.slice(0, 8)}`,
    subtitle: job.status,
    isSelected: job.job_id === state.selectedJobId,
    onClick: () => {
      if (state.mode !== "migration") {
        dispatch({ type: "REQUEST_SWITCH", mode: "migration" });
      }
      dispatch({ type: "SELECT_JOB", job });
    },
  }));

  return (
    <div className="flex flex-1 min-h-0">
      {/* Main chat area — centered column */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden items-center px-4">
        {/* Mobile header */}
        <div className="flex items-center justify-between w-full h-10 border-b border-border shrink-0 md:hidden">
          <span className="text-sm font-semibold text-foreground">Explain</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => dispatch({ type: "SET_DRAWER_OPEN", open: true })}
          >
            Migrations
          </Button>
        </div>

        <div className="flex flex-col w-full max-w-190 h-full">
          {/* Mode tabs */}
          <div className="flex border-b border-border shrink-0">
            <button
              className={cn(
                "px-4 py-2 text-sm font-medium transition-colors",
                state.mode === "migration"
                  ? "border-b-2 border-primary text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
              onClick={() => dispatch({ type: "REQUEST_SWITCH", mode: "migration" })}
            >
              Migration Chat
            </button>
            <button
              className={cn(
                "px-4 py-2 text-sm font-medium transition-colors",
                state.mode === "sas_general"
                  ? "border-b-2 border-primary text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
              onClick={() => dispatch({ type: "REQUEST_SWITCH", mode: "sas_general" })}
            >
              SAS General
            </button>
          </div>
          <MessageList
            messages={state.messages}
            listRef={messageListRef}
            mode={state.mode}
            audience={state.audience}
            hasContext={hasContext}
            onSuggest={handleSuggest}
          />
          <div className="px-4 pb-6 pt-2 shrink-0">
            <ChatInput
              value={state.inputValue}
              onChange={(v) => dispatch({ type: "SET_INPUT", value: v })}
              onSend={() => void handleSend()}
              onFilesAttached={(files) => {
                if (state.mode !== "sas_general") {
                  dispatch({ type: "REQUEST_SWITCH", mode: "sas_general" });
                }
                dispatch({ type: "ATTACH_FILES", files });
              }}
              isLoading={state.isLoading}
              disabled={inputDisabled}
              attachedFiles={state.attachedFiles}
              onRemoveFile={(name) => dispatch({ type: "REMOVE_FILE", name })}
              audience={state.audience}
              onAudienceChange={(a) =>
                dispatch({ type: "SET_AUDIENCE", audience: a })
              }
              contextLabel={contextLabel}
              onClearContext={() => dispatch({ type: "CLEAR_CONTEXT" })}
              mode={state.mode}
            />
          </div>
        </div>
      </div>

      {/* Right panel — desktop */}
      <div className="hidden md:flex h-full">
        <RightSidebar
          title={state.mode === "migration" ? "Migrations" : "Chats"}
          sidebarKey="explain-sidebar-collapsed"
          items={state.mode === "migration" ? migrationItems : []}
          header={sessionFooter}
        />
      </div>

      {/* Mobile drawer */}
      {state.drawerOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden bg-black/40"
          onClick={() => dispatch({ type: "SET_DRAWER_OPEN", open: false })}
        >
          <div
            className="absolute inset-y-0 right-0 bg-background shadow-xl flex h-full"
            onClick={(e) => e.stopPropagation()}
          >
            <RightSidebar
              title={state.mode === "migration" ? "Migrations" : "Chats"}
              sidebarKey="explain-sidebar-collapsed"
              items={state.mode === "migration" ? migrationItems : []}
              header={sessionFooter}
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
            <Button
              variant="outline"
              onClick={() => dispatch({ type: "CANCEL_SWITCH" })}
            >
              Cancel
            </Button>
            <Button onClick={() => dispatch({ type: "CONFIRM_SWITCH" })}>
              Switch
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
