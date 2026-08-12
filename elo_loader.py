"""ELO rating loader — downloads and parses Club-ELO bulk CSV.

Maintains a weekly CSV from clubelo.com and provides a name-mapping layer
that translates API-Sports team names to Club-ELO names.
"""

import csv
from datetime import datetime
from pathlib import Path

import requests

from config import DATA_DIR, CACHE_DIR, CLUBELO_BULK_URL
from logger import logger

ELO_CSV_PATH = DATA_DIR / "club_elo.csv"

# ---------------------------------------------------------------------------
# Mapping: API-Sports / common name → Club-ELO exact name
# ---------------------------------------------------------------------------
_TEAM_NAME_MAPPINGS = {
    # English
    "manchester united": "Man United",
    "manchester city": "Man City",
    "tottenham hotspur": "Tottenham",
    "tottenham": "Tottenham",
    "newcastle united": "Newcastle",
    "newcastle": "Newcastle",
    "west ham united": "West Ham",
    "leicester city": "Leicester",
    "aston villa": "Aston Villa",
    "leeds united": "Leeds",
    "norwich city": "Norwich",
    "brighton & hove albion": "Brighton",
    "brighton and hove albion": "Brighton",
    "wolverhampton wanderers": "Wolves",
    "wolves": "Wolves",
    "sheffield united": "Sheffield United",
    "west bromwich albion": "West Brom",
    "nottingham forest": "Nottingham Forest",
    "burnley": "Burnley",
    "bournemouth": "Bournemouth",
    # Spanish
    "real betis": "Betis",
    "betis": "Betis",
    "athletic bilbao": "Athletic",
    "athletic club": "Athletic",
    "atletico madrid": "Atletico",
    "rayo vallecano": "Rayo Vallecano",
    "real sociedad": "Real Sociedad",
    "sevilla": "Sevilla",
    "villarreal": "Villarreal",
    "real madrid": "Real Madrid",
    "fc barcelona": "Barcelona",
    "valencia": "Valencia",
    "celta vigo": "Celta",
    # German
    "rb leipzig": "RB Leipzig",
    "bayer leverkusen": "Leverkusen",
    "borussia dortmund": "Dortmund",
    "vfb stuttgart": "Stuttgart",
    "tsg hoffenheim": "Hoffenheim",
    "bayern munich": "Bayern",
    "fc bayern munchen": "Bayern",
    # Italian
    "juventus": "Juventus",
    "napoli": "Napoli",
    "ac milan": "Milan",
    "inter milan": "Inter",
    "internazionale": "Inter",
    "atalanta": "Atalanta",
    "roma": "Roma",
    "lazio": "Lazio",
    "fiorentina": "Fiorentina",
    # French
    "paris saint-germain": "Paris SG",
    "paris saint germain": "Paris SG",
    "psg": "Paris SG",
    "marseille": "Marseille",
    "lille": "Lille",
    "rennes": "Rennes",
    "monaco": "Monaco",
    "nice": "Nice",
    # Portuguese
    "benfica": "Benfica",
    "fc porto": "Porto",
    "sporting": "Sporting",
    # Dutch
    "ajax": "Ajax",
    "psv eindhoven": "PSV",
    "feyenoord": "Feyenoord",
}

# ---------------------------------------------------------------------------
# Cache in memory (refreshed daily via _elo_cache_date)
# ---------------------------------------------------------------------------
_elo_cache: dict = None
_elo_cache_date: str = ""


