import StatusChip from "@/components/JobDetail/StatusChip";
import { Button } from "@/components/ui/button";
import { Check } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

// ---------------------------------------------------------------------------
// F96 — Welcome page at "/". Static content only (no live data — see the
// locked decision in docs/plans/F96-welcome-page.md), so it reads correctly
// regardless of demo-account state. Mirrors the approved mockup
// (docs/design/welcome-page.dc.html) translated into this codebase's real
// Tailwind/shadcn conventions and `.brand-manifest` tokens rather than the
// mockup's standalone CSS.
//
// No sidebar / outer `flex`/`main` wrapper here — App.tsx already renders
// <AppSidebar /> once and wraps every route in a shared <main> (see
// DocsPage.tsx / ExplainPage.tsx for the same content-only page pattern).
// ---------------------------------------------------------------------------

const STEPS = [
  {
    num: "01",
    title: "Upload",
    desc: "Scripts, macros, includes, and reference data for an existing workload.",
  },
  {
    num: "02",
    title: "Review",
    desc: "A migration plan, proposed ETL, and proposed data model, block by block.",
  },
  {
    num: "03",
    title: "Accept",
    desc: "Once reconciliation proves the output matches, sign off and download.",
  },
] as const;

const TRUST_ITEMS = [
  "Every line traced to its SAS source",
  "Validated against your reference data",
  "Full audit trail, ready for review",
] as const;

// ── Code-proof panel ─────────────────────────────────────────────────────────
// Hardcoded illustrative SAS -> PySpark example, not live job data (locked
// decision: static content only). Keyword color ties to the shared teal
// accent (bg-[var(--primary)] pattern, not bg-primary — see F88/PR #157);
// string/function syntax colors reuse existing token/Tailwind-scale classes
// rather than introducing new hardcoded hex values.

function CodeProofPanel(): React.ReactElement {
  return (
    <div className="rounded-md border border-border bg-card overflow-hidden">
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-border">
        <span className="text-xs text-muted-foreground">Same logic, translated</span>
        <StatusChip tone="success">
          <Check className="size-3" />
          Reconciled
        </StatusChip>
      </div>

      <div className="px-4 py-3.5">
        <span className="block font-mono text-[10.5px] tracking-wide text-muted-foreground mb-2">
          SAS
        </span>
        <pre className="m-0 font-mono text-xs leading-relaxed overflow-x-auto">
          <span className="text-[var(--primary)]">data</span> adsl;{"\n"}
          {"  "}
          <span className="text-[var(--primary)]">set</span> demographics;{"\n"}
          {"  "}
          <span className="text-[var(--primary)]">where</span> age {">="} 18;{"\n"}
          {"  "}trtdurd = trtedt-trtsdt+1;{"\n"}
          <span className="text-[var(--primary)]">run</span>;
        </pre>
      </div>

      <div className="px-4 py-3.5 border-t border-border">
        <span className="block font-mono text-[10.5px] tracking-wide text-muted-foreground mb-2">
          PYTHON
        </span>
        <pre className="m-0 font-mono text-xs leading-relaxed overflow-x-auto">
          <span className="italic text-muted-foreground"># SAS: build_adsl.sas:12</span>
          {"\n"}
          adsl = (demographics{"\n"}
          {"  "}.<span className="text-blue-700 dark:text-blue-400">filter</span>(F.col(
          <span className="text-[var(--tone-warning)]">&quot;age&quot;</span>) {">="} 18){"\n"}
          {"  "}.<span className="text-blue-700 dark:text-blue-400">withColumn</span>(
          <span className="text-[var(--tone-warning)]">&quot;trtdurd&quot;</span>,{"\n"}
          {"    "}F.
          <span className="text-blue-700 dark:text-blue-400">datediff</span>(
          <span className="text-[var(--tone-warning)]">&quot;trtedt&quot;</span>,{" "}
          <span className="text-[var(--tone-warning)]">&quot;trtsdt&quot;</span>)+1)){"\n"}
        </pre>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function WelcomePage(): React.ReactElement {
  const navigate = useNavigate();

  return (
    <div className="brand-manifest bg-[var(--brand-paper)] h-full overflow-y-auto flex items-center justify-center px-6 py-12 md:px-10 md:py-16">
      <div className="w-full max-w-[940px]">
        <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-10 lg:gap-12 items-start mb-10">
          <div>
            <div className="inline-flex items-center gap-2 font-mono text-xs tracking-wide text-[var(--primary)] mb-5">
              <span className="size-1.5 rounded-full bg-[var(--primary)]" aria-hidden="true" />
              # sas &rarr; python, validated
            </div>

            <h1 className="text-4xl font-extrabold tracking-tight leading-[1.15] text-foreground text-balance mb-4">
              See a SAS workload migrated, and proven correct.
            </h1>

            <p className="text-base leading-relaxed text-muted-foreground max-w-[52ch] mb-8">
              A working Python pipeline from a legacy SAS job, without weeks of manual rewriting,
              ready to hand to your own engineers.
            </p>

            <div className="flex items-center gap-4">
              <Button
                type="button"
                onClick={() => navigate("/jobs?upload=1")}
                className="bg-[var(--primary)] text-[var(--primary-foreground)] cursor-pointer"
              >
                New migration
              </Button>
              <Link
                to="/jobs"
                className="text-[13.5px] text-muted-foreground border-b border-border pb-px hover:text-foreground transition-colors"
              >
                or view existing migrations
              </Link>
            </div>
          </div>

          <CodeProofPanel />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-px bg-border border border-border rounded-md overflow-hidden mb-9">
          {STEPS.map((step) => (
            <div key={step.num} className="bg-card p-5">
              <span className="block font-mono text-xs text-[var(--primary)] mb-2.5">
                {step.num}
              </span>
              <p className="text-[14.5px] font-bold text-foreground mb-1.5">{step.title}</p>
              <p className="text-[13px] leading-relaxed text-muted-foreground">{step.desc}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-x-7 gap-y-2">
          {TRUST_ITEMS.map((item) => (
            <div key={item} className="flex items-center gap-2 text-xs text-muted-foreground">
              <Check className="size-3.5 shrink-0 text-[var(--tone-success)]" />
              {item}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
