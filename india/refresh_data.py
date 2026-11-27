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
import sys, glob, time, warnings
import csv
import io
import json
from math import isclose, isfinite
from pathlib import Path
from zipfile import BadZipFile, ZipFile
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
    df.index = idx.normalize()
    out = pd.DataFrame(index=df.index)
    out.index.name = "time"
    for c in ("open", "high", "low", "close"):
        out[c] = pd.to_numeric(df.get(c), errors="coerce")
    out["tick_volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0).astype("int64")
    out["spread"] = 0.0
    return out.dropna(subset=["close"])


def _verified_alias_history(yf, ticker, existing, fresh):
    """Backfill a renamed feed only after proving continuity on saved closes."""
    latest_saved = existing.index.max()
    if fresh.empty or fresh.index.min() > latest_saved - pd.Timedelta(days=14):
        downloaded = yf.Ticker(ticker).history(
            start=(latest_saved - pd.Timedelta(days=30)).date(), auto_adjust=False,
        )
        if downloaded.empty:
            raise ValueError("renamed provider symbol returned no history")
        fresh = _to_schema(downloaded)
    overlap = existing[["close"]].join(fresh[["close"]], how="inner", rsuffix="_provider").tail(5)
    if len(overlap) < 5 or overlap.isna().any().any():
        raise ValueError("renamed provider series has fewer than five comparable saved closes")
    difference = (overlap["close_provider"] - overlap["close"]).abs()
    if (difference > overlap["close"].abs() * 0.00005).any():
        raise ValueError("renamed provider closes disagree with the saved price basis")
    return fresh


def _reconcile_mm_final_sessions(path, exceptions=None):
    """Replace two partial M&M bars with identified NSE EQ final records in staging.

    CEO 2026-11-27 · this used to RAISE when a saved bar matched neither the
    known partial nor the NSE final - and the raise killed the entire India
    refresh, all 228 symbols, over two old bars of one stock. It happened on
    2026-11-27: a git merge brought CI's copy of MM_D1.parquet, a DIFFERENT
    vendor partial (close 3527.10 / 3499.30), and India died in 10 seconds.

    The session is now identified by its OPEN, which a partial and the final
    record share (they differ in high/low/close/volume); an identified
    session is replaced with the NSE final. A bar that cannot be identified
    is left untouched and flagged in `exceptions` for review, so one stock
    can no longer stop the market.
    """
    if not path.is_file():
        return
    expected = {
        "2026-11-20": ((3487.9, 3538, 3479.2, 3510, 1263071),
                       (3487.9, 3570, 3479.2, 3545, 3534774)),
        "2026-11-23": ((3550, 3568, 3495.5, 3501.7, 2210378),
                       (3550, 3568, 3468.3, 3487.4, 2693707)),
    }
    columns = ["open", "high", "low", "close", "tick_volume"]
    saved = pd.read_parquet(path)
    corrections = []
    for session, (previous, final) in expected.items():
        index = pd.Timestamp(session)
        if index not in saved.index:
            continue
        values = saved.loc[index, columns].tolist()
        if all(isclose(x, y, abs_tol=0.001) for x, y in zip(values, final)):
            continue
        if not all(isclose(x, y, abs_tol=0.001) for x, y in zip(values, previous)):
            if not isclose(values[0], final[0], abs_tol=0.001):
                msg = (f"MM {session} has unknown prior data (open {values[0]} vs NSE "
                       f"final open {final[0]}) · left unchanged, review")
                print(f"  {msg}")
                if exceptions is not None:
                    exceptions["MM"] = msg
                continue
            # same session (same open), a different vendor partial -> NSE final
        corrections.append({
            "session": session, "ticker": "MM", "exchange_symbol": "M&M",
            "isin": "INE101A01026", "series": "EQ",
            "source": ("https://archives.nseindia.com/content/cm/"
                       f"BhavCopy_NSE_CM_0_0_0_{session.replace('-', '')}_F_0000.csv.zip"),
            "before": dict(zip(columns, values)),
            "after": dict(zip(columns, final)),
        })
        for column, value in zip(columns, final):
            saved.at[index, column] = value
    if not corrections:
        return
    audit = ROOT / "reports" / "audit" / "nse_final_price_corrections_mm_202611.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    if audit.is_file():
        prior = json.loads(audit.read_text(encoding="utf-8"))
        corrections = list({row["session"]: row for row in [*prior, *corrections]}.values())
    audit_temp = audit.with_suffix(".tmp")
    try:
        audit_temp.write_text(json.dumps(corrections, indent=2), encoding="utf-8")
        audit_temp.replace(audit)
    finally:
        audit_temp.unlink(missing_ok=True)
    _atomic_parquet(saved, path)


def _atomic_parquet(data, path):
    temporary = path.with_suffix(".tmp")
    try:
        data.to_parquet(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _nse_final_fallback(symbols, session, exceptions=None):
    """Append final NSE equity bars missing from the vendor's completed session."""
    import requests
    from backend.shared.atomic_io import write_text_atomic

    exceptions = exceptions if exceptions is not None else {}
    pending = {}
    for ticker in symbols:
        if ticker in NON_STOCK:
            continue
        path = RAW / f"{ticker}_D1.parquet"
        try:
            previous = pd.read_parquet(path, columns=[]).index.max()
        except (OSError, ValueError) as error:
            exceptions[ticker] = f"saved file unreadable: {error}"
            continue
        if pd.isna(previous):
            exceptions[ticker] = "saved history is empty"
            continue
        if previous < session:
            pending[ticker_for(ticker).removesuffix(".NS")] = (ticker, path, previous)
    if not pending:
        return []

    failures = []
    for host in ("archives.nseindia.com", "nsearchives.nseindia.com"):
        url = f"https://{host}/content/cm/BhavCopy_NSE_CM_0_0_0_{session:%Y%m%d}_F_0000.csv.zip"
        try:
            response = requests.get(url, timeout=(8, 30), headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            break
        except requests.RequestException as error:
            failures.append(str(error))
    else:
        for ticker, _, _ in pending.values():
            exceptions[ticker] = f"NSE final archive unavailable: {failures}"
        return []

    rows = {}
    session_iso = session.date().isoformat()
    with ZipFile(io.BytesIO(response.content)) as archive:
        member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        with archive.open(member) as stream:
            for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")):
                symbol = row["TckrSymb"]
                if symbol not in pending or row["SctySrs"] != "EQ" or row["TradDt"] != session_iso:
                    continue
                ticker = pending[symbol][0]
                if symbol in rows or ticker in exceptions:
                    exceptions[ticker] = f"ambiguous NSE final equity rows on {session_iso}"
                    continue
                try:
                    prices = {key: float(row[column]) for key, column in (
                        ("open", "OpnPric"), ("high", "HghPric"), ("low", "LwPric"), ("close", "ClsPric"),
                    )}
                    volume = int(row["TtlTradgVol"])
                except (ValueError, TypeError, KeyError):
                    exceptions[ticker] = f"malformed NSE final equity row on {session_iso}"
                    continue
                if (not all(isfinite(value) and value > 0 for value in prices.values()) or volume <= 0
                        or not prices["low"] <= min(prices["open"], prices["close"])
                        <= max(prices["open"], prices["close"]) <= prices["high"]):
                    exceptions[ticker] = f"invalid NSE final equity row on {session_iso}"
                    continue
                rows[symbol] = (row["ISIN"], {**prices, "tick_volume": volume, "spread": 0.0})
    receipts = []
    for symbol, (ticker, path, previous) in pending.items():
        if ticker in exceptions or symbol not in rows:
            exceptions.setdefault(ticker, f"NSE final EQ row absent for {symbol} on {session_iso}; {url}")
            continue
        isin, bar = rows[symbol]
        saved = pd.read_parquet(path)
        if saved.index.max() != previous:
            raise RuntimeError(f"saved price data changed during NSE reconciliation: {path}")
        append = pd.DataFrame([bar], index=pd.DatetimeIndex([session], name=saved.index.name))
        _atomic_parquet(pd.concat([saved, append], axis=0), path)
        receipts.append({"ticker": ticker, "exchange_symbol": symbol, "isin": isin,
                         "previous_last_date": previous.date().isoformat(), "bar": bar})
    if not receipts:
        return []
    audit = ROOT / "reports" / "audit" / f"nse_final_bar_fallback_{session_iso}.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(audit.read_text(encoding="utf-8"))["bars"] if audit.is_file() else []
    write_text_atomic(audit, json.dumps({"session": session_iso, "source": url, "bars": existing + receipts},
                                       indent=2) + "\n")
    return [row["ticker"] for row in receipts]


def _restore_ltim_prices(yf, last_session, path):
    """Restore the configured LTIM member after the NSE trading symbol changed."""
    if path.exists():
        return
    provider = ticker_for("LTIM")
    try:
        history = yf.Ticker(provider).history(period="5y", auto_adjust=False)
    except Exception as error:
        raise ValueError(f"{provider} history request failed: {error}") from error
    if history.empty:
        raise ValueError(f"{provider} returned no history for the configured LTIM member")
    from scripts.check_data_freshness import NSE_HOLIDAYS_2026

    bars = _to_schema(history)
    bars = bars.loc[(bars.index <= last_session) & ~bars.index.isin(NSE_HOLIDAYS_2026)]
    basis_day = pd.Timestamp("2026-11-23")
    if (len(bars) < 250 or not bars.index.is_unique or not bars.index.is_monotonic_increasing
            or basis_day not in bars.index
            or not isclose(float(bars.at[basis_day, "close"]), 4215.0, abs_tol=0.01)):
        raise ValueError("LTIM provider history failed the NSE identity or historical data checks")
    audit = ROOT / "reports" / "audit" / "nse_ltim_symbol_recovery.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps({
        "canonical_key": "LTIM", "provider_symbol": provider, "isin": "INE214T01019",
        "first_session": bars.index.min().date().isoformat(),
        "last_session": bars.index.max().date().isoformat(), "rows": len(bars),
        "close_verified_on": "2026-11-23", "close_verified": 4215.0,
        "listing_circular": "https://nsearchives.nseindia.com/corporate/vinodn_23022026185614_CML72948.pdf",
        "close_source": ("https://archives.nseindia.com/content/cm/"
                         "BhavCopy_NSE_CM_0_0_0_20261123_F_0000.csv.zip"),
    }, indent=2), encoding="utf-8")
    _atomic_parquet(bars, path)


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


