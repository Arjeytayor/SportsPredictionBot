"""Lineup monitoring module — fetches confirmed lineups and flags key player absences.

Runs approximately 65 minutes before kickoff for each fixture where a pick
has been selected. Compares confirmed lineup against the key_players list
and sends a warning to Telegram if any key player is missing.
"""

from typing import Dict, List, Any, Set

from data_fetch import fetch_football_lineups
from logger import logger

# In-memory store for key players per team
# Structure: {team_name: [player_name, ...]}
KEY_PLAYERS_DB: Dict[str, List[str]] = {}


def set_key_players(team_name: str, players: List[str]) -> None:
    """Register key players for a team."""
    KEY_PLAYERS_DB[team_name] = [p.strip().lower() for p in players]


def get_key_players(team_name: str) -> List[str]:
    """Get the list of key players for a team."""
    return KEY_PLAYERS_DB.get(team_name, [])


def check_lineup_for_absences(fixture_id: int, home_team: str, away_team: str) -> Dict[str, Any]:
    """Check confirmed lineups for missing key players.

    Args:
        fixture_id: API-Sports fixture ID.
        home_team: Name of the home team.
        away_team: Name of the away team.

    Returns:
        Dict with:
            - 'absent_players': list of missing key player names
            - 'confidence_reduction': total percentage points to reduce
            - 'warnings': list of human-readable warning strings
    """
    absent_players = []
    warnings = []

    try:
        lineups = fetch_football_lineups(fixture_id)
        if not lineups:
            logger.warning(f"No lineup data available for fixture {fixture_id}")
            return {
                "absent_players": [],
                "confidence_reduction": 0.0,
                "warnings": [],
            }

        # Extract all players in the confirmed lineup
        lineup_names: Set[str] = set()
        for lineup in lineups:
            for player in lineup.get("startXI", []) + lineup.get("substitutes", []):
                name = player.get("player", {}).get("name", "").strip().lower()
                if name:
                    lineup_names.add(name)

        # Check home team key players
        for player in get_key_players(home_team):
            if player and player not in lineup_names:
                absent_players.append(player)
                warnings.append(
                    f"⚠Key player absent: {player.title()} not in confirmed lineup for {home_team}. Confidence reduced."
                )

        # Check away team key players
        for player in get_key_players(away_team):
            if player and player not in lineup_names:
                absent_players.append(player)
                warnings.append(
                    f"⚠Key player absent: {player.title()} not in confirmed lineup for {away_team}. Confidence reduced."
                )

        confidence_reduction = len(absent_players) * 7.0 if absent_players else 0.0

        return {
            "absent_players": absent_players,
            "confidence_reduction": confidence_reduction,
            "warnings": warnings,
        }

    except Exception as exc:
        logger.error(f"Error checking lineups for fixture {fixture_id}: {exc}", exc_info=True)
        return {
            "absent_players": [],
            "confidence_reduction": 0.0,
            "warnings": [],
        }
