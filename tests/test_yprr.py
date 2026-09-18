"""Tests for the YPRR routes logic.

`nfl_data.yprr` loads its own data, so these patch the nflreadpy entry points
with fixtures. No network, no GCP.
"""

import polars as pl
import pytest

from nfl_data import yprr


@pytest.fixture
def patched(monkeypatch):
    """Two teams, a handful of dropbacks, one traded receiver."""
    players = pl.DataFrame({
        "gsis_id": ["wr1", "wr2", "te1", "ol1", "qb1"],
        "display_name": ["Wide One", "Wide Two", "Tight One", "Line One", "Quarter One"],
        "position": ["WR", "WR", "TE", "T", "QB"],
        "pfr_id": ["p1", "p2", "p3", "p4", "p5"],
    })

    # Regular season: 3 dropbacks for BUF (plays 1-3), 2 for MIA (plays 4-5).
    # Postseason: 2 more BUF dropbacks in a separate game (plays 6-7). Those
    # exist so that anything summing across season_type shows up as a wrong
    # number rather than passing quietly.
    pbp = pl.DataFrame({
        "season": [2025] * 7,
        "season_type": ["REG"] * 5 + ["POST"] * 2,
        "game_id": ["g1"] * 5 + ["g2"] * 2,
        "play_id": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        "week": [1] * 5 + [19] * 2,
        "posteam": ["BUF", "BUF", "BUF", "MIA", "MIA", "BUF", "BUF"],
        "pass_attempt": [1, 1, 0, 1, 1, 1, 1],
        "sack": [0, 0, 1, 0, 0, 0, 0],
    })

    # wr1 on the field for all 3 BUF regular season dropbacks, te1 for 2,
    # ol1/qb1 for all. wr1 also plays both postseason dropbacks.
    participation = pl.DataFrame({
        "nflverse_game_id": ["g1"] * 5 + ["g2"] * 2,
        "play_id": [1, 2, 3, 4, 5, 6, 7],
        "offense_players": [
            "wr1;te1;ol1;qb1",
            "wr1;te1;ol1;qb1",
            "wr1;ol1;qb1",
            "wr2;ol1;qb1",
            "wr2;ol1;qb1",
            "wr1;te1;ol1;qb1",
            "wr1;te1;ol1;qb1",
        ],
    })

    monkeypatch.setattr(yprr.nfl, "load_players", lambda *a, **k: players)
    monkeypatch.setattr(yprr.nfl, "load_pbp", lambda *a, **k: pbp)
    monkeypatch.setattr(yprr.nfl, "load_participation", lambda *a, **k: participation)
    return {"players": players, "pbp": pbp, "participation": participation}


def test_counts_dropbacks_the_player_was_on_field_for(patched):
    out = yprr.count_routes_on_field([2025])
    got = dict(zip(out["gsis_id"].to_list(), out["routes_est"].to_list()))
    assert got["wr1"] == 3.0   # on for all three BUF regular season dropbacks
    assert got["te1"] == 2.0
    assert got["wr2"] == 2.0


def test_linemen_and_quarterbacks_are_excluded(patched):
    """offense_players is all eleven; only skill positions run routes."""
    out = yprr.count_routes_on_field([2025])
    assert "ol1" not in out["gsis_id"].to_list()
    assert "qb1" not in out["gsis_id"].to_list()


def test_exact_rows_are_marked_as_such(patched):
    out = yprr.count_routes_on_field([2025])
    assert set(out["routes_method"].unique().to_list()) == {yprr.ROUTES_EXACT}


def test_seasons_before_participation_get_nothing_from_the_exact_path(patched):
    assert yprr.count_routes_on_field([2014, 2015]).height == 0


def test_routes_for_falls_back_below_2016(monkeypatch, patched):
    """Pre-2016 has no participation, so those seasons must come through the
    estimate rather than silently disappearing."""
    est = pl.DataFrame({
        "season": [2015], "season_type": ["REG"], "gsis_id": ["wr1"],
        "player": ["Wide One"], "position": ["WR"], "team": ["BUF"],
        "routes_est": [100.0], "games": [16],
        "routes_method": [yprr.ROUTES_ESTIMATED],
    }).select(yprr.ROUTES_COLUMNS)
    monkeypatch.setattr(yprr, "estimate_routes_run", lambda seasons, season_type: est)

    out = yprr.routes_for([2015, 2025])
    methods = dict(zip(out["season"].to_list(), out["routes_method"].to_list()))
    assert methods[2015] == yprr.ROUTES_ESTIMATED
    assert methods[2025] == yprr.ROUTES_EXACT


def test_traded_player_production_is_split_by_team(monkeypatch, patched):
    """Regression. Routes are counted per team, so production must be too --
    joining on (season, gsis_id) alone put a full season of yards on every team
    row and inflated a traded player's YPRR on all of them."""
    weekly = pl.DataFrame({
        "season": [2025, 2025],
        "season_type": ["REG", "REG"],
        "player_id": ["wr1", "wr1"],
        "team": ["BUF", "MIA"],
        "targets": [10, 5],
        "receiving_yards": [300, 100],
    })
    monkeypatch.setattr(yprr.nfl, "load_player_stats", lambda *a, **k: weekly)

    prod = yprr.load_receiving_production([2025])
    by_team = dict(zip(prod["team"].to_list(), prod["receiving_yards"].to_list()))
    assert by_team == {"BUF": 300, "MIA": 100}
    # the season total must not appear against either team
    assert 400 not in prod["receiving_yards"].to_list()


