"""AEGIS USA · Price Context v1.0.

Per-ticker CMP + previous close + day change + 52W high/low +
distances. Reads from usa/data/raw/us/*.parquet. Emits
usa/reports/price_context.json.

USD everywhere.
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]
RAW_DIR = _USA / "data" / "raw" / "us"


def build_for(ticker: str) -> dict:
    p = RAW_DIR / f"{ticker}_D1.parquet"
    if not p.exists():
        return {"ticker": ticker, "available": False, "note": "no parquet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:
        return {"ticker": ticker, "available": False, "note": str(e)[:60]}
    if df.empty or "close" not in df.columns or len(df) < 2:
        return {"ticker": ticker, "available": False, "note": "insufficient rows"}

    close = df["close"].astype(float).dropna().sort_index()
    cmp_val = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    day_change = (cmp_val - prev) / prev if prev else 0.0
    tail = close.tail(252)
    hi = float(tail.max()); lo = float(tail.min())
    return {
        "ticker": ticker, "available": True,
        "cmp":               round(cmp_val, 2),
        "previous_close":    round(prev, 2),
        "day_change_pct":    round(day_change, 5),
        "high_52w":          round(hi, 2),
        "low_52w":           round(lo, 2),
        "distance_from_52w_high": round((cmp_val - hi) / hi, 5) if hi > 0 else 0,
        "distance_from_52w_low":  round((cmp_val - lo) / lo, 5) if lo > 0 else 0,
        "latest_date":       str(close.index[-1].date()),
    }


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Price Context v1.0")
    print("=" * 70)

    universe = json.loads((_USA / "reports" / "universe.json").read_text(encoding="utf-8"))
    tickers = sorted(str(t.get("symbol")) for t in (universe.get("tickers") or []))

    result: dict = {}
    for t in tickers:
        result[t] = build_for(t)
    n_avail = sum(1 for r in result.values() if r.get("available"))

    out = {
        "engine":       "usa_price_context",
        "version":      "v1.0",
        "market":       "USA",
        "currency":     "USD",
        "run_utc":      datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "n_tickers":    len(result),
        "n_available":  n_avail,
        "tickers":      result,
    }
    (_USA / "reports" / "price_context.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")

    print(f"  tickers:      {len(result)}")
    print(f"  with prices:  {n_avail}")
    print(f"  elapsed:      {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
