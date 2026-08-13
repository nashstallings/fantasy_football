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

Three BigQuery datasets in `ff-python-api`:

| Table | Dataset | Source | Notes |
|---|---|---|---|
| `players` | `nflreadpy` | nflreadpy | Skill-position players + cross-platform IDs |
| `player_stats` | `nflreadpy` | nflreadpy | Weekly stats, with a within-week/position PPR rank added |
| `snap_counts` | `nflreadpy` | nflreadpy | Weekly snap share by player |
| `nextgen_stats` | `nflreadpy` | nflreadpy | Passing/receiving/rushing NGS, stacked long |
| `ff_opportunity` | `nflreadpy` | nflreadpy | Weekly opportunity/target-share model output |
| `yprr_proxy` | `dynasty` | derived (nflreadpy) | Estimated YPRR/target rate via a snap-share proxy — see `yprr.py` module docstring for methodology and caveats before trusting the numbers |
| `player_auction_values` | `dynasty_tycoon` | Sleeper + nflreadpy | Age-adjusted, superflex-aware dynasty auction values, priced to a $3000/12-team budget |

All tables are filtered to `QB`/`RB`/`WR`/`TE` and replaced wholesale on each run.

### Known gotchas

- Sleeper's `gsis_id` field is sparse. `nfl_data.id_matching.resolve_gsis_ids` backfills it by name+position match against nflreadpy's player table, then falls back to a stable synthetic id (`config.SYNTHETIC_GSIS_OVERRIDES` for known cases, else `SL_<sleeper_id>`) for anyone still unmatched — mostly very recent rookies.
- League scoring, age curve, VOR demand, QB superflex premium, and auction budget are all in `src/nfl_data/config.py` — tune there rather than hand-editing pipeline code.

## Other files

- **`index.html`** — Dynasty Tycoon auction draft model, a standalone client-side roster/contract tracker (manual entry, no BigQuery integration yet).
- **`nfl_data.py`** — an older scratch script (nfl_data_py-based fantasy scoring exploration), separate from the `nfl_data` package above.
