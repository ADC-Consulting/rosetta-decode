import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  mode: "migration" | "upload";
  hasContext: boolean;
  onSuggest: (prompt: string) => void;
}

const ALL_CHIPS = [
  "Summarise this migration",
  "What are the high-risk blocks?",
  "Explain this PROC SQL step",
];

export default function EmptyState({
  onSuggest,
}: EmptyStateProps): React.ReactElement {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 text-center px-4">
      {/* Rosetta icon placeholder */}
      <div className="size-10 rounded-xl bg-foreground/10 flex items-center justify-center">
        <span className="text-lg font-bold text-foreground">R</span>
      </div>
      <div className="space-y-1">
        <h2 className="text-base font-semibold text-foreground">
          Ask anything about your migrations
        </h2>
        <p className="text-sm text-muted-foreground">
          Select a migration or attach files, then ask a question.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {ALL_CHIPS.map((text) => (
          <Button
            key={text}
            variant="outline"
            size="sm"
            onClick={() => onSuggest(text)}
          >
            {text}
          </Button>
        ))}
      </div>
    </div>
  );
}
