"""Silver layer: pure enrichment functions over raw play-by-play.

Every function here takes a polars DataFrame and returns a new one. Nothing
touches BigQuery or the network, so the whole layer is unit-testable against
small fixture frames (see tests/test_silver.py).

Grain is unchanged from bronze: one row per (game_id, play_id).
"""

from __future__ import annotations

import polars as pl

from . import config

# Columns this layer adds, in output order.
ENRICHED_COLUMNS = [
    "garbage_time",
    "situation_bucket",
    "true_pressure",
    "true_pressure_method",
    "success_strict",
]


def _has(df: pl.DataFrame, column: str) -> bool:
    return column in df.columns


def add_garbage_time(df: pl.DataFrame) -> pl.DataFrame:
    """Flag plays where the result is effectively decided, so play-calling stops
    being representative of how a team actually operates.

    A play is garbage time when the score margin clears a quarter-specific
    threshold AND -- where win probability is available -- the game is already
    decided (the trailing side is at or under GARBAGE_TIME_WP_CEILING).

    The win-probability guard matters: a 17-point deficit early in the fourth
    is recoverable and shouldn't be discarded, while the same margin with two
    minutes left is noise. Margin alone cannot tell those apart.
    """
    margin = pl.col("score_differential").abs()
    qtr = pl.col("qtr")

    over_threshold = pl.lit(False)
    for quarter, cutoff in config.GARBAGE_TIME_MARGIN_BY_QUARTER.items():
        over_threshold = over_threshold | ((qtr == quarter) & (margin >= cutoff))
    # anything past regulation is never garbage time
    over_threshold = over_threshold & (qtr <= 4)

    if _has(df, "wp"):
        # min(wp, 1-wp) is "the trailing side's chance", regardless of which
        # team has possession. Null wp falls back to the margin rule alone.
        decided = (
            pl.min_horizontal(pl.col("wp"), 1 - pl.col("wp")) <= config.GARBAGE_TIME_WP_CEILING
        ).fill_null(True)
        flag = over_threshold & decided
    else:
        flag = over_threshold

    return df.with_columns(flag.fill_null(False).alias("garbage_time"))


def add_situation_bucket(df: pl.DataFrame) -> pl.DataFrame:
    """Bucket each play by down and distance.

    1st-and-10 gets its own bucket rather than being folded into a generic
    "long" bin -- it is the single most common situation in football (~45% of
    scrimmage plays), and letting it dominate an "early_long" bucket would make
    that bucket mean "normal football" instead of "behind schedule".

    Deliberately excludes field position: `yardline_100` is already a column,
    and folding red zone into this categorical would force an arbitrary
    precedence choice (is 3rd-and-9 from the 15 "third_long" or "red_zone"?).
    Keeping the two orthogonal lets gold filter on either without losing the
    other.
    """
    down, togo = pl.col("down"), pl.col("ydstogo")

    bucket = (
        pl.when(down.is_null())
        .then(pl.lit("no_down"))  # kickoffs, extra points, timeouts
        .when(down == 4)
        .then(pl.lit("fourth_down"))
        .when((down == 3) & (togo <= 3))
        .then(pl.lit("third_short"))
        .when((down == 3) & (togo <= 6))
        .then(pl.lit("third_medium"))
        .when(down == 3)
        .then(pl.lit("third_long"))
        .when((down == 2) & (togo <= 3))
        .then(pl.lit("second_short"))
        .when((down == 2) & (togo <= 7))
        .then(pl.lit("second_medium"))
        .when(down == 2)
        .then(pl.lit("second_long"))
        .when((down == 1) & (togo == 10))
        .then(pl.lit("first_and_10"))
        .otherwise(pl.lit("first_other"))  # 1st and goal, or 1st and long after a penalty
    )
    return df.with_columns(bucket.alias("situation_bucket"))


