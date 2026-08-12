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

MIN_HISTORY_MATCHES = 3  # skip scoring until a team has some real rolling form

_LEAGUE_DISPLAY_NAMES = {
    "premier_league": "Premier League",
    "la_liga": "La Liga",
    "bundesliga": "Bundesliga",
    "serie_a": "Serie A",
    "ligue_1": "Ligue 1",
}


def _update_history(team_history: Dict[str, List[Dict]], team: str, goals_for: float, goals_against: float) -> None:
    team_history.setdefault(team, []).append({"goals_for": goals_for, "goals_against": goals_against})


def _run_model_backtest(model_key: str, df: pd.DataFrame, league_key: str, league_display: str) -> Dict[str, Any]:
    """Walk one league's matches chronologically, scoring one model."""
    team_history: Dict[str, List[Dict]] = {}
    wins = losses = 0
    stakes = 0.0
    returns = 0.0

    for _, row in df.iterrows():
        fthg, ftag, ftr = row.get("FTHG"), row.get("FTAG"), row.get("FTR")
        home_team = str(row.get("HomeTeam", "")).strip()
        away_team = str(row.get("AwayTeam", "")).strip()
        if pd.isna(fthg) or pd.isna(ftag) or not home_team or not away_team:
            continue

        home_stats = team_history.get(home_team, [])
        away_stats = team_history.get(away_team, [])

        if len(home_stats) >= MIN_HISTORY_MATCHES and len(away_stats) >= MIN_HISTORY_MATCHES:
            try:
                if model_key == "xgboost":
                    result = predict_xgboost(
                        home_team, away_team, home_stats, away_stats,
                        h2h_results=None, league_name=league_display,
                    )
                else:
                    result = predict_football(home_team, away_team, home_stats, away_stats)

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
            except Exception as exc:
                logger.error(f"Backtest error [{model_key}] {home_team} v {away_team}: {exc}", exc_info=True)

        # Update rolling history AFTER scoring, using the real result —
        # this match must never be visible to its own prediction.
        _update_history(team_history, home_team, float(fthg), float(ftag))
        _update_history(team_history, away_team, float(ftag), float(fthg))

    total = wins + losses
    return {
        "league": league_key,
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
    per_model_leagues: Dict[str, List[Dict]] = {"poisson_elo": [], "xgboost": []}

    for key in LEAGUE_FILES:
        df = load_historical_csv(key)
        if df is None or df.empty:
            continue

        if "Date" in df.columns:
            df = df.copy()
            df["_parsed_date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
            df = df.sort_values("_parsed_date")

        league_display = _LEAGUE_DISPLAY_NAMES.get(key, key.replace("_", " ").title())

        poisson_stats = _run_model_backtest("poisson_elo", df, key, league_display)
        if poisson_stats["total_picks"] > 0:
            per_model_leagues["poisson_elo"].append(poisson_stats)

        xgb_stats = _run_model_backtest("xgboost", df, key, league_display)
        if xgb_stats["total_picks"] > 0:
            per_model_leagues["xgboost"].append(xgb_stats)

    summary = {}
    for model_key, per_league in per_model_leagues.items():
        total_wins = sum(r["wins"] for r in per_league)
        total_losses = sum(r["losses"] for r in per_league)
        total_picks = total_wins + total_losses
        total_stakes = sum(r["stakes"] for r in per_league)
        total_returns = sum(r["returns"] for r in per_league)
        summary[model_key] = {
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
        lines.append("  League Breakdown:")
        for lg in stats["leagues"]:
            lines.append(
                f"    {lg['league']:20s} | Picks: {lg['total_picks']:4d} | "
                f"Wins: {lg['wins']:4d} | Losses: {lg['losses']:4d} | "
                f"Accuracy: {lg['accuracy']:6.2f}% | ROI: {lg['roi']:+.2f}%"
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
