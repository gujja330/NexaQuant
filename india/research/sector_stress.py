# india/research/sector_stress.py
"""
SECTOR<=1 vs <=2 vs <=3 — is sector<=1's high Sharpe (2.19) real or over-concentration?
Tests each through real corrections + Deflated Sharpe, and shows the SECTOR RISK CONTRIBUTION
of the current basket. (HRP + regime + global, 15 stocks, quarterly.) Portfolio engineering.

Run: python india/research/sector_stress.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats, select_names, weights_for
from india.validation import deflated_sharpe
from india.feature_engine import load_panels
from india.sectors import sector_of

WIN = [("2022", "2022-01-01", "2022-06-30"), ("2023", "2023-01-01", "2023-03-31"),
       ("2025", "2025-01-01", "2025-03-31"), ("2026", "2026-01-01", "2026-04-30")]


def dd(s):
    eq = (1 + s).cumprod(); return 100 * ((eq.cummax() - eq) / eq.cummax()).max()


def main():
    print("=" * 84)
    print("  SECTOR CAP VALIDATION — <=1 vs <=2 vs <=3 (15 stk, quarterly): stress + Deflated Sharpe")
    print("=" * 84)
    hdr = f"  {'cap':<8}{'Sharpe':>7}{'maxDD':>7}{'DSR':>7}" + "".join(f"{w[0]+' DD':>9}" for w in WIN)
    print(hdr)
    for sc in (1, 2, 3):
        net, idx = backtest("hrp", regime="global", topn=15, sector_cap=sc, rebal=63)
        s = stats(net, idx); d = deflated_sharpe(net.values, n_trials=20)
        wdd = "".join(f"{dd(net.loc[a:b]):>8.1f}%" for _, a, b in WIN)
        flag = "ROBUST" if d["dsr"] > 0.95 else "check"
        print(f"  sec<={sc:<4}{s['sharpe']:>7.2f}{s['dd']:>6.1f}%{d['dsr']:>7.3f}{wdd}  {flag}")

    # sector risk contribution of the CURRENT sector<=2 basket
    print("\n  CURRENT BASKET — sector risk contribution (sector<=2, 15 stk):")
    closes = load_panels()[0]; rets = closes.pct_change()
    hist = rets.tail(120).dropna(axis=1, how="any")
    sel = select_names(hist, 15, sector_cap=2)
    w = weights_for("hrp", hist[sel]); w = w / w.sum()
    cov = hist[sel].cov()
    port_var = float(w.values @ cov.values @ w.values)
    rc = {}
    for s in sel:
        mc = w[s] * (cov[s] @ w) / port_var            # risk contribution share
        k = sector_of(s); rc[k] = rc.get(k, 0) + mc
    for k, v in sorted(rc.items(), key=lambda x: -x[1]):
        bar = "#" * int(40 * v); print(f"   {k:<12}{bar} {100*v:.0f}%")
    print("\n  Verdict: prefer the cap that keeps DSR robust + corrections shallow + risk spread.")


if __name__ == "__main__":
    main()
