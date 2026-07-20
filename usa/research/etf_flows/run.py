"""AEGIS USA · ETF Flows Proxy Ingest v1.0.

Sector-level flow proxy from ETF price + volume × price (dollar volume).
True fund-flow (net creations/redemptions) requires paid feeds; this
approximates sector rotation using publicly-priced ETFs.

Free source: yfinance for major sector ETFs (SPDR sector suite + broad
market + international).

Output:
  usa/data/raw/us/etf_flows.parquet          (per-ETF daily rows)
  usa/reports/etf_flows_summary.json          (rotation heat map)

All values in USD ($).
"""
from __future__ import annotations

import io
import json
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

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]

OUT_PARQUET = _USA / "data" / "raw" / "us" / "etf_flows.parquet"
OUT_SUMMARY = _USA / "reports" / "etf_flows_summary.json"

# Curated ETF set — broad market + sectors + defensives + international
ETFS = {
    # Broad market
    "SPY":  "S&P 500",
    "QQQ":  "Nasdaq 100",
    "IWM":  "Russell 2000 (small cap)",
    "DIA":  "Dow Jones Industrial Average",
    "VTI":  "Total US Market",
    # SPDR sectors
    "XLK":  "Technology",
    "XLF":  "Financials",
    "XLV":  "Healthcare",
    "XLE":  "Energy",
    "XLI":  "Industrials",
    "XLY":  "Consumer Discretionary",
    "XLP":  "Consumer Staples",
    "XLU":  "Utilities",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLC":  "Communication Services",
    # Defensives + international
    "GLD":  "Gold",
    "TLT":  "20+Y Treasuries",
    "EEM":  "Emerging Markets",
    "EFA":  "EAFE Developed ex-US",
}

LOOKBACK_DAYS = 30


def main() -> int:
    print("=" * 70); print("  USA ETF Flows Proxy Ingest v1.0"); print("=" * 70)
    try:
        import yfinance as yf
    except ImportError:
        print("  FATAL: yfinance not installed"); return 1

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    print(f"  ETFs: {len(ETFS)}  · window: {LOOKBACK_DAYS} trading days")

    all_rows: list[dict] = []
    per_etf: list[dict] = []
    for etf, label in sorted(ETFS.items()):
        try:
            df = yf.download(etf, period=f"{LOOKBACK_DAYS + 20}d", interval="1d",
                              progress=False, auto_adjust=False)
            if df is None or df.empty: continue
            # Normalise flat vs multi-index columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            df = df.tail(LOOKBACK_DAYS).reset_index()
            df["ticker"] = etf
            df["label"]  = label
            df["dollar_volume"] = df["Close"] * df["Volume"]
            df["ingested_utc"] = now_iso
            # Persist per-day rows
            for _, r in df.iterrows():
                all_rows.append({
                    "ticker": etf,
                    "label":  label,
                    "date":   r["Date"].date().isoformat() if hasattr(r["Date"], "date") else str(r["Date"])[:10],
                    "close":  float(r["Close"]),
                    "volume": float(r["Volume"]),
                    "dollar_volume": float(r["dollar_volume"]),
                    "ingested_utc": now_iso,
                })
            # Roll up per ETF
            first_close = float(df["Close"].iloc[0])
            last_close  = float(df["Close"].iloc[-1])
            ret_pct     = (last_close / first_close - 1.0) * 100.0 if first_close else 0.0
            avg_dv      = float(df["dollar_volume"].mean())
            per_etf.append({
                "ticker":       etf,
                "label":        label,
                "period_days":  int(len(df)),
                "return_pct":   round(ret_pct, 2),
                "avg_dollar_volume_usd": round(avg_dv, 2),
                "last_close":   round(last_close, 2),
            })
        except Exception as e:
            per_etf.append({"ticker": etf, "label": label,
                             "error": f"{type(e).__name__}: {e}"})

    # APPEND-only: concat with existing history, dedupe on (ticker, date).
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(all_rows)
    if OUT_PARQUET.exists():
        try:
            df_old = pd.read_parquet(OUT_PARQUET)
            df_full = pd.concat([df_old, df_new], ignore_index=True) \
                        .drop_duplicates(subset=["ticker", "date"], keep="last") \
                        .sort_values(["ticker", "date"]).reset_index(drop=True)
        except Exception:
            df_full = df_new
    else:
        df_full = df_new
    df_full.to_parquet(OUT_PARQUET, index=False)

    # Ranking: strongest sector rotations (top + bottom by return_pct)
    ranked = [e for e in per_etf if "return_pct" in e]
    ranked.sort(key=lambda x: x["return_pct"], reverse=True)
    summary = {
        "engine":       "usa_etf_flows",
        "version":      "v1.0",
        "run_utc":      now_iso,
        "asof":         now.date().isoformat(),
        "window_days":  LOOKBACK_DAYS,
        "n_etfs":       len(ETFS),
        "n_with_data":  len(ranked),
        "top_3_gainers": ranked[:3],
        "top_3_losers":  ranked[-3:][::-1] if len(ranked) >= 3 else ranked[::-1],
        "per_etf":      sorted(per_etf, key=lambda x: x["ticker"]),
        "parquet":      str(OUT_PARQUET.relative_to(_ROOT).as_posix()),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_PARQUET.relative_to(_ROOT)} · {len(all_rows)} rows")
    if ranked:
        print(f"  top gainer: {ranked[0]['ticker']} ({ranked[0]['label']}) {ranked[0]['return_pct']:+.2f}%")
        print(f"  top loser:  {ranked[-1]['ticker']} ({ranked[-1]['label']}) {ranked[-1]['return_pct']:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
