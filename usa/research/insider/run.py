"""AEGIS USA · Insider Transactions Ingest v1.0.

Per-ticker recent insider (Form 4) transactions, from yfinance.

Free source: yfinance's .insider_transactions returns recent SEC Form 4
filings. We snapshot a per-ticker net insider flow (buy dollars − sell dollars,
trailing 90 days) plus per-transaction ledger.

Output:
  usa/data/raw/us/insider_transactions.parquet   (per-transaction ledger)
  usa/reports/insider_summary.json                (per-ticker roll-up)

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

UNIVERSE_JSON = _USA / "reports" / "universe.json"
OUT_PARQUET   = _USA / "data" / "raw" / "us" / "insider_transactions.parquet"
OUT_SUMMARY   = _USA / "reports" / "insider_summary.json"

WINDOW_DAYS = 90


def _load_universe() -> list[str]:
    if not UNIVERSE_JSON.exists(): return []
    data = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
    return sorted({t["symbol"] for t in data.get("tickers", []) if t.get("symbol")})


def _to_float(x) -> float | None:
    if x is None or (isinstance(x, float) and pd.isna(x)): return None
    try: return float(x)
    except Exception: return None


def main() -> int:
    print("=" * 70); print("  USA Insider Transactions Ingest v1.0"); print("=" * 70)
    try:
        import yfinance as yf
    except ImportError:
        print("  FATAL: yfinance not installed"); return 1

    universe = _load_universe()
    if not universe:
        print("  FATAL: no universe found"); return 1
    print(f"  universe: {len(universe)} tickers · window: trailing {WINDOW_DAYS}d")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=WINDOW_DAYS)

    all_txns: list[dict] = []
    per_ticker: list[dict] = []
    for sym in universe:
        buy_val = 0.0; sell_val = 0.0; n_buy = 0; n_sell = 0
        try:
            t = yf.Ticker(sym)
            ix = t.insider_transactions
            if isinstance(ix, pd.DataFrame) and not ix.empty:
                cols = {c.lower(): c for c in ix.columns}
                date_col = cols.get("start date") or cols.get("date")
                if date_col is None or date_col not in ix.columns:
                    ix_df = ix
                else:
                    ix_df = ix.copy()
                    ix_df[date_col] = pd.to_datetime(ix_df[date_col], errors="coerce")
                    ix_df = ix_df[ix_df[date_col] >= cutoff]
                for _, r in ix_df.iterrows():
                    txn_type = str(r.get("Transaction") or r.get("Text") or "").lower()
                    shares = _to_float(r.get("Shares"))
                    value = _to_float(r.get("Value"))
                    if value is None and shares is not None:
                        # yfinance sometimes returns shares without value — skip valuation
                        pass
                    is_buy = ("buy" in txn_type) or ("purchase" in txn_type) or ("open market buy" in txn_type)
                    is_sell = ("sale" in txn_type) or ("sell" in txn_type)
                    if is_buy and value is not None:
                        buy_val += value; n_buy += 1
                    elif is_sell and value is not None:
                        sell_val += value; n_sell += 1
                    all_txns.append({
                        "ticker": sym,
                        "date":   str(r.get(date_col) or r.get("Date") or "")[:10],
                        "insider": str(r.get("Insider") or ""),
                        "position": str(r.get("Position") or ""),
                        "transaction": txn_type,
                        "shares": shares,
                        "value_usd": value,
                        "ingested_utc": now_iso,
                    })
        except Exception as e:
            per_ticker.append({"ticker": sym, "error": f"{type(e).__name__}: {e}",
                                "buy_value_usd": 0.0, "sell_value_usd": 0.0,
                                "net_value_usd": 0.0, "n_buy": 0, "n_sell": 0})
            continue

        per_ticker.append({
            "ticker": sym,
            "buy_value_usd":  round(buy_val, 2),
            "sell_value_usd": round(sell_val, 2),
            "net_value_usd":  round(buy_val - sell_val, 2),
            "n_buy":  n_buy,
            "n_sell": n_sell,
        })

    # APPEND-only: dedupe on (ticker, date, insider, transaction, shares) so the
    # same Form 4 event isn't double-counted across daily runs.
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(all_txns)
    if OUT_PARQUET.exists() and not df_new.empty:
        try:
            df_old = pd.read_parquet(OUT_PARQUET)
            df_full = pd.concat([df_old, df_new], ignore_index=True) \
                        .drop_duplicates(subset=["ticker", "date", "insider",
                                                    "transaction", "shares"],
                                            keep="last") \
                        .sort_values(["ticker", "date"]).reset_index(drop=True)
        except Exception:
            df_full = df_new
    else:
        df_full = df_new
    df_full.to_parquet(OUT_PARQUET, index=False)

    total_buy = sum(x["buy_value_usd"] for x in per_ticker)
    total_sell = sum(x["sell_value_usd"] for x in per_ticker)
    summary = {
        "engine":              "usa_insider",
        "version":             "v1.0",
        "run_utc":             now_iso,
        "asof":                now.date().isoformat(),
        "window_days":         WINDOW_DAYS,
        "n_tickers":           len(per_ticker),
        "n_transactions":      len(all_txns),
        "total_buy_value_usd": round(total_buy, 2),
        "total_sell_value_usd": round(total_sell, 2),
        "net_flow_usd":        round(total_buy - total_sell, 2),
        "per_ticker":          sorted(per_ticker, key=lambda x: x["ticker"]),
        "parquet":             str(OUT_PARQUET.relative_to(_ROOT).as_posix()),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_PARQUET.relative_to(_ROOT)} · {len(all_txns)} transactions")
    print(f"  net insider flow (90d): ${summary['net_flow_usd']:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
