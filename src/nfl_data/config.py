"""Project-wide configuration for the nfl_data pipeline."""

PROJECT_ID = "ff-python-api"

# BigQuery datasets. Kept separate because they differ in nature: raw
# nflreadpy pulls (replaced wholesale each run) vs. a derived analytical
# proxy vs. a weekly-tuned dynasty valuation model.
NFLREADPY_DATASET_ID = "nflreadpy"
YPRR_DATASET_ID = "dynasty"
VALUATION_DATASET_ID = "dynasty_tycoon"

FANTASY_POSITIONS = ["QB", "RB", "WR", "TE"]

# Season for the core nflreadpy loads (player_stats, snap_counts, nextgen_stats, ff_opportunity)
CURRENT_SEASON = 2025

# Seasons for the YPRR proxy table (snap_counts, its input, starts in 2012)
YPRR_SEASONS = list(range(2012, CURRENT_SEASON + 1))
YPRR_MIN_ROUTES = 50

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
