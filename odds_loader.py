"""Historical odds loader — parses football-data.co.uk CSVs.

Provides Pinnacle closing odds (PSH, PSD, PSA) for backtesting and
benchmarking value.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from config import HISTORICAL_DIR
from logger import logger

# Mapping of football-data.co.uk league codes to file names
LEAGUE_FILES = {
    "premier_league": "E0",
    "championship": "E1",
    "league_one": "E2",
    "league_two": "E3",
    "la_liga": "SP1",
    "la_liga_2": "SP2",
    "serie_a": "I1",
    "serie_b": "I2",
    "bundesliga": "D1",
    "bundesliga_2": "D2",
    "ligue_1": "F1",
    "ligue_2": "F2",
    "eredivisie": "N1",
    "primeira_liga": "P1",
    "championship_playoffs": "EC",
}


def load_historical_csv(league_key: str, season: int = None) -> Optional[pd.DataFrame]:
    """Load a historical odds CSV for a given league key.

    Args:
        league_key: One of the keys in LEAGUE_FILES.
        season: The season year (e.g. 2024 for 2024-25).

    Returns:
        pandas DataFrame or None if file not found.
    """
    file_name = LEAGUE_FILES.get(league_key, league_key)
    path = HISTORICAL_DIR / f"{file_name}.csv"

    if not path.exists():
        logger.warning(f"Historical CSV not found: {path}")
        return None

    try:
        df = pd.read_csv(path, encoding="latin1", on_bad_lines="skip")
        if season:
            df = df[df.get("Season", pd.Series([season] * len(df))) == season]
        return df
    except Exception as exc:
        logger.error(f"Failed to load historical CSV {path}: {exc}", exc_info=True)
        return None


def get_pinnacle_odds(df: pd.DataFrame, match_index: int) -> Dict[str, float]:
    """Extract Pinnacle closing odds for a specific match row.

    Returns:
        {"H": float, "D": float, "A": float}
    """
    row = df.iloc[match_index]
    return {
        "H": float(row.get("PSH", 0.0)),
        "D": float(row.get("PSD", 0.0)),
        "A": float(row.get("PSA", 0.0)),
    }


def list_available_leagues() -> List[str]:
    """Return a list of league keys for which CSVs exist in data/historical/."""
    available = []
    for key, filename in LEAGUE_FILES.items():
        if (HISTORICAL_DIR / f"{filename}.csv").exists():
            available.append(key)
    return available
