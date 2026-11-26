# india/corporate_actions.py
"""
CORPORATE ACTIONS INGEST (Sprint 1B) — dividends + splits per NSE ticker, from yfinance.

Free source: yfinance's .actions accessor returns the full dividend + split history
for each symbol. We snapshot the RECENT history (last N days) daily/weekly so downstream
engines have a fresh "what happened lately" ledger without paying for a corporate-actions
feed.

Output: data/raw/india/corporate_actions.parquet
Columns: ticker, action_date, dividend, split_ratio, ingested_utc

Run:  python india/corporate_actions.py
"""
from __future__ import annotations

import io
import sys
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.ingest.ticker_health import yahoo_symbol
from india.data_nse import UNIVERSE  # tenant-generic — read from repo's canonical universe

OUT = ROOT / "data" / "raw" / "india" / "corporate_actions.parquet"

# Only keep the trailing window — corporate actions are point-in-time events, not tick data
KEEP_DAYS = 365


def pull(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf
    rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=KEEP_DAYS)

    for sym in tickers:
        if sym.startswith("^"):
            continue
        try:
            t = yf.Ticker(yahoo_symbol(ROOT, "india", sym))
            acts = t.history(period="1y", auto_adjust=False, actions=True)
            if acts is None or acts.empty:
                continue
            # keep last KEEP_DAYS window
            idx = pd.to_datetime(acts.index).tz_localize(None)
            mask = idx >= cutoff
            empty = pd.Series(0.0, index=acts.index)
            dividends = pd.to_numeric(acts.get("Dividends", empty), errors="coerce").fillna(0.0)
            splits = pd.to_numeric(acts.get("Stock Splits", empty), errors="coerce").fillna(0.0)
            for dt, dv, sp in zip(idx[mask], dividends[mask], splits[mask]):
                if (dv is None or float(dv) == 0.0) and (sp is None or float(sp) == 0.0):
                    continue
                rows.append({
                    "ticker": sym,
                    "action_date": dt.date().isoformat(),
                    "dividend": float(dv) if dv else 0.0,
                    "split_ratio": float(sp) if sp else 0.0,
                    "ingested_utc": now,
                })
        except Exception as e:
            print(f"    | WARN {sym}: {type(e).__name__}: {e}")
    return pd.DataFrame(rows, columns=["ticker", "action_date", "dividend", "split_ratio", "ingested_utc"])


def main() -> int:
    tickers = [s for s in UNIVERSE if not s.startswith("^")]
    print(f"corporate_actions · pulling actions for {len(tickers)} NSE tickers "
          f"(trailing {KEEP_DAYS} days)")
    df = pull(tickers)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        old = pd.read_parquet(OUT)
        if df.empty:
            print(f"  no new actions returned; retained {len(old)} saved rows")
            return 0
        df = pd.concat([old, df], ignore_index=True)
    df = df.drop_duplicates(subset=["ticker", "action_date"], keep="first") \
           .sort_values(["ticker", "action_date"]).reset_index(drop=True)
    temporary = OUT.with_suffix(".tmp")
    try:
        df.to_parquet(temporary, index=False)
        temporary.replace(OUT)
    finally:
        temporary.unlink(missing_ok=True)
    n_div = int((df.get("dividend", pd.Series(dtype=float)) > 0).sum()) if not df.empty else 0
    n_split = int((df.get("split_ratio", pd.Series(dtype=float)) > 0).sum()) if not df.empty else 0
    print(f"  wrote {OUT.relative_to(ROOT)} · {len(df)} rows · {n_div} dividends · {n_split} splits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
