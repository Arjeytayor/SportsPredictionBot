# SportsPredictionBot

A Python sports-prediction pipeline covering football, basketball, volleyball, and MMA —
fetches daily fixtures, runs a dual prediction model per football match (Poisson + ELO and
a trained XGBoost classifier), enriches picks with NVIDIA NIM-generated analyst narratives,
and delivers results via a Telegram bot.

## What it does

- **Dual-model football predictions**: a Poisson + ELO hybrid and a trained XGBoost
  classifier (`model_xgboost.py`) run independently on every fixture; each pick is labeled
  with which model actually produced it (`source: trained` vs `source: fallback` when the
  trained model isn't available).
- **NVIDIA NIM integration** (`nim_enricher.py`): generates plain-English analyst
  explanations per pick via NIM-hosted LLMs (Mistral / Qwen / DeepSeek fallback chain),
  with retry/backoff and rate-limit handling.
- **Multi-sport support**: dedicated models for football (Poisson+ELO / XGBoost),
  basketball (point differential + home court), volleyball (set-based binomial), and MMA
  (custom ELO + streak/finish rate).
- **Telegram delivery**: scheduled daily fetch → predict → send cycle via APScheduler,
  with `/picks`, `/mega`, `/longshot`, `/results`, `/status` commands.
- **Backtesting** (`backtest.py`): walks each league's real historical results
  chronologically, scoring the actual production models (not a stand-in heuristic) with no
  lookahead — each prediction only sees a team's rolling form from strictly earlier
  matches. Latest run: **978 picks per model across Premier League / La Liga / Bundesliga**,
  full breakdown in [`logs/backtest_results.txt`](logs/backtest_results.txt).

## Project structure

See [`PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md) for the full engineering log — architecture,
every bug found and fixed, known gaps, and how the models were trained and validated. It's
kept as-is (including open issues) rather than cleaned up for appearances.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your own API keys
python main.py --no-bot   # scheduler only, no Telegram polling
```

Requires API-Sports (football/basketball/volleyball/MMA), a Telegram bot token, and an
NVIDIA NIM API key. Football historical data (for training/backtesting) comes from
[football-data.co.uk](https://www.football-data.co.uk/) — a small sample is included under
`data/historical/`.

## Train / backtest

```bash
# Train the XGBoost model on historical data
python -c "from model_xgboost import train_xgboost_model; train_xgboost_model()"

# Backtest both models against real historical outcomes
python backtest.py
```

## Known limitations

The free API-Sports tier (100 requests/day) can't cover a full day's fixture slate — see
`PROJECT_SUMMARY.md` §10 for the tradeoffs.

**No model here has a measured edge, and that is the honest headline.** Four football
models (Poisson-ELO, XGBoost, Pi ratings, Dixon-Coles) were backtested walk-forward
across 15 leagues and then re-scored on a held-out window, on an identical sample, against
Pinnacle's closing odds. Out-of-sample ROI is negative for all four (best: XGBoost at
−1.57%, against a bookmaker margin of roughly 2–3%). Betting only where a model prices an
outcome above the market — the strategy anyone would actually run — makes every model
*worse*, which is what adverse selection looks like. Full numbers and reasoning in
`PROJECT_SUMMARY.md` §13.

Accuracy (~46–49%) is reported alongside RPS, which is the metric that matters: accuracy
only records which outcome ranked first, while RPS scores the whole distribution.

The basketball, volleyball and MMA paths are **unvalidated** — no local data, no trained
artifact, no backtest coverage. That is different from measured and poor.
