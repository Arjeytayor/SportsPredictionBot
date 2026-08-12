"""Configuration module for the Sports Prediction Bot.

All settings, API keys, paths, and thresholds are centralised here.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Base directories
# ---------------------------------------------------------------------------
BASE_DIR = Path(r"C:/Users/DELL/Documents/SportsPredictionBot")
CACHE_DIR = BASE_DIR / "cache"
DATA_DIR = BASE_DIR / "data"
HISTORICAL_DIR = DATA_DIR / "historical"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
for _dir in (CACHE_DIR, DATA_DIR, HISTORICAL_DIR, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# API Keys and tokens (loaded from environment or fall back to defaults)
# ---------------------------------------------------------------------------
load_dotenv()
API_SPORTS_KEY: str = os.getenv("API_SPORTS_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
NIM_API_KEY: str = os.getenv("NIM_API_KEY", "")

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
API_SPORTS_BASE = "https://v3.football.api-sports.io"
API_BASKETBALL_BASE = "https://v1.basketball.api-sports.io"
API_VOLLEYBALL_BASE = "https://v1.volleyball.api-sports.io"
API_MMA_BASE = "https://v1.mma.api-sports.io"
BALLDONTLIE_BASE = "https://api.balldontlie.io/v1"
CLUBELO_BULK_URL = "http://clubelo.com/download"
FOOTBALL_DATA_BASE = "https://www.football-data.co.uk"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
VALUE_THRESHOLD: float = 0.05  # Minimum positive edge for a pick
CONFIDENCE_MEGA: float = 75.0  # 75%+ → MEGA PICK
CONFIDENCE_HIGH: float = 65.0  # 65-74% → HIGH CONFIDENCE
CONFIDENCE_MODERATE: float = 55.0  # 55-64% → MODERATE
# Below 55% → dropped

# ---------------------------------------------------------------------------
# Daily request budget per sport (API-Sports free tier = 100 requests/day)
# ---------------------------------------------------------------------------
DAILY_REQUEST_LIMIT: int = 100
BUDGET_WARNING_THRESHOLD: int = 90

# ---------------------------------------------------------------------------
# Request budget helpers
# ---------------------------------------------------------------------------

def _budget_file(date_str: str) -> Path:
    return CACHE_DIR / f"request_count_{date_str}.json"


def get_request_count(date_str: str) -> dict:
    """Return the current request count per sport for *date_str* (YYYY-MM-DD)."""
    path = _budget_file(date_str)
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {
        "football": 0,
        "basketball": 0,
        "volleyball": 0,
        "mma": 0,
    }


def set_request_count(date_str: str, counts: dict) -> None:
    """Persist the daily request count per sport."""
    with open(_budget_file(date_str), "w", encoding="utf-8") as fh:
        json.dump(counts, fh, indent=2)


def increment_request(sport: str, date_str: str) -> None:
    """Increment the request counter for a given sport."""
    counts = get_request_count(date_str)
    counts.setdefault(sport, 0)
    counts[sport] += 1
    set_request_count(date_str, counts)
