interface ContextBannerProps {
  mode: "migration" | "upload";
  jobName: string | null;
  fileCount: number;
  onClear: () => void;
}

export default function ContextBanner({
  mode,
  jobName,
  fileCount,
  onClear,
}: ContextBannerProps): React.ReactElement | null {
  if (mode === "migration" && !jobName) return null;
  if (mode === "upload" && fileCount === 0) return null;

  const label =
    mode === "migration"
      ? `Asking about: ${jobName}`
      : `Asking about ${fileCount} file${fileCount !== 1 ? "s" : ""}`;

  return (
    <div className="flex items-center gap-2 mb-2 px-3 py-1.5 rounded-md bg-muted text-xs text-muted-foreground shrink-0">
      <span>{label}</span>
      <button onClick={onClear} className="ml-auto hover:text-foreground" aria-label="Clear context">
        ✕
      </button>
    </div>
  );
}
