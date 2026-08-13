"""Write pipeline outputs to BigQuery."""

import pandas as pd
import pandas_gbq


def write_tables(tables: dict[str, pd.DataFrame], project_id: str, dataset_id: str) -> None:
    for table_name, df in tables.items():
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
