# data/calendar.py
"""
Economic-calendar builder for the event/volatility guard (strategy/event_guard.py) — no
paid keys. Produces data/raw/EVENTS.parquet (index 'time', column 'impact').

Two no-key paths:
  1. USER CSV   : if data/raw/calendar_input.csv exists (e.g. a ForexFactory CSV export
                  with columns date,time,impact,event), it is converted directly.
  2. RECURRING  : otherwise generates the predictable HIGH-impact USD releases over the
                  span of the price data — NFP (first Friday) and CPI (~13th) — so the
                  guard has real blackout windows even with zero external dependencies.
                  (FOMC dates aren't formulaic — add them via the CSV path when needed.)

The guard then blocks new entries within +/- window of these times.

Run: python data/calendar.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = RAW / "EVENTS.parquet"
CSV_IN = RAW / "calendar_input.csv"


def _data_span():
    """Date range covered by whatever price data we have."""
    files = list(RAW.glob("*_D1.parquet")) or list(RAW.glob("*_H1.parquet"))
    if not files:
        return None, None
    idx = pd.read_parquet(files[0]).index
    return idx.min().normalize(), idx.max().normalize()


def from_csv():
    df = pd.read_csv(CSV_IN)
    cols = {c.lower(): c for c in df.columns}
    dt = pd.to_datetime(df[cols.get("date", "date")].astype(str) + " " +
                        df.get(cols.get("time", "time"), pd.Series("12:00", index=df.index)).astype(str),
                        errors="coerce")
    ev = pd.DataFrame({"impact": df[cols.get("impact", "impact")].astype(str).str.lower()},
                      index=dt).dropna()
    ev.index.name = "time"
    return ev


def recurring_high_impact(start, end):
    """NFP (first Friday, 13:30 UTC) + CPI (~13th, 13:30 UTC) high-impact USD events."""
    rows = []
    for m in pd.date_range(start, end, freq="MS"):
        # NFP = first Friday of the month
        fridays = pd.date_range(m, m + pd.offsets.MonthEnd(0), freq="W-FRI")
        if len(fridays):
            rows.append((fridays[0] + pd.Timedelta(hours=13, minutes=30), "high", "NFP"))
        # CPI ~ 13th
        rows.append((m.replace(day=13) + pd.Timedelta(hours=13, minutes=30), "high", "CPI"))
    ev = pd.DataFrame(rows, columns=["time", "impact", "event"]).set_index("time").sort_index()
    return ev[(ev.index >= start) & (ev.index <= end)]


def build():
    if CSV_IN.exists():
        ev = from_csv()
        print(f"  built from {CSV_IN.name}: {len(ev)} events")
    else:
        start, end = _data_span()
        if start is None:
            sys.exit("no price data to bound the calendar; pull data first")
        ev = recurring_high_impact(start, end)
        print(f"  generated recurring NFP+CPI high-impact events: {len(ev)} "
              f"({start.date()} -> {end.date()})  [add FOMC via {CSV_IN.name}]")
    ev.to_parquet(OUT)
    print(f"  saved {OUT}")


if __name__ == "__main__":
    print("=== economic calendar ===")
    build()
