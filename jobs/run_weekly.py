#!/usr/bin/env python3
"""Incremental weekly update.

Refreshes the *entire current season* rather than trying to identify "the new
week". That is deliberate:

  - Every write is a MERGE, so re-processing a season already loaded is a no-op
    on row count -- there is nothing to gain from being clever.
  - GitHub Actions cron is best-effort and can skip a firing entirely. Rebuilding
    the season means the next successful run silently repairs any gap, instead of
    leaving a permanent hole that only a manual backfill would catch.
  - Stat corrections land days after a game. Re-merging picks them up; an
    append-only "just the new week" job never would.

A current season with no games yet (offseason, or the gap before Week 1) exits
cleanly with status 0 -- a scheduled job that alerts for five months a year gets
muted, and then it isn't there when it matters.

    python jobs/run_weekly.py [--season 2026]
"""

from __future__ import annotations

import argparse
import sys

import nflreadpy as nfl

from nfl_pbp import bq_io, bronze, config, gold, silver
from run_backfill import publish_matchup_view, rebuild_gold_for


def run(season: int | None = None, project_id: str | None = None) -> int:
    season = season or nfl.get_current_season()
    print(f"Weekly update for season {season}")

    try:
        plays = bronze.build(season)
    except Exception as exc:  # noqa: BLE001
        # nflverse publishes the season's pbp file only once the season starts;
        # a missing file in the offseason is expected, not a failure.
        print(f"  no play-by-play available for {season} ({exc}) -- nothing to do")
        return 0

    if plays.height == 0:
        print(f"  season {season} has no plays yet -- nothing to do")
        return 0

    weeks = sorted(plays["week"].drop_nulls().unique().to_list())
    print(f"  loaded {plays.height:,} plays across weeks {weeks[0]}-{weeks[-1]}")

    bq = bq_io.client(project_id)

    bq_io.merge_table(
        bq, plays, config.BRONZE_DATASET, config.BRONZE_PLAYS,
        key=config.PLAY_KEY,
        partition_field=config.PARTITION_FIELD,
        cluster_fields=config.CLUSTER_FIELDS,
    )

    enriched = silver.enrich(plays, ftn=bronze.load_ftn(season))
    bq_io.merge_table(
        bq, enriched, config.SILVER_DATASET, config.SILVER_PLAYS,
        key=config.PLAY_KEY,
        partition_field=config.PARTITION_FIELD,
        cluster_fields=config.CLUSTER_FIELDS,
    )

    rebuild_gold_for(bq, enriched, season)
    publish_matchup_view(bq)

    print("\nWeekly update complete.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--season", type=int, default=None,
                   help="defaults to nflreadpy's current season")
    p.add_argument("--project", default=None, help="defaults to config.PROJECT_ID")
    a = p.parse_args()
    return run(a.season, a.project)


if __name__ == "__main__":
    sys.exit(main())
