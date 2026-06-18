# india/picker_pro.py
"""
PICKER PRO — the proven momentum+low-vol picker, upgraded with the real edges you flagged:
  * CORRELATION cap   — don't hold 5 look-alike names; greedily skip a pick too correlated
                        (>cap on 60d returns) with names already selected -> true diversification.
  * SECTOR cap        — max N per sector (avoid 5 banks) -> sector diversification.
  * VIX de-risk       — when India VIX is in its high regime, cut exposure (news/war/fear proxy).
Compared head-to-head with the base picker, per year, net of cost. Evidence-first: keep an
add-on only if it improves risk-adjusted return / cuts the 2026 crash.

Run: python india/picker_pro.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.equity_engine import load, composite_score, COST_BPS

# HARDENED champion = PURE MOMENTUM. (mom+low-vol won on the narrow 23-stock universe but was
# OVERFIT — on a realistic ~49-stock universe it collapsed to Sharpe 0.42; pure momentum holds
# at Sharpe ~0.79. Lesson: validate on a broad universe.)
WEIGHTS = {"momentum": 1.0}
TOPN, REBAL = 5, 5
SECTOR = {  # liquid large-cap sector map
    "HDFCBANK": "Fin", "ICICIBANK": "Fin", "SBIN": "Fin", "KOTAKBANK": "Fin",
    "AXISBANK": "Fin", "BAJFINANCE": "Fin", "TCS": "IT", "INFY": "IT", "WIPRO": "IT",
    "RELIANCE": "Energy", "ONGC": "Energy", "NTPC": "Power", "POWERGRID": "Power",
    "ITC": "FMCG", "HINDUNILVR": "FMCG", "ASIANPAINT": "FMCG", "TITAN": "Cons",
    "MARUTI": "Auto", "SUNPHARMA": "Pharma", "BHARTIARTL": "Telecom", "LT": "Infra",
    "ADANIENT": "Infra", "TATASTEEL": "Metal",
}


def vix_regime():
    p = ROOT / "data" / "raw" / "india" / "INDIAVIX_D1.parquet"
    if not p.exists():
        return None
    vix = pd.read_parquet(p)["close"].sort_index()
    hi = vix.rolling(120, min_periods=30).quantile(0.80)         # high-vol regime threshold
    return (vix > hi)                                            # True = fearful


def select(score_row, closes, ret60, corr_cap, sector_cap):
    """Greedy selection: highest score first, skip if too correlated with chosen or sector full."""
    r = score_row.dropna().sort_values(ascending=False)
    chosen, sec_count = [], {}
    for s in r.index:
        if len(chosen) >= TOPN:
            break
        sec = SECTOR.get(s, "Other")
        if sector_cap and sec_count.get(sec, 0) >= sector_cap:
            continue
        if corr_cap and chosen:
            cc = ret60[chosen].corrwith(ret60[s]).abs().max()
            if cc > corr_cap:
                continue
        chosen.append(s); sec_count[sec] = sec_count.get(sec, 0) + 1
    return chosen


def backtest(corr_cap=None, sector_cap=None, vix_derisk=False):
    closes, _ = load()
    rets = closes.pct_change().fillna(0.0)
    ret60 = rets.rolling(60).mean() * 0 + rets          # placeholder; use raw daily for corr
    score = composite_score(closes, WEIGHTS)
    rebal_days = closes.index[::REBAL]
    vix_hi = vix_regime()
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    cur = []
    for dt in closes.index:
        if dt in rebal_days:
            if corr_cap or sector_cap:
                roll = rets.loc[:dt].tail(60)
                cur = select(score.loc[dt], closes, roll, corr_cap, sector_cap)
            else:
                r = score.loc[dt].dropna().sort_values(ascending=False)
                cur = list(r.index[:TOPN])
        if cur:
            wt = 1.0 / len(cur)
            w.loc[dt, cur] = wt
    w = w.fillna(0.0)
    gross = (w.shift(1) * rets).sum(axis=1)
    net = gross - (w - w.shift(1)).abs().sum(axis=1) * (COST_BPS / 1e4)
    if vix_derisk and vix_hi is not None:
        scale = vix_hi.reindex(net.index).fillna(False).map({True: 0.5, False: 1.0})
        net = net * scale
    return net


def report(name, net):
    eq = (1 + net).cumprod(); peak = eq.cummax()
    rows = [(y, 100 * ((1 + g).prod() - 1)) for y, g in net.groupby(net.index.year) if len(g) > 30]
    pos = sum(1 for _, r in rows if r > 0)
    sh = net.mean() / (net.std() + 1e-12) * np.sqrt(252)
    print(f"  {name:<34}{100*(eq.iloc[-1]-1):>7.0f}%{sh:>8.2f}{100*((peak-eq)/peak).max():>8.1f}%"
          f"{pos:>4}/{len(rows):<3}{min(r for _,r in rows):>8.1f}")
    return rows


print("=" * 84)
print("  PICKER PRO — base vs +correlation cap / +sector cap / +VIX de-risk (per-yr, net)")
print("=" * 84)
print(f"  {'variant':<34}{'total':>8}{'Sharpe':>8}{'maxDD':>8}{'pos yr':>7}{'worst%':>8}")
base = report("base (mom+low-vol)", backtest())
report("+ correlation cap 0.85", backtest(corr_cap=0.85))
report("+ sector cap (max 2/sector)", backtest(sector_cap=2))
report("+ corr 0.85 + sector 2", backtest(corr_cap=0.85, sector_cap=2))
report("+ corr+sector + VIX de-risk", backtest(corr_cap=0.85, sector_cap=2, vix_derisk=True))
rows = report("+ VIX de-risk only", backtest(vix_derisk=True))
print("\n  (worst% = worst single year — the 2026 crash is what we want to shrink)")
