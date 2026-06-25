# india/evidence/layer_value_test.py
"""
LAYER VALUE TEST (Research Mode) — the user's key idea: optimise FEATURE LAYERS, not just portfolio
settings. For any candidate layer (Sector Score, Earnings, News, Flows...), measure its INCREMENTAL
recommendation quality over the baseline. KEEP only if it lifts the evidence; otherwise DISCARD.

  Baseline      = current selection (lowest-volatility, sector-capped)
  + Layer X     = same, but informed by layer X
  Incremental   = RQS(baseline + X) - RQS(baseline)   ·   KEEP if > +0.02, else DISCARD

RQS (Recommendation Quality Score) = average forward-return percentile of the picks (0.50 = random).
This turns AEGIS from "find the best portfolio settings" into "discover which information creates
alpha." It is data-honest: layers needing data we don't have (fundamentals/news/earnings) plug into
the SAME test the day that data exists — today only price-derivable layers (Sector Score) can run.

Run: python india/evidence/layer_value_test.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
warnings.simplefilter("ignore")
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.sectors import SECTORS, sector_of

CAD, LOOK, HOLD, TOPN, CAP = 21, 120, 63, 15, 2


def _rqs(picks_per_date, fwd_pct_per_date):
    vals = []
    for dt, picks in picks_per_date.items():
        p = fwd_pct_per_date.get(dt)
        if p is not None and picks:
            vals.append(p.reindex(picks).dropna().mean())
    return float(np.nanmean(vals)) if vals else np.nan


def lowvol_pick(hist, cols, sector_cap, allowed=None):
    iv = (1.0 / hist[cols].std().replace(0, np.nan)).dropna().sort_values(ascending=False)
    chosen, sec = [], {}
    for s in iv.index:
        if allowed is not None and sector_of(s) not in allowed:
            continue
        if len(chosen) >= TOPN:
            break
        k = SECTORS.get(s, "Other")
        if sec.get(k, 0) >= sector_cap:
            continue
        chosen.append(s); sec[k] = sec.get(k, 0) + 1
    return chosen


def main():
    closes, *_ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    base_picks, sec_picks, fwd_pct = {}, {}, {}
    for i in range(LOOK, len(closes) - HOLD, CAD):
        dt = closes.index[i]
        hist = rets.iloc[i - LOOK:i].dropna(axis=1, how="any")
        cols = list(hist.columns)
        if len(cols) < 40:
            continue
        fwd = (closes.iloc[i + HOLD] / closes.iloc[i] - 1).reindex(cols).dropna()
        fwd_pct[dt] = fwd.rank(pct=True)
        # Sector Score layer = sector 3M momentum; keep only top-half sectors
        smom = {}
        for sec in set(sector_of(c) for c in cols):
            names = [c for c in cols if sector_of(c) == sec]
            smom[sec] = (closes[names].iloc[i] / closes[names].iloc[i - HOLD] - 1).mean()
        med = np.median(list(smom.values())); strong = {s for s, v in smom.items() if v >= med}
        base_picks[dt] = lowvol_pick(hist, cols, CAP)
        sec_picks[dt] = lowvol_pick(hist, cols, CAP, allowed=strong)
    base_rqs = _rqs(base_picks, fwd_pct); sec_rqs = _rqs(sec_picks, fwd_pct)
    inc = sec_rqs - base_rqs

    print("=" * 70)
    print("  LAYER VALUE TEST — does the layer add INCREMENTAL recommendation quality?")
    print("=" * 70)
    print(f"  Baseline (lowest-vol, sector-capped)        RQS {base_rqs:.3f}")
    print(f"  + Sector Score (price 3M strength filter)   RQS {sec_rqs:.3f}")
    print(f"  Incremental                                  {inc:+.3f}")
    verdict = "KEEP — adds value" if inc > 0.02 else "DISCARD — no incremental value"
    print(f"  VERDICT: {verdict}")
    print("\n  (0.50 = random. A price-based Sector Score competing for the same low-vol names rarely")
    print("  helps — consistent with the rejected sector-momentum tilt. A FUNDAMENTAL sector score")
    print("  needs sector earnings/valuation data we don't have; it plugs into this same test then.)")
    print("\n  This is the FRAMEWORK: every future data layer (earnings/flows/news) earns its place")
    print("  here by INCREMENTAL RQS, or it is discarded. Information must prove it creates alpha.")


if __name__ == "__main__":
    main()
