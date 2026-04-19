import type { MigrateResponse } from "./types";
import { extractApiError } from "./errors";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function submitMigration(
  sasFiles: File[],
  refDataset?: File,
  zipFile?: File,
  name?: string,
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
  const res = await fetch(`${BASE}/migrate`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<MigrateResponse>;
}
