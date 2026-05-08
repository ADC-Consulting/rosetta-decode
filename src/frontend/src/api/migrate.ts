import type { AnalyseResponse, MigrateResponse } from "./types";
import { extractApiError } from "./errors";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface AnalyseInput {
  sasFiles: File[];
  refDataset?: File;
  zipFile?: File;
  refTargetPath?: string | null;
}

export async function analyseMigration(input: AnalyseInput): Promise<AnalyseResponse> {
  const fd = new FormData();
  if (input.zipFile) {
    fd.append("zip_file", input.zipFile);
  } else {
    for (const f of input.sasFiles) {
      fd.append("sas_files", f);
    }
    if (input.refDataset) {
      fd.append("ref_dataset", input.refDataset);
    }
  }
  if (input.refTargetPath) fd.append("ref_target_path", input.refTargetPath);
  const res = await fetch(`${BASE}/analyse`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<AnalyseResponse>;
}

export async function submitMigration(
  sasFiles: File[],
  refDataset?: File,
  zipFile?: File,
  name?: string,
  refTargetPath?: string | null,
  notes?: string,
  importanceOverrides?: Record<string, "low" | "medium" | "high">,
  assessmentSnapshot?: object,
): Promise<MigrateResponse> {
  const fd = new FormData();
  if (zipFile) {
    fd.append("zip_file", zipFile);
  } else {
    for (const f of sasFiles) {
      fd.append("sas_files", f); // repeated key — do NOT set Content-Type header
    }
    if (refDataset) {
      fd.append("ref_dataset", refDataset);
    }
  }
  if (name) fd.append("name", name);
  if (refTargetPath) fd.append("ref_target_path", refTargetPath);
  if (notes) fd.append("notes", notes);
  if (importanceOverrides) fd.append("importance_overrides", JSON.stringify(importanceOverrides));
  if (assessmentSnapshot) fd.append("assessment_json", JSON.stringify(assessmentSnapshot));
  const res = await fetch(`${BASE}/migrate`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<MigrateResponse>;
}
