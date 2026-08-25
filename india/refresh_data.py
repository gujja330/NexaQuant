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


def _load_yf_aliases() -> dict:
    """2026-08-25 · aliases from configs/ticker_aliases.yaml so we can
    translate legacy universe entries (MM.NS) to their current yfinance
    symbols (M&M.NS) WITHOUT touching MON001-sealed india/data_nse.py.
    Keeps scientific integrity intact while still pulling live data."""
    p = ROOT / "configs" / "ticker_aliases.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return {k.upper(): v for k, v in (cfg.get("india") or {}).items()}
    except Exception:
        return {}


_YF_ALIASES = _load_yf_aliases()


def ticker_for(sym):
    """Universe symbol → yfinance download symbol. Applies alias
    translation for legacy names (MM → M&M etc.). Non-stock indices
    keep their special mapping."""
    if sym in NON_STOCK:
        return NON_STOCK[sym]
    yf_sym = _YF_ALIASES.get(sym.upper(), sym)
    return f"{yf_sym}.NS"


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


def _angel_daily_fallback(sym: str) -> "pd.DataFrame | None":
    """2026-08-24 · Angel SmartAPI fallback for tickers where yfinance
    fails (delisted / renamed / 404). Uses .env.angel credentials.
    Returns fresh daily bars in the parquet schema or None on failure."""
    try:
        from backend.intraday.feed import angel_adapter as _angel
        df = _angel.fetch_bars(ROOT, sym, market="india",
                                              interval="1d", lookback_days=45)
        if df is None or df.empty: return None
        # angel_adapter returns df with 'date' index + open/high/low/close/volume
        df2 = df.rename(columns=str.lower)
        idx = pd.to_datetime(df2.index).normalize()
        out = pd.DataFrame(index=idx)
        out.index.name = "time"
        for c in ("open", "high", "low", "close"):
            if c in df2.columns:
                out[c] = pd.to_numeric(df2[c], errors="coerce")
        out["tick_volume"] = pd.to_numeric(
            df2.get("volume", 0), errors="coerce").fillna(0).astype("int64")
        out["spread"] = 0.0
        return out.dropna(subset=["close"])
    except Exception:
        return None


def refresh(limit=None):
    import yfinance as yf
    # 2026-08-24 · ticker_health tracker · log every attempt so operator
    # sees which symbols are consistently dead (TATAMOTORS / MM / LTIM / PEL
    # pattern). Non-fatal if the module isn't available.
    try:
        from backend.ingest import ticker_health as _th
    except Exception:
        _th = None

    files = sorted(glob.glob(str(RAW / "*_D1.parquet")))
    syms = [Path(f).stem.replace("_D1", "") for f in files]
    syms = [s for s in syms if s not in SKIP]
    if limit:
        syms = syms[:limit]
    tmap = {ticker_for(s): s for s in syms}
    tickers = list(tmap)
    updated, total_rows, failed, newest = 0, 0, [], None
    angel_rescued = 0     # 2026-08-24 · count tickers Angel saved

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
            yf_ok = False
            try:
                sub = data[tkr] if isinstance(data.columns, pd.MultiIndex) else data
                fresh = _to_schema(sub.dropna(how="all"))
                if not fresh.empty:
                    yf_ok = True
                    existing = pd.read_parquet(path)
                    add = fresh[fresh.index > existing.index[-1]]
                    if not add.empty:
                        merged = pd.concat([existing, add[existing.columns.intersection(add.columns)]])
                        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                        merged.to_parquet(path)
                        updated += 1; total_rows += len(add)
                        newest = max(newest, merged.index[-1]) if newest else merged.index[-1]
                    if _th is not None:
                        _th.record(ROOT, "india", sym, source="yfinance:daily", ok=True)
            except Exception as e:
                if _th is not None:
                    _th.record(ROOT, "india", sym, source="yfinance:daily",
                                     ok=False, error=str(e)[:200])
            # 2026-08-24 · yfinance failed · try Angel SmartAPI fallback
            if not yf_ok:
                _rescued = _angel_daily_fallback(sym)
                if _rescued is not None and not _rescued.empty:
                    try:
                        existing = pd.read_parquet(path)
                        add = _rescued[_rescued.index > existing.index[-1]]
                        if not add.empty:
                            merged = pd.concat([existing, add[existing.columns.intersection(add.columns)]])
                            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                            merged.to_parquet(path)
                            updated += 1; total_rows += len(add)
                            newest = max(newest, merged.index[-1]) if newest else merged.index[-1]
                            angel_rescued += 1
                            if _th is not None:
                                _th.record(ROOT, "india", sym,
                                                 source="angel:daily:fallback", ok=True)
                    except Exception:
                        failed.append(tkr)
                        if _th is not None:
                            _th.record(ROOT, "india", sym,
                                             source="angel:daily:fallback", ok=False)
                else:
                    failed.append(tkr)
                    if _th is not None:
                        _th.record(ROOT, "india", sym,
                                         source="angel:daily:fallback", ok=False,
                                         error="no data returned")
    # Emit ticker health report daily
    if _th is not None:
        try:
            from datetime import date as _d
            rep = _th.compute_report(ROOT, "india", _d.today().isoformat())
            _th.emit(ROOT, rep)
        except Exception:
            pass
    return dict(updated=updated, rows=total_rows, failed=failed,
                     newest=newest, n=len(tickers), angel_rescued=angel_rescued)


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
    if r.get("angel_rescued"):
        print(f"  Angel rescued   : {r['angel_rescued']}  (yfinance 404 · fallback succeeded)")
    if r["failed"]:
        print(f"  failed/skipped  : {len(r['failed'])} (e.g. {r['failed'][:5]})")
    if r["updated"] == 0 and not r["failed"]:
        print("  already current — nothing to append.")


if __name__ == "__main__":
    main()
