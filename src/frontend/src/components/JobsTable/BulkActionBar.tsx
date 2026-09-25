import { Button } from "@/components/ui/button";
import { Archive, ArchiveRestore, Download, Trash2, X } from "lucide-react";

interface BulkActionBarProps {
  selectedCount: number;
  onDownload: () => void;
  onArchive: () => void;
  onDeleteClick: () => void;
  onClear: () => void;
  isArchiving?: boolean;
  /** True when every selected row is already archived — flips the button to "Unarchive". */
  allSelectedArchived?: boolean;
}

/**
 * Replaces the search/filter/New-migration toolbar row while >=1 row is
 * selected, per the Manifest mockup (docs/design/MigrationsPage.dc.html).
 */
export default function BulkActionBar({
  selectedCount,
  onDownload,
  onArchive,
  onDeleteClick,
  onClear,
  isArchiving = false,
  allSelectedArchived = false,
}: BulkActionBarProps): React.ReactElement {
  return (
    <div className="flex items-center gap-3 rounded-md border border-border bg-muted/40 px-3 py-1.5">
      <span className="text-sm font-medium text-foreground">{selectedCount} selected</span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={onDownload}>
          <Download className="h-3.5 w-3.5" />
          Download
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onArchive}
          disabled={isArchiving}
          aria-busy={isArchiving}
        >
          {allSelectedArchived ? (
            <>
              <ArchiveRestore className="h-3.5 w-3.5" />
              Unarchive
            </>
          ) : (
            <>
              <Archive className="h-3.5 w-3.5" />
              Archive
            </>
          )}
        </Button>
        <Button variant="destructive" size="sm" onClick={onDeleteClick}>
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </Button>
      </div>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onClear}
        aria-label="Clear selection"
        className="ml-auto"
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