def download_elo_csv() -> None:
    """Download the latest Club-ELO bulk CSV (cached for 7 days)."""
    cache_file = CACHE_DIR / "club_elo_last_download.txt"
    should_download = True

    if cache_file.exists():
        last = cache_file.read_text().strip()
        if last == datetime.now().strftime("%Y-%m-%d"):
            should_download = False
        elif ELO_CSV_PATH.exists():
            age_days = (datetime.now().timestamp() - ELO_CSV_PATH.stat().st_mtime) / 86400
            if age_days < 7:
                should_download = False

    if not should_download:
        return

    try:
        response = requests.get(CLUBELO_BULK_URL, timeout=30)
        response.raise_for_status()
        ELO_CSV_PATH.write_bytes(response.content)
        cache_file.write_text(datetime.now().strftime("%Y-%m-%d"))
        _reset_cache()
        logger.info("Downloaded latest Club-ELO CSV.")
    except Exception as exc:
        logger.error(f"Failed to download Club-ELO CSV: {exc}", exc_info=True)


def _normalise(name: str) -> str:
    return name.strip().lower()


def _reset_cache():
    """Invalidate the in-memory ELO cache."""
    global _elo_cache, _elo_cache_date
    _elo_cache = None
    _elo_cache_date = ""


def _load_elo_dict() -> dict:
    """Load the entire Club-ELO CSV into a {name: elo} dict (cached in memory)."""
    global _elo_cache, _elo_cache_date
    today = datetime.now().strftime("%Y-%m-%d")

    if _elo_cache is not None and _elo_cache_date == today:
        return _elo_cache

    download_elo_csv()
    if not ELO_CSV_PATH.exists():
        return {}

    try:
        with open(ELO_CSV_PATH, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            _elo_cache = {row["Club"]: int(row["Elo"]) for row in reader if "Club" in row and "Elo" in row}
            _elo_cache_date = today
            return _elo_cache
    except Exception as exc:
        logger.error(f"Error parsing ELO CSV: {exc}", exc_info=True)
        return {}


def _get_mapping(team_name: str) -> str:
    """Return the Club-ELO canonical name if a mapping exists."""
    lower = _normalise(team_name)
    return _TEAM_NAME_MAPPINGS.get(lower, team_name)


def _fuzzy_match(target: str, candidates: list) -> str:
    """Find the best fuzzy match for target from a list of candidate names.

    Tries: prefix containment, suffix containment, common substring.
    """
    norm_target = _normalise(target)
    best_score = 0.0
    best_match = None

    for candidate in candidates:
        norm_cand = _normalise(candidate)

    # Exact match after normalisation
        if norm_cand == norm_target:
            return candidate

    # Substring match
        if norm_target in norm_cand or norm_cand in norm_target:
            score = min(len(norm_target), len(norm_cand)) / max(len(norm_target), len(norm_cand))
            if score > best_score:
                best_score = score
                best_match = candidate

    # Token overlap (e.g., "Manchester" matches "Man United" poorly, but we already have mappings)
    target_words = set(norm_target.split())
    for candidate in candidates:
        norm_cand = _normalise(candidate)
        cand_words = set(norm_cand.split())
        if target_words & cand_words:
            overlap = len(target_words & cand_words)
            score = overlap / max(len(target_words), len(cand_words))
            if score > best_score:
                best_score = score
                best_match = candidate

    # Require at least 30% similarity
    return best_match if best_score >= 0.3 else None


def parse_elo_csv(team_name: str) -> int:
    """Return the most recent ELO rating for a given team name.

    Lookup priority:
    1. Known name mapping (API name → Club-ELO name)
    2. Exact match (case-insensitive)
    3. Fuzzy match fallback
    """
    data = _load_elo_dict()
    if not data:
        return 1500

    # Step 1: Check known mapping
    mapped = _get_mapping(team_name)
    if mapped != team_name:
        for name, elo in data.items():
            if _normalise(name) == _normalise(mapped):
                return elo

    # Step 2: Exact match
    norm = _normalise(team_name)
    for name, elo in data.items():
        if _normalise(name) == norm:
            return elo

    # Step 3: Fuzzy match
    best = _fuzzy_match(team_name, list(data.keys()))
    if best:
        return data[best]

    return 1500


def get_team_elo(team_name: str) -> int:
    """Alias for parse_elo_csv with better name."""
    return parse_elo_csv(team_name)
