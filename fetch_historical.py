"""Historical data fetcher -- pulls football-data.co.uk CSVs for many
leagues and seasons into data/historical/.

football-data.co.uk publishes one CSV per league per season at
    https://www.football-data.co.uk/mmz4281/<SEASON>/<CODE>.csv
where SEASON is the 4-digit short form ("2425" == 2024-25).

Seasons are concatenated per league and written to data/historical/<CODE>.csv,
sorted by date, so odds_loader.load_historical_csv() and backtest.py keep
working unchanged -- they just see far more matches.

Usage:
    python fetch_historical.py                # default 5 seasons, all leagues
    python fetch_historical.py --seasons 2425 # a single season
"""

import argparse
import io
from typing import List, Optional

import pandas as pd
import requests

from config import HISTORICAL_DIR
from logger import logger
from odds_loader import LEAGUE_FILES

BASE_URL = "https://www.football-data.co.uk/mmz4281"

# Most recent five completed/current seasons.
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425", "2526"]

# Columns the models and backtest actually rely on.
REQUIRED = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]


def fetch_one(season: str, code: str, timeout: int = 30) -> Optional[pd.DataFrame]:
    """Download a single league-season CSV. Returns None if unavailable."""
    url = f"{BASE_URL}/{season}/{code}.csv"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        # football-data.co.uk sends cp1252 bytes with no charset header, so
        # resp.text relies on requests guessing (and encoding= is ignored once
        # the input is a StringIO). Decode explicitly instead of by luck.
        text = resp.content.decode("latin-1")
        df = pd.read_csv(io.StringIO(text), on_bad_lines="skip")
    except Exception as exc:
        logger.warning(f"Could not fetch {url}: {exc}")
        return None

    if df.empty or not all(c in df.columns for c in REQUIRED):
        logger.warning(f"{url} missing required columns -- skipped.")
        return None

    df = df.dropna(subset=["HomeTeam", "AwayTeam"])
    df["Season"] = season
    return df


def fetch_league(code: str, seasons: List[str]) -> Optional[pd.DataFrame]:
    """Fetch and concatenate every available season for one league code."""
    frames = [df for df in (fetch_one(s, code) for s in seasons) if df is not None]
    if not frames:
        return None

    # .copy() de-fragments the concatenated frame; without it pandas warns on
    # every subsequent column insert.
    combined = pd.concat(frames, ignore_index=True, sort=False).copy()
    combined["_parsed_date"] = pd.to_datetime(
        combined["Date"], dayfirst=True, errors="coerce"
    )
    combined = combined.sort_values("_parsed_date").drop(columns=["_parsed_date"])
    return combined.reset_index(drop=True)


def fetch_all(seasons: List[str] = None) -> None:
    """Fetch every league in odds_loader.LEAGUE_FILES and write to disk."""
    seasons = seasons or DEFAULT_SEASONS
    total_matches = 0
    written = 0

    for league_key, code in LEAGUE_FILES.items():
        combined = fetch_league(code, seasons)
        if combined is None:
            print(f"  {code:<4} ({league_key:<22}) no data")
            continue

        path = HISTORICAL_DIR / f"{code}.csv"
        combined.to_csv(path, index=False, encoding="latin-1")
        n_seasons = combined["Season"].nunique()
        print(f"  {code:<4} ({league_key:<22}) {len(combined):>5} matches, {n_seasons} seasons")
        logger.info(f"Wrote {len(combined)} matches to {path}")
        total_matches += len(combined)
        written += 1

    print(f"\n{written} leagues written, {total_matches} matches total.")
    logger.info(f"Historical fetch complete: {written} leagues, {total_matches} matches.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch football-data.co.uk historicals")
    parser.add_argument(
        "--seasons", nargs="+", default=None,
        help=f"Season codes, e.g. 2425 2526 (default: {' '.join(DEFAULT_SEASONS)})",
    )
    args = parser.parse_args()
    print(f"Fetching into {HISTORICAL_DIR} ...")
    fetch_all(args.seasons)


if __name__ == "__main__":
    main()
