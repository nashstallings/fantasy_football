# WR volume vs efficiency

Top-12 wide receivers per season by half-PPR points, 2021–2025, plotted as
points per game (x) against YPRR (y). Five seasons, 60 player-seasons, one
panel per season on shared axes.

| File | |
|---|---|
| `query.sql` | Pulls the 60 rows from `yprr_proxy`, regular season only. |
| `data.py` | Those rows, so the chart renders offline. Current as of 2026-09-18. |
| `build_chart.py` | Renders `wr_chart.html` from `data.py`. Self-contained, no deps. |
| `archive/single_season_2025.py` | First iteration: 2025 only, full PPR, one panel. Superseded. |

```
python build_chart.py            # writes wr_chart.html next to the script
python build_chart.py out.html   # or wherever you want it
```

## Refreshing

Two steps, and the second is the one people skip:

1. Run `query.sql`, replace `ROWS` in `data.py`.
2. **Recompute `FIT` in `build_chart.py`** — per-season least-squares slope,
   intercept and Pearson *r*, fitted to those exact rows. New points under old
   fit lines render a chart that looks correct and is not.

Then check the axis constants still bracket the data (`X_MIN/X_MAX`,
`Y_MIN/Y_MAX`) and re-run. The script prints a count of labels it couldn't
place; it should be 0. If it isn't, a point has drifted toward an edge and the
range needs widening — that's what the current `X_MAX = 22.5` is for.

## What changed on 2026-09-18

The rows were rebuilt on the corrected `yprr_proxy`, which counts actual
on-field dropbacks instead of estimating routes from snap share. Both the
points and the story moved.

Removing measurement error from the denominator raised the correlation in four
of five seasons:

| season | r before | r after |
|---|---|---|
| 2021 | 0.856 | **0.894** |
| 2022 | 0.472 | **0.570** |
| 2023 | 0.732 | 0.715 |
| 2024 | 0.395 | **0.546** |
| 2025 | 0.802 | **0.816** |

That direction is expected — noise in a denominator attenuates correlation, so
a more accurate denominator should recover some of it — but the size of the
move mattered. The old headline said some years the top scorers *aren't* the
efficient ones, resting on 2022 and 2024 at 0.47 and 0.40. At 0.57 and 0.55
that reading no longer holds: every season now sits between 0.55 and 0.89, so
the relationship never actually breaks, it only loosens. The headline and dek
were rewritten to say that instead.

## Design notes

Five seasons on a single scatter would need five categorical hues; the
palette caps all-pairs forms at three, so this facets into five single-hue
panels rather than overloading one.

Labels are placed programmatically — 12 labels on a 12-point scatter collide
badly by hand. Each tries candidate offsets in preference order and takes the
first clearing every dot, every already-placed label, the axis tick labels,
and the plot bounds. Only two points per panel are labelled: the season's top
scorer and its efficiency leader, which collapse to one when they're the same
player.
