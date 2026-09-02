# SportsPredictionBot

A Python football-prediction pipeline and the measurement study that grades it. Four
forecasting models are walked forward across 15 European leagues and 29,438 matches, then
scored out-of-sample against Pinnacle's closing line. A Telegram bot delivers daily picks;
basketball, volleyball and MMA paths exist but are unvalidated.

**The headline finding is negative, and that is the point of the project.** No model here
beats the market, no combination of them does either, and betting only where a model
disagrees with the price makes every single one of them worse.

## The result

| Forecast | RPS (lower is better) | Flat ROI | Value ROI | CLV |
|---|---|---|---|---|
| **Market (margin-free close)** | **0.1981** | −4.36% | +5.14% | — |
| Best ensemble (fitted linear) | 0.2009 | −2.77% | −8.54% | −0.87% |
| XGBoost | 0.2032 | +0.57% | −3.38% | −0.91% |
| Dixon-Coles | 0.2065 | −6.06% | −12.88% | −0.97% |
| Pi ratings | 0.2119 | −0.85% | −4.16% | −0.59% |
| Poisson-ELO | 0.2176 | −5.60% | −8.28% | −0.39% |

*1,125 held-back matches, identical sample for every row. Bets struck at Pinnacle's
opening price; the closing line is the benchmark. Uniform 1/3-1/3-1/3 scores RPS 0.2778.*

Closing-line value — whether the price moved toward a bet after it was struck — is
significantly negative for all four models. Backing the market favourite with no model at
all scores −0.768%; Dixon-Coles and XGBoost, the two *best* forecasters, do worse than
that. The measurement code is not simply blind to edges: fed the margin-free closing line
as a forecast, it correctly finds +5.14% over 687 value bets.

**[`METHODOLOGY.md`](METHODOLOGY.md) is the full study** — the six ways to manufacture a
fake edge and how each is closed, why value betting inverts model quality, why the one
profitable league is noise, and what the exercise does not cover.

## What the pipeline does

- **Four football models**: Poisson + ELO, a trained XGBoost classifier, Pi ratings, and
  Dixon-Coles with the tau low-score correction. Every pick records which model produced
  it (`source: trained` vs `source: fallback`).
- **Walk-forward backtesting** (`backtest.py`): each league's real history in date order,
  with a team's rolling form read strictly before a match is scored and updated only
  after. Writes a per-league breakdown to
  [`logs/backtest_results.txt`](logs/backtest_results.txt).
- **Out-of-sample evaluation** (`ensemble_eval.py`): linear and log-pool ensembles,
  value-bet books, and closing-line value against the market benchmark.
- **NVIDIA NIM integration** (`nim_enricher.py`): plain-English analyst notes per pick via
  NIM-hosted LLMs (Mistral / Qwen / DeepSeek fallback chain), with retry and rate-limit
  handling.
- **Telegram delivery**: scheduled daily fetch → predict → send cycle via APScheduler,
  with `/picks`, `/mega`, `/longshot`, `/results`, `/status`.
- **Other sports**: basketball (point differential + home court), volleyball (set-based
  binomial), MMA (custom ELO + streak/finish rate). See the limitations below.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your own API keys
python main.py --no-bot   # scheduler only, no Telegram polling
```

Requires API-Sports (football/basketball/volleyball/MMA), a Telegram bot token, and an
NVIDIA NIM API key. Football historical data comes from
[football-data.co.uk](https://www.football-data.co.uk/) — a sample is included under
`data/historical/`.

## Train and measure

```bash
# Train the XGBoost model on pre-holdout history
python -c "from model_xgboost import train_xgboost_model; train_xgboost_model()"

# Walk-forward backtest, four models, 15 leagues (~30 min)
python backtest.py

# Ensembles and closing-line value (seconds — reads the dumped probability rows)
python ensemble_eval.py
```

## Known limitations

**No model here has a measured edge.** Out-of-sample ROI is negative for all four against
a bookmaker margin of roughly 2–3%, and closing-line value is significantly negative for
every one of them. The least-bad figures are near-market performance paying the vig, not
an edge. Value betting — the only strategy that could monetise a real edge — makes every
model worse, which is what adverse selection looks like. Full numbers and reasoning in
[`METHODOLOGY.md`](METHODOLOGY.md).

Accuracy (~46–49%) is reported alongside RPS, which is the metric that matters: accuracy
only records which outcome ranked first, while RPS scores the whole distribution.

The basketball, volleyball and MMA paths are **unvalidated** — no local data, no trained
artifact, no backtest coverage. That is different from measured and poor.

The free API-Sports tier (100 requests/day) cannot cover a full day's fixture slate — see
`PROJECT_SUMMARY.md` §10 for the tradeoffs.

## Project structure

[`PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md) is the full engineering log — architecture,
every bug found and fixed, known gaps, and how the models were trained and validated. It
is kept as-is, open issues included, rather than cleaned up for appearances.
