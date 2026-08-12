"""Telegram bot module — handles all bot commands and message formatting.

Uses python-telegram-bot v20+ (async). Provides commands:
/picks, /mega, /longshot, /results, /status
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackContext,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    CACHE_DIR,
    BASE_DIR,
)
from logger import logger
from confidence import confidence_band


# ---------------------------------------------------------------------------
# In-memory storage for today's picks (populated by scheduler or external call)
# ---------------------------------------------------------------------------
_today_picks: List[Dict[str, Any]] = []
_today_results: List[Dict[str, Any]] = []
_last_fetch_time: Optional[datetime] = None
_api_request_count: int = 0


# ---------------------------------------------------------------------------
# Message formatting helpers
# ---------------------------------------------------------------------------
DISCLAIMER = (
    "\n\nWARN️ DISCLAIMER: These are statistical picks for informational purposes only. "
    "They are NOT financial advice. Never bet more than you can afford to lose. "
    "Gamble responsibly. Past pick accuracy does not guarantee future results."
)


def format_pick(pick: Dict[str, Any]) -> str:
    """Format a single pick into a Telegram message."""
    sport = pick.get("sport", "Football")
    league = pick.get("league", "")
    home = pick.get("home_team", "")
    away = pick.get("away_team", "")
    kickoff = pick.get("kickoff", "")
    pick_type = pick.get("pick", "Home Win")
    confidence = pick.get("confidence", 0.0)
    value = pick.get("value", 0.0)
    odds = pick.get("odds", 0.0)
    odds_source = pick.get("odds_source", "estimated")
    reasons = pick.get("reasons", [])
    warnings = pick.get("warnings", [])
    band = confidence_band(confidence)
    model_source = pick.get("model_source")
    model_label = f" | {model_source}" if model_source else ""

    lines = [
        f"SPORT {sport} - {league}{model_label}",
        f" {home} vs {away}",
        f"TIME Kickoff: {kickoff}",
        "",
        f"Pick: {pick_type}",
        f"Confidence: {confidence:.1f}%  |  Value: +{value:.2%}",
        f"Odds: {odds:.2f} ({odds_source})",
        f"Band: {band}",
        "",
        "Reasons:",
    ]
    for reason in reasons:
        lines.append(f"- {reason}")

    # AI-generated analysis (NIM)
    nim_explanation = pick.get("nim_explanation")
    if nim_explanation:
        lines.extend(["", f"AI: AI Analysis: {nim_explanation}"])

    for warning in warnings:
        lines.append(f"WARN {warning}")

    return "\n".join(lines)


def format_results(results: List[Dict[str, Any]]) -> str:
    """Format the results summary for Telegram."""
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    lines = [f"STATS Results — {date_str}", "",]

    wins = 0
    losses = 0
    pending = 0

    for res in results:
        match = f"{res['home_team']} vs {res['away_team']}"
        pick = res['pick']
        outcome = res.get('outcome', 'PENDING')

        if outcome == "WON":
            lines.append(f"[OK] {match}: {pick} — WON")
            wins += 1
        elif outcome == "LOST":
            lines.append(f"[X] {match}: {pick} — LOST")
            losses += 1
        else:
            lines.append(f"⏳ {match}: {pick} — PENDING")
            pending += 1

    total = wins + losses
    accuracy = (wins / total * 100) if total > 0 else 0.0

    lines.append(f"\nRecord today: {wins} wins / {losses} losses / {pending} pending")
    lines.append(f"Running accuracy (last 30 days): {accuracy:.1f}%")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram command handlers
# ---------------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "🤖 Welcome to Sports Prediction Bot!\n\n"
        "Commands:\n"
        "/picks — All today's picks\n"
        "/mega — Only mega picks (75%+ confidence)\n"
        "/longshot — Longshot picks (Monday only)\n"
        "/results — Yesterday's results\n"
        "/status — Bot status"
    )


MAX_PICKS_PER_MESSAGE = 50  # cap to avoid Telegram message-too-long errors


async def _reply_in_chunks(update: Update, messages: List[str]) -> None:
    """Send a list of pick messages, split across multiple Telegram messages.

    The disclaimer is only appended to the final message.
    Each chunk is capped below Telegram's 4096-character limit.
    """
    if not messages:
        return

    MAX_CHUNK = 3500  # characters, leaves headroom below Telegram's 4096 limit
    chunks: List[str] = []
    current = ""

    for msg in messages:
        if current and len(current) + len(msg) + 4 > MAX_CHUNK:
            chunks.append(current)
            current = msg
        else:
            current = current + "\n\n" + msg if current else msg
    if current:
        chunks.append(current)

    # Send all parts except the last one raw
    for part in chunks[:-1]:
        await update.message.reply_text(part)
    # Append disclaimer only to the final chunk
    await update.message.reply_text(chunks[-1] + DISCLAIMER)


async def picks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /picks command — send top picks above 55% confidence."""
    try:
        _ensure_picks_loaded()
        picks = [p for p in _today_picks if p.get("confidence", 0) >= 55.0]
        if not picks:
            await update.message.reply_text("No picks available today. Check back after 06:30 WAT." + DISCLAIMER)
            return

        # Sort by confidence descending and cap at MAX_PICKS_PER_MESSAGE
        picks = sorted(picks, key=lambda x: x.get("confidence", 0), reverse=True)[:MAX_PICKS_PER_MESSAGE]
        messages = [format_pick(p) for p in picks]
        await _reply_in_chunks(update, messages)
    except Exception as exc:
        logger.error(f"Error in picks_command: {exc}", exc_info=True)
        await update.message.reply_text("Something went wrong fetching picks. Please try again later.")


