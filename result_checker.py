"""Result checker module — fetches completed match scores and updates W/L log.

Runs nightly at 23:30 to compare morning picks against actual results
and appends the outcome to results.log.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from data_fetch import fetch_football_fixtures
from config import LOGS_DIR
from logger import logger

RESULTS_LOG = LOGS_DIR / "results.log"


def get_fixture_result(fixture_id: int) -> Optional[Dict[str, Any]]:
    """Fetch the result for a specific fixture.

    Returns:
        Dict with keys 'home_goals', 'away_goals', 'winner', 'status',
        or None if the match is not yet completed.
    """
    try:
        # Try to find in cached fixture data or fetch fresh
        today = datetime.now().strftime("%Y-%m-%d")
        # We need to fetch by fixture ID specifically; simplest is to check today's fixtures
        fixtures = fetch_football_fixtures(today)
        for fixture in fixtures:
            if fixture.get("fixture", {}).get("id") == fixture_id:
                status = fixture.get("fixture", {}).get("status", {}).get("short", "")
                if status in ("FT", "AET", "PEN"):
                    goals = fixture.get("goals", {})
                    score = fixture.get("score", {}).get("fulltime", {})
                    home_goals = goals.get("home", 0) or score.get("home", 0)
                    away_goals = goals.get("away", 0) or score.get("away", 0)

                    if home_goals > away_goals:
                        winner = "home"
                    elif away_goals > home_goals:
                        winner = "away"
                    else:
                        winner = "draw"

                    return {
                        "fixture_id": fixture_id,
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                        "winner": winner,
                        "status": "FT",
                    }
        return None
    except Exception as exc:
        logger.error(f"Error fetching result for fixture {fixture_id}: {exc}", exc_info=True)
        return None


def check_pick_result(pick: Dict[str, Any]) -> str:
    """Determine if a pick won, lost, or is still pending.

    Args:
        pick: Dict containing at least 'fixture_id' and 'pick_type' (home/draw/away).

    Returns:
        'WON', 'LOST', or 'PENDING'.
    """
    result = get_fixture_result(pick["fixture_id"])
    if result is None:
        return "PENDING"

    pick_type = pick.get("pick", "").lower()
    winner = result.get("winner", "").lower()

    if pick_type == winner or (pick_type == "draw" and winner == "draw"):
        return "WON"
    return "LOST"


def log_result(pick: Dict[str, Any], outcome: str, odds: float = None, value: float = None) -> None:
    """Append a single pick result to the results log."""
    try:
        from config import BASE_DIR
        LOGS_DIR = BASE_DIR / "logs"
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        results_file = LOGS_DIR / "results.log"

        with open(results_file, "a", encoding="utf-8") as fh:
            line = f"[{datetime.now().isoformat()}] Fixture {pick['fixture_id']} | Pick: {pick['pick']} | Outcome: {outcome}"
            if odds:
                line += f" | Odds: {odds}"
            if value:
                line += f" | Value: {value:.2%}"
            fh.write(line + "\n")
    except Exception as exc:
        logger.error(f"Error logging result: {exc}", exc_info=True)


def check_all_results(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check results for all picks and return updated pick info.

    Args:
        picks: List of pick dicts from the morning's selections.

    Returns:
        List of dicts with added 'outcome' keys ('WON', 'LOST', or 'PENDING').
    """
    updated = []
    for pick in picks:
        outcome = check_pick_result(pick)
        pick_copy = pick.copy()
        pick_copy["outcome"] = outcome
        updated.append(pick_copy)

        # Log the result
        log_result(pick_copy, outcome, pick.get("odds"), pick.get("value"))

    return updated


def calculate_running_accuracy(days: int = 30) -> float:
    """Calculate the running win accuracy over the last N days from results.log.

    Args:
        days: Number of days to look back.

    Returns:
        Win percentage (0-100).
    """
    try:
        if not RESULTS_LOG.exists():
            return 0.0

        cutoff = datetime.now() - timedelta(days=days)
        wins = 0
        total = 0

        with open(RESULTS_LOG, "r", encoding="utf-8") as fh:
            for line in fh:
                # Parse timestamp from the line
                try:
                    timestamp_str = line.split("]")[0].strip("[")
                    line_date = datetime.fromisoformat(timestamp_str)
                    if line_date >= cutoff:
                        if "Outcome: WON" in line:
                            wins += 1
                            total += 1
                        elif "Outcome: LOST" in line:
                            total += 1
                except (ValueError, IndexError):
                    continue

        return (wins / total * 100) if total > 0 else 0.0
    except Exception as exc:
        logger.error(f"Error calculating running accuracy: {exc}", exc_info=True)
        return 0.0
