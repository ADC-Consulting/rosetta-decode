export default function ReconSummaryCard({
  report,
}: {
  report: Record<string, unknown> | null;
}): React.ReactElement | null {
  if (!report) return null;
  const checks =
    (report.checks as Array<{ name: string; status: string }> | undefined) ??
    [];
  const passed = checks.filter((c) => c.status === "pass").length;
  const failed = checks.filter((c) => c.status !== "pass").length;
  const allPassed = failed === 0 && checks.length > 0;
  return (
    <div
      className={`rounded-lg border p-3 flex items-center gap-3 ${
        allPassed
          ? "border-emerald-200 bg-emerald-50"
          : "border-red-200 bg-red-50"
      }`}
    >
      <span
        className={`text-lg ${allPassed ? "text-emerald-600" : "text-red-500"}`}
      >
        {allPassed ? "✓" : "✗"}
      </span>
      <div>
        <p
          className={`text-sm font-semibold ${allPassed ? "text-emerald-700" : "text-red-700"}`}
        >
          {allPassed
            ? "Reconciliation passed"
            : "Reconciliation issues detected"}
        </p>
        <p className="text-xs text-muted-foreground">
          {passed} passed · {failed} failed · {checks.length} total checks
        </p>
        {!allPassed && (report.diff_summary as string | undefined) && (
          <p className="text-xs text-red-600 mt-1">
            {report.diff_summary as string}
          </p>
        )}
      </div>
    </div>
  );
}
