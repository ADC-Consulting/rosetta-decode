import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface DeleteConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  count: number;
  onConfirm: () => void;
  isPending?: boolean;
}

/**
 * Shared confirm dialog for both single-row (kebab menu) and bulk delete.
 * Delete is a hard delete (see journal/DECISIONS.md 2026-09-24) — irreversible,
 * so this gate is required before either call fires.
 */
export default function DeleteConfirmDialog({
  open,
  onOpenChange,
  count,
  onConfirm,
  isPending = false,
}: DeleteConfirmDialogProps): React.ReactElement {
  const subject = count === 1 ? "this migration" : `these ${count} migrations`;
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            Delete {count === 1 ? "migration" : `${count} migrations`}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            This permanently deletes {subject} and all associated generated code, plans, and
            audit history. This cannot be undone — use Archive instead to hide it while keeping
            the record.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={onConfirm}
            disabled={isPending}
            aria-busy={isPending}
          >
            {isPending ? "Deleting…" : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
