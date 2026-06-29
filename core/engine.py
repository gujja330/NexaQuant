# core/engine.py
"""
CORE ENGINE — market-agnostic recommendation logic. Runs the SAME validated process on ANY market via a
MarketAdapter: lowest-volatility selection + sector cap + HRP weighting + regime exposure.

This is the genuine "core extraction": the portfolio math (HRP) is reused from the frozen india engine
(it already operates on plain return matrices), while selection + regime are reimplemented here in a
market-neutral way (they use adapter.get_sector / the adapter's index+vix, not India hardcodes).

USA runs in PAPER mode — same engine, US data, output clearly marked paper. It becomes the USA price
baseline that future multi-factor research (SEC fundamentals, insider, ETF flows, earnings, sector
strength, macro, news) must beat through the data-layer gate — one factor at a time, never hardcoded.

Run:  python -m core.engine usa        # USA paper recommendations
      python -m core.engine india       # sanity: same core on India data
"""
import sys, warnings
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import weights_for, LOOKBACK      # HRP is already market-agnostic (returns matrix in)
from core.market_adapter import get_adapter


def select_low_vol(hist, topn, sector_cap, sector_fn):
    """Lowest trailing-volatility names, capped per sector — market-neutral (uses adapter.get_sector)."""
    iv = (1.0 / hist.std().replace(0, np.nan)).dropna().sort_values(ascending=False)
    chosen, sec = [], {}
    for s in iv.index:
        if len(chosen) >= topn:
            break
        k = sector_fn(s)
        if sec.get(k, 0) >= sector_cap:
            continue
        chosen.append(s); sec[k] = sec.get(k, 0) + 1
    return chosen


def regime_exposure(idx, vix, lookback=200):
    """Market-agnostic regime: de-risk when the index is below its 200-DMA and/or volatility is high."""
    scale = 1.0
    if len(idx) >= lookback and idx.iloc[-1] < idx.tail(lookback).mean():
        scale *= 0.6
    if vix is not None and len(vix) >= 120 and vix.iloc[-1] > vix.tail(120).quantile(0.80):
        scale *= 0.6
    label = "Strong" if scale >= 0.9 else ("Neutral" if scale >= 0.6 else "Weak")
    return scale, label


def recommend(adapter, topn=12, sector_cap=2, name_cap=0.30):
    closes, highs, lows, vols, idx, vix, _ = adapter.get_market_data()
    uni = set(adapter.get_universe())
    closes = closes[[c for c in closes.columns if c in uni]]
    rets = closes.pct_change()
    hist = rets.tail(LOOKBACK).dropna(axis=1, how="any")
    sel = select_low_vol(hist, topn, sector_cap, adapter.get_sector)
    w = weights_for("hrp", hist[sel]); w = (w / w.sum()).clip(upper=name_cap); w = w / w.sum()
    exp, regime = regime_exposure(idx, vix)
    px = closes.iloc[-1]; vol = hist.std() * np.sqrt(252) * 100
    rows = [{"Stock": s, "Sector": adapter.get_sector(s), "Price": round(float(px[s]), 2),
             "Weight %": round(100 * float(w[s]), 1), "Vol %": round(float(vol[s]))}
            for s in w.sort_values(ascending=False).index]
    return pd.DataFrame(rows), exp, regime, str(closes.index[-1].date())


def main():
    market = sys.argv[1] if len(sys.argv) > 1 else "usa"
    adp = get_adapter(market)
    recs, exp, regime, asof = recommend(adp)
    tag = "PAPER" if market != "india" else "(core re-run; production = india/ frozen engine)"
    print("=" * 64)
    print(f"  AEGIS CORE ENGINE — {market.upper()}  {tag}")
    print("=" * 64)
    print(f"  as-of {asof} · regime {regime} · deploy {exp:.0%} · {len(recs)} holdings\n")
    print(recs.to_string(index=False))
    if market != "india":
        out = ROOT / "data" / "usa" / f"USA_PAPER_{date.today()}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        recs.assign(asof=asof, regime=regime, deploy=f"{exp:.0%}", mode="PAPER").to_csv(out, index=False)
        print(f"\n  PAPER recommendations -> {out.relative_to(ROOT)}")
        print("  USA is PAPER ONLY — same validated price/risk engine, US data. Becomes the baseline")
        print("  future USA multi-factor research must beat (SEC/insider/ETF/earnings via the gate).")


if __name__ == "__main__":
    main()
