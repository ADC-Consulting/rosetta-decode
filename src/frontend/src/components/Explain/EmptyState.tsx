import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  mode: "migration" | "sas_general";
  audience: "tech" | "non_tech";
  hasContext: boolean;
  onSuggest: (prompt: string) => void;
}

const CHIPS: Record<"migration" | "sas_general", Record<"tech" | "non_tech", string[]>> = {
  migration: {
    tech: [
      "Show me the highest-risk blocks in this migration",
      "Which blocks have manual TODOs and why?",
      "Explain the lineage for the main output dataset",
    ],
    non_tech: [
      "Summarise what this migration does in plain English",
      "What data does this pipeline read and produce?",
      "Are there any parts of the migration that need human review?",
    ],
  },
  sas_general: {
    tech: [
      "How does PROC SQL differ from a DATA step merge?",
      "Convert this PROC SORT + BY group pattern to pandas",
      "Explain how %MACRO and %MEND work with parameters",
    ],
    non_tech: [
      "What is SAS and why do companies migrate away from it?",
      "In simple terms, what does a DATA step do?",
      "What does it mean when a SAS job 'reconciles' its output?",
    ],
  },
};

const SUBTITLE: Record<"migration" | "sas_general", string> = {
  migration: "Select a migration from the sidebar, then ask a question.",
  sas_general: "Ask any SAS question, or attach a .sas file for context.",
};

export default function EmptyState({
  mode,
  audience,
  onSuggest,
}: EmptyStateProps): React.ReactElement {
  const chips = CHIPS[mode][audience];

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 text-center px-4">
      <div className="size-10 rounded-xl bg-foreground/10 flex items-center justify-center">
        <span className="text-lg font-bold text-foreground">R</span>
      </div>
      <div className="space-y-1">
        <h2 className="text-base font-semibold text-foreground">
          {mode === "migration" ? "Ask about this migration" : "Ask anything about SAS"}
        </h2>
        <p className="text-sm text-muted-foreground">{SUBTITLE[mode]}</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {chips.map((text) => (
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
