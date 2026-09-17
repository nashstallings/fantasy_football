"""Bronze layer: load raw play-by-play and normalize types for BigQuery.

Typed passthrough only -- no derived columns, no filtering, no opinions. If a
value is wrong here it is wrong upstream in nflverse, which keeps the silver
layer's logic the only place anything can go subtly wrong.
"""

from __future__ import annotations

import nflreadpy as nfl
import polars as pl

from . import config


def load_raw(seasons: int | list[int]) -> pl.DataFrame:
    """Raw play-by-play straight from nflverse."""
    return nfl.load_pbp(seasons=seasons)


def load_ftn(seasons: int | list[int]) -> pl.DataFrame | None:
    """FTN charting for the pressure-adjacent signals, or None when the seasons
    requested predate FTN coverage (2022) or the fetch fails.

    Returning None rather than raising is deliberate: FTN is an enhancement to
    `true_pressure`, not a requirement, and a backfill of 2016 should not die
    because charting doesn't exist for those years.
    """
    wanted = [seasons] if isinstance(seasons, int) else list(seasons)
    covered = [s for s in wanted if s >= config.FTN_FIRST_SEASON]
    if not covered:
        return None
    try:
        return nfl.load_ftn_charting(seasons=covered)
    except Exception as exc:  # noqa: BLE001 - enhancement only, never fatal
        print(f"  FTN charting unavailable for {covered} ({exc}); "
              f"true_pressure will fall back to pbp-only for these seasons")
        return None


def normalize(df: pl.DataFrame) -> pl.DataFrame:
    """Coerce the handful of columns whose nflverse types don't survive contact
    with BigQuery.

    - `game_date` arrives as a STRING. BigQuery cannot partition on STRING, and
      the whole table is partitioned on it, so it must become a DATE.
    - `play_id` arrives as Float64. It is half the MERGE key; a float key is a
      correctness hazard (1.0 vs 1 comparisons), so it becomes INT64.
    - `season` / `week` become INT64 so they cluster and join cleanly against
      the `nflreadpy` dataset, where they are already integers.
    """
    casts = []
    if "game_date" in df.columns and df.schema["game_date"] != pl.Date:
        casts.append(pl.col("game_date").str.to_date(strict=False).alias("game_date"))
    if "play_id" in df.columns:
        casts.append(pl.col("play_id").cast(pl.Int64).alias("play_id"))
    for col in ("season", "week"):
        if col in df.columns:
            casts.append(pl.col(col).cast(pl.Int64).alias(col))
    return df.with_columns(casts) if casts else df


def build(seasons: int | list[int]) -> pl.DataFrame:
    """Load + normalize. This is what lands in pbp_bronze.plays."""
    df = normalize(load_raw(seasons))

    n, unique = df.height, df.select(config.PLAY_KEY).unique().height
    if n != unique:
        raise ValueError(
            f"play key {config.PLAY_KEY} is not unique ({n} rows, {unique} distinct) -- "
            "MERGE would silently drop or duplicate rows, refusing to write"
        )
    return df
