"""Fast debug -- run football model directly with only mock data."""
from model_football import predict_football

# Simulate a real football fixture with some recent stats
home_stats = [
    {"goals_for": 2, "goals_against": 1},
    {"goals_for": 3, "goals_against": 0},
    {"goals_for": 1, "goals_against": 1},
    {"goals_for": 2, "goals_against": 2},
    {"goals_for": 1, "goals_against": 0},
]

away_stats = [
    {"goals_for": 1, "goals_against": 2},
    {"goals_for": 0, "goals_against": 3},
    {"goals_for": 1, "goals_against": 1},
    {"goals_for": 2, "goals_against": 2},
    {"goals_for": 0, "goals_against": 1},
]

result = predict_football("Arsenal", "Liverpool", home_stats, away_stats)
print("Football prediction (with team stats):")
print(f"  Home Win: {result['home_win']:.1%}")
print(f"  Draw:     {result['draw']:.1%}")
print(f"  Away Win: {result['away_win']:.1%}")
print(f"  BTTS:     {result['btts']:.1%}")
print(f"  Over2.5:  {result['over_2_5']:.1%}")

# Also check persistence can write
from persistence import save_state, load_state
import os

test_picks = [
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
        "model_home": result["home_win"],
        "reasons": [f"Model probability: {result['home_win']:.1%}"],
        "warnings": [],
    }
]

save_state(test_picks, [])
state = load_state()
print(f"\nPersistence test: {len(state['picks'])} picks loaded from {state['date']}")
print(f"  First pick: {state['picks'][0]['home_team']} vs {state['picks'][0]['away_team']}")

print("\nYou can now send /picks in Telegram — the pick should appear!")
