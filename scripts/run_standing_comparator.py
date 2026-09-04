"""P5.5 Standing Comparator · daily runner.

Runs the FIXED equal-weight top-10 by 3-month momentum comparator for each
market. Appends one observation per day to the ledger. Rebalance only every
REBALANCE_INTERVAL_DAYS · otherwise holds the last basket.

Governance: comparator is NOT a candidate · NEVER modifies R2 production.
"""
from __future__ import annotations
import argparse, io, json, sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.comparators.standing_comparator import emit_daily_observation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--asof", type=str, default=None)
    args = ap.parse_args()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        obs = emit_daily_observation(_ROOT, m, args.asof)
        print(f"{m.upper()}: rebalance={obs['rebalance']} · picks={len(obs.get('picks',[]))}")
        if obs.get("rebalance"):
            for p in obs["picks"][:5]:
                print(f"  {p['ticker']:10s}  mom_3m={p['momentum_3m_pct']:+.2f}%  weight={p['weight']}")


if __name__ == "__main__":
    main()
