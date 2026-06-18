# Databricks Deployment Guide

> This document mirrors the `DEPLOYMENT_GUIDE.md` bundled in each generated zip.
> Keep in sync with `src/backend/api/templates/databricks_deployment_guide.md.j2`.

What Rosetta Decode packages and how to deploy it to a Databricks workspace.

---

## Prerequisites

- Databricks workspace with Unity Catalog enabled
- Databricks CLI ≥ 0.200 (`pip install databricks-cli` or `brew install databricks/tap/databricks`)
- Service principal or personal access token with:
  - `CREATE TABLE` on `<catalog>.<your-schema>` (catalog defaults to `main`)
  - Read access to source data at the provider storage root (see §Storage paths below)
- Source Delta tables available at the storage root (see §Storage paths below)

> **Cloud-aware (F75):** the accept-time questionnaire tailors the generated bundle and this
> guide per job — cloud provider (Azure / AWS / GCP), data-ingestion approach (historical /
> staging), compute mode (serverless / classic cluster), and the Unity Catalog catalog/schema.
> The per-job `DEPLOYMENT_GUIDE.md` in each zip is rendered with the chosen answers; absent
> answers default to Azure / serverless / catalog `main`, reproducing the F74 bundle exactly.

---

## What's in the generated package

Each migration job produces a `.zip` that can be deployed directly as a Databricks Asset Bundle (DAB).

> **Delivery format (F76):** the accept-time questionnaire also chooses the bundle's
> *delivery format* — **DLT pipeline** (default) or **Classic Spark Job**. The DLT format
> ships `transformations/<pipeline_name>_dlt.py` with one `@dlt.table` per dataset wired into
> a Lakeflow Pipeline. The Classic Spark Job format ships `jobs/<task>.py` PySpark modules —
> one Job task per Delta table (`saveAsTable`) wired into a multi-task Lakeflow Job, for
> workspaces that cannot run DLT. Both read source files from `ROSETTA_DATA_ROOT`.

| File | Purpose |
|---|---|
| `databricks.yml` | Databricks Asset Bundle (DAB) — pipeline+job (DLT) or multi-task Spark Job |
| `transformations/<pipeline_name>_dlt.py` | DLT pipeline module — one `@dlt.table` per dataset (DLT format) |
| `jobs/<task>.py` | PySpark task modules — one Job task per Delta table (Classic Spark Job format) |
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

2. **Authenticate** (the per-job guide prints the host for the chosen cloud):
   ```bash
   databricks configure --token
   # or — host depends on the chosen provider:
   #   Azure: databricks auth login --host https://<workspace>.azuredatabricks.net
   #   AWS:   databricks auth login --host https://<workspace>.cloud.databricks.com
   #   GCP:   databricks auth login --host https://<workspace>.gcp.databricks.com
   ```

3. **Review and set bundle variables** in `databricks.yml`:
   - `catalog` (default: `main`, or the questionnaire answer) — Unity Catalog catalog name
   - `target_schema` — schema/database to write tables into
   - `storage_root` — provider storage root for source Delta tables. Default scheme per provider:
     - Azure: `abfss://<container>@<account>.dfs.core.windows.net/<path>/`
     - AWS: `s3://<bucket>/<path>/`
     - GCP: `gs://<bucket>/<path>/`
   - **Compute:** serverless by default. When *classic cluster* is chosen, `databricks.yml` carries a
     placeholder `node_type_id` (`Standard_DS3_v2` Azure / `i3.xlarge` AWS / `n1-standard-4` GCP) with
     `autoscale` 1–2 workers and a `# TODO` — confirm these for your workspace/region before deploying.

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

Generated code reads source files from `ROSETTA_DATA_ROOT` (the portable `DATA_ROOT` constant),
which the bundle defaults to a Unity Catalog Volume (`/Volumes/<catalog>/<schema>/landing`).
**Upload your source files to that Volume before running.** For the DLT format, inter-table reads
use `dlt.read(...)`; for the Classic Spark Job format they use `spark.read.table(...)` and outputs
are written with `saveAsTable(...)`. Update the paths in the generated modules if your layout differs.

---

## Data migration

The per-job guide includes a section tailored to the chosen ingestion approach:

- **Historical (one-time):** PROC EXPORT → CSV/Parquet then upload to the storage root, or read the
  `.sas7bdat` directly (`spark-sas7bdat` / `pandas.read_sas`) and write Delta once.
- **Staging (ongoing):** Lakeflow Connect managed connectors, Spark JDBC against the source RDBMS, or
  Auto Loader (`cloudFiles`) to incrementally ingest files dropped into the provider storage root.

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
