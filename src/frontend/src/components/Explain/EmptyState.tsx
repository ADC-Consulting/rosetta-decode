import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  mode: "migration" | "upload";
  hasContext: boolean;
  onSuggest: (prompt: string) => void;
}

const MIGRATION_CHIPS = [
  "What does this migration do?",
  "Which blocks need manual review?",
  "What are the key transformations?",
];

const UPLOAD_CHIPS = [
  "Explain this SAS macro",
  "What datasets does this read?",
  "Summarize what this program does",
];

export default function EmptyState({ mode, hasContext, onSuggest }: EmptyStateProps): React.ReactElement {
  if (!hasContext) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
        <p className="text-sm">
          {mode === "migration"
            ? "Select a migration from the panel to get started"
            : "Attach a SAS file below to get started"}
        </p>
      </div>
    );
  }

  const chips = mode === "migration" ? MIGRATION_CHIPS : UPLOAD_CHIPS;

  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
      <p className="text-sm">What would you like to know?</p>
      <div className="flex flex-wrap justify-center gap-2">
        {chips.map((text) => (
          <Button key={text} variant="outline" size="sm" onClick={() => onSuggest(text)}>
            {text}
          </Button>
        ))}
      </div>
    </div>
  );
}
