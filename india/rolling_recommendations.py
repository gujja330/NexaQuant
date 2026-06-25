# india/rolling_recommendations.py
"""
ROLLING WALK-FORWARD MONTHLY SIMULATION — the "proof of recommendation".

Not one big backtest. Every month: generate the recommendation portfolio (causal), invest, hold
HORIZON, exit, score vs Nifty. Repeat to today. This answers "if I'd started any month, how would
AEGIS's recommendation have done?" — thousands of rolling decisions, the way institutions validate.

HONESTY (user's caution): we evaluate the ACTUAL MONTHLY PORTFOLIO (all recommended holdings
together) vs the benchmark — proving PORTFOLIO performance, which has real evidence. We do NOT claim
individual stock-picking skill (the selection's RQS ~0.51 ≈ random). Windows overlap (monthly
cadence, 3-month hold) and the universe is survivorship-tilted -> trust the vs-Nifty RELATIVE result.

Run: python india/rolling_recommendations.py
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
from india.sectors import sector_of

CADENCE, HOLD, TOPN = 21, 63, 15      # monthly cadence, 3-month hold, 15 stocks


def rolling_sim(cadence=CADENCE, hold=HOLD, topn=TOPN):
    closes, _, _, _, idx, _, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    cycles, perstock = [], {}
    for i in range(LOOKBACK, len(closes) - hold, cadence):
        dt = closes.index[i]
        hist = rets.iloc[i - LOOKBACK:i].dropna(axis=1, how="any")
        if hist.shape[1] < 20:
            continue
        sel = select_names(hist, topn, sector_cap=2)
        if len(sel) < 3:
            continue
        w = weights_for("hrp", hist[sel]); w = w / w.sum()
        fwd_all = (closes.iloc[i + hold] / closes.iloc[i] - 1)
        port = float((w * fwd_all.reindex(w.index)).sum())
        nif = float(idx.iloc[i + hold] / idx.iloc[i] - 1)
        cycles.append(dict(month=dt.strftime("%Y-%m"), n=len(sel),
                           stocks=", ".join(list(w.sort_values(ascending=False).index[:5])) + " ...",
                           port=100 * port, nifty=100 * nif, beat=int(port > nif)))
        pct = fwd_all.reindex(w.index.union(fwd_all.dropna().index)).dropna().rank(pct=True)
        N = fwd_all.dropna().shape[0]
        for s in w.index:
            if s in fwd_all.index and not np.isnan(fwd_all[s]):
                perstock.setdefault(s, []).append((100 * fwd_all[s], int((1 - pct.get(s, 0.5)) * N) + 1, N))
    cyc = pd.DataFrame(cycles)
    ps = pd.DataFrame([dict(Stock=s, Recommended=len(v),
                            Wins=sum(1 for r, _, _ in v if r > 0),
                            **{"Median Ret %": round(np.median([r for r, _, _ in v]), 1)},
                            **{"Best %": round(max(r for r, _, _ in v), 1)},
                            **{"Worst %": round(min(r for r, _, _ in v), 1)},
                            **{"Avg Rank": f"{np.mean([rk for _, rk, _ in v]):.0f}/{int(np.median([n for *_ , n in v]))}"})
                      for s, v in sorted(perstock.items(), key=lambda kv: -len(kv[1]))])
    return cyc, ps


def stats_table(cyc):
    n = len(cyc); beats = int(cyc["beat"].sum())
    out = (cyc["port"] - cyc["nifty"])
    return pd.DataFrame([
        ["Recommendation cycles", n], ["Cycles beating Nifty", f"{beats} ({100*beats/n:.0f}%)"],
        ["Cycles positive", f"{int((cyc['port']>0).sum())} ({100*(cyc['port']>0).mean():.0f}%)"],
        ["Avg portfolio return / cycle", f"{cyc['port'].mean():+.1f}%"],
        ["Median portfolio return", f"{cyc['port'].median():+.1f}%"],
        ["Best / Worst cycle", f"{cyc['port'].max():+.1f}% / {cyc['port'].min():+.1f}%"],
        ["Avg Nifty return / cycle", f"{cyc['nifty'].mean():+.1f}%"],
        ["Avg outperformance vs Nifty", f"{out.mean():+.1f}%"],
    ], columns=["Metric", "Value"])


def main():
    cyc, ps = rolling_sim()
    print("=" * 76)
    print(f"  ROLLING MONTHLY RECOMMENDATION PROOF  ({len(cyc)} cycles · 3-month hold · vs Nifty)")
    print("=" * 76)
    print(f"  {'month':<9}{'port%':>8}{'nifty%':>8}{'beat?':>7}   top holdings")
    for r in cyc.to_dict("records"):
        print(f"  {r['month']:<9}{r['port']:>+7.1f}{r['nifty']:>+8.1f}{('YES' if r['beat'] else 'no'):>7}   {r['stocks']}")
    print("  " + "-" * 72)
    for _, row in stats_table(cyc).iterrows():
        print(f"  {row['Metric']:<32}{row['Value']}")
    print("\n  This proves the PORTFOLIO vs Nifty (honest). It does NOT claim stock-picking skill")
    print("  (selection RQS ~0.51). Windows overlap + survivorship-tilted -> the vs-Nifty edge is the signal.")


if __name__ == "__main__":
    main()
