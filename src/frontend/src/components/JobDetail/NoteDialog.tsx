import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { MessageSquarePlus, MessageSquareText } from "lucide-react";
import { useState } from "react";

export default function NoteDialog({
  blockId,
  currentNote,
  isSaving,
  onSave,
}: {
  blockId: string;
  currentNote: string;
  isSaving: boolean;
  onSave: (blockId: string, value: string) => void;
}): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");

  const hasNote = currentNote.trim().length > 0;
  const Icon = hasNote ? MessageSquareText : MessageSquarePlus;

  const handleOpen = (): void => {
    setDraft(currentNote);
    setOpen(true);
  };

  const handleSave = (): void => {
    onSave(blockId, draft);
    setOpen(false);
  };

  return (
    <div className="flex items-center justify-center">
      <button
        onClick={handleOpen}
        className={cn(
          "cursor-pointer inline-flex items-center justify-center rounded p-1 transition-colors",
          hasNote
            ? "text-primary hover:bg-primary/10"
            : "text-muted-foreground hover:text-foreground hover:bg-muted",
        )}
        aria-label={
          hasNote ? `Edit note for ${blockId}` : `Add note for ${blockId}`
        }
        title={hasNote ? "Edit note" : "Add note"}
      >
        <Icon className={cn("size-4 shrink-0", isSaving && "animate-pulse")} />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl">
          <textarea
            className={cn(
              "w-full min-h-48 resize-y rounded-md border border-input bg-background",
              "px-3 py-2 text-sm placeholder:text-muted-foreground",
              "focus:outline-none focus:ring-1 focus:ring-ring",
            )}
            placeholder="Add a note for the Agent"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoFocus
          />
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOpen(false)}
              className="cursor-pointer"
            >
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} className="cursor-pointer">
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
