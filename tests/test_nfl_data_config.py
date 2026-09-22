"""Tests for season resolution and the empty-write guard.

The pipeline used to carry a hardcoded season, so none of this could drift.
Now that it resolves at run time, these are the things that can.
"""

import pandas as pd
import pytest

from nfl_data import config
from nfl_data.bigquery_io import EmptyWriteRefused, write_tables


# --- season resolution -----------------------------------------------------


def test_current_season_comes_from_nflreadpy(monkeypatch):
    monkeypatch.delenv(config.SEASON_ENV_VAR, raising=False)
    monkeypatch.setattr(config.nfl, "get_current_season", lambda *a, **k: 2031)
    assert config.current_season() == 2031


def test_env_var_overrides(monkeypatch):
    monkeypatch.setattr(config.nfl, "get_current_season", lambda *a, **k: 2031)
    monkeypatch.setenv(config.SEASON_ENV_VAR, "2024")
    assert config.current_season() == 2024


def test_season_is_resolved_per_call_not_at_import(monkeypatch):
    """The regression this whole change exists for. A module-level constant
    freezes at import and the pipeline republishes a finished season until
    someone notices and edits a literal."""
    monkeypatch.delenv(config.SEASON_ENV_VAR, raising=False)
    monkeypatch.setattr(config.nfl, "get_current_season", lambda *a, **k: 2026)
    assert config.current_season() == 2026
    monkeypatch.setattr(config.nfl, "get_current_season", lambda *a, **k: 2027)
    assert config.current_season() == 2027


def test_raw_seasons_keeps_the_previous_season(monkeypatch):
    """Rollover must not drop the season that just finished. These tables are
    replaced wholesale, so a one-season window would swap a complete season
    for a Week 1 stub."""
    monkeypatch.delenv(config.SEASON_ENV_VAR, raising=False)
    monkeypatch.setattr(config.nfl, "get_current_season", lambda *a, **k: 2026)
    assert config.raw_seasons() == [2025, 2026]


def test_yprr_seasons_runs_from_first_to_current(monkeypatch):
    monkeypatch.delenv(config.SEASON_ENV_VAR, raising=False)
    monkeypatch.setattr(config.nfl, "get_current_season", lambda *a, **k: 2026)
    s = config.yprr_seasons()
    assert s[0] == config.YPRR_FIRST_SEASON == 2013
    assert s[-1] == 2026
    assert 2012 not in s      # nflverse publishes no 2012 snap counts


# --- the empty-write guard -------------------------------------------------


def test_empty_frame_is_refused(monkeypatch):
    """if_exists='replace' means writing 0 rows deletes the table. Refuse,
    so an upstream outage costs a skipped run rather than the table."""
    called = []
    monkeypatch.setattr("nfl_data.bigquery_io.pandas_gbq.to_gbq",
                        lambda *a, **k: called.append(a))

    with pytest.raises(EmptyWriteRefused, match="refusing to replace"):
        write_tables({"player_stats": pd.DataFrame()}, "proj", "ds")
    assert called == []       # nothing reached BigQuery


def test_empty_frame_blocks_before_any_table_is_written(monkeypatch):
    """The guard has to run per table before its own write, so a bad frame
    cannot land after a good one has already replaced its table."""
    written = []
    monkeypatch.setattr("nfl_data.bigquery_io.pandas_gbq.to_gbq",
                        lambda df, dest, **k: written.append(dest))

    with pytest.raises(EmptyWriteRefused):
        write_tables({"empty": pd.DataFrame()}, "proj", "ds")
    assert written == []


def test_allow_empty_overrides(monkeypatch):
    written = []
    monkeypatch.setattr("nfl_data.bigquery_io.pandas_gbq.to_gbq",
                        lambda df, dest, **k: written.append(dest))

    write_tables({"t": pd.DataFrame()}, "proj", "ds", allow_empty=True)
    assert written == ["ds.t"]


def test_populated_frames_write_normally(monkeypatch):
    written = []
    monkeypatch.setattr("nfl_data.bigquery_io.pandas_gbq.to_gbq",
                        lambda df, dest, **k: written.append((dest, len(df))))

    write_tables({"a": pd.DataFrame({"x": [1, 2]}),
                  "b": pd.DataFrame({"x": [3]})}, "proj", "ds")
    assert written == [("ds.a", 2), ("ds.b", 1)]
