import { Button } from "@/components/ui/button";
import { Paperclip } from "lucide-react";
import { useEffect, useRef } from "react";
import { FileIcon, TypeBadge } from "./shared";
import { fileExt } from "./utils";

interface ChatInputProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onFilesAttached: (files: File[]) => void;
  isLoading: boolean;
  disabled: boolean;
  attachedFiles: File[];
  onRemoveFile: (name: string) => void;
}

export default function ChatInput({
  value,
  onChange,
  onSend,
  onFilesAttached,
  isLoading,
  disabled,
  attachedFiles,
  onRemoveFile,
}: ChatInputProps): React.ReactElement {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + "px";
  }, [value]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="shrink-0 mt-2 rounded-md border border-border bg-background p-3 space-y-2">
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachedFiles.map((file) => {
            const ext = fileExt(file.name);
            return (
              <div
                key={file.name}
                className="flex items-center gap-1 px-2 py-1 rounded-full bg-muted text-xs"
              >
                <FileIcon ext={ext} className="h-3 w-3" />
                <TypeBadge ext={ext} />
                <span>{file.name}</span>
                <button
                  onClick={() => onRemoveFile(file.name)}
                  aria-label={`Remove ${file.name}`}
                  className="ml-0.5 text-muted-foreground hover:text-foreground"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      )}

      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? "Select a migration or attach files to start…" : "Ask a question…"}
        disabled={disabled || isLoading}
        aria-label="Chat input"
        className="w-full resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none disabled:cursor-not-allowed disabled:opacity-50 max-h-40 overflow-y-auto"
      />

      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          aria-label="Attach files"
        >
          <Paperclip className="size-4" />
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".sas,.sas7bdat,.csv,.log,.xls,.xlsx,.zip"
          className="sr-only"
          onChange={(e) => {
            if (e.target.files) onFilesAttached(Array.from(e.target.files));
            e.target.value = "";
          }}
        />
        <Button
          size="sm"
          onClick={onSend}
          disabled={disabled || isLoading || value.trim() === ""}
          aria-label="Send message"
        >
          Send
        </Button>
      </div>
    </div>
  );
}
