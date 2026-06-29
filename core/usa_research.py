# core/usa_research.py
"""
USA RESEARCH CYCLE 001 — do point-in-time SEC fundamentals beat the price-only baseline?

The first real AI-Lab experiment for USA. NOT "add more datasets" — TEST the one we have. Walk-forward,
point-in-time (fundamentals as KNOWN at each past rebalance, reconstructed from SEC 'filed' dates), on
the names that have both price history and SEC data.

Measures:
  - Information Coefficient (IC): rank-corr(fundamental composite, forward return), averaged over dates.
  - Incremental lift: forward-return percentile of price+fundamental selection vs price-only selection.
  Verdict: PROMOTE only if IC is meaningful AND consistent AND lift > 0; else REJECT / INSUFFICIENT.

Honest about power: USA price history + SEC coverage are limited, so an "insufficient evidence" verdict
is a valid, disciplined outcome (and tells us to widen coverage before concluding).

Run:  python -m core.usa_research
"""
import sys, glob, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from core.market_adapter import USAAdapter
from core.usa_fundamentals import normalize_one, RAW

CAD, HOLD = 21, 63           # monthly rebalance, ~quarter forward window


def composite(funds):
    """Higher = better fundamentals: blend of ROE, net margin, revenue growth, low leverage (z-scored)."""
    df = pd.DataFrame(funds).T
    parts = []
    for col, sign in [("f_roe", 1), ("f_net_margin", 1), ("f_rev_growth_yoy", 1), ("f_debt_to_equity", -1)]:
        if col in df:
            z = (df[col] - df[col].mean()) / (df[col].std() + 1e-9)
            parts.append(sign * z.clip(-3, 3))
    return pd.concat(parts, axis=1).mean(axis=1) if parts else pd.Series(dtype=float)


def main():
    adp = USAAdapter()
    closes = adp.get_market_data()[0]
    covered = [Path(f).stem for f in glob.glob(str(RAW / "*.json")) if Path(f).stem != "cik_map"]
    covered = [c for c in covered if c in closes.columns]
    closes = closes[covered]
    print("=" * 74)
    print("  USA RESEARCH CYCLE 001 — SEC fundamentals vs price-only baseline")
    print("=" * 74)
    print(f"  coverage: {len(covered)} names with BOTH price history and SEC filings\n")

    ics, base_rqs, fund_rqs, n = [], [], [], 0
    for i in range(126, len(closes) - HOLD, CAD):
        dt = str(closes.index[i].date())
        fwd = (closes.iloc[i + HOLD] / closes.iloc[i] - 1).dropna()
        if len(fwd) < 15:
            continue
        funds = {}
        for s in fwd.index:
            r = normalize_one(s, today=dt)                 # PIT fundamentals as known at dt
            if r:
                funds[s] = {k: v for k, v in r.items() if k.startswith("f_")}
        comp = composite(funds).dropna()
        common = comp.index.intersection(fwd.index)
        if len(common) < 15:
            continue
        pct = fwd.rank(pct=True)
        ic = comp[common].rank().corr(fwd[common].rank())  # Spearman IC
        ics.append(ic)
        # selection: price-only (lowest vol) vs price + top-half-fundamental
        vol = closes.pct_change().iloc[i - 120:i].std()
        base = list(vol[common].nsmallest(10).index)
        strong = set(comp[common][comp[common] >= comp[common].median()].index)
        fund_pick = list(vol[[c for c in common if c in strong]].nsmallest(10).index)
        base_rqs.append(pct.reindex(base).dropna().mean())
        fund_rqs.append(pct.reindex(fund_pick).dropna().mean() if fund_pick else np.nan)
        n += 1

    if n < 4:
        print("  INSUFFICIENT DATA — too few walk-forward dates with coverage to conclude.")
        print("  Action: widen SEC coverage (full universe) + longer price history, then re-run.")
        return
    mean_ic = float(np.nanmean(ics)); ic_ir = mean_ic / (np.nanstd(ics) + 1e-9) * np.sqrt(len(ics))
    b, f = float(np.nanmean(base_rqs)), float(np.nanmean(fund_rqs)); lift = f - b
    print(f"  walk-forward dates: {n}")
    print(f"  mean IC (fundamental composite vs fwd return): {mean_ic:+.3f}  (IC-IR {ic_ir:+.2f})")
    print(f"  price-only RQS {b:.3f}   ·   price+fundamental RQS {f:.3f}   ·   lift {lift:+.3f}")
    promote = (abs(mean_ic) > 0.03 and abs(ic_ir) > 2.0 and lift > 0.02)
    print("  " + "-" * 70)
    if promote:
        print("  VERDICT: PROMISING — SEC fundamentals add measurable lift. Validate further (more")
        print("  coverage + forward paper) before promoting to the USA production baseline.")
    else:
        print("  VERDICT: NOT PROMOTED (yet) — no statistically meaningful lift on current coverage.")
        print("  Either fundamentals don't help selection here, or coverage/history is too thin to tell.")
        print("  Disciplined outcome: do NOT add the feature to production on this evidence.")
    print("  (Honest scope: limited USA history + SEC coverage. This is a first pass, not a final word.)")


if __name__ == "__main__":
    main()
