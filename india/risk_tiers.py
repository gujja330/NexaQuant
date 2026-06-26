# india/risk_tiers.py
"""
RISK-TIER VALIDATION — does medium / high risk pay off, or does low risk win? Let the backtest decide.

Splits the Nifty-200 into LOW / MEDIUM / HIGH volatility tiers at each rebalance (trailing-vol
terciles), builds a sector-capped HRP portfolio inside each tier, and walk-forward backtests all three
the same way (quarterly hold, net of nothing here = gross, so the comparison is apples-to-apples; the
regime overlay would scale all three equally). Reports CAGR / Sharpe / max-DD / win / beat-Nifty plus
the realised volatility of each tier's picks — so "risk level" is shown, not assumed.

This is the evidence behind offering (or not) Conservative / Balanced / Aggressive recommendations.

Run: python india/risk_tiers.py
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

CAD, TOPN, CAP = 63, 15, 2                      # quarterly hold, 15 names, sector cap 2 (production cadence)
TIERS = ["Low risk", "Medium risk", "High risk"]


def tier_members(vol):
    r = vol.rank(pct=True)
    return {"Low risk": list(r[r <= 0.34].index),
            "Medium risk": list(r[(r > 0.34) & (r <= 0.67)].index),
            "High risk": list(r[r > 0.67].index)}


def summarize(cyc, nif, vol_used):
    a = pd.Series(cyc).dropna()
    eq = (1 + a).cumprod(); yrs = len(a) * CAD / 252
    cagr = 100 * (eq.iloc[-1] ** (1 / yrs) - 1)
    dd = 100 * ((eq.cummax() - eq) / eq.cummax()).max()
    shp = a.mean() / (a.std() + 1e-12) * np.sqrt(252 / CAD)
    win = 100 * (a > 0).mean()
    beat = 100 * (a.values > pd.Series(nif).reindex(a.index).values).mean()
    return dict(cagr=cagr, sharpe=shp, dd=dd, win=win, beat=beat,
                avgret=100 * a.mean(), vol=float(np.nanmean(vol_used)) * np.sqrt(252) * 100)


def main():
    closes, _, _, _, idx, _, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    acc = {t: [] for t in TIERS}; volused = {t: [] for t in TIERS}; nif = []
    for i in range(LOOKBACK, len(closes) - CAD, CAD):
        hist = rets.iloc[i - LOOKBACK:i].dropna(axis=1, how="any")
        if hist.shape[1] < 40:
            continue
        vol = hist.std()
        fwd = (closes.iloc[i + CAD] / closes.iloc[i] - 1)
        nif.append(float(idx.iloc[i + CAD] / idx.iloc[i] - 1))
        for t, members in tier_members(vol).items():
            members = [m for m in members if m in hist.columns]
            sel = select_names(hist[members], TOPN, CAP) if len(members) >= 5 else []
            if len(sel) < 3:
                acc[t].append(np.nan); continue
            w = weights_for("hrp", hist[sel]); w = w / w.sum()
            acc[t].append(float((w * fwd.reindex(w.index)).sum()))
            volused[t].append(float(vol[sel].mean()))

    nif_s = pd.Series(nif)
    nstats = dict(cagr=100 * ((1 + nif_s).cumprod().iloc[-1] ** (252 / CAD / len(nif_s)) - 1),
                  sharpe=nif_s.mean() / (nif_s.std() + 1e-12) * np.sqrt(252 / CAD),
                  dd=100 * (((1 + nif_s).cumprod().cummax() - (1 + nif_s).cumprod()) /
                            (1 + nif_s).cumprod().cummax()).max(),
                  win=100 * (nif_s > 0).mean())
    print("=" * 86)
    print("  AEGIS RISK-TIER VALIDATION — Nifty-200 split by volatility, walk-forward (quarterly, gross)")
    print("=" * 86)
    print(f"  {'Tier':<14}{'PickVol%':>9}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'Win%':>7}{'BeatN%':>8}{'AvgCyc%':>9}")
    for t in TIERS:
        s = summarize(acc[t], nif, volused[t])
        print(f"  {t:<14}{s['vol']:>8.0f}%{s['cagr']:>7.1f}%{s['sharpe']:>8.2f}{s['dd']:>7.1f}%"
              f"{s['win']:>6.0f}%{s['beat']:>7.0f}%{s['avgret']:>+9.1f}")
    print(f"  {'NIFTY-50':<14}{'—':>9}{nstats['cagr']:>7.1f}%{nstats['sharpe']:>8.2f}"
          f"{nstats['dd']:>7.1f}%{nstats['win']:>6.0f}%{'—':>8}{'—':>9}")
    print("\n  PickVol% = annualised volatility of the tier's chosen names (confirms the tiers differ).")
    print("  Same regime overlay would scale ALL tiers equally, so this gross view isolates risk level.")
    print("  Read: higher tiers usually buy higher CAGR with a worse Sharpe + deeper drawdown — the")
    print("  tradeoff you'd be choosing if AEGIS offered Conservative / Balanced / Aggressive.")


if __name__ == "__main__":
    main()
