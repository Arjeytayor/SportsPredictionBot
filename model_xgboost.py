"""XGBoost football prediction model — second model alongside Poisson-ELO.

Runs on every football fixture; trainer can be called separately to build a
proper model from football-data.co.uk historicals. Until then, a feature-
based heuristic provides meaningful (& different) predictions to the Poisson.
"""

import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from config import BASE_DIR
from elo_loader import get_team_elo
from logger import logger

try:
    import xgboost as xgb

    _has_xgb = True
except ImportError:
    _has_xgb = False
    logger.warning("xgboost not installed — fallback heuristic only")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL_PATH = BASE_DIR / "data" / "xgboost_football.json"
FEATURE_ORDER = [
    "home_attack","home_defense","away_attack","away_defense",
    "home_form_gf","home_form_ga","away_form_gf","away_form_ga",
    "home_xg","away_xg","home_xg_against","away_xg_against",
    "home_win_rate","away_win_rate","elo_diff","h2h_win_rate",
    "league_tier",
]

_LEAGUE_TIER = {
    "Premier League": 1, "La Liga": 1, "Bundesliga": 1,
    "Serie A": 1, "Ligue 1": 1,
    "Primeira Liga": 2, "Eredivisie": 2,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _league_tier(league_name: str) -> int:
    for key, tier in _LEAGUE_TIER.items():
        if key.lower() in league_name.lower():
            return tier
    return 2


def _form_features(stats: List[Dict]) -> Tuple[float, float, float]:
    n = len(stats)
    recent = stats[-5:] if n >= 5 else stats
    if not recent:
        return 0.0, 0.0, 0.0
    gf = sum(m.get("goals_for", 0) for m in recent) / max(len(recent), 1)
    ga = sum(m.get("goals_against", 0) for m in recent) / max(len(recent), 1)
    wins = sum(1 for m in recent if m.get("goals_for", 0) > m.get("goals_against", 0))
    return gf, ga, wins / max(len(recent), 1)


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
def engineer_features(
    home_team: str,
    away_team: str,
    home_stats: List[Dict],
    away_stats: List[Dict],
    h2h_results: List[str] = None,
    league_name: str = "",
) -> Dict[str, float]:
    """Build feature dict from raw inputs."""
    h_recent = home_stats[-10:] if len(home_stats) >= 10 else home_stats
    a_recent = away_stats[-10:] if len(away_stats) >= 10 else away_stats

    hgf = sum(m.get("goals_for", 0) for m in h_recent) / max(len(h_recent), 1)
    hga = sum(m.get("goals_against", 0) for m in h_recent) / max(len(h_recent), 1)
    agf = sum(m.get("goals_for", 0) for m in a_recent) / max(len(a_recent), 1)
    aga = sum(m.get("goals_against", 0) for m in a_recent) / max(len(a_recent), 1)

    hfgf, hfga, hw = _form_features(home_stats)
    afgf, afga, aw = _form_features(away_stats)

    try:
        elo_d = get_team_elo(home_team) - get_team_elo(away_team)
    except Exception:
        elo_d = 0.0

    if h2h_results:
        hwins = sum(1 for r in h2h_results if r.upper() == "W")
        h2h_wr = hwins / max(len(h2h_results), 1)
    else:
        h2h_wr = 0.5

    # xG from Understat (if available in stats dicts)
    hxg = sum(m.get("xg_for", 0.0) for m in h_recent) / max(len(h_recent), 1)
    hxc = sum(m.get("xg_against", 0.0) for m in h_recent) / max(len(h_recent), 1)
    axg = sum(m.get("xg_for", 0.0) for m in a_recent) / max(len(a_recent), 1)
    axc = sum(m.get("xg_against", 0.0) for m in a_recent) / max(len(a_recent), 1)

    return {
        "home_attack": hgf, "home_defense": hga,
        "away_attack": agf, "away_defense": aga,
        "home_form_gf": hfgf, "home_form_ga": hfga,
        "away_form_gf": afgf, "away_form_ga": afga,
        "home_xg": hxg, "away_xg": axg,
        "home_xg_against": hxc, "away_xg_against": axc,
        "home_win_rate": hw, "away_win_rate": aw,
        "elo_diff": elo_d, "h2h_win_rate": h2h_wr,
        "league_tier": _league_tier(league_name),
    }


def _feature_vector(features: Dict[str, float]) -> List[float]:
    return [features[f] for f in FEATURE_ORDER]


# ---------------------------------------------------------------------------
# Fallback heuristic (different from Poisson)
# ---------------------------------------------------------------------------
def _fallback_predict(features: Dict[str, float]) -> Dict[str, float]:
    """Feature-weighted heuristic — intentionally different from Poisson!
    Uses ELO base with form adjustments rather than scoreline matrix."""
    elo_diff = features["elo_diff"]
    base_home = _sigmoid(elo_diff / 300.0)

    home_score = features["home_attack"] / max(features["away_defense"], 0.5)
    away_score = features["away_attack"] / max(features["home_defense"], 0.5)

    norm_home = home_score / (home_score + away_score + 1.0)
    norm_away = away_score / (home_score + away_score + 1.0)

    p_home = 0.5 * base_home + 0.5 * norm_home
    p_away = 0.5 * (1.0 - base_home) + 0.5 * norm_away

    h2h_adj = (features["h2h_win_rate"] - 0.5) * 0.2
    p_home += h2h_adj
    p_away -= h2h_adj

    balance = 1.0 - abs(p_home - p_away)
    p_draw = max(0.15, 0.25 * balance)

    total = p_home + p_draw + p_away
    if total > 0:
        p_home /= total
        p_draw /= total
        p_away /= total

    return {"home_win": p_home, "draw": p_draw, "away_win": p_away}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Booster cache -- the model file is ~665KB; deserialising it on every call made
# prediction ~150x slower than the Poisson model. Keyed on mtime so a retrain is
# picked up without restarting the process.
# ---------------------------------------------------------------------------
_booster = None
_booster_mtime: float = 0.0


def _get_booster():
    """Return the trained Booster, loading from disk only when it has changed."""
    global _booster, _booster_mtime
    mtime = MODEL_PATH.stat().st_mtime
    if _booster is None or mtime != _booster_mtime:
        booster = xgb.Booster()
        booster.load_model(str(MODEL_PATH))
        _booster, _booster_mtime = booster, mtime
        logger.info(f"Loaded XGBoost booster from {MODEL_PATH}")
    return _booster


def predict_xgboost(
    home_team: str,
    away_team: str,
    home_stats: List[Dict],
    away_stats: List[Dict],
    h2h_results: List[str] = None,
    league_name: str = "",
) -> Dict[str, float]:
    """Return XGBoost 1X2 probabilities (trained or heuristic fallback)."""
    features = engineer_features(
        home_team, away_team, home_stats, away_stats, h2h_results, league_name
    )

    if _has_xgb and MODEL_PATH.exists():
        try:
            model = _get_booster()
            vec = _feature_vector(features)
            dmatrix = xgb.DMatrix([vec])
            probs = model.predict(dmatrix)
            return {
                "home_win": float(probs[0][0]),
                "draw": float(probs[0][1]),
                "away_win": float(probs[0][2]),
                "source": "trained",
            }
        except Exception as exc:
            logger.warning(f"XGBoost trained model failed ({exc}), using fallback")

    result = _fallback_predict(features)
    result["source"] = "fallback"
    return result


# ---------------------------------------------------------------------------
# Training (call separately: python -c "from model_xgboost import train_xgboost_model; train_xgboost_model()")  # noqa: E501
# ---------------------------------------------------------------------------
def train_xgboost_model() -> bool:
    """Train XGBoost on football-data.co.uk CSVs using proper rolling features."""
    if not _has_xgb:
        logger.error("xgboost not installed")
        return False

    import urllib.request  # Import inside function only on train
    import pandas as pd

    historical_dir = BASE_DIR / "data" / "historical"
    historical_dir.mkdir(parents=True, exist_ok=True)

    # Download sample if missing
    sample = {"E0": "Premier League", "SP1": "La Liga", "D1": "Bundesliga"}
    season = "2425"
    for code in sample:
        url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
        dest = historical_dir / f"{code}.csv"
        if not dest.exists():
            try:
                urllib.request.urlretrieve(url, dest)
            except Exception:
                pass

    all_matches = []
    for csv_file in historical_dir.glob("*.csv"):
        try:
            df = pd.read_csv(csv_file, encoding="latin1", on_bad_lines="skip")
            for _, row in df.iterrows():
                fthg = row.get("FTHG")
                ftag = row.get("FTAG")
                if pd.isna(fthg) or pd.isna(ftag):
                    continue
                ht = str(row.get("HomeTeam", "")).strip()
                at = str(row.get("AwayTeam", "")).strip()
                if not ht or not at:
                    continue
                all_matches.append({
                    "home_team": ht, "away_team": at,
                    "fthg": float(fthg), "ftag": float(ftag),
                })
        except Exception as exc:
            logger.warning(f"Could not parse {csv_file}: {exc}")

    if len(all_matches) < 100:
        logger.warning(f"Only {len(all_matches)} rows")
        return False

    team_history = {}

    def _team_features(team_name):
        history = team_history.get(team_name, [])
        if not history:
            return {"avg_gf": 1.5, "avg_ga": 1.5, "win_rate": 0.5}
        last_5 = history[-5:]
        avg_gf = sum(m["goals_for"] for m in last_5) / len(last_5)
        avg_ga = sum(m["goals_against"] for m in last_5) / len(last_5)
        wins = sum(1 for m in last_5 if m["result"] == "W")
        return {"avg_gf": avg_gf, "avg_ga": avg_ga, "win_rate": wins / len(last_5)}

    rows, labels = [], []
    for match in all_matches:
        ht = match["home_team"]
        at = match["away_team"]

        home_state = _team_features(ht)
        away_state = _team_features(at)

        feat = {
            "home_attack": home_state["avg_gf"],
            "home_defense": home_state["avg_ga"],
            "away_attack": away_state["avg_gf"],
            "away_defense": away_state["avg_ga"],
            "home_form_gf": home_state["avg_gf"],
            "home_form_ga": home_state["avg_ga"],
            "away_form_gf": away_state["avg_gf"],
            "away_form_ga": away_state["avg_ga"],
            "home_xg": 0.0, "away_xg": 0.0,
            "home_xg_against": 0.0, "away_xg_against": 0.0,
            "home_win_rate": home_state["win_rate"],
            "away_win_rate": away_state["win_rate"],
            "elo_diff": 0.0,
            "h2h_win_rate": 0.5,
            "league_tier": 1,
        }
        rows.append(_feature_vector(feat))

        fthg, ftag = match["fthg"], match["ftag"]
        if fthg > ftag:
            labels.append(0)
        elif fthg == ftag:
            labels.append(1)
        else:
            labels.append(2)

        result_map = {0: "W", 1: "D", 2: "L"}
        team_history.setdefault(ht, []).append({
            "goals_for": fthg, "goals_against": ftag,
            "result": result_map[labels[-1]]
        })
        away_result = "W" if ftag > fthg else "D" if ftag == fthg else "L"
        team_history.setdefault(at, []).append({
            "goals_for": ftag, "goals_against": fthg,
            "result": away_result
        })

    if len(rows) < 100:
        logger.warning(f"Only {len(rows)} training rows - not enough")
        return False

    # Try to fetch xG from Understat for rolling features (best-effort, cached)
    try:
        from data_soccerdata import fetch_team_xg_form
    except ImportError:
        fetch_team_xg_form = None

    for i, match in enumerate(all_matches):
        ht = match["home_team"]
        at = match["away_team"]

        # Base xG values (will be overridden if Understat data available)
        hxg, hxc, axg, axc = 0.0, 0.0, 0.0, 0.0
        if fetch_team_xg_form:
            try:
                hxg_data = fetch_team_xg_form(ht, last_n=5)
                axg_data = fetch_team_xg_form(at, last_n=5)
                if hxg_data:
                    hxg_vals = [m.get("xg_for", 0.0) for m in hxg_data if m.get("xg_for") is not None]
                    hxc_vals = [m.get("xg_against", 0.0) for m in hxg_data if m.get("xg_against") is not None]
                    axg_vals = [m.get("xg_for", 0.0) for m in axg_data if m.get("xg_for") is not None]
                    axc_vals = [m.get("xg_against", 0.0) for m in axg_data if m.get("xg_against") is not None]
                    if hxg_vals:
                        hxg = sum(hxg_vals) / len(hxg_vals)
                    if hxc_vals:
                        hxc = sum(hxc_vals) / len(hxc_vals)
                    if axg_vals:
                        axg = sum(axg_vals) / len(axg_vals)
                    if axc_vals:
                        axc = sum(axc_vals) / len(axc_vals)
            except Exception:
                pass

        # Rebuild feature dict with xG
        feat = {
            "home_attack": rows[i][0], "home_defense": rows[i][1],
            "away_attack": rows[i][2], "away_defense": rows[i][3],
            "home_form_gf": rows[i][4], "home_form_ga": rows[i][5],
            "away_form_gf": rows[i][6], "away_form_ga": rows[i][7],
            "home_xg": hxg, "away_xg": axg,
            "home_xg_against": hxc, "away_xg_against": axc,
            "home_win_rate": rows[i][8], "away_win_rate": rows[i][9],
            "elo_diff": rows[i][10], "h2h_win_rate": rows[i][11],
            "league_tier": rows[i][12],
        }
        rows[i] = _feature_vector(feat)

    X = np.array(rows)
    y = np.array(labels)

    dtrain = xgb.DMatrix(X, label=y)
    params = {
        "objective": "multi:softprob",
        "num_class": 3,
        "max_depth": 5,
        "eta": 0.1,
        "eval_metric": "mlogloss",
        "seed": 42,
    }
    model = xgb.train(params, dtrain, num_boost_round=100)
    model.save_model(str(MODEL_PATH))
    logger.info(f"XGBoost model saved to {MODEL_PATH} with xG features")
    return True
