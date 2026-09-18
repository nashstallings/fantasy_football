-- Top-12 WRs by half-PPR points per season, 2021-2025, with YPRR.
-- 60 player-seasons: the rowset behind the small-multiples scatter.
--
-- REQUIRES the Colab re-run of the nfl_data pipeline (PRs #14 + #15). Until
-- yprr_proxy is rebuilt it has no season_type column and this fails outright,
-- which is the good failure mode -- the old shape cannot silently return
-- pooled numbers.
--
-- Replaces the hand-rolled routes estimate the previous version carried. That
-- workaround existed only because yprr_proxy pooled regular season and
-- postseason, so it reimplemented offense_snap_pct * team_dropbacks in SQL to
-- get a REG-only denominator. The table now does that correctly itself, and
-- does it better: 2016+ rows count the dropbacks a player was actually on the
-- field for (routes_method = 'participation_on_field') rather than estimating
-- from snap share. All five seasons here are on the exact method.
--
-- Expect the y-axis to move. The estimate this replaces ran ~7.4% off the
-- count at the median on 2025, so YPRR values shift and the per-season fit
-- lines in gen_chart2.py (the FIT dict) must be recomputed from the new rows.

WITH scoring AS (
  SELECT
    season,
    player_id,
    ANY_VALUE(player_display_name) AS player_name,
    ARRAY_AGG(team ORDER BY week DESC LIMIT 1)[OFFSET(0)] AS team,
    SUM(fantasy_points + 0.5 * receptions) AS half_ppr,
    COUNT(DISTINCT week) AS games,
    SUM(receiving_yards) AS rec_yards,
    SUM(targets) AS targets
  FROM `ff-python-api.nflreadpy.player_stats_weekly`
  WHERE season BETWEEN 2021 AND 2025
    AND season_type = 'REG'
    AND position = 'WR'
  GROUP BY season, player_id
),

routes AS (
  -- yprr_proxy is grained per (season, season_type, gsis_id, team), so a
  -- traded player has a row per team. Sum across them to get the season
  -- denominator, and do NOT average the per-row yprr_est -- that weights a
  -- 40-route stint the same as a 400-route one.
  SELECT
    season,
    gsis_id,
    SUM(routes_est)      AS routes_est,
    SUM(receiving_yards) AS rec_yards,
    ANY_VALUE(routes_method) AS routes_method
  FROM `ff-python-api.nflreadpy.yprr_proxy`
  WHERE season BETWEEN 2021 AND 2025
    AND season_type = 'REG'     -- the whole point: never sum REG and POST
    AND position = 'WR'
  GROUP BY season, gsis_id
),

ranked AS (
  SELECT s.*, ROW_NUMBER() OVER (PARTITION BY season ORDER BY half_ppr DESC) AS rk
  FROM scoring s
)

SELECT
  r.season,
  r.rk,
  r.player_name,
  r.team,
  r.games,
  ROUND(r.half_ppr, 1)                   AS half_ppr,
  ROUND(r.half_ppr / r.games, 2)         AS ppg,
  ROUND(rt.rec_yards / rt.routes_est, 3) AS yprr,
  CAST(ROUND(rt.routes_est) AS INT64)    AS routes_est,
  r.targets,
  r.rec_yards,
  rt.routes_method
FROM ranked r
LEFT JOIN routes rt
  ON rt.season = r.season
 AND rt.gsis_id = r.player_id
WHERE r.rk <= 12
ORDER BY r.season, r.rk;


-- Sanity checks to run alongside it. Both should come back clean; if the
-- second one returns anything, the join is picking up postseason rows.
--
--   SELECT season, COUNT(*) AS n, COUNTIF(yprr IS NULL) AS missing_yprr
--   FROM (<query above>) GROUP BY season ORDER BY season;
--   -- expect 12 rows per season, 0 missing
--
--   SELECT MAX(games) FROM `ff-python-api.nflreadpy.yprr_proxy`
--   WHERE season_type = 'REG';
--   -- expect <= 17
