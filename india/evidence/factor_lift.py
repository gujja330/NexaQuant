# india/evidence/factor_lift.py
"""
FACTOR LIFT TABLE (Research Mode) — "what actually works?" Every price-derivable factor is measured
for INCREMENTAL recommendation quality over the low-vol baseline. Positive lift -> KEEP; else THROW
IT AWAY. This is the evidence-based version of "does RSI matter? does momentum matter?".

Method: at each rebalance, baseline = lowest-vol picks (sector-capped). For each factor, the
augmented selection picks lowest-vol names that are ALSO in the top half by that factor. RQS =
average forward-return percentile of the picks (0.50 = random). Lift = RQS(augmented) - RQS(base).

Honest scope: only PRICE factors run here (momentum, relative strength, trend). Fundamentals/news/
earnings need data we don't have and plug into this SAME table the day that data exists.

Run: python india/evidence/factor_lift.py
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


def lowvol(hist, cols, allowed=None):
    iv = (1.0 / hist[cols].std().replace(0, np.nan)).dropna().sort_values(ascending=False)
    chosen, sec = [], {}
    for s in iv.index:
        if allowed is not None and s not in allowed:
            continue
        if len(chosen) >= TOPN:
            break
        k = SECTORS.get(s, "Other")
        if sec.get(k, 0) >= CAP:
            continue
        chosen.append(s); sec[k] = sec.get(k, 0) + 1
    return chosen


def main():
    closes, _, _, _, idx, _, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    FACTORS = ["3M momentum", "6M momentum", "Rel strength vs Nifty", "Above 200-DMA"]
    base_acc, fac_acc = [], {f: [] for f in FACTORS}
    for i in range(LOOK, len(closes) - HOLD, CAD):
        hist = rets.iloc[i - LOOK:i].dropna(axis=1, how="any"); cols = list(hist.columns)
        if len(cols) < 40:
            continue
        fwd = (closes.iloc[i + HOLD] / closes.iloc[i] - 1).reindex(cols).dropna()
        pct = fwd.rank(pct=True)
        px = closes.iloc[i]
        fv = {
            "3M momentum": (px / closes.iloc[i - 63] - 1).reindex(cols),
            "6M momentum": (px / closes.iloc[i - 126] - 1).reindex(cols) if i > 126 else pd.Series(0, index=cols),
            "Rel strength vs Nifty": (px / closes.iloc[i - 63] - 1).reindex(cols) - (idx.iloc[i] / idx.iloc[i - 63] - 1),
            "Above 200-DMA": (px > closes.iloc[i - 200:i].mean()).reindex(cols).astype(float) if i > 200 else pd.Series(1.0, index=cols),
        }
        base = lowvol(hist, cols)
        base_acc.append(pct.reindex(base).dropna().mean())
        for f in FACTORS:
            v = fv[f].dropna(); strong = set(v[v >= v.median()].index)
            aug = lowvol(hist, cols, allowed=strong)
            fac_acc[f].append(pct.reindex(aug).dropna().mean() if aug else np.nan)
    base_rqs = float(np.nanmean(base_acc))

    print("=" * 66)
    print("  FACTOR LIFT TABLE — does each factor add recommendation quality?")
    print("=" * 66)
    print(f"  Baseline (lowest-vol, sector-capped): RQS {base_rqs:.3f}\n")
    print(f"  {'Factor':<24}{'+RQS':>8}{'Lift':>8}   Verdict")
    for f in FACTORS:
        r = float(np.nanmean(fac_acc[f])); lift = r - base_rqs
        verdict = "KEEP" if lift > 0.02 else "throw away"
        print(f"  {f:<24}{r:>8.3f}{lift:>+8.3f}   {verdict}")
    print("\n  (0.50 = random. Price factors competing for the same low-vol names rarely lift RQS —")
    print("  consistent with every prior test: price doesn't rank future winners. The KEEP/throw-away")
    print("  gate is the point: fundamentals/earnings/news/flows must clear THIS bar to enter the engine.)")


if __name__ == "__main__":
    main()
