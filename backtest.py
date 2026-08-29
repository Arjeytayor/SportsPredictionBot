"""Backtesting module — walks each league's real match history chronologically
and scores the actual production models (Poisson + ELO, XGBoost) against real
outcomes, using flat-stake ROI vs Pinnacle closing odds (PSH, PSD, PSA columns).

For each match, a team's rolling form (last N results) is read BEFORE the
match is scored, and only updated with the real result AFTER scoring — so no
match ever contributes to its own prediction (no lookahead).

Usage: python backtest.py
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from config import LOGS_DIR
from odds_loader import LEAGUE_FILES, load_historical_csv
from model_football import predict_football
from model_xgboost import predict_xgboost
from logger import logger

try:
    from penaltyblog.ratings import PiRatingSystem
    _has_pi = True
except ImportError:
    _has_pi = False

try:
    from penaltyblog.metrics import rps_average
    _has_rps = True
except ImportError:  # penaltyblog optional
    _has_rps = False

try:
    from penaltyblog.models import DixonColesGoalModel, dixon_coles_weights
    _has_dc = True
except ImportError:
    _has_dc = False

# A uniform 1/3-1/3-1/3 forecast scores RPS 0.2778. Any model scoring worse
# than that is worse than admitting it does not know.
RPS_UNIFORM = 0.2778

class _NotPriceable(Exception):
    """Raised when a model legitimately has no opinion on a match."""


MIN_HISTORY_MATCHES = 3  # skip scoring until a team has some real rolling form

# --- Dixon-Coles tuning ------------------------------------------------
# DixonColesGoalModel is a batch maximum-likelihood solver, not an incremental
# updater like Pi ratings, so it has to be refitted as history grows. Measured
# fit cost is 0.10-0.36s and flat in history length -- it scales with team
# count, not row count -- so refitting on every match would cost ~84 min across
# all 15 leagues. Refitting every DC_REFIT_EVERY matches costs ~8 min for at
# most one matchweek of staleness, well below the noise we are measuring.
DC_REFIT_EVERY = 10

# The solver needs each team to appear several times before its attack and
# defence parameters are identifiable -- roughly half a league-season.
DC_MIN_FIT_MATCHES = 200

# Exponential time decay (Dixon & Coles 1997). At xi=0.0018 a match five
# seasons old carries ~4% of the weight of one played last week.
DC_XI = 0.0018

# XGBoost is trained on everything before this date, so its numbers over the
# full sample are ~80% in-sample and not comparable with the walk-forward
# models. Every model is therefore ALSO scored on this window alone, where all
# four are genuinely out-of-sample.
XGB_HOLDOUT_START = pd.Timestamp("2025-08-16")

_LEAGUE_DISPLAY_NAMES = {
    "premier_league": "Premier League",
    "la_liga": "La Liga",
    "bundesliga": "Bundesliga",
    "serie_a": "Serie A",
    "ligue_1": "Ligue 1",
}


def _update_history(team_history: Dict[str, List[Dict]], team: str, goals_for: float, goals_against: float) -> None:
    team_history.setdefault(team, []).append({"goals_for": goals_for, "goals_against": goals_against})


class _DixonColesFitter:
    """Walk-forward wrapper around penaltyblog's batch Dixon-Coles solver.

    Holds only matches that have already been scored, so a match can never
    inform its own prediction, and refits on a cadence instead of per match.
    """

    def __init__(self) -> None:
        self._goals_home: List[int] = []
        self._goals_away: List[int] = []
        self._teams_home: List[str] = []
        self._teams_away: List[str] = []
        self._dates: List[Any] = []
        self._model = None
        self._fitted_teams: set = set()
        self._since_refit = 0

    def add(self, home: str, away: str, goals_home: int, goals_away: int, date: Any) -> None:
        """Record a played match. Called only AFTER that match has been scored."""
        self._teams_home.append(home)
        self._teams_away.append(away)
        self._goals_home.append(goals_home)
        self._goals_away.append(goals_away)
        self._dates.append(date)
        self._since_refit += 1

    def _refit(self, base_date: Any) -> None:
        weights = None
        dates = pd.Series(self._dates)
        if not dates.isna().any():
            # Decay is measured back from the match being predicted, not from
            # the end of the file -- using the latter would leak the future.
            weights = dixon_coles_weights(dates, xi=DC_XI, base_date=base_date)
        model = DixonColesGoalModel(
            self._goals_home, self._goals_away,
            self._teams_home, self._teams_away,
            weights=weights,
        )
        model.fit()
        self._model = model
        self._fitted_teams = set(self._teams_home) | set(self._teams_away)
        self._since_refit = 0

    def predict(self, home: str, away: str, date: Any):
        """Return H/D/A probabilities, or None if the model cannot price this match."""
        if len(self._goals_home) < DC_MIN_FIT_MATCHES:
            return None
        if self._model is None or self._since_refit >= DC_REFIT_EVERY:
            self._refit(date)
        # A team promoted into this league has no fitted parameters yet.
        if home not in self._fitted_teams or away not in self._fitted_teams:
            return None
        home_p, draw_p, away_p = self._model.predict(home, away).home_draw_away
        return {"home_win": float(home_p), "draw": float(draw_p), "away_win": float(away_p)}


def _run_model_backtest(model_key: str, df: pd.DataFrame, league_key: str, league_display: str) -> Dict[str, Any]:
    """Walk one league's matches chronologically, scoring one model."""
    team_history: Dict[str, List[Dict]] = {}
    pi = PiRatingSystem() if (model_key == "pi_ratings" and _has_pi) else None
    dc = _DixonColesFitter() if (model_key == "dixon_coles" and _has_dc) else None
    prob_rows: List[List[float]] = []
    outcomes: List[int] = []
    # Which matches this model actually priced, so the models can be compared
    # on an identical sample rather than on whatever each one happened to cover.
    scored_keys: List[Any] = []
    scored_dates: List[Any] = []
    wins = losses = 0
    stakes = 0.0
    returns = 0.0

    for idx, row in df.iterrows():
        fthg, ftag, ftr = row.get("FTHG"), row.get("FTAG"), row.get("FTR")
        home_team = str(row.get("HomeTeam", "")).strip()
        away_team = str(row.get("AwayTeam", "")).strip()
        if pd.isna(fthg) or pd.isna(ftag) or not home_team or not away_team:
            continue

        home_stats = team_history.get(home_team, [])
        away_stats = team_history.get(away_team, [])

        if len(home_stats) >= MIN_HISTORY_MATCHES and len(away_stats) >= MIN_HISTORY_MATCHES:
            try:
                if model_key == "pi_ratings":
                    result = pi.calculate_match_probabilities(home_team, away_team)
                elif model_key == "dixon_coles":
                    result = dc.predict(home_team, away_team, row.get("_parsed_date"))
                elif model_key == "xgboost":
                    result = predict_xgboost(
                        home_team, away_team, home_stats, away_stats,
                        h2h_results=None, league_name=league_display,
                    )
                else:
                    result = predict_football(home_team, away_team, home_stats, away_stats)

                if result is None:
                    raise _NotPriceable
                probs = {"H": result["home_win"], "D": result.get("draw", 0.0), "A": result.get("away_win", 0.0)}
                pick = max(probs, key=probs.get)

                psh, psd, psa = row.get("PSH", 0), row.get("PSD", 0), row.get("PSA", 0)
                odds = {"H": psh, "D": psd, "A": psa}.get(pick, 0)
                actual = str(ftr).strip().upper()

                if odds and odds > 0:
                    stakes += 1.0
                    if pick == actual:
                        returns += odds

                if pick == actual:
                    wins += 1
                else:
                    losses += 1

                # RPS needs a proper distribution; the models do not always
                # normalise, so rescale before scoring.
                if actual in ("H", "D", "A"):
                    total_p = probs["H"] + probs["D"] + probs["A"]
                    if total_p > 0:
                        prob_rows.append([probs["H"] / total_p,
                                          probs["D"] / total_p,
                                          probs["A"] / total_p])
                        outcomes.append({"H": 0, "D": 1, "A": 2}[actual])
                        scored_keys.append(idx)
                        scored_dates.append(row.get("_parsed_date"))
            except _NotPriceable:
                pass  # model has no opinion yet -- not an error, just no pick
            except Exception as exc:
                logger.error(f"Backtest error [{model_key}] {home_team} v {away_team}: {exc}", exc_info=True)

        # Update rolling history AFTER scoring, using the real result —
        # this match must never be visible to its own prediction.
        _update_history(team_history, home_team, float(fthg), float(ftag))
        _update_history(team_history, away_team, float(ftag), float(fthg))
        if pi is not None:
            pi.update_ratings(home_team, away_team, int(fthg) - int(ftag))
        if dc is not None:
            dc.add(home_team, away_team, int(fthg), int(ftag), row.get("_parsed_date"))

    total = wins + losses
    rps = float(rps_average(prob_rows, outcomes)) if (_has_rps and prob_rows) else None
    return {
        "league": league_key,
        "rps": rps,
        "rps_n": len(prob_rows),
        "_scored_keys": scored_keys,
        "_scored_dates": scored_dates,
        "_prob_rows": prob_rows,
        "_outcomes": outcomes,
        "wins": wins,
        "losses": losses,
        "total_picks": total,
        "accuracy": (wins / total * 100) if total else 0.0,
        "roi": ((returns - stakes) / stakes * 100) if stakes > 0 else 0.0,
        "stakes": stakes,
        "returns": returns,
    }


