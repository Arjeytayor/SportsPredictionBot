"""Quick API health check."""
import requests
from config import API_SPORTS_KEY

print(f"API Key present: {'Yes' if API_SPORTS_KEY else 'No'}")
print("Testing fixtures endpoint for today...\n")

try:
    resp = requests.get(
        "https://v3.football.api-sports.io/fixtures",
        params={"date": "2026-06-13", "season": 2026, "league": 39},  # Premier League
        headers={"x-apisports-key": API_SPORTS_KEY},
        timeout=15,
    )
    data = resp.json()

    if "errors" in data and data["errors"]:
        print(f"  API ERROR: {data['errors']}")
    else:
        results = data.get("results", 0)
        print(f"  Response Code: {resp.status_code}")
        print(f"  Results count: {results}")
        print(f"  First 3 fixtures: {[(f['teams']['home']['name'], f['teams']['away']['name']) for f in data.get('response', [])[:3]]}")

        if results == 0:
            print("\n  No fixtures returned. Possible causes:")
            print("    - API quota exhausted (100 req/day on free tier)")
            print("    - API key quota reset hasn't happened yet")
            print("    - No Premier League fixtures scheduled today")

except requests.exceptions.RequestException as e:
    print(f"  Request FAILED: {e}")
except Exception as e:
    print(f"  Error: {e}")

print("\nDone." if results is not None else "\nFailed.")