# --- season_type -----------------------------------------------------------
#
# Regression tests for pooling. The published table summed regular season and
# postseason into one row, which put up to 21 games and two incomparable
# samples behind a single YPRR.


def test_routes_default_to_regular_season_only(patched):
    """wr1 ran 3 regular season and 2 postseason routes. The default must be 3."""
    out = yprr.count_routes_on_field([2025])
    got = dict(zip(out["gsis_id"].to_list(), out["routes_est"].to_list()))
    assert got["wr1"] == 3.0
    assert set(out["season_type"].unique().to_list()) == {"REG"}


def test_postseason_routes_are_available_but_separate(patched):
    out = yprr.count_routes_on_field([2025], season_type="POST")
    got = dict(zip(out["gsis_id"].to_list(), out["routes_est"].to_list()))
    assert got["wr1"] == 2.0
    assert "wr2" not in got          # MIA played no postseason dropbacks
    assert set(out["season_type"].unique().to_list()) == {"POST"}


def test_games_are_counted_within_one_season_type(patched):
    """The symptom that surfaced this: player-seasons with more than 17 games."""
    reg = yprr.count_routes_on_field([2025])
    post = yprr.count_routes_on_field([2025], season_type="POST")
    assert reg.filter(pl.col("gsis_id") == "wr1")["games"].item() == 1
    assert post.filter(pl.col("gsis_id") == "wr1")["games"].item() == 1


def test_team_dropbacks_exclude_the_other_season_type(patched):
    reg = yprr.load_team_dropbacks([2025])
    assert reg.filter(pl.col("team") == "BUF")["team_dropbacks"].sum() == 3
    post = yprr.load_team_dropbacks([2025], season_type="POST")
    assert post.filter(pl.col("team") == "BUF")["team_dropbacks"].sum() == 2


def test_production_is_split_by_season_type(monkeypatch, patched):
    """Yards are counted within one season_type because routes are. A playoff
    run's yards over a regular season route count is a numerator and a
    denominator from different games."""
    weekly = pl.DataFrame({
        "season": [2025, 2025],
        "season_type": ["REG", "POST"],
        "player_id": ["wr1", "wr1"],
        "team": ["BUF", "BUF"],
        "targets": [10, 4],
        "receiving_yards": [300, 90],
    })
    monkeypatch.setattr(yprr.nfl, "load_player_stats", lambda *a, **k: weekly)

    assert yprr.load_receiving_production([2025])["receiving_yards"].to_list() == [300]
    assert yprr.load_receiving_production(
        [2025], season_type="POST")["receiving_yards"].to_list() == [90]


def test_snap_count_estimate_treats_every_playoff_round_as_post(monkeypatch, patched):
    """snap_counts labels the postseason by round -- WC, DIV, CON, SB -- while
    every other source just says POST. Matching on equality would silently
    return nothing for the postseason estimate."""
    snaps = pl.DataFrame({
        "season": [2025] * 3,
        "week": [1, 19, 20],
        "game_id": ["g1", "g2", "g3"],
        "team": ["BUF"] * 3,
        "position": ["WR"] * 3,
        "player": ["Wide One"] * 3,
        "pfr_player_id": ["p1"] * 3,
        "game_type": ["REG", "WC", "DIV"],
        "offense_pct": [1.0, 1.0, 1.0],
    })
    monkeypatch.setattr(yprr.nfl, "load_snap_counts", lambda *a, **k: snaps)

    # pbp only has a week-19 postseason game, so DIV drops out on the join --
    # what matters is that WC was not filtered away before it got there.
    post = yprr.estimate_routes_run([2025], season_type="POST")
    assert post["routes_est"].to_list() == [2.0]
    assert post["season_type"].to_list() == ["POST"]


def test_build_yprr_table_carries_season_type(monkeypatch, patched):
    weekly = pl.DataFrame({
        "season": [2025],
        "season_type": ["REG"],
        "player_id": ["wr1"],
        "team": ["BUF"],
        "targets": [2],
        "receiving_yards": [30],
    })
    monkeypatch.setattr(yprr.nfl, "load_player_stats", lambda *a, **k: weekly)

    out = yprr.build_yprr_table([2025], min_routes=1)
    assert out["season_type"].to_list() == ["REG"]
    assert out["routes_est"].to_list() == [3.0]
    assert out["yprr_est"].to_list() == [10.0]


def test_both_routes_paths_emit_the_same_columns_in_the_same_order(monkeypatch, patched):
    """polars concatenates vertically by position. If the exact and estimated
    paths ever drift apart, routes_for would stack mismatched columns rather
    than raise -- ROUTES_COLUMNS is what stops that, so assert it holds."""
    snaps = pl.DataFrame({
        "season": [2025], "week": [1], "game_id": ["g1"], "team": ["BUF"],
        "position": ["WR"], "player": ["Wide One"], "pfr_player_id": ["p1"],
        "game_type": ["REG"], "offense_pct": [1.0],
    })
    monkeypatch.setattr(yprr.nfl, "load_snap_counts", lambda *a, **k: snaps)

    exact = yprr.count_routes_on_field([2025])
    estimated = yprr.estimate_routes_run([2025])
    assert exact.columns == yprr.ROUTES_COLUMNS
    assert estimated.columns == yprr.ROUTES_COLUMNS


def test_a_combined_season_type_is_rejected_rather_than_pooled(patched):
    """There is deliberately no 'both' mode. Asking for one has to fail loudly
    instead of falling through to the summed row this change removes."""
    for bad in ("ALL", "BOTH", "", "reg"):
        with pytest.raises(ValueError, match="season_type must be one of"):
            yprr.build_yprr_table([2025], season_type=bad)
