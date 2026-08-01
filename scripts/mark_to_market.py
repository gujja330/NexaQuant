"""Standalone mark-to-market re-pricer for the position store.

Post-mortem 2026-07-31 fix: Max Gain and Max DD were stuck at 0.00% because
position_store's high_water / low_water were never re-priced after opening.

This script is SAFE to run any time:
  · Reads latest close from daily bar cache (yfinance fallback for USA)
  · Updates last_seen_price, high_water, low_water for every active position
  · Never touches first_seen_* fields (position identity preserved)
  · Never triggers the enricher, snapshot archiver, or recommendation regen
  · Complements scripts/stamp_only.py (they cover different concerns)

Usage:
    python scripts/mark_to_market.py --market india
    python scripts/mark_to_market.py --market usa
    python scripts/mark_to_market.py --market both

Called automatically by scripts/telegram_command_center_send.py before
every send · so Max Gain/DD always reflect today's actual close.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.portfolio.position_store.mark_to_market import (  # noqa: E402
    mark_to_market,
    validate_position_freshness,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--validate-only", action="store_true",
                       help="Skip re-pricing · only run freshness check")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    asof = args.asof or date.today().isoformat()
    markets = ["india", "usa"] if args.market == "both" else [args.market]

    all_ok = True
    for m in markets:
        if not args.validate_only:
            r = mark_to_market(_ROOT, m, asof=asof)
            print(f"[mark_to_market:{m}] asof={asof} "
                    f"n_positions={r['n_positions']} "
                    f"n_repriced={r['n_repriced']} "
                    f"n_missing_price={r['n_missing_price']}")
            if r["errors"]:
                for e in r["errors"][:3]:
                    print(f"  · {e}")

        v = validate_position_freshness(_ROOT, m, asof=asof, max_stale_days=1)
        print(f"[freshness_check:{m}] verdict={v['verdict']} "
                f"n_active={v['n_active']} n_stale={v['n_stale']}")
        if v["stale_tickers"]:
            for s in v["stale_tickers"][:5]:
                print(f"  · {s['ticker']}: last_seen={s['last_seen']} "
                        f"({s['days_behind']}d behind asof)")
        if v["verdict"] == "STALE":
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
