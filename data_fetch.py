"""Data fetching module for the Sports Prediction Bot.

Handles all API-Sports calls, caching, and request budget management.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import (
    API_SPORTS_KEY,
    API_SPORTS_BASE,
    API_BASKETBALL_BASE,
    API_VOLLEYBALL_BASE,
    API_MMA_BASE,
    BALLDONTLIE_BASE,
    CACHE_DIR,
    DAILY_REQUEST_LIMIT,
    BUDGET_WARNING_THRESHOLD,
    increment_request,
    get_request_count,
)
from logger import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CACHE_TTL_FIXTURES = 1  # days
CACHE_TTL_STANDINGS = 1
CACHE_TTL_H2H = 1
CACHE_TTL_ODDS = 1
CACHE_TTL_ELO = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _cache_key(sport: str, endpoint: str, **kwargs) -> str:
    """Build a cache filename from sport, endpoint and query params."""
    today = datetime.now().strftime("%Y-%m-%d")
    parts = [sport, endpoint, today]
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}_{v}")
    key = "_".join(parts); key = key.replace("/", "_"); return key + ".json"


def _cache_path(sport: str, endpoint: str, **kwargs) -> Path:
    return CACHE_DIR / _cache_key(sport, endpoint, **kwargs)


def _is_cache_valid(path: Path, ttl_days: int = 1) -> bool:
    if not path.exists():
        return False
    age = (datetime.now().timestamp() - path.stat().st_mtime) / 86400
    return age < ttl_days


def _check_budget(sport: str) -> bool:
    """Return True if we still have budget for this sport."""
    today = datetime.now().strftime("%Y-%m-%d")
    counts = get_request_count(today)
    current = counts.get(sport, 0)
    if current >= DAILY_REQUEST_LIMIT:
        logger.warning(f"Daily request limit reached for {sport}")
        return False
    if current >= BUDGET_WARNING_THRESHOLD:
        logger.warning(f"Budget warning: {current}/{DAILY_REQUEST_LIMIT} requests used for {sport}")
    return True


# ---------------------------------------------------------------------------
# Core fetcher
# ---------------------------------------------------------------------------
def _api_get(sport: str, base_url: str, endpoint: str, params: Dict[str, Any] = None, headers: Dict[str, str] = None) -> Optional[Dict]:
    """Make an API GET request with caching and budget tracking."""
    today = datetime.now().strftime("%Y-%m-%d")
    cache_file = _cache_path(sport, endpoint, **(params or {}))

    # Budget check
    if not _check_budget(sport):
        return None

    try:
        url = f"{base_url}/{endpoint.lstrip('/')}"
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        # Cache response
        with open(cache_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

        increment_request(sport, today)
        return data
    except requests.exceptions.RequestException as exc:
        logger.error(f"API request failed for {sport} {endpoint}: {exc}", exc_info=True)
        return None
    except Exception as exc:
        logger.error(f"Unexpected error in {sport} {endpoint}: {exc}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Football (API-Sports)
# ---------------------------------------------------------------------------
def fetch_football_fixtures(date_str: str) -> List[Dict]:
    """Fetch fixtures for a given date (YYYY-MM-DD)."""
    cache_file = _cache_path("football", "fixtures", date=date_str)
    if _is_cache_valid(cache_file, CACHE_TTL_FIXTURES):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh).get("response", [])

    headers = {"x-apisports-key": API_SPORTS_KEY}
    data = _api_get("football", API_SPORTS_BASE, "fixtures", params={"date": date_str}, headers=headers)
    return data.get("response", []) if data else []


def fetch_football_standings(league_id: int, season: int) -> List[Dict]:
    cache_file = _cache_path("football", "standings", league=league_id, season=season)
    if _is_cache_valid(cache_file, CACHE_TTL_STANDINGS):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh).get("response", [])

    headers = {"x-apisports-key": API_SPORTS_KEY}
    data = _api_get("football", API_SPORTS_BASE, "standings", params={"league": league_id, "season": season}, headers=headers)
    return data.get("response", []) if data else []


def fetch_football_h2h(team1_id: int, team2_id: int) -> List[Dict]:
    cache_file = _cache_path("football", "h2h", t1=team1_id, t2=team2_id)
    if _is_cache_valid(cache_file, CACHE_TTL_H2H):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh).get("response", [])

    headers = {"x-apisports-key": API_SPORTS_KEY}
    data = _api_get("football", API_SPORTS_BASE, "fixtures/headtohead", params={"h2h": f"{team1_id}-{team2_id}"}, headers=headers)
    return data.get("response", []) if data else []


def fetch_football_odds(fixture_id: int) -> List[Dict]:
    cache_file = _cache_path("football", "odds", fixture=fixture_id)
    if _is_cache_valid(cache_file, CACHE_TTL_ODDS):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh).get("response", [])

    headers = {"x-apisports-key": API_SPORTS_KEY}
    data = _api_get("football", API_SPORTS_BASE, "odds", params={"fixture": fixture_id}, headers=headers)
    return data.get("response", []) if data else []


def fetch_football_statistics(fixture_id: int) -> Dict:
    cache_file = _cache_path("football", "statistics", fixture=fixture_id)
    if _is_cache_valid(cache_file, CACHE_TTL_FIXTURES):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh)

    headers = {"x-apisports-key": API_SPORTS_KEY}
    data = _api_get("football", API_SPORTS_BASE, "fixtures/statistics", params={"fixture": fixture_id}, headers=headers)
    return data if data else {}


def fetch_football_lineups(fixture_id: int) -> List[Dict]:
    """Fetch confirmed lineups — always bypass cache for fresh data.

    Uses a direct HTTP request instead of _api_get to avoid writing
    to the on-disk cache so lineup data is always current.
    """
    headers = {"x-apisports-key": API_SPORTS_KEY}
    url = f"{API_SPORTS_BASE}/fixtures/lineups"
    try:
        response = requests.get(url, params={"fixture": fixture_id}, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("response", [])
    except requests.exceptions.RequestException as exc:
        logger.error(f"API request failed for lineups fixture {fixture_id}: {exc}", exc_info=True)
        return []
    except Exception as exc:
        logger.error(f"Unexpected error fetching lineups for {fixture_id}: {exc}", exc_info=True)
        return []


def fetch_football_team_form(team_id: int, season: int, last_n: int = 10) -> List[Dict]:
    """Fetch last N matches for a team to build attack/defence stats.

    Args:
        team_id: API-Sports team ID.
        season: Season year.
        last_n: Number of recent matches to fetch.

    Returns:
        List of fixture dicts from the API response.
    """
    cache_file = _cache_path("football", "team_form", team=team_id, season=season, last=last_n)
    if _is_cache_valid(cache_file, CACHE_TTL_FIXTURES):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh).get("response", [])

    headers = {"x-apisports-key": API_SPORTS_KEY}
    data = _api_get("football", API_SPORTS_BASE, "fixtures",
                    params={"team": team_id, "last": last_n, "season": season}, headers=headers)
    return data.get("response", []) if data else []


def build_team_stats_from_form(team_id: int, fixtures: List[Dict]) -> List[Dict]:
    """Convert API fixture list to attack/defence stats dicts for the model.

    Args:
        team_id: The team whose stats we want.
        fixtures: Raw fixture list from the API (e.g. from fetch_football_team_form).

    Returns:
        List of dicts with keys 'goals_for' and 'goals_against'.
    """
    stats = []
    for match in fixtures:
        teams = match.get("teams", {})
        goals = match.get("goals", {})
        if not teams or not goals:
            continue

        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        home_goals = goals.get("home", 0) or 0
        away_goals = goals.get("away", 0) or 0

        if home_id == team_id:
            stats.append({"goals_for": int(home_goals), "goals_against": int(away_goals)})
        elif away_id == team_id:
            stats.append({"goals_for": int(away_goals), "goals_against": int(home_goals)})

    return stats


# ---------------------------------------------------------------------------
# Basketball (balldontlie.io + API-Sports)
# ---------------------------------------------------------------------------
def fetch_basketball_games(date_str: str) -> List[Dict]:
    cache_file = _cache_path("basketball", "games", date=date_str)
    if _is_cache_valid(cache_file, CACHE_TTL_FIXTURES):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh).get("data", [])

    try:
        response = requests.get(f"{BALLDONTLIE_BASE}/games", params={"start_date": date_str, "end_date": date_str}, timeout=30)
        response.raise_for_status()
        data = response.json()
        with open(cache_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        increment_request("basketball", datetime.now().strftime("%Y-%m-%d"))
        return data.get("data", [])
    except Exception as exc:
        logger.error(f"Failed to fetch basketball games: {exc}", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Volleyball (API-Sports)
# ---------------------------------------------------------------------------
def fetch_volleyball_fixtures(date_str: str) -> List[Dict]:
    cache_file = _cache_path("volleyball", "fixtures", date=date_str)
    if _is_cache_valid(cache_file, CACHE_TTL_FIXTURES):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh).get("response", [])

    headers = {"x-apisports-key": API_SPORTS_KEY}
    data = _api_get("volleyball", API_VOLLEYBALL_BASE, "games", params={"date": date_str}, headers=headers)
    return data.get("response", []) if data else []


# ---------------------------------------------------------------------------
# MMA (API-Sports)
# ---------------------------------------------------------------------------
def fetch_mma_fights(date_str: str) -> List[Dict]:
    cache_file = _cache_path("mma", "fights", date=date_str)
    if _is_cache_valid(cache_file, CACHE_TTL_FIXTURES):
        with open(cache_file, "r", encoding="utf-8") as fh:
            return json.load(fh).get("response", [])

    headers = {"x-apisports-key": API_SPORTS_KEY}
    data = _api_get("mma", API_MMA_BASE, "fights", params={"date": date_str}, headers=headers)
    return data.get("response", []) if data else []
