"""Estimates historical Yards Per Route Run (YPRR) and route-adjusted
target rate (targets / estimated routes run) for WR/TE/RB, using a
snap-share proxy since nflverse/nflreadpy has no free per-player
route-participation field before 2022 (and FTN charting, 2022+,
doesn't carry one either -- it's play-context data, not a route flag).

METHODOLOGY / CAVEATS (read before trusting the numbers):
  routes_est = offense_snap_pct * team_dropbacks (per game, summed to season)

  This assumes a player runs a route on every offensive snap they're on
  the field for during a "dropback" play. In practice:
    - Overstates routes for in-line/blocking TEs and pass-pro RBs
      (they're on the field but not running a route on some dropbacks)
    - Slightly understates for players subbed out specifically on
      known-pass/empty looks (rare, mostly elite slot WRs)
    - "Dropback" here = pass_attempt == 1 or sack == 1 (scrambles that
      start as dropbacks are included; pure designed QB runs are not)

  For real routes run, PFF is the industry-standard paid source. This
  proxy is a reasonable stand-in for relative player comparison within
  the same position group, but treat absolute YPRR values as directional,
  not precise -- especially for TEs and RBs where blocking-snap
  contamination is worst.

DATA SOURCES (all via nflreadpy, free):
  - load_pbp()          -> team dropbacks per game
  - load_snap_counts()  -> player offense_pct per game (2012+)
  - load_player_stats() -> targets, receiving_yards (season/week)
  - load_players()      -> gsis_id <-> pfr_id crosswalk
                            (snap_counts keys on pfr_id, player_stats
                             keys on gsis_id -- these must be joined)

OUTPUT GRAIN: season, player (gsis_id), team, position
"""

import nflreadpy as nfl
import polars as pl

TABLE_DESCRIPTION = (
    "Estimated YPRR / target rate via snap-share proxy "
    "(offense_snap_pct * team_dropbacks), NOT true charted routes run. "
    "See yprr.py module docstring for methodology and known biases "
    "(overstates for blocking-heavy TE/RB usage). Free-data proxy only; "
    "not a substitute for PFF-sourced routes run."
)


def load_team_dropbacks(seasons: list[int]) -> pl.DataFrame:
    """Team dropbacks per game: pass attempts + sacks, by posteam/game."""
    pbp = nfl.load_pbp(seasons=seasons)
    return (
        pbp.filter((pl.col("pass_attempt") == 1) | (pl.col("sack") == 1))
        .group_by(["season", "week", "game_id", "posteam"])
        .agg(pl.len().alias("team_dropbacks"))
        .rename({"posteam": "team"})
    )


def load_player_id_crosswalk() -> pl.DataFrame:
    """gsis_id <-> pfr_id, needed because snap_counts and player_stats
    key on different id systems."""
    players = nfl.load_players()
    return (
        players.select(["gsis_id", "pfr_id", "display_name"])
        .filter(pl.col("gsis_id").is_not_null() & pl.col("pfr_id").is_not_null())
        .unique(subset=["pfr_id"])
    )


def estimate_routes_run(seasons: list[int]) -> pl.DataFrame:
    """Per-player, per-game estimated routes run, rolled up to season."""
    snaps = nfl.load_snap_counts(seasons=seasons).filter(pl.col("position").is_in(["WR", "TE", "RB"]))
    dropbacks = load_team_dropbacks(seasons)
    crosswalk = load_player_id_crosswalk()

    game_level = (
        snaps.join(dropbacks, on=["season", "week", "team"], how="inner")
        .with_columns((pl.col("offense_pct") * pl.col("team_dropbacks")).alias("routes_est_game"))
        .join(crosswalk, left_on="pfr_player_id", right_on="pfr_id", how="left")
    )

    return (
        game_level.group_by(["season", "gsis_id", "player", "position", "team"])
        .agg(
            pl.col("routes_est_game").sum().round(0).alias("routes_est"),
            pl.col("game_id").n_unique().alias("games"),
        )
        .filter(pl.col("gsis_id").is_not_null())
    )


def load_receiving_production(seasons: list[int]) -> pl.DataFrame:
    """Season-level targets and receiving yards per player."""
    weekly = nfl.load_player_stats(seasons=seasons, summary_level="week")
    season_level = weekly.group_by(["season", "player_id"]).agg(
        pl.col("targets").sum().alias("targets"),
        pl.col("receiving_yards").sum().alias("receiving_yards"),
    )
    return season_level.rename({"player_id": "gsis_id"})


def build_yprr_table(seasons: list[int], min_routes: int = 50) -> pl.DataFrame:
    """Full pipeline: join routes proxy to production, compute YPRR and
    target rate. min_routes filters out tiny/noisy samples."""
    routes = estimate_routes_run(seasons)
    production = load_receiving_production(seasons)

    df = (
        routes.join(production, on=["season", "gsis_id"], how="inner")
        .filter(pl.col("routes_est") >= min_routes)
        .with_columns(
            (pl.col("receiving_yards") / pl.col("routes_est")).round(3).alias("yprr_est"),
            (pl.col("targets") / pl.col("routes_est")).round(3).alias("target_rate_est"),
        )
        .sort(["season", "yprr_est"], descending=[True, True])
    )
    return df.select(
        [
            "season",
            "gsis_id",
            "player",
            "position",
            "team",
            "games",
            "routes_est",
            "targets",
            "receiving_yards",
            "yprr_est",
            "target_rate_est",
        ]
    )
