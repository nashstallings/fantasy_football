"""Tests for the BigQuery dataframe conversion.

No GCP auth -- these cover the pandas/polars dtype handoff only, which is where
the first backfill actually broke.
"""

import polars as pl

from nfl_pbp import bq_io


def test_date_columns_survive_as_bigquery_date():
    """Regression: polars Date -> `.to_pandas()` gives datetime64, which
    BigQuery autodetects as DATETIME, and `PARTITION BY game_date` then fails
    with a 400 that says nothing about dataframe dtypes."""
    df = pl.DataFrame({"game_date": ["2024-09-05", "2024-09-08"]}).with_columns(
        pl.col("game_date").str.to_date(strict=False)
    )
    assert df.schema["game_date"] == pl.Date

    # the naive conversion is what broke
    assert str(df.to_pandas()["game_date"].dtype).startswith("datetime64")

    out = bq_io.to_bq_dataframe(df)
    assert str(out["game_date"].dtype) == "dbdate"


def test_null_dates_are_preserved():
    df = pl.DataFrame({"game_date": ["2024-09-05", None]}).with_columns(
        pl.col("game_date").str.to_date(strict=False)
    )
    out = bq_io.to_bq_dataframe(df)
    assert str(out["game_date"].dtype) == "dbdate"
    assert out["game_date"].isna().sum() == 1


def test_non_date_columns_are_untouched():
    df = pl.DataFrame({
        "game_id": ["g1"],
        "play_id": [1],
        "epa": [0.5],
        "game_date": ["2024-09-05"],
    }).with_columns(pl.col("game_date").str.to_date(strict=False))

    out = bq_io.to_bq_dataframe(df)
    # pandas may give strings `object` or `StringDtype` depending on version --
    # what matters is that only the date column was rewritten.
    assert str(out["game_id"].dtype) in ("object", "str", "string")
    assert str(out["play_id"].dtype).startswith("int")
    assert str(out["epa"].dtype).startswith("float")
    assert str(out["game_date"].dtype) == "dbdate"


def test_frame_without_dates_round_trips_unchanged():
    df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    out = bq_io.to_bq_dataframe(df)
    assert list(out.columns) == ["a", "b"]
    assert len(out) == 2
