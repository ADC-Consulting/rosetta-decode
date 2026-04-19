import { cn } from "@/lib/utils";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  GitFork,
  LayoutList,
  MessageSquare,
  Moon,
  Sun,
  Upload,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useState } from "react";
import { NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/upload", label: "Upload", Icon: Upload },
  { to: "/jobs", label: "Migrations", Icon: LayoutList },
  { to: "/lineage", label: "Lineage", Icon: GitFork },
  { to: "/docs", label: "Docs", Icon: FileText },
  { to: "/explain", label: "Explain", Icon: MessageSquare },
];

function readCollapsed(): boolean {
  try {
    return localStorage.getItem("sidebar-collapsed") === "true";
  } catch {
    return false;
  }
}

const ICON_COL = 56; // collapsed sidebar width in px; icon is always centred within this column
const ICON_LEFT = (ICON_COL - 18) / 2; // left padding so 18px icon is centred
const LABEL_WIDTH = 140; // max label width when expanded

export default function AppSidebar(): React.ReactElement {
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);
  const { resolvedTheme, setTheme } = useTheme();

  function toggle(): void {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("sidebar-collapsed", String(next));
    } catch {
      // ignore
    }
  }

  return (
    // No overflow-hidden here — tooltips must escape the sidebar boundary
    <aside
      aria-label="Main navigation"
      style={{ width: collapsed ? ICON_COL : 220 }}
      className="relative flex flex-col h-screen shrink-0 bg-background border-r border-border transition-[width] duration-200 ease-in-out"
    >
      {/* Logo */}
      <div
        className="flex items-center h-14 border-b border-border shrink-0 overflow-hidden"
        style={{ paddingLeft: (ICON_COL - 20) / 2 }}
      >
        <span
          className="size-5 rounded bg-foreground shrink-0"
          aria-hidden="true"
        />
        <span
          className="text-sm font-semibold text-foreground whitespace-nowrap overflow-hidden transition-[width,opacity,margin] duration-200 ease-in-out"
          style={{
            width: collapsed ? 0 : LABEL_WIDTH,
            opacity: collapsed ? 0 : 1,
            marginLeft: collapsed ? 0 : 10,
          }}
        >
          Rosetta
        </span>
      </div>

      {/* Nav items */}
      <nav className="flex-1 py-2">
        {NAV_ITEMS.map(({ to, label, Icon }) => (
          <div key={to} className="group/nav relative">
            <NavLink
              to={to}
              aria-label={label}
              className={({ isActive }) =>
                cn(
                  "flex items-center h-10 text-sm text-muted-foreground overflow-hidden",
                  "hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer",
                  isActive && "bg-muted text-foreground font-medium",
                )
              }
              style={{ paddingLeft: ICON_LEFT }}
            >
              <Icon size={18} className="shrink-0" />
              <span
                className="whitespace-nowrap overflow-hidden text-ellipsis transition-[width,opacity,margin] duration-200 ease-in-out"
                style={{
                  width: collapsed ? 0 : LABEL_WIDTH,
                  opacity: collapsed ? 0 : 1,
                  marginLeft: collapsed ? 0 : 12,
                }}
              >
                {label}
              </span>
            </NavLink>

            {/* Instant CSS tooltip — escapes aside because aside has no overflow-hidden */}
            <div
              aria-hidden="true"
              className={cn(
                "pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-3 z-50",
                "rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap",
                "opacity-0 transition-opacity duration-100",
                collapsed ? "group-hover/nav:opacity-100" : "hidden",
              )}
            >
              {label}
            </div>
          </div>
        ))}
      </nav>

      {/* Theme + Collapse toggles */}
      <div className="shrink-0 border-t border-border">
        {/* Theme toggle */}
        <div className="group/theme relative">
          <button
            type="button"
            onClick={() =>
              setTheme(resolvedTheme === "dark" ? "light" : "dark")
            }
            aria-label={
              resolvedTheme === "dark"
                ? "Switch to light theme"
                : "Switch to dark theme"
            }
            className="flex items-center h-10 w-full overflow-hidden text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
            style={{ paddingLeft: ICON_LEFT }}
          >
            {resolvedTheme === "dark" ? (
              <Sun size={18} className="shrink-0" />
            ) : (
              <Moon size={18} className="shrink-0" />
            )}
            <span
              className="text-sm whitespace-nowrap overflow-hidden transition-[width,opacity,margin] duration-200 ease-in-out"
              style={{
                width: 0,
                opacity: 0,
                marginLeft: 0,
              }}
            >
              Theme
            </span>
          </button>
          <div
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-3 z-50",
              "rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap",
              "opacity-0 transition-opacity duration-100",
              collapsed ? "group-hover/theme:opacity-100" : "hidden",
            )}
          >
            {resolvedTheme === "dark" ? "Light theme" : "Dark theme"}
          </div>
        </div>
        <div className="group/toggle relative">
          <button
            type="button"
            onClick={toggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="flex items-center h-10 w-full overflow-hidden text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
            style={{ paddingLeft: ICON_LEFT }}
          >
            {collapsed ? (
              <ChevronRight size={18} className="shrink-0" />
            ) : (
              <ChevronLeft size={18} className="shrink-0" />
            )}
            <span
              className="text-sm whitespace-nowrap overflow-hidden transition-[width,opacity,margin] duration-200 ease-in-out"
              style={{
                width: 0,
                opacity: 0,
                marginLeft: 0,
              }}
            >
              Collapse
            </span>
          </button>

          <div
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-3 z-50",
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
