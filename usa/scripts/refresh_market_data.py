"""AEGIS USA · Market Data Refresh.

Pulls OHLCV daily bars from yfinance for every ticker in the active
USA universe (usa/reports/universe.json), plus the benchmark indices
(S&P 500, NASDAQ 100, Dow, VIX). Writes one parquet per ticker to
usa/data/raw/us/{TICKER}_D1.parquet.

Mirrors India's data-raw layout but is completely isolated under
usa/. No India file is touched.

Deterministic: retry logic per ticker, timezone-normalised timestamps,
sorted ticker iteration, atomic writes.

ALL PRICES IN USD ($).
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"FATAL: missing dep: {e}. Run: pip install pandas yfinance pyarrow")
    sys.exit(1)


_ROOT     = Path(__file__).resolve().parents[2]
_USA      = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from backend.ingest.ticker_health import yahoo_symbol
from backend.research.evidence.trading_calendars import completed_nyse_session
from backend.shared.atomic_io import replace_with_retry

UNIVERSE  = _USA / "reports" / "universe.json"
RAW_DIR   = _USA / "data" / "raw" / "us"


# Retry parameters
MAX_RETRIES = 3
BACKOFF_SEC = 1.5

# History window: 5 years is enough for backtester, Winner Genome, and
# 52-week context. yfinance handles the pagination internally.
HISTORY_PERIOD = "5y"

# v3.x scale tolerance: with 918-ticker S&P 500 + MidCap 400 universe,
# yfinance's Yahoo backend returns ~5-15% failures on any given day
# (delisted symbols, ticker renames, transient 404s, rate-limit spikes).
# Requiring 100% success would fail CI every day for reasons unrelated to
# our pipeline correctness. Set a minimum-success threshold: pipeline is
# green if at least THIS FRACTION of tickers refresh successfully.
# Below the threshold = actual outage · fail the step.
MIN_SUCCESS_FRACTION = 0.85

# Between-request throttle to reduce rate-limit collisions
INTER_REQUEST_SLEEP_SEC = 0.05


def _completed_bar_date(now: datetime) -> date:
    return completed_nyse_session(now)


def _new_bars_on_saved_basis(feed: pd.DataFrame, saved: pd.DataFrame | None) -> pd.DataFrame:
    """Keep historical rows and continue only a close basis evidenced by overlap."""
    fields = [c for c in ("open", "high", "low", "close", "volume") if c in feed]
    raw = feed[fields]
    adjusted = raw.copy()
    factors = feed["adj close"] / feed["close"]
    for col in ("open", "high", "low", "close"):
        if col in adjusted:
            adjusted[col] = adjusted[col] * factors
    if saved is None or saved.empty:
        return adjusted
    if not saved.index.is_unique or not saved.index.is_monotonic_increasing:
        raise ValueError("saved prices must have a unique increasing date axis")
    if not (saved["close"] > 0).all():
        raise ValueError("saved bars contain invalid closes")
    if raw.index.max() <= saved.index.max():
        return saved
    overlap = saved.index.intersection(raw.index)[-5:]
    if len(overlap) != 5:
        raise ValueError("insufficient overlapping closes to verify the price basis")
    if not set(saved.columns) <= set(fields):
        raise ValueError("provider does not supply the saved bar schema")
    reference = saved.loc[overlap, "close"]
    for candidate in (adjusted, raw):
        ratio = candidate.loc[overlap, "close"] / reference
        if ((ratio - 1).abs() <= 0.00005).all():
            added = candidate.loc[candidate.index > saved.index.max(), saved.columns]
            added = added.rename_axis(saved.index.name)
            return pd.concat([saved, added])
    raise ValueError("provider close basis disagrees with saved overlapping sessions")


def _fetch_one(symbol: str, saved: pd.DataFrame | None = None) -> pd.DataFrame | None:
    """Fetch OHLCV for one symbol with retries. Returns cleaned DataFrame
    or None if all retries fail."""
    provider_symbol = yahoo_symbol(_ROOT, "usa", symbol)
    cutoff = pd.Timestamp(_completed_bar_date(datetime.now(timezone.utc)))
    if saved is not None and not saved.empty and saved.index.max() > cutoff:
        print(f"    [BASIS BLOCK] {symbol}: saved bars extend beyond the last completed session")
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            period = HISTORY_PERIOD
            if saved is not None and not saved.empty and (cutoff - saved.index.max()).days <= 14:
                period = "1mo"
            df = yf.Ticker(provider_symbol).history(period=period, auto_adjust=False)
            if df is None or df.empty:
                raise RuntimeError("empty response")
            # Normalise: rename to lower-case, keep OHLCV, tz-strip index
            df = df.rename(columns=str.lower)
            keep = [c for c in ("open", "high", "low", "close", "adj close", "volume") if c in df.columns]
            df = df[keep].copy()
            df.index = pd.to_datetime(df.index).tz_localize(None) if df.index.tz else df.index
            df.index.name = "date"
            df = df.sort_index()
            df = df.loc[df.index <= cutoff]
            df = df.loc[(df["close"] > 0) & (df["adj close"] > 0)]
            if df.empty:
                raise RuntimeError("all-null close column after cleaning")
            return _new_bars_on_saved_basis(df, saved)
        except ValueError as e:
            print(f"    [BASIS BLOCK] {symbol}: {e}")
            return None
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"    [FAIL] {symbol}: {e}")
                return None
            time.sleep(BACKOFF_SEC * attempt)
    return None


def _write_parquet(df: pd.DataFrame, path: Path) -> int:
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=True)
    replace_with_retry(tmp, path)
    return path.stat().st_size


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Market Data Refresh · yfinance → data/raw/us/")
    print("=" * 70)

    if not UNIVERSE.exists():
        print(f"FATAL: {UNIVERSE.relative_to(_ROOT)} not found. Run build_universe.py first.")
        return 1

    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    tickers  = [str(t.get("symbol")) for t in (universe.get("tickers") or []) if t.get("symbol")]
    from backend.delivery.canonical.retirement import retired_runners
    from backend.research.opportunity_registry import load_all

    retired = retired_runners(_ROOT)
    monitored = {
        position.ticker for group in load_all(_ROOT).values() for position in group
        if position.market.lower() == "usa" and position.status == "ACTIVE"
        and position.runner not in retired
    }
    outside = monitored - set(tickers)
    tickers.extend(sorted(outside))
    print(f"  active positions outside scoring universe: {len(outside)}")
    benches  = universe.get("benchmarks") or {}
    for role, spec in benches.items():
        sym = spec.get("symbol") if isinstance(spec, dict) else None
        if sym: tickers.append(sym)

    # Deduplicate + sort for deterministic iteration
    tickers = sorted(set(tickers))
    required_symbols = set(tickers)
    pending_symbols = set((universe.get("security_master") or {}).get("pending") or ()) - required_symbols
    tickers.extend(sorted(pending_symbols))
    print(f"  universe: {universe.get('active_universe')}  ·  {len(tickers)} symbols to refresh")
    print(f"  period:   {HISTORY_PERIOD}")
    print(f"  target:   {RAW_DIR.relative_to(_ROOT)}/")
    print()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    ok, fail, skipped = 0, 0, 0
    total_bytes = 0
    freshness_by_symbol: dict[str, str] = {}

    failed_symbols: list[str] = []
    for i, sym in enumerate(tickers, 1):
        # Escape unsafe filename chars for indices like ^GSPC
        safe = sym.replace("^", "_IDX_")
        out_path = RAW_DIR / f"{safe}_D1.parquet"

        try:
            saved = pd.read_parquet(out_path) if out_path.exists() else None
            df = _fetch_one(sym, saved)
        except (OSError, ValueError, TypeError) as error:
            print(f"  {sym}: refresh deferred: {type(error).__name__}")
            df = None
        if df is None:
            fail += 1
            failed_symbols.append(sym)
            # Gentle throttle even on failure so we don't hammer rate limits
            time.sleep(INTER_REQUEST_SLEEP_SEC)
            continue

        b = _write_parquet(df, out_path) if df is not saved else out_path.stat().st_size
        total_bytes += b
        ok += 1
        last_date = str(df.index[-1].date())
        freshness_by_symbol[sym] = last_date
        print(f"  [{i:>2}/{len(tickers)}] {sym:<8} → {out_path.name:<22}  rows={len(df):>4}  last={last_date}  {b/1024:.1f} KB")
        # Rate-limit-friendly throttle · adds ~46s for 918 tickers, worth it
        time.sleep(INTER_REQUEST_SLEEP_SEC)

    elapsed = time.time() - t0
    print()
    print(f"  ok: {ok}  ·  failed: {fail}  ·  total size: {total_bytes/1024/1024:.2f} MB  ·  elapsed: {elapsed:.1f}s")
    # Log the sample of failures for operator visibility (delisted / renamed)
    if failed_symbols:
        head = failed_symbols[:15]
        tail = f" ... +{len(failed_symbols) - 15} more" if len(failed_symbols) > 15 else ""
        print(f"  failed sample: {', '.join(head)}{tail}")

    # Emit a freshness manifest so downstream steps can verify
    manifest = {
        "engine":   "usa_market_data_refresh",
        "version":  "v1.0",
        "run_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "period":   HISTORY_PERIOD,
        "n_ok":     ok,
        "n_fail":   fail,
        "total_bytes": total_bytes,
        "freshness": freshness_by_symbol,
    }
    (_USA / "reports" / "market_data_freshness.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    # v3.x scale tolerance: at 918-ticker scale, yfinance always returns
    # some failures (delisted / renamed / rate-limit spikes). Pass if the
    # success FRACTION exceeds MIN_SUCCESS_FRACTION. Log the failed
    # symbols above for operator inspection. Only true outages (< threshold)
    # fail the step. This matches the operator's Evidence-Gated Improvement
    # Cycle Ticket 7 (Data Source Governance · partial-failure tolerance).
    n_total = len(required_symbols)
    if n_total == 0:
        print("  no tickers in universe · treating as failure")
        return 1
    success_fraction = len(required_symbols & freshness_by_symbol.keys()) / n_total
    if success_fraction >= MIN_SUCCESS_FRACTION:
        print(f"  verdict: PASS · success {success_fraction:.1%} >= threshold {MIN_SUCCESS_FRACTION:.0%}")
        return 0
    print(f"  verdict: FAIL · success {success_fraction:.1%} < threshold "
          f"{MIN_SUCCESS_FRACTION:.0%} (likely real yfinance outage)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
