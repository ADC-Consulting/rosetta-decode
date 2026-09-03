import { TabsList, TabsTrigger } from "@/components/ui/tabs";

interface ChevronTabBarProps {
  activeTab: string;
}

interface Step {
  key: string;
  label: string;
}

const STEPS: Step[] = [
  { key: "plan", label: "Plan" },
  { key: "etl", label: "ETL" },
  { key: "data-storage", label: "Data" },
  { key: "bi", label: "BI" },
  { key: "ai", label: "AI" },
];

const CLIP_FIRST = "polygon(0 0, calc(100% - 20px) 0, 100% 50%, calc(100% - 20px) 100%, 0 100%)";
const CLIP_MIDDLE =
  "polygon(0 0, calc(100% - 20px) 0, 100% 50%, calc(100% - 20px) 100%, 0 100%, 20px 50%)";
const CLIP_LAST = "polygon(0 0, 100% 0, 100% 100%, 0 100%, 20px 50%)";

export default function ChevronTabBar({ activeTab }: ChevronTabBarProps): React.ReactElement {
  const activeIndex = STEPS.findIndex((s) => s.key === activeTab);

  // z-index decreases left to right so left tabs render their arrow tip on top of the next tab
  const zIndexMap = [5, 4, 3, 2, 1];

  return (
    <TabsList className="h-auto p-0 bg-transparent gap-0 rounded-none overflow-visible">
      {STEPS.map((step, i) => {
        const isActive = step.key === activeTab;
        const isVisited = i < activeIndex;

        let clipPath: string;
        if (i === 0) clipPath = CLIP_FIRST;
        else if (i === STEPS.length - 1) clipPath = CLIP_LAST;
        else clipPath = CLIP_MIDDLE;

        const baseClasses =
          "relative h-9 rounded-none border-0 px-6 text-sm font-medium transition-colors cursor-pointer";
        const stateClasses = isActive
          ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
          : isVisited
            ? "bg-muted/70 text-foreground hover:bg-muted/80"
            : "bg-muted/30 text-muted-foreground hover:bg-muted/50";
        const overlapClass = i === 0 ? "" : "-ml-3";

        return (
          <TabsTrigger
            key={step.key}
            value={step.key}
            className={`${baseClasses} ${stateClasses} ${overlapClass}`}
            style={{ clipPath, zIndex: zIndexMap[i] }}
            aria-label={step.label}
          >
            {step.label}
          </TabsTrigger>
        );
      })}
    </TabsList>
  );
}
