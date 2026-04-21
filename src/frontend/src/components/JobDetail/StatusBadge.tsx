import type { JobStatusValue } from "@/api/types";
import { cn } from "@/lib/utils";
import {
  STATUS_LABEL,
  STATUS_PILL_CLASS,
  STATUS_SHIMMER,
} from "./constants";

export function StatusBadge({
  status,
}: {
  status: JobStatusValue;
}): React.ReactElement {
  const shimmer = STATUS_SHIMMER[status];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5",
        STATUS_PILL_CLASS[status],
      )}
    >
      {shimmer && (
        <style>{`@keyframes shimmer { from { background-position: 200% center; } to { background-position: -200% center; } }`}</style>
      )}
      <span
        className={cn("text-xs font-medium", !shimmer && "text-white")}
        style={
          shimmer
            ? {
                background:
                  status === "running"
                    ? "linear-gradient(90deg, #bfdbfe 25%, #eff6ff 50%, #bfdbfe 75%)"
                    : status === "proposed"
                      ? "linear-gradient(90deg, #fde68a 25%, #fffbeb 50%, #fde68a 75%)"
                      : "linear-gradient(90deg, #e2e8f0 25%, #f8fafc 50%, #e2e8f0 75%)",
                backgroundSize: "200% 100%",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
                animation: "shimmer 3.5s linear infinite",
              }
            : undefined
        }
      >
        {STATUS_LABEL[status]}
      </span>
    </span>
  );
}
