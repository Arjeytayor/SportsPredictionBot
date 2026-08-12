"""Live end-to-end test of XGBoost + NIM pipeline."""
import sys
sys.path.insert(0, r"C:\Users\DELL\Documents\SportsPredictionBot")

from model_xgboost import predict_xgboost
from nim_enricher import generate_nim_explanation
from telegram_bot import format_pick

# Test XGBoost prediction
print("=" * 60)
print("LIVE XGBoost + NIM Pipeline Test")
print("=" * 60)

stats = [{"goals_for": 2, "goals_against": 0}]
result = predict_xgboost("Arsenal", "Chelsea", stats, stats)
print(f"\nXGBoost prediction: H={result['home_win']:.1%} D={result['draw']:.1%} A={result['away_win']:.1%}")

# Test NIM explanation
nim_text = generate_nim_explanation(
    "Arsenal", "Chelsea", "Home Win", 76.0,
    result["home_win"], result["draw"], result["away_win"], "XGBoost ML"
)
print(f"\nNIM explanation: {nim_text}")

# Test Telegram formatting with NIM
pick = {
    "sport": "Football",
    "league": "Premier League",
    "home_team": "Arsenal",
    "away_team": "Chelsea",
    "kickoff": "15:00",
    "pick": "Home Win",
    "confidence": 76.0,
    "value": 0.15,
    "odds": 1.85,
    "odds_source": "estimated",
    "model_source": "XGBoost ML",
    "model_home": result["home_win"],
    "reasons": ["Strong home form"],
    "warnings": [],
    "nim_explanation": nim_text,
}
msg = format_pick(pick)
print("\n--- Telegram Output ---")
print(msg)
print("\n" + "=" * 60)
print("[OK] Full pipeline test complete")
