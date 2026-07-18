"""Validation Engine v2.0 · per-ticker validation rollup CLI.

Reads reports/learning.parquet + reports/recommendations.json.
Emits reports/stock_validation.json with per-ticker historical rollup."""
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

from validation_v2.lib import stock_history                                            # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 72); print(f"  {msg}"); print("=" * 72)


def main() -> int:
    t0 = time.time()
    _banner("STOCK VALIDATION · PER-TICKER HISTORICAL ROLLUP")

    result = stock_history.build_all()
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    result["run_utc"] = datetime.now(timezone.utc).isoformat() + "Z"
    result["engine"]  = "Validation Engine · stock rollup"
    result["version"] = "v2.0.1"
    result["governance"] = ("Advisory only. Historical per-ticker rollup "
                              "is derived deterministically from learning.parquet.")

    print(f"  tickers analyzed:      {result['n_tickers']}")
    print(f"  with trade history:    {result['n_with_history']}")
    print(f"  without history:       {result['n_without_history']}")

    # Reliability distribution
    stars_dist = {i: 0 for i in range(6)}
    for t, r in result["tickers"].items():
        stars_dist[r["reliability_stars"]] += 1
    _banner("RELIABILITY STAR DISTRIBUTION")
    for stars in [5, 4, 3, 2, 1, 0]:
        bar = "*" * stars + "-" * (5 - stars)
        print(f"  {bar}   {stars_dist[stars]:>4} tickers")

    # Top-10 by reliability (5-star + high win rate)
    _banner("TOP-10 BY RELIABILITY (5-star, most trades, highest win rate)")
    sorted_tickers = sorted(
        [(t, r) for t, r in result["tickers"].items() if r["reliability_stars"] >= 4],
        key=lambda kv: (-kv[1]["reliability_stars"], -kv[1]["win_rate"], -kv[1]["n_trades"])
    )[:10]
    for t, r in sorted_tickers:
        print(f"  {t:<14} {'*' * r['reliability_stars']:<6} "
              f"wr {r['win_rate']*100:>5.1f}%  "
              f"n {r['n_trades']:>2}  "
              f"avg_ret {r['avg_return_pct']*100:>+6.2f}%  "
              f"largest_gain {r['largest_gain_pct']*100:>+6.1f}%  "
              f"largest_loss {r['largest_loss_pct']*100:>+6.1f}%")

    # Write
    p = HERE.parents[1] / "reports" / "stock_validation.json"
    p.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    _banner(f"WRITTEN")
    print(f"  reports/stock_validation.json ({p.stat().st_size / 1024:.1f} KB)")

    _banner(f"DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
