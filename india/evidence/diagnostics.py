# india/research/diagnostics.py
"""
PORTFOLIO DIAGNOSTICS (Phase 2 — engineering, not models) for Core v2.1 (HRP+regime+global,
quarterly, 15 stk, sector<=2):
  1. Turnover decomposition (name / weight / sector)
  2. Time diversification (P(positive) by holding length)
  3. Rolling sub-period consistency
  4. Benchmark expansion (Nifty / equal-weight-200 / gold)
  5. Tax+slippage sensitivity (does quarterly still beat monthly at higher cost?)
  6. Sequence risk (best/worst rolling year + recovery)

Run: python india/research/diagnostics.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats, select_names, weights_for
from india.feature_engine import load_panels
from india.sectors import sector_of

CFG = dict(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)


def champ_weights():
    closes = load_panels()[0]; rets = closes.pct_change()
    from india.data_nse import NIFTY200
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    W = {}
    for dt in closes.index[::63]:
        hist = rets.loc[:dt].tail(120).dropna(axis=1, how="any")
        if hist.shape[1] < 20:
            continue
        sel = select_names(hist, 15, sector_cap=2)
        w = weights_for("hrp", hist[sel]); W[dt] = (w / w.sum())
    return pd.DataFrame(W).T.fillna(0.0)


def main():
    net, idx = backtest(**CFG)
    eq = (1 + net).cumprod()

    print("=" * 70); print("  AEGIS v2.1 — PORTFOLIO DIAGNOSTICS"); print("=" * 70)

    # 1) turnover decomposition
    W = champ_weights(); rebals = W.index
    name_chg, wt_chg, sec_chg = [], [], []
    for i in range(1, len(rebals)):
        a, b = W.iloc[i - 1], W.iloc[i]
        held_a, held_b = set(a[a > 0].index), set(b[b > 0].index)
        name_chg.append(len(held_b - held_a))
        wt_chg.append((b - a).abs().sum() / 2)
        sa = a.groupby(W.columns.map(sector_of)).sum(); sb = b.groupby(W.columns.map(sector_of)).sum()
        sec_chg.append((sb - sa).abs().sum() / 2)
    py = 252 / 63                                     # rebalances per year
    print(f"\n  1) TURNOVER (per quarter -> /yr): names changed {np.mean(name_chg):.1f}/15 "
          f"({np.mean(name_chg)*py:.0f}/yr) · weight {100*np.mean(wt_chg):.0f}% · sector {100*np.mean(sec_chg):.0f}%")

    # 2) time diversification
    print("\n  2) TIME DIVERSIFICATION — probability of a POSITIVE outcome:")
    for label, d in [("1 month", 21), ("3 months", 63), ("6 months", 126), ("1 year", 252),
                     ("2 years", 504), ("3 years", 756)]:
        r = (eq.shift(-d) / eq - 1).dropna()
        if len(r):
            print(f"     {label:<9} P(+ve) {100*(r>0).mean():>3.0f}%   avg {100*r.mean():>+5.1f}%")

    # 3) rolling sub-periods
    print("\n  3) ROLLING SUB-PERIODS (consistency):")
    for a, b in [("2021", "2023"), ("2022", "2024"), ("2023", "2026")]:
        seg = net.loc[a:b]
        if len(seg) < 200:
            continue
        e = (1 + seg).cumprod(); yrs = len(seg) / 252
        print(f"     {a}-{b}: CAGR {100*(e.iloc[-1]**(1/yrs)-1):>5.1f}%  Sharpe {seg.mean()/(seg.std()+1e-12)*np.sqrt(252):.2f}"
              f"  maxDD {100*((e.cummax()-e)/e.cummax()).max():.1f}%")

    # 4) benchmark expansion
    print("\n  4) BENCHMARK EXPANSION (full period, total return):")
    closes, _, _, _, idx2, _, _ = load_panels()
    from india.data_nse import NIFTY200
    ew = closes[[c for c in closes.columns if c in set(NIFTY200)]].pct_change().mean(axis=1)
    gold = None
    gp = Path(__file__).resolve().parents[2] / "data/raw/india/global/GOLD.parquet"
    if gp.exists():
        gold = pd.read_parquet(gp)["close"].pct_change().reindex(net.index).fillna(0)
    benches = {"AEGIS v2.1": net, "Nifty-50": idx2.pct_change().fillna(0),
               "Equal-weight-200": ew.reindex(net.index).fillna(0)}
    if gold is not None:
        benches["Gold"] = gold
    for nm, r in benches.items():
        e = (1 + r.reindex(net.index).fillna(0)).cumprod()
        print(f"     {nm:<18}{100*(e.iloc[-1]-1):>+6.0f}%   Sharpe {r.mean()/(r.std()+1e-12)*np.sqrt(252):.2f}")

    # 5) tax + slippage sensitivity (quarterly vs monthly)
    print("\n  5) TAX+SLIPPAGE SENSITIVITY (cost bps; does QUARTERLY still beat MONTHLY?):")
    for c in (21, 40, 60, 90):
        q = stats(backtest(**{**CFG, "cost_bps": c})[0], idx)
        m = stats(backtest(**{**CFG, "rebal": 21, "cost_bps": c})[0], idx)
        print(f"     {c}bps: quarterly Sharpe {q['sharpe']:.2f} / CAGR {q['cagr']:.1f}%   "
              f"monthly {m['sharpe']:.2f} / {m['cagr']:.1f}%   -> {'quarterly' if q['sharpe']>m['sharpe'] else 'monthly'} wins")

    # 6) sequence risk
    r1 = (eq.shift(-252) / eq - 1).dropna()
    print(f"\n  6) SEQUENCE RISK (rolling 1-yr): best {100*r1.max():+.0f}%  worst {100*r1.min():+.0f}%  "
          f"median {100*r1.median():+.0f}%")
    print("\n  (All survivorship-inflated; the relative/probability shapes are the honest signal.)")


if __name__ == "__main__":
    main()
