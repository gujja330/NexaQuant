"""AEGIS USA · SEC 13F Institutional Holdings Ingest v1.0.

Institutional ownership snapshots per ticker, from yfinance's
.institutional_holders + .major_holders accessors. Not a true 13F
parse (which requires SEC EDGAR full-text ingest, deferred to a
later sprint) — but sufficient to answer "who holds this, at what
weight, and did it change materially quarter-over-quarter."

Output:
  usa/data/raw/us/institutional_holders.parquet  (top holders per ticker)
  usa/reports/sec_13f_summary.json                (per-ticker roll-up)

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
OUT_PARQUET   = _USA / "data" / "raw" / "us" / "institutional_holders.parquet"
OUT_SUMMARY   = _USA / "reports" / "sec_13f_summary.json"


def _load_universe() -> list[str]:
    if not UNIVERSE_JSON.exists(): return []
    data = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
    return sorted({t["symbol"] for t in data.get("tickers", []) if t.get("symbol")})


def _to_float(x) -> float | None:
    if x is None or (isinstance(x, float) and pd.isna(x)): return None
    try: return float(x)
    except Exception: return None


def main() -> int:
    print("=" * 70); print("  USA SEC 13F Institutional Holdings Ingest v1.0"); print("=" * 70)
    print("  NOTE: uses yfinance institutional holders view (not full EDGAR 13F parse).")
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

    rows: list[dict] = []
    per_ticker: list[dict] = []
    for sym in universe:
        entry = {"ticker": sym}
        try:
            t = yf.Ticker(sym)
            # Institutional top holders
            ih = t.institutional_holders
            if isinstance(ih, pd.DataFrame) and not ih.empty:
                for _, r in ih.iterrows():
                    rows.append({
                        "ticker":         sym,
                        "holder":         str(r.get("Holder", "")),
                        "shares":         _to_float(r.get("Shares")),
                        "pct_out":        _to_float(r.get("pctHeld") if "pctHeld" in ih.columns
                                                    else r.get("% Out")),
                        "value_usd":      _to_float(r.get("Value")),
                        "date_reported":  str(r.get("Date Reported", ""))[:10],
                        "ingested_utc":   now_iso,
                    })
                entry["n_top_holders"] = int(len(ih))
                entry["top_holder"]    = str(ih.iloc[0].get("Holder", ""))
                entry["top_pct"]       = _to_float(ih.iloc[0].get("pctHeld") if "pctHeld" in ih.columns
                                                    else ih.iloc[0].get("% Out"))
            else:
                entry["n_top_holders"] = 0

            # Major holders — pct-institutional summary
            mh = t.major_holders
            if isinstance(mh, pd.DataFrame) and not mh.empty:
                # Format varies — try to pull the "% Held by Institutions" line
                m = mh.astype(str)
                for _, r in m.iterrows():
                    row_vals = list(r.values)
                    if any("institutions" in str(v).lower() for v in row_vals):
                        # First column is usually the percentage string
                        pct_str = str(row_vals[0]).replace("%", "").strip()
                        try:
                            entry["institutional_pct"] = float(pct_str)
                        except Exception:
                            pass
                        break
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        per_ticker.append(entry)

    df = pd.DataFrame(rows)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)

    inst_pcts = [x["institutional_pct"] for x in per_ticker
                 if isinstance(x.get("institutional_pct"), (int, float))]
    summary = {
        "engine":                 "usa_sec_13f",
        "version":                "v1.0",
        "run_utc":                now_iso,
        "asof":                   now.date().isoformat(),
        "n_tickers":              len(universe),
        "n_with_holders":         sum(1 for x in per_ticker if x.get("n_top_holders", 0) > 0),
        "n_total_holder_rows":    int(len(df)),
        "avg_institutional_pct":  round(sum(inst_pcts) / len(inst_pcts), 2) if inst_pcts else 0.0,
        "per_ticker":             sorted(per_ticker, key=lambda x: x["ticker"]),
        "parquet":                str(OUT_PARQUET.relative_to(_ROOT).as_posix()),
        "notes":                  "yfinance institutional_holders view (top 10 per ticker). "
                                   "Full EDGAR 13F parse (all filers) deferred to a later sprint.",
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  wrote {OUT_PARQUET.relative_to(_ROOT)} · {len(df)} holder rows")
    print(f"  avg institutional ownership: {summary['avg_institutional_pct']:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
