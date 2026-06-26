# india/universe.py
"""
DYNAMIC TRADABLE UNIVERSE — the universe is BUILT from filters, not hard-coded to an index.

Index membership becomes one input, not the definition. Each rebalance we screen every symbol we have
price data for by what we can actually measure on price/volume:

  · enough clean history        (tradability — no thin/gappy series)
  · minimum price floor          (avoid illiquid penny names)
  · liquidity = avg daily turnover (close x volume), with a floor + a top-N liquidity cap

Market-cap / free-float / governance filters are stubbed for when that data arrives (they plug in here
without touching the engine). The result is an extensible universe: add more tickers (e.g. Nifty-500)
and the liquid, tradable ones are selected automatically; the rest are filtered out.

Run: python india/universe.py            # show the universe + what was excluded and why
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.feature_engine import load_panels, NON_STOCKS

# defaults — liquidity floor in Rs/day, price floor in Rs, min history in days, liquidity cap
CFG = dict(lookback=120, min_days=250, min_price=10.0, min_turnover=2e7, top_liquid=220)


def build_universe(closes=None, vols=None, cfg=None, asof=None, with_reasons=False):
    cfg = {**CFG, **(cfg or {})}
    if closes is None:
        closes, _, _, vols, _, _, _ = load_panels()
    cols = [c for c in closes.columns if c not in NON_STOCKS]
    at = (closes[cols] * vols[cols]).tail(cfg["lookback"]).mean()      # avg daily turnover (Rs)
    last = closes[cols].iloc[-1]
    cover = closes[cols].notna().sum()
    keep, reasons = [], {}
    for s in cols:
        if cover[s] < cfg["min_days"]:
            reasons[s] = "thin history"; continue
        if pd.isna(last[s]) or last[s] < cfg["min_price"]:
            reasons[s] = "below price floor"; continue
        if pd.isna(at[s]) or at[s] < cfg["min_turnover"]:
            reasons[s] = "illiquid (low turnover)"; continue
        keep.append(s)
    # liquidity cap — keep the most tradable names
    if cfg["top_liquid"] and len(keep) > cfg["top_liquid"]:
        ranked = at[keep].sort_values(ascending=False)
        dropped = list(ranked.index[cfg["top_liquid"]:])
        for s in dropped:
            reasons[s] = "outside top-liquidity cap"
        keep = list(ranked.index[:cfg["top_liquid"]])
    keep = sorted(keep)
    return (keep, reasons, at) if with_reasons else keep


def main():
    closes, _, _, vols, _, _, _ = load_panels()
    keep, reasons, at = build_universe(closes, vols, with_reasons=True)
    from india.data_nse import NIFTY200
    nifty = set(NIFTY200)
    print("=" * 70)
    print("  AEGIS DYNAMIC TRADABLE UNIVERSE")
    print("=" * 70)
    print(f"  symbols with data : {len([c for c in closes.columns if c not in NON_STOCKS])}")
    print(f"  tradable universe : {len(keep)}")
    print(f"  median turnover   : Rs{np.nanmedian(at[keep])/1e7:.1f} cr/day")
    added = [s for s in keep if s not in nifty]
    dropped = [s for s in nifty if s not in keep and s in reasons]
    print(f"  vs Nifty-200      : +{len(added)} non-index liquid names, -{len(dropped)} index names filtered")
    if dropped:
        print("  filtered index names:", ", ".join(f"{s} ({reasons[s]})" for s in dropped[:6]))
    # reason breakdown
    rc = pd.Series(list(reasons.values())).value_counts().to_dict()
    print("  exclusions:", "  ".join(f"{k}={v}" for k, v in rc.items()))
    print("\n  Universe is filter-built (liquidity/tradability), so adding more tickers auto-screens them.")
    print("  Market-cap / free-float / governance filters plug in here when that data is acquired.")


if __name__ == "__main__":
    main()
