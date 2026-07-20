"""AEGIS USA · Validation Engine v1.0.

USA equivalent of India's validation_v2. Emits:

  usa/reports/validation_latest.json  — paper-portfolio + drift stubs
  usa/reports/stock_validation.json   — per-ticker rollup

Day-1 baseline: everything reports "insufficient live evidence" —
same as India did on its baseline day. Populates as USA archive
matures.

All prices in USD ($).
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
    print("  AEGIS USA · Validation Engine v1.0")
    print("=" * 70)

    recs_p = _USA / "reports" / "recommendations.json"
    if not recs_p.exists():
        print("FATAL: recommendations.json missing.")
        return 1
    recs = json.loads(recs_p.read_text(encoding="utf-8"))

    # Paper harness — stub for day-1; will grow as archive accumulates
    paper_state = {
        "n_open_positions":  0,
        "n_closed_trades":   0,
        "avg_return_pct":    None,
        "verdict":           "insufficient_evidence",
        "note":              "Day 1 baseline — populates as archive matures.",
    }

    # Drift proxy
    drift = {
        "flag":              "insufficient_evidence",
        "first_half_sharpe": None,
        "second_half_sharpe": None,
        "note":              "Requires ≥ 30 closed paper trades.",
    }

    out = {
        "engine":            "usa_validation",
        "version":           "v1.0",
        "market":            "USA",
        "currency":          "USD",
        "run_utc":           datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "n_open_positions":  paper_state["n_open_positions"],
        "n_closed_trades":   paper_state["n_closed_trades"],
        "paper_portfolio":   paper_state,
        "metric_drift":      drift,
    }
    (_USA / "reports" / "validation_latest.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")

    # Per-ticker validation — day-1 all 0 trades
    tickers_out = {}
    for r in (recs.get("recommendations") or []):
        t = str(r.get("ticker"))
        tickers_out[t] = {
            "ticker":              t,
            "n_trades":            0,
            "n_winners":           0,
            "n_losers":            0,
            "win_rate":            None,
            "avg_return_pct":      None,
            "reliability_stars":   0,
            "trades":              [],
            "note":                "Day 1 baseline — grows with archive.",
        }
    sv = {
        "engine":            "usa_stock_validation",
        "version":           "v1.0",
        "run_utc":           datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "n_tickers":         len(tickers_out),
        "n_with_history":    0,
        "n_without_history": len(tickers_out),
        "tickers":           tickers_out,
    }
    (_USA / "reports" / "stock_validation.json").write_text(
        json.dumps(sv, indent=2, default=str), encoding="utf-8")

    print(f"  paper positions:    {paper_state['n_open_positions']}")
    print(f"  closed trades:      {paper_state['n_closed_trades']}")
    print(f"  drift flag:         {drift['flag']}")
    print(f"  tickers validated:  {len(tickers_out)} (all 0-trade baseline)")
    print(f"  elapsed:            {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
