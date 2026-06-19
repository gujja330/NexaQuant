# india/labels.py
"""
STAGE A3 — Labels for the Arjuna AI models.

Two targets, both computed at the rebalance frequency and aligned to the feature panel index
(date, symbol) so they join 1:1 with india/feature_engine.build_features():

  * fwd_ret   : forward return from this rebalance date to the NEXT one (what we'd actually earn).
  * fwd_rank  : cross-sectional percentile rank of fwd_ret among that date's stocks (0..1).
                -> the RANKER's target (Gu-Kelly-Xiu framing: predict relative winners).
  * win       : 1 if fwd_ret beats the round-trip cost, else 0.
                -> the AVOIDANCE filter's target (P(win); veto low-probability picks before ordering).

The last rebalance date has no "next" -> its labels are NaN (dropped in training, kept for live picks).

Run (self-test): python india/labels.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.feature_engine import load_panels, STEP

COST = 21.0 / 1e4                                  # round-trip cost threshold a "win" must clear


def build_labels(freq="W"):
    closes, *_ = load_panels()
    step = STEP.get(freq, 5)
    rebal = closes.index[::step]
    rc = closes.reindex(rebal)
    fwd_ret = rc.shift(-1) / rc - 1.0              # this rebal -> next rebal
    fwd_rank = fwd_ret.rank(axis=1, pct=True)      # 0..1 cross-sectional rank
    win = (fwd_ret > COST).astype(float).where(fwd_ret.notna())

    out = pd.concat({"fwd_ret": fwd_ret.stack(dropna=False),
                     "fwd_rank": fwd_rank.stack(dropna=False),
                     "win": win.stack(dropna=False)}, axis=1)
    out.index.names = ["date", "symbol"]
    return out


if __name__ == "__main__":
    print("=" * 70)
    print("  STAGE A3 — labels self-test")
    print("=" * 70)
    for freq in ("W", "M"):
        lab = build_labels(freq)
        valid = lab.dropna(subset=["fwd_ret"])
        wr = valid["win"].mean()
        print(f"\n  freq={freq}: {lab.shape[0]:,} rows, {valid.shape[0]:,} with a forward label")
        print(f"           base win rate (fwd_ret > cost): {100*wr:.1f}%")
        print(f"           mean fwd_ret {100*valid['fwd_ret'].mean():+.2f}%  "
              f"median {100*valid['fwd_ret'].median():+.2f}%")
    print("\n  sample (first 3 with labels):")
    print(valid.head(3).to_string())
