"""Thin wrapper around the Sleeper API for player metadata and season projections."""

from sleeper_wrapper import Players, Stats


def fetch_player_db() -> dict:
    """Full Sleeper player directory, keyed by sleeper_id. Carries gsis_id
    (sparse -- see id_matching.resolve_gsis_ids), position, team, age."""
    return Players().get_all_players()


def fetch_season_projections(season: int, season_type: str = "regular") -> dict:
    """Season-long projections, keyed by sleeper_id -> stat dict."""
    return Stats().get_all_projections(season_type, season)
