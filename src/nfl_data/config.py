"""Project-wide configuration for the nfl_data pipeline."""

import os

import nflreadpy as nfl

PROJECT_ID = "ff-python-api"

# BigQuery datasets. The nflreadpy pulls and the derived yprr_proxy table
# share a dataset (all replaced wholesale each run); the weekly-tuned dynasty
# valuation model is kept separate.
NFLREADPY_DATASET_ID = "nflreadpy"
VALUATION_DATASET_ID = "dynasty_tycoon"

FANTASY_POSITIONS = ["QB", "RB", "WR", "TE"]

# snap_counts, the YPRR proxy's input, is published from 2013. nflverse has no
# 2012 file despite the range this used to claim.
YPRR_FIRST_SEASON = 2013

# How many seasons the raw nflreadpy tables carry, counting the current one.
# See raw_seasons().
#
# Four, because this pipeline is the sole writer of these tables and the
# downstream consumer needs four. sleeper_dynasty_overview's refresh scripts
# use SEASONS_BACK = 4 -- `WHERE season > MAX(season) - 4` -- so a narrower
# window here silently starves the player cards in that dashboard rather than
# failing anything. If that consumer's window changes, this has to move with it.
RAW_SEASON_HISTORY = 4

SEASON_ENV_VAR = "NFL_DATA_SEASON"


def current_season() -> int:
    """The season to load, resolved when it is asked for rather than at import.

    This was a hardcoded literal, which is how the pipeline came to spend the
    opening weeks of 2026 faithfully republishing 2025. Reading it from
    nflreadpy means the rollover needs no commit.

    nflreadpy rolls this over on the Thursday after Labor Day, so through the
    offseason it still names the season that just finished -- which is the
    right answer for a table of results, and the reason raw_seasons() keeps a
    window rather than trusting any single value.

    Set NFL_DATA_SEASON to override, for a backfill or a test.
    """
    override = os.environ.get(SEASON_ENV_VAR)
    if override:
        return int(override)
    return nfl.get_current_season()


def raw_seasons() -> list[int]:
    """Seasons published to the raw nflreadpy tables.

    A window, not a single season, because these tables are written with
    if_exists="replace". Loading only the current season would mean the first
    run after a rollover replaces a finished season with whatever exists of
    the new one -- in Week 1 that is a near-empty table, and the season it
    overwrote is gone.
    """
    current = current_season()
    return list(range(current - RAW_SEASON_HISTORY + 1, current + 1))


def yprr_seasons() -> list[int]:
    """Every season the YPRR proxy covers, through the current one."""
    return list(range(YPRR_FIRST_SEASON, current_season() + 1))


YPRR_MIN_ROUTES = 50

# Season types published to yprr_proxy, as separate rows rather than one summed
# row. Set to ("REG",) to drop the postseason block entirely; do not try to
# merge them, a row spanning both is meaningless.
YPRR_SEASON_TYPES = ("REG", "POST")

# Season the Sleeper dynasty auction valuation targets
PROJECTION_SEASON = 2026

# League scoring: 0.5 PPR for RB/WR, full PPR for TE (TE premium), superflex
PASS_TD_PTS = 4
PPR_BY_POSITION = {"QB": 0.0, "RB": 0.5, "WR": 0.5, "TE": 1.0}

# Age-adjustment curve applied to projected points: list of (age_cutoff, multiplier),
# first cutoff the player's age is <= wins.
AGE_CURVE = {
    "QB": [(23, 1.04), (26, 1.03), (28, 1.00), (30, 0.96), (32, 0.90), (99, 0.82)],
    "RB": [(23, 1.12), (26, 1.05), (28, 0.96), (30, 0.86), (32, 0.74), (99, 0.62)],
    "WR": [(23, 1.12), (26, 1.07), (28, 1.00), (30, 0.92), (32, 0.84), (99, 0.74)],
    "TE": [(23, 1.10), (26, 1.06), (28, 1.00), (30, 0.95), (32, 0.90), (99, 0.84)],
}

# Replacement-level rank per position for VOR, sized for a 12-team superflex league
POSITIONAL_DEMAND = {"QB": 24, "RB": 34, "WR": 48, "TE": 14}

# Superflex scarcity premium applied to QB value-over-replacement before ranking/pricing
QB_PREMIUM = 1.50

# Auction pricing: the top N players' values sum to exactly TOTAL_BUDGET; everyone else is $1
AUCTION_TOP_N = 300
AUCTION_TOTAL_BUDGET = 3000

# Players nflreadpy doesn't carry a gsis_id for yet (rookies, very recent additions) --
# name -> stable synthetic id. Anyone else unmatched falls back to "SL_<sleeper_id>".
SYNTHETIC_GSIS_OVERRIDES = {
    "Travis Hunter": "HUNTER_2026",
}
