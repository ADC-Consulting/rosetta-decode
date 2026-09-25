import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AlertTriangle } from "lucide-react";

/**
 * Red warning glyph shown next to a job name when `sensitive_data` is true
 * (derived server-side from F32's PII scanner findings). Must render inside
 * a `TooltipProvider` ancestor.
 */
export default function SensitiveDataIcon(): React.ReactElement {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<span className="inline-flex shrink-0" aria-label="Sensitive data detected" />}
      >
        <AlertTriangle className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
      </TooltipTrigger>
      <TooltipContent>Sensitive data detected</TooltipContent>
    </Tooltip>
  );
}
