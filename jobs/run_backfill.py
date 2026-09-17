#!/usr/bin/env python3
"""Full historical load: bronze -> silver -> gold for a range of seasons.

Triggered by hand from the Actions UI (workflow_dispatch) with a season range.
Safe to re-run: every write is a MERGE on the natural key, so a repeat of the
same seasons leaves row counts unchanged.

    python jobs/run_backfill.py --start-season 2016 --end-season 2025
"""

from __future__ import annotations

import argparse
import sys

import nflreadpy as nfl

from nfl_pbp import bq_io, bronze, config, gold, silver


def _load_roster():
    """Player table for the gsis_id -> full name lookup. Non-fatal: a failure
    here costs the full names, not the run -- player_name falls back to
    play-by-play's abbreviated form."""
    try:
        return nfl.load_players()
    except Exception as exc:  # noqa: BLE001
        print(f"  players lookup unavailable ({exc}); "
              f"player_name falls back to the abbreviated pbp name")
        return None


def run(start_season: int, end_season: int, project_id: str | None = None) -> int:
    bq = bq_io.client(project_id)
    seasons = list(range(start_season, end_season + 1))
    print(f"Backfilling seasons {seasons[0]}-{seasons[-1]} into {bq.project}")

    for season in seasons:
        print(f"\n[{season}]")
        plays = bronze.build(season)
        if plays.height == 0:
            print("  no play-by-play; skipping")
            continue
        print(f"  loaded {plays.height:,} plays")

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
    print("\nBackfill complete.")
    return 0


def rebuild_gold_for(bq, enriched, season: int) -> None:
    """Recompute both gold tables for one season and merge them in."""
    # nflreadpy caches within the process, so this is one fetch across seasons.
    roster = _load_roster()

    player_weekly = gold.player_weekly_efficiency(enriched, players=roster)
    bq_io.merge_table(
        bq, player_weekly, config.GOLD_DATASET, config.GOLD_PLAYER_WEEKLY,
        key=["season", "week", "team", "player_id"],
    )

    teams = gold.team_unit_weekly(enriched)
    bq_io.merge_table(
        bq, teams, config.GOLD_DATASET, config.GOLD_TEAM_UNIT_WEEKLY,
        key=["season", "week", "team", "side"],
    )


def publish_matchup_view(bq) -> None:
    bq_io.replace_view(
        bq, config.GOLD_DATASET, config.GOLD_MATCHUP_DELTAS,
        gold.matchup_deltas_sql(bq.project),
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start-season", type=int, required=True)
    p.add_argument("--end-season", type=int, required=True)
    p.add_argument("--project", default=None, help="defaults to config.PROJECT_ID")
    a = p.parse_args()

    if a.end_season < a.start_season:
        p.error("--end-season must be >= --start-season")
    return run(a.start_season, a.end_season, a.project)


if __name__ == "__main__":
    sys.exit(main())
