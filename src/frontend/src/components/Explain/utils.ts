export function fileExt(name: string): string {
  const lower = name.toLowerCase();
  const exts = [".sas7bdat", ".sas", ".csv", ".log", ".xls", ".xlsx", ".zip"];
  for (const ext of exts) {
    if (lower.endsWith(ext)) return ext;
  }
  return "";
}
