"""Orchestrates three independent write stages: raw nflreadpy tables, the
YPRR proxy table, and the Sleeper-based dynasty auction valuation table."""

import nflreadpy as nfl
import pandas as pd

from . import config
from .bigquery_io import set_table_description, write_tables
from .id_matching import resolve_gsis_ids
from .loaders import fetch_ff_opportunity, fetch_nextgen_stats, fetch_player_stats, fetch_players, fetch_snap_counts
from .sleeper_client import fetch_player_db, fetch_season_projections
from .valuation import build_auction_values, build_projection_table
from .yprr import TABLE_DESCRIPTION as YPRR_TABLE_DESCRIPTION
from .yprr import build_yprr_table


def run_nflreadpy_tables(season: int = config.CURRENT_SEASON, write_to_bq: bool = True) -> dict[str, pd.DataFrame]:
    tables = {
        "players": fetch_players(),
        "player_stats": fetch_player_stats(season),
        "snap_counts": fetch_snap_counts(season),
        "nextgen_stats": fetch_nextgen_stats(season),
        "ff_opportunity": fetch_ff_opportunity(season),
    }
    if write_to_bq:
        write_tables(tables, config.PROJECT_ID, config.NFLREADPY_DATASET_ID)
    return tables


def run_yprr(seasons: list[int] | None = None, write_to_bq: bool = True) -> pd.DataFrame:
    seasons = seasons or config.YPRR_SEASONS
    df = build_yprr_table(seasons=seasons, min_routes=config.YPRR_MIN_ROUTES).to_pandas()
    if write_to_bq:
        write_tables({"yprr_proxy": df}, config.PROJECT_ID, config.YPRR_DATASET_ID)
        set_table_description(config.PROJECT_ID, config.YPRR_DATASET_ID, "yprr_proxy", YPRR_TABLE_DESCRIPTION)
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
    tables["player_auction_values"] = run_auction_values(write_to_bq=write_to_bq)
    return tables
