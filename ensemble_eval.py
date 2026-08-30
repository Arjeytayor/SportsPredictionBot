"""Does combining the four models beat any of them -- or the market?

Every individual model loses to Pinnacle's margin-free close on RPS. The
obvious follow-up is whether a blend holds information none of them has alone,
so this scores several ensembles on the same holdout sample the backtest uses.

Reads the probability rows dumped by `python backtest.py` (logs/prob_rows.pkl)
so it never has to re-run the walk-forward.

    python ensemble_eval.py
"""

import pickle
from typing import Dict, List, Sequence, Tuple

import numpy as np

from backtest import XGB_HOLDOUT_START, _flat_roi, _value_roi
from config import LOGS_DIR

DUMP_PATH = LOGS_DIR / "prob_rows.pkl"


def rps(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean Ranked Probability Score for ordered 3-way outcomes.

    Lower is better; a uniform forecast scores 0.2778. Unlike accuracy this
    scores the whole distribution and respects that home/draw/away is ordered,
    so a confident wrong pick is punished more than a hesitant one.
    """
    cum_p = np.cumsum(probs, axis=1)[:, :2]
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(outcomes)), outcomes] = 1.0
    cum_o = np.cumsum(onehot, axis=1)[:, :2]
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1) / 2.0))


def market_probs(odds: np.ndarray) -> np.ndarray:
    """Pinnacle's implied probabilities with the margin divided out.

    This is the benchmark to beat on forecast quality. It is NOT what you get
    to bet at -- betting happens at the raw price, margin included.
    """
    inv = 1.0 / odds
    return inv / inv.sum(axis=1, keepdims=True)


def load_rows() -> Tuple[List[str], Dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    """Flatten the per-league dump into aligned arrays over the holdout window."""
    with open(DUMP_PATH, "rb") as fh:
        dump = pickle.load(fh)

    models = sorted({m for lg in dump.values() for m in lg})
    probs: Dict[str, List[List[float]]] = {m: [] for m in models}
    outcomes: List[int] = []
    odds_rows: List[List[float]] = []
    close_rows: List[List[float]] = []

    for league, by_model in dump.items():
        if set(by_model) != set(models):
            raise SystemExit(f"{league}: model set mismatch {sorted(by_model)}")

        ref = by_model[models[0]]
        for m in models[1:]:
            if [r[0] for r in by_model[m]] != [r[0] for r in ref]:
                raise SystemExit(f"{league}: rows not aligned across models")

        for i, (_key, date, _p, outcome, odds, close) in enumerate(ref):
            if date is None or date < XGB_HOLDOUT_START:
                continue
            # Need both lines: the open is what you bet, the close is the
            # benchmark and the thing CLV measures movement against.
            if min(odds) <= 0 or min(close) <= 0:
                continue
            for m in models:
                probs[m].append(list(by_model[m][i][2]))
            outcomes.append(outcome)
            odds_rows.append(list(odds))
            close_rows.append(list(close))

    return (
        models,
        {m: np.asarray(v, dtype=float) for m, v in probs.items()},
        np.asarray(outcomes, dtype=int),
        np.asarray(odds_rows, dtype=float),
        np.asarray(close_rows, dtype=float),
    )


def linear_pool(stack: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted arithmetic mean of model probabilities."""
    return np.tensordot(w, stack, axes=(0, 0))


def log_pool(stack: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted geometric mean, renormalised.

    Sharper than the linear pool: it suppresses outcomes any member thinks are
    unlikely, rather than averaging that disagreement away.
    """
    logs = np.tensordot(w, np.log(np.clip(stack, 1e-9, None)), axes=(0, 0))
    ex = np.exp(logs - logs.max(axis=1, keepdims=True))
    return ex / ex.sum(axis=1, keepdims=True)


def fit_weights(stack: np.ndarray, outcomes: np.ndarray, pool) -> np.ndarray:
    """Grid-search simplex weights minimising RPS. Coarse but deterministic."""
    n = stack.shape[0]
    best_w, best = np.full(n, 1.0 / n), float("inf")
    step = 0.1
    grid = np.arange(0.0, 1.0 + step / 2, step)

    def recurse(prefix: Sequence[float]):
        nonlocal best_w, best
        if len(prefix) == n - 1:
            last = 1.0 - sum(prefix)
            if last < -1e-9:
                return
            w = np.array(list(prefix) + [max(last, 0.0)])
            score = rps(pool(stack, w), outcomes)
            if score < best:
                best, best_w = score, w
            return
        for g in grid:
            if sum(prefix) + g <= 1.0 + 1e-9:
                recurse(list(prefix) + [g])

    recurse([])
    return best_w


def clv(probs: np.ndarray, open_odds: np.ndarray, close_odds: np.ndarray,
        value_only: bool) -> Dict:
    """Closing-line value: did the price move toward the bets we struck?

    We bet at the open and the market settles at the close. If a model has real
    information, the prices it takes should shorten by the time betting stops --
    the market ends up agreeing with it. CLV measures that directly and does not
    care who won, so it carries far less variance than ROI: a few hundred bets
    say as much as thousands of settled results. Beating the close is the
    standard evidence of an edge; losing to it is proof of none.
    """
    if value_only:
        # Same rule as the value book: back anything the model prices above
        # the opening line's implied chance.
        mask = probs > (1.0 / open_odds)
    else:
        mask = np.zeros_like(probs, dtype=bool)
        mask[np.arange(len(probs)), probs.argmax(axis=1)] = True

    o, c = open_odds[mask], close_odds[mask]
    if len(o) == 0:
        return {"n": 0, "clv": None, "beat": None}
    # Price taken vs price at the close. Positive means we took the better side.
    edge = o / c - 1.0
    return {"n": int(len(o)), "clv": float(edge.mean() * 100),
            "beat": float((edge > 0).mean() * 100)}


def book(name: str, probs: np.ndarray, outcomes: np.ndarray, odds: np.ndarray) -> Dict:
    rows = list(zip(probs.tolist(), outcomes.tolist(), odds.tolist()))
    flat, val = _flat_roi(rows), _value_roi(rows)
    return {
        "name": name,
        "probs": probs,
        "rps": rps(probs, outcomes),
        "flat": flat["roi"],
        "value": val["roi"],
        "value_n": int(val["stakes"]),
    }


def main() -> None:
    models, probs, outcomes, odds, close = load_rows()
    stack = np.stack([probs[m] for m in models])
    n_models, n_matches, _ = stack.shape
    print(f"holdout matches (priced, common sample): {n_matches}")
    print(f"models: {', '.join(models)}\n")

    # Weights are fitted on the first half of the holdout and everything is
    # scored on the second. Fitting on the pre-holdout period instead would
    # over-weight XGBoost, which trained on it. Crucially, the market and the
    # unfitted candidates are scored on that SAME held-back half -- comparing a
    # half-sample ensemble against a full-sample market is not a comparison.
    half = n_matches // 2
    te = slice(half, None)
    out_te, odds_te, close_te = outcomes[te], odds[te], close[te]
    print(f"weights fitted on first {half}; ALL rows below scored on the "
          f"held-back {n_matches - half} matches")
    print()

    results = [book(m, probs[m][te], out_te, odds_te) for m in models]

    eq = np.full(n_models, 1.0 / n_models)
    results.append(book("ENSEMBLE mean", linear_pool(stack[:, te], eq), out_te, odds_te))
    results.append(book("ENSEMBLE logpool", log_pool(stack[:, te], eq), out_te, odds_te))

    fitted = []
    for label, pool in (("linear", linear_pool), ("logpool", log_pool)):
        w = fit_weights(stack[:, :half], outcomes[:half], pool)
        res = book(f"ENSEMBLE {label} (fitted)", pool(stack[:, te], w), out_te, odds_te)
        res["note"] = "  weights " + ", ".join(
            f"{m}={wi:.2f}" for m, wi in zip(models, w))
        results.append(res)
        fitted.append(res)

    # The benchmark is the margin-free CLOSING line -- the sharpest price the
    # market produces, and the hardest thing to beat. Bets are still struck at
    # the open, which is the softer line and so generous to the models.
    market = book("MARKET (margin-free close)", market_probs(close_te), out_te, odds_te)
    results.append(market)

    print(f"{'':28s} {'RPS':>8s} {'flat ROI':>10s} {'value ROI':>10s} {'n':>6s}")
    print("-" * 66)
    for r in sorted(results, key=lambda r: r["rps"]):
        fl = f"{r['flat']:+.2f}%" if r["flat"] is not None else "n/a"
        vl = f"{r['value']:+.2f}%" if r["value"] is not None else "n/a"
        print(f"{r['name']:28s} {r['rps']:8.4f} {fl:>10s} {vl:>10s} {r['value_n']:6d}")
        if r.get("note"):
            print(r["note"])

    print()
    print("CLOSING LINE VALUE -- bets struck at the open, measured against the close")
    print(f"{'':28s} {'flat CLV':>10s} {'beat%':>7s} {'value CLV':>11s} {'beat%':>7s}")
    print("-" * 66)
    for r in results:
        if r is market:
            continue
        f, v = (clv(r["probs"], odds_te, close_te, False),
                clv(r["probs"], odds_te, close_te, True))
        fs = f"{f['clv']:+.2f}%" if f["clv"] is not None else "n/a"
        vs = f"{v['clv']:+.2f}%" if v["clv"] is not None else "n/a"
        fb = f"{f['beat']:.1f}" if f["beat"] is not None else "-"
        vb = f"{v['beat']:.1f}" if v["beat"] is not None else "-"
        print(f"{r['name']:28s} {fs:>10s} {fb:>7s} {vs:>11s} {vb:>7s}")
    print("Positive CLV = the market moved toward the bet after it was struck.")

    best = min((r for r in results if r is not market), key=lambda r: r["rps"])
    print()
    if best["rps"] < market["rps"]:
        print(f"{best['name']} beats the margin-free close "
              f"({best['rps']:.4f} < {market['rps']:.4f}), gap "
              f"{best['rps'] - market['rps']:+.4f}.")
    else:
        print(f"Nothing beats the margin-free close ({market['rps']:.4f}). "
              f"Best is {best['name']} at {best['rps']:.4f}, gap "
              f"{best['rps'] - market['rps']:+.4f}.")


if __name__ == "__main__":
    main()
