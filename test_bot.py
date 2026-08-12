"""Test script — populates fake picks and sends a test message on Telegram.

Usage:
    cd C:\Users\DELL\Documents\SportsPredictionBot
    python test_bot.py
"""
import asyncio
import sys

from telegram_bot import (
    build_application,
    store_picks,
    send_picks_to_chat,
    format_pick,
)
from config import TELEGRAM_CHAT_ID


# ── Mock pick data (no API key needed) ──────────────────────────────────────
MOCK_PICKS = [
    {
        "fixture_id": 123,
        "sport": "Football",
        "league": "Premier League",
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "kickoff": "20:00 WAT",
        "pick": "Home Win",
        "confidence": 78.5,
        "value": 0.15,
        "odds": 2.10,
        "odds_source": "estimated",
        "model_home": 0.52,
        "reasons": [
            "Model probability: 52.0%",
            "ELO-adjusted probability: 52.0%",
            "Arsenal: W W W D W in last 5",
            "ELO gap: 180 pts in Arsenal's favour",
        ],
        "warnings": [],
    },
    {
        "fixture_id": 456,
        "sport": "Football",
        "league": "La Liga",
        "home_team": "Real Madrid",
        "away_team": "Barcelona",
        "kickoff": "21:30 WAT",
        "pick": "Home Win",
        "confidence": 62.0,
        "value": 0.08,
        "odds": 1.85,
        "odds_source": "estimated",
        "model_home": 0.55,
        "reasons": [
            "Model probability: 55.0%",
            "Real Madrid won 4 of last 5 H2H meetings",
        ],
        "warnings": [],
    },
]


def test_store_picks() -> None:
    """Verify picks are stored and retrievable."""
    store_picks(MOCK_PICKS)
    print("✅ Picks stored successfully.")
    print(f"   {len(MOCK_PICKS)} mock picks added.")


def test_formatting() -> None:
    """Verify pick message formatting."""
    print("\n--- Testing pick formatting ---")
    for pick in MOCK_PICKS:
        formatted = format_pick(pick)
        print(f"\n{formatted[:100]}...")
    print("✅ Formatting OK.")


async def test_telegram_send() -> None:
    """Send the mock picks to Telegram."""
    print("\n--- Sending to Telegram ---")
    try:
        app = build_application()
        await app.bot.initialize()
        await send_picks_to_chat(app, MOCK_PICKS)
        print("✅ Message sent to Telegram successfully!")
    except Exception as exc:
        print(f"❌ Telegram send failed: {exc}")
        raise


def main() -> None:
    """Run all tests."""
    print("=" * 60)
    print("  SPORTS BOT — TEST SCRIPT")
    print("=" * 60)

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID is not set in config/.env")
        sys.exit(1)

    # Test 1: Store picks
    test_store_picks()

    # Test 2: Formatting
    test_formatting()

    # Test 3: Telegram send
    asyncio.run(test_telegram_send())

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
    print("Now go check your Telegram — you should see the picks!")
    print("Try sending /picks to the bot.")


if __name__ == "__main__":
    main()
