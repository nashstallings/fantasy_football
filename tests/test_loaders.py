"""Tests for the raw nflreadpy loaders.

Only the part that has logic in it: the positional rank. The rest is a typed
passthrough and testing it would just assert that nflreadpy was called.
"""

import polars as pl

from nfl_data import loaders


def test_weekly_rank_is_scoped_to_one_season(monkeypatch):
    """Regression. These loads span more than one season now; grouping the
    rank on week alone pools Week 1 of every season into one ranking, so a
    'weekly positional rank' silently stops being one.

    Two seasons, same week, same position. Each season's leader must rank 1.
    """
    raw = pl.DataFrame({
        "season": [2025, 2025, 2026, 2026],
        "week": [1, 1, 1, 1],
        "position": ["WR"] * 4,
        "player_id": ["a", "b", "c", "d"],
        "fantasy_points_ppr": [30.0, 10.0, 25.0, 5.0],
    })
    monkeypatch.setattr(loaders.nfl, "load_player_stats", lambda *a, **k: raw)

    out = loaders.fetch_player_stats([2025, 2026])
    ranks = dict(zip(out["player_id"], out["weekly_positional_rank"]))
    assert ranks == {"a": 1.0, "b": 2.0, "c": 1.0, "d": 2.0}
    assert max(ranks.values()) == 2       # not 4, which is what pooling gives


def test_rank_still_separates_by_week_and_position(monkeypatch):
    raw = pl.DataFrame({
        "season": [2026] * 4,
        "week": [1, 1, 2, 2],
        "position": ["WR", "TE", "WR", "TE"],
        "player_id": ["w1", "t1", "w2", "t2"],
        "fantasy_points_ppr": [20.0, 5.0, 18.0, 4.0],
    })
    monkeypatch.setattr(loaders.nfl, "load_player_stats", lambda *a, **k: raw)

    out = loaders.fetch_player_stats(2026)
    assert set(out["weekly_positional_rank"]) == {1.0}   # each is alone in its group


def test_non_fantasy_positions_are_dropped_before_ranking(monkeypatch):
    """A kicker in the frame would not change a WR's rank, but it would sit in
    the published table, which is filtered to fantasy positions everywhere."""
    raw = pl.DataFrame({
        "season": [2026] * 3,
        "week": [1] * 3,
        "position": ["WR", "K", "WR"],
        "player_id": ["a", "k", "b"],
        "fantasy_points_ppr": [20.0, 99.0, 10.0],
    })
    monkeypatch.setattr(loaders.nfl, "load_player_stats", lambda *a, **k: raw)

    out = loaders.fetch_player_stats(2026)
    assert list(out["player_id"]) == ["a", "b"]
    assert list(out["weekly_positional_rank"]) == [1.0, 2.0]


# --- schedules --------------------------------------------------------------


def test_schedules_also_requests_the_next_season(monkeypatch):
    """The next schedule is published in May, months before current_season()
    rolls over. Asking for it unconditionally is what makes offseason byes
    point at the season about to be drafted for."""
    asked = {}

    def fake(seasons):
        asked["seasons"] = seasons
        return pl.DataFrame({"season": seasons, "game_type": ["REG"] * len(seasons)})

    monkeypatch.setattr(loaders.nfl, "load_schedules", fake)
    loaders.fetch_schedules([2023, 2024, 2025, 2026])
    assert asked["seasons"] == [2023, 2024, 2025, 2026, 2027]


def test_schedules_accepts_a_single_season(monkeypatch):
    asked = {}
    monkeypatch.setattr(loaders.nfl, "load_schedules",
                        lambda seasons: asked.setdefault("s", seasons) and pl.DataFrame({"season": seasons}))
    loaders.fetch_schedules(2026)
    assert asked["s"] == [2026, 2027]


def test_schedules_are_not_position_filtered(monkeypatch):
    """Games, not players -- there is no position column to filter on, and
    dropping rows here would invent byes downstream."""
    games = pl.DataFrame({
        "season": [2026, 2026], "game_type": ["REG", "REG"], "week": [1, 2],
        "home_team": ["BUF", "KC"], "away_team": ["MIA", "DEN"],
    })
    monkeypatch.setattr(loaders.nfl, "load_schedules", lambda seasons: games)
    assert len(loaders.fetch_schedules(2026)) == 2
