"""Debug script -- step through the prediction pipeline and report."""

import os
import sys
from datetime import datetime

# --- Step 1: Check file paths ---
from config import BASE_DIR, DATA_DIR
state_path = DATA_DIR / "bot_state.json"
print(f"BASE_DIR: {BASE_DIR}")
print(f"DATA_DIR: {DATA_DIR}")
print(f"State file path: {state_path}")
print(f"State file exists: {state_path.exists()}")
print()

# --- Step 2: Run the pipeline ---
from scheduler import fetch_all_data, run_predictions, _todays_fixtures, _todays_picks

print("[1] Running fetch_all_data()...")
fetch_all_data()
print(f"    Football fixtures:   {len(_todays_fixtures.get('football', []))}")
print(f"    Basketball games:    {len(_todays_fixtures.get('basketball', []))}")
print(f"    Volleyball matches:  {len(_todays_fixtures.get('volleyball', []))}")
print(f"    MMA fights:          {len(_todays_fixtures.get('mma', []))}")
print()

print("[2] Running run_predictions()...")
run_predictions()
print(f"    Picks generated: {len(_todays_picks)}")

for p in _todays_picks:
    print(f"    - [{p.get('sport')}] {p.get('home_team','')} vs {p.get('away_team','')} -> {p.get('pick')} (conf: {p.get('confidence'):.1f}%, odds: {p.get('odds',0):.2f})")

print()
print(f"[3] Checking state file: {state_path}")
print(f"    Exists after run: {state_path.exists()}")
if state_path.exists():
    import json
    data = json.loads(state_path.read_text())
    print(f"    Saved picks: {len(data.get('picks', []))}")

print("\nDone." if _todays_picks or not _todays_fixtures.get('football') else "\nNo picks generated or no fixtures today.")
