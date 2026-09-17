"""Unit tests for the silver enrichment functions.

No GCP auth, no network -- everything runs against small fixture frames, which
is the point of keeping the enrichment logic pure.
"""

import polars as pl
import pytest

from nfl_pbp import silver


def make_plays(**overrides) -> pl.DataFrame:
    """A minimal pbp-shaped frame. Pass column overrides as equal-length lists."""
    base = {
        "game_id": ["g1"], "play_id": [1.0],
        "qtr": [1], "score_differential": [0], "wp": [0.5],
        "down": [1], "ydstogo": [10], "yards_gained": [5],
        "qb_hit": [0], "sack": [0], "qb_dropback": [1],
        "play_type": ["pass"], "aborted_play": [0],
    }
    n = max((len(v) for v in overrides.values()), default=1)
    for k, v in base.items():
        base[k] = v * n if len(v) == 1 else v
    base.update(overrides)
    return pl.DataFrame(base)


# --------------------------------------------------------------------------
# garbage_time
# --------------------------------------------------------------------------

def test_garbage_time_requires_both_margin_and_decided_game():
    df = make_plays(
        qtr=[4, 4, 4, 1],
        score_differential=[20, 20, 10, 40],
        wp=[0.02, 0.35, 0.02, 0.01],
    )
    got = silver.add_garbage_time(df)["garbage_time"].to_list()
    # big margin + decided -> yes; big margin but still competitive -> no;
    # small margin -> no; 1st quarter is never garbage time
    assert got == [True, False, False, False]


def test_garbage_time_uses_margin_when_wp_missing():
    df = make_plays(qtr=[4], score_differential=[24], wp=[None])
    assert silver.add_garbage_time(df)["garbage_time"].to_list() == [True]


def test_garbage_time_symmetric_for_leader_and_trailer():
    """wp is possession-team win probability, so a blowout must register whether
    the team with the ball is ahead or behind."""
    df = make_plays(qtr=[4, 4], score_differential=[-25, 25], wp=[0.01, 0.99])
    assert silver.add_garbage_time(df)["garbage_time"].to_list() == [True, True]


def test_overtime_is_never_garbage_time():
    df = make_plays(qtr=[5], score_differential=[30], wp=[0.01])
    assert silver.add_garbage_time(df)["garbage_time"].to_list() == [False]


# --------------------------------------------------------------------------
# situation_bucket
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "down,togo,expected",
    [
        (None, 0, "no_down"),
        (1, 10, "first_and_10"),
        (1, 15, "first_other"),
        (1, 5, "first_other"),
        (2, 2, "second_short"),
        (2, 6, "second_medium"),
        (2, 12, "second_long"),
        (3, 1, "third_short"),
        (3, 5, "third_medium"),
        (3, 9, "third_long"),
        (4, 1, "fourth_down"),
        (4, 15, "fourth_down"),
    ],
)
def test_situation_bucket(down, togo, expected):
    df = make_plays(down=[down], ydstogo=[togo])
    assert silver.add_situation_bucket(df)["situation_bucket"].to_list() == [expected]


def test_first_and_10_is_not_lumped_into_long():
    """1st-and-10 is the most common situation in football; if it landed in a
    generic 'long' bucket that bucket would just mean 'normal football'."""
    df = make_plays(down=[1, 1], ydstogo=[10, 12])
    got = silver.add_situation_bucket(df)["situation_bucket"].to_list()
    assert got[0] != got[1]


# --------------------------------------------------------------------------
# true_pressure
# --------------------------------------------------------------------------

def test_true_pressure_from_hit_or_sack():
    df = make_plays(qb_hit=[1, 0, 0], sack=[0, 1, 0], qb_dropback=[1, 1, 1])
    assert silver.add_true_pressure(df)["true_pressure"].to_list() == [True, True, False]


def test_true_pressure_null_on_non_dropbacks():
    """Null, not False -- a run play must not dilute the pressure-rate mean."""
    df = make_plays(qb_hit=[0], sack=[0], qb_dropback=[0])
    out = silver.add_true_pressure(df)
    assert out["true_pressure"].to_list() == [None]
    assert out["true_pressure_method"].to_list() == [None]


