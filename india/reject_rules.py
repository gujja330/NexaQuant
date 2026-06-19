# india/reject_rules.py
"""
STAGE B3 — hard REJECT rules (deterministic pre-trade vetoes).

Before the AI even scores a stock, eliminate the obviously-bad ones (research checklist sec.4):
  * ILLIQUID        : bottom-decile traded value -> impact cost + manipulation risk.
  * BROKEN TREND    : below 200-DMA AND in a deep drawdown -> falling knife.
  * WEAK BALANCE    : very high debt AND negative margin -> fragile business (snapshot fundamentals).
  * SECTOR DOWNTREND: its sector is in the weakest band -> don't fight a weak sector.
  * MOMENTUM-CRASH  : extreme run-up + extreme volatility -> crowded, crash-prone.

These are NON-NEGOTIABLE vetoes (no AI). Returns a boolean Series (True = REJECT) aligned to the
feature panel. We evaluate by checking the REJECTED names earn LESS than the kept ones (Rs first).

Run (self-test): python india/reject_rules.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.dataset import build_dataset


def reject_mask(panel):
    """panel: (date,symbol) feature frame. Returns boolean Series, True = veto this name."""
    p = panel
    rej = pd.Series(False, index=p.index)

    # ILLIQUID: bottom-decile turnover within each date
    liq_floor = p.groupby(level="date")["turnover_log"].transform(lambda s: s.quantile(0.10))
    rej |= p["turnover_log"] < liq_floor

    # BROKEN TREND: below 200-DMA and >20% off the 3m high
    rej |= (p["above_ma200"] < 0.5) & (p["dd_3m"] < -0.20)

    # WEAK BALANCE SHEET: very high debt and negative profit margin (snapshot)
    if "f_debt2eq" in p and "f_margin" in p:
        rej |= (p["f_debt2eq"] > 200) & (p["f_margin"] < 0)

    # SECTOR DOWNTREND: stock's sector in the weakest 15% band
    rej |= p["sector_rank"] < 0.15

    # MOMENTUM-CRASH risk: extreme 6m run-up AND top-decile volatility
    vol_hi = p.groupby(level="date")["vol_3m"].transform(lambda s: s.quantile(0.90))
    rej |= (p["mom_6m"] > 1.0) & (p["vol_3m"] > vol_hi)

    return rej.fillna(False)


if __name__ == "__main__":
    print("=" * 70)
    print("  STAGE B3 — reject-rules self-test (Rs first)")
    print("=" * 70)
    for freq in ("M", "W"):
        df = build_dataset(freq).dropna(subset=["fwd_ret"])
        rej = reject_mask(df)
        kept, dropped = df[~rej], df[rej]
        kr, dr = kept["fwd_ret"].mean(), dropped["fwd_ret"].mean()
        print(f"\n  [{freq}] rejected {rej.mean()*100:.1f}% of rows ({rej.sum():,}/{len(rej):,})")
        print(f"     KEPT    avg fwd_ret {100*kr:+.2f}%   win {100*(kept['fwd_ret']>21/1e4).mean():.1f}%")
        print(f"     REJECTED avg fwd_ret {100*dr:+.2f}%   win {100*(dropped['fwd_ret']>21/1e4).mean():.1f}%")
        print(f"     -> rejects underperform kept by {100*(kr-dr):+.2f}% per period "
              f"({'GOOD - vetoing losers' if kr > dr else 'BAD - vetoing winners!'})")
