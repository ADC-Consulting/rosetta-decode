import { cn } from "@/lib/utils";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useState } from "react";

interface RightSidebarItem {
  id: string;
  label: string;
  isSelected: boolean;
  onClick: () => void;
}

interface RightSidebarProps {
  title: string;
  items: RightSidebarItem[];
  footer?: React.ReactNode;
}

// Mirror of AppSidebar constants
const ICON_COL = 56;
const ICON_RIGHT = (ICON_COL - 18) / 2; // right padding so 18px icon is centred
const LABEL_WIDTH = 140;

export default function RightSidebar({
  title,
  items,
  footer,
}: RightSidebarProps): React.ReactElement {
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState("");

  function toggle(): void {
    setCollapsed((c) => !c);
  }

  const filtered = search
    ? items.filter((i) => i.label.toLowerCase().includes(search.toLowerCase()))
    : items;

  return (
    // Mirror of AppSidebar <aside> — border-l instead of border-r, no overflow-hidden so tooltips escape
    <aside
      aria-label={title}
      style={{ width: collapsed ? ICON_COL : 220 }}
      className="relative flex flex-col h-full shrink-0 bg-background border-l border-border transition-[width] duration-200 ease-in-out"
    >
      {/* Title row — mirrors Logo row */}
      <div
        className="flex items-center h-14 border-b border-border shrink-0 overflow-hidden"
        style={{ paddingRight: (ICON_COL - 20) / 2 }}
      >
        <span
          className="text-sm font-semibold text-foreground whitespace-nowrap overflow-hidden transition-[width,opacity,margin] duration-200 ease-in-out"
          style={{
            width: collapsed ? 0 : LABEL_WIDTH,
            opacity: collapsed ? 0 : 1,
            marginLeft: collapsed ? 0 : (ICON_COL - 20) / 2,
            marginRight: collapsed ? 0 : 8,
          }}
        >
          {title}
        </span>
      </div>

      {/* Search row — mirrors a nav item row */}
      <div className="group/search relative">
        <div
          className="flex items-center h-10 text-sm text-muted-foreground overflow-hidden border-b border-border"
          style={{ paddingRight: ICON_RIGHT }}
        >
          {/* Search icon — always visible like nav icons */}
          <Search
            size={18}
            className="shrink-0"
            style={{ marginLeft: ICON_RIGHT }}
          />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            aria-label="Search migrations"
            className="bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground whitespace-nowrap overflow-hidden transition-[width,opacity,margin] duration-200 ease-in-out"
            style={{
              width: collapsed ? 0 : LABEL_WIDTH,
              opacity: collapsed ? 0 : 1,
              marginLeft: collapsed ? 0 : 12,
            }}
          />
        </div>
        {/* Tooltip when collapsed */}
        <div
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute right-full top-1/2 -translate-y-1/2 mr-3 z-50",
            "rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap",
            "opacity-0 transition-opacity duration-100",
            collapsed ? "group-hover/search:opacity-100" : "hidden",
          )}
        >
          Search
        </div>
      </div>

      {/* Items — mirrors NAV_ITEMS nav rows exactly */}
      <nav className="flex-1 py-2 overflow-y-auto">
        {filtered.map((item) => (
          <div key={item.id} className="group/item relative">
            <button
              type="button"
              onClick={item.onClick}
              aria-label={item.label}
              className={cn(
                "flex items-center h-10 w-full text-sm text-muted-foreground overflow-hidden",
                "hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer",
                item.isSelected && "bg-muted text-foreground font-medium",
              )}
              style={{ paddingRight: ICON_RIGHT }}
            >
              {/* Dot — mirrors the Icon in AppSidebar nav rows */}
              <span
                className="shrink-0 flex items-center justify-center"
                style={{
                  width: 18,
                  height: 18,
                  marginLeft: ICON_RIGHT,
                }}
              >
                <span
                  className={cn(
                    "size-1.5 rounded-full transition-colors",
                    item.isSelected ? "bg-foreground" : "bg-muted-foreground/50",
                  )}
                />
              </span>
              <span
                className="whitespace-nowrap overflow-hidden text-ellipsis transition-[width,opacity,margin] duration-200 ease-in-out text-left"
                style={{
                  width: collapsed ? 0 : LABEL_WIDTH,
                  opacity: collapsed ? 0 : 1,
                  marginLeft: collapsed ? 0 : 12,
                }}
              >
                {item.label}
              </span>
            </button>

            {/* Tooltip on the left when collapsed — mirrors AppSidebar tooltip on right */}
            <div
              aria-hidden="true"
              className={cn(
                "pointer-events-none absolute right-full top-1/2 -translate-y-1/2 mr-3 z-50",
                "rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap",
                "opacity-0 transition-opacity duration-100",
                collapsed ? "group-hover/item:opacity-100" : "hidden",
              )}
            >
              {item.label}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer slot — rendered above collapse toggle */}
      {footer && (
        <div
          className="shrink-0 border-t border-border overflow-hidden transition-opacity duration-200"
          style={{
            opacity: collapsed ? 0 : 1,
            pointerEvents: collapsed ? "none" : "auto",
          }}
        >
          {footer}
        </div>
      )}

      {/* Collapse toggle — mirrors AppSidebar bottom toggle */}
      <div className="shrink-0 border-t border-border">
        <div className="group/toggle relative">
          <button
            type="button"
            onClick={toggle}
            aria-label={collapsed ? "Expand panel" : "Collapse panel"}
            className="flex items-center h-10 w-full overflow-hidden text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
            style={{ paddingRight: ICON_RIGHT }}
          >
            {/* Chevron: when collapsed show ChevronLeft (open leftward); expanded show ChevronRight (close rightward) */}
            {collapsed ? (
              <ChevronLeft size={18} className="shrink-0 mx-auto" />
            ) : (
              <>
                <span
                  className="text-sm whitespace-nowrap overflow-hidden transition-[width,opacity,margin] duration-200 ease-in-out"
                  style={{
                    width: LABEL_WIDTH,
                    opacity: 1,
                    marginLeft: ICON_RIGHT,
                  }}
                >
                  Collapse
                </span>
                <ChevronRight size={18} className="shrink-0" />
              </>
            )}
          </button>

          {/* Tooltip when collapsed */}
          <div
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute right-full top-1/2 -translate-y-1/2 mr-3 z-50",
              "rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap",
              "opacity-0 transition-opacity duration-100",
              collapsed ? "group-hover/toggle:opacity-100" : "hidden",
            )}
          >
            Expand
          </div>
        </div>
      </div>
    </aside>
  );
}
