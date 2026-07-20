"""AEGIS USA · Macro Indicators Ingest v1.0.

Free-source macro snapshot: rates, dollar, commodities, volatility.

Symbols (yfinance):
  ^TNX  10-Year Treasury yield
  ^TYX  30-Year Treasury yield
  ^FVX  5-Year Treasury yield
  ^IRX  13-Week T-Bill yield
  DX=F  Dollar Index (DXY) — futures
  GC=F  Gold futures
  CL=F  WTI Crude futures
  BZ=F  Brent Crude futures
  ^VIX  S&P volatility (equity)
  ^MOVE Merrill bond volatility

Output:
  usa/data/raw/us/macro.parquet         (per-symbol daily rows)
  usa/reports/macro_summary.json        (latest reads + short trend)

All values in USD ($) where applicable.
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

OUT_PARQUET = _USA / "data" / "raw" / "us" / "macro.parquet"
OUT_SUMMARY = _USA / "reports" / "macro_summary.json"

MACROS = {
    "^TNX":  "10Y Treasury yield",
    "^TYX":  "30Y Treasury yield",
    "^FVX":  "5Y Treasury yield",
    "^IRX":  "13W T-Bill yield",
    "UUP":   "US Dollar Index (Invesco DB proxy)",
    "GC=F":  "Gold futures",
    "CL=F":  "WTI Crude futures",
    "BZ=F":  "Brent Crude futures",
    "^VIX":  "S&P 500 volatility",
    "^MOVE": "Merrill bond volatility",
}

LOOKBACK_DAYS = 30


def main() -> int:
    print("=" * 70); print("  USA Macro Indicators Ingest v1.0"); print("=" * 70)
    try:
        import yfinance as yf
    except ImportError:
        print("  FATAL: yfinance not installed"); return 1

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    print(f"  indicators: {len(MACROS)}  · window: {LOOKBACK_DAYS}d")

    all_rows: list[dict] = []
    per_symbol: list[dict] = []
    for sym, label in sorted(MACROS.items()):
        try:
            df = yf.download(sym, period=f"{LOOKBACK_DAYS + 20}d", interval="1d",
                              progress=False, auto_adjust=False)
            if df is None or df.empty:
                per_symbol.append({"symbol": sym, "label": label, "error": "no data"})
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            df = df.tail(LOOKBACK_DAYS).reset_index()
            df["symbol"] = sym; df["label"] = label; df["ingested_utc"] = now_iso
            for _, r in df.iterrows():
                all_rows.append({
                    "symbol": sym, "label": label,
                    "date":   r["Date"].date().isoformat() if hasattr(r["Date"], "date") else str(r["Date"])[:10],
                    "close":  float(r["Close"]),
                    "ingested_utc": now_iso,
                })
            last = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else last
            week_ago = float(df["Close"].iloc[-6]) if len(df) >= 6 else last
            month_ago = float(df["Close"].iloc[0])
            per_symbol.append({
                "symbol":       sym,
                "label":        label,
                "last":         round(last, 4),
                "prev":         round(prev, 4),
                "chg_1d_pct":   round((last / prev - 1.0) * 100.0, 3) if prev else 0.0,
                "chg_1w_pct":   round((last / week_ago - 1.0) * 100.0, 3) if week_ago else 0.0,
                "chg_1m_pct":   round((last / month_ago - 1.0) * 100.0, 3) if month_ago else 0.0,
            })
        except Exception as e:
            per_symbol.append({"symbol": sym, "label": label,
                                "error": f"{type(e).__name__}: {e}"})

    # APPEND-only: fetch today's rows, concat with existing history, dedupe on (symbol, date).
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(all_rows)
    if OUT_PARQUET.exists():
        try:
            df_old = pd.read_parquet(OUT_PARQUET)
            df_full = pd.concat([df_old, df_new], ignore_index=True) \
                        .drop_duplicates(subset=["symbol", "date"], keep="last") \
                        .sort_values(["symbol", "date"]).reset_index(drop=True)
        except Exception:
            df_full = df_new
    else:
        df_full = df_new
    df_full.to_parquet(OUT_PARQUET, index=False)

    summary = {
        "engine":      "usa_macro",
        "version":     "v1.0",
        "run_utc":     now_iso,
        "asof":        now.date().isoformat(),
        "window_days": LOOKBACK_DAYS,
        "n_symbols":   len(MACROS),
        "n_with_data": sum(1 for x in per_symbol if "last" in x),
        "per_symbol":  sorted(per_symbol, key=lambda x: x["symbol"]),
        "parquet":     str(OUT_PARQUET.relative_to(_ROOT).as_posix()),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_PARQUET.relative_to(_ROOT)} · {len(all_rows)} rows")
    for s in [x for x in per_symbol if "last" in x][:5]:
        print(f"  {s['symbol']:<6} {s['label']:<28}  last={s['last']:>9.3f}  "
              f"1d={s['chg_1d_pct']:+.2f}%  1m={s['chg_1m_pct']:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
