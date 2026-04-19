import { cn } from "@/lib/utils";

function SkeletonBar({ className }: { className?: string }): React.ReactElement {
  return (
    <div
      className={cn(
        "rounded",
        "bg-linear-to-r from-muted via-muted-foreground/10 to-muted",
        "bg-size-[200%_100%]",
        "animate-[shimmer_2s_linear_infinite]",
        className,
      )}
      aria-hidden="true"
    />
  );
}

export default function DocsPage(): React.ReactElement {
  return (
    <div className="space-y-6">
      <style>{`@keyframes shimmer { from { background-position: 200% center; } to { background-position: -200% center; } }`}</style>

      <div>
        <h1 className="text-xl font-semibold text-foreground">Documentation</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          LLM-generated migration summaries will appear here.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {([0, 1, 2] as const).map((i) => (
          <div
            key={i}
            className="rounded-md border border-border bg-card p-4 space-y-3"
            aria-hidden="true"
          >
            {/* Title skeleton */}
            <SkeletonBar className="h-4 w-2/3" />
            {/* Text line skeletons */}
            <SkeletonBar className="h-3 w-full" />
            <SkeletonBar className="h-3 w-4/5" />
            {/* Date skeleton */}
            <SkeletonBar className="h-3 w-1/3 mt-2" />
          </div>
        ))}
      </div>
    </div>
  );
}
