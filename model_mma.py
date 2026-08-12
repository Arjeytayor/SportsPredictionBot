"""MMA prediction model — head-to-head ELO model.

Maintains custom ELO ratings per fighter updated after every fight result.
Supplements with win streak, recent finish rate, and style matchup flags.
Confidence is capped at 60% due to high variance.
"""

from typing import Dict, List, Any

from logger import logger

K_FACTOR = 32
MAX_CONFIDENCE = 0.60  # cap for MMA


def _expected_score(elo_a: int, elo_b: int) -> float:
    """ELO expected score formula."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def update_elo(winner_elo: int, loser_elo: int, k: int = K_FACTOR) -> tuple:
    """Update ELO ratings after a fight.

    Returns:
        (new_winner_elo, new_loser_elo)
    """
    exp_winner = _expected_score(winner_elo, loser_elo)
    exp_loser = 1.0 - exp_winner
    new_winner = winner_elo + k * (1.0 - exp_winner)
    new_loser = loser_elo + k * (0.0 - exp_loser)
    return round(new_winner), round(new_loser)


def calculate_win_streak(fights: List[Dict[str, Any]], fighter_name: str) -> int:
    """Count consecutive wins from most recent fights."""
    streak = 0
    for fight in reversed(fights):
        if fight.get("winner") == fighter_name:
            streak += 1
        else:
            break
    return streak


def calculate_finish_rate(fights: List[Dict[str, Any]], fighter_name: str) -> float:
    """Calculate recent finish rate (KO/TKO or submission wins)."""
    if not fights:
        return 0.0
    finishes = sum(
        1 for f in fights[-5:]
        if f.get("winner") == fighter_name and f.get("finish_type", "") in ("KO", "TKO", "SUB", "Submission")
    )
    return finishes / min(len(fights[-5:]), 5)


def predict_mma(
    fighter_a: str,
    fighter_b: str,
    fighter_a_elo: int,
    fighter_b_elo: int,
    fighter_a_fights: List[Dict[str, Any]] = None,
    fighter_b_fights: List[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """Predict MMA fight outcome.

    Args:
        fighter_a: Name of fighter A.
        fighter_b: Name of fighter B.
        fighter_a_elo: Current ELO rating of fighter A.
        fighter_b_elo: Current ELO rating of fighter B.
        fighter_a_fights: List of recent fight dicts for fighter A.
        fighter_b_fights: List of recent fight dicts for fighter B.

    Returns:
        Dict with keys: fighter_a_win, fighter_b_win (capped at 60%).
    """
    try:
        base_prob_a = _expected_score(fighter_a_elo, fighter_b_elo)

        # Adjust for streak and finish rate if data is available
        if fighter_a_fights:
            streak_a = calculate_win_streak(fighter_a_fights, fighter_a)
            finish_a = calculate_finish_rate(fighter_a_fights, fighter_a)
            base_prob_a += (streak_a * 0.01) + (finish_a * 0.03)

        if fighter_b_fights:
            streak_b = calculate_win_streak(fighter_b_fights, fighter_b)
            finish_b = calculate_finish_rate(fighter_b_fights, fighter_b)
            base_prob_a -= (streak_b * 0.01) + (finish_b * 0.03)

        # Clamp and normalise
        base_prob_a = max(0.15, min(0.85, base_prob_a))
        base_prob_b = 1.0 - base_prob_a

        # Cap confidence at 60%
        if max(base_prob_a, base_prob_b) > MAX_CONFIDENCE:
            # Scale down so max is exactly 60%
            max_p = max(base_prob_a, base_prob_b)
            scale = MAX_CONFIDENCE / max_p
            base_prob_a *= scale
            base_prob_b *= scale

        return {
            f"{fighter_a}_win": base_prob_a,
            f"{fighter_b}_win": base_prob_b,
        }
    except Exception as exc:
        logger.error(f"Error in MMA prediction for {fighter_a} v {fighter_b}: {exc}", exc_info=True)
        return {
            f"{fighter_a}_win": 0.5,
            f"{fighter_b}_win": 0.5,
        }