def run_backtest() -> Dict[str, Any]:
    """Backtest both production models (Poisson-ELO, XGBoost) chronologically,
    per league, against real historical results."""
    models = ["poisson_elo", "xgboost"]
    if _has_pi:
        models.append("pi_ratings")
    if _has_dc:
        models.append("dixon_coles")
    per_model_leagues: Dict[str, List[Dict]] = {m: [] for m in models}

    for key in LEAGUE_FILES:
        df = load_historical_csv(key)
        if df is None or df.empty:
            continue

        if "Date" in df.columns:
            df = df.copy()
            df["_parsed_date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
            df = df.sort_values("_parsed_date")

        league_display = _LEAGUE_DISPLAY_NAMES.get(key, key.replace("_", " ").title())

        league_stats = {m: _run_model_backtest(m, df, key, league_display) for m in models}

        # Models disagree on which matches they can price at all: Dixon-Coles
        # needs a league-wide burn-in, the others only need per-team form. RPS
        # computed over different samples is not comparable, so score every
        # model a second time over the matches ALL of them priced.
        common = set.intersection(*(set(st["_scored_keys"]) for st in league_stats.values()))             if league_stats else set()
        for stats in league_stats.values():
            pairs = [(p, o) for k, p, o in
                     zip(stats["_scored_keys"], stats["_prob_rows"], stats["_outcomes"])
                     if k in common]
            hold = [(p, o) for k, d, p, o in
                    zip(stats["_scored_keys"], stats["_scored_dates"],
                        stats["_prob_rows"], stats["_outcomes"])
                    if k in common and d is not None and d >= XGB_HOLDOUT_START]
            stats["rps_holdout_n"] = len(hold)
            stats["rps_holdout"] = (
                float(rps_average([p for p, _ in hold], [o for _, o in hold]))
                if (_has_rps and hold) else None
            )
            stats["rps_common_n"] = len(pairs)
            stats["rps_common"] = (
                float(rps_average([p for p, _ in pairs], [o for _, o in pairs]))
                if (_has_rps and pairs) else None
            )
            for tmp in ("_scored_keys", "_scored_dates", "_prob_rows", "_outcomes"):
                stats.pop(tmp, None)

        for model_key, stats in league_stats.items():
            if stats["total_picks"] > 0:
                per_model_leagues[model_key].append(stats)

    summary = {}
    for model_key, per_league in per_model_leagues.items():
        total_wins = sum(r["wins"] for r in per_league)
        total_losses = sum(r["losses"] for r in per_league)
        total_picks = total_wins + total_losses
        total_stakes = sum(r["stakes"] for r in per_league)
        total_returns = sum(r["returns"] for r in per_league)
        rps_n = sum(r["rps_n"] for r in per_league if r.get("rps") is not None)
        overall_rps = (
            sum(r["rps"] * r["rps_n"] for r in per_league if r.get("rps") is not None) / rps_n
            if rps_n else None
        )
        common_n = sum(r.get("rps_common_n", 0) for r in per_league if r.get("rps_common") is not None)
        overall_common = (
            sum(r["rps_common"] * r["rps_common_n"] for r in per_league if r.get("rps_common") is not None) / common_n
            if common_n else None
        )
        hold_n = sum(r.get("rps_holdout_n", 0) for r in per_league if r.get("rps_holdout") is not None)
        overall_hold = (
            sum(r["rps_holdout"] * r["rps_holdout_n"] for r in per_league if r.get("rps_holdout") is not None) / hold_n
            if hold_n else None
        )
        summary[model_key] = {
            "rps": overall_rps,
            "rps_holdout": overall_hold,
            "rps_holdout_n": hold_n,
            "rps_common": overall_common,
            "rps_common_n": common_n,
            "wins": total_wins,
            "losses": total_losses,
            "total_picks": total_picks,
            "accuracy": (total_wins / total_picks * 100) if total_picks else 0.0,
            "roi": ((total_returns - total_stakes) / total_stakes * 100) if total_stakes > 0 else 0.0,
            "leagues": per_league,
        }

    return summary


def save_backtest_report(results: Dict[str, Any], path: Path = None) -> None:
    """Write the backtest summary to a text file."""
    if path is None:
        path = LOGS_DIR / "backtest_results.txt"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 70,
        "SPORTS PREDICTION BOT — BACKTEST RESULTS",
        f"Generated: {datetime.now().isoformat()}",
        "Method: chronological walk-forward per league. Each prediction uses only",
        "rolling team form from matches strictly before it; history is updated",
        "with the real result only after scoring (no lookahead).",
        "=" * 70,
        "",
    ]

    for model_key, stats in results.items():
        lines.append(f"MODEL: {model_key}")
        lines.append(f"  Total Picks: {stats['total_picks']}")
        lines.append(f"  Wins: {stats['wins']}  Losses: {stats['losses']}")
        lines.append(f"  Accuracy: {stats['accuracy']:.2f}%")
        lines.append(f"  Flat-Stake ROI (vs Pinnacle closing odds): {stats['roi']:.2f}%")
        if stats.get("rps") is not None:
            verdict = "beats" if stats["rps"] < RPS_UNIFORM else "WORSE THAN"
            lines.append(
                f"  Ranked Probability Score: {stats['rps']:.4f} "
                f"({verdict} uniform {RPS_UNIFORM:.4f}; lower is better)"
            )
        if stats.get("rps_common") is not None:
            lines.append(
                f"  RPS on common sample: {stats['rps_common']:.4f} "
                f"(n={stats['rps_common_n']}; the matches EVERY model priced -- "
                f"this is the only like-for-like comparison)"
            )
        if stats.get("rps_holdout") is not None:
            lines.append(
                f"  RPS on XGBoost holdout window (>= {XGB_HOLDOUT_START.date()}): "
                f"{stats['rps_holdout']:.4f} (n={stats['rps_holdout_n']}; "
                f"the only window where ALL FOUR models are out-of-sample)"
            )
        lines.append("  League Breakdown:")
        for lg in stats["leagues"]:
            lines.append(
                f"    {lg['league']:20s} | Picks: {lg['total_picks']:4d} | "
                f"Wins: {lg['wins']:4d} | Losses: {lg['losses']:4d} | "
                f"Accuracy: {lg['accuracy']:6.2f}% | ROI: {lg['roi']:+.2f}%"
                + (f" | RPS: {lg['rps']:.4f}" if lg.get("rps") is not None else "")
                + (f" | RPSc: {lg['rps_common']:.4f}" if lg.get("rps_common") is not None else "")
            )
        lines.append("")

    lines.extend(["=" * 70, ""])

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"Backtest results saved to: {path}")


if __name__ == "__main__":
    print("Running backtest...")
    results = run_backtest()
    save_backtest_report(results)
    for model_key, stats in results.items():
        print(f"{model_key}: Accuracy={stats['accuracy']:.2f}%  ROI={stats['roi']:.2f}%  Picks={stats['total_picks']}")
