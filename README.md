# fantasy_football

## `nfl_data` pipeline

A BigQuery-backed pipeline for current NFL player data, feeding the Dynasty Tycoon auction draft model (`index.html`).

- **`src/nfl_data/`** — the pipeline logic (data pulls, transforms, BigQuery writes). Edit this in Claude Code.
- **`notebooks/nfl_data_runner.ipynb`** — a thin notebook that clones this repo, installs it, and calls `nfl_data.run()`. Runs in Colab so you get GCP auth for free. This notebook should rarely need edits — logic changes belong in `src/`.

### Local dev (Claude Code)

```bash
pip install -e .
```

Then edit modules under `src/nfl_data/`, test locally, commit, push.

### Running in Colab

1. Open `notebooks/nfl_data_runner.ipynb` in Colab (or `File > Open notebook > GitHub` and paste this repo's URL).
2. Run all cells. It clones the repo fresh each run, so it always uses whatever is on `main`. The repo is public, so no token is needed.

### Tables produced

`nfl_data.run()` writes everything to the `nflreadpy` dataset in `ff-python-api` by default:

| Table | Source | Notes |
|---|---|---|
| `players` | nflreadpy | Skill-position players + cross-platform IDs |
| `player_stats` | nflreadpy | Weekly stats, with a within-week/position PPR rank added |
| `snap_counts` | nflreadpy | Weekly snap share by player |
| `nextgen_stats` | nflreadpy | Passing/receiving/rushing NGS, stacked long |
| `ff_opportunity` | nflreadpy | Weekly opportunity/target-share model output |
| `yprr_proxy` | derived (nflreadpy) | Estimated YPRR/target rate via a snap-share proxy — see `yprr.py` module docstring for methodology and caveats before trusting the numbers |

All of the above are filtered to `QB`/`RB`/`WR`/`TE` and replaced wholesale on each run.

`player_auction_values` (`dynasty_tycoon` dataset, Sleeper + nflreadpy, age-adjusted/superflex-aware dynasty auction values priced to a $3000/12-team budget) is **not** run by default — call `nfl_data.run_auction_values()` explicitly (see notebook step 6) if you want it.

### Known gotchas

- Sleeper's `gsis_id` field is sparse. `nfl_data.id_matching.resolve_gsis_ids` backfills it by name+position match against nflreadpy's player table, then falls back to a stable synthetic id (`config.SYNTHETIC_GSIS_OVERRIDES` for known cases, else `SL_<sleeper_id>`) for anyone still unmatched — mostly very recent rookies.
- League scoring, age curve, VOR demand, QB superflex premium, and auction budget are all in `src/nfl_data/config.py` — tune there rather than hand-editing pipeline code.

## Other files

- **`index.html`** — Dynasty Tycoon auction draft model, a standalone client-side roster/contract tracker (manual entry, no BigQuery integration yet).
- **`nfl_data.py`** — an older scratch script (nfl_data_py-based fantasy scoring exploration), separate from the `nfl_data` package above.

---

## `nfl_pbp` pipeline (play-by-play enrichment)

Ingests NFL play-by-play via `nflreadpy`, enriches it with derived evaluation
columns, and rolls it up for Dynasty Tycoon's player tabs and the planned
`nfl-matchup-notes` tool. Runs on GitHub Actions, not Colab.

- **`src/nfl_pbp/`** — pure transforms (`bronze`, `silver`, `gold`) plus `bq_io`.
- **`jobs/`** — thin CLI entrypoints. No logic lives here.
- **`tests/`** — fixture-driven unit tests; no GCP auth, no network.
- **`.github/workflows/`** — scheduled weekly run, manual backfill, and CI.

### Layers

| Table | Grain | Notes |
|---|---|---|
| `pbp_bronze.plays` | play | Typed passthrough of `load_pbp()`. Partitioned by `game_date`, clustered by season/week/posteam. |
| `pbp_silver.plays_enriched` | play | Same grain + `garbage_time`, `situation_bucket`, `true_pressure`, `success_strict`. |
| `pbp_gold.player_weekly_efficiency` | player × week | Target/air-yards share, WOPR, EPA/play, success rate, snap share. |
| `pbp_gold.team_unit_weekly` | team × week × side | EPA/play, success, explosive and pressure rates, red zone. **`nfl-matchup-notes` queries this.** |
| `pbp_gold.team_matchup_deltas` | view | Z-scores vs. league. A view, so it retunes without a backfill. |

### Running

```bash
pip install -e ".[pbp,dev]"
pytest tests/ -q

python jobs/run_backfill.py --start-season 2016 --end-season 2025
python jobs/run_weekly.py
```

In CI both jobs authenticate through Workload Identity Federation — there is no
service-account key anywhere in this repo. Requires repo secrets
`GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`.

### Gotchas

- **`true_pressure` is a proxy, and its definition changes at 2022.** There is no
  pressure field in free nflverse data — `was_pressure` exists in neither
  play-by-play nor FTN charting; it's a PFF product. This ORs `qb_hit`/`sack`
  with FTN's `is_qb_out_of_pocket`/`is_throw_away`, which only exist from 2022.
  Measured on 2024, that is the difference between a 14.6% and a 30.7% pressure
  rate, so a backfill shows a step change at 2022 that is purely definitional.
  Every row carries `true_pressure_method` (`pbp_only` / `pbp_plus_ftn`) — filter
  on it before comparing across that boundary.
- **The weekly job rebuilds the whole current season**, not just the new week.
  GitHub cron is best-effort and skips firings; rebuilding means a missed week
  self-heals, and late stat corrections get picked up.
- **Every write is a `MERGE`**, keyed on `game_id + play_id` (verified unique:
  2024 has 49,492 plays and 49,492 distinct pairs). Re-running any job is safe.
- **Rates are suppressed below `MIN_PLAYS_FOR_RATE`** rather than published on a
  handful of snaps; the play count is still reported so you can see why.
- **Team rates exclude garbage time; player volume does not** — garbage-time
  production still scores in fantasy, so `player_weekly_efficiency` keeps it in
  the volume columns and offers `_clean` variants for evaluation.
