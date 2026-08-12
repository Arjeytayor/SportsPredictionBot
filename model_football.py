"""Football prediction model — Poisson + ELO hybrid.

Implements the full model described in the master prompt:
1. Attack / defence strength from last 10 matches
2. Home advantage factor (1.35)
3. Expected goals via Poisson
4. ELO blend for probability adjustments
5. BTTS and Over 2.5 probability outputs
"""

import math
from typing import Dict, List, Tuple

from scipy.stats import poisson

from elo_loader import get_team_elo
from logger import logger


def _factorial(n: int) -> float:
    """Compute n! using math.factorial."""
    return math.factorial(n)


def compute_attack_defence_strength(
    team_stats: List[Dict],
    league_avg_scored: float,
    league_avg_conceded: float,
    home: bool = True,
) -> Dict[str, float]:
    """Compute attack and defence strength for a single team.

    Returns:
        Dict with keys: "attack" and "defence".
    """
    recent = team_stats[-10:] if len(team_stats) >= 10 else team_stats
    goals_for = sum(m.get("goals_for", 0) for m in recent) / max(len(recent), 1)
    goals_against = sum(m.get("goals_against", 0) for m in recent) / max(len(recent), 1)

    attack = goals_for / league_avg_scored if league_avg_scored > 0 else 1.0
    defence = goals_against / league_avg_conceded if league_avg_conceded > 0 else 1.0

    return {"attack": attack, "defence": defence}


def calculate_expected_goals(
    home_attack: float,
    home_defence: float,
    away_attack: float,
    away_defence: float,
    league_avg_goals: float,
) -> Tuple[float, float]:
    """Calculate expected goals for home and away teams."""
    lambda_home = home_attack * away_defence * league_avg_goals * 1.35
    lambda_away = away_attack * home_defence * league_avg_goals
    return max(lambda_home, 0.05), max(lambda_away, 0.05)


def poisson_scoreline_probability(lambda_val: float, goals: int) -> float:
    """Probability of exactly `goals` given Poisson mean `lambda_val`."""
    return (lambda_val ** goals * math.exp(-lambda_val)) / _factorial(goals)


def calculate_scoreline_matrix(lambda_home: float, lambda_away: float, max_goals: int = 5) -> Tuple[float, float, float]:
    """Build the scoreline matrix and return P(home win), P(draw), P(away win)."""
    p_home_win = 0.0
    p_draw = 0.0
    p_away_win = 0.0

    for home_goals in range(max_goals + 1):
        for away_goals in range(max_goals + 1):
            p = poisson_scoreline_probability(lambda_home, home_goals) * poisson_scoreline_probability(lambda_away, away_goals)
            if home_goals > away_goals:
                p_home_win += p
            elif home_goals == away_goals:
                p_draw += p
            else:
                p_away_win += p

    return p_home_win, p_draw, p_away_win


def calculate_btts(lambda_home: float, lambda_away: float, max_goals: int = 5) -> float:
    """Probability that both teams score (BTTS) using Poisson."""
    p_both_score = 0.0
    for hg in range(1, max_goals + 1):
        for ag in range(1, max_goals + 1):
            p = poisson_scoreline_probability(lambda_home, hg) * poisson_scoreline_probability(lambda_away, ag)
            p_both_score += p
    return p_both_score


def calculate_over_2_5(lambda_home: float, lambda_away: float, max_goals: int = 5) -> float:
    """Probability that total goals > 2.5 using Poisson."""
    p_over = 0.0
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            if hg + ag > 2:
                p = poisson_scoreline_probability(lambda_home, hg) * poisson_scoreline_probability(lambda_away, ag)
                p_over += p
    return p_over


def apply_elo_blend(home_team: str, away_team: str, p_home: float, p_draw: float, p_away: float) -> Tuple[float, float, float]:
    """Adjust win probabilities based on ELO difference."""
    try:
        elo_home = get_team_elo(home_team)
        elo_away = get_team_elo(away_team)
        elo_diff = elo_home - elo_away

        if elo_diff > 200:
            adj = 0.10
        elif elo_diff > 100:
            adj = 0.05
        elif elo_diff < -200:
            adj = -0.10
        elif elo_diff < -100:
            adj = -0.05
        else:
            return p_home, p_draw, p_away

        # Apply adjustment while keeping total probability = 1.0
        if adj > 0:
            p_home = min(p_home + adj, 1.0)
            p_away = max(p_away - adj, 0.0)
        else:
            p_away = min(p_away + abs(adj), 1.0)
            p_home = max(p_home - abs(adj), 0.0)

        # Renormalise
        total = p_home + p_draw + p_away
        if total > 0:
            p_home /= total
            p_draw /= total
            p_away /= total

        return p_home, p_draw, p_away
    except Exception as exc:
        logger.error(f"Error in ELO blend: {exc}", exc_info=True)
        return p_home, p_draw, p_away


def predict_football(
    home_team: str,
    away_team: str,
    home_stats: List[Dict],
    away_stats: List[Dict],
    league_avg_scored: float = 1.40,
    league_avg_conceded: float = 1.40,
) -> Dict[str, float]:
    """Run the full Poisson + ELO prediction model for a football fixture.

    Args:
        home_team: Name of the home team.
        away_team: Name of the away team.
        home_stats: List of last-match dicts for the home team.
        away_stats: List of last-match dicts for the away team.
        league_avg_scored: League average goals scored per match.
        league_avg_conceded: League average goals conceded per match.

    Returns:
        Dict with keys: home_win, draw, away_win, btts, over_2_5
    """
    try:
        # Step 1: Attack / Defence strength
        home_ad = compute_attack_defence_strength(home_stats, league_avg_scored, league_avg_conceded, home=True)
        away_ad = compute_attack_defence_strength(away_stats, league_avg_scored, league_avg_conceded, home=False)

        # Step 2: Expected goals
        lambda_home, lambda_away = calculate_expected_goals(
            home_ad["attack"], home_ad["defence"],
            away_ad["attack"], away_ad["defence"],
            league_avg_goals=(league_avg_scored + league_avg_conceded) / 2,
        )

        # Step 3: Scoreline matrix
        p_home, p_draw, p_away = calculate_scoreline_matrix(lambda_home, lambda_away)

        # Step 4: ELO blend
        p_home, p_draw, p_away = apply_elo_blend(home_team, away_team, p_home, p_draw, p_away)

        # Step 5: BTTS and Over 2.5
        btts = calculate_btts(lambda_home, lambda_away)
        over_2_5 = calculate_over_2_5(lambda_home, lambda_away)

        return {
            "home_win": p_home,
            "draw": p_draw,
            "away_win": p_away,
            "btts": btts,
           "over_2_5": over_2_5,
        }
    except Exception as exc:
        logger.error(f"Error in football prediction for {home_team} v {away_team}: {exc}", exc_info=True)
        return {
            "home_win": 0.33, "draw": 0.34, "away_win": 0.33,
            "btts": 0.5, "over_2_5": 0.5,
        }
