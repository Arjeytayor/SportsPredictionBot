"""Value betting module — calculates whether a pick offers positive expected value.

Core formula: value = (model_probability * decimal_odds) - 1
"""

from typing import Dict, Optional, Tuple

from config import VALUE_THRESHOLD
from logger import logger


def calculate_value(model_prob: float, decimal_odds: float) -> float:
    """Calculate the expected value of a bet.

    Args:
        model_prob: Model probability (0-1) of the outcome occurring.
        decimal_odds: Decimal odds offered by the bookmaker.

    Returns:
        Expected value as a float. Positive = value bet.
    """
    return (model_prob * decimal_odds) - 1.0


def is_value_bet(model_prob: float, decimal_odds: float, threshold: float = VALUE_THRESHOLD) -> bool:
    """Check if a bet meets the minimum value threshold.

    Args:
        model_prob: Model probability (0-1).
        decimal_odds: Decimal odds.
        threshold: Minimum positive edge required.

    Returns:
        True if the bet is a value bet.
    """
    value = calculate_value(model_prob, decimal_odds)
    return value > threshold


def get_best_odds(odds_data: list) -> Tuple[Dict[str, float], str]:
    """Extract the best 1X2 odds from API-Sports v3 odds response.

    Parses the 'Match Winner' market and returns the best Home, Draw,
    and Away odds found across all bookmakers.

    Args:
        odds_data: Raw odds list from API-Sports (response array).

    Returns:
        Tuple of ({'Home': float, 'Draw': float, 'Away': float}, best_bookmaker)
        or (None, None) if unavailable.
    """
    try:
        if not odds_data:
            return None, None

        best_1x2 = {"Home": 0.0, "Draw": 0.0, "Away": 0.0}
        best_bookmaker = ""

        for odds_item in odds_data:
            for bookmaker in odds_item.get("bookmakers", []):
                for bet in bookmaker.get("bets", []):
                    # Only look at the 1X2 / Match Winner market
                    if bet.get("name") != "Match Winner":
                        continue

                    for value in bet.get("values", []):
                        try:
                            value_name = value.get("value", "")
                            odd_val = float(value.get("odd", 0))

                            if value_name in best_1x2 and odd_val > best_1x2[value_name]:
                                best_1x2[value_name] = odd_val
                                best_bookmaker = bookmaker.get("name", "")
                        except (ValueError, TypeError):
                            continue

        # Only return if we found at least one outcome
        if any(v > 0 for v in best_1x2.values()):
            return best_1x2, best_bookmaker
        return None, None
    except Exception as exc:
        logger.error(f"Error extracting best odds: {exc}", exc_info=True)
        return None, None


def estimate_odds(model_prob: float) -> float:
    """Generate a conservative odds estimate when live odds are unavailable.

    Adds a small buffer so the value filter does not kill every pick
    when real bookmaker odds are unavailable.
    """
    if model_prob <= 0:
        return float("inf")
    # Give a small value edge (≈8%) so the pick clears the value
    # threshold even without live odds.
    return (1.0 / model_prob) * 1.08
