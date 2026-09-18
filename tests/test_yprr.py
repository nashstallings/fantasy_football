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

    # 3 dropbacks for BUF (plays 1-3), 2 for MIA (plays 4-5)
    pbp = pl.DataFrame({
        "season": [2025] * 5,
        "game_id": ["g1"] * 5,
        "play_id": [1.0, 2.0, 3.0, 4.0, 5.0],
        "week": [1] * 5,
        "posteam": ["BUF", "BUF", "BUF", "MIA", "MIA"],
        "pass_attempt": [1, 1, 0, 1, 1],
        "sack": [0, 0, 1, 0, 0],
    })

    # wr1 on the field for all 3 BUF dropbacks, te1 for 2, ol1/qb1 for all
    participation = pl.DataFrame({
        "nflverse_game_id": ["g1"] * 5,
        "play_id": [1, 2, 3, 4, 5],
        "offense_players": [
            "wr1;te1;ol1;qb1",
            "wr1;te1;ol1;qb1",
            "wr1;ol1;qb1",
            "wr2;ol1;qb1",
            "wr2;ol1;qb1",
        ],
    })

    monkeypatch.setattr(yprr.nfl, "load_players", lambda *a, **k: players)
    monkeypatch.setattr(yprr.nfl, "load_pbp", lambda *a, **k: pbp)
    monkeypatch.setattr(yprr.nfl, "load_participation", lambda *a, **k: participation)
    return {"players": players, "pbp": pbp, "participation": participation}


def test_counts_dropbacks_the_player_was_on_field_for(patched):
    out = yprr.count_routes_on_field([2025])
    got = dict(zip(out["gsis_id"].to_list(), out["routes_est"].to_list()))
    assert got["wr1"] == 3.0   # on for all three BUF dropbacks
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
        "season": [2015], "gsis_id": ["wr1"], "player": ["Wide One"],
        "position": ["WR"], "team": ["BUF"], "routes_est": [100.0], "games": [16],
        "routes_method": [yprr.ROUTES_ESTIMATED],
    })
    monkeypatch.setattr(yprr, "estimate_routes_run", lambda seasons: est)

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
