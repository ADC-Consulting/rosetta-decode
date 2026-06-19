import type { BlockPlan } from "@/api/types";

// Mirrors backend _sas_to_module_name exactly:
// strips directory components, then strips everything after the last dot.
// "subdir/01_build_sdtm_dm.sas" → "01_build_sdtm_dm.py"
// "utils.sas7bdat" → "utils.py"   (matches os.path.splitext behaviour)
export function sasFileToPyFile(sourceFile: string): string {
  const basename = sourceFile.split("/").pop() ?? sourceFile;
  const lastDot = basename.lastIndexOf(".");
  const stem = lastDot > 0 ? basename.slice(0, lastDot) : basename;
  return `${stem}.py`;
}

// Returns all SAS source files in blockPlans that map to a given Python filename.
// When the result has >1 entry, those SAS files were merged into one Python module.
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
