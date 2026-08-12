import os, sys
sys.path.insert(0, r"C:\Users\DELL\Documents\SportsPredictionBot")

# Delete old model if exists
p = r"C:\Users\DELL\Documents\SportsPredictionBot\data\xgboost_football.json"
if os.path.exists(p):
    os.remove(p)
    print("Old model deleted")

# Retrain with corrected feature vector
from model_xgboost import train_xgboost_model
print("Retraining XGBoost model...")
result = train_xgboost_model()
print(f"Training result: {result}")

if result:
    from model_xgboost import predict_xgboost
    from nim_enricher import generate_nim_explanation
    
    # Test with xG data
    r = predict_xgboost("Arsenal", "Chelsea",
        [{"goals_for":2,"goals_against":1}],
        [{"goals_for":1,"goals_against":2}])
    print(f"Prediction: H={r['home_win']:.1%} D={r['draw']:.1%} A={r['away_win']:.1%}")
    
    # Test NIM explanation
    nim = generate_nim_explanation("Arsenal","Chelsea","Home Win",76.0,
        r["home_win"],r["draw"],r["away_win"],"XGBoost ML")
    print(f"NIM: {nim[:100]}..." if nim else "NIM: None (API key not set or NIM down)")
    
    print("\n[OK] Full pipeline test complete")
else:
    print("[ERR] Training failed")
