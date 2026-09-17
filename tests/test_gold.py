"""Unit tests for the gold rollups.

Fixture-driven like the silver tests -- no BigQuery, no network.
"""

import polars as pl

from nfl_pbp import gold


def make_enriched() -> pl.DataFrame:
    """Two teams, one week, a handful of plays with known answers."""
    return pl.DataFrame({
        "season": [2024] * 6,
        "week": [1] * 6,
        "posteam": ["BUF", "BUF", "BUF", "BUF", "MIA", "MIA"],
        "defteam": ["MIA", "MIA", "MIA", "MIA", "BUF", "BUF"],
        "play_type": ["pass", "pass", "run", "pass", "run", "pass"],
        "aborted_play": [0] * 6,
        "epa": [1.0, -0.5, 0.5, 2.0, 0.0, 1.0],
        "success_strict": [True, False, True, True, False, True],
        "garbage_time": [False, False, False, True, False, False],
        "yards_gained": [25, 0, 3, 40, 2, 8],
        "air_yards": [20.0, 10.0, None, 35.0, None, 5.0],
        "touchdown": [1, 0, 0, 1, 0, 0],
        "yardline_100": [25, 40, 15, 45, 10, 30],
        "pass_attempt": [1, 1, 0, 1, 0, 1],
        "complete_pass": [1, 0, 0, 1, 0, 1],
        "true_pressure": [False, True, None, False, None, True],
        "true_pressure_method": ["pbp_only", "pbp_only", None, "pbp_only", None, "pbp_only"],
        "receiver_player_id": ["r1", "r1", None, "r2", None, "r3"],
        "rusher_player_id": [None, None, "b1", None, "b2", None],
    })


# --------------------------------------------------------------------------
# team_unit_weekly
# --------------------------------------------------------------------------

def test_offense_and_defense_rows_mirror_each_other():
    """A defense allowed exactly what the opposing offense produced, so the two
    rows for one game must carry identical metrics. This is the property the
    whole matchup table leans on."""
    out = gold.team_unit_weekly(make_enriched())
    buf_off = out.filter((pl.col("team") == "BUF") & (pl.col("side") == "offense"))
    mia_def = out.filter((pl.col("team") == "MIA") & (pl.col("side") == "defense"))

    assert buf_off.height == 1 and mia_def.height == 1
    for col in ("plays", "epa_per_play", "success_rate", "explosive_rate"):
        assert buf_off[col][0] == mia_def[col][0], col


def test_garbage_time_excluded_from_team_rates(monkeypatch):
    """BUF has 4 plays, one of them garbage time, so rates use 3.

    The fixture is smaller than MIN_PLAYS_FOR_RATE, so drop the threshold here
    to make the arithmetic observable; suppression itself is covered below.
    """
    monkeypatch.setattr(gold.config, "MIN_PLAYS_FOR_RATE", 1)
    out = gold.team_unit_weekly(make_enriched())
    buf = out.filter((pl.col("team") == "BUF") & (pl.col("side") == "offense"))
    assert buf["plays"][0] == 3
    # epa of the three non-garbage plays: 1.0, -0.5, 0.5 -> mean 1/3
    assert abs(buf["epa_per_play"][0] - (1.0 / 3)) < 1e-9


def test_thin_samples_have_rates_suppressed():
    """Publishing an EPA/play built on three snaps invites false confidence, so
    rates below the play threshold come back null rather than noisy."""
    out = gold.team_unit_weekly(make_enriched())
    buf = out.filter((pl.col("team") == "BUF") & (pl.col("side") == "offense"))
    assert buf["plays"][0] == 3  # the count is still reported
    assert buf["epa_per_play"][0] is None
    assert buf["success_rate"][0] is None
    assert buf["explosive_rate"][0] is None


def test_team_unit_grain_is_team_week_side():
    out = gold.team_unit_weekly(make_enriched())
    assert out.select(["season", "week", "team", "side"]).unique().height == out.height
    assert set(out["side"].unique().to_list()) == {"offense", "defense"}


def test_pressure_rate_uses_dropbacks_only():
    """Run plays carry null true_pressure and must not dilute the rate."""
    out = gold.team_unit_weekly(make_enriched())
    buf = out.filter((pl.col("team") == "BUF") & (pl.col("side") == "offense"))
    # non-garbage BUF dropbacks: False, True -> 0.5 over 2, not over 3 plays
    assert buf["dropbacks"][0] == 2
    assert abs(buf["pressure_rate"][0] - 0.5) < 1e-9


# --------------------------------------------------------------------------
# player_weekly_efficiency
# --------------------------------------------------------------------------

def test_player_shares_and_wopr():
    out = gold.player_weekly_efficiency(make_enriched())
    r1 = out.filter(pl.col("player_id") == "r1")
    assert r1.height == 1
    # BUF threw 3 pass attempts across all scrimmage plays (garbage included)
    assert r1["targets"][0] == 2
    assert abs(r1["target_share"][0] - (2 / 3)) < 1e-9
    expected_wopr = 1.5 * r1["target_share"][0] + 0.7 * r1["air_yards_share"][0]
    assert abs(r1["wopr"][0] - expected_wopr) < 1e-9


def test_volume_keeps_garbage_time_but_clean_efficiency_drops_it():
    """Garbage-time production still scores in fantasy, so it stays in the
    volume columns; the `_clean` efficiency columns exclude it."""
    out = gold.player_weekly_efficiency(make_enriched())
    r2 = out.filter(pl.col("player_id") == "r2")  # r2's only play is garbage time
    assert r2["targets"][0] == 1
    assert r2["garbage_time_plays"][0] == 1
    assert r2["epa_per_play"][0] == 2.0
    assert r2["epa_per_play_clean"][0] is None


def test_player_appearing_as_both_receiver_and_rusher_gets_one_row():
    df = make_enriched().with_columns(
        pl.Series("rusher_player_id", [None, None, "r1", None, "b2", None])
    )
    out = gold.player_weekly_efficiency(df)
    r1 = out.filter((pl.col("player_id") == "r1") & (pl.col("team") == "BUF"))
    assert r1.height == 1
    assert r1["targets"][0] == 2 and r1["carries"][0] == 1


def test_snap_share_null_without_snap_counts():
    out = gold.player_weekly_efficiency(make_enriched(), snaps=None)
    assert "snap_share" in out.columns
    assert out["snap_share"].null_count() == out.height


def test_snap_share_joins_when_provided():
    snaps = pl.DataFrame({
        "season": [2024], "week": [1], "gsis_id": ["r1"], "offense_pct": [0.87],
    })
    out = gold.player_weekly_efficiency(make_enriched(), snaps=snaps)
    r1 = out.filter(pl.col("player_id") == "r1")
    assert abs(r1["snap_share"][0] - 0.87) < 1e-9
