"""Continuous Benchmark v1.0 · CLI.

Emits reports/benchmark.json (portfolio + per-ticker + by-sector).
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

from benchmark.lib import benchmark                                                    # noqa: E402


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  CONTINUOUS BENCHMARK v1.0 · AEGIS vs NIFTY + synthetic sector")
    print("=" * 70)

    result = benchmark.compute_benchmark()
    result["engine"]  = "benchmark"
    result["version"] = "v1.0"
    result["run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"

    if not result.get("available"):
        print(f"\n  unavailable: {result.get('reason')}")
    else:
        p = result["portfolio"]
        print(f"\n  index:                  {result['index_used']}  (available: {result['index_available']})")
        print(f"  trades benchmarked:     {p['n_trades_benchmarked']} / {p['n_trades_total']}")
        print()
        print(f"  AEGIS avg return:       {p['aegis_avg_return'] * 100:+.2f}%")
        print(f"  NIFTY avg return:       {p['nifty_avg_return'] * 100:+.2f}%" if p['nifty_avg_return'] is not None else "  NIFTY avg return:       —")
        print(f"  Sector avg return:      {p['sector_avg_return'] * 100:+.2f}%" if p['sector_avg_return'] is not None else "  Sector avg return:      —")
        print()
        print(f"  Excess alpha (avg):     {p['excess_alpha_avg'] * 100:+.2f}%" if p['excess_alpha_avg'] is not None else "  Excess alpha:           —")
        print(f"  Excess alpha (median):  {p['excess_alpha_median'] * 100:+.2f}%" if p['excess_alpha_median'] is not None else "")
        print(f"  Beat NIFTY:             {p['n_beat_nifty']} / {p['n_trades_benchmarked']}  ({p['pct_beat_nifty'] * 100:.1f}%)" if p['pct_beat_nifty'] is not None else "")
        print(f"  Verdict:                {p['verdict']}")
        print()

        print("  Top 5 alpha-generating tickers (min 3 trades):")
        for e in (result.get("top_alpha") or [])[:5]:
            print(f"    {e['ticker']:12s}  α={e['excess_alpha_avg'] * 100:+.2f}%  "
                  f"n={e['n_trades']}  beat={e['pct_beat_nifty'] * 100:.0f}%")
        print("\n  Worst 5 alpha-destroying tickers:")
        for e in (result.get("bottom_alpha") or [])[:5]:
            print(f"    {e['ticker']:12s}  α={e['excess_alpha_avg'] * 100:+.2f}%  "
                  f"n={e['n_trades']}  beat={e['pct_beat_nifty'] * 100:.0f}%")

    p = HERE.parents[1] / "reports" / "benchmark.json"
    p.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n  written: reports/benchmark.json ({p.stat().st_size / 1024:.1f} KB)")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
