"""Orchestrates the pipeline's independent write stages: raw nflreadpy
tables and the YPRR proxy table run by default via run(). The Sleeper-based
dynasty auction valuation table (run_auction_values) is available but not
part of the default run -- call it explicitly if you want it."""

import nflreadpy as nfl
import pandas as pd
import polars as pl

from . import config
from .bigquery_io import set_table_description, write_tables
from .id_matching import resolve_gsis_ids
from .loaders import fetch_ff_opportunity, fetch_nextgen_stats, fetch_player_stats, fetch_players, fetch_snap_counts
from .sleeper_client import fetch_player_db, fetch_season_projections
from .valuation import build_auction_values, build_projection_table
from .yprr import TABLE_DESCRIPTION as YPRR_TABLE_DESCRIPTION
from .yprr import build_yprr_table


def run_nflreadpy_tables(
    seasons: int | list[int] | None = None, write_to_bq: bool = True
) -> dict[str, pd.DataFrame]:
    """Refresh the raw nflreadpy tables for `seasons`.

    Defaults to config.raw_seasons(), a window ending at the current season --
    resolved now, not at import, so the season rolls over on its own.
    """
    seasons = seasons if seasons is not None else config.raw_seasons()
    print(f"Loading nflreadpy tables for {seasons}")
    tables = {
        "players": fetch_players(),
        "player_stats": fetch_player_stats(seasons),
        "snap_counts": fetch_snap_counts(seasons),
        "nextgen_stats": fetch_nextgen_stats(seasons),
        "ff_opportunity": fetch_ff_opportunity(seasons),
    }
    if write_to_bq:
        write_tables(tables, config.PROJECT_ID, config.NFLREADPY_DATASET_ID)
    return tables


def run_yprr(
    seasons: list[int] | None = None,
    write_to_bq: bool = True,
    season_types: tuple[str, ...] = config.YPRR_SEASON_TYPES,
) -> pd.DataFrame:
    """Build the YPRR proxy table, one block of rows per season_type.

    Both REG and POST are published, kept apart by the season_type column.
    Every query against this table needs a season_type predicate -- without
    one a player with a playoff run comes back as two rows, which is the
    point: those are two different samples and were never addable.
    """
    seasons = seasons or config.yprr_seasons()
    blocks = [
        build_yprr_table(
            seasons=seasons,
            min_routes=config.YPRR_MIN_ROUTES,
            season_type=season_type,
        )
        for season_type in season_types
    ]
    df = pl.concat(blocks, how="vertical_relaxed").to_pandas()
    if write_to_bq:
        write_tables({"yprr_proxy": df}, config.PROJECT_ID, config.NFLREADPY_DATASET_ID)
        set_table_description(config.PROJECT_ID, config.NFLREADPY_DATASET_ID, "yprr_proxy", YPRR_TABLE_DESCRIPTION)
    return df


def run_auction_values(season: int = config.PROJECTION_SEASON, write_to_bq: bool = True) -> pd.DataFrame:
    player_db = fetch_player_db()
    projections = fetch_season_projections(season)
    nfl_players = nfl.load_players().to_pandas()

    projection_table = build_projection_table(player_db, projections)
    projection_table = resolve_gsis_ids(projection_table, nfl_players, config.SYNTHETIC_GSIS_OVERRIDES)
    auction_values = build_auction_values(projection_table, season)

    if write_to_bq:
        write_tables({"player_auction_values": auction_values}, config.PROJECT_ID, config.VALUATION_DATASET_ID)
    return auction_values


def run(write_to_bq: bool = True) -> dict[str, pd.DataFrame]:
    tables = run_nflreadpy_tables(write_to_bq=write_to_bq)
    tables["yprr_proxy"] = run_yprr(write_to_bq=write_to_bq)
    return tables
