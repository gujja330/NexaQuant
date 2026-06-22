# india/research/frontier_grid.py
"""
FRONTIER GRID — the 5 untested implementation/risk backtests (no new models). Evidence decides.
  1. Dynamic-N (regime -> position count)        4. Holding-period / rebalance frequency
  2. Discrete exposure tiers (0/25/50/75/100)    5. Dynamic sector-strength tilt
  3. Capital-aware deployment (positions vs Rs)

Base = HRP + regime + global on Nifty-200, net of cost. Run: python india/research/frontier_grid.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats, weights_for, select_names
from india.feature_engine import load_panels
from india.equity_engine import COST_BPS
from india.data_nse import NIFTY200
from india.sectors import SECTORS


def line(tag, net, idx, extra=""):
    s = stats(net, idx)
    print(f"  {tag:<30}{s['cagr']:>6.1f}%{s['sharpe']:>7.2f}{s['sortino']:>8.2f}{s['dd']:>7.1f}%{s['calmar']:>7.2f}  {extra}")


def regime_exposure_series(idx, vix, index):
    scale = pd.Series(1.0, index=index)
    hi = (vix > vix.rolling(120, min_periods=30).quantile(0.80)).reindex(index).fillna(False)
    scale *= hi.map({True: 0.6, False: 1.0})
    below = (idx < idx.rolling(200).mean()).reindex(index).fillna(False)
    scale *= below.map({True: 0.6, False: 1.0})
    from india.global_risk import global_exposure
    g = global_exposure()
    if g is not None:
        scale *= g.reindex(index).ffill().fillna(1.0)
    return scale


def dynamic_or_tiered(mode):
    """mode='dynamicN' (regime -> #stocks) or 'tiers' (regime -> discrete 0/25/50/75/100 exposure)."""
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    cols = [c for c in closes.columns if c in set(NIFTY200)]
    closes = closes[cols]; rets = closes.pct_change()
    exp = regime_exposure_series(idx, vix, closes.index)
    rebal_idx = closes.index[::21]
    W = {}
    for dt in rebal_idx:
        hist = rets.loc[:dt].tail(120).dropna(axis=1, how="any")
        if hist.shape[1] < 20:
            continue
        e = float(exp.loc[dt]) if dt in exp.index else 1.0
        tier = min([0.0, 0.25, 0.5, 0.75, 1.0], key=lambda t: abs(t - e))   # snap to tier
        n = {0.0: 0, 0.25: 3, 0.5: 5, 0.75: 8, 1.0: 10}[tier]
        if mode == "dynamicN":
            if n == 0:
                W[dt] = pd.Series(dtype=float); continue
            sel = select_names(hist, n, sector_cap=3, corr_cap=2)
            w = weights_for("hrp", hist[sel]); w = w / w.sum()
            W[dt] = w                                       # full exposure, count varies
        else:  # tiers: fixed 10 names, exposure snapped to tier
            sel = select_names(hist, 10, sector_cap=3, corr_cap=2)
            w = weights_for("hrp", hist[sel]); w = (w / w.sum()) * tier
            W[dt] = w
    Wdf = pd.DataFrame(W).T.reindex(columns=closes.columns).fillna(0.0).reindex(closes.index).ffill().fillna(0.0)
    gross = (Wdf.shift(1) * rets).sum(axis=1)
    net = gross - (Wdf - Wdf.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    return net, idx


def sector_strength():
    """Overweight strong sectors (6m sector momentum), pick lowest-vol stock per top sectors."""
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    cols = [c for c in closes.columns if c in set(NIFTY200)]
    closes = closes[cols]; rets = closes.pct_change()
    sect = pd.Series({s: SECTORS.get(s, "Other") for s in cols})
    exp = regime_exposure_series(idx, vix, closes.index)
    rebal_idx = closes.index[::21]; W = {}
    for dt in rebal_idx:
        hist = rets.loc[:dt].tail(120).dropna(axis=1, how="any")
        if hist.shape[1] < 20:
            continue
        avail = hist.columns
        mom6 = (closes.loc[dt, avail] / closes.loc[:dt].iloc[-126][avail] - 1) if len(closes.loc[:dt]) > 126 else None
        if mom6 is None:
            continue
        sec_mom = mom6.groupby(sect[avail]).mean().sort_values(ascending=False)
        top_secs = sec_mom.head(5).index                    # 5 strongest sectors
        picks = []
        for k in top_secs:
            names = [s for s in avail if sect[s] == k]
            if names:
                vol = hist[names].std()
                picks.append(vol.idxmin())                  # lowest-vol stock in the sector
        if len(picks) < 3:
            continue
        w = weights_for("hrp", hist[picks]); w = (w / w.sum()) * float(exp.loc[dt])
        W[dt] = w
    Wdf = pd.DataFrame(W).T.reindex(columns=closes.columns).fillna(0.0).reindex(closes.index).ffill().fillna(0.0)
    gross = (Wdf.shift(1) * rets).sum(axis=1)
    net = gross - (Wdf - Wdf.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    return net, idx


if __name__ == "__main__":
    _, idx = backtest("ew")
    print("=" * 82)
    print("  FRONTIER GRID  (HRP+regime+global base, Nifty-200, net, ~5.5y)")
    print("=" * 82)
    print(f"  {'strategy':<30}{'CAGR':>6}{'Sharpe':>7}{'Sortino':>8}{'maxDD':>7}{'Calmar':>7}")
    print("  -- #4 Holding period (rebalance frequency) --")
    for tag, r in [("monthly (21d)", 21), ("quarterly (63d)", 63), ("6-monthly (126d)", 126), ("yearly (252d)", 252)]:
        line(f"hold {tag}", *backtest("hrp", regime="global", topn=10, sector_cap=3, corr_cap=2, rebal=r))
    print("  -- #1/#2 Dynamic-N & exposure tiers --")
    line("CONTINUOUS (current champ N=10)", *backtest("hrp", regime="global", topn=10, sector_cap=3, corr_cap=2))
    line("DYNAMIC-N (regime->#stocks)", *dynamic_or_tiered("dynamicN"))
    line("DISCRETE TIERS (0/25/50/75/100)", *dynamic_or_tiered("tiers"))
    print("  -- #5 Dynamic sector-strength tilt --")
    line("SECTOR-STRENGTH (top-5 sectors)", *sector_strength())
    print("  -- benchmark --")
    nf = idx.pct_change().fillna(0.0)
    print(f"  {'NIFTY-50':<30}{100*((1+nf).prod()**(252/len(nf))-1):>6.1f}%{nf.mean()/(nf.std()+1e-12)*np.sqrt(252):>7.2f}")

    print("\n  -- #3 Capital-aware deployment (Position Budget Engine) --")
    from india.run_arjuna import current_portfolio, position_budget
    asof, w, prices, deploy, lbl, exc = current_portfolio()
    print(f"  {'capital':<12}{'positions':>11}{'deployed':>12}{'idle cash':>12}")
    for capn in (50000, 100000, 200000, 500000, 1000000):
        df, spent, n = position_budget(w, prices, capn, deploy)
        print(f"  Rs{capn:<10,}{len(df):>11}{f'Rs{spent:,.0f}':>12}{f'Rs{capn-spent:,.0f}':>12}")
    print("\n  Evidence decides. Promote to Core only after beating champion + 12mo forward + DSR/PBO.")