async def mega_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mega command — send only mega picks (75%+ confidence)."""
    try:
        _ensure_picks_loaded()
        mega_picks = [p for p in _today_picks if p.get("confidence", 0) >= 75.0]
        if not mega_picks:
            await update.message.reply_text("No MEGA picks today. HOT" + DISCLAIMER)
            return

        mega_picks = sorted(mega_picks, key=lambda x: x.get("confidence", 0), reverse=True)[:MAX_PICKS_PER_MESSAGE]
        messages = [format_pick(p) for p in mega_picks]
        await _reply_in_chunks(update, messages)
    except Exception as exc:
        logger.error(f"Error in mega_command: {exc}", exc_info=True)
        await update.message.reply_text("Something went wrong fetching mega picks. Please try again later.")


async def longshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /longshot command — only runs on Monday."""
    try:
        if datetime.now().weekday() != 0:  # Monday = 0
            await update.message.reply_text("🎯 Longshot picks are only available on Mondays!" + DISCLAIMER)
            return

        _ensure_picks_loaded()
        longshots = [p for p in _today_picks if p.get("odds", 0) > 4.0 and p.get("value", 0) > 0.05]
        if not longshots:
            await update.message.reply_text("No longshot picks available today." + DISCLAIMER)
            return

        messages = [format_pick(p) for p in longshots[:2]]
        await _reply_in_chunks(update, messages)
    except Exception as exc:
        logger.error(f"Error in longshot_command: {exc}", exc_info=True)
        await update.message.reply_text("Something went wrong fetching longshots. Please try again later.")


async def results_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /results command — yesterday's pick outcomes."""
    try:
        _ensure_results_loaded()
        text = format_results(_today_results)
        await update.message.reply_text(text, parse_mode="HTML" if "<" in text else None)
    except Exception as exc:
        logger.error(f"Error in results_command: {exc}", exc_info=True)
        await update.message.reply_text("Something went wrong fetching results. Please try again later.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command — bot status summary."""
    try:
        _ensure_picks_loaded()
        last_fetch = _last_fetch_time.strftime("%Y-%m-%d %H:%M WAT") if _last_fetch_time else "Never"
        num_picks = len(_today_picks)
        text = (
            f"STATS Bot Status\n\n"
            f"Last data fetch: {last_fetch}\n"
            f"Picks today: {num_picks}\n"
            f"API requests used: {_api_request_count}\n"
        )
        await update.message.reply_text(text)
    except Exception as exc:
        logger.error(f"Error in status_command: {exc}", exc_info=True)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def build_application() -> Application:
    """Build and return the Telegram application."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("picks", picks_command))
    app.add_handler(CommandHandler("mega", mega_command))
    app.add_handler(CommandHandler("longshot", longshot_command))
    app.add_handler(CommandHandler("results", results_command))
    app.add_handler(CommandHandler("status", status_command))

    return app


# ---------------------------------------------------------------------------
# Utility functions for the scheduler to call
# ---------------------------------------------------------------------------
async def send_picks_to_chat(application: Application, picks: List[Dict[str, Any]], mega_only: bool = False) -> None:
    """Send picks to the configured Telegram chat."""
    if not picks:
        return

    if mega_only:
        picks = [p for p in picks if p.get("confidence", 0) >= 75.0]
        if not picks:
            return

    messages = [format_pick(p) for p in picks]
    text = "\n\n".join(messages) + DISCLAIMER

    try:
        # Send in chunks if too long
        max_len = 4096
        if len(text) <= max_len:
            await application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
        else:
            parts = []
            current = ""
            for message in messages:
                if len(current) + len(message) + 4 > max_len:
                    parts.append(current)
                    current = message
                else:
                    current += "\n\n" + message if current else message
            if current:
                parts.append(current)
            for part in parts:
                await application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=part)
    except Exception as exc:
        logger.error(f"Failed to send Telegram message: {exc}", exc_info=True)


async def send_lineup_warning(application: Application, warning: str) -> None:
    """Send a lineup warning to Telegram."""
    try:
        await application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=warning)
    except Exception as exc:
        logger.error(f"Failed to send lineup warning: {exc}", exc_info=True)


def store_picks(picks: List[Dict[str, Any]]) -> None:
    """Store picks in memory for the bot to serve.

    Also persists to disk so picks survive across processes.
    """
    global _today_picks
    _today_picks = picks
    try:
        from persistence import save_state
        save_state(picks, _today_results)
    except ImportError:
        pass


def store_results(results: List[Dict[str, Any]]) -> None:
    """Store results in memory for the /results command."""
    global _today_results
    _today_results = results
    try:
        from persistence import save_state
        save_state(_today_picks, results)
    except ImportError:
        pass


def _ensure_picks_loaded() -> None:
    """Reload picks from disk if the in-memory list is empty."""
    global _today_picks
    if _today_picks:
        return
    try:
        from persistence import load_state
        state = load_state()
        _today_picks = state.get("picks", [])
    except ImportError:
        pass


def _ensure_results_loaded() -> None:
    """Reload results from disk if the in-memory list is empty."""
    global _today_results
    if _today_results:
        return
    try:
        from persistence import load_state
        state = load_state()
        _today_results = state.get("results", [])
    except ImportError:
        pass


def update_last_fetch_time() -> None:
    """Update the last fetch timestamp."""
    global _last_fetch_time
    _last_fetch_time = datetime.now()


def update_api_count(count: int) -> None:
    """Update the API request count."""
    global _api_request_count
    _api_request_count = count
