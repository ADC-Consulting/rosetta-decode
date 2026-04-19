export default function GlobalLineagePage(): React.ReactElement {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Global Lineage</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Cross-job dependency graph — coming soon.
        </p>
      </div>

      {/* Simple CSS node illustration */}
      <div
        className="rounded-md border border-border bg-muted/30 flex items-center justify-center py-16"
        aria-hidden="true"
      >
        <div className="flex items-center gap-0">
          {/* Node A */}
          <div className="flex flex-col items-center gap-1.5">
            <div className="w-20 h-10 rounded-md border border-border bg-muted flex items-center justify-center">
              <span className="text-xs font-mono text-muted-foreground">raw.sas</span>
            </div>
          </div>

          {/* Edge A → B */}
          <div className="flex items-center mx-1">
            <div className="w-12 border-t border-dashed border-border" />
            <div className="w-0 h-0 border-y-4 border-y-transparent border-l-[6px] border-l-border" />
          </div>

          {/* Node B — transform */}
          <div className="flex flex-col items-center gap-1.5">
            <div className="w-10 h-10 rounded-full border border-border bg-muted flex items-center justify-center">
              <span className="text-xs font-mono text-muted-foreground">T</span>
            </div>
          </div>

          {/* Edge B → C */}
          <div className="flex items-center mx-1">
            <div className="w-12 border-t border-dashed border-border" />
            <div className="w-0 h-0 border-y-4 border-y-transparent border-l-[6px] border-l-border" />
          </div>

          {/* Node C */}
          <div className="flex flex-col items-center gap-1.5">
            <div className="w-20 h-10 rounded-md border border-border bg-muted flex items-center justify-center">
              <span className="text-xs font-mono text-muted-foreground">out.py</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
