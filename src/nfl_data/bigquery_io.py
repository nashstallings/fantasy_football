"""Write pipeline outputs to BigQuery."""

import pandas as pd
import pandas_gbq


class EmptyWriteRefused(RuntimeError):
    """An empty frame was about to replace a table. See write_tables."""


def write_tables(
    tables: dict[str, pd.DataFrame],
    project_id: str,
    dataset_id: str,
    allow_empty: bool = False,
) -> None:
    """Replace each table with the frame given.

    An empty frame is refused rather than written. Every write here is
    if_exists="replace", so writing zero rows does not leave the table
    unchanged -- it deletes it and creates an empty one. That was unreachable
    while the season was a hardcoded literal pointing at a finished season;
    once the season is resolved at run time it is one upstream outage, or one
    scheduled run in the hours before a season's first file is published, away
    from wiping a table nobody asked to change.

    Pass allow_empty=True if a genuinely empty table is what you want.
    """
    for table_name, df in tables.items():
        if len(df) == 0 and not allow_empty:
            raise EmptyWriteRefused(
                f"{dataset_id}.{table_name}: refusing to replace a table with 0 rows. "
                f"The source returned nothing -- likely an upstream outage, or a season "
                f"whose files are not published yet. Nothing was written, so the existing "
                f"table is intact. Pass allow_empty=True to override."
            )
        pandas_gbq.to_gbq(df, f"{dataset_id}.{table_name}", project_id=project_id, if_exists="replace")
        print(f"Wrote {len(df):,} rows to {dataset_id}.{table_name}")


def set_table_description(project_id: str, dataset_id: str, table_name: str, description: str) -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    table_ref = client.get_table(f"{project_id}.{dataset_id}.{table_name}")
    table_ref.description = description
    client.update_table(table_ref, ["description"])


def read_table(project_id: str, dataset_id: str, table_name: str) -> pd.DataFrame | None:
    """Return the full contents of a BigQuery table, or None if it doesn't exist yet."""
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    try:
        return client.query(f"SELECT * FROM `{project_id}.{dataset_id}.{table_name}`").to_dataframe()
    except NotFound:
        return None


def verify(project_id: str, dataset_id: str) -> pd.DataFrame:
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    query = f"SELECT table_id, row_count FROM `{project_id}.{dataset_id}.__TABLES__`"
    return client.query(query).to_dataframe()
