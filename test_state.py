"""Verify that state file loads and filtering works."""
from persistence import load_state

state = load_state()
picks = state.get("picks", [])
print(f"State has {len(picks)} picks")
filtered = [p for p in picks if p.get("confidence", 0) >= 55.0]
print(f"After filtering (>=55%): {len(filtered)} picks")
if filtered:
    p = filtered[0]
    print(f"  First: {p['home_team']} vs {p['away_team']} -> {p['pick']} (conf: {p['confidence']:.1f}%)")
    print(f"  Odds: {p['odds']} ({p['odds_source']})")
else:
    print("  No picks with confidence >= 55.0")
