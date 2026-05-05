# Databricks notebook source
# MAGIC %md
# MAGIC # Delta Row Editor — setup
# MAGIC
# MAGIC Creates the schema, target table (`customers`), and audit table
# MAGIC (`customers_audit`), then seeds the target with sample rows.
# MAGIC
# MAGIC Run on a serverless cluster. Edit the widgets below if you want to
# MAGIC point at a different catalog or schema.

# COMMAND ----------

dbutils.widgets.text("catalog", "lr_serverless_aws_us_catalog")
dbutils.widgets.text("schema", "delta_row_editor")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
target = f"{catalog}.{schema}.customers"
audit = f"{catalog}.{schema}.customers_audit"
print(f"target: {target}")
print(f"audit:  {audit}")

# COMMAND ----------

# MAGIC %md ## Schema + tables

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {target} (
      customer_id     STRING NOT NULL,
      name            STRING,
      email           STRING,
      status          STRING,
      region          STRING,
      lifetime_value  DECIMAL(12, 2),
      updated_at      TIMESTAMP
    ) USING DELTA
    TBLPROPERTIES (delta.enableChangeDataFeed = true)
    """
)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {audit} (
      pk_value      STRING NOT NULL,
      column_name   STRING NOT NULL,
      old_value     STRING,
      new_value     STRING,
      changed_by    STRING,
      changed_at    TIMESTAMP
    ) USING DELTA
    """
)

# COMMAND ----------

# MAGIC %md ## Seed sample customers

# COMMAND ----------

from pyspark.sql import functions as F

sample = [
    ("C001", "Ada Lovelace",     "ada@example.com",     "active",   "EMEA", 12500.00),
    ("C002", "Alan Turing",      "alan@example.com",    "active",   "EMEA",  8400.50),
    ("C003", "Grace Hopper",     "grace@example.com",   "churned",  "AMER",  3200.00),
    ("C004", "Linus Torvalds",   "linus@example.com",   "active",   "EMEA",   650.75),
    ("C005", "Margaret Hamilton","margaret@example.com","prospect", "AMER",     0.00),
    ("C006", "Edsger Dijkstra",  "edsger@example.com",  "active",   "EMEA",  4200.10),
    ("C007", "Barbara Liskov",   "barbara@example.com", "active",   "AMER",  9100.00),
    ("C008", "Donald Knuth",     "don@example.com",     "active",   "AMER",  7800.20),
]

df = spark.createDataFrame(
    sample,
    schema="customer_id STRING, name STRING, email STRING, status STRING, region STRING, lifetime_value DECIMAL(12,2)",
).withColumn("updated_at", F.current_timestamp())

(
    df.write.mode("overwrite").saveAsTable(target)
)

# COMMAND ----------

display(spark.table(target))
