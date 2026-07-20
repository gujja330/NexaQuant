"""AEGIS USA · Corporate Actions Ingest v1.0.

Per-ticker dividends + splits, from yfinance's .actions accessor.

Free source: yfinance returns full dividend + split history per ticker.
We snapshot the trailing window daily so downstream engines have a fresh
"what happened lately" ledger.

Output:
  usa/data/raw/us/corporate_actions.parquet     (all events, trailing 365d)
  usa/reports/corporate_actions_summary.json    (recent events + counts)

All values in USD ($).
"""
from __future__ import annotations

import io
import json
import sys
import warnings
from datetime import datetime, timezone
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
OUT_PARQUET   = _USA / "data" / "raw" / "us" / "corporate_actions.parquet"
OUT_SUMMARY   = _USA / "reports" / "corporate_actions_summary.json"

KEEP_DAYS = 365


def _load_universe() -> list[str]:
    if not UNIVERSE_JSON.exists(): return []
    data = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
    return sorted({t["symbol"] for t in data.get("tickers", []) if t.get("symbol")})


def main() -> int:
    print("=" * 70); print("  USA Corporate Actions Ingest v1.0"); print("=" * 70)
    try:
        import yfinance as yf
    except ImportError:
        print("  FATAL: yfinance not installed"); return 1

    universe = _load_universe()
    if not universe:
        print("  FATAL: no universe found"); return 1
    print(f"  universe: {len(universe)} tickers  · trailing {KEEP_DAYS}d")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=KEEP_DAYS)

    rows: list[dict] = []
    per_ticker: list[dict] = []
    for sym in universe:
        n_div = 0; n_split = 0
        try:
            t = yf.Ticker(sym)
            acts = t.actions
            if acts is None or acts.empty:
                per_ticker.append({"ticker": sym, "n_dividends": 0, "n_splits": 0})
                continue
            idx = pd.to_datetime(acts.index).tz_localize(None)
            mask = idx >= cutoff
            for dt, dv, sp in zip(idx[mask], acts["Dividends"][mask], acts["Stock Splits"][mask]):
                dv_f = float(dv) if dv else 0.0
                sp_f = float(sp) if sp else 0.0
                if dv_f == 0.0 and sp_f == 0.0:
                    continue
                rows.append({
                    "ticker":       sym,
                    "action_date":  dt.date().isoformat(),
                    "dividend_usd": dv_f,
                    "split_ratio":  sp_f,
                    "ingested_utc": now_iso,
                })
                if dv_f > 0: n_div += 1
                if sp_f > 0: n_split += 1
        except Exception as e:
            per_ticker.append({"ticker": sym, "error": f"{type(e).__name__}: {e}",
                                "n_dividends": 0, "n_splits": 0})
            continue
        per_ticker.append({"ticker": sym, "n_dividends": n_div, "n_splits": n_split})

    # APPEND-only: merge today's events with existing history, dedupe on (ticker, action_date).
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(rows) if rows else pd.DataFrame()
    if OUT_PARQUET.exists() and not df_new.empty:
        try:
            df_old = pd.read_parquet(OUT_PARQUET)
            df = pd.concat([df_old, df_new], ignore_index=True) \
                    .drop_duplicates(subset=["ticker", "action_date"], keep="last") \
                    .sort_values(["ticker", "action_date"]).reset_index(drop=True)
        except Exception:
            df = df_new.drop_duplicates(subset=["ticker", "action_date"], keep="last") \
                        .sort_values(["ticker", "action_date"]).reset_index(drop=True)
    else:
        df = df_new
    df.to_parquet(OUT_PARQUET, index=False)

    # Recent events (last 30 days)
    recent_cutoff = (datetime.now(timezone.utc).date().toordinal() - 30)
    recent = []
    for r in rows:
        try:
            if datetime.fromisoformat(r["action_date"]).date().toordinal() >= recent_cutoff:
                recent.append(r)
        except Exception:
            continue

    summary = {
        "engine":         "usa_corporate_actions",
        "version":        "v1.0",
        "run_utc":        now_iso,
        "asof":           now.date().isoformat(),
        "window_days":    KEEP_DAYS,
        "n_tickers":      len(universe),
        "n_events":       int(len(df)),
        "n_dividends":    int((df["dividend_usd"] > 0).sum()) if not df.empty else 0,
        "n_splits":       int((df["split_ratio"] > 0).sum()) if not df.empty else 0,
        "recent_30d":     recent[-30:],   # tail
        "per_ticker":     sorted(per_ticker, key=lambda x: x["ticker"]),
        "parquet":        str(OUT_PARQUET.relative_to(_ROOT).as_posix()),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_PARQUET.relative_to(_ROOT)} · {len(df)} events")
    print(f"  dividends: {summary['n_dividends']}  · splits: {summary['n_splits']}  · recent (30d): {len(recent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
