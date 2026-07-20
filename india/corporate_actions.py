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
            t = yf.Ticker(sym)
            acts = t.actions  # DataFrame indexed by date, columns=['Dividends','Stock Splits']
            if acts is None or acts.empty:
                continue
            # keep last KEEP_DAYS window
            idx = pd.to_datetime(acts.index).tz_localize(None)
            mask = idx >= cutoff
            for dt, dv, sp in zip(idx[mask], acts["Dividends"][mask], acts["Stock Splits"][mask]):
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
    return pd.DataFrame(rows)


def main() -> int:
    tickers = [s for s in UNIVERSE if not s.startswith("^")]
    print(f"corporate_actions · pulling actions for {len(tickers)} NSE tickers "
          f"(trailing {KEEP_DAYS} days)")
    df = pull(tickers)
    if df.empty:
        print("  no actions in window — writing empty ledger")
    else:
        # dedupe on (ticker, action_date) — a repeat pull is idempotent
        df = df.drop_duplicates(subset=["ticker", "action_date"], keep="last") \
               .sort_values(["ticker", "action_date"]).reset_index(drop=True)
    # APPEND-only: merge with existing corpus, dedupe on (ticker, action_date).
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists() and not df.empty:
        try:
            df_old = pd.read_parquet(OUT)
            df = pd.concat([df_old, df], ignore_index=True) \
                    .drop_duplicates(subset=["ticker", "action_date"], keep="last") \
                    .sort_values(["ticker", "action_date"]).reset_index(drop=True)
        except Exception:
            pass
    df.to_parquet(OUT, index=False)
    n_div = int((df.get("dividend", pd.Series(dtype=float)) > 0).sum()) if not df.empty else 0
    n_split = int((df.get("split_ratio", pd.Series(dtype=float)) > 0).sum()) if not df.empty else 0
    print(f"  wrote {OUT.relative_to(ROOT)} · {len(df)} rows · {n_div} dividends · {n_split} splits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
