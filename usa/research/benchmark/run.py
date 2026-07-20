"""AEGIS USA · Continuous Benchmark v1.0.

Compares USA recommendations against S&P 500 (^GSPC) as primary
benchmark, NASDAQ 100 (^NDX) and Dow (^DJI) as secondaries. Day 1
baseline: only sets up the schema — no historical closed trades yet
(no learning.parquet-equivalent for USA). Populates as USA archive
accumulates closed trades.

USD everywhere.
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

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Continuous Benchmark v1.0")
    print("=" * 70)

    # Day-1 baseline — no closed trades yet. Structure preserved for symmetry
    # with India's benchmark.json so the same dashboard/report renderers work.
    result = {
        "engine":              "usa_benchmark",
        "version":             "v1.0",
        "market":              "USA",
        "currency":            "USD",
        "run_utc":             datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "available":           True,
        "index_used":          "^GSPC",
        "index_available":     True,
        "peers_max_per_sector": 20,
        "portfolio": {
            "n_trades_total":        0,
            "n_trades_benchmarked":  0,
            "aegis_avg_return":      None,
            "aegis_median_return":   None,
            "nifty_avg_return":      None,       # kept "nifty" key for schema-compat with India renderers
            "spx_avg_return":        None,       # USA-native
            "sector_avg_return":     None,
            "excess_alpha_avg":      None,
            "excess_alpha_median":   None,
            "n_beat_nifty":          0,
            "n_beat_spx":            0,
            "n_lost_to_nifty":       0,
            "n_lost_to_spx":         0,
            "pct_beat_nifty":        None,
            "pct_beat_spx":          None,
            "verdict":               "insufficient_evidence",
        },
        "per_ticker":  {},
        "by_sector":   {},
        "top_alpha":   [],
        "bottom_alpha": [],
        "trades":      [],
        "note":        "Day-1 baseline. USA has no historical closed-trade "
                       "corpus (unlike India's learning.parquet). Populates "
                       "as USA paper portfolio accumulates closed positions.",
    }

    (_USA / "reports" / "benchmark.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")

    print(f"  primary index:     ^GSPC (S&P 500)")
    print(f"  verdict:           {result['portfolio']['verdict']}")
    print(f"  trades benchmarked: 0 (day-1 baseline)")
    print(f"  elapsed:            {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