def add_true_pressure(df: pl.DataFrame, ftn: pl.DataFrame | None = None) -> pl.DataFrame:
    """Flag dropbacks where the quarterback was disrupted.

    IMPORTANT -- there is no pressure field in free nflverse data. `was_pressure`
    does not exist in play-by-play (372 columns checked) and does not exist in
    FTN charting either; it is a PFF product. So this is a proxy built from what
    is actually available:

        qb_hit OR sack                          (always)
        OR is_qb_out_of_pocket OR is_throw_away  (FTN, 2022+ only)

    `qb_hit` alone undercounts badly -- it only fires when the QB is actually
    hit, missing every play he was flushed or forced to dump off.

    Because the FTN signals only exist from 2022, the definition is era-
    dependent, and a naive backfill would show a discontinuity at 2022 that is
    purely definitional. `true_pressure_method` records which definition
    produced each row so downstream code can avoid comparing across the
    boundary (or filter to one method).

    The flag is null on non-dropbacks rather than False, so pressure rates
    computed as a mean aren't diluted by run plays.
    """
    base = (pl.col("qb_hit").fill_null(0) == 1) | (pl.col("sack").fill_null(0) == 1)

    out = df
    method = pl.lit("pbp_only")
    joined_cols: list[str] = []

    if ftn is not None and ftn.height > 0:
        ftn_cols = [c for c in ("is_qb_out_of_pocket", "is_throw_away") if c in ftn.columns]
        if ftn_cols:
            slim = ftn.select(
                pl.col("nflverse_game_id").alias("game_id"),
                pl.col("nflverse_play_id").cast(pl.Int64).alias("_join_play_id"),
                *[pl.col(c).cast(pl.Boolean, strict=False) for c in ftn_cols],
            ).unique(subset=["game_id", "_join_play_id"])

            # pbp ships play_id as Float64 while FTN uses Int64; join on a
            # normalized temporary key so this works whether or not bronze has
            # already cast it.
            out = (
                out.with_columns(pl.col("play_id").cast(pl.Int64).alias("_join_play_id"))
                .join(slim, on=["game_id", "_join_play_id"], how="left")
                .drop("_join_play_id")
            )
            joined_cols = ftn_cols

            ftn_signal = pl.lit(False)
            for c in ftn_cols:
                ftn_signal = ftn_signal | pl.col(c).fill_null(False)

            matched = pl.any_horizontal([pl.col(c).is_not_null() for c in ftn_cols])
            base = base | ftn_signal
            method = pl.when(matched).then(pl.lit("pbp_plus_ftn")).otherwise(pl.lit("pbp_only"))

    is_dropback = pl.col("qb_dropback").fill_null(0) == 1

    # Materialize before dropping the joined FTN columns -- `base` and `method`
    # are lazy expressions that still reference them.
    out = out.with_columns(
        pl.when(is_dropback).then(base).otherwise(None).alias("true_pressure"),
        pl.when(is_dropback).then(method).otherwise(None).alias("true_pressure_method"),
    )
    if joined_cols:
        out = out.drop(joined_cols)
    return out


def add_success_strict(df: pl.DataFrame) -> pl.DataFrame:
    """Down-and-distance success, stricter than nflverse's built-in `success`.

    nflverse defines `success` as EPA > 0. This uses the conventional charting
    standard instead -- 40% of the sticks on 1st down, 60% on 2nd, a conversion
    on 3rd/4th -- which is independent of the EPA model and easier to explain to
    someone reading a matchup note.

    Null on plays with no down (kickoffs, extra points) so those never enter a
    success-rate denominator.
    """
    down, togo, gained = pl.col("down"), pl.col("ydstogo"), pl.col("yards_gained")

    needed = pl.lit(None, dtype=pl.Float64)
    for d, frac in config.SUCCESS_YARDS_FRACTION_BY_DOWN.items():
        needed = pl.when(down == d).then(togo * frac).otherwise(needed)

    flag = pl.when(down.is_null() | gained.is_null()).then(None).otherwise(gained >= needed)
    return df.with_columns(flag.alias("success_strict"))


def enrich(df: pl.DataFrame, ftn: pl.DataFrame | None = None) -> pl.DataFrame:
    """Apply the full silver transform. Grain is preserved."""
    out = add_garbage_time(df)
    out = add_situation_bucket(out)
    out = add_true_pressure(out, ftn=ftn)
    out = add_success_strict(out)
    return out


def is_scrimmage_play(df: pl.DataFrame) -> pl.Series:
    """Rows that are an actual run or pass from scrimmage -- the denominator for
    most rate stats. Excludes kicks, penalties that wiped the play, and aborted
    snaps."""
    keep = pl.col("play_type").is_in(["pass", "run"])
    if _has(df, "aborted_play"):
        keep = keep & (pl.col("aborted_play").fill_null(0) == 0)
    return df.select(keep.alias("k"))["k"]
