import { Button } from "@/components/ui/button";

interface TabSaveBarProps {
  onSave?: () => void;
  isSaving?: boolean;
  saved?: boolean;
  saveLabel?: string;
  disabled?: boolean;
  children?: React.ReactNode;
}

export default function TabSaveBar({
  onSave,
  isSaving = false,
  saved = false,
  saveLabel = "Save",
  disabled = false,
  children,
}: TabSaveBarProps): React.ReactElement {
  return (
    <div className="flex items-center gap-3 pt-3 border-t border-border mt-4">
      {onSave !== undefined && (
        <Button
          size="sm"
          onClick={onSave}
          disabled={disabled || isSaving}
          className="cursor-pointer"
        >
          {isSaving ? "Saving" : saveLabel}
        </Button>
      )}
      {children}
      {saved && (
        <span className="text-xs text-emerald-500 transition-opacity">
          Saved.
        </span>
      )}
    </div>
  );
}
