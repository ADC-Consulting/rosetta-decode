const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function submitMigration(
  sasFiles: File[],
  refDataset?: File,
): Promise<{ job_id: string }> {
  const fd = new FormData();
  for (const f of sasFiles) {
    fd.append("sas_files", f); // repeated key — do NOT set Content-Type header
  }
  if (refDataset) {
    fd.append("ref_dataset", refDataset);
  }
  const res = await fetch(`${BASE}/migrate`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ job_id: string }>;
}
