import type { BlockPlan } from "@/api/types";

/**
 * Derives the Python module filename from a SAS source file path.
 * Mirrors backend _sas_to_module_name: strips directory components,
 * then strips everything after the last dot (any extension, not just .sas).
 *
 * Examples:
 *   "subdir/01_build_sdtm_dm.sas" → "01_build_sdtm_dm.py"
 *   "utils.sas7bdat"              → "utils.py"
 *   "etl"                         → "etl.py"
 */
export function sasFileToPyFile(sourceFile: string): string {
  const basename = sourceFile.split("/").pop() ?? sourceFile;
  const lastDot = basename.lastIndexOf(".");
  const stem = lastDot > 0 ? basename.slice(0, lastDot) : basename;
  return `${stem}.py`;
}

/**
 * Returns all distinct SAS source files in blockPlans that map to the
 * given Python filename. Order is first-seen in blockPlans.
 *
 * When the result has more than one entry, those SAS files were merged
 * into one Python module by the code generator.
 */
export function pyFileToSasFiles(pyFile: string, blockPlans: BlockPlan[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const bp of blockPlans) {
    if (sasFileToPyFile(bp.source_file) === pyFile && !seen.has(bp.source_file)) {
      seen.add(bp.source_file);
      result.push(bp.source_file);
    }
  }
  return result;
}
