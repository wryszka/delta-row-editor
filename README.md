# delta-row-editor

A minimal Databricks App that lets end users edit rows in a Delta table from
the browser. Streamlit UI, deployed via Databricks Asset Bundles.

- **No Lakebase.** Reads/writes go through a serverless SQL warehouse.
- **MERGE + audit.** Each save produces a `MERGE INTO target` per row and
  one audit-table row per changed cell.
- **Optimistic concurrency.** The MERGE includes `WHEN MATCHED AND
  target.updated_at = source.original_updated_at`; if any row was edited by
  someone else since the data was loaded, the save fails loudly.
- **On-behalf-of-user OAuth.** SQL calls run as the signed-in user (not the
  app service principal), so Unity Catalog audit logs attribute edits
  correctly.

> About this demo: a sample Databricks App provided as-is for demonstration
> purposes. No client names or internal references.

## File layout

```
delta-row-editor/
├── app.py                 # Streamlit UI
├── app.yaml               # Databricks Apps runtime config
├── databricks.yml         # DAB bundle: variables, targets, app resource
├── requirements.txt
├── src/
│   ├── auth.py            # X-Forwarded-* header parsing, local fallback
│   ├── db.py              # SQL warehouse connection (OBO token)
│   ├── editor.py          # diff + MERGE + concurrency check
│   └── audit.py           # audit-row INSERT helpers
└── notebooks/
    └── 00_setup_data.py   # creates schema, tables, seeds sample rows
```

## Prerequisites

1. **Workspace with a serverless SQL warehouse.** Note its warehouse ID.
2. **Unity Catalog grants** for the user(s) editing data:
   - `USE CATALOG` on the catalog
   - `USE SCHEMA` on the schema
   - `SELECT, MODIFY` on the target table
   - `MODIFY` on the audit table (or `SELECT, MODIFY`)
3. **App service principal grants:** the SP needs `CAN_USE` on the warehouse
   (handled automatically by the bundle's `resources` block). It does **not**
   need table grants — table access is via the user's OBO token.

## One-time data setup

Open `notebooks/00_setup_data.py` in the workspace and run it on a serverless
cluster. It creates `customers`, `customers_audit`, and seeds eight sample
rows. Adjust the `catalog` / `schema` widgets if needed.

The DDL it runs:

```sql
CREATE TABLE customers (
  customer_id     STRING NOT NULL,
  name            STRING,
  email           STRING,
  status          STRING,
  region          STRING,
  lifetime_value  DECIMAL(12, 2),
  updated_at      TIMESTAMP
) USING DELTA;

CREATE TABLE customers_audit (
  pk_value      STRING NOT NULL,
  column_name   STRING NOT NULL,
  old_value     STRING,
  new_value     STRING,
  changed_by    STRING,
  changed_at    TIMESTAMP
) USING DELTA;
```

## Deploy

Defaults target the `lr_serverless_aws_us_catalog.delta_row_editor` schema.
Override per environment with bundle variables.

```bash
databricks bundle deploy -t dev \
  --var warehouse_id=<your-serverless-warehouse-id>

databricks bundle run delta_row_editor -t dev
```

To override table or column names:

```bash
databricks bundle deploy -t dev \
  --var warehouse_id=<id> \
  --var catalog=my_catalog \
  --var schema=my_schema \
  --var target_table_name=customers \
  --var pk_column=customer_id
```

For prod, set `warehouse_id` (and any other overrides) in
`databricks.yml` under `targets.prod.variables`, or pass via `--var`.

## Local dev

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt --native-tls

export DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
export DATABRICKS_CONFIG_PROFILE=DEFAULT
export WAREHOUSE_ID=<id>
export TARGET_TABLE=lr_serverless_aws_us_catalog.delta_row_editor.customers
export AUDIT_TABLE=lr_serverless_aws_us_catalog.delta_row_editor.customers_audit
export PK_COLUMN=customer_id

streamlit run app.py
```

When running locally the app uses your CLI profile for auth (no OBO token),
shows a warning, and writes audit rows attributed to `(local dev)`.

## Caveats

- **Multi-statement transactions.** Databricks SQL does not support them.
  Saves apply MERGEs row-by-row, then INSERT audit rows. If the audit INSERT
  fails after MERGEs succeed, the app raises and surfaces partial state. For
  most demo workloads this is fine; production deployments should consider
  consolidating into a single `INSERT ... SELECT` audit pipeline driven by
  CDF on the target table.
- **Schema changes.** The editor reflects whatever columns the target table
  has at refresh time. Adding a column requires re-running the setup
  notebook (or a separate `ALTER TABLE`) and refreshing the app.
