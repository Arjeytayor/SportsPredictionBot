"""Basketball prediction model — points differential + home court.

Covers NBA via balldontlie.io (free, no key required).
Uses average point differential over last 10 games, home court advantage,
optionally a sport-specific ELO diff, and a logistic conversion to
win probability.
"""

import math
from typing import Dict, List, Any, Optional

from logger import logger

HOME_COURT_ADVANTAGE = 3.5  # points


def _sigmoid(x: float) -> float:
    """Logistic sigmoid mapping any real value to (0, 1)."""
    return 1.0 / (1.0 + math.exp(-x))


def calculate_point_differential(games: List[Dict[str, Any]]) -> float:
    """Average point differential from a list of game results.

    Args:
        games: List of dicts with keys 'team_score' and 'opponent_score'.

    Returns:
        Average point differential (positive = winning margin).
    """
    if not games:
        return 0.0
    diffs = [
        g.get("team_score", 0) - g.get("opponent_score", 0)
        for g in games
    ]
    return sum(diffs) / len(diffs)

def predict_basketball(
    home_team: str,
    away_team: str,
    home_recent_games: Optional[List[Dict[str, Any]]] = None,
    away_recent_games: Optional[List[Dict[str, Any]]] = None,
    home_elo: int = None,
    away_elo: int = None,
) -> Dict[str, float]:
    """Predict basketball match outcome.

    Args:
        home_team: Name of the home team.
        away_team: Name of the away team.
        home_recent_games: Last games for the home team (optional).
        away_recent_games: Last games for the away team (optional).
        home_elo: Optional sport-specific ELO for home team.
        away_elo: Optional sport-specific ELO for away team.

    Returns:
        Dict with keys: home_win, away_win.
    """
    try:
        home_diff = calculate_point_differential(home_recent_games or [])
        away_diff = calculate_point_differential(away_recent_games or [])

    # Combined score: positive favours home team
        combined_score = (
            (home_diff - away_diff) * 0.5
            + HOME_COURT_ADVANTAGE
        )

    # Optional ELO adjustment (sport-specific ratings)
        if home_elo is not None and away_elo is not None:
            elo_diff = home_elo - away_elo
            combined_score += (elo_diff / 100.0) * 0.3

    # Logistic conversion to probability
        home_prob = _sigmoid(combined_score / 5.0)
        away_prob = 1.0 - home_prob

        return {
            "home_win": home_prob,
            "away_win": away_prob,
        }
    except Exception as exc:
        logger.error(f"Error in basketball prediction for {home_team} v {away_team}: {exc}", exc_info=True)
        return {"home_win": 0.5, "away_win": 0.5}
