"""Scheduler module -- orchestrates all daily jobs using APScheduler.

Jobs (all in WAT -- UTC+1):
- 06:00  fetch_all_data()
- 06:30  run_predictions()
- 07:00  send_morning_picks()
- ~1h before kickoff  check_lineups()  (for each fixture with a pick)
- 23:30  check_results()
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
import pytz

from config import get_request_count
from data_fetch import (
    fetch_football_fixtures,
    fetch_basketball_games,
    fetch_volleyball_fixtures,
    fetch_mma_fights,
    fetch_football_odds,
    fetch_football_h2h,
    fetch_football_team_form,
    build_team_stats_from_form,
)
from model_football import predict_football
from model_basketball import predict_basketball
from model_volleyball import predict_volleyball
from model_mma import predict_mma
from model_xgboost import predict_xgboost
from nim_enricher import generate_nim_explanation
from confidence import calculate_confidence, should_send
from elo_loader import get_team_elo
from value_checker import calculate_value, get_best_odds, is_value_bet, estimate_odds
from lineup_monitor import check_lineup_for_absences
from result_checker import check_all_results
from telegram_bot import (
    build_application,
    send_picks_to_chat,
    send_lineup_warning,
    store_picks,
    store_results,
    update_last_fetch_time,
    update_api_count,
)
from persistence import load_state, save_state
from logger import logger


# Todays data per sport
_todays_fixtures: Dict[str, List[Dict[str, Any]]] = {}
_todays_picks: List[Dict[str, Any]] = []
_scheduler: BackgroundScheduler = None

# Track which lineups have already been scheduled to avoid duplicates
_scheduled_lineups: set = set()


def fetch_all_data() -> None:
    """Pull fixtures from all APIs. Download ELO CSV. Cache to JSON."""
    global _todays_fixtures
    date_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Starting data fetch for {date_str}")

    try:
        football_fixtures = fetch_football_fixtures(date_str)
        logger.info(f"Fetched {len(football_fixtures)} football fixtures")

        basketball_games = fetch_basketball_games(date_str)
        logger.info(f"Fetched {len(basketball_games)} basketball games")

        volleyball_fixtures = fetch_volleyball_fixtures(date_str)
        logger.info(f"Fetched {len(volleyball_fixtures)} volleyball fixtures")

        mma_fights = fetch_mma_fights(date_str)
        logger.info(f"Fetched {len(mma_fights)} MMA fights")

        _todays_fixtures = {
            "football": football_fixtures,
            "basketball": basketball_games,
            "volleyball": volleyball_fixtures,
            "mma": mma_fights,
        }
        update_last_fetch_time()

        today = datetime.now().strftime("%Y-%m-%d")
        counts = get_request_count(today)
        update_api_count(sum(counts.values()))

        total = sum(len(v) for v in _todays_fixtures.values())
        logger.info(f"Data fetch complete. Total fixtures across all sports: {total}")

    except Exception as exc:
        logger.error(f"Error in fetch_all_data: {exc}", exc_info=True)


def _process_football() -> List[Dict[str, Any]]:
    """Run football model with real team stats and generate picks."""
    picks = []
    season = datetime.now().year

    for fixture in _todays_fixtures.get("football", []):
        try:
            fixture_id = fixture.get("fixture", {}).get("id")
            home_team = fixture.get("teams", {}).get("home", {}).get("name", "")
            away_team = fixture.get("teams", {}).get("away", {}).get("name", "")
            home_team_id = fixture.get("teams", {}).get("home", {}).get("id")
            away_team_id = fixture.get("teams", {}).get("away", {}).get("id")
            league = fixture.get("league", {}).get("name", "")
            kickoff_obj = fixture.get("fixture", {}).get("date", "")
            kickoff = "Unknown"
            if kickoff_obj:
                try:
                    dt = datetime.fromisoformat(kickoff_obj.replace("Z", "+00:00"))
                    kickoff = dt.strftime("%H:%M WAT")
                except (ValueError, AttributeError):
                    kickoff = str(kickoff_obj)

            # Fetch real team form
            home_stats = []
            away_stats = []
            try:
                if home_team_id:
                    raw_home = fetch_football_team_form(home_team_id, season, last_n=10)
                    home_stats = build_team_stats_from_form(home_team_id, raw_home)
            except Exception as exc:
                logger.warning(f"Could not fetch form for {home_team}: {exc}")
            try:
                if away_team_id:
                    raw_away = fetch_football_team_form(away_team_id, season, last_n=10)
                    away_stats = build_team_stats_from_form(away_team_id, raw_away)
            except Exception as exc:
                logger.warning(f"Could not fetch form for {away_team}: {exc}")

            # Run both models on the same fixture data
            # -----------------------------------------------------------------
            # Get odds (common for both models)
            odds_data = fetch_football_odds(fixture_id)
            odds_1x2, bookmaker = get_best_odds(odds_data) if odds_data else (None, None)

            # Fetch H2H data (common for both models)
            h2h_results_raw = []
            if home_team_id and away_team_id:
                try:
                    h2h_fixtures = fetch_football_h2h(home_team_id, away_team_id)
                    for h2h in h2h_fixtures[-5:]:
                        teams = h2h.get("teams", {})
                        h2h_home_id = teams.get("home", {}).get("id")
                        if h2h_home_id == home_team_id:
                            home_winner = teams.get("home", {}).get("winner")
                            if home_winner is True:
                                h2h_results_raw.append("W")
                            elif home_winner is False:
                                h2h_results_raw.append("L")
                            else:
                                h2h_results_raw.append("D")
                except Exception as exc:
                    logger.warning(f"H2H fetch failed for fixture {fixture_id}: {exc}")

            # ELO (common for both models)
            try:
                home_elo = get_team_elo(home_team)
                away_elo = get_team_elo(away_team)
                elo_diff = home_elo - away_elo
            except Exception as exc:
                logger.warning(f"ELO fetch failed for {home_team}/{away_team}: {exc}")
                elo_diff = 0.0

            # Run both models
            model_result = predict_football(home_team, away_team, home_stats, away_stats)
            xgb_result = predict_xgboost(
                home_team, away_team, home_stats, away_stats,
                h2h_results=h2h_results_raw, league_name=league
            )

            # Process each model's predictions
            MIN_PROB_THRESHOLD = 0.38
            xgb_label = "XGBoost ML" if xgb_result.get("source") == "trained" else "XGBoost (fallback heuristic)"
            model_outputs = [
                ("Poisson-ELO", model_result),
                (xgb_label, xgb_result),
            ]

            for model_name, result in model_outputs:
                try:
                    probs = [
                        ("Home Win", result["home_win"]),
                        ("Draw", result.get("draw", 0.0)),
                        ("Away Win", result.get("away_win", 0.0)),
                    ]
                    pick_type, max_prob = max(probs, key=lambda x: x[1])

                    if max_prob < MIN_PROB_THRESHOLD:
                        logger.debug(f"  {model_name} skipped - prob {max_prob:.2%} below threshold")
                        continue

                    odds_for_pick = None
                    if odds_1x2:
                        odds_map = {"Home Win": "Home", "Draw": "Draw", "Away Win": "Away"}
                        odds_for_pick = odds_1x2.get(odds_map.get(pick_type, "Home"))

                    use_estimated = False
                    if not odds_for_pick:
                        odds_for_pick = estimate_odds(max_prob)
                        bookmaker = "estimated"
                        use_estimated = True

                    value = calculate_value(max_prob, odds_for_pick)

                    # Skip value check when using estimated odds
                    if not use_estimated and not is_value_bet(max_prob, odds_for_pick):
                        continue

                    # Perspective adjustments
                    if pick_type == "Away Win":
                        h2h_results_eval = [
                            "L" if r == "W" else "W" if r == "L" else "D" for r in h2h_results_raw
                        ]
                        elo_diff_eval = -elo_diff
                    else:
                        h2h_results_eval = h2h_results_raw
                        elo_diff_eval = elo_diff

                    confidence = calculate_confidence(
                        raw_prob=max_prob,
                        h2h_results=h2h_results_eval,
                        elo_diff=elo_diff_eval,
                        is_high_variance_sport=False,
                    )

                    if not should_send(confidence):
                        continue

                    pick = {
                        "fixture_id": fixture_id,
                        "sport": "Football",
                        "league": league,
                        "home_team": home_team,
                        "away_team": away_team,
                        "kickoff": kickoff,
                        "kickoff_iso": kickoff_obj,
                        "pick": pick_type,
                        "confidence": confidence,
                        "value": value,
                        "odds": odds_for_pick,
                        "odds_source": bookmaker or "estimated",
                        "model_source": model_name,
                        "model_home": result["home_win"],
                        "reasons": [
                            f"{model_name} - {pick_type}: {max_prob:.1%}",
                            f"ELO: {elo_diff:+.0f} | H2H: {len(h2h_results_raw)} matches",
                        ],
                        "warnings": [],
                    }

                    # NIM AI-generated narrative (best-effort)
                    try:
                        nim_text = generate_nim_explanation(
                            home_team, away_team, pick_type, confidence,
                            result["home_win"], result.get("draw", 0.0),
                            result.get("away_win", 0.0), model_name,
                        )
                        if nim_text:
                            pick["nim_explanation"] = nim_text
                    except Exception:
                        pass

                    picks.append(pick)

                except Exception as exc:
                    logger.error(
                        f"Error processing {model_name} pick for fixture {fixture_id}: {exc}",
                        exc_info=True,
                    )
                    continue

        except Exception as exc:
            f_id = fixture.get("fixture", {}).get("id") if isinstance(fixture, dict) else "unknown"
            logger.error(f"Error processing football fixture {f_id}: {exc}", exc_info=True)
            continue

    return picks


def _process_basketball() -> List[Dict[str, Any]]:
    """Process basketball fixtures and generate picks."""
    picks = []
    for game in _todays_fixtures.get("basketball", []):
        try:
            home_team = game.get("home_team", {}).get("name", "")
            away_team = game.get("visitor_team", {}).get("name", "")
            if not home_team or not away_team:
                continue

            model_result = predict_basketball(home_team, away_team)

            probs = [
                ("Home Win", model_result["home_win"]),
                ("Away Win", model_result["away_win"]),
            ]
            pick_type, max_prob = max(probs, key=lambda x: x[1])

            odds_for_pick = estimate_odds(max_prob)
            value = calculate_value(max_prob, odds_for_pick)

            confidence = calculate_confidence(
                raw_prob=max_prob,
                is_high_variance_sport=False,
            )
            if not should_send(confidence):
                continue

            picks.append({
                "fixture_id": game.get("id", 0),
                "sport": "Basketball",
                "league": game.get("season", "NBA"),
                "home_team": home_team,
                "away_team": away_team,
                "kickoff": "Unknown",
                "pick": pick_type,
                "confidence": confidence,
                "value": value,
                "odds": odds_for_pick,
                "odds_source": "estimated",
                "model_home": model_result["home_win"],
                "reasons": [f"Model probability ({pick_type}): {max_prob:.1%}"],
                "warnings": [],
            })
        except Exception as exc:
            logger.error(f"Error processing basketball game: {exc}", exc_info=True)
    return picks


def _process_volleyball() -> List[Dict[str, Any]]:
    """Process volleyball fixtures and generate picks."""
    picks = []
    for match in _todays_fixtures.get("volleyball", []):
        try:
            home_team = match.get("teams", {}).get("home", {}).get("name", "")
            away_team = match.get("teams", {}).get("away", {}).get("name", "")
            if not home_team or not away_team:
                continue

            model_result = predict_volleyball(home_team, away_team, {}, {})

            # Dynamic key names based on team names
            home_key = f"{home_team}_win"
            away_key = f"{away_team}_win"
            probs = [
                ("Home Win", model_result.get(home_key, 0.5)),
                ("Away Win", model_result.get(away_key, 0.5)),
            ]
            pick_type, max_prob = max(probs, key=lambda x: x[1])

            odds_for_pick = estimate_odds(max_prob)
            value = calculate_value(max_prob, odds_for_pick)

            confidence = calculate_confidence(
                raw_prob=max_prob,
                is_high_variance_sport=False,
            )
            if not should_send(confidence):
                continue

            picks.append({
                "fixture_id": match.get("fixture", {}).get("id", 0),
                "sport": "Volleyball",
                "league": match.get("league", {}).get("name", ""),
                "home_team": home_team,
                "away_team": away_team,
                "kickoff": "Unknown",
                "pick": pick_type,
                "confidence": confidence,
                "value": value,
                "odds": odds_for_pick,
                "odds_source": "estimated",
                "model_home": model_result.get(home_key, 0.5),
                "reasons": [f"Model probability ({pick_type}): {max_prob:.1%}"],
                "warnings": [],
            })
        except Exception as exc:
            logger.error(f"Error processing volleyball match: {exc}", exc_info=True)
    return picks


def _process_mma() -> List[Dict[str, Any]]:
    """Process MMA fights and generate picks."""
    picks = []
    for fight in _todays_fixtures.get("mma", []):
        try:
            fighters = fight.get("fighters", [])
            if len(fighters) < 2:
                continue
            fighter_a = fighters[0].get("name", "")
            fighter_b = fighters[1].get("name", "")
            if not fighter_a or not fighter_b:
                continue

            # No external ELO source for MMA -- use 1500 each
            model_result = predict_mma(fighter_a, fighter_b, 1500, 1500)

            key_a = f"{fighter_a}_win"
            key_b = f"{fighter_b}_win"
            probs = [
                (f"{fighter_a} Win", model_result.get(key_a, 0.5)),
                (f"{fighter_b} Win", model_result.get(key_b, 0.5)),
            ]
            pick_type, max_prob = max(probs, key=lambda x: x[1])

            odds_for_pick = estimate_odds(max_prob)
            value = calculate_value(max_prob, odds_for_pick)

            confidence = calculate_confidence(
                raw_prob=max_prob,
                is_high_variance_sport=True,  # MMA has 60% cap
            )
            if not should_send(confidence):
                continue

            picks.append({
                "fixture_id": fight.get("fight", {}).get("id", 0),
                "sport": "MMA",
                "league": fight.get("league", {}).get("name", ""),
                "home_team": fighter_a,
                "away_team": fighter_b,
                "kickoff": "Unknown",
                "pick": pick_type,
                "confidence": confidence,
                "value": value,
                "odds": odds_for_pick,
                "odds_source": "estimated",
                "reasons": [f"Model probability ({pick_type}): {max_prob:.1%}"],
                "warnings": [],
            })
        except Exception as exc:
            logger.error(f"Error processing MMA fight: {exc}", exc_info=True)
    return picks


def run_predictions() -> None:
    """Run all sport models, score confidence, run value check, build pick list."""
    global _todays_picks
    logger.info("Starting prediction run across all sports...")

    # Restore persisted state if available and valid
    try:
        state = load_state()
        state_picks = state.get("picks", [])
        if state_picks:
            # Validate: must have home_team and pick keys; reject corrupted saves
            valid_picks = [p for p in state_picks if all(k in p for k in ("home_team", "away_team", "pick"))]
            if valid_picks:
                _todays_picks = valid_picks
                store_picks(_todays_picks)
                logger.info(f"Restored {len(_todays_picks)} valid picks from today's persisted state.")
                return
            logger.warning("Persisted state found but data was corrupted; regenerating picks.")
    except Exception as exc:
        logger.warning(f"Could not load persisted state: {exc}")

    try:
        all_picks = []

        if _todays_fixtures.get("football"):
            football_picks = _process_football()
            all_picks.extend(football_picks)
            logger.info(f"Football picks: {len(football_picks)}")

        if _todays_fixtures.get("basketball"):
            basketball_picks = _process_basketball()
            all_picks.extend(basketball_picks)
            logger.info(f"Basketball picks: {len(basketball_picks)}")

        if _todays_fixtures.get("volleyball"):
            volleyball_picks = _process_volleyball()
            all_picks.extend(volleyball_picks)
            logger.info(f"Volleyball picks: {len(volleyball_picks)}")

        if _todays_fixtures.get("mma"):
            mma_picks = _process_mma()
            all_picks.extend(mma_picks)
            logger.info(f"MMA picks: {len(mma_picks)}")

        _todays_picks = all_picks
        store_picks(all_picks)

        # Persist to disk
        save_state(all_picks, [])
        logger.info(f"Prediction run complete. {len(all_picks)} total picks generated.")

    except Exception as exc:
        logger.error(f"Error in run_predictions: {exc}", exc_info=True)


def send_morning_picks() -> None:
    """Format and send daily picks to Telegram."""
    try:
        if not _todays_picks:
            logger.warning("No picks to send.")
            return

        app = build_application()
        asyncio.run(send_picks_to_chat(app, _todays_picks))
        logger.info(f"Sent {len(_todays_picks)} picks to Telegram.")
    except Exception as exc:
        logger.error(f"Error sending morning picks: {exc}", exc_info=True)


def check_lineups(fixture_id: int, home_team: str, away_team: str) -> None:
    """Fetch confirmed lineups, flag key player absences, send warning."""
    try:
        result = check_lineup_for_absences(fixture_id, home_team, away_team)

        if result["warnings"]:
            app = build_application()
            for warning in result["warnings"]:
                asyncio.run(send_lineup_warning(app, warning))
            logger.info(
                f"Sent {len(result['warnings'])} lineup warnings for fixture {fixture_id}"
            )

    except Exception as exc:
        logger.error(f"Error checking lineups for {fixture_id}: {exc}", exc_info=True)


def check_results() -> None:
    """Fetch completed match scores, compare to picks, send W/L summary."""
    try:
        if not _todays_picks:
            logger.warning("No picks to check results for.")
            return

        results = check_all_results(_todays_picks)
        store_results(results)

        # Persist updated results
        save_state(_todays_picks, results)

        wins = sum(1 for r in results if r.get("outcome") == "WON")
        losses = sum(1 for r in results if r.get("outcome") == "LOST")
        logger.info(f"Results checked. W: {wins}, L: {losses}")

    except Exception as exc:
        logger.error(f"Error in check_results: {exc}", exc_info=True)


def _schedule_lineup_checks() -> None:
    """Read today's picks and schedule one-off lineup checks ~65 min before kickoff."""
    global _scheduler, _scheduled_lineups
    if not _scheduler or not _todays_picks:
        return

    for pick in _todays_picks:
        kickoff_iso = pick.get("kickoff_iso")
        f_id = pick.get("fixture_id")
        if not kickoff_iso or not f_id:
            continue

        # Avoid duplicate schedules
        job_id = f"lineup_{f_id}"
        if job_id in _scheduled_lineups:
            continue

        try:
            kickoff_dt = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
            check_time = kickoff_dt - timedelta(minutes=65)

            if check_time > datetime.now(check_time.tzinfo):
                _scheduler.add_job(
                    check_lineups,
                    trigger=DateTrigger(run_date=check_time),
                    args=[f_id, pick["home_team"], pick["away_team"]],
                    id=job_id,
                    replace_existing=True,
                )
                _scheduled_lineups.add(job_id)
                logger.info(
                    f"Scheduled lineup check for {pick['home_team']} v {pick['away_team']} "
                    f"at {check_time.isoformat()}"
                )
        except (ValueError, TypeError) as exc:
            logger.error(
                f"Error scheduling lineup check for fixture {f_id}: {exc}",
                exc_info=True,
            )


def setup_scheduler() -> BackgroundScheduler:
    """Set up and return the APScheduler with all jobs."""
    global _scheduler
    tz = pytz.timezone("Africa/Lagos")
    _scheduler = BackgroundScheduler(timezone=tz)

    _scheduler.add_job(fetch_all_data, CronTrigger(hour=6, minute=0, timezone=tz))
    _scheduler.add_job(run_predictions, CronTrigger(hour=6, minute=30, timezone=tz))
    _scheduler.add_job(send_morning_picks, CronTrigger(hour=7, minute=0, timezone=tz))
    _scheduler.add_job(_schedule_lineup_checks, CronTrigger(hour=6, minute=35, timezone=tz))
    _scheduler.add_job(check_results, CronTrigger(hour=23, minute=30, timezone=tz))

    return _scheduler
