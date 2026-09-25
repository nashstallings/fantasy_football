"""Core nflreadpy pulls, filtered to fantasy-relevant skill positions."""

import pandas as pd
import nflreadpy as nfl

from . import config

# nflreadpy hardcodes the DynastyProcess player-id file behind the
# github.com/<owner>/<repo>/raw/... redirect, which intermittently 404s
# (GitHub rate-limits that redirect layer, and Colab's shared egress IPs get
# hit hardest). The file itself is fine -- this is the same object served
# directly, skipping the flaky redirect.
FF_PLAYERIDS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"


def _filter_positions(df: pd.DataFrame, position_col: str = "position") -> pd.DataFrame:
    return df[df[position_col].isin(config.FANTASY_POSITIONS)].reset_index(drop=True)


def load_ff_playerids() -> pd.DataFrame:
    """DynastyProcess cross-platform player IDs, falling back to the direct
    raw.githubusercontent.com URL when nflreadpy's redirect-based fetch fails."""
    try:
        return nfl.load_ff_playerids().to_pandas()
    except Exception as exc:
        print(f"load_ff_playerids() via nflreadpy failed ({exc}); retrying direct: {FF_PLAYERIDS_URL}")
        return pd.read_csv(FF_PLAYERIDS_URL, low_memory=False)


def fetch_players() -> pd.DataFrame:
    """Skill-position players, enriched with cross-platform IDs (Sleeper, ESPN, etc.)."""
    players = nfl.load_players().to_pandas()
    players = _filter_positions(players)

    ids = load_ff_playerids()
    merged = pd.merge(players, ids, on="gsis_id", how="left", suffixes=("", "_dup"))
    return merged.drop(columns=merged.filter(regex="_dup$").columns)


def fetch_player_stats(seasons: int | list[int]) -> pd.DataFrame:
    """Weekly stat lines with a within-week, within-position PPR rank added.

    The rank groups on season as well as week. It has to: these loads span
    more than one season now, and grouping on week alone pools Week 1 of every
    season into a single ranking. Across 2025+2026 that moved 1,397 of 7,037
    rows and pushed the worst rank from 152 to 301 -- a number that reads like
    a positional rank and isn't one.
    """
    stats = nfl.load_player_stats(seasons=seasons, summary_level="week").to_pandas()
    stats = _filter_positions(stats)
    stats["weekly_positional_rank"] = stats.groupby(["season", "week", "position"])[
        "fantasy_points_ppr"
    ].rank(method="min", ascending=False)
    return stats


def fetch_snap_counts(seasons: int | list[int]) -> pd.DataFrame:
    snaps = nfl.load_snap_counts(seasons=seasons).to_pandas()
    return _filter_positions(snaps)


def fetch_nextgen_stats(seasons: int | list[int]) -> pd.DataFrame:
    """Passing + receiving + rushing Next Gen Stats, stacked long."""
    frames = [
        nfl.load_nextgen_stats(seasons=seasons, stat_type=stat_type).to_pandas()
        for stat_type in ("passing", "receiving", "rushing")
    ]
    combined = pd.concat(frames, ignore_index=True)
    return _filter_positions(combined, position_col="player_position")


def fetch_ff_opportunity(seasons: int | list[int]) -> pd.DataFrame:
    opportunity = nfl.load_ff_opportunity(
        seasons=seasons, stat_type="weekly", model_version="latest"
    ).to_pandas()
    return _filter_positions(opportunity)


def fetch_schedules(seasons: int | list[int]) -> pd.DataFrame:
    """Every game -- played or not -- for `seasons`, plus the following season
    once nflverse publishes it.

    The one game-level table here, so no position filter. It carries future
    games too, which is what makes it useful: sleeper_dynasty_overview derives
    each team's bye as the one regular-season week it has no game, and that
    only works against a complete schedule.

    The extra season is for the offseason. current_season() doesn't roll over
    until September, but the next schedule comes out in May, and byes for the
    season about to be drafted for are the ones worth having. Asking for a
    season that isn't published yet returns no rows rather than raising, so
    requesting it unconditionally is safe -- it just appears once it exists.
    """
    wanted = [seasons] if isinstance(seasons, int) else list(seasons)
    wanted = sorted(set(wanted) | {max(wanted) + 1})
    return nfl.load_schedules(seasons=wanted).to_pandas()
