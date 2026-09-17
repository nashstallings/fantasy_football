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


# --------------------------------------------------------------------------
# MERGE statement construction
# --------------------------------------------------------------------------

def test_merge_quotes_reserved_word_columns():
    """Regression: play-by-play has a column named `desc`, which is a BigQuery
    reserved word. Unquoted it fails with
    `Syntax error: Expected "(" but got keyword DESC` -- an error that points
    at a character offset rather than naming the column."""
    sql = bq_io.build_merge_sql(
        target="p.d.plays", staging="p.d._stg_plays",
        cols=["game_id", "play_id", "desc", "epa"],
        key=["game_id", "play_id"],
    )
    assert "`desc` = S.`desc`" in sql
    assert " desc = S.desc" not in sql


def test_merge_quotes_every_identifier():
    sql = bq_io.build_merge_sql(
        target="p.d.t", staging="p.d.s", cols=["a", "b", "c"], key=["a"],
    )
    assert "T.`a` = S.`a`" in sql
    assert "`b` = S.`b`" in sql and "`c` = S.`c`" in sql
    assert "(`a`, `b`, `c`)" in sql
    assert "S.`a`, S.`b`, S.`c`" in sql


def test_merge_key_columns_are_not_in_the_update_set():
    """Updating a column you matched on is redundant and BigQuery rejects it
    for partitioned/clustered targets."""
    sql = bq_io.build_merge_sql(
        target="p.d.t", staging="p.d.s",
        cols=["game_id", "play_id", "epa"], key=["game_id", "play_id"],
    )
    update_clause = sql.split("UPDATE SET")[1].split("WHEN NOT MATCHED")[0]
    assert "`epa`" in update_clause
    assert "`game_id`" not in update_clause
    assert "`play_id`" not in update_clause


def test_merge_uses_composite_key():
    sql = bq_io.build_merge_sql(
        target="p.d.t", staging="p.d.s",
        cols=["game_id", "play_id", "epa"], key=["game_id", "play_id"],
    )
    on_clause = sql.split("ON ")[1].split("WHEN")[0]
    assert "T.`game_id` = S.`game_id`" in on_clause
    assert "AND" in on_clause
    assert "T.`play_id` = S.`play_id`" in on_clause
