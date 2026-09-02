# How the models were measured, and why the answer is negative

This document is the measurement half of the project. The other half — the bot that
fetches fixtures, runs models and sends picks to Telegram — is described in
[`README.md`](README.md), and the full engineering log lives in
[`PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md).

It is written up separately because the measurement is the part worth reading. Building
a model that outputs three probabilities is a weekend. Establishing whether those
probabilities are worth anything is the actual work, and almost every published version
of this project skips it.

---

## The question

**Do any of these models know something the betting market does not?**

Not "are they accurate" — accuracy is easy to reach and means little. The question is
whether they hold information that is not already in the price. That is the only version
of the question with a decision attached to it, and it has a hard, unambiguous answer.

## The short answer

No. Four models, four ensembles of them, 15 leagues, 29,438 matches walked forward
chronologically, scored on a held-out window against Pinnacle's closing line:

| Forecast | RPS (lower is better) | Flat ROI | Value ROI | CLV |
|---|---|---|---|---|
| **Market (margin-free close)** | **0.1981** | −4.36% | +5.14% | — |
| Ensemble, linear, fitted weights | 0.2009 | −2.77% | −8.54% | −0.87% |
| Ensemble, log pool, fitted | 0.2015 | −3.00% | −7.60% | −0.92% |
| Ensemble, equal-weight mean | 0.2026 | −2.91% | −8.23% | −0.72% |
| XGBoost | 0.2032 | +0.57% | −3.38% | −0.91% |
| Dixon-Coles | 0.2065 | −6.06% | −12.88% | −0.97% |
| Pi ratings | 0.2119 | −0.85% | −4.16% | −0.59% |
| Poisson-ELO | 0.2176 | −5.60% | −8.28% | −0.39% |

*1,125 held-back matches. Bets struck at Pinnacle's opening price; the closing line is
the benchmark. A uniform 1/3-1/3-1/3 forecast scores RPS 0.2778.*

Nothing beats the close on forecast quality. Every model's closing-line value is
significantly negative. Betting only where a model disagrees with the market makes every
single model **worse**. That is not a tuning problem — it is what no edge looks like.

---

## The data

15 European league divisions from [football-data.co.uk](https://www.football-data.co.uk/):
England E0–E3 and EC (National League), Spain SP1/SP2, Italy I1/I2, Germany D1/D2,
France F1/F2, Netherlands N1, Portugal P1. Roughly 30,000 matches with results and odds.

The odds columns matter more than they look:

- `PSH/PSD/PSA` — Pinnacle's **opening** price.
- `PSCH/PSCD/PSCA` — Pinnacle's **closing** price.

These are not interchangeable, and the project got this wrong for two commits: the loader
always read the opening columns while every document said "closing". The measured margin
settles which is which — 4.61% at the open against 3.69% at the close. The close is
sharper, as it should be: it has absorbed team news, weather, and everyone else's money.

The correction turned out to run in the models' favour. They had been betting into the
*softer* of the two lines and still lost, so fixing the label strengthened the negative
result rather than rescuing it. That was luck, not care. The right move is to pin the
benchmark down before drawing any conclusion, not after.

The design now uses both lines deliberately:

- **Bets are struck at the open.** That is the price you could realistically have taken
  at the moment a prediction was made, and it is the more beatable one.
- **The close is the benchmark**, for both forecast quality and closing-line value.

## The four models

| Model | Kind | Fitting |
|---|---|---|
| Poisson-ELO | Poisson goal model driven by ELO ratings | incremental |
| Pi ratings | Rating system from Constantinou & Fenton | incremental |
| Dixon-Coles | Bivariate Poisson with the tau low-score correction | batch MLE, refit every 10 matches |
| XGBoost | Gradient-boosted classifier on rolling-form features | trained once on pre-2025-08-16 data |

Dixon-Coles is a batch solver, so walking it forward honestly means refitting as history
grows. Measured fit cost is 0.10–0.36s and flat in history length — it scales with team
count, not row count — so refitting on every match would cost about 84 minutes across all
15 leagues. Refitting every 10 matches costs about 8 minutes for at most one matchweek of
staleness, well below the noise being measured. Its time-decay weight is anchored on the
match being predicted rather than the end of the file; anchoring it on the file end would
leak the future into every early fit.

---

## Six ways to manufacture an edge that is not there

Each of these produces a confident, wrong, publishable-looking number. Each is closed
explicitly.

### 1. Lookahead

The classic. A team's rolling form is read **before** the match is scored, and updated
with the real result only **after**. No match ever contributes to its own prediction. The
backtest walks each league in date order for exactly this reason; vectorising it over the
whole file would be far faster and quietly wrong.

### 2. Scoring a model on data it was trained on

XGBoost was trained on history. Reporting its ROI over the full sample scores it largely
on matches it has memorised — and that full-sample figure is **+0.34%**, the only positive
headline number in the project. It is meaningless.

`XGB_HOLDOUT_START = 2025-08-16` splits the data. Only matches on or after it are out of
sample for all four models, and every headline number is restricted to that window.

### 3. Comparing models on different samples

Models fail on different matches — a team with too little history, a fit that does not
converge, a missing price. If each model is scored on whatever it happened to price, the
comparison is between different tournaments.

Everything is restricted to `common`, the intersection of matches **every** model
successfully scored: 26,910 of 29,438 overall, 5,837 in the holdout window. One
Dixon-Coles fit fails in the whole dataset (Bayern Munich v Greuther Fürth, negative
probabilities out of the tau correction); that match is dropped for all four models, not
just for Dixon-Coles.

### 4. Grading with the wrong metric

Accuracy records only which outcome ranked first. It cannot distinguish a model that says
50/30/20 from one that says 90/6/4, and it is blind to the draw, which is roughly a
quarter of all football results.

The primary metric is **RPS** (Ranked Probability Score), which scores the whole
distribution and respects that home/draw/away is ordered — being wrong by one position is
penalised less than being wrong by two. Lower is better; uniform scores 0.2778. The
implementation was cross-checked against `penaltyblog.metrics.rps_average` and agrees to
1.11e-16.

Accuracy is still reported, because it is what everyone asks for. It is 46–49% across the
four models, and it ranks them differently from RPS, which is the point.

### 5. No benchmark, or a flattering one

"RPS 0.21, better than the 0.2778 uniform baseline" is true and worthless. Beating an
uninformed guess is not the bar; the bar is the price you would have to beat to make
money.

The benchmark is Pinnacle's **closing** line with the margin divided out — implied
probabilities renormalised to sum to 1. That is the sharpest forecast the market produces
and the honest thing to compare against. It scores **0.1981**. Nothing here beats it.

The margin is removed for the *forecasting* comparison and deliberately **kept** for the
*betting* comparison, because you bet the price you are given, vig included.

### 6. Taking the best of many comparisons

With 15 leagues and 4 models there are 60 league-by-model cells, and something will look
profitable in a few of them by construction. Out-of-sample ROI across those 60 cells has a
standard deviation of 9.22% around a mean of −4.31%; 22 of them (37%) are positive.
Picking the best of 60 noisy draws should be expected to land around +2.5 SD. Any single
positive cell has to clear that bar before it means anything. See the Serie A section
below for the one that had to be argued down.

---

## Two betting books

**Flat book.** Back `argmax(p)` in every match, one unit, at the opening price. This is a
measurement device, not a strategy — it pays the margin on every ticket by construction
and is guaranteed to lose against a fair book. Its use is comparability.

**Value book.** Back outcome *i* only when

```
p_model[i] > (1 + edge) / price[i]
```

i.e. only where the model says the offered price is positive expected value. This is what
anyone would actually run. It bets less often and, if a model knows anything, should do
better than flat.

It does worse. For every model. That gap is the finding.

### Why value betting makes a good model look worse

Selecting on "my probability exceeds the market's implied probability" does not select
matches where the model is right. It selects matches where the model's number is
**higher** — which, when the market is better calibrated than the model, means matches
where the model is overconfident. The filter is a detector for the model's own errors,
pointed the wrong way. This is adverse selection, and it is why the best forecaster here
is the worst bettor: Dixon-Coles leads on both RPS and accuracy and posts the worst value
ROI at −12.88%.

---

## Closing-line value: the test that settles it

ROI on a few thousand bets is mostly noise. A 2% edge and a 2% loss are hard to separate
without tens of thousands of settled results, which is why so many betting systems look
alive for a season.

**Closing-line value** asks a different question: after we struck a bet at the open, did
the price move toward it by the close?

```
CLV = open_price / close_price − 1
```

If a model holds real information, the market should eventually agree with it, and the
prices it takes should shorten. CLV does not depend on who won, so it carries far less
variance than ROI — roughly a thousand bets say what tens of thousands of settled results
would. Beating the close is the standard evidence of an edge in this field. Losing to it
is proof of none.

| Selection | mean CLV | t vs 0 | % of bets beating the close |
|---|---|---|---|
| Poisson-ELO | −0.388% | −2.00 | 40.0% |
| Pi ratings | −0.587% | −3.39 | 39.6% |
| Ensemble mean | −0.718% | −3.74 | 38.8% |
| **back the favourite (no model)** | **−0.768%** | — | — |
| XGBoost | −0.910% | −4.64 | 37.6% |
| Dixon-Coles | −0.968% | −5.09 | 38.5% |
| *random bet (no selection)* | *−1.105%* | −8.67 | 39.9% |

**The baseline is −0.768%, not zero.** Backing the market favourite blindly, with no model
at all, earns that — short prices simply drift differently from long ones. Every model
here picks the favourite between 72% and 87% of the time, so the favourite baseline is the
comparator, not zero. Measuring against zero would let a model claim credit for a drift
pattern it did nothing to find.

**Dixon-Coles and XGBoost — the two best forecasters — do worse than the no-model
baseline.** And this is not a longshot artifact: Dixon-Coles picks favourites more often
than any other model (86.9%) and still posts the worst CLV of the four. It is genuinely
poor selection.

Poisson-ELO sits about 2 standard errors above the favourite baseline while taking longer
prices on average (2.15 against 1.99). Suggestive at best, and it does not survive the
context: four models were tested, it is the weakest forecaster of the four by RPS, and the
fitted ensemble gives it weight **0.00**.

---

## Does blending help?

Yes, and not nearly enough. `ensemble_eval.py` reuses the probability rows dumped by the
backtest so blends can be scored without re-running the walk-forward.

Weights are grid-searched on the first half of the priced holdout, and **everything —
market included — is scored on the held-back second half of 1,125 matches**. An earlier
version fitted on one sample and compared against a market scored on twice as many rows,
which is not a comparison at all.

- **Blending genuinely helps.** Even equal weights (0.2026) beat every individual model
  (best single: 0.2032). Fitting closes a little more, to 0.2009.
- **It is not enough.** The market sits at 0.1981. Ensembling closes roughly 40% of the
  gap between the best single model and the close, then stops.
- **The residual is not a weighting problem.** These models are all Poisson-family or
  form-based on the same features, so their errors are correlated. Averaging removes
  independent error; it cannot manufacture information none of them has.
- **Poisson-ELO earns weight 0.00** in both fitted pools. It carries nothing the other
  three lack — which is worth noting, because it is the model production actually runs.
- **Adverse selection survives ensembling.** The best-forecasting blend posts the second
  worst value ROI in the table (−8.54%).

Fitted weights, linear pool: XGBoost 0.50, Dixon-Coles 0.40, Pi ratings 0.10, Poisson-ELO
0.00. Log pool: Dixon-Coles 0.50, XGBoost 0.40, Pi ratings 0.10, Poisson-ELO 0.00.

---

## The one positive result, and why it is noise

Pi ratings returned **+6.39% over 1,849 Serie A picks** on the full sample — the single
positive that needed explaining. Per-league holdout columns were added to settle it, and
out of sample the figure did not shrink. It grew, to **+12.33%**.

It is still noise, on four independent grounds:

1. **It is not even the largest cell.** Across the 60 league-by-model cells, out-of-sample
   ROI has σ = 9.22% around a mean of −4.31%. Serie A / Pi ratings is 1.8 SD above that
   and only the *second* largest; Bundesliga 2 / XGBoost reaches +15.04%. Best-of-60 noisy
   draws should be expected near +2.5 SD, so +12.33% is *less* extreme than chance alone
   predicts.
2. **No other model shares it.** Serie A returns −1.72% (Poisson-ELO), +0.41% (XGBoost),
   −4.29% (Dixon-Coles). A genuinely soft league would lift all four.
3. **There is no forecast superiority behind it.** Pi ratings has the second-*worst* Serie
   A RPS of the four (0.2025 against XGBoost's 0.1937). Profit without better forecasts is
   luck, not edge.
4. **The value book erases it**: −2.81% over 287 bets. Value betting is the only strategy
   that could monetise a real edge, and it declines to.

The general point: a losing process with per-league samples of ~150 bets produces positive
cells at roughly this rate. None of them survives contact with a second question.

---

## The positive control

A negative result is only worth as much as the instrument that produced it. If the value
and CLV code simply never reported an edge, it would produce this exact output on a model
that had one.

So: feed the **margin-free closing line** in as if it were a forecast, and stake it at the
**opening** price.

It returns **+5.14% over 687 value bets.**

That is real and entirely expected — it amounts to "bet wherever the close disagrees with
the open", and the close is the sharper line. It is not a strategy; you cannot know the
close when you bet the open. Its purpose is diagnostic: the machinery detects an edge when
a genuine one is present. The models' negative results are therefore a finding about the
models, not an artifact of the measurement.

---

## What this does not cover

- **Basketball, volleyball and MMA** are in the codebase (~300 lines) and are entirely
  **unvalidated** — no local data, no trained artifact, no backtest coverage. That is a
  different statement from "measured and poor", and it is not softened here.
- **One market only.** Home/draw/away 1X2. Asian handicap, totals, and in-play are not
  touched, and it does not follow from this that no edge exists in them.
- **One bookmaker.** Pinnacle, chosen because it is the sharpest widely-quoted line and so
  the hardest benchmark. Softer books exist; whether these models beat *those* is not
  measured, and the CLV result makes it unlikely.
- **No stake sizing.** Flat unit stakes throughout. Kelly and its variants change the
  variance of a positive-edge strategy; they cannot turn a negative one positive.
- **No live execution.** Every number assumes the quoted opening price was available and
  takeable. Real limits, line moves and account restrictions are not modelled.

---

## Reproducing it

```bash
pip install -r requirements.txt

# Train the XGBoost model on pre-holdout history
python -c "from model_xgboost import train_xgboost_model; train_xgboost_model()"

# Walk-forward backtest, all four models, 15 leagues (~30 min)
python backtest.py

# Ensembles and closing-line value, off the dumped probability rows (seconds)
python ensemble_eval.py
```

`backtest.py` writes a full per-league breakdown to `logs/backtest_results.txt` and dumps
per-match probability rows to `logs/prob_rows.pkl`, which `ensemble_eval.py` reads so it
never has to re-run the walk-forward.

---

## What the exercise was worth

The honest summary is that four models were built and none of them beats the market, which
is the outcome anyone should expect: Pinnacle's closing line is one of the most efficient
prices in any public market, and beating it with public data and freely available model
families is not a realistic target.

What is worth keeping is that the project can *say so with confidence*, and can say
exactly why — a holdout that closes the in-sample trap, a common sample that makes the
models comparable, a proper scoring rule instead of accuracy, the market as the benchmark
instead of a uniform prior, closing-line value instead of noisy ROI, a multiplicity
correction on the one positive result, and a positive control proving the instrument
works.

The alternative version of this project reports 47.81% accuracy and +0.34% ROI, and is
wrong on both counts.
