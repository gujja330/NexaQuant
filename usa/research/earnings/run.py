"""AEGIS USA · Earnings Calendar Ingest v1.0.

Per-ticker next-earnings-date + last-quarter EPS surprise, from yfinance.

Free source: yfinance's .calendar accessor (upcoming date) + .earnings_dates
(historical actuals vs estimates). This is a LIVE snapshot — the calendar
walks forward, so a daily rebuild is idempotent.

Output:
  usa/data/raw/us/earnings.parquet         (per-ticker calendar snapshot)
  usa/reports/earnings_summary.json         (next-N-days heat map)

All values in USD ($).
"""
from __future__ import annotations

import io
import json
import sys
import warnings
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

warnings.simplefilter("ignore")

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]

UNIVERSE_JSON = _USA / "reports" / "universe.json"
OUT_PARQUET   = _USA / "data" / "raw" / "us" / "earnings.parquet"
OUT_SUMMARY   = _USA / "reports" / "earnings_summary.json"


def _parse_date(d) -> str | None:
    if d is None: return None
    if isinstance(d, (list, tuple)):
        d = d[0] if d else None
    if d is None: return None
    try:
        if hasattr(d, "date"): return d.date().isoformat()
        s = str(d)
        return datetime.fromisoformat(s.split()[0]).date().isoformat()
    except Exception:
        try:
            return str(d)[:10]
        except Exception:
            return None


def _load_universe() -> list[str]:
    if not UNIVERSE_JSON.exists(): return []
    data = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
    return sorted({t["symbol"] for t in data.get("tickers", []) if t.get("symbol")})


def main() -> int:
    print("=" * 70); print("  USA Earnings Calendar Ingest v1.0"); print("=" * 70)
    try:
        import yfinance as yf
    except ImportError:
        print("  FATAL: yfinance not installed"); return 1

    universe = _load_universe()
    if not universe:
        print("  FATAL: no universe found"); return 1
    print(f"  universe: {len(universe)} tickers")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    today = now.date()

    rows: list[dict] = []
    for sym in universe:
        row = {"ticker": sym, "ingested_utc": now_iso, "asof": today.isoformat()}
        try:
            t = yf.Ticker(sym)
            # Upcoming date via .calendar
            cal = t.calendar
            nxt = None
            if isinstance(cal, dict):
                nxt = cal.get("Earnings Date")
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                nxt = cal.iloc[0].get("Earnings Date") if "Earnings Date" in cal.columns else None
            row["next_earnings_date"] = _parse_date(nxt)

            # Last reported surprise via .earnings_dates
            ed = t.earnings_dates
            if isinstance(ed, pd.DataFrame) and not ed.empty:
                ed = ed.dropna(subset=["Reported EPS"]) if "Reported EPS" in ed.columns else ed
                if not ed.empty:
                    last = ed.iloc[0]
                    row["last_report_date"] = _parse_date(ed.index[0]) if len(ed.index) else None
                    row["last_reported_eps"] = float(last["Reported EPS"]) \
                        if "Reported EPS" in ed.columns and pd.notna(last.get("Reported EPS")) else None
                    row["last_eps_estimate"] = float(last["EPS Estimate"]) \
                        if "EPS Estimate" in ed.columns and pd.notna(last.get("EPS Estimate")) else None
                    row["last_surprise_pct"] = float(last["Surprise(%)"]) \
                        if "Surprise(%)" in ed.columns and pd.notna(last.get("Surprise(%)")) else None
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        rows.append(row)

    # APPEND-only: keep a per-day snapshot ledger; dedupe on (ticker, asof).
    # This preserves the historical view "what did the calendar say on day X"
    # — needed for walk-forward replay of PEAD strategies.
    df_new = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PARQUET.exists():
        try:
            df_old = pd.read_parquet(OUT_PARQUET)
            df = pd.concat([df_old, df_new], ignore_index=True) \
                    .drop_duplicates(subset=["ticker", "asof"], keep="last") \
                    .sort_values(["asof", "ticker"]).reset_index(drop=True)
        except Exception:
            df = df_new
    else:
        df = df_new
    df.to_parquet(OUT_PARQUET, index=False)

    # Compact summary: next-30-days heat map
    horizon = today + timedelta(days=30)
    upcoming = []
    for _, r in df.iterrows():
        d = r.get("next_earnings_date")
        if not d or not isinstance(d, str): continue
        try:
            edate = datetime.fromisoformat(d).date()
        except Exception:
            continue
        if today <= edate <= horizon:
            upcoming.append({"ticker": r["ticker"], "date": d,
                              "days_away": (edate - today).days})
    upcoming.sort(key=lambda x: x["days_away"])

    summary = {
        "engine":            "usa_earnings",
        "version":           "v1.0",
        "run_utc":           now_iso,
        "asof":              today.isoformat(),
        "n_tickers":         int(len(df)),
        "n_with_calendar":   int(df["next_earnings_date"].notna().sum())
                              if "next_earnings_date" in df.columns else 0,
        "n_upcoming_30d":    len(upcoming),
        "upcoming":          upcoming[:20],
        "parquet":           str(OUT_PARQUET.relative_to(_ROOT).as_posix()),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_PARQUET.relative_to(_ROOT)} · {len(df)} rows")
    print(f"  upcoming (next 30d): {summary['n_upcoming_30d']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
