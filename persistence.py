"""Simple JSON persistence module for the Sports Prediction Bot.

Saves today's picks and results to disk so they survive bot restarts.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from config import BASE_DIR
from logger import logger

_STATE_PATH = BASE_DIR / "data" / "bot_state.json"


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_state() -> Dict[str, Any]:
    """Load the last persisted bot state (picks and results).

    Only returns state from today; anything older is discarded.
    """
    if not _STATE_PATH.exists():
        return {"picks": [], "results": [], "date": _today_str()}

    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        # Only reuse picks from the same day
        if data.get("date") == _today_str():
            logger.info(f"Restored state: {len(data.get('picks', []))} picks, {len(data.get('results', []))} results")
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to load bot state: {exc}")

    return {"picks": [], "results": [], "date": _today_str()}


def save_state(picks: List[Dict], results: List[Dict]) -> None:
    """Persist picks and results to disk.

    Args:
        picks: List of pick dicts (football, basketball, etc.).
        results: List of result dicts.
    """
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = {
            "date": _today_str(),
            "picks": picks,
            "results": results,
            "saved_at": datetime.now().isoformat(),
        }
        _STATE_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.debug(f"Bot state saved: {len(picks)} picks, {len(results)} results")
    except (OSError, TypeError) as exc:
        logger.error(f"Failed to save bot state: {exc}", exc_info=True)
