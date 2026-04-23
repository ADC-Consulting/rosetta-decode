import { Bot, User } from "lucide-react";
import EmptyState from "./EmptyState";
import MarkdownRenderer from "./MarkdownRenderer";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isLoading?: boolean;
  timestamp?: string;
}

interface MessageListProps {
  messages: ChatMessage[];
  listRef: React.RefObject<HTMLDivElement | null>;
  mode: "migration" | "upload";
  hasContext: boolean;
  onSuggest: (prompt: string) => void;
}

export default function MessageList({
  messages,
  listRef,
  mode,
  hasContext,
  onSuggest,
}: MessageListProps): React.ReactElement {
  return (
    <div
      ref={listRef}
      className="flex-1 overflow-y-auto py-6 space-y-6"
      aria-live="polite"
      aria-label="Conversation messages"
    >
      {messages.length === 0 ? (
        <EmptyState mode={mode} hasContext={hasContext} onSuggest={onSuggest} />
      ) : (
        messages.map((msg) =>
          msg.role === "user" ? (
            <div key={msg.id} className="flex flex-col items-end gap-1">
              <div className="flex items-start gap-2 justify-end">
                <div className="rounded-2xl px-4 py-2 max-w-[80%] bg-primary text-primary-foreground">
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
                <User className="mt-2 shrink-0 size-4 text-muted-foreground" />
              </div>
              {msg.timestamp && (
                <span className="text-xs text-muted-foreground pr-6">
                  {new Date(msg.timestamp).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              )}
            </div>
          ) : (
            <div key={msg.id} className="flex items-start gap-3">
              <Bot className="mt-1.5 shrink-0 size-[18px] text-muted-foreground" />
              <div className="flex-1 min-w-0">
                {msg.isLoading ? (
                  <div className="rounded-xl bg-muted/50 border border-border px-4 py-3">
                    <div className="flex gap-1 items-center">
                      <span className="size-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.3s]" />
                      <span className="size-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.15s]" />
                      <span className="size-2 rounded-full bg-muted-foreground animate-bounce" />
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl bg-muted/50 border border-border px-4 py-3">
                    <MarkdownRenderer content={msg.content} />
                  </div>
                )}
                {msg.timestamp && (
                  <span className="text-xs text-muted-foreground mt-1 block">
                    {new Date(msg.timestamp).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                )}
              </div>
            </div>
          ),
        )
      )}
    </div>
  );
}