def _maintain_tracked_history(last_session, holidays, exceptions):
    """Seed missing histories for verified curated/held identities only."""
    import json
    from backend.delivery.canonical.retirement import retired_runners
    from backend.feature_store.features.technical import BARS_52W
    from backend.ingest.security_master import populations
    from backend.research.opportunity_registry import active_opportunities, load_all
    from backend.shared.atomic_io import write_text_atomic
    from india.data_nse import STOCKS, fetch

    retired = retired_runners(ROOT)
    held = {position.ticker.upper().removesuffix(".NS").removesuffix(".BO")
            for position in active_opportunities(load_all(ROOT))
            if position.market == "india" and position.runner not in retired}
    master = populations(ROOT, "india", STOCKS, held, ("^NSEI", "^NSEBANK"))
    master["policy"] = "CURATED"
    master["session"] = last_session.date().isoformat()
    master["data_pending"] = []
    for symbol in sorted(set(STOCKS) | held):
        if (not symbol or not symbol[0].isalnum()
                or not all(char.isalnum() or char in ".&-" for char in symbol)):
            continue
        path = RAW / f"{symbol}_D1.parquet"
        if path.is_file():
            continue
        master["data_pending"].append(symbol)
        # Missing legacy files need proof of the successor/history basis.
        if symbol in {"PEL", "TATAMOTORS"} or symbol in _YF_ALIASES:
            continue
        try:
            bars = fetch(ticker_for(symbol), years=2)
            if bars is not None:
                bars.index = pd.to_datetime(bars.index).tz_localize(None).normalize()
                bars = bars.loc[(bars.index <= last_session) & ~bars.index.isin(holidays)]
                if (len(bars) >= BARS_52W and bars.index.is_unique and bars.index.is_monotonic_increasing
                        and bars.index[-1] == last_session and (bars["close"] > 0).all()
                        and (bars["close"] < float("inf")).all()):
                    _atomic_parquet(bars, path)
                    master["data_pending"].remove(symbol)
                    continue
            exceptions[symbol] = "initial price history or completed session not verified"
        except Exception as error:
            exceptions[symbol] = f"initial price history unavailable ({type(error).__name__})"
    write_text_atomic(ROOT / "reports/context/security_master_india.json",
                      json.dumps(master, indent=2))


