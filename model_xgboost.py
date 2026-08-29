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
    elo_diff: float = None,
) -> Dict[str, float]:
    """Build feature dict from raw inputs.

    *elo_diff* lets a caller supply a point-in-time rating difference. Training
    must pass one: get_team_elo() returns TODAY's Club-ELO, so letting it fill
    this in would leak a team's future strength into its 2021 rows.
    """
    h_recent = home_stats[-10:] if len(home_stats) >= 10 else home_stats
    a_recent = away_stats[-10:] if len(away_stats) >= 10 else away_stats

    hgf = sum(m.get("goals_for", 0) for m in h_recent) / max(len(h_recent), 1)
    hga = sum(m.get("goals_against", 0) for m in h_recent) / max(len(h_recent), 1)
    agf = sum(m.get("goals_for", 0) for m in a_recent) / max(len(a_recent), 1)
    aga = sum(m.get("goals_against", 0) for m in a_recent) / max(len(a_recent), 1)

    hfgf, hfga, hw = _form_features(home_stats)
    afgf, afga, aw = _form_features(away_stats)

    if elo_diff is not None:
        elo_d = float(elo_diff)
    else:
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
# Understat only covers the big five. Every other league trains with xG at
# 0.0, recorded honestly rather than back-filled with a league average.
_UNDERSTAT_LEAGUES = {
    "premier_league": "ENG-Premier League",
    "la_liga": "ESP-La Liga",
    "serie_a": "ITA-Serie A",
    "bundesliga": "GER-Bundesliga",
    "ligue_1": "FRA-Ligue 1",
}

# Elo result encoding used by penaltyblog: 0 home win, 1 draw, 2 away win.
_ELO_RESULT = {0: 0, 1: 1, 2: 2}


def _xg_by_date(league_key: str, teams) -> Dict[str, Dict]:
    """Per-team {date: (xg_for, xg_against)} from Understat, for point-in-time joins.

    Keyed on date because a team plays at most once a day, which sidesteps the
    Understat-vs-football-data team naming differences for the opponent field.
    """
    code = _UNDERSTAT_LEAGUES.get(league_key)
    if not code:
        return {}
    try:
        from data_soccerdata import fetch_team_xg_history
    except ImportError:
        return {}

    out: Dict[str, Dict] = {}
    for team in teams:
        try:
            rows = fetch_team_xg_history(team, league_code=code)
        except Exception:
            continue
        if not rows:
            continue
        by_date = {}
        for r in rows:
            d = r.get("date")
            if d is None:
                continue
            key = d.date() if hasattr(d, "date") else d
            by_date[key] = (r.get("xg_for"), r.get("xg_against"))
        if by_date:
            out[team] = by_date
    return out


def build_training_samples(use_xg: bool = True) -> List:
    """Walk every league chronologically and emit (date, feature_vector, label).

    Extracted so training and evaluation share one implementation -- the
    original bug in this module came from the trainer reimplementing feature
    logic that then drifted from the serving path.
    """
    import pandas as pd

    from odds_loader import LEAGUE_FILES, load_historical_csv

    try:
        from penaltyblog.ratings import Elo
    except ImportError:
        logger.error("penaltyblog required for point-in-time Elo.")
        return []

    from backtest import _LEAGUE_DISPLAY_NAMES

    samples = []
    xg_hits = xg_total = 0

    for league_key in LEAGUE_FILES:
        df = load_historical_csv(league_key)
        if df is None or df.empty:
            continue
        df = df.copy()
        df["_d"] = pd.to_datetime(df.get("Date"), dayfirst=True, errors="coerce")
        df = df.sort_values("_d")

        league_display = _LEAGUE_DISPLAY_NAMES.get(
            league_key, league_key.replace("_", " ").title()
        )
        teams = set(df["HomeTeam"].dropna().astype(str).str.strip())
        xg_map = _xg_by_date(league_key, teams) if use_xg else {}

        elo = Elo()
        history: Dict[str, List[Dict]] = {}
        h2h: Dict[tuple, List[str]] = {}

        for _, row in df.iterrows():
            fthg, ftag = row.get("FTHG"), row.get("FTAG")
            home = str(row.get("HomeTeam", "")).strip()
            away = str(row.get("AwayTeam", "")).strip()
            if pd.isna(fthg) or pd.isna(ftag) or not home or not away:
                continue

            hs, as_ = history.get(home, []), history.get(away, [])
            if len(hs) >= 5 and len(as_) >= 5:
                elo_d = elo.get_team_rating(home) - elo.get_team_rating(away)
                feat = engineer_features(
                    home, away, hs, as_,
                    h2h_results=h2h.get((home, away)),
                    league_name=league_display,
                    elo_diff=elo_d,
                )
                fthg_i, ftag_i = int(fthg), int(ftag)
                label = 0 if fthg_i > ftag_i else (1 if fthg_i == ftag_i else 2)
                samples.append((row["_d"], _feature_vector(feat), label))

            # ---- everything below updates state AFTER the row is emitted ----
            fthg_f, ftag_f = float(fthg), float(ftag)
            mdate = row["_d"].date() if pd.notna(row["_d"]) else None

            for team, gf, ga in ((home, fthg_f, ftag_f), (away, ftag_f, fthg_f)):
                entry = {"goals_for": gf, "goals_against": ga}
                xg_total += 1
                pair = xg_map.get(team, {}).get(mdate)
                if pair and pair[0] is not None:
                    entry["xg_for"], entry["xg_against"] = float(pair[0]), float(pair[1] or 0.0)
                    xg_hits += 1
                history.setdefault(team, []).append(entry)

            outcome = 0 if fthg_f > ftag_f else (1 if fthg_f == ftag_f else 2)
            elo.update_ratings(home, away, _ELO_RESULT[outcome])
            h2h.setdefault((home, away), []).append(
                "W" if outcome == 0 else ("D" if outcome == 1 else "L")
            )

    samples.sort(key=lambda s: s[0])
    logger.info(
        f"Built {len(samples)} samples; xG coverage "
        f"{(xg_hits / xg_total * 100) if xg_total else 0.0:.1f}%."
    )
    return samples


