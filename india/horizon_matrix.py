# india/horizon_matrix.py
"""
DYNAMIC HORIZON ENGINE (AEGIS v3) — don't fix the holding period; evaluate ALL of them.

For every monthly rebalance, build the portfolio ONCE (selection doesn't depend on horizon), then
score it across EVERY holding period in HOLDING_PERIODS. Produces the Horizon Performance Matrix:
win rate, avg return, beat-Nifty %, worst cycle, annualised Sharpe, and a data-driven confidence —
so the investor sees where the evidence is strongest and AEGIS recommends a horizon dynamically.

Honest: this is PORTFOLIO-level (the validated thing). Short horizons (1W/1M) are ~coin flips by
design; the matrix shows that. Per-STOCK horizon scoring is NOT supported (selection RQS ~0.5).
Config-driven: add/remove a horizon = edit HOLDING_PERIODS, not code. Windows overlap (monthly
cadence) and the universe is survivorship-tilted -> trust the vs-Nifty relative gradient.

Run: python india/horizon_matrix.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import select_names, weights_for, LOOKBACK
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.probability_surface import mode_of

CADENCE, TOPN = 21, 15
HOLDING_PERIODS = [5, 10, 21, 42, 63, 126, 189, 252]      # config: add/remove a horizon here
LABELS = {5: "1W", 10: "2W", 21: "1M", 42: "2M", 63: "3M", 126: "6M", 189: "9M", 252: "1Y"}


def confidence_from(win):
    return "Low" if win < 60 else ("Medium" if win < 75 else ("High" if win < 90 else "Very High"))


def horizon_matrix():
    closes, _, _, _, idx, _, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change(); mx = max(HOLDING_PERIODS)
    acc = {h: [] for h in HOLDING_PERIODS}
    for i in range(LOOKBACK, len(closes) - 1, CADENCE):
        hist = rets.iloc[i - LOOKBACK:i].dropna(axis=1, how="any")
        if hist.shape[1] < 20:
            continue
        sel = select_names(hist, TOPN, sector_cap=2)
        if len(sel) < 3:
            continue
        w = weights_for("hrp", hist[sel]); w = w / w.sum()              # built ONCE, scored at every horizon
        for h in HOLDING_PERIODS:
            if i + h >= len(closes):
                continue
            port = float((w * (closes.iloc[i + h] / closes.iloc[i] - 1).reindex(w.index)).sum())
            nif = float(idx.iloc[i + h] / idx.iloc[i] - 1)
            acc[h].append((100 * port, 100 * nif))
    rows = []
    for h in HOLDING_PERIODS:
        a = np.array(acc[h])
        if len(a) < 5:
            continue
        port, nif = a[:, 0], a[:, 1]
        win = 100 * (port > 0).mean(); beat = 100 * (port > nif).mean()
        sharpe = (port.mean() / (port.std() + 1e-12)) * np.sqrt(252 / h)
        mode, _, _ = mode_of(h)
        rows.append({"Horizon": LABELS[h], "Mode": mode, "Cycles": len(a),
                     "Win Rate %": round(win), "Avg Return %": round(port.mean(), 1),
                     "Median Return %": round(float(np.median(port)), 1), "Best Cycle %": round(port.max(), 1),
                     "Beat Nifty %": round(beat), "Worst Cycle %": round(port.min(), 1),
                     "Sharpe (ann)": round(sharpe, 1), "Confidence": confidence_from(win)})
    return pd.DataFrame(rows)


def recommend(mat):
    """Strongest horizon = best annualised Sharpe among horizons with >=70% win rate (else best Sharpe)."""
    strong = mat[mat["Win Rate %"] >= 70]
    pick = (strong if not strong.empty else mat).sort_values("Sharpe (ann)", ascending=False).iloc[0]
    return pick["Horizon"], pick["Confidence"]


def main():
    mat = horizon_matrix()
    print("=" * 78)
    print("  AEGIS — HORIZON PERFORMANCE MATRIX (portfolio, rolling, vs Nifty)")
    print("=" * 78)
    print(f"  {'Horizon':<9}{'Mode':<13}{'Win%':>6}{'AvgRet%':>9}{'BeatN%':>8}{'Worst%':>8}{'Sharpe':>8}  Confidence")
    for r in mat.to_dict("records"):
        print(f"  {r['Horizon']:<9}{r['Mode']:<13}{r['Win Rate %']:>5}%{r['Avg Return %']:>+8.1f}"
              f"{r['Beat Nifty %']:>7}%{r['Worst Cycle %']:>+8.1f}{r['Sharpe (ann)']:>8.1f}  {r['Confidence']}")
    h, conf = recommend(mat)
    print(f"\n  RECOMMENDED HORIZON: {h}  (confidence {conf}) — strongest risk-adjusted evidence.")
    print("  Short horizons (1W/1M) are ~coin flips by design; the edge builds from ~3-6 months.")
    print("  Portfolio-level only — per-stock horizon skill is NOT supported (selection RQS ~0.5).")


if __name__ == "__main__":
    main()
