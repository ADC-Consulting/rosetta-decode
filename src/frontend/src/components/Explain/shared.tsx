import { cn } from "@/lib/utils";
import { Database, File, FileCode2, FileSpreadsheet, ScrollText } from "lucide-react";

export function FileIcon({ ext, className }: { ext: string; className?: string }) {
  const cls = cn("shrink-0", className ?? "h-4 w-4");
  if (ext === ".sas") return <FileCode2 className={cls} />;
  if (ext === ".sas7bdat") return <Database className={cls} />;
  if (ext === ".xls" || ext === ".xlsx" || ext === ".csv") return <FileSpreadsheet className={cls} />;
  if (ext === ".log") return <ScrollText className={cls} />;
  return <File className={cls} />;
}

export function TypeBadge({ ext }: { ext: string }) {
  if (ext === ".sas")
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
        SAS source
      </span>
    );
  if (ext === ".sas7bdat")
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-400">
        Dataset
      </span>
    );
  if (ext === ".zip")
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-400">
        Zip archive
      </span>
    );
  if (ext === ".log" || ext === ".csv" || ext === ".xls" || ext === ".xlsx")
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
        Supporting
      </span>
    );
  return (
    <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-destructive/10 text-destructive">
      Unsupported
    </span>
  );
}

