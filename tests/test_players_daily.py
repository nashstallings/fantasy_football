"""Tests for the daily players-only refresh.

The point of the split is that the daily run touches `players` and nothing
else. A daily job that accidentally rebuilt the stats tables would be merely
wasteful; one that wrote them from a narrower window would be destructive,
because every write is if_exists="replace".
"""

import pandas as pd
import pytest

import run_nfl_data
from nfl_data import pipeline
from nfl_data.bigquery_io import EmptyWriteRefused


@pytest.fixture
def writes(monkeypatch):
    """Record every table handed to write_tables, and stub out the fetches so
    any accidental call to a stats loader fails loudly."""
    written = []
    monkeypatch.setattr(pipeline, "write_tables",
                        lambda tables, *a, **k: written.extend(tables))
    monkeypatch.setattr(pipeline, "fetch_players",
                        lambda: pd.DataFrame({"gsis_id": ["a", "b"]}))

    def boom(*a, **k):
        raise AssertionError("the daily players run must not load stats tables")

    for name in ("fetch_player_stats", "fetch_snap_counts",
                 "fetch_nextgen_stats", "fetch_ff_opportunity",
                 "fetch_schedules"):
        monkeypatch.setattr(pipeline, name, boom)
    return written


def test_run_players_writes_only_players(writes):
    out = pipeline.run_players()
    assert writes == ["players"]
    assert len(out) == 2


def test_run_players_dry_run_writes_nothing(writes):
    pipeline.run_players(write_to_bq=False)
    assert writes == []


def test_players_only_job_touches_nothing_else(writes):
    assert run_nfl_data.run_players_only() == 0
    assert writes == ["players"]


def test_empty_players_is_a_clean_skip(monkeypatch):
    """Same posture as the weekly job: an empty upstream file must not fail
    the run every day until someone looks, and must not write."""
    def refuse(*a, **k):
        raise EmptyWriteRefused("nflreadpy.players: refusing to replace a table with 0 rows")
    monkeypatch.setattr(pipeline, "run_players", refuse)
    assert run_nfl_data.run_players_only() == 0


@pytest.mark.parametrize("extra", [["--seasons", "2025"], ["--skip-yprr"]])
def test_players_only_rejects_flags_it_would_ignore(monkeypatch, extra):
    """players has no season window. Accepting --seasons and silently ignoring
    it would let someone believe they had scoped a run they had not."""
    monkeypatch.setattr("sys.argv", ["run_nfl_data.py", "--players-only", *extra])
    with pytest.raises(SystemExit):
        run_nfl_data.main()
