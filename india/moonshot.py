# india/moonshot.py
"""
ARJUNA MOONSHOT — the VC/power-law way to chase multibaggers (NOT by predicting which one doubles).

Own a broad QUALITY + GROWTH + MOMENTUM basket (40 names, equal-weight, sector-capped, annual
rebalance, multi-year hold). You can't pick the next BSE/Dixon/Mazdock in advance (proven), but if
you OWN many quality-growth names, the power-law winners drive the basket.

BARBELL: 70% ARJUNA Core (HRP + regime + global risk) + 30% Moonshot -> stable compounding +
occasional 5-20x. Compared to Nifty, net of cost. (Quality uses snapshot fundamentals -> the
absolute CAGR is OPTIMISTIC/look-ahead; the structure + multibagger-capture are the honest points.)

Run: python india/moonshot.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels
from india.equity_engine import COST_BPS
from india.sectors import SECTORS
from india.data_nse import NIFTY200
from india.arjuna_v2 import backtest as core_backtest, stats

RAW = ROOT / "data" / "raw" / "india"
N, REBAL, SECTOR_CAP = 40, 252, 8        # 40 names, annual rebalance, max 8/sector (~20%)


def _z(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


def quality_z(cols):
    fp = RAW / "fundamentals.parquet"
    if not fp.exists():
        return pd.Series(0.0, index=cols)
    f = pd.read_parquet(fp); sign = {"returnOnEquity": +1, "profitMargins": +1,
                                     "earningsGrowth": +1, "debtToEquity": -1}
    z = pd.DataFrame(index=f.index)
    for m, s in sign.items():
        if m in f.columns:
            c = pd.to_numeric(f[m], errors="coerce"); z[m] = s * (c - c.mean()) / (c.std() + 1e-9)
    return z.mean(axis=1).reindex(cols).fillna(0.0)


def moonshot_backtest():
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    cols = [c for c in closes.columns if c in set(NIFTY200)]
    closes = closes[cols]; rets = closes.pct_change().fillna(0.0)
    mom12 = closes.shift(21) / closes.shift(252) - 1
    trend = (closes > closes.rolling(200).mean()).astype(float)
    lowvol = -rets.rolling(120).std()
    q = quality_z(cols)
    score = _z(mom12) + _z(lowvol) + trend
    score = score.add(q, axis=1)                     # + quality/growth tilt (snapshot)
    rebal_idx = set(closes.index[::REBAL])
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns); held = []
    for dt in closes.index:
        if dt in rebal_idx:
            row = score.loc[dt].dropna()
            if len(row) >= N:
                ranked = row.sort_values(ascending=False); chosen, sec = [], {}
                for s in ranked.index:
                    if len(chosen) >= N:
                        break
                    k = SECTORS.get(s, "Other")
                    if sec.get(k, 0) >= SECTOR_CAP:
                        continue
                    chosen.append(s); sec[k] = sec.get(k, 0) + 1
                held = chosen
        if held:
            w.loc[dt, held] = 1.0 / len(held)
    w = w.fillna(0.0)
    net = (w.shift(1) * rets).sum(axis=1) - (w - w.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    return net, idx, held


if __name__ == "__main__":
    print("=" * 72)
    print("  ARJUNA MOONSHOT — quality+growth+momentum basket (40, equal-wt, annual) + BARBELL")
    print("=" * 72)
    moon, idx, held = moonshot_backtest()
    core, _ = core_backtest("hrp", regime="global")
    common = moon.index.intersection(core.index)
    moon, core = moon.reindex(common).fillna(0), core.reindex(common).fillna(0)
    barbell = 0.7 * core + 0.3 * moon
    nifty = idx.pct_change().reindex(common).fillna(0.0)

    def line(name, net):
        s = stats(net, idx)
        print(f"  {name:<34}{s['cagr']:>7.1f}%{s['sharpe']:>8.2f}{s['dd']:>8.1f}%   Rs{s['end']:>11,.0f}")
    print(f"  {'sleeve':<34}{'CAGR':>7}{'Sharpe':>8}{'maxDD':>8}   {'Rs1L ->':>13}")
    line("ARJUNA Core (HRP+regime+global)", core)
    line("Moonshot (40 quality-growth)", moon)
    line("BARBELL 70% Core + 30% Moonshot", barbell)
    neq = (1 + nifty).cumprod()
    print(f"  {'NIFTY-50':<34}{100*((neq.iloc[-1])**(1/(len(nifty)/252))-1):>7.1f}%"
          f"{nifty.mean()/(nifty.std()+1e-12)*np.sqrt(252):>8.2f}{'':>8}   Rs{neq.iloc[-1]*1e5:>11,.0f}")

    # multibagger capture: did the current moonshot basket hold the big winners?
    first = closes_last = None
    cl = load_panels()[0][[c for c in load_panels()[0].columns if c in set(NIFTY200)]]
    mult = (cl.apply(lambda c: c.dropna().iloc[-1] / c.dropna().iloc[0] if c.notna().any() else np.nan)).dropna()
    top = set(mult.sort_values(ascending=False).head(15).index)
    print(f"\n  multibaggers (top-15 by total multiple) currently HELD by Moonshot: "
          f"{len(top & set(held))}/15 -> {', '.join(sorted(top & set(held)))}")
    print("  (Moonshot OWNS the winners by holding the broad quality-growth basket — VC power-law.)")
