# india/ai_avoid.py
"""
STAGE B2 — the AVOIDANCE FILTER (avoid bad stocks BEFORE placing the order).

A gradient-boosted CLASSIFIER estimates each candidate's probability of WINNING (fwd_ret > cost).
The portfolio then keeps only high-P(win) names and VETOES the rest — so we don't order a stock the
model has low confidence in. (López de Prado meta-labeling.)

P&L FIRST: we judge it by whether the HIGH-confidence half earns more Rs (and wins more often)
than the low-confidence half, out-of-sample. If high ~ low, the filter has no skill and we say so.

Run (self-test): python india/ai_avoid.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.dataset import build_dataset, feature_list
from sklearn.ensemble import HistGradientBoostingClassifier

TARGET = "win"


def make_model():
    return HistGradientBoostingClassifier(
        max_depth=3, max_iter=300, learning_rate=0.04, l2_regularization=1.0,
        min_samples_leaf=60, early_stopping=True, validation_fraction=0.15, random_state=0)


def walkforward(freq="M", feature_set="full", min_train_frac=0.45, retrain_every=3, embargo=1):
    df = build_dataset(freq).dropna(subset=[TARGET, "fwd_ret"])
    feats = feature_list(feature_set)
    dates = np.array(sorted(df.index.get_level_values("date").unique()))
    n0 = int(len(dates) * min_train_frac)
    out, model, last_fit = [], None, -10_000
    for i in range(n0, len(dates)):
        td = dates[i]
        if model is None or (i - last_fit) >= retrain_every:
            train_dates = dates[: i - embargo]
            tr = df[df.index.get_level_values("date").isin(train_dates)]
            if tr[TARGET].nunique() < 2:
                continue
            model = make_model().fit(tr[feats].values, tr[TARGET].values)
            last_fit = i
        te = df[df.index.get_level_values("date") == td]
        pw = model.predict_proba(te[feats].values)[:, 1]
        out.append(pd.DataFrame({"date": td, "symbol": te.index.get_level_values("symbol"),
                                 "p_win": pw, "fwd_ret": te["fwd_ret"].values,
                                 "win": te["win"].values}))
    return pd.concat(out, ignore_index=True)


def evaluate(pred, capital=100_000):
    """Split each date into high-confidence vs low-confidence half; compare Rs + win rate."""
    hi_r, lo_r, hi_w, lo_w, hn, ln = [], [], 0, 0, 0, 0
    for _, g in pred.groupby("date"):
        med = g["p_win"].median()
        hi, lo = g[g["p_win"] >= med], g[g["p_win"] < med]
        if len(hi): hi_r.append(hi["fwd_ret"].mean()); hi_w += (hi["fwd_ret"] > 21/1e4).sum(); hn += len(hi)
        if len(lo): lo_r.append(lo["fwd_ret"].mean()); lo_w += (lo["fwd_ret"] > 21/1e4).sum(); ln += len(lo)
    hi_eq = float((1 + pd.Series(hi_r)).prod()); lo_eq = float((1 + pd.Series(lo_r)).prod())
    return dict(hi_win=100*hi_w/max(hn,1), lo_win=100*lo_w/max(ln,1),
                hi_end=capital*hi_eq, lo_end=capital*lo_eq,
                hi_gain=capital*(hi_eq-1), lo_gain=capital*(lo_eq-1))


if __name__ == "__main__":
    print("=" * 78)
    print("  STAGE B2 — AVOIDANCE FILTER walk-forward (high-P(win) vs low-P(win), Rs first)")
    print("=" * 78)
    for freq in ("M", "W"):
        for fs in ("floor", "full"):
            pred = walkforward(freq=freq, feature_set=fs)
            r = evaluate(pred)
            tag = "technical-only (honest)" if fs == "floor" else "+fundamentals (optimistic)"
            print(f"\n  [{freq}] {tag}")
            print(f"     HIGH-confidence half: win {r['hi_win']:.1f}%   Rs1,00,000 -> Rs{r['hi_end']:>11,.0f}  (gain Rs{r['hi_gain']:>+11,.0f})")
            print(f"     LOW-confidence  half: win {r['lo_win']:.1f}%   Rs1,00,000 -> Rs{r['lo_end']:>11,.0f}  (gain Rs{r['lo_gain']:>+11,.0f})")
            print(f"     -> avoidance value: {r['hi_win']-r['lo_win']:+.1f}pp win, Rs{r['hi_gain']-r['lo_gain']:+,.0f} more gain by avoiding the low half")
