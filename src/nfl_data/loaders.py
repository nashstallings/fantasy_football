"""Core nflreadpy pulls, filtered to fantasy-relevant skill positions."""

import pandas as pd
import nflreadpy as nfl

from . import config


def _filter_positions(df: pd.DataFrame, position_col: str = "position") -> pd.DataFrame:
    return df[df[position_col].isin(config.FANTASY_POSITIONS)].reset_index(drop=True)


def fetch_players() -> pd.DataFrame:
    """Skill-position players, enriched with cross-platform IDs (Sleeper, ESPN, etc.)."""
    players = nfl.load_players().to_pandas()
    players = _filter_positions(players)

    ids = nfl.load_ff_playerids().to_pandas()
    merged = pd.merge(players, ids, on="gsis_id", how="left", suffixes=("", "_dup"))
    return merged.drop(columns=merged.filter(regex="_dup$").columns)


def fetch_player_stats(season: int) -> pd.DataFrame:
    """Weekly stat lines with a within-week, within-position PPR rank added."""
    stats = nfl.load_player_stats(seasons=season, summary_level="week").to_pandas()
    stats = _filter_positions(stats)
    stats["weekly_positional_rank"] = stats.groupby(["week", "position"])["fantasy_points_ppr"].rank(
        method="min", ascending=False
    )
    return stats


def fetch_snap_counts(season: int) -> pd.DataFrame:
    snaps = nfl.load_snap_counts(seasons=season).to_pandas()
    return _filter_positions(snaps)


def fetch_nextgen_stats(season: int) -> pd.DataFrame:
    """Passing + receiving + rushing Next Gen Stats, stacked long."""
    frames = [
        nfl.load_nextgen_stats(seasons=season, stat_type=stat_type).to_pandas()
        for stat_type in ("passing", "receiving", "rushing")
    ]
    combined = pd.concat(frames, ignore_index=True)
    return _filter_positions(combined, position_col="player_position")


def fetch_ff_opportunity(season: int) -> pd.DataFrame:
    opportunity = nfl.load_ff_opportunity(seasons=season, stat_type="weekly", model_version="latest").to_pandas()
    return _filter_positions(opportunity)