def test_true_pressure_method_marks_pbp_only_without_ftn():
    df = make_plays()
    assert silver.add_true_pressure(df)["true_pressure_method"].to_list() == ["pbp_only"]


def test_ftn_signals_widen_pressure_and_mark_the_method():
    df = make_plays(game_id=["g1", "g1"], play_id=[1.0, 2.0],
                    qb_hit=[0, 0], sack=[0, 0], qb_dropback=[1, 1])
    ftn = pl.DataFrame({
        "nflverse_game_id": ["g1", "g1"],
        "nflverse_play_id": [1, 2],
        "is_qb_out_of_pocket": [True, False],
        "is_throw_away": [False, False],
    })
    out = silver.add_true_pressure(df, ftn=ftn)
    assert out["true_pressure"].to_list() == [True, False]
    assert out["true_pressure_method"].to_list() == ["pbp_plus_ftn", "pbp_plus_ftn"]


def test_unmatched_ftn_rows_fall_back_to_pbp_only():
    """A play with no FTN row keeps the narrower definition and says so, rather
    than silently looking like a charted play with no pressure."""
    df = make_plays(game_id=["g1"], play_id=[99.0], qb_hit=[1], qb_dropback=[1])
    ftn = pl.DataFrame({
        "nflverse_game_id": ["g1"], "nflverse_play_id": [1],
        "is_qb_out_of_pocket": [True], "is_throw_away": [False],
    })
    out = silver.add_true_pressure(df, ftn=ftn)
    assert out["true_pressure_method"].to_list() == ["pbp_only"]
    assert out["true_pressure"].to_list() == [True]  # from qb_hit


def test_ftn_join_does_not_change_grain_or_leak_columns():
    df = make_plays(game_id=["g1", "g1"], play_id=[1.0, 2.0], qb_dropback=[1, 1])
    ftn = pl.DataFrame({
        "nflverse_game_id": ["g1", "g1"], "nflverse_play_id": [1, 2],
        "is_qb_out_of_pocket": [False, False], "is_throw_away": [False, False],
    })
    out = silver.add_true_pressure(df, ftn=ftn)
    assert out.height == df.height
    assert "is_qb_out_of_pocket" not in out.columns
    assert "_join_play_id" not in out.columns


# --------------------------------------------------------------------------
# success_strict
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "down,togo,gained,expected",
    [
        (1, 10, 4, True),    # 40% of the sticks on 1st
        (1, 10, 3, False),
        (2, 10, 6, True),    # 60% on 2nd
        (2, 10, 5, False),
        (3, 5, 5, True),     # conversion required on 3rd
        (3, 5, 4, False),
        (4, 2, 2, True),
        (4, 2, 1, False),
    ],
)
def test_success_strict_thresholds(down, togo, gained, expected):
    df = make_plays(down=[down], ydstogo=[togo], yards_gained=[gained])
    assert silver.add_success_strict(df)["success_strict"].to_list() == [expected]


def test_success_strict_null_without_a_down():
    df = make_plays(down=[None], ydstogo=[0], yards_gained=[40])
    assert silver.add_success_strict(df)["success_strict"].to_list() == [None]


def test_success_strict_is_stricter_than_epa_success():
    """A 5-yard gain on 2nd-and-10 is positive EPA but not 'on schedule'."""
    df = make_plays(down=[2], ydstogo=[10], yards_gained=[5])
    assert silver.add_success_strict(df)["success_strict"].to_list() == [False]


# --------------------------------------------------------------------------
# enrich
# --------------------------------------------------------------------------

def test_enrich_preserves_grain_and_adds_every_column():
    df = make_plays(game_id=["g1", "g1", "g2"], play_id=[1.0, 2.0, 1.0])
    out = silver.enrich(df)
    assert out.height == df.height
    for col in silver.ENRICHED_COLUMNS:
        assert col in out.columns
    assert out.select(["game_id", "play_id"]).unique().height == out.height
