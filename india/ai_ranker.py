# india/ai_ranker.py
"""
STAGE B1 — the AI RANKER (picks the best stocks).

A gradient-boosted-tree model (HistGBM — the family that won Gu-Kelly-Xiu) learns, from history,
which COMBINATIONS of the ~30 features predict the next period's actual forward RETURN. Each
rebalance it scores every stock; we buy the top-N. This replaces the single hardcoded momentum
rule that LOST to the Nifty.

P&L FIRST (user): we evaluate by the Rs GAIN of the top-N picks vs the universe baseline — not
just by how often we're right. Walk-forward (expanding window + embargo) so it's out-of-sample.

Run (self-test): python india/ai_ranker.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.dataset import build_dataset, feature_list
from sklearn.ensemble import HistGradientBoostingRegressor

TARGET = "fwd_ret"          # predict actual forward return (P&L-relevant), then rank & pick top-N


def make_model():
    # modest capacity + regularization -> resist the overfit that faked Sharpe 1.23 before
    return HistGradientBoostingRegressor(
        max_depth=3, max_iter=300, learning_rate=0.04, l2_regularization=1.0,
        min_samples_leaf=60, early_stopping=True, validation_fraction=0.15, random_state=0)


def walkforward(freq="M", feature_set="full", topn=15, min_train_frac=0.45,
                retrain_every=3, embargo=1):
    """Expanding-window OOS prediction. Returns per-date test rows with pred + actual fwd_ret."""
    df = build_dataset(freq).dropna(subset=[TARGET])
    feats = feature_list(feature_set)
    dates = np.array(sorted(df.index.get_level_values("date").unique()))
    n0 = int(len(dates) * min_train_frac)
    preds = []
    model, last_fit = None, -10_000
    for i in range(n0, len(dates)):
        td = dates[i]
        if model is None or (i - last_fit) >= retrain_every:
            train_dates = dates[: i - embargo]                  # embargo: drop the overlapping window
            tr = df[df.index.get_level_values("date").isin(train_dates)]
            model = make_model().fit(tr[feats].values, tr[TARGET].values)
            last_fit = i
        te = df[df.index.get_level_values("date") == td]
        p = model.predict(te[feats].values)
        preds.append(pd.DataFrame({"date": td, "symbol": te.index.get_level_values("symbol"),
                                   "pred": p, "fwd_ret": te[TARGET].values}))
    return pd.concat(preds, ignore_index=True)


def evaluate(pred, topn=15, capital=100_000):
    """Rs-FIRST scorecard: compound the top-N picks vs the universe baseline, period by period."""
    ic = pred.groupby("date").apply(lambda g: g["pred"].corr(g["fwd_ret"], method="spearman")).mean()
    top_r, base_r, wins, n = [], [], 0, 0
    for _, g in pred.groupby("date"):
        picks = g.nlargest(topn, "pred")
        top_r.append(picks["fwd_ret"].mean())
        base_r.append(g["fwd_ret"].mean())
        wins += (picks["fwd_ret"] > 21/1e4).sum(); n += len(picks)
    top_r, base_r = pd.Series(top_r), pd.Series(base_r)
    top_eq = float((1 + top_r).prod()); base_eq = float((1 + base_r).prod())
    periods = len(top_r)
    ann = (top_eq ** (252/ ( {'M':21,'W':5}.get('M',21)*periods) ) - 1) if periods else 0
    return dict(ic=ic, periods=periods, win_rate=100*wins/max(n,1),
                top_total=100*(top_eq-1), base_total=100*(base_eq-1),
                top_end=capital*top_eq, base_end=capital*base_eq,
                top_gain=capital*(top_eq-1), base_gain=capital*(base_eq-1),
                avg_period_top=100*top_r.mean(), avg_period_base=100*base_r.mean())


def yoy(pred, topn=15, capital=100_000):
    """Year-by-year: top-N picks vs universe baseline, with a running Rs balance (top-N)."""
    p = pred.copy(); p["year"] = pd.to_datetime(p["date"]).dt.year
    rows, bal = [], capital
    for y, gy in p.groupby("year"):
        tr, br = [], []
        for _, g in gy.groupby("date"):
            tr.append(g.nlargest(topn, "pred")["fwd_ret"].mean())
            br.append(g["fwd_ret"].mean())
        top = float((1 + pd.Series(tr)).prod() - 1); base = float((1 + pd.Series(br)).prod() - 1)
        start = bal; bal *= (1 + top)
        rows.append((y, gy["date"].nunique(), 100*top, 100*base, start, bal, bal-start))
    return rows


if __name__ == "__main__":
    print("=" * 86)
    print("  STAGE B1 — AI RANKER walk-forward (OUT-OF-SAMPLE: model trains on early years,")
    print("             these results are the LAST ~3 years it never saw). top-15 picks, Rs first.")
    print("=" * 86)
    for freq in ("M", "W"):
        for fs in ("floor", "full"):
            pred = walkforward(freq=freq, feature_set=fs, topn=15)
            r = evaluate(pred, topn=15)
            tag = "TECHNICALS ONLY (honest floor)" if fs == "floor" else "FUNDAMENTALS + TECHNICALS"
            lo = pd.to_datetime(pred["date"]).min().date(); hi = pd.to_datetime(pred["date"]).max().date()
            print(f"\n  [{freq}] {tag}  | OOS window {lo} -> {hi}  ({r['periods']} periods)")
            print(f"     IC {r['ic']:+.3f}   win {r['win_rate']:.1f}%   "
                  f"TOP-15 Rs{r['top_end']:,.0f} (gain Rs{r['top_gain']:+,.0f})   "
                  f"baseline Rs{r['base_end']:,.0f} (gain Rs{r['base_gain']:+,.0f})")
            print(f"     {'year':<6}{'top%':>8}{'base%':>8}{'top edge':>10}{'start_Rs':>13}{'end_Rs':>13}{'gain_Rs':>12}")
            for y, n, top, base, st, en, gl in yoy(pred, 15):
                print(f"     {y:<6}{top:>8.1f}{base:>8.1f}{top-base:>+10.1f}{st:>13,.0f}{en:>13,.0f}{gl:>+12,.0f}")
