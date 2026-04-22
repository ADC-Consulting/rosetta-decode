import { refineBlock } from "@/api/jobs";
import type { BlockRefineResponse } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

interface BlockRefineDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  jobId: string;
  blockId: string;
  blockNote?: string | null;
  isAccepted?: boolean;
  onSuccess?: (response: BlockRefineResponse) => void;
}

export default function BlockRefineDialog({
  open,
  onOpenChange,
  jobId,
  blockId,
  blockNote,
  isAccepted,
  onSuccess,
}: BlockRefineDialogProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState(blockNote ?? "");
  const [hint, setHint] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleOpenChange = (next: boolean): void => {
    if (!loading) {
      if (next) {
        setNotes(blockNote ?? "");
        setHint("");
        setError(null);
      }
      onOpenChange(next);
    }
  };

  const handleSubmit = async (): Promise<void> => {
    if (!notes.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await refineBlock(jobId, blockId, {
        notes: notes.trim(),
        hint: hint.trim() || null,
      });
      await queryClient.invalidateQueries({
        queryKey: ["block-revisions", jobId, blockId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["trust-report", jobId],
      });
      await queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      toast.success(`Block refined — revision ${response.revision_number}`);
      onOpenChange(false);
      onSuccess?.(response);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "An unexpected error occurred",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-xl">
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-semibold leading-none tracking-tight">
              Refine block:{" "}
              <span className="font-mono text-sm text-muted-foreground">
                {blockId.replace(/:\d+$/, "")}
              </span>
            </h2>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="refine-notes"
              className="text-sm font-medium leading-none"
            >
              Your instructions{" "}
              <span className="text-destructive" aria-hidden>
                *
              </span>
            </label>
            <textarea
              id="refine-notes"
              rows={4}
              className={cn(
                "w-full resize-y rounded-md border border-input bg-background",
                "px-3 py-2 text-sm placeholder:text-muted-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring",
              )}
              placeholder={
                "Describe what needs to change — e.g. 'Use LEFT JOIN instead of INNER JOIN'" +
                " or 'RETAIN variable x must carry over to next row'"
              }
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              disabled={loading || isAccepted}
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="refine-hint"
              className="text-sm font-medium leading-none"
            >
              Auto-hint{" "}
              <span className="text-xs text-muted-foreground font-normal">
                (optional)
              </span>
            </label>
            <input
              id="refine-hint"
              type="text"
              className={cn(
                "w-full rounded-md border border-input bg-background",
                "px-3 py-2 text-sm placeholder:text-muted-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring",
              )}
              placeholder="Leave blank unless you have a specific reconciliation error to reference"
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              disabled={loading || isAccepted}
            />
          </div>

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleOpenChange(false)}
            disabled={loading}
            className="cursor-pointer"
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={() => void handleSubmit()}
            disabled={loading || isAccepted || !notes.trim()}
            className="cursor-pointer"
          >
            {loading ? (
              <>
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                Refining…
              </>
            ) : (
              "Refine"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
