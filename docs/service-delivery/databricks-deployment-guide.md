# Databricks Deployment Guide

> This document mirrors the `DEPLOYMENT_GUIDE.md` bundled in each generated zip.
> Keep in sync with `src/backend/api/templates/databricks_deployment_guide.md.j2`.

What Rosetta Decode packages and how to deploy it to a Databricks workspace.

---

## Prerequisites

- Databricks workspace with Unity Catalog enabled
- Databricks CLI ≥ 0.200 (`pip install databricks-cli` or `brew install databricks/tap/databricks`)
- Service principal or personal access token with:
  - `CREATE TABLE` on `main.<your-schema>`
  - Read access to source data at `abfss://<container>@<account>.dfs.core.windows.net/<path>/`
- Source Delta tables available at the storage root (see §Storage paths below)

---

## What's in the generated package

Each migration job produces a `.zip` that can be deployed directly as a Databricks Asset Bundle (DAB).

| File | Purpose |
|---|---|
| `databricks.yml` | Databricks Asset Bundle (DAB) — pipeline + scheduling job |
| `transformations/<pipeline_name>_dlt.py` | DLT pipeline module — one `@dlt.table` per dataset |
| `DEPLOYMENT_GUIDE.md` | Per-job copy of this guide, rendered with job-specific values |
| `src/` | PySpark modules (local reconciliation reference) |
| `requirements.txt` | Python dependencies |
| `audit.json` | Migration audit trail |
| `reconciliation_report.json` | Local reconciliation results |
| `migration_summary.md` | Migration summary |

---

## Datasets

The guide bundled in each zip lists the exact tables the pipeline will create, including target schema, primary keys, and column counts. A generic example row:

| Dataset | Target Schema | Primary Keys | Columns |
|---|---|---|---|
| `your_output_dataset` | `public` | `id` | 12 |

---

## Deployment steps

1. **Install the Databricks CLI** (if not already installed):
   ```bash
   pip install databricks-cli
   # or
   brew install databricks/tap/databricks
   ```

2. **Authenticate**:
   ```bash
   databricks configure --token
   # or
   databricks auth login --host https://<your-workspace>.azuredatabricks.net
   ```

3. **Review and set bundle variables** in `databricks.yml`:
   - `catalog` (default: `main`) — Unity Catalog catalog name
   - `target_schema` — schema/database to write tables into
   - `storage_root` (default: `abfss://<container>@<account>.dfs.core.windows.net/<path>/`) — ABFSS root for source Delta tables

4. **Validate the bundle** (offline, no workspace required):
   ```bash
   databricks bundle validate
   ```

5. **Deploy**:
   ```bash
   databricks bundle deploy --target production
   ```

6. **Run the pipeline** (first run or manual trigger):
   ```bash
   databricks bundle run rosetta_your-job-name_job
   ```

   Or trigger via the Databricks UI: Jobs → `rosetta_your-job-name_job` → Run now.

---

## Storage paths

Source tables are read from `DATABRICKS_DATA_ROOT` (set via the `storage_root` bundle variable).
Each dataset maps to `<storage_root>/<dataset_name>/`. Update the paths in
`transformations/<pipeline_name>_dlt.py` if your data layout differs.

---

## Manual migration required (when applicable)

If the migration summary reports untranslatable blocks, those blocks are represented as placeholder
tables in the DLT pipeline. They will raise `NotImplementedError` at runtime and must be manually
implemented before deployment.

The per-job `DEPLOYMENT_GUIDE.md` inside the zip lists each affected dataset, its source file and
line number, and the reason it could not be translated automatically.

---

## Known limitations

- **Storage paths** must be confirmed and updated in `transformations/<pipeline_name>_dlt.py`
  and `databricks.yml` before deploying.
- **Unity Catalog ACLs** — grant `CREATE TABLE` / `SELECT` permissions as required by your
  workspace security model.
- **Multi-output blocks** — when a single SAS PROC produces multiple output datasets, the block
  code is repeated in each `@dlt.table`. Review for efficiency if the block is expensive.
- **Live validation** — generated packages are validated with `databricks bundle validate` (offline
  schema check). End-to-end data validation against a live Databricks workspace is a first-engagement
  step and is not performed by the tool.

---

## Troubleshooting

| Symptom | Resolution |
|---|---|
| `RESOURCE_DOES_NOT_EXIST` on pipeline run | Check `storage_root` points to accessible Delta tables |
| `PERMISSION_DENIED` | Verify service principal has `CREATE TABLE` on the target catalog/schema |
| `NotImplementedError` on a table | See §Manual migration required above; that block needs manual implementation |
| Schema mismatch | Re-download the package after editing column types in the Data Storage tab |

---

## SAS version compatibility

Databricks deployment packages are generated for any SAS source version supported by the migration
tool. See the [Input Prerequisites](../input-prerequisites.md) document for the full SAS version
compatibility matrix.
