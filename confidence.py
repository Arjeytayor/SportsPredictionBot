"""Confidence scoring module — adjusts raw model probabilities using signals.

Signals include form, head-to-head patterns, ELO difference, home record,
key player absence, odds agreement, and league tier adjustments.
"""

from typing import Any, Dict, List

from logger import logger


CONFIDENCE_MEGA = 75.0
CONFIDENCE_HIGH = 65.0
CONFIDENCE_MODERATE = 55.0


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
def last_5_form(matches: List[str]) -> int:
    """Evaluate last 5 form and return a confidence adjustment (+5 or 0)."""
    wins = sum(1 for r in matches if r.upper() == "W")
    losses = sum(1 for r in matches if r.upper() == "L")
    if wins >= 4:
        return +5
    if losses >= 4:
        return -5
    return 0


def h2h_pattern(h2h_results: List[str]) -> int:
    """Check for strong head-to-head pattern and return adjustment (+3 or 0)."""
    if len(h2h_results) < 4:
        return 0
    wins = sum(1 for r in h2h_results if r.upper() == "W")
    if wins >= 4:
        return +3
    return 0


def elo_adjustment(elo_diff: float) -> int:
    """Return ELO-based confidence adjustment (+5 or 0)."""
    if elo_diff > 150:
        return +5
    return 0


def home_record_adjustment(home_win_rate: float) -> int:
    """Return home record adjustment (+3 or 0)."""
    if home_win_rate >= 0.70:
        return +3
    return 0


def odds_agreement(model_prob: float, market_prob: float) -> int:
    """Check if model and market odds agree within 5% (+5 or 0)."""
    if abs(model_prob - market_prob) <= 0.05:
        return +5
    return 0


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------
def calculate_confidence(
    raw_prob: float,
    last_5: List[str] = None,
    h2h_results: List[str] = None,
    elo_diff: float = 0.0,
    home_win_rate: float = 0.0,
    key_player_absent: bool = False,
    market_prob: float = None,
    is_lower_league: bool = False,
    is_high_variance_sport: bool = False,
) -> float:
    """Calculate the final confidence score for a pick.

    Args:
        raw_prob: Raw model probability (0-1).
        last_5: Last 5 match results (W/D/L).
        h2h_results: Last 5 head-to-head results.
        elo_diff: ELO difference (home - away).
        home_win_rate: Home win rate this season (0-1).
        key_player_absent: Whether a key player is absent.
        market_prob: Market implied probability (0-1).
        is_lower_league: Below tier 2 in any country.
        is_high_variance_sport: MMA or tennis.

    Returns:
        Confidence score as a percentage (0-100).
    """
    try:
        confidence = raw_prob * 100.0

        # Apply signal adjustments
        if last_5:
            confidence += last_5_form(last_5)
        if h2h_results:
            confidence += h2h_pattern(h2h_results)
        confidence += elo_adjustment(elo_diff)
        if home_win_rate:
            confidence += home_record_adjustment(home_win_rate)
        if market_prob is not None:
            confidence += odds_agreement(raw_prob, market_prob)
        if key_player_absent:
            confidence -= 7.0
        if is_lower_league:
            # Apply a cap of -10%
            confidence = min(confidence, 90.0)

        # High variance sport cap
        if is_high_variance_sport:
            confidence = min(confidence, 60.0)

        return max(0.0, min(100.0, confidence))
    except Exception as exc:
        logger.error(f"Error calculating confidence: {exc}", exc_info=True)
        return raw_prob * 100.0


def confidence_band(confidence: float) -> str:
    """Map a confidence score to a human-readable band.

    Returns:
        One of: 'MEGA PICK', 'HIGH CONFIDENCE', 'MODERATE', 'LOW'.
    """
    if confidence >= CONFIDENCE_MEGA:
        return "MEGA PICK"
    if confidence >= CONFIDENCE_HIGH:
        return "HIGH CONFIDENCE"
    if confidence >= CONFIDENCE_MODERATE:
        return "MODERATE"
    return "LOW"


def should_send(confidence: float) -> bool:
    """Return True if the pick meets the minimum confidence threshold."""
    return confidence >= CONFIDENCE_MODERATE
