"""Validation Engine v2.0 · price context CLI.

Emits reports/price_context.json with CMP + 52W bounds per ticker.
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from validation_v2.lib import price_context                                             # noqa: E402


def main() -> int:
    t0 = time.time()
    print("=" * 60)
    print("  PRICE CONTEXT · CMP + 52W bounds per ticker")
    print("=" * 60)

    result = price_context.build_all()
    result["run_utc"] = datetime.now(timezone.utc).isoformat() + "Z"

    print(f"  tickers:       {result['n_tickers']}")
    print(f"  with price:    {result['n_available']}")
    print(f"  missing:       {result['n_missing']}")
    print()

    # Distance-from-52w-high summary — a proxy for "how much room"
    at_high  = sum(1 for r in result["tickers"].values()
                     if r.get("available") and abs(r["distance_from_52w_high"]) < 0.05)
    at_low   = sum(1 for r in result["tickers"].values()
                     if r.get("available") and r["distance_from_52w_low"] < 0.10)
    print(f"  within 5% of 52W high:  {at_high}")
    print(f"  within 10% of 52W low:  {at_low}")

    p = HERE.parents[1] / "reports" / "price_context.json"
    p.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  written: reports/price_context.json ({p.stat().st_size / 1024:.1f} KB)")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
