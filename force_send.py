"""Force-send today's picks immediately (ignores the clock).

Uses mock picks to bypass any API/rate-limit issues and prove the
Telegram delivery pipeline works end-to-end.
"""
import asyncio
from datetime import datetime

import scheduler as _sch
from telegram_bot import build_application, send_picks_to_chat, store_picks


MOCK_PICKS = [
    {
        "fixture_id": 999001,
        "sport": "Football",
        "league": "Premier League",
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "kickoff": "21:00 WAT",
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
        ],
        "warnings": [],
    },
    {
        "fixture_id": 999002,
        "sport": "Football",
        "league": "La Liga",
        "home_team": "Real Madrid",
        "away_team": "Barcelona",
        "kickoff": "22:30 WAT",
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


def main() -> None:
    print("=" * 60)
    print("  FORCE SEND — BYPASSING LIVE API (MOCK PICKS)")
    print("=" * 60)
    print(f"  Local time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Inject mock picks into the scheduler and bot storage
    _sch._todays_picks = MOCK_PICKS
    store_picks(MOCK_PICKS)
    print(f"[1] Injected {len(MOCK_PICKS)} mock picks into storage.")

    # Build application and send
    print("[2] Initializing Telegram bot...")
    app = build_application()

    print("[3] Sending picks to Telegram...")
    try:
        asyncio.run(send_picks_to_chat(app, MOCK_PICKS))
        print()
        print("=" * 60)
        print("  SUCCESS — picks sent to Telegram!")
        print("=" * 60)
        print("  Check your Telegram now.")
    except Exception as exc:
        print(f"\n  ERROR sending to Telegram: {exc}")
        raise


if __name__ == "__main__":
    main()
