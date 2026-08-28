"""soccerdata wrapper — enriches team stats with xG and advanced metrics from Understat.

Fetches cached Understat data (xG, xGA, shots) per team to supplement the basic
goal data from API-Sports.  soccerdata caches downloads locally under
~/soccerdata/data/ so repeat runs are fast.
"""

from typing import Dict, List

from logger import logger

# Lazy import — soccerdata is heavy, only load when needed
_sd = None


def _load_sd():
    global _sd
    if _sd is None:
        import warnings
        warnings.filterwarnings("ignore")
        import soccerdata as _sd_mod
        _sd = _sd_mod
    return _sd


# Default season window for history pulls. Use soccerdata's unambiguous short
# form: "2122" == 2021-22. Plain "2021" is ambiguous and resolves to 2020-21,
# which silently skips a season.
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425"]

# Cache one schedule DataFrame per (league, seasons) so pulling 20 teams costs
# one download, not 20.
_schedule_cache: Dict[tuple, object] = {}


def _read_schedule(league_code: str, seasons: List[str]):
    """Return the Understat schedule for *seasons*, memoised per league+seasons."""
    key = (league_code, tuple(seasons))
    if key not in _schedule_cache:
        sd = _load_sd()
        _schedule_cache[key] = sd.Understat(league_code, list(seasons)).read_schedule()
    return _schedule_cache[key]


def fetch_team_xg_history(
    team_name: str,
    league_code: str = "ENG-Premier League",
    seasons: List[str] = None,
) -> List[Dict]:
    """Full chronological xG series for *team_name* across several seasons.

    Unlike fetch_team_xg_form (single season, last N), this returns every played
    match in date order -- long enough to be a usable time series rather than a
    38-point fragment.

    Returns:
        List of dicts ordered oldest-first with keys:
            date, goals_for, goals_against, xg_for, xg_against, opponent
        Empty list on failure.
    """
    seasons = seasons or DEFAULT_SEASONS
    try:
        sched = _read_schedule(league_code, seasons)
    except Exception as exc:
        logger.warning(f"soccerdata Understat history failed for {team_name}: {exc}")
        return []

    rows = []
    for _, row in sched.iterrows():
        home, away = row.get("home_team", ""), row.get("away_team", "")
        if team_name not in (home, away):
            continue
        if not row.get("is_result"):
            continue

        is_home = home == team_name
        gf = row["home_goals"] if is_home else row["away_goals"]
        ga = row["away_goals"] if is_home else row["home_goals"]
        xgf = row.get("home_xg") if is_home else row.get("away_xg")
        xga = row.get("away_xg") if is_home else row.get("home_xg")

        rows.append({
            "date": row.get("date"),
            "goals_for": int(gf) if gf == gf else None,
            "goals_against": int(ga) if ga == ga else None,
            "xg_for": float(xgf) if xgf == xgf else None,
            "xg_against": float(xga) if xga == xga else None,
            "opponent": away if is_home else home,
        })

    rows.sort(key=lambda r: r["date"])
    return rows


# ---------------------------------------------------------------------------
# Understat xG form (supplements build_team_stats_from_form)
# ---------------------------------------------------------------------------
def fetch_team_xg_form(
    team_name: str,
    league_code: str = "ENG-Premier League",
    season: str = "2024",
    last_n: int = 5,
) -> List[Dict]:
    """Fetch last N matches xG form for a team from Understat via soccerdata.

    Returns:
        List of dicts with keys:
            goals_for, goals_against, xg_for, xg_against, opponent
        Empty list if not found.
    """
    try:
        sd = _load_sd()
        under = sd.Understat(league_code, season)
        sched = under.read_schedule()
    except Exception as exc:
        logger.warning(f"soccerdata Understat fetch failed for {team_name}: {exc}")
        return []

    # Filter to matches involving this team
    team_matches = []
    for _, row in sched.iterrows():
        home = row.get("home_team", "")
        away = row.get("away_team", "")
        if team_name not in (home, away):
            continue

        # Check if result exists
        if not row.get("is_result"):
            continue

        is_home = home == team_name
        gf = row["home_goals"] if is_home else row["away_goals"]
        ga = row["away_goals"] if is_home else row["home_goals"]
        xgf = row.get("home_xg") if is_home else row.get("away_xg")
        xga = row.get("away_xg") if is_home else row.get("home_xg")

        team_matches.append({
            "goals_for": int(gf) if gf == gf else None,
            "goals_against": int(ga) if ga == ga else None,
            "xg_for": float(xgf) if xgf == xgf else None,
            "xg_against": float(xga) if xga == xga else None,
            "opponent": away if is_home else home,
        })

    # Return last N (already sorted by date in Understat schedule)
    return team_matches[-last_n:] if len(team_matches) >= last_n else team_matches


# ---------------------------------------------------------------------------
# Format for the bot
# ---------------------------------------------------------------------------
def build_team_stats_with_xg(
    team_id: int,
    raw_fixtures: List[Dict],
    team_name: str = "",
    use_understat: bool = True,
) -> List[Dict]:
    """Enhanced build_team_stats that adds xG when available.

    Args:
        team_id: API-Sports team ID
        raw_fixtures: fixtures from fetch_football_team_form()
        team_name: Name for soccerdata lookup
        use_understat: Try to fetch xG data from Understat

    Returns:
        List of stat dicts with keys: goals_for, goals_against,
        xg_for, xg_against (xG keys added only if found).
    """
    stats = []
    for match in raw_fixtures:
        # Build from raw fixtures exactly like build_team_stats_from_form does
        teams = match.get("teams", {})
        goals = match.get("goals", {})
        if not teams or not goals:
            continue

        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        home_goals = goals.get("home", 0) or 0
        away_goals = goals.get("away", 0) or 0

        if home_id == team_id:
            stats.append({
                "goals_for": int(home_goals),
                "goals_against": int(away_goals),
            })
        elif away_id == team_id:
            stats.append({
                "goals_for": int(away_goals),
                "goals_against": int(home_goals),
            })

    # Try to add xG from Understat
    xg_rows = []
    if use_understat and team_name:
        try:
            xg_rows = fetch_team_xg_form(team_name, last_n=len(stats))
        except Exception:
            pass

    # Merge xG into stats (best-effort: match by position)
    if xg_rows and len(xg_rows) == len(stats):
        for i, xg in enumerate(xg_rows):
            if xg.get("xg_for") is not None:
                stats[i]["xg_for"] = xg["xg_for"]
            if xg.get("xg_against") is not None:
                stats[i]["xg_against"] = xg["xg_against"]

    return stats