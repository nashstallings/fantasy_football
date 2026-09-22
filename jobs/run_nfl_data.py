#!/usr/bin/env python3
"""Weekly refresh of the nfl_data tables in the `nflreadpy` BigQuery dataset.

Replaces what the Colab notebook did by hand. The notebook still works and is
still the place to run a one-off or to iterate -- this just means nobody has to
remember to open it every Tuesday.

Every table is rewritten in full on each run, not appended to. That is
deliberate, for the same reasons as the play-by-play job:

  - GitHub cron is best-effort and can skip a firing. A full rewrite means the
    next successful run repairs the gap; an incremental one leaves a hole that
    only a manual fix would catch.
  - Stat corrections land days after a game. A rewrite picks them up.
  - There is nothing to gain from being clever: the whole build is under a
    minute.

    python jobs/run_nfl_data.py                      # current window
    python jobs/run_nfl_data.py --seasons 2024 2025  # explicit
    python jobs/run_nfl_data.py --skip-yprr          # raw tables only
"""

from __future__ import annotations

import argparse
import sys

import nflreadpy as nfl

from nfl_data import config, pipeline
from nfl_data.bigquery_io import EmptyWriteRefused


def run(
    seasons: list[int] | None = None,
    skip_yprr: bool = False,
    write_to_bq: bool = True,
) -> int:
    seasons = seasons or config.raw_seasons()
    print(f"nfl_data refresh | season {config.current_season()} week {nfl.get_current_week()}")
    print(f"  raw tables: {seasons}")

    try:
        tables = pipeline.run_nflreadpy_tables(seasons=seasons, write_to_bq=write_to_bq)
    except EmptyWriteRefused as exc:
        # Not a crash worth alerting on every week: a source with no rows yet
        # is normal in the hours around a season's first games. Nothing was
        # written, so the existing tables are intact and the next run fixes it.
        print(f"\n  {exc}")
        print("  Nothing written. This resolves itself once the source publishes.")
        return 0

    for name, df in tables.items():
        print(f"  {name}: {len(df):,} rows")

    if skip_yprr:
        print("\nSkipping yprr_proxy (--skip-yprr).")
        return 0

    yprr_seasons = config.yprr_seasons()
    print(f"\n  yprr_proxy: {yprr_seasons[0]}-{yprr_seasons[-1]}, "
          f"season types {config.YPRR_SEASON_TYPES}")
    yprr = pipeline.run_yprr(write_to_bq=write_to_bq)
    print(f"  yprr_proxy: {len(yprr):,} rows")

    print("\nRefresh complete.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seasons", type=int, nargs="+", default=None,
                   help="seasons for the raw tables; defaults to config.raw_seasons()")
    p.add_argument("--skip-yprr", action="store_true",
                   help="refresh the raw tables only")
    p.add_argument("--dry-run", action="store_true",
                   help="build everything but write nothing (no GCP auth needed)")
    a = p.parse_args()
    return run(a.seasons, a.skip_yprr, write_to_bq=not a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
