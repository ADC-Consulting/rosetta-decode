import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Tone } from "./status-colors";
import { TONE_CHIP_CLASS, TONE_TEXT_CLASS } from "./status-colors";

interface StatusChipProps {
  /** Semantic tone resolved from a status-colors.ts map (confidence/strategy/risk/criticality). */
  tone: Tone;
  children: React.ReactNode;
  /**
   * "chip" (default) renders a bordered pill — for strategy/risk/criticality badges.
   * "text" renders plain colored text with no background/border — for inline values such
   * as a confidence percentage sitting directly in a table cell.
   */
  variant?: "chip" | "text";
  className?: string;
}

/**
 * One consistent status pill/text treatment, built on shadcn `Badge`. Wraps a semantic `Tone`
 * (see ./status-colors.ts) so every confidence/strategy/risk/criticality indicator in the Plan
 * and ETL tabs shares the same shape, size, and color convention instead of each call site
 * hand-rolling its own `inline-flex items-center rounded ... text-xs font-medium` markup.
 */
export default function StatusChip({
  tone,
  children,
  variant = "chip",
  className,
}: StatusChipProps): React.ReactElement {
  if (variant === "text") {
    return (
      <span className={cn("text-xs font-medium", TONE_TEXT_CLASS[tone], className)}>
        {children}
      </span>
    );
  }
  return (
    <Badge variant="outline" className={cn(TONE_CHIP_CLASS[tone], className)}>
      {children}
    </Badge>
  );
}
