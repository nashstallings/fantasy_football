# WR volume vs efficiency

Top-12 wide receivers per season by half-PPR points, 2021–2025, plotted as
points per game (x) against YPRR (y). Five seasons, 60 player-seasons, one
panel per season on shared axes.

| File | |
|---|---|
| `query.sql` | Pulls the 60 rows from BigQuery. **Current** — reads the corrected `yprr_proxy`. |
| `data.py` | The rows as a snapshot, so the chart renders offline. **Stale** — see below. |
| `build_chart.py` | Renders `wr_chart.html` from `data.py`. Self-contained, no deps. |
| `archive/single_season_2025.py` | First iteration: 2025 only, full PPR, one panel. Superseded. |

```
python build_chart.py            # writes wr_chart.html next to the script
python build_chart.py out.html   # or wherever you want it
```

## Read this before using the numbers

`data.py` is a snapshot taken before two corrections landed, and its `yprr`
column is wrong by a small but real amount.

It **is** regular-season only. That was never the problem here — the query
that produced it reimplemented the routes denominator in SQL precisely to
route around `yprr_proxy` pooling regular season and postseason together.

What's stale is the denominator itself. Those routes are snap-share
**estimates** (`offense_snap_pct × team_dropbacks`), not counts. The estimate
runs ~7% off the exact on-field count at the median, and further on some
players:

| 2025 | routes | YPRR |
|---|---|---|
| Nacua, as snapshotted | 409 | 4.193 |
| Nacua, counted | 465 | 3.688 |

Every `yprr` in `data.py` is off by something in that range. Relative ordering
within a season mostly survives; absolute values don't.

## Refreshing it

`yprr_proxy` now counts actual on-field dropbacks from nflverse participation
and keeps `season_type` as a column, so `query.sql` reads it directly instead
of rebuilding the estimate. Two steps:

1. Re-run the `nfl_data` pipeline (the Colab notebook in `notebooks/`) so
   BigQuery carries the corrected table. Until then `query.sql` fails on the
   missing `season_type` column — which is the failure mode you want, rather
   than silently pooled numbers.
2. Run `query.sql`, replace `ROWS` in `data.py`, and **recompute the `FIT`
   dict in `build_chart.py`** — those are per-season least-squares slopes,
   intercepts and Pearson *r* over the old rows. Stale fit lines drawn over
   fresh points is the one failure here that looks fine.

## Design notes

Five seasons on a single scatter would need five categorical hues; the
palette caps all-pairs forms at three, so this facets into five single-hue
panels rather than overloading one.

Labels are placed programmatically — 12 labels on a 12-point scatter collide
badly by hand. Each tries candidate offsets in preference order and takes the
first clearing every dot, every already-placed label, the axis tick labels,
and the plot bounds. Both scripts print a count of labels they couldn't place
cleanly; it should be 0.
