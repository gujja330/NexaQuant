"""Daily runner · Economic Calendar ingest (Phase 2 prep · data only).

Usage:
    python scripts/ingest_economic_calendar.py --asof 2026-08-05
    python scripts/ingest_economic_calendar.py --query --days 7

Wires into scripts/aegis_daily_v2.py as an optional new step so calendar
history starts accumulating from today · Phase 2A (2026-09-09) will have
30+ days of data ready to consume.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date as _date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.context.economic_calendar import ingest as _ing  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=_date.today().isoformat())
    ap.add_argument("--query", action="store_true",
                       help="dump upcoming events instead of ingesting")
    ap.add_argument("--days", type=int, default=7,
                       help="lookahead window for --query")
    ap.add_argument("--region", choices=["USA", "INDIA", "EU", "JP", "UK", "CHINA", "GLOBAL"])
    args = ap.parse_args()

    if args.query:
        events = _ing.query_upcoming(_ROOT, args.asof, args.days,
                                              region=args.region)
        print(f"[economic_calendar] {len(events)} events in next {args.days} days"
              + (f" · region={args.region}" if args.region else ""))
        for e in events[:30]:
            print(f"  {e['event_date']} · {e['region']:<7} · "
                     f"[{e['expected_impact']:<6}] {e['event_name']} · "
                     f"→ {e['tickers_affected']}")
        return 0

    summary = _ing.ingest_daily(_ROOT, args.asof)
    print(f"[economic_calendar] appended {summary['total_appended']} entries "
          f"({summary['n_seeded_recurring']} seed · "
          f"{summary['n_earnings_upcoming']} earnings)")
    print(f"  output: {summary['output']}")
    print(f"  phase:  {summary['phase']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
