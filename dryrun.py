"""Dry-run script -- tests the full prediction pipeline with mock data.

No API calls are made, so no API-Sports credits are consumed.
Tests: football form builder, ELO lookup, all 4 sport models,
value checker, odds extraction, confidence scoring.
"""

import sys
from scheduler import (
    _process_football,
    _process_basketball,
    _process_volleyball,
    _process_mma,
)


# ---------------------------------------------------------------------------
# Mock football fixtures (simulates real API-Sports v3 response)
# ---------------------------------------------------------------------------
MOCK_FOOTBALL_FIXTURE = {
    "fixture": {"id": 123456, "date": "2026-06-13T15:00:00+00:00"},
    "teams": {
        "home": {"id": 33, "name": "Manchester United"},
        "away": {"id": 34, "name": "Newcastle United"},
    },
    "league": {"name": "Premier League"},
}

# ---------------------------------------------------------------------------
# Mock basketball game (balldontlie format)
# ---------------------------------------------------------------------------
MOCK_BASKETBALL_GAME = {
    "id": 98765,
    "home_team": {"name": "Los Angeles Lakers"},
    "visitor_team": {"name": "Boston Celtics"},
    "season": 2026,
}

# ---------------------------------------------------------------------------
# Mock volleyball fixture
# ---------------------------------------------------------------------------
MOCK_VOLLEYBALL_MATCH = {
    "fixture": {"id": 55555, "date": "2026-06-13T19:00:00+00:00"},
    "teams": {
        "home": {"name": "Serbia"},
        "away": {"name": "Italy"},
    },
    "league": {"name": "World Championship"},
}

# ---------------------------------------------------------------------------
# Mock MMA fight
# ---------------------------------------------------------------------------
MOCK_MMA_FIGHT = {
    "fight": {"id": 88888, "date": "2026-06-13T20:00:00+00:00"},
    "fighters": [
        {"name": "Islam Makhachev"},
        {"name": "Justin Gaethje"},
    ],
    "league": {"name": "UFC"},
}


def inject_and_process() -> None:
    import scheduler as _sch
    _sch._todays_fixtures = {
        "football": [MOCK_FOOTBALL_FIXTURE],
        "basketball": [MOCK_BASKETBALL_GAME],
        "volleyball": [MOCK_VOLLEYBALL_MATCH],
        "mma": [MOCK_MMA_FIGHT],
    }

    # -----------------------------------------------------------------------
    # 1. Football (tests: team form, ELO lookup, H2H, odds, confidence)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  Football Prediction (with real team stats)")
    print("=" * 60)
    football_picks = _process_football()
    if football_picks:
        for p in football_picks:
            print(f"  {p['home_team']} vs {p['away_team']} -> {p['pick']} @ {p['odds']:.2f} ({p['odds_source']})")
            print(f"    Confidence: {p['confidence']:.1f}%, Value: {p['value']:.2%}")
    else:
        print("  No football pick generated (likely low confidence/value)")

    # -----------------------------------------------------------------------
    # 2. Basketball (tests: point differential model)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  Basketball Prediction")
    print("=" * 60)
    basketball_picks = _process_basketball()
    if basketball_picks:
        for p in basketball_picks:
            print(f"  {p['home_team']} vs {p['away_team']} -> {p['pick']} @ {p['odds']:.2f}")
            print(f"    Confidence: {p['confidence']:.1f}%")
    else:
        print("  No basketball pick generated")

    # -----------------------------------------------------------------------
    # 3. Volleyball (tests: set-based binomial model)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  Volleyball Prediction")
    print("=" * 60)
    volleyball_picks = _process_volleyball()
    if volleyball_picks:
        for p in volleyball_picks:
            print(f"  {p['home_team']} vs {p['away_team']} -> {p['pick']} @ {p['odds']:.2f}")
            print(f"    Confidence: {p['confidence']:.1f}%")
    else:
        print("  No volleyball pick generated")

    # -----------------------------------------------------------------------
    # 4. MMA (tests: high-variance model, 60% cap)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  MMA Prediction")
    print("=" * 60)
    mma_picks = _process_mma()
    if mma_picks:
        for p in mma_picks:
            print(f"  {p['home_team']} vs {p['away_team']} -> {p['pick']} @ {p['odds']:.2f}")
            print(f"    Confidence: {p['confidence']:.1f}%")
    else:
        print("  No MMA pick generated")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    total = len(football_picks) + len(basketball_picks) + len(volleyball_picks) + len(mma_picks)
    print("\n" + "=" * 60)
    print(f"  DRY-RUN SUMMARY: {total} total picks generated")
    print(f"    Football:   {len(football_picks)}")
    print(f"    Basketball: {len(basketball_picks)}")
    print(f"    Volleyball: {len(volleyball_picks)}")
    print(f"    MMA:        {len(mma_picks)}")
    print("=" * 60)

    if total == 0:
        print("\n  All models returned 0 picks. This may happen if:")
        print("    - Odds estimation pushed values below threshold")
        print("    - Confidence scores fell below 55% minimum")
        print("    - No real stats available (football uses empty defaults)")


if __name__ == "__main__":
    print("=" * 60)
    print("  SPORTS PREDICTION BOT -- DRY RUN")
    print("  No API calls will be made")
    print("=" * 60)
    inject_and_process()
