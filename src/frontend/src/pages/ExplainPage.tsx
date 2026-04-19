import { useRef } from "react";
import { Button } from "@/components/ui/button";

export default function ExplainPage(): React.ReactElement {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  return (
    <div className="flex flex-col h-full" style={{ minHeight: "calc(100vh - 128px)" }}>
      {/* Heading */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-foreground">Explain</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask questions about your SAS code and get plain-English explanations.
        </p>
      </div>

      {/* Message list — empty state, takes up available space */}
      <div
        className="flex-1 rounded-md border border-border bg-muted/20 flex items-center justify-center"
        aria-label="Conversation messages"
        aria-live="polite"
      >
        <p className="text-sm text-muted-foreground">No messages yet.</p>
      </div>

      {/* Input area pinned to bottom of the flex column */}
      <div className="mt-4 rounded-md border border-border bg-background p-3 space-y-2">
        <textarea
          ref={textareaRef}
          rows={3}
          disabled
          placeholder="Ask about a SAS construct, function, or pattern…"
          aria-label="Chat input"
          className="w-full resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none disabled:cursor-not-allowed disabled:opacity-50"
        />
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">Chat functionality coming soon.</p>
          <Button size="sm" disabled aria-label="Send message">
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}
