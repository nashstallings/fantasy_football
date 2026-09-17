"""Configuration for the play-by-play enrichment pipeline.

Writes to three new datasets in the existing ff-python-api project, kept
separate from the `nflreadpy` dataset (rosters/snaps/stats), which the
nfl_data pipeline owns and this one never touches.
"""

PROJECT_ID = "ff-python-api"

BRONZE_DATASET = "pbp_bronze"
SILVER_DATASET = "pbp_silver"
GOLD_DATASET = "pbp_gold"

BRONZE_PLAYS = "plays"
SILVER_PLAYS = "plays_enriched"
GOLD_PLAYER_WEEKLY = "player_weekly_efficiency"
GOLD_TEAM_UNIT_WEEKLY = "team_unit_weekly"
GOLD_MATCHUP_DELTAS = "team_matchup_deltas"

# Natural key for every bronze/silver row. Verified unique in nflverse pbp
# (2024: 49,492 rows, 49,492 distinct pairs), which is what makes MERGE safe.
PLAY_KEY = ["game_id", "play_id"]

# BigQuery physical layout. game_date arrives from nflreadpy as a STRING and is
# cast to DATE in bronze -- BigQuery cannot partition on a STRING column.
PARTITION_FIELD = "game_date"
CLUSTER_FIELDS = ["season", "week", "posteam"]

LOAD_LOCATION = "US"

# ---------------------------------------------------------------------------
# Enrichment thresholds (silver). Kept here so they are tunable in one place
# rather than buried in the transforms.
# ---------------------------------------------------------------------------

# Garbage time: a lopsided score late enough that play-calling stops being
# representative. Quarter -> minimum absolute score margin to qualify.
GARBAGE_TIME_MARGIN_BY_QUARTER = {3: 22, 4: 17}

# Win-probability guard: even at a big margin, a play is not garbage time while
# the trailing team still has a real chance. Applied when `wp` is populated.
GARBAGE_TIME_WP_CEILING = 0.10

# "Success" by the conventional down-and-distance standard, which is stricter
# than nflverse's built-in `success` (EPA > 0).
SUCCESS_YARDS_FRACTION_BY_DOWN = {1: 0.4, 2: 0.6, 3: 1.0, 4: 1.0}

# FTN charting (pressure-adjacent signals) only exists from this season on.
FTN_FIRST_SEASON = 2022

# Minimum routes/plays before a rate is considered stable enough to publish.
MIN_PLAYS_FOR_RATE = 10
