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

### Running weekly (automatic)

`.github/workflows/nfl_data_weekly.yml` refreshes every table each Tuesday at
13:00 UTC, so the current season lands without anyone opening a notebook. It
authenticates through Workload Identity Federation — the same secrets the
play-by-play jobs use — and skips with a notice if they aren't set.

Run it by hand from the Actions tab (**NFL Data Weekly Refresh** →
Run workflow) to force a refresh or to load specific seasons. Locally:

```bash
python jobs/run_nfl_data.py --dry-run     # builds everything, writes nothing
python jobs/run_nfl_data.py               # needs GCP credentials
```

**The season is not configured anywhere.** `config.current_season()` reads it
from nflreadpy at run time, so the rollover needs no commit. Override with
`NFL_DATA_SEASON` for a backfill.

### Running in Colab

Still works, and still the place for a one-off or for iterating. The weekly job
just means nobody has to remember.

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
| `yprr_proxy` | derived (nflreadpy) | YPRR/target rate. **Always filter on `season_type`** — REG and POST are separate rows. Check `routes_method`: `participation_on_field` counts actual on-field dropbacks (2016+), `snap_share_estimate` is the older proxy. See `yprr.py` for caveats before trusting the numbers |

All of the above are filtered to `QB`/`RB`/`WR`/`TE` and replaced wholesale on each run.

The four weekly tables carry a **four-season window** (`config.raw_seasons()`),
not just the current one. They're written with `if_exists="replace"`, so a
single-season window would mean the first run after a rollover swaps a finished
season for a Week 1 stub and the old one is gone. `yprr_proxy` is independent of
that window — it always spans 2013 through the current season.

### This pipeline is the only writer of `nflreadpy.*`

Every table above is written `if_exists="replace"`. Two processes replacing the
same table is not a merge — whichever ran last wins, silently, and the other's
data is simply gone until it runs again.

`contract_dynasty_draft/nfl_data_refresh.py` used to write these same five
tables on a daily cron, with the seasons hardcoded (`range(2022, 2026)`, and a
bare `2025` for the rest). It was removed when this job took over. If you find
another writer, retire it rather than trying to make the two agree.

Known **consumers**, which read and must not write:

| Repo | Reads |
|---|---|
| `sleeper_dynasty_overview` | `player_stats`, `snap_counts`, `players` via its `scripts/refresh_*.py`, which write JSON the static app loads. Uses `SEASONS_BACK = 4` — the reason `RAW_SEASON_HISTORY` is 4. |
| `contract_dynasty_draft` | `players`, `player_stats`, `snap_counts`, `ff_opportunity` via its `bq-proxy`. |

`player_auction_values` (`dynasty_tycoon` dataset, Sleeper + nflreadpy, age-adjusted/superflex-aware dynasty auction values priced to a $3000/12-team budget) is **not** run by default — call `nfl_data.run_auction_values()` explicitly (see notebook step 6) if you want it.

### Known gotchas

- Sleeper's `gsis_id` field is sparse. `nfl_data.id_matching.resolve_gsis_ids` backfills it by name+position match against nflreadpy's player table, then falls back to a stable synthetic id (`config.SYNTHETIC_GSIS_OVERRIDES` for known cases, else `SL_<sleeper_id>`) for anyone still unmatched — mostly very recent rookies.
- League scoring, age curve, VOR demand, QB superflex premium, and auction budget are all in `src/nfl_data/config.py` — tune there rather than hand-editing pipeline code.
- `yprr_proxy` has one row per `(season, season_type, gsis_id, team)`. A query without a `season_type` predicate returns a player's regular season *and* postseason rows, so `SELECT ... WHERE season = 2025` alone will double-count anyone whose team made the playoffs. Summing the two back together is not a workaround — a four-game playoff sample and a seventeen-game one are different statistics, and pooling them is the bug this grain exists to prevent.
- **The season in progress uses a different routes method, and switches mid-season.** nflverse doesn't publish participation until after the fact, so the current season's `yprr_proxy` rows fall back to `snap_share_estimate` while every completed season from 2016 on is `participation_on_field`. The estimate runs ~7% off the count at the median and far worse on blocking tight ends, so a current-season row is not comparable to a prior-season one without checking `routes_method` — and those rows will change when participation lands. Expect small samples too: at Week 3 the 50-route floor leaves ~60 qualifying players on two games each.
- **The weekly job rewrites every table in full**, rather than appending the new week — same reasoning as the play-by-play job. Cron skips firings, and a full rewrite means the next run repairs the gap instead of leaving a permanent hole. It also picks up the stat corrections that land days after a game.
- **An empty source is refused, not written.** Every write is `if_exists="replace"`, so a frame with zero rows would delete the table rather than leave it alone. `write_tables` raises `EmptyWriteRefused` instead, and the weekly job treats that as a clean skip — an upstream outage costs a run, not a table.