def train_xgboost_model(test_fraction: float = 0.2, use_xg: bool = True) -> bool:
    """Train XGBoost walk-forward across every league CSV, with a time-ordered holdout.

    Features are produced by engineer_features -- the same function the live
    prediction path calls -- so training and serving cannot drift apart. Every
    input is built only from matches strictly before the one being labelled:

      * rolling form comes from history appended AFTER each match is recorded
      * elo_diff is an incremental Elo, not today's Club-ELO rating
      * xG is joined by match date, not "this team's most recent five games"

    The previous implementation got all three of those wrong, and an index
    mismatch when it rebuilt the feature vector zeroed both win-rate features
    and wrote home_win_rate into the league_tier slot.
    """
    if not _has_xgb:
        logger.error("xgboost not installed")
        return False

    import numpy as _np

    samples = build_training_samples(use_xg=use_xg)

    if len(samples) < 1000:
        logger.error(f"Only {len(samples)} training rows -- aborting.")
        return False

    split = int(len(samples) * (1.0 - test_fraction))
    train, test = samples[:split], samples[split:]

    X_tr = _np.array([s[1] for s in train]); y_tr = _np.array([s[2] for s in train])
    X_te = _np.array([s[1] for s in test]);  y_te = _np.array([s[2] for s in test])

    params = {
        "objective": "multi:softprob", "num_class": 3,
        "max_depth": 5, "eta": 0.1, "eval_metric": "mlogloss", "seed": 42,
    }
    dtrain = xgb.DMatrix(X_tr, label=y_tr)
    dtest = xgb.DMatrix(X_te, label=y_te)
    model = xgb.train(
        params, dtrain, num_boost_round=400,
        evals=[(dtrain, "train"), (dtest, "holdout")],
        early_stopping_rounds=25, verbose_eval=False,
    )

    probs = model.predict(dtest, iteration_range=(0, model.best_iteration + 1))
    acc = float((probs.argmax(axis=1) == y_te).mean() * 100)

    # Holdout RPS is the number comparable to the other models in backtest.py;
    # holdout accuracy on its own hides calibration.
    rps = None
    try:
        from penaltyblog.metrics import rps_average
        rps = float(rps_average(probs.tolist(), y_te.tolist()))
    except ImportError:
        pass

    logger.info(
        f"Trained on {len(train)} rows, held out {len(test)} "
        f"(chronological split at {train[-1][0].date()}). "
        f"Holdout accuracy {acc:.2f}%"
        + (f", holdout RPS {rps:.4f}" if rps is not None else "")
        + f", best_iter={model.best_iteration}."
    )

    model.save_model(str(MODEL_PATH))
    logger.info(f"XGBoost model saved to {MODEL_PATH}")
    return True
