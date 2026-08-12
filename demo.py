"""End-to-end demo — full pipeline in Lagos (WAT) timezone.

Usage (run from the project root)::

    cd "C:\\Users\\DELL\\Documents\\SportsPredictionBot"
    python demo.py

This script runs a complete mock cycle so you can verify the bot
actually delivers picks to your Telegram.
"""

import asyncio
import sys
from datetime import datetime
from typing import Any, Dict, List

import pytz

# Import the scheduler module itself (for _todays_fixtures access)
import scheduler as _sch
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from telegram_bot import (
    build_application,
    store_picks,
    send_picks_to_chat,
    format_pick,
)
from model_football import predict_football
from confidence import calculate_confidence, should_send
from value_checker import calculate_value, is_value_bet, estimate_odds
from logger import logger

# ── Timezone ──────────────────────────────────────────────────────────────────
WAT = pytz.timezone("Africa/Lagos")

# ── Data for mock fixtures (no API key needed) ───────────────────────────────
MOCK_FIXTURES: List[Dict[str, Any]] = [
    {
        "fixture": {"id": 123}
,
        "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Liverpool"}},
        "league": {"name": "Premier League"},
    },
    {
        "fixture": {"id": 456, "date": "2026-06-10T19:00:00+00:00"},
        "teams": {"home": {"name": "Real Madrid"}, "away": {"name": "Barcelona"}},
        "league": {"name": "La Liga"},
    },
    {
        "fixture": {"id": 789, "date": "2026-06-10T20:30:00+00:00"},
        "teams": {"home": {"name": "Milan"}, "away": {"name": "Juventus"}},
        "league": {"name": "Serie A"},
    },
    {
        "fixture": {"id": 101, "date": "2026-06-10T18:15:00+00:00"},
        "teams": {"home": {"name": "Bayern Munich"}, "away": {"name": "Dortmund"}},
        "league": {"name": "Bundesliga"},
    },
    {
        "fixture": {"id": 202, "date": "2026-06-10T21:00:00+00:00"},
        "teams": {"home": {"name": "PSG"}, "away": {"name": "Marseille"}},
        "league": {"name": "Ligue 1"},
    },
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def now_wat() -> str:
    """Current time in Lagos, nicely formatted."""
    return datetime.now(WAT).strftime("%Y-%m-%d %H:%M:%S WAT")


def make_kickoff_wat(utc_hour: int) -> str:
    """Convert a UTC hour to a WAT kickoff string (UTC+1)."""
    kick_dt = datetime(2026, 6, 9, utc_hour, 0, 0, tzinfo=pytz.utc)
    kick_wat = kick_dt.astimezone(WAT)
    return kick_wat.strftime("%H:%M WAT")


def inject_mock_fixtures() -> None:
    """Put mock fixtures into the scheduler's _todays_fixtures."""
    _sch._todays_fixtures = MOCK_FIXTURES
    print(f"   → Injected {len(MOCK_FIXTURES)} mock fixtures")


def generate_picks() -> List[Dict[str, Any]]:
    """Run the prediction model over the injected fixtures and return picks."""
    picks = []

    for fixture in MOCK_FIXTURES:
        fixture_id = fixture["fixture"]["id"]
        home_team = fixture["teams"]["home"]["name"]
        away_team = fixture["teams"]["away"]["name"]
        league_name = fixture["league"]["name"]
        kickoff_utc = fixture["fixture"].get("date", "")

        if kickoff_utc:
            try:
                dt = datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00"))
                dt_wat = dt.astimezone(WAT)
                kickoff_str = dt_wat.strftime("%H:%M WAT")
            except (ValueError, TypeError):
                kickoff_str = now_wat()
        else:
            kickoff_str = now_wat()

        # Run the football model
        model_result = predict_football(home_team, away_team, [], [])

        # Mock odds
        best_odds = estimate_odds(model_result["home_win"])
        bookmaker = "estimated"

        value = calculate_value(model_result["home_win"], best_odds)
        if not is_value_bet(model_result["home_win"], best_odds):
            continue

        confidence = calculate_confidence(
            raw_prob=model_result["home_win"],
            last_5=["W", "W", "W", "D", "W"],  # mock form
            h2h_results=["W", "W", "W", "L", "W"],
            elo_diff=180,
            home_win_rate=0.72,
            market_prob=None,
        )

        if not should_send(confidence):
            continue

        pick = {
            "fixture_id": fixture_id,
            "sport": "Football",
            "league": league_name,
            "home_team": home_team,
            "away_team": away_team,
            "kickoff": kickoff_str,
            "kickoff_iso": kickoff_utc or datetime.now(WAT).isoformat(),
            "pick": "Home Win",
            "confidence": confidence,
            "value": value,
            "odds": best_odds,
            "odds_source": bookmaker,
            "model_home": model_result["home_win"],
            "reasons": [
                f"Model probability: {model_result['home_win']:.1%}",
                f"Model draw: {model_result['draw']:.1%}",
                f"Model away: {model_result['away_win']:.1%}",
            ],
            "warnings": [],
        }
        picks.append(pick)

    _sch._todays_picks = picks
    store_picks(picks)
    return picks


# ── Main flow ────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 70)
    print("  SPORTS PREDICTION BOT -- END-TO-END DEMO")
    print("=" * 70)
    print(f"  Current Lagos time: {now_wat()}")
    print()

    # 1️⃣  Credentials check ────────────────────────────────────────────────
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
        print("   Create a .env file in the project folder with:")
        print("   TELEGRAM_BOT_TOKEN=your_token_here")
        print("   TELEGRAM_CHAT_ID=your_chat_id_here")
        sys.exit(1)
    print("✅ Telegram credentials verified.")
    print(f"   Target chat ID: {TELEGRAM_CHAT_ID}")
    print()

    # 2️⃣  Inject mock fixtures ─────────────────────────────────────────────
    print("[1] Step 1: Injecting mock fixtures...")
    inject_mock_fixtures()

    # 3️⃣  Run predictions ──────────────────────────────────────────────────
    print("[2] Step 2: Running prediction models...")
    picks = generate_picks()
    if not picks:
        print("   WARN  No picks passed the confidence / value filters.")
        sys.exit(0)
    print(f"   → {len(picks)} picks generated")

    # 4️⃣  Show picks on console ────────────────────────────────────────────
    print()
    print("-" * 70)
    print("  📊 PICKS (Lagos timezone)")
    print("-" * 70)
    for pick in picks:
        print()
        print(format_pick(pick))
    print()
    print("-" * 70)

    # 5️⃣  Send to Telegram ─────────────────────────────────────────────────
    print("📤 Step 3: Sending picks to Telegram...")
    try:
        app = build_application()
        await app.bot.initialize()
        await send_picks_to_chat(app, picks)
        print("✅ Picks delivered to Telegram successfully!")
    except Exception as exc:
        print(f"❌ Telegram delivery failed: {exc}")
        raise

    # 6️⃣  Done ─────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  🎉 DEMO COMPLETE — Check your Telegram now!")
    print(f"  Time delivered: {now_wat()}")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Check Telegram — you should see the picks.")
    print("  2. Try the bot commands: /picks /mega /status /results")
    print("  3. Keep python main.py running for daily auto-picks.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