## Analysis

One-off charts and studies built on these tables live in `analysis/`, each in
its own directory with the query that produced it.

- **`analysis/wr_volume_vs_efficiency/`** — top-12 WRs per season, 2021–2025, points per game against YPRR. Rebuilt on the corrected `yprr_proxy`; the directory README covers how to refresh it.

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
| `pbp_silver.plays_enriched` | play | Same grain + `garbage_time`, `situation_bucket`, `true_pressure`, `success_strict`, and participation fields (`personnel_grouping`, `offense_formation`, `defenders_in_box`). |
| `pbp_gold.player_weekly_efficiency` | player × week | `player_name`, target/air-yards share, WOPR, EPA/play, success rate, snap share. |
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

The same service account backs the `nfl_data` weekly job, so its grant list
covers `pbp_bronze`, `pbp_silver`, `pbp_gold` **and** `nflreadpy`. If you set
WIF up before that fourth dataset was added, the `nfl_data` job fails with
`Access Denied ... bigquery.tables.get denied on table nflreadpy.players` —
re-run `./scripts/setup_wif.sh`, which is idempotent and adds only what's
missing. `dynasty_tycoon` is deliberately *not* granted: nothing in Actions
writes it.

First-time setup is one command, easiest from
[Google Cloud Shell](https://console.cloud.google.com/) (gcloud and bq are
preinstalled and already authenticated):

```bash
gcloud config set project ff-python-api
./scripts/setup_wif.sh
```

See [docs/workload-identity-federation.md](docs/workload-identity-federation.md)
for what it creates and the two things that are easy to get wrong. Until the
secrets exist the weekly job skips with a notice instead of failing.

### Gotchas

- **`true_pressure` mixes a real measurement with a proxy — check the method.**
  nflverse participation carries a charted `was_pressure` per play (2016–2025,
  effectively complete from 2023), and it is used directly wherever present. The
  proxy (`qb_hit`/`sack`, plus FTN's `is_qb_out_of_pocket`/`is_throw_away` from
  2022) only fills plays participation doesn't cover — most importantly the
  **current season, which nflverse does not publish until after the fact**.
  The definitions disagree: on 2025 the charted rate is 29.7% against the
  proxy's 32.6%, and on 2024 the pbp-only proxy gives 14.6% against 30.7% with
  FTN. Every row carries `true_pressure_method` (`participation` /
  `pbp_plus_ftn` / `pbp_only`); filter on it before comparing pressure across
  seasons, or you will read a definitional step change as a real one.
- **Personnel is null for the current season.** `offense_personnel`,
  `personnel_grouping`, `offense_formation`, `defenders_in_box` and
  `number_of_pass_rushers` all come from participation, so they cover 2016–2025
  (fully from 2023) and are null until nflverse publishes the season in
  progress. `personnel_grouping` is the conventional two digits — backs, then
  tight ends, with a fullback counting as a back — so `11` is 1 RB/1 TE/3 WR.
  On 2025 that resolves to 58.8% `11`, 24.1% `12`, 7.0% `21`.
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
