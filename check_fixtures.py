"""Check API-Sports for fixtures across multiple days."""
import requests
from datetime import datetime, timedelta
from config import API_SPORTS_KEY

headers = {"x-apisports-key": API_SPORTS_KEY}

def check_day(date_str):
    url = "https://v3.football.api-sports.io/fixtures"
    try:
        resp = requests.get(url, params={"date": date_str}, headers=headers, timeout=15)
        data = resp.json()
        results = data.get("results", 0)
        if results > 0:
            sample = [(f"{f['teams']['home']['name']} vs {f['teams']['away']['name']}") for f in data.get("response", [])[:2]]
            return results, sample
        return results, []
    except Exception as e:
        return -1, [str(e)]

# Check next 5 days
for i in range(5):
    day = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
    count, sample = check_day(day)
    print(f"{day}: {count} fixtures  {sample[:2] if sample else ''}")

print("\nDone.")
