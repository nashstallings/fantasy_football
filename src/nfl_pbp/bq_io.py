"""BigQuery I/O: dataset/table creation, idempotent MERGE, and view management.

Every write in this pipeline goes through `merge_table`, keyed on
(game_id, play_id) for bronze/silver and on the natural rollup key for gold.
Nothing appends blindly, because both jobs can be re-triggered by hand from the
Actions UI and a re-run must not duplicate rows.
"""

from __future__ import annotations

import polars as pl
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from . import config


def client(project_id: str | None = None) -> bigquery.Client:
    return bigquery.Client(project=project_id or config.PROJECT_ID)


def ensure_dataset(bq: bigquery.Client, dataset_id: str) -> None:
    ref = bigquery.Dataset(f"{bq.project}.{dataset_id}")
    ref.location = config.LOAD_LOCATION
    try:
        bq.get_dataset(ref)
    except NotFound:
        bq.create_dataset(ref)
        print(f"  created dataset {dataset_id}")


def _staging_id(bq: bigquery.Client, dataset_id: str, table: str) -> str:
    return f"{bq.project}.{dataset_id}._stg_{table}"


def load_staging(
    bq: bigquery.Client, df: pl.DataFrame, dataset_id: str, table: str
) -> str:
    """Drop the frame into a throwaway table so MERGE has something to read."""
    staging = _staging_id(bq, dataset_id, table)
    job = bq.load_table_from_dataframe(
        df.to_pandas(),
        staging,
        job_config=bigquery.LoadJobConfig(
            write_disposition="WRITE_TRUNCATE", autodetect=True
        ),
    )
    job.result()
    return staging


def merge_table(
    bq: bigquery.Client,
    df: pl.DataFrame,
    dataset_id: str,
    table: str,
    key: list[str],
    partition_field: str | None = None,
    cluster_fields: list[str] | None = None,
) -> int:
    """Idempotently upsert `df` into `dataset.table` on `key`.

    First write creates the table (partitioned/clustered as asked) directly from
    the staging load; subsequent writes MERGE. Re-running the same seasons is
    therefore a no-op on row count, which is what makes the backfill safe to
    retrigger.

    Returns the table's row count after the write.
    """
    if df.height == 0:
        print(f"  {dataset_id}.{table}: nothing to write")
        return _row_count(bq, dataset_id, table)

    ensure_dataset(bq, dataset_id)
    staging = load_staging(bq, df, dataset_id, table)
    target = f"{bq.project}.{dataset_id}.{table}"

    try:
        bq.get_table(target)
        exists = True
    except NotFound:
        exists = False

    if not exists:
        ddl_extra = ""
        if partition_field:
            ddl_extra += f"\nPARTITION BY {partition_field}"
        if cluster_fields:
            ddl_extra += f"\nCLUSTER BY {', '.join(cluster_fields)}"
        bq.query(
            f"CREATE TABLE `{target}`{ddl_extra} AS SELECT * FROM `{staging}`"
        ).result()
        print(f"  created {dataset_id}.{table}")
    else:
        cols = [f.name for f in bq.get_table(staging).schema]
        on = " AND ".join(f"T.{k} = S.{k}" for k in key)
        updates = ", ".join(f"{c} = S.{c}" for c in cols if c not in key)
        insert_cols = ", ".join(cols)
        insert_vals = ", ".join(f"S.{c}" for c in cols)
        bq.query(
            f"""
            MERGE `{target}` T
            USING `{staging}` S
            ON {on}
            WHEN MATCHED THEN UPDATE SET {updates}
            WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
            """
        ).result()

    bq.delete_table(staging, not_found_ok=True)
    n = _row_count(bq, dataset_id, table)
    print(f"  {dataset_id}.{table}: merged {df.height:,} rows -> {n:,} total")
    return n


def _row_count(bq: bigquery.Client, dataset_id: str, table: str) -> int:
    try:
        return bq.get_table(f"{bq.project}.{dataset_id}.{table}").num_rows
    except NotFound:
        return 0


def replace_view(bq: bigquery.Client, dataset_id: str, view: str, sql: str) -> None:
    """Create or replace a view. Views are recomputed on read, so tuning the
    logic never requires re-running a backfill."""
    ensure_dataset(bq, dataset_id)
    target = f"{bq.project}.{dataset_id}.{view}"
    bq.query(f"CREATE OR REPLACE VIEW `{target}` AS\n{sql}").result()
    print(f"  view {dataset_id}.{view} updated")


def set_table_description(
    bq: bigquery.Client, dataset_id: str, table: str, description: str
) -> None:
    ref = bq.get_table(f"{bq.project}.{dataset_id}.{table}")
    ref.description = description
    bq.update_table(ref, ["description"])


def read_silver(
    bq: bigquery.Client, seasons: list[int] | None = None, weeks: list[int] | None = None
) -> pl.DataFrame:
    """Pull enriched plays back out for the gold rollups."""
    where = []
    if seasons:
        where.append(f"season IN ({', '.join(str(s) for s in seasons)})")
    if weeks:
        where.append(f"week IN ({', '.join(str(w) for w in weeks)})")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = (
        f"SELECT * FROM `{bq.project}.{config.SILVER_DATASET}.{config.SILVER_PLAYS}` {clause}"
    )
    return pl.from_pandas(bq.query(sql).to_dataframe())
