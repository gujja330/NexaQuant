"""Sprint F · Government-source daily ingest (FRED + EDGAR + NSE bhavcopy).

Zero paid vendors. All sources are public.
Usage:
    python scripts/ingest_government_sources.py
    python scripts/ingest_government_sources.py --only fred
    python scripts/ingest_government_sources.py --only edgar
    python scripts/ingest_government_sources.py --only nse
"""
from __future__ import annotations
import argparse, io, sys
from datetime import date as _date
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=_date.today().isoformat())
    ap.add_argument("--only", choices=["fred", "edgar", "nse"], help="run only one source")
    args = ap.parse_args()

    if args.only in (None, "fred"):
        from backend.ingest.fred import ingest as _fred
        r = _fred.ingest_daily(_ROOT, args.asof)
        print(f"[fred] {r['n_available']}/{r['n_series']} series fetched")
        for sid, s in list(r.get("series", {}).items())[:6]:
            if s.get("available"):
                print(f"  {sid:<12} {s['label']:<28} "
                      f"= {s['latest_value']:>10} {s['unit']}  "
                      f"30d {s.get('change_30d_pct')}% · pctile {s.get('percentile_2y')}%")

    if args.only in (None, "edgar"):
        from backend.ingest.edgar import ingest as _ed
        r = _ed.ingest_daily(_ROOT, args.asof)
        print(f"[edgar] {r['n_ok']}/{r['universe_size']} tickers · "
              f"{r['n_form4_total']} Form 4 filings last 90d")
        for t, v in list(r.get("per_ticker", {}).items())[:5]:
            if v.get("available"):
                print(f"  {t:<8} {v.get('n_form4_last_90d')} filings")

    if args.only in (None, "nse"):
        from backend.ingest.nse_bhavcopy import ingest as _nse
        r = _nse.ingest_daily(_ROOT, args.asof)
        if r.get("available"):
            print(f"[nse_bhavcopy] {r['n_rows']} rows fetched for {r['asof']}")
            print(f"  turnover: {r.get('total_turnover_lacs')} lacs")
        else:
            print(f"[nse_bhavcopy] not available · {r.get('reason')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
