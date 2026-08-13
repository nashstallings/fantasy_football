"""Turns Sleeper season projections into dynasty auction values: league
scoring -> age-adjusted value -> superflex-aware VOR -> $3000 auction price
-> tier label."""

import numpy as np
import pandas as pd

from . import config


def fantasy_points(position: str, stat_line: dict) -> float:
    """League scoring: 1pt/25 pass yds, 1pt/10 rush-rec yds, position-based
    PPR (config.PPR_BY_POSITION), configurable passing TD value."""
    g = lambda key: float(stat_line.get(key, 0) or 0)
    points = 0.0
    points += g("pass_yd") * 0.04
    points += g("pass_td") * config.PASS_TD_PTS
    points += g("pass_int") * -2
    points += g("pass_2pt") * 2
    points += g("rush_yd") * 0.1
    points += g("rush_td") * 6
    points += g("rush_2pt") * 2
    points += g("rec_yd") * 0.1
    points += g("rec_td") * 6
    points += g("rec_2pt") * 2
    points += g("rec") * config.PPR_BY_POSITION.get(position, 0.5)
    points += g("fum_lost") * -2
    return round(points, 1)


def build_projection_table(player_db: dict, projections: dict) -> pd.DataFrame:
    """One row per skill-position player with a real (non-placeholder) season projection."""
    rows = []
    for sleeper_id, stat_line in projections.items():
        player = player_db.get(sleeper_id)
        if not player:
            continue
        position = player.get("position")
        if position not in config.FANTASY_POSITIONS:
            continue
        if not any(key.startswith("pts_") for key in stat_line):
            continue  # placeholder/empty projection, not a real player forecast
        rows.append(
            {
                "sleeper_id": sleeper_id,
                "gsis_id": player.get("gsis_id"),
                "name": f"{player.get('first_name', '')} {player.get('last_name', '')}".strip(),
                "position": position,
                "team": player.get("team"),
                "age": player.get("age"),
                "proj_pts": fantasy_points(position, stat_line),
            }
        )
    df = pd.DataFrame(rows)
    return df[df["proj_pts"] > 0].sort_values("proj_pts", ascending=False).reset_index(drop=True)


def _age_multiplier(position: str, age: float) -> float:
    if pd.isna(age):
        return 1.0
    for cutoff, multiplier in config.AGE_CURVE[position]:
        if age <= cutoff:
            return multiplier
    return 1.0


def _replacement_levels(df: pd.DataFrame) -> dict[str, float]:
    levels = {}
    for position, demand in config.POSITIONAL_DEMAND.items():
        pool = df.loc[df["position"] == position, "dyn_val"].sort_values(ascending=False).to_numpy()
        levels[position] = pool[demand - 1] if len(pool) >= demand else (pool[-1] if len(pool) else 0)
    return levels


def _price_top_n(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Distribute AUCTION_TOTAL_BUDGET across the top AUCTION_TOP_N players,
    proportional to value_col with a $1 floor, correcting rounding drift on
    the single largest value so the top N sum to exactly the target budget.
    Everyone past the top N is a flat $1."""
    top = df[df["rank"] <= config.AUCTION_TOP_N].copy()
    tail = df[df["rank"] > config.AUCTION_TOP_N].copy()

    distributable = config.AUCTION_TOTAL_BUDGET - config.AUCTION_TOP_N
    top["auction_value"] = (1 + top[value_col] / top[value_col].sum() * distributable).round().astype(int).clip(
        lower=1
    )
    drift = config.AUCTION_TOTAL_BUDGET - top["auction_value"].sum()
    if drift != 0:
        top.loc[top["auction_value"].idxmax(), "auction_value"] += drift

    tail["auction_value"] = 1
    return pd.concat([top, tail]).sort_values("rank").reset_index(drop=True)


def _tier(auction_value: int) -> tuple[str, str]:
    if auction_value >= 50:
        return ("TIER 1", "Elite / anchor")
    if auction_value >= 30:
        return ("TIER 2", "Strong starter")
    if auction_value >= 18:
        return ("TIER 3", "Solid starter")
    if auction_value >= 8:
        return ("TIER 4", "Flex / depth")
    if auction_value >= 2:
        return ("TIER 5", "Bench upside")
    return ("TIER 6", "Min-value / stash")


def build_auction_values(projections: pd.DataFrame, season: int) -> pd.DataFrame:
    """Age-adjust projections, compute superflex-aware value-over-replacement,
    price to a 12-team $3000 auction budget, and assign tiers. `projections`
    must already have gsis_id resolved (see id_matching.resolve_gsis_ids)."""
    df = projections.copy()
    df["dyn_val"] = df.apply(lambda r: r["proj_pts"] * _age_multiplier(r["position"], r["age"]), axis=1)

    replacement = _replacement_levels(df)
    df["vor"] = df.apply(lambda r: max(r["dyn_val"] - replacement[r["position"]], 0), axis=1)
    df["vor_adj"] = df.apply(lambda r: r["vor"] * config.QB_PREMIUM if r["position"] == "QB" else r["vor"], axis=1)

    df = df.sort_values(["vor_adj", "dyn_val"], ascending=False).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)

    priced = _price_top_n(df, "vor_adj")
    priced["pos_rank"] = priced.groupby("position").cumcount() + 1

    return pd.DataFrame(
        {
            "player_id": priced["gsis_id"].astype(str),
            "player_name": priced["name"],
            "rank": priced["rank"].astype(int),
            "position": priced["position"],
            "auction_value": priced["auction_value"].astype(int),
            "tier": priced["auction_value"].map(lambda v: _tier(v)[0]),
            "tier_desc": priced["auction_value"].map(lambda v: _tier(v)[1]),
            "ranking_note": priced.apply(
                lambda r: f"{r['position']}{int(r['pos_rank'])} · {r['proj_pts']:.0f} proj pts", axis=1
            ),
            "data_source": f"Sleeper {season} proj · VOR + SF premium",
            "created_at": pd.Timestamp.utcnow(),
        }
    )
