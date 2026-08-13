"""Resolve gsis_id for players Sleeper doesn't carry one for.

Sleeper's own gsis_id field is sparse. We backfill it by matching on a
normalized name + position against nflreadpy's player table, and fall back
to a stable synthetic id for anyone still unmatched (usually rookies
nflreadpy hasn't onboarded yet).
"""

import pandas as pd


def _keyname(name: str) -> str:
    """Normalize a player name for matching: lowercase, strip punctuation
    and generational suffixes that the two sources don't apply consistently."""
    return (
        str(name)
        .lower()
        .strip()
        .replace(".", "")
        .replace("'", "")
        .replace("-", " ")
        .replace(" jr", "")
        .replace(" sr", "")
        .replace(" iii", "")
        .replace(" ii", "")
    )


def _build_lookup(nfl_players: pd.DataFrame) -> dict[str, str]:
    npx = nfl_players[["gsis_id", "display_name", "position"]].dropna(subset=["gsis_id"]).copy()
    npx["key"] = npx["display_name"].map(_keyname) + "|" + npx["position"]
    lookup: dict[str, str] = {}
    for _, row in npx.iterrows():
        lookup.setdefault(row["key"], row["gsis_id"])
    return lookup


def resolve_gsis_ids(
    df: pd.DataFrame, nfl_players: pd.DataFrame, synthetic_overrides: dict[str, str] | None = None
) -> pd.DataFrame:
    """Fill missing gsis_id in df (columns: gsis_id, name, position, sleeper_id)
    by name+position match against nfl_players, then a named override, then a
    stable synthetic id derived from the sleeper_id."""
    df = df.copy()
    lookup = _build_lookup(nfl_players)
    overrides = synthetic_overrides or {}

    def resolve(row):
        if pd.notna(row["gsis_id"]):
            return row["gsis_id"]
        matched = lookup.get(_keyname(row["name"]) + "|" + row["position"])
        if matched:
            return matched
        if row["name"] in overrides:
            return overrides[row["name"]]
        return f"SL_{row['sleeper_id']}"

    df["gsis_id"] = df.apply(resolve, axis=1)
    return df
