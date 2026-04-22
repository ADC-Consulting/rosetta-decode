import { cn } from "@/lib/utils";
import EmptyState from "./EmptyState";
import MarkdownRenderer from "./MarkdownRenderer";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isLoading?: boolean;
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
      className="flex-1 overflow-y-auto p-4 space-y-4"
      aria-live="polite"
      aria-label="Conversation messages"
    >
      {messages.length === 0 ? (
        <EmptyState mode={mode} hasContext={hasContext} onSuggest={onSuggest} />
      ) : (
        messages.map((msg) => (
          <div
            key={msg.id}
            className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}
          >
            <div
              className={cn(
                "rounded-2xl px-4 py-2 max-w-[80%]",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground rounded-tr-sm"
                  : "bg-muted text-foreground rounded-tl-sm",
              )}
            >
              {msg.isLoading ? (
                <div className="flex gap-1 items-center py-1">
                  <span className="size-2 rounded-full bg-current animate-bounce [animation-delay:-0.3s]" />
                  <span className="size-2 rounded-full bg-current animate-bounce [animation-delay:-0.15s]" />
                  <span className="size-2 rounded-full bg-current animate-bounce" />
                </div>
              ) : msg.role === "user" ? (
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              ) : (
                <MarkdownRenderer content={msg.content} />
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
