# india/refresh_data.py
"""
DAILY DATA REFRESH — append the latest market data so the pipeline always runs on the newest date.

Pulls recent daily bars from Yahoo Finance for every symbol that already has a parquet in
data/raw/india/ (stocks as SYMBOL.NS, plus the index/vix: NSEI->^NSEI, INDIAVIX->^INDIAVIX,
NSEBANK->^NSEBANK, SP500->^GSPC), maps Yahoo's OHLCV onto the existing schema
(open/high/low/close/tick_volume/spread, index name 'time'), and APPENDS only the new dates
(dedup, sorted). Existing history is never overwritten — only extended.

Run:  python india/refresh_data.py            # refresh everything, then run the engine
      python india/refresh_data.py --limit 5  # quick test on a few symbols
"""
import sys, glob, warnings
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
RAW = ROOT / "data" / "raw" / "india"
NON_STOCK = {"NSEI": "^NSEI", "NSEBANK": "^NSEBANK", "INDIAVIX": "^INDIAVIX", "SP500": "^GSPC"}
SKIP = {"fundamentals"}
CHUNK = 40


def ticker_for(sym):
    return NON_STOCK.get(sym, f"{sym}.NS")


def _to_schema(df):
    """Yahoo OHLCV -> the existing parquet schema (lowercase + tick_volume + spread, naive date index)."""
    df = df.rename(columns=str.lower)
    idx = pd.to_datetime(df.index)
    try:
        idx = idx.tz_localize(None)
    except Exception:
        idx = idx.tz_convert(None) if getattr(idx, "tz", None) is not None else idx
    out = pd.DataFrame(index=idx.normalize())
    out.index.name = "time"
    for c in ("open", "high", "low", "close"):
        out[c] = pd.to_numeric(df.get(c), errors="coerce")
    out["tick_volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0).astype("int64")
    out["spread"] = 0.0
    return out.dropna(subset=["close"])


def refresh(limit=None):
    import yfinance as yf
    files = sorted(glob.glob(str(RAW / "*_D1.parquet")))
    syms = [Path(f).stem.replace("_D1", "") for f in files]
    syms = [s for s in syms if s not in SKIP]
    if limit:
        syms = syms[:limit]
    tmap = {ticker_for(s): s for s in syms}
    tickers = list(tmap)
    updated, total_rows, failed, newest = 0, 0, [], None

    for i in range(0, len(tickers), CHUNK):
        batch = tickers[i:i + CHUNK]
        try:
            data = yf.download(batch, period="1mo", group_by="ticker", progress=False,
                               auto_adjust=False, threads=True)   # 1mo covers gaps from missed runs
        except Exception:
            failed += batch; continue
        for tkr in batch:
            sym = tmap[tkr]
            path = RAW / f"{sym}_D1.parquet"
            try:
                sub = data[tkr] if isinstance(data.columns, pd.MultiIndex) else data
                fresh = _to_schema(sub.dropna(how="all"))
                if fresh.empty:
                    continue
                existing = pd.read_parquet(path)
                add = fresh[fresh.index > existing.index[-1]]
                if add.empty:
                    continue
                merged = pd.concat([existing, add[existing.columns.intersection(add.columns)]])
                merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                merged.to_parquet(path)
                updated += 1; total_rows += len(add)
                newest = max(newest, merged.index[-1]) if newest else merged.index[-1]
            except Exception:
                failed.append(tkr)
    return dict(updated=updated, rows=total_rows, failed=failed, newest=newest, n=len(tickers))


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    print("=" * 60)
    print("  AEGIS DATA REFRESH — appending latest market data")
    print("=" * 60)
    r = refresh(limit=limit)
    print(f"  symbols checked : {r['n']}")
    print(f"  updated         : {r['updated']}  (+{r['rows']} new rows)")
    print(f"  newest date now : {r['newest'].date() if r['newest'] is not None else 'unchanged'}")
    if r["failed"]:
        print(f"  failed/skipped  : {len(r['failed'])} (e.g. {r['failed'][:5]})")
    if r["updated"] == 0 and not r["failed"]:
        print("  already current — nothing to append.")


if __name__ == "__main__":
    main()