def refresh(limit=None, *, reconcile_final_bars=False):
    import yfinance as yf
    from scripts.check_data_freshness import completed_nse_session, NSE_HOLIDAYS_2026

    last_session = pd.Timestamp(completed_nse_session())
    # 2026-08-24 · ticker_health tracker · log every attempt so operator
    # sees which symbols are consistently dead (TATAMOTORS / MM / LTIM / PEL
    # pattern). Non-fatal if the module isn't available.
    try:
        from backend.ingest import ticker_health as _th
    except Exception:
        _th = None

    exceptions = {}
    if reconcile_final_bars:
        _reconcile_mm_final_sessions(RAW / "MM_D1.parquet", exceptions)
        try:
            _restore_ltim_prices(yf, last_session, RAW / "LTIM_D1.parquet")
        except ValueError as error:
            exceptions["LTIM"] = str(error)
            print(f"  LTIM recovery deferred: {error}")
        if limit is None:
            _maintain_tracked_history(last_session, NSE_HOLIDAYS_2026, exceptions)
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
        # CEO 2026-10-20 · RETRY. This was a bare `except Exception: failed +=
        # batch; continue` - one transient yfinance error (rate limit, DNS,
        # 5xx) abandoned an ENTIRE batch of tickers with no second attempt. A
        # few unlucky batches leave the data stale, the freshness gate then
        # correctly aborts the run, and the operator gets no workbook for the
        # day because of a blip that a retry would have absorbed. yfinance
        # rate-limits aggressively, so retry with backoff before giving up.
        data = None
        for _attempt in range(4):
            try:
                data = yf.download(batch, period="1mo", group_by="ticker",
                                   progress=False, auto_adjust=False,
                                   threads=True)   # 1mo covers gaps from missed runs
                if data is not None and not data.empty:
                    break
                data = None
            except Exception as _e:
                data = None
            if _attempt < 3:
                _wait = 5 * (_attempt + 1)
                print("  [refresh] batch %d-%d attempt %d failed · retrying in %ds"
                      % (i, i + len(batch), _attempt + 1, _wait))
                time.sleep(_wait)
        if data is None:
            print("  [refresh] batch %d-%d FAILED after 4 attempts · %d ticker(s) "
                  "left to the Angel fallback / freshness gate"
                  % (i, i + len(batch), len(batch)))
            failed += batch
            continue
        for tkr in batch:
            sym = tmap[tkr]
            path = RAW / f"{sym}_D1.parquet"
            yf_ok = False
            renamed = sym.upper() in _YF_ALIASES
            try:
                sub = data[tkr] if isinstance(data.columns, pd.MultiIndex) else data
                fresh = _to_schema(sub.dropna(how="all"))
                if renamed or not fresh.empty:
                    existing = pd.read_parquet(path)
                    if renamed:
                        fresh = _verified_alias_history(yf, tkr, existing, fresh)
                    if sym != "SP500":
                        fresh = fresh.loc[(fresh.index <= last_session)
                                          & ~fresh.index.isin(NSE_HOLIDAYS_2026)]
                    add = fresh[fresh.index > existing.index[-1]]
                    if not add.empty:
                        merged = pd.concat([existing, add[existing.columns.intersection(add.columns)]])
                        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                        _atomic_parquet(merged, path)
                        updated += 1; total_rows += len(add)
                        newest = max(newest, merged.index[-1]) if newest else merged.index[-1]
                    yf_ok = True
                    if _th is not None:
                        _th.record(ROOT, "india", sym, source="yfinance:daily", ok=True)
            except Exception as e:
                if _th is not None:
                    _th.record(ROOT, "india", sym, source="yfinance:daily",
                                     ok=False, error=str(e)[:200])
            if renamed and not yf_ok:
                failed.append(tkr)
                continue
            # 2026-08-24 · yfinance failed · try Angel SmartAPI fallback
            if not yf_ok:
                _rescued = _angel_daily_fallback(sym)
                if _rescued is not None and not _rescued.empty:
                    try:
                        existing = pd.read_parquet(path)
                        if sym != "SP500":
                            _rescued = _rescued.loc[(_rescued.index <= last_session)
                                                    & ~_rescued.index.isin(NSE_HOLIDAYS_2026)]
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
    recovered = []
    if reconcile_final_bars:
        from india.price_availability import audit_prices

        try:
            recovered = _nse_final_fallback(tmap.values(), last_session, exceptions)
        except (BadZipFile, UnicodeError, KeyError, StopIteration) as error:
            exceptions["_archive"] = f"NSE final archive unreadable: {error}"
        audit_prices(ROOT, last_session.date().isoformat(), tmap.values(), exceptions)
    if recovered:
        recovered_provider = {ticker_for(ticker) for ticker in recovered}
        failed = [symbol for symbol in failed if symbol not in recovered_provider]
        updated += len(recovered)
        total_rows += len(recovered)
        newest = max(newest, last_session) if newest else last_session
    return dict(updated=updated, rows=total_rows, failed=failed, nse_recovered=recovered,
                     newest=newest, n=len(tickers), angel_rescued=angel_rescued)


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    print("=" * 60)
    print("  AEGIS DATA REFRESH — appending latest market data")
    print("=" * 60)
    r = refresh(limit=limit, reconcile_final_bars="--reconcile-final-bars" in sys.argv)
    print(f"  symbols checked : {r['n']}")
    print(f"  updated         : {r['updated']}  (+{r['rows']} new rows)")
    print(f"  newest date now : {r['newest'].date() if r['newest'] is not None else 'unchanged'}")
    if r.get("angel_rescued"):
        print(f"  Angel rescued   : {r['angel_rescued']}  (yfinance 404 · fallback succeeded)")
    if r["nse_recovered"]:
        print(f"  NSE final bars  : recovered {', '.join(r['nse_recovered'])}")
    if r["failed"]:
        print(f"  failed/skipped  : {len(r['failed'])} (e.g. {r['failed'][:5]})")
    if r["updated"] == 0 and not r["failed"]:
        print("  already current — nothing to append.")


if __name__ == "__main__":
    main()
