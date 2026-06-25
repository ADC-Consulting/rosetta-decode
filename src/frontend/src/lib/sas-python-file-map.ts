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

// Parse "# SAS: <file>:<line>" provenance comments to build the accurate
// Python-file → SAS-source-files map. Handles merging (2 SAS → 1 py) and
// splitting (1 SAS → 2 py) transparently.
export function buildPyFileToSasFilesMap(
  generatedFiles: Record<string, string>,
): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const [pyFile, content] of Object.entries(generatedFiles)) {
    if (pyFile === "pipeline.py") continue;
    const seen = new Set<string>();
    const sasFiles: string[] = [];
    for (const m of content.matchAll(/# SAS: ([^:\n]+):\d+/g)) {
      const sasFile = m[1].trim();
      if (!seen.has(sasFile)) {
        seen.add(sasFile);
        sasFiles.push(sasFile);
      }
    }
    map.set(pyFile, sasFiles);
  }
  return map;
}

// Reverse: SAS source file → list of Python files that contain blocks from it.
export function buildSasFileToPyFilesMap(
  generatedFiles: Record<string, string>,
): Map<string, string[]> {
  const pyToSas = buildPyFileToSasFilesMap(generatedFiles);
  const map = new Map<string, string[]>();
  for (const [pyFile, sasFiles] of pyToSas) {
    for (const sasFile of sasFiles) {
      const existing = map.get(sasFile) ?? [];
      existing.push(pyFile);
      map.set(sasFile, existing);
    }
  }
  return map;
}
