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

# nflverse participation, which carries the per-play on-field roster, starts here.
PARTICIPATION_FIRST_SEASON = 2016

ROUTES_EXACT = "participation_on_field"
ROUTES_ESTIMATED = "snap_share_estimate"

TABLE_DESCRIPTION = (
    "YPRR / target rate over routes that are NOT charted routes run. Check "
    "routes_method per row: 'participation_on_field' counts the dropbacks a "
    "player was actually on the field for (nflverse participation, 2016+); "
    "'snap_share_estimate' is the older offense_snap_pct * team_dropbacks "
    "proxy, used where participation does not reach. Neither distinguishes "
    "running a route from blocking on a dropback, so both overstate routes "
    "for blocking-heavy TE/RB usage; the estimate additionally carries ~7% "
    "median error against the exact count. Not a substitute for PFF-sourced "
    "routes run."
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


def count_routes_on_field(seasons: list[int]) -> pl.DataFrame:
    """Exact count of dropbacks each skill player was on the field for.

    nflverse participation carries `offense_players`, the eleven gsis_ids on the
    field for every play. Intersecting that with dropbacks replaces the
    snap-share estimate with a count -- no aggregation, no rounding.

    This is a better denominator, not a correct one. Being on the field for a
    dropback still isn't running a route: a tight end kept in to block is on the
    field and running nothing. That residual bias is why the output column stays
    `routes_est` and the table description still says these aren't charted
    routes. What goes away is the *estimation* error, which on 2025 ran to a
    7.4% median and 36% on the worst blocking tight ends.

    Processed a season at a time: exploding eleven players per play across a
    decade at once is a needlessly large frame.
    """
    wanted = [s for s in seasons if s >= PARTICIPATION_FIRST_SEASON]
    if not wanted:
        return pl.DataFrame()

    skill = (
        nfl.load_players()
        .filter(pl.col("position").is_in(["WR", "TE", "RB"]))
        .select(["gsis_id", "display_name", "position"])
        .filter(pl.col("gsis_id").is_not_null())
        .unique(subset=["gsis_id"])
    )

    frames = []
    for season in wanted:
        try:
            part = nfl.load_participation(seasons=season)
        except Exception as exc:  # noqa: BLE001 - fall back to the estimate
            print(f"  participation unavailable for {season} ({exc}); "
                  f"falling back to the snap-share estimate")
            continue
        if part.height == 0:
            continue

        # Same dropback definition the estimate uses, so the two methods stay
        # comparable where they overlap.
        drops = (
            nfl.load_pbp(seasons=season)
            .filter((pl.col("pass_attempt") == 1) | (pl.col("sack") == 1))
            .select(
                pl.col("season"), pl.col("game_id"),
                pl.col("play_id").cast(pl.Int64).alias("_pid"),
                pl.col("posteam").alias("team"),
            )
        )

        frames.append(
            part.select(
                pl.col("nflverse_game_id").alias("game_id"),
                pl.col("play_id").cast(pl.Int64).alias("_pid"),
                pl.col("offense_players"),
            )
            .join(drops, on=["game_id", "_pid"], how="inner")
            .with_columns(pl.col("offense_players").str.split(";").alias("_ids"))
            .explode("_ids")
            .rename({"_ids": "gsis_id"})
            # An empty offense_players entry is not a player. The inner join
            # below would drop it anyway; filtering here keeps that independent
            # of how polars treats empty strings on split.
            .filter(pl.col("gsis_id").is_not_null() & (pl.col("gsis_id") != ""))
            .join(skill, on="gsis_id", how="inner")
            .group_by(["season", "gsis_id", "display_name", "position", "team"])
            .agg(
                pl.len().cast(pl.Float64).alias("routes_est"),
                pl.col("game_id").n_unique().alias("games"),
            )
            .rename({"display_name": "player"})
        )

    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="vertical_relaxed").with_columns(
        pl.lit(ROUTES_EXACT).alias("routes_method")
    )


def estimate_routes_run(seasons: list[int]) -> pl.DataFrame:
    """Per-player, per-game estimated routes run, rolled up to season.

    The fallback, used for seasons participation doesn't cover: before 2016,
    and the season in progress, which nflverse publishes only after the fact.
    """
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
        .with_columns(pl.lit(ROUTES_ESTIMATED).alias("routes_method"))
    )


def routes_for(seasons: list[int]) -> pl.DataFrame:
    """Routes per player-season-team, exact where participation reaches and
    estimated everywhere else, with `routes_method` recording which.

    Do not compare a `participation_on_field` row against a
    `snap_share_estimate` one without accounting for the method: the estimate
    runs about 7% off the count at the median, and much further on blocking
    tight ends, so a player's apparent year-over-year change across the 2016
    boundary can be entirely methodological.
    """
    exact = count_routes_on_field(seasons)
    covered = set(exact["season"].unique().to_list()) if exact.height else set()

    remaining = [s for s in seasons if s not in covered]
    if not remaining:
        return exact

    estimated = estimate_routes_run(remaining)
    if exact.height == 0:
        return estimated
    return pl.concat([exact, estimated], how="vertical_relaxed")


def load_receiving_production(seasons: list[int]) -> pl.DataFrame:
    """Targets and receiving yards per player-season-TEAM.

    Split by team on purpose. Routes are counted per team (a player who is
    traded has a row for each), so production has to match that grain --
    aggregating to the player-season instead attaches a full season of yards to
    every team row, and a traded player's YPRR comes out inflated on all of
    them. Jakobi Meyers in 2025 is the worked example: 495 yards on 237 routes
    for JAX and 352 on 293 for LV, which the season-level join reported as 847
    yards against each.
    """
    weekly = nfl.load_player_stats(seasons=seasons, summary_level="week")
    by_team = weekly.group_by(["season", "player_id", "team"]).agg(
        pl.col("targets").sum().alias("targets"),
        pl.col("receiving_yards").sum().alias("receiving_yards"),
    )
    return by_team.rename({"player_id": "gsis_id"})


def build_yprr_table(seasons: list[int], min_routes: int = 50) -> pl.DataFrame:
    """Full pipeline: join routes proxy to production, compute YPRR and
    target rate. min_routes filters out tiny/noisy samples."""
    routes = routes_for(seasons)
    production = load_receiving_production(seasons)

    df = (
        routes.join(production, on=["season", "gsis_id", "team"], how="inner")
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
            "routes_method",
        ]
    )
