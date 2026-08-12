"""Volleyball prediction model — set-based binomial.

Predicts set win probability from attack efficiency and service error rates,
then uses binomial distribution to derive match win probability.
Assumes best-of-5 sets (first to 3 sets wins).
"""

from typing import Dict, List, Any
from math import comb

from logger import logger


def calculate_set_win_prob(
    team_stats: Dict[str, float],
    opponent_stats: Dict[str, float],
) -> float:
    """Estimate the probability that a team wins a single set.

    Args:
        team_stats: Dict with keys 'attack_efficiency', 'serve_error_rate'
        opponent_stats: Dict with keys 'attack_efficiency', 'serve_error_rate'

    Returns:
        Probability (0-1) of this team winning a set.
    """
    teff = team_stats.get("attack_efficiency", 0.3)
    terr = team_stats.get("serve_error_rate", 0.15)
    oppeff = opponent_stats.get("attack_efficiency", 0.3)
    opperr = opponent_stats.get("serve_error_rate", 0.15)

    # Simple heuristic: higher attack efficiency and lower serve error = better
    net_score = (teff - oppeff) * 100 - (terr - opperr) * 50
    prob = 0.5 + net_score / 20.0
    return max(0.1, min(0.9, prob))


def match_win_from_sets(set_win_prob: float) -> float:
    """Convert per-set win probability to match win probability (best of 5).

    Uses the binomial distribution: P(win at least 3 of 5 sets).
    """
    prob = 0.0
    for wins in range(3, 6):
        prob += comb(5, wins) * (set_win_prob ** wins) * ((1 - set_win_prob) ** (5 - wins))
    return prob


def predict_volleyball(
    team1: str,
    team2: str,
    team1_stats: Dict[str, float],
    team2_stats: Dict[str, float],
) -> Dict[str, float]:
    """Predict volleyball match outcome.

    Args:
        team1: Name of team 1 (home).
        team2: Name of team 2 (away).
        team1_stats: Attack efficiency and serve error rate for team 1.
        team2_stats: Attack efficiency and serve error rate for team 2.

    Returns:
        Dict with keys: team1_win, team2_win
    """
    try:
        set_p1 = calculate_set_win_prob(team1_stats, team2_stats)
        set_p2 = 1.0 - set_p1

        match_p1 = match_win_from_sets(set_p1)
        match_p2 = match_win_from_sets(set_p2)

        # Normalise
        total = match_p1 + match_p2
        if total > 0:
            match_p1 /= total
            match_p2 /= total

        return {
            f"{team1}_win": match_p1,
            f"{team2}_win": match_p2,
        }
    except Exception as exc:
        logger.error(f"Error in volleyball prediction for {team1} v {team2}: {exc}", exc_info=True)
        return {f"{team1}_win": 0.5, f"{team2}_win": 0.5}
