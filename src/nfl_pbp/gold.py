"""Gold layer: rollups that downstream tools query directly.

Like silver, these are pure polars transforms -- they take enriched plays and
return a frame. The jobs handle reading and writing; nothing here touches
BigQuery, so the aggregation logic is testable on fixtures.
"""

from __future__ import annotations

import polars as pl

from . import config

# Explosive-play thresholds, by convention: 20+ through the air, 10+ on the ground.
EXPLOSIVE_PASS_YARDS = 20
EXPLOSIVE_RUSH_YARDS = 10
RED_ZONE_YARDLINE = 20


def _scrimmage(plays: pl.DataFrame) -> pl.DataFrame:
    keep = pl.col("play_type").is_in(["pass", "run"])
    if "aborted_play" in plays.columns:
        keep = keep & (pl.col("aborted_play").fill_null(0) == 0)
    return plays.filter(keep)


# ---------------------------------------------------------------------------
# player_weekly_efficiency
# ---------------------------------------------------------------------------

def player_weekly_efficiency(
    plays: pl.DataFrame,
    snaps: pl.DataFrame | None = None,
    players: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """One row per player / season / week / team.

    Volume and share metrics use every scrimmage play, because garbage-time
    production still scores in fantasy. The efficiency metrics are reported
    twice -- overall and `_clean` (garbage time removed) -- since a receiver who
    piles up yards in blowouts should look different under evaluation than he
    does on a stat sheet. `garbage_time_plays` shows the exposure behind that gap.

    `snap_share` requires snap counts, which do not exist in play-by-play. Pass
    the `nflreadpy.snap_counts` table (already keyed to gsis_id via the players
    crosswalk) to populate it; omit it and the column comes back null.

    `player_name` prefers the full display name from `players`
    (`nflreadpy.load_players()`), falling back to play-by-play's own name field,
    which is abbreviated to an initial and surname ("T.McBride"). That is
    readable enough to identify a row but collides between players who share a
    surname and first initial, so the full name is worth the join.
    """
    sp = _scrimmage(plays)

    # A player can be both a target and a ball carrier in the same week, so
    # build one long "involvement" frame and aggregate once.
    receiving = sp.filter(pl.col("receiver_player_id").is_not_null()).select(
        pl.col("season"), pl.col("week"), pl.col("posteam").alias("team"),
        pl.col("receiver_player_id").alias("player_id"),
        pl.col("receiver_player_name").alias("name_pbp"),
        pl.col("epa"), pl.col("success_strict"), pl.col("garbage_time"),
        pl.col("yards_gained"), pl.col("air_yards").fill_null(0).alias("air_yards"),
        pl.col("touchdown").fill_null(0).alias("touchdown"),
        pl.col("yardline_100"),
        pl.lit(1).alias("target"), pl.lit(0).alias("carry"),
        pl.col("complete_pass").fill_null(0).alias("reception"),
    )
    rushing = sp.filter(pl.col("rusher_player_id").is_not_null()).select(
        pl.col("season"), pl.col("week"), pl.col("posteam").alias("team"),
        pl.col("rusher_player_id").alias("player_id"),
        pl.col("rusher_player_name").alias("name_pbp"),
        pl.col("epa"), pl.col("success_strict"), pl.col("garbage_time"),
        pl.col("yards_gained"), pl.lit(0.0).alias("air_yards"),
        pl.col("touchdown").fill_null(0).alias("touchdown"),
        pl.col("yardline_100"),
        pl.lit(0).alias("target"), pl.lit(1).alias("carry"),
        pl.lit(0).alias("reception"),
    )
    long = pl.concat([receiving, rushing], how="vertical_relaxed")

    clean = ~pl.col("garbage_time").fill_null(False)

    per_player = long.group_by(["season", "week", "team", "player_id"]).agg(
        pl.col("name_pbp").drop_nulls().first().alias("name_pbp"),
        pl.len().alias("plays"),
        pl.col("target").sum().alias("targets"),
        pl.col("carry").sum().alias("carries"),
        pl.col("reception").sum().alias("receptions"),
        pl.col("air_yards").sum().alias("air_yards"),
        pl.col("yards_gained").sum().alias("yards"),
        pl.col("touchdown").sum().alias("touchdowns"),
        pl.col("epa").mean().alias("epa_per_play"),
        pl.col("success_strict").mean().alias("success_rate"),
        pl.col("epa").filter(clean).mean().alias("epa_per_play_clean"),
        pl.col("success_strict").filter(clean).mean().alias("success_rate_clean"),
        (~clean).sum().alias("garbage_time_plays"),
    )

    # Team denominators for the share metrics.
    team_totals = sp.group_by(["season", "week", pl.col("posteam").alias("team")]).agg(
        pl.col("pass_attempt").fill_null(0).sum().alias("team_targets"),
        pl.col("air_yards").fill_null(0).sum().alias("team_air_yards"),
        pl.len().alias("team_plays"),
    )

    out = per_player.join(team_totals, on=["season", "week", "team"], how="left")

    target_share = pl.when(pl.col("team_targets") > 0).then(
        pl.col("targets") / pl.col("team_targets")
    ).otherwise(None)
    air_share = pl.when(pl.col("team_air_yards") > 0).then(
        pl.col("air_yards") / pl.col("team_air_yards")
    ).otherwise(None)

    out = out.with_columns(
        target_share.alias("target_share"),
        air_share.alias("air_yards_share"),
    ).with_columns(
        # WOPR, the standard weighting of volume vs. downfield role.
        (1.5 * pl.col("target_share").fill_null(0)
         + 0.7 * pl.col("air_yards_share").fill_null(0)).alias("wopr")
    )

    out = _attach_player_name(out, players)

    if snaps is not None and snaps.height > 0:
        out = _attach_snap_share(out, snaps)
    else:
        out = out.with_columns(pl.lit(None, dtype=pl.Float64).alias("snap_share"))

    cols = out.columns
    ordered = ["season", "week", "team", "player_id", "player_name"]
    return out.select(ordered + [c for c in cols if c not in ordered]).sort(
        ["season", "week", "team", "player_id"]
    )


def _attach_player_name(df: pl.DataFrame, players: pl.DataFrame | None) -> pl.DataFrame:
    """Resolve `player_name`, preferring the full display name over the
    abbreviated one play-by-play carries."""
    full = None
    if players is not None and players.height > 0:
        name_col = next(
            (c for c in ("display_name", "full_name", "player_name") if c in players.columns),
            None,
        )
        if name_col and "gsis_id" in players.columns:
            full = (
                players.select(
                    pl.col("gsis_id").alias("player_id"),
                    pl.col(name_col).alias("_full_name"),
                )
                .filter(pl.col("player_id").is_not_null())
                .unique(subset=["player_id"])
            )

    if full is not None:
        df = df.join(full, on="player_id", how="left").with_columns(
            pl.coalesce([pl.col("_full_name"), pl.col("name_pbp")]).alias("player_name")
        ).drop("_full_name")
    else:
        df = df.with_columns(pl.col("name_pbp").alias("player_name"))

    return df.drop("name_pbp")


def _attach_snap_share(df: pl.DataFrame, snaps: pl.DataFrame) -> pl.DataFrame:
    """Join offensive snap share. Expects a frame carrying season, week, and a
    gsis-keyed player id -- i.e. snap counts already run through the players
    crosswalk, since snap counts natively key on pfr_player_id."""
    id_col = next(
        (c for c in ("gsis_id", "player_id", "pfr_player_id") if c in snaps.columns), None
    )
    pct_col = next((c for c in ("offense_pct", "snap_pct") if c in snaps.columns), None)
    if id_col is None or pct_col is None:
        return df.with_columns(pl.lit(None, dtype=pl.Float64).alias("snap_share"))

    slim = (
        snaps.select(
            pl.col("season").cast(pl.Int64),
            pl.col("week").cast(pl.Int64),
            pl.col(id_col).alias("player_id"),
            pl.col(pct_col).cast(pl.Float64).alias("snap_share"),
        )
        .filter(pl.col("player_id").is_not_null())
        .unique(subset=["season", "week", "player_id"])
    )
    return df.join(slim, on=["season", "week", "player_id"], how="left")


# ---------------------------------------------------------------------------
# team_unit_weekly
# ---------------------------------------------------------------------------

def team_unit_weekly(plays: pl.DataFrame) -> pl.DataFrame:
    """One row per team / season / week / side of ball.

    Offense rows describe what a team did; defense rows describe what it
    allowed, which falls out of grouping the same plays by `defteam` instead of
    `posteam`. This is the table `nfl-matchup-notes` should query.

    Rates are computed over non-garbage-time plays -- for matchup evaluation,
    what a defense allows once a game is decided is noise.
    """
    sp = _scrimmage(plays).filter(~pl.col("garbage_time").fill_null(False))

    frames = []
    for side, team_col, opp_col in (
        ("offense", "posteam", "defteam"),
        ("defense", "defteam", "posteam"),
    ):
        explosive = (
            ((pl.col("play_type") == "pass") & (pl.col("yards_gained") >= EXPLOSIVE_PASS_YARDS))
            | ((pl.col("play_type") == "run") & (pl.col("yards_gained") >= EXPLOSIVE_RUSH_YARDS))
        )
        in_rz = pl.col("yardline_100") <= RED_ZONE_YARDLINE

        agg = (
            sp.filter(pl.col(team_col).is_not_null())
            .group_by([
                pl.col("season"), pl.col("week"),
                pl.col(team_col).alias("team"), pl.col(opp_col).alias("opponent"),
            ])
            .agg(
                pl.len().alias("plays"),
                pl.col("epa").mean().alias("epa_per_play"),
                pl.col("success_strict").mean().alias("success_rate"),
                explosive.mean().alias("explosive_rate"),
                pl.col("true_pressure").mean().alias("pressure_rate"),
                pl.col("true_pressure").drop_nulls().len().alias("dropbacks"),
                in_rz.sum().alias("red_zone_plays"),
                pl.col("touchdown").filter(in_rz).fill_null(0).mean().alias("red_zone_td_rate"),
                pl.col("true_pressure_method").drop_nulls().first().alias("pressure_method"),
            )
            .with_columns(pl.lit(side).alias("side"))
        )
        frames.append(agg)

    out = pl.concat(frames, how="vertical_relaxed")

    # Suppress rates built on too little evidence rather than publishing noise.
    thin = pl.col("plays") < config.MIN_PLAYS_FOR_RATE
    out = out.with_columns(
        [
            pl.when(thin).then(None).otherwise(pl.col(c)).alias(c)
            for c in ("epa_per_play", "success_rate", "explosive_rate")
        ]
    )
    return out.select(
        "season", "week", "team", "opponent", "side", "plays", "dropbacks",
        "epa_per_play", "success_rate", "explosive_rate", "pressure_rate",
        "pressure_method", "red_zone_plays", "red_zone_td_rate",
    ).sort(["season", "week", "team", "side"])


# ---------------------------------------------------------------------------
# team_matchup_deltas -- a VIEW, never materialized
# ---------------------------------------------------------------------------

MATCHUP_DELTAS_SQL = """
-- Each team-week expressed as a z-score against that season's league
-- distribution for the same side of the ball. Built as a view so the
-- definition can be retuned without re-running a backfill.
--
-- This is the simple, league-relative version. Opponent adjustment
-- (strength-of-schedule weighting) is the intended next iteration and can be
-- layered in here without touching the tables underneath.
WITH base AS (
  SELECT * FROM `{project}.{gold}.{team_unit}`
),
league AS (
  SELECT
    season, side,
    AVG(epa_per_play)   AS lg_epa,   STDDEV(epa_per_play)   AS sd_epa,
    AVG(success_rate)   AS lg_succ,  STDDEV(success_rate)   AS sd_succ,
    AVG(explosive_rate) AS lg_expl,  STDDEV(explosive_rate) AS sd_expl,
    AVG(pressure_rate)  AS lg_press, STDDEV(pressure_rate)  AS sd_press
  FROM base
  GROUP BY season, side
)
SELECT
  b.season, b.week, b.team, b.opponent, b.side, b.plays,
  b.epa_per_play, b.success_rate, b.explosive_rate, b.pressure_rate,
  b.pressure_method,
  SAFE_DIVIDE(b.epa_per_play   - l.lg_epa,   l.sd_epa)   AS epa_z,
  SAFE_DIVIDE(b.success_rate   - l.lg_succ,  l.sd_succ)  AS success_z,
  SAFE_DIVIDE(b.explosive_rate - l.lg_expl,  l.sd_expl)  AS explosive_z,
  SAFE_DIVIDE(b.pressure_rate  - l.lg_press, l.sd_press) AS pressure_z
FROM base b
JOIN league l USING (season, side)
"""


def matchup_deltas_sql(project_id: str | None = None) -> str:
    return MATCHUP_DELTAS_SQL.format(
        project=project_id or config.PROJECT_ID,
        gold=config.GOLD_DATASET,
        team_unit=config.GOLD_TEAM_UNIT_WEEKLY,
    )
