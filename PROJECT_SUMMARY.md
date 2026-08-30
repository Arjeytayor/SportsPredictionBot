# 🎯 SportsPredictionBot — Project Summary & Progress Log

**Date:** 2026-06-13
**Status:** ✅ Core Architecture Complete | ⚠️ Partial Testing Done | 🔬 Ready for XGBoost Integration

---

## 📋 Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Structure](#2-directory-structure)
3. [Current Architecture](#3-current-architecture)
4. [All Fixes Applied](#4-all-fixes-applied)
5. [Issues Found & Solutions](#5-issues-found--solutions)
6. [Known Remaining Gaps](#6-known-remaining-gaps)
7. [Testing History](#7-testing-history)
8. [Next Steps: Dual-Model Integration](#8-next-steps-dual-model-integration)
9. [API Key Status](#9-api-key-status)
10. [Quick Start Commands](#10-quick-start-commands)

---

## 1. Project Overview

A Python-based sports prediction bot that fetches daily fixtures, runs prediction models, and sends picks via Telegram. Supports Football, Basketball, Volleyball, and MMA.

**Key Features:**
- Poisson + ELO hybrid for football (1X2 prediction)
- Point differential + home court for basketball
- Set-based binomial for volleyball
- UFC/MMA with custom ELO model
- Telegram bot with `/picks`, `/mega`, `/longshot`, `/results`, `/status`
- Daily scheduled fetch at 06:00, predictions at 06:30, sends at 07:00 (WAT Lagos)
- Lineup monitoring 65 min pre-kickoff
- Rolling 2-week rotating logs
- JSON persistence for state survival across restarts

---

## 2. Directory Structure

```
SportsPredictionBot/
├── main.py                    # Entry point — scheduler + Telegram bot
├── scheduler.py               # Orchestrates all daily jobs via APScheduler
├── telegram_bot.py            # All Telegram commands & message formatting
├── model_football.py          # Poisson + ELO hybrid model
├── model_basketball.py        # Point differential + home court (no ELO dependency)
├── model_volleyball.py        # Set-based binomial model
├── model_mma.py               # Custom ELO + streak/finish rate
├── data_fetch.py              # API-Sports calls with caching & budget tracking
├── elo_loader.py              # Club-ELO CSV download + name mapping (20+ teams)
├── value_checker.py           # Value betting formula + best odds extraction
├── confidence.py             # Multi-signal confidence scoring
├── odds_loader.py            # Historical odds CSV loader (football-data.co.uk)
├── backtest.py               # Historical backtesting module
├── result_checker.py         # W/L summary + logging
├── lineup_monitor.py         # Key player absence detection
├── persistence.py            # NEW — JSON state persistence (pick/results)
├── logger.py                 # NEW — 2-week rotating log + console + error log
├── config.py                 # Central config, paths, API keys, thresholds
├── .env                       # API keys (API_SPORTS_KEY, TELEGRAM_BOT_TOKEN, CHAT_ID)
├── cache/                    # API response caches (TTL managed)
├── data/                     # ELO CSV, historical data, bot_state.json
├── logs/                     # app.log (rotating), errors.log
├── test_bot.py              # Mock pick test + Telegram send test
├── demo.py                  # End-to-end demo with mock fixtures
├── force_send.py            # Force-send mock picks (bypasses API)
├── quick_test.py            # Quick Telegram bot token test
├── send_todays_picks.py     # Direct state-to-Telegram sender
├── dryrun.py                # Mock fixture dry-run (no API)
├── debug_run.py             # Full pipeline debug (real API, traces failures)
└── check_fixtures.py        # Check API for fixtures across next 5 days
```

---

## 3. Current Architecture

### Daily Schedule (WAT — Lagos timezone)
| Time | Job | What It Does |
|------|-----|-------------|
| 06:00 | `fetch_all_data()` | Fetches fixtures from all APIs (football, basketball, volleyball, MMA) |
| 06:30 | `run_predictions()` | Runs models on all fixtures, scores confidence, checks value |
| 07:00 | `send_morning_picks()` | Sends MEGA picks (>=75% confidence) to Telegram |
| ~kickoff-65min | `check_lineups()` | Fetches confirmed lineups, warns if key players missing |
| 23:30 | `check_results()` | Checks completed matches vs picks, logs W/L |

### Pick Generation Flow
```
fetch_all_data()                                              
  ├── football_fixtures (API-Sports v3)                       
  ├── basketball_games (balldontlie.io)                      
  ├── volleyball_fixtures (API-Sports v3)                     
  └── mma_fights (API-Sports v3)                             
        ↓                                                      
run_predictions()                                              
  ├── _process_football() — Poisson + ELO                    
  ├── _process_basketball() — Point diff only                  
  ├── _process_volleyball() — Set-based binomial               
  └── _process_mma() — Custom ELO (default 1500)              
        ↓                                                      
value_checker.is_value_bet() — filters picks                 
confidence.calculate_confidence() — scores confidence          
persistence.save_state() — persists to data/bot_state.json   
telegram_bot.store_picks() — keeps in memory for /picks      
```

---

## 4. All Fixes Applied

### Fix 1: `persistence.py` — NEW (State Persistence)
- **Problem**: Picks lost on bot restart (all in-memory)
- **Solution**: JSON file `data/bot_state.json` saves/loads picks & results by date
- **Functions**: `load_state()`, `save_state(picks, results)`
- **Integrated**: `telegram_bot.py` (save on store), `scheduler.py` (restore on startup, save after predictions)

### Fix 2: `data_fetch.py` — Team Form + Lineup Bypass
- **Added `fetch_football_team_form(team_id, season, last_n)`**: Fetches last N matches from API-Sports
- **Added `build_team_stats_from_form(team_id, fixtures)`**: Converts API response to `{"goals_for": x, "goals_against": y}` format
- **Fixed `fetch_football_lineups()`**: Now makes direct `requests.get()` call (bypasses `_api_get()` and cache writes)

### Fix 3: `elo_loader.py` — Name Mapping + Fuzzy Matching
- **Problem**: API-Sports names ("Manchester City") != Club-ELO names ("Man City") → ELO always 1500
- **Solution**: Added `_TEAM_NAME_MAPPINGS` dict with 20+ known name translations (English, Spanish, German, Italian, French, Portuguese, Dutch)
- **Added fuzzy matching**: Exact → mapped name → fuzzy substring → token overlap → 1500 default
- **Added in-memory caching**: Loads CSV once per day, not on every `get_team_elo()` call

### Fix 4: `model_basketball.py` — Decoupled from Football ELO
- **Problem**: Called `get_team_elo()` which loaded football (clubelo.com) ratings for basketball teams
- **Solution**: Removed `get_team_elo()` import entirely. Now takes optional `home_elo` / `away_elo` params for sport-specific ratings
- **Result**: Works standalone with point differential + home court advantage only

### Fix 5: `value_checker.py` — Fixed `get_best_odds()` API Structure
- **Problem**: Assumed flat `odds_data` list → returned single float. Broke on real API-Sports v3 response
- **Solution**: Now correctly parses `response[0].bookmakers[].bets[{name:"Match Winner", values}]`
- **Return type changed**: `Tuple[float, str]` → `Tuple[Dict[str, float], str]` (returns `{"Home": x, "Draw": y, "Away": z}`)

### Fix 6: `scheduler.py` — Wired All Sports, Real Stats, Fixidity, Edge Threshold
- **Football**: Now uses `fetch_football_team_form()` + `build_team_stats_from_form()` → no more empty `[], []`
- **All sports**: Basketball, Volleyball, MMA now processed by `_process_basketball()`, `_process_volleyball()`, `_process_mma()`
- **State restoration**: Tries to load persisted picks before regenerating
- **State validation**: Added `MIN_PROB_THRESHOLD = 0.38` — skips fixtures where no outcome has a meaningful edge (fixes "everything is Draw" problem)

### Fix 7: `telegram_bot.py` — Multi-Message Split, Disclaimer Fix, Error Handling
- **Max picks**: 15 → changed to **50** per `/picks` command
- **Message chunking**: `_reply_in_chunks()` automatically splits across multiple Telegram messages if text > 4096 chars
- **Disclaimer**: Only appears on the LAST message, not every sub-message
- **Error handling**: All commands wrapped in try-except → logs to `logs/app.log`, shows friendly error to user
- **Pick reloading**: Added `_ensure_picks_loaded()` / `_ensure_results_loaded()` so bot reads from disk when in-memory is empty

### Fix 8: `logger.py` — 2-Week Rotating Log
- **Problem**: Single error log only, no general activity log
- **Solution**: `TimedRotatingFileHandler` on `logs/app.log` (keeps 14 days, auto-deletes old)
- **Also**: Separate `logs/errors.log` (ERROR only), console output for visibility

---

## 5. Issues Found & Solutions

| # | Issue | Root Cause | Fix |
|---|-------|-----------|-----|
| 1 | `/picks` empty after fetch | API call hung / returned stale `bot_state.json` | Cleared state, added validation, re-fetched |
| 2 | Draw-only predictions | Model: 33.4%/33.1%/33.5% → "Draw" wins by 0.1% | Added `MIN_PROB_THRESHOLD = 0.38` — no edge = skip |
| 3 | 570 picks in state file, 0 showing | Telegram message >4096 chars → silent crash | Capped at 50, split across multiple messages |
| 4 | Pick refresh doesn't update bot | Separate Python processes = separate memory | Persistence + reload on every `/picks` call |
| 5 | ELO always 1500 | Name mismatch API-Sports vs Club-ELO | Name mapping table + fuzzy matching |
| 6 | Basketball model returns wrong odds | Used football ELO for basketball | Removed ELO dependency from basketball model |
| 7 | Duplicate lineup warnings | Lineup checks re-scheduled without dedup | Added `_scheduled_lineups` set to prevent duplicates |
| 8 | `/results` command empty | Results never persisted to disk | Added persistence save after every `check_all_results()` |

---

## 6. Known Remaining Gaps

| # | Gap | Impact | Plan |
|---|-----|--------|------|
| 1 | **Draw bias in Poisson** | Model undervalues draws despite most football matches ending in draws | Add Dixon-Coles `rho` correction factor |
| 2 | **No time decay on form** | Games 10 weeks ago weighted equally to last week | Add exponential weighting in `_process_football()` |
| 3 | **Basketball stats are empty** | Only point differential + home court, no box-score data | Integrate balldontlie stats API |
| 4 | **Volleyball stats missing** | No attack efficiency / serve error data | Currently falls back to defaults |
| 5 | **MMA fighter ELO hardcoded** | Both fighters start at 1500 | Build local Glicko-2 tracker |
| 6 | **No market-consensus (CLV)** | Model only vs. bookmaker odds (if available) | Could flip: Pinnacle odds as primary signal |
| 7 | ~~No historical accuracy tracking~~ | ~~Can't tell which model is better over time~~ | ✅ Fixed 2026-08-12 — see §12 |
| 8 | **Football model is basic Poisson** | Industry standard is Dixon-Coles or Bradley-Terry | **NEXT: XGBoost dual-model integration** |

---

## 7. Testing History

| Test | Command | Result |
|------|---------|--------|
| **Dry-run** (no API) | `python dryrun.py` | ✅ Football 1 pick, Basketball 1 pick, Volleyball/MMA 0 |
| **Telegram health** | `python quick_test.py` | ✅ Message sent, ID 23 |
| **Mock picks → Telegram** | `python force_send.py` | ✅ Both mock picks delivered |
| **Bot startup (--no-bot)** | `python main.py --no-bot` | ✅ Scheduler started, shutdown cleanly |
| **Full bot + polling** | `python main.py` | ✅ Responds to `/start`, `/status`, others |
| **State persistence** | `python test_state.py` | ✅ 570 picks, all confidence ≥ 55% |
| **API quota check** | `python check_fixtures.py` | ✅ 570 fixtures today, 380 tomorrow. Key is active. |
| **Debug run** | `python debug_run.py` | ⚠️ Ran but generated 0 fresh picks (state file existed, early-return) |
| **Fast debug** | `python debug_fast.py` | ✅ Creates state file, pick appears in `/picks` |
| **Full prediction** | `python -c "fetch_all_data(); run_predictions()"` | ⚠️ User ran but state was corrupted, restarted after fix |
| **User live test** (/picks) | Telegram `/picks` | ⚠️ Shows picks but heavily skewed to "Draw" before threshold fix. Now fixed with MIN_PROB. |
| **50-pick test** | Telegram `/picks` after max=50 | ✅ Sends top 50 across multiple messages |

---

## 8. Phase 2 Complete: Dual-Model + NVIDIA NIM AI (2026-06-13/14)

### ✅ What Was Built

| Feature | Module | Status |
|---------|--------|--------|
| **XGBoost ML model** | `model_xgboost.py` | ✅ Created + trained on football-data.co.uk |
| **Dual-model per fixture** | `scheduler.py` | ✅ Poisson-ELO + XGBoost both run on each match |
| **Model attribution** | `telegram_bot.py` | ✅ Header shows `Football · Premier League \| XGBoost ML` |
| **NIM AI Explanations** | `nim_enricher.py` | ✅ Plain-English analyst narrative per pick |
| **NIM retry + fallback** | `nim_enricher.py` | ✅ Auto-retries with backoff, falls back to deepseek |
| **XGBoost fallback heuristic** | `model_xgboost.py` | ✅ Fallback works when no trained model exists |
| **Windows console fixes** | `main.py`, `telegram_bot.py`, `data_fetch.py` | ✅ Replaced all unicode emojis with ASCII |
| **Cache key fix** | `data_fetch.py` | ✅ Slashes → underscores for Windows paths |

### Test Results (all pass)
| Test | Result |
|------|--------|
| `test_dual_model.py` | ✅ ALL PASS (XGBoost, Telegram format, scheduler, persistence, trained model) |
| `test_nim_live.py` | ✅ NIM generates analyst-quality prose live |
| Import test | ✅ All NIM-integrated modules load OK |

---

## 9. API Key Status

| API | Key Present | Status | Limit / Notes |
|-----|-------------|--------|---------------|
| API-Sports (Football) | ✅ Yes | Active | 100 req/day free tier — **BLOCKER for full pipeline** |
| API-Sports (Basketball) | ✅ Shared key | Active | Part of 100/day pool |
| API-Sports (Volleyball) | ✅ Shared key | Active | Part of 100/day pool |
| API-Sports (MMA) | ✅ Shared key | Active | Part of 100/day pool |
| balldontlie (Basketball) | 🚫 No key needed | Active | Free, no key required |
| Telegram Bot | ✅ Yes | Active | N/A |
| **NVIDIA NIM** | **✅ Yes (nvapi-...)** | **Active** | **Free tier — retry + fallback configured** |

---

## 10. Production Blocker

**API-Sports free tier (100 req/day) cannot support the full 380-fixture pipeline.**

| Current | 380 fixtures × (form + H2H + odds) ≈ 1,500+ calls | ❌ Budget exhausted after ~5 fixtures |
| Option 1 | Filter to top 5 leagues only (~30 fixtures) | ✅ Fits in 100/day, no cost |
| Option 2 | Upgrade API-Sports plan ($4.99/mo = 300/day) | ✅ Everything works as built |
| Option 3 | Leave as-is | ⚠️ Works but `/picks` returns empty on days with many fixtures |

---

## 11. Quick Start Commands

```bash
cd C:\Users\DELL\Documents\SportsPredictionBot

# Start bot (scheduler + Telegram polling)
python main.py

# Start without Telegram
python main.py --no-bot

# Generate picks manually (clears old state, fetches, predicts)
python -c "from scheduler import _todays_fixtures, run_predictions; run_predictions()"

# Train XGBoost on fresh historical data
python -c "from model_xgboost import train_xgboost_model; train_xgboost_model()"

# Test live NIM integration
python test_nim_live.py

# Test dual-model end-to-end
python test_dual_model.py

# Check API keys and fixtures
python check_fixtures.py

# Clear stale cache
Remove-Item -Recurse -Force __pycache__

# View logs
type logs\app.log
type logs\errors.log
```

---

## 12. Phase 3: Real Trained Model + Honest Model Attribution + Real Backtest (2026-08-12)

### Problems found on review
- `data/xgboost_football.json` didn't exist — `predict_xgboost()` was always silently
  using `_fallback_predict()` (a hand-written heuristic), but `scheduler.py` hardcoded
  the label `"XGBoost ML"` regardless of which path actually ran. Every live pick ever
  labeled XGBoost ML was really the heuristic.
- `backtest.py`'s `model_predict()` was a disconnected placeholder — it inverted B365
  odds columns rather than calling the real Poisson-ELO or XGBoost models, so "backtest
  accuracy" never reflected the models actually deployed. No `results.log` had ever
  been produced.

### Fixes applied
- **Trained the real XGBoost model**: `python -c "from model_xgboost import train_xgboost_model; train_xgboost_model()"` on the existing E0/SP1/D1 historicals — `data/xgboost_football.json` now exists (100 boosted rounds, loads and predicts correctly).
- **`model_xgboost.py`**: `predict_xgboost()` now returns `"source": "trained"` or `"source": "fallback"` so callers know which path actually produced a given prediction.
- **`scheduler.py`**: pick labeling now reads that `source` flag — only says `"XGBoost ML"` when the trained model genuinely ran; otherwise labels it `"XGBoost (fallback heuristic)"`. No more silent mislabeling.
- **`backtest.py`**: rewritten to walk each league chronologically, building each team's rolling form match-by-match and scoring the *actual* production models (`predict_football`, `predict_xgboost`) — never the match's own outcome (no lookahead). Real run: **978 picks per model across Premier League / La Liga / Bundesliga** — Poisson-ELO 48.67% accuracy / -7.03% ROI, XGBoost 45.91% accuracy / -1.94% ROI vs Pinnacle odds. Full breakdown in `logs/backtest_results.txt`. *(Superseded by §13 — that run covered 3 leagues and 2 models, and its ROI was computed over matches XGBoost had trained on.)*
- `test_dual_model.py` re-run and still passes end-to-end after all changes.

### Still open
- API-Sports free tier (100 req/day) remains the live-pipeline blocker (§10/§11) —
  unrelated to model correctness, not addressed in this pass.
- Backtest accuracy (~46-49%) and negative ROI are honest results, not a marketing
  number — flat-staking every model pick against the market is a hard way to turn a
  profit and isn't expected to be profitable; the value is in the methodology being
  real and reproducible, not in the ROI being positive.

---

## 13. Phase 4: Four Models, 15 Leagues, and an Honest Answer on Profitability (2026-08-29/30)

Covers two commits that were never written up (`84b01a1`, `89c3134`) plus the
out-of-sample evaluation that followed.

### What was added
- **15 leagues** of football-data.co.uk history (E0–E3, EC, SP1/SP2, I1/I2, D1/D2,
  F1/F2, N1, P1) replacing the original three, via a new `fetch_historical.py`.
- **Two more models**, taking the roster to four: **Pi ratings** (`84b01a1`) and
  **Dixon-Coles** (`89c3134`) — batch MLE with the tau low-score correction, wrapped
  walk-forward by `_DixonColesFitter` (refit every 10 matches, 200-match minimum,
  time-decay xi = 0.0018 with the decay anchored on the match being predicted, not the
  end of the file, which would leak the future).
- **RPS (Ranked Probability Score)** as the primary forecast metric. Accuracy throws
  away everything except which outcome ranked first; RPS scores the whole distribution
  and respects the ordering of home/draw/away. Uniform = 0.2778.
- **XGBoost trainer rebuilt** (`89c3134`), and the `model_xgboost.py` internals reworked.

### The measurement problem this pass fixed
The single ROI figure the report had always quoted was computed over **every** match —
including the ~80% that XGBoost was trained on. It flattered that model and could not
answer the only question that matters: *is any of this profitable?*

Two changes fixed it:
1. **A holdout window.** `XGB_HOLDOUT_START = 2025-08-16`; only matches on or after it
   are out-of-sample for all four models. RPS and ROI are also restricted to `common`,
   the intersection of matches every model successfully scored, so the four books run
   on an identical sample (2,253 flat bets) and are directly comparable.
2. **A value-bet track.** Backing the model's favourite in every match is not a strategy
   anyone would run — it pays the bookmaker's margin on every ticket by construction.
   The value book bets outcome *i* only when `p_model[i] > (1 + edge) / price[i]`, i.e.
   positive EV at the offered price. The margin is deliberately **not** removed: you bet
   the price you are given.

### Results (out-of-sample, identical sample, Pinnacle opening odds)

| Model | Accuracy | RPS | Flat ROI | Value ROI |
|---|---|---|---|---|
| dixon_coles | 48.71% | **0.2112** | −6.03% | **−9.09%** (n=2442) |
| xgboost | 47.81% | 0.2152 | **−1.57%** | −1.75% (n=2619) |
| pi_ratings | 46.02% | 0.2182 | −2.88% | −4.83% (n=3246) |
| poisson_elo | 47.12% | 0.2250 | −6.43% | −6.68% (n=2490) |

Margin-free Pinnacle scores **0.2042** — better than all four. (That is the margin-free *opening* line; benchmarked against the sharper **close** the market scores **0.1981**, so the gap is wider still. See the correction below.)

### What the numbers say
- **Nothing is profitable out-of-sample.** XGBoost's −1.57% is the least-bad, but
  Pinnacle's margin is roughly 2–3%, so that is a model performing near the market and
  paying the vig. A smaller loss, not an edge.
- **Value betting is worse than flat betting for every single model.** Where these
  models disagree with the close, the close is right. Textbook adverse selection:
  filtering for "my probability exceeds the market's" preferentially selects the matches
  where the model's probability is too high.
- **The best forecaster is the worst bettor.** Dixon-Coles leads on both RPS and
  accuracy and posts the worst value ROI. Good overall calibration concentrates the
  *residual* disagreements with the market in genuine overconfidence — exactly what
  value selection targets. Ranking by forecast quality does not rank by profitability.
- **Any full-sample XGBoost ROI is in-sample and must be ignored**, including the
  +0.34% the report shows. This is the specific trap the holdout window exists to close.

### The Serie A anomaly, and why it is nothing
Pi ratings showed **+6.39% ROI over 1,849 Serie A picks** on the full sample — the one
positive that needed explaining. Per-league holdout columns were added to settle it. Out
of sample the figure did not shrink; it grew to **+12.33%**. It is still noise:

- Across all **60 league x model cells**, out-of-sample ROI has a standard deviation of
  **9.22%** around a mean of -4.31%. Serie A / pi ratings sits 1.8 SD above that mean and
  is only the *second* largest cell (Bundesliga 2 / XGBoost reaches +15.04%). Taking the
  best of 60 noisy draws would be expected to land near +2.5 SD, so +12.33% is *less*
  extreme than chance alone predicts.
- **The other three models do not share it**: Serie A returns -1.72% (poisson_elo),
  +0.41% (xgboost), -4.29% (dixon_coles). A genuinely soft league would lift all four.
- **There is no forecast superiority behind it.** Pi ratings has the second-worst RPS of
  the four in Serie A (0.2025 vs XGBoost's 0.1937). Profit without better forecasts is
  luck, not edge.
- **The value book erases it**: -2.81% over 287 bets. Value betting is the only strategy
  that could monetise a real edge, and it declines to.

Generalising: 22 of 60 cells (37%) are positive out-of-sample, which is what you get from
a losing process with per-league samples of ~150 bets. No league survives as an edge.

### Does an ensemble beat the market? No -- but it beats every single model
`ensemble_eval.py` reuses the probability rows dumped by `backtest.py`
(`logs/prob_rows.pkl`, gitignored) so blends can be scored without re-running the
walk-forward. Weights are grid-searched on the first half of the priced holdout and
**everything -- market included -- is scored on the held-back second half (1,125
matches)**. Note this is the *priced* subset, so RPS here is not comparable to the
`rps_holdout` figures above, which cover all 5,837 common holdout matches.

| Forecast | RPS | Flat ROI | Value ROI |
|---|---|---|---|
| **MARKET (margin-free close)** | **0.1981** | -4.36% | +5.14% |
| ENSEMBLE linear (fitted) | 0.2009 | -2.77% | -8.54% |
| ENSEMBLE logpool (fitted) | 0.2015 | -3.00% | -7.60% |
| ENSEMBLE mean (equal weight) | 0.2026 | -2.91% | -8.23% |
| xgboost | 0.2032 | +0.57% | -3.38% |
| ENSEMBLE logpool (equal weight) | 0.2036 | -4.11% | -5.60% |
| dixon_coles | 0.2065 | -6.06% | -12.88% |
| pi_ratings | 0.2119 | -0.85% | -4.16% |
| poisson_elo | 0.2176 | -5.60% | -8.28% |

Fitted weights: dixon_coles 0.40, xgboost 0.50, pi_ratings 0.10, **poisson_elo 0.00**.

- **Blending genuinely helps.** Even equal weights (0.2026) beat every individual model.
  Fitting closes a little more, to 0.2009.
- **It is not enough.** The market sits at 0.1981. Ensembling closes roughly 40% of the
  gap between the best single model and the close, and stops there. The residual is not
  a weighting problem -- these models are all Poisson-family or form-based on the same
  features, so their errors are correlated and averaging cannot remove what none of them
  knows.
- **Poisson-ELO earns weight 0.00.** The fitted blend discards it entirely; it carries no
  information the other three lack. Dixon-Coles 0.50, XGBoost 0.40, Pi ratings 0.10.
- **Adverse selection survives ensembling.** The best forecaster here posts the *second
  worst* value ROI (-9.33%). Better probabilities did not translate into better bets.
- XGBoost's +0.57% flat on this half is noise on 1,125 bets, and its own value book
  (-3.38%) contradicts it.

This closes the modelling question: no individual model and no combination of them beats
Pinnacle's closing line, so there is no edge here to stake.

### Correction: those are OPENING odds, not closing
football-data.co.uk ships two Pinnacle lines: `PSH/PSD/PSA` are the **opening** prices
and `PSCH/PSCD/PSCA` the **closing** ones. `odds_loader.py` has always read the opening
columns, while this file, the README, the report and commit `abdf36d` all said "closing
odds". Every number was internally consistent; the label was wrong.

Which way it cuts matters: the open is the *softer* line (margin 4.61% vs 3.69% at the
close). The models were betting into the more beatable price and still lost, so the
negative result survives and strengthens. That was luck rather than care -- the benchmark
should have been pinned down before any conclusion was drawn.

Now fixed: bets are still struck at the **open**, which is the price you could actually
take when the prediction is made, and the **close** is used as the forecasting benchmark
and for closing-line value.

### Closing-line value: the definitive test, and it is negative
CLV asks whether the price moved toward a bet after it was struck. If a model knows
something, the market should end up agreeing with it. It does not depend on who won, so
it carries far less variance than ROI -- roughly a thousand bets say what tens of
thousands of settled results would. Scored on the same held-back 1,125 matches:

| Selection | mean CLV | t vs 0 | % of bets beating the close |
|---|---|---|---|
| poisson_elo | -0.388% | -2.00 | 40.0% |
| pi_ratings | -0.587% | -3.39 | 39.6% |
| ENSEMBLE mean | -0.718% | -3.74 | 38.8% |
| **back the favourite (no model)** | **-0.768%** | -- | -- |
| xgboost | -0.910% | -4.64 | 37.6% |
| dixon_coles | -0.968% | -5.09 | 38.5% |
| *random bet, no selection* | *-1.105%* | -8.67 | 39.9% |

- **Every model has significantly negative CLV.** None beats the close. This is the
  cleanest statement of the whole exercise: there is no edge here.
- **The right baseline is -0.768%, not zero.** Backing the market favourite blindly earns
  that, purely because short prices drift differently from long ones. Every model picks
  the favourite 72-87% of the time, so that is what they must be measured against.
- **Dixon-Coles and XGBoost -- the two best forecasters -- do worse than backing the
  favourite blindly.** Dixon-Coles picks favourites most often of all (86.9%) and still
  posts the worst CLV, so this is not a longshot artifact; it is genuinely poor selection.
- Poisson-ELO sits ~2 SE above the favourite baseline while taking *longer* prices (2.15
  vs 1.99). Suggestive at best: four models were tested, and it is the weakest forecaster
  of the four and earns weight 0.00 in the ensemble.

### The machinery works -- a positive control
The margin-free **closing** line, used as a forecast and staked at the **opening** price,
returns **+5.14% on 687 value bets**. That is real and expected: it is just "bet where
the close disagrees with the open", and the close is the sharper line. It matters because
it proves the value-betting and CLV code detects an edge when a genuine one is present.
The models' negative results are therefore a finding about the models, not an artifact of
the measurement.

### Still open / not measured
- **Basketball, volleyball and MMA** (~300 lines) have no local data, no trained
  artifact and no backtest coverage. They are genuinely **unvalidated** — not "measured
  and poor". Reviving basketball needs a free balldontlie API key in `.env`.
- One Dixon-Coles fit fails out of ~30k matches (Bayern Munich v Greuther Furth —
  negative probabilities from the tau correction). Caught by the existing handler; the
  match goes unscored and is dropped from `common` for all four models.
- `odds_loader.py`: the league key `championship_playoffs` was a mislabel and is now
  `national_league`. `EC` is football-data.co.uk's National League (English 5th tier).
  The data was always right; the name wasn't, and no data moved.

---

## 📌 Last Updated: 2026-08-30

**Current status**: Phase 4 complete — four football models measured out-of-sample on an
identical sample against Pinnacle's close, on both a flat and a value-bet book. The
headline finding is negative and is meant to be: no model shows an edge, and selecting
for value makes every one of them worse. The value here is that the measurement is now
trustworthy enough to say so.

**The open decision** (blocks what gets built next):
- **Live bot** — keep pushing toward a running prediction service, which means solving
  the API-Sports tier blocker (§10) and accepting that the picks have no measured edge.
- **Portfolio piece** — treat this as a finished, honest modelling study. The
  walk-forward methodology, RPS benchmarking against the closing line, and the
  adverse-selection result are the interesting output, and they already exist.

**Also blocked on**: a free balldontlie API key (`BALLDONTLIE_KEY` in `.env`) if
basketball is worth reviving.

**Pending options** (still open from Phase 2):
- **A) Filter to top-5 leagues** — fits free tier, 30 min of coding, run production same day
- **B) Upgrade API-Sports** — $19/mo, full 380-fixture pipeline, no code changes
- **C) Add Understat xG** — live xG enrichment per fixture, requires Path A or B first
