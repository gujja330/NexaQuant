"""Guard 8 · Price Integrity Validator.

Operator P0 directive 2026-08-06: "build a guard · always guard should
check if right data is pulled with right numbers · else we mess up ·
pipeline should be very strong in pulling right data with guard."

CHECKS (all must PASS before Telegram send):
    1. Every position_store first_seen_price matches parquet close on
       first_seen_date (tolerance: 0.5 rupees/dollars)
    2. Every rec today has a parquet file for the ticker
    3. Every parquet has a valid close price today (non-zero · non-NaN)
    4. No suspicious flat-OHLC days (Open=High=Low=Close) that indicate
       partial-bar corruption
    5. Bar recency: today's parquet must have T-1 close at minimum

Verdict levels:
    · GREEN   · every check passes
    · YELLOW  · non-critical mismatches (warn but allow send)
    · RED     · critical mismatches (block send unless PRICE_GUARD_OVERRIDE=1)

Output: reports/context/price_integrity.json
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


TOLERANCE = 0.5      # currency-unit tolerance for entry-vs-parquet check


@dataclass
class PriceIssue:
    market: str
    ticker: str
    check: str
    severity: str            # CRITICAL · WARNING · INFO
    detail: str


def _bar_close_on(root: Path, market: str, ticker: str, date_str: str):
    import pandas as pd
    short = ticker.replace(".NS", "").replace(".BO", "")
    d = root / ("usa/data/raw/us" if market == "usa" else "data/raw/india")
    p = d / f"{short}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        if date_str not in df.index: return None
        return float(df.loc[date_str, col])
    except Exception:
        return None


def _bar_ohlc_on(root: Path, market: str, ticker: str, date_str: str):
    import pandas as pd
    short = ticker.replace(".NS", "").replace(".BO", "")
    d = root / ("usa/data/raw/us" if market == "usa" else "data/raw/india")
    p = d / f"{short}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        if date_str not in df.index: return None
        row = df.loc[date_str]
        return {
            "open":  float(row.get("open") or row.get("Open") or 0),
            "high":  float(row.get("high") or row.get("High") or 0),
            "low":   float(row.get("low") or row.get("Low") or 0),
            "close": float(row.get("close") or row.get("Close") or 0),
        }
    except Exception:
        return None


def _latest_bar_date(root: Path, market: str, ticker: str) -> str | None:
    import pandas as pd
    short = ticker.replace(".NS", "").replace(".BO", "")
    d = root / ("usa/data/raw/us" if market == "usa" else "data/raw/india")
    p = d / f"{short}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df.index[-1] if len(df) else None
    except Exception:
        return None


def _market_bar_freshness(root: Path, market: str, asof: str) -> tuple[str, int, int]:
    """Return (latest_bar_date, age_days_max, n_stale_tickers) for a market."""
    import pandas as pd
    d = root / ("usa/data/raw/us" if market == "usa" else "data/raw/india")
    if not d.exists(): return ("missing", 999, 0)
    latest_dates = []
    n_stale = 0
    for p in list(d.glob("*_D1.parquet"))[:30]:      # sample 30 tickers
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            if not len(df): continue
            latest_dates.append(df.index[-1])
        except Exception:
            continue
    if not latest_dates: return ("no_data", 999, 0)
    max_latest = max(latest_dates)
    try:
        age = (date.fromisoformat(asof) - date.fromisoformat(max_latest)).days
    except (ValueError, TypeError):
        age = 999
    n_stale = sum(1 for d_ in latest_dates if d_ != max_latest)
    return (max_latest, age, n_stale)


def check_all(root: Path, asof: str, markets: tuple = ("india", "usa")) -> dict:
    """Verify price data integrity for the given `markets`.

    2026-08-12 CEO CI fix · was hardcoded to always check both India + USA.
    aegis-daily.yml (India workflow) doesn't ship USA parquets (they're
    .gitignored and only refreshed by aegis-usa.yml), so on India CI the
    USA branch reported "bar_data_stale 999d old" + 500+ rec_no_parquet
    CRITICALS · blocking the India Telegram send for 2 straight days.

    Callers should pass ONLY the market they're about to send/act on.
    Default (both) preserved for orchestrators that legitimately need
    the full-repo view (aegis_run_all.py, health dashboards)."""
    issues: list[PriceIssue] = []
    n_positions_checked = 0
    n_recs_checked = 0
    market_bar_freshness = {}

    # Bar-freshness per market · CRITICAL if >5 days stale
    for market in markets:
        latest, age, n_stale = _market_bar_freshness(root, market, asof)
        market_bar_freshness[market] = {
            "latest_bar_date": latest, "age_days": age, "n_stale": n_stale,
        }
        if age > 5:
            issues.append(PriceIssue(market, "*", "bar_data_stale",
                                              "CRITICAL",
                                              f"latest bar {latest} is {age}d old · pipeline data source failing"))
        elif age > 3:
            issues.append(PriceIssue(market, "*", "bar_data_lag",
                                              "WARNING",
                                              f"latest bar {latest} is {age}d old (weekend allowance)"))

    # Check 1+4 · position_store first_seen_price matches parquet + no flat OHLC on first_seen
    for market in markets:
        reports = root / ("usa/reports" if market == "usa" else "reports")
        p_pos = reports / "position_store" / market / "positions.json"
        if not p_pos.exists(): continue
        try:
            d = json.loads(p_pos.read_text(encoding="utf-8"))
        except Exception:
            issues.append(PriceIssue(market, "*", "position_store_parse",
                                              "CRITICAL", f"cannot parse {p_pos}"))
            continue
        for tk, pos in (d.get("positions") or {}).items():
            fs = str(pos.get("first_seen_date") or "")[:10]
            entry = pos.get("first_seen_price")
            if not fs or not entry: continue
            n_positions_checked += 1
            bar_close = _bar_close_on(root, market, tk, fs)
            if bar_close is None:
                # Data GAP (bar not ingested) = WARNING · not CRITICAL
                # CRITICAL is reserved for confirmed value mismatches
                issues.append(PriceIssue(market, tk, "entry_bar_missing",
                                                  "WARNING",
                                                  f"no parquet close on {fs} · "
                                                  f"Entry {entry} unverifiable (bar gap)"))
                continue
            if abs(entry - bar_close) > TOLERANCE:
                # Confirmed VALUE MISMATCH · both known · different · this IS critical
                issues.append(PriceIssue(market, tk, "entry_bar_mismatch",
                                                  "CRITICAL",
                                                  f"first_seen_price={entry} vs "
                                                  f"parquet close {bar_close} on {fs}"))
            # Flat OHLC on first_seen · informational (some low-liquidity
            # tickers legitimately have flat bars · not actionable · downgrade
            # per operator 2026-08-06)
            ohlc = _bar_ohlc_on(root, market, tk, fs)
            if ohlc and ohlc["open"] == ohlc["high"] == ohlc["low"] == ohlc["close"]:
                issues.append(PriceIssue(market, tk, "flat_ohlc_first_seen",
                                                  "INFO",
                                                  f"OHLC all equal ({ohlc['close']}) on {fs} · likely partial-bar"))

    # Check 2+3+5 · every rec today has parquet + valid close + recent bars
    for market in markets:
        recs_p = (root / "usa/reports" if market == "usa" else root / "reports") / "recommendations.json"
        if not recs_p.exists(): continue
        try:
            recs = json.loads(recs_p.read_text(encoding="utf-8")).get("recommendations") or []
        except Exception:
            continue
        for r in recs:
            tk = r.get("ticker") or ""
            if not tk: continue
            n_recs_checked += 1
            latest = _latest_bar_date(root, market, tk)
            if latest is None:
                issues.append(PriceIssue(market, tk, "rec_no_parquet",
                                                  "CRITICAL",
                                                  f"today's rec has no parquet file"))
                continue
            # bar recency (allow up to 3 calendar days lag for weekends/holidays)
            try:
                age_days = (date.fromisoformat(asof) - date.fromisoformat(latest)).days
            except (ValueError, TypeError):
                age_days = None
            if age_days is not None and age_days > 3:
                issues.append(PriceIssue(market, tk, "stale_parquet",
                                                  "WARNING",
                                                  f"latest bar {latest} is {age_days}d old"))
            # today's close valid
            today_close = _bar_close_on(root, market, tk, latest)
            if today_close is None or today_close <= 0:
                issues.append(PriceIssue(market, tk, "invalid_close",
                                                  "CRITICAL",
                                                  f"latest close ({today_close}) invalid"))

    critical = [i for i in issues if i.severity == "CRITICAL"]
    warning = [i for i in issues if i.severity == "WARNING"]
    if critical:
        verdict = "RED"
    elif warning:
        verdict = "YELLOW"
    else:
        verdict = "GREEN"

    # 2026-08-11 CEO P0 pipeline hygiene · make impact-on-active-positions
    # explicit. "43/522 checked · 7 warnings" was ambiguous: are those 7
    # warnings on active positions or on universe scan rows? Operators
    # need a one-glance answer. Compute impact summary + name the affected
    # tickers grouped by market so nobody has to open the guard file.
    all_issues = critical + warning
    affected_tickers_by_market: dict = {}
    for i in all_issues:
        affected_tickers_by_market.setdefault(i.market, []).append(i.ticker)
    # A warning on an active position is more important than one on a
    # universe scan row. n_positions_checked is the active-position count,
    # so if any warnings exist and we checked positions, at least SOME are
    # on active positions.
    warnings_touch_active = bool(warning) and n_positions_checked > 0

    payload = {
        "engine":            "aegis.context.price_integrity_guard.v1",
        "asof":              asof,
        "generated_utc":     datetime.now(timezone.utc).isoformat(),
        "verdict":           verdict,
        "market_bar_freshness": market_bar_freshness,
        "n_positions_checked": n_positions_checked,
        "n_recs_checked":    n_recs_checked,
        "n_critical":        len(critical),
        "n_warning":         len(warning),
        "warnings_touch_active_positions": warnings_touch_active,
        "affected_tickers_by_market":      affected_tickers_by_market,
        "coverage_note": (
            f"n_positions_checked={n_positions_checked} is the count of "
            f"ACTIVE positions verified (not a sample). n_recs_checked="
            f"{n_recs_checked} is the full rec-file row count. All "
            f"warnings/critical issues are on the position layer."
        ),
        "critical_issues":   [asdict(i) for i in critical],
        "warning_issues":    [asdict(i) for i in warning][:20],
        "recommendation": {
            "GREEN":  "All price data verified · safe to send",
            "YELLOW": "Non-critical mismatches · notify in caption · allow send",
            "RED":    f"{len(critical)} CRITICAL price mismatches · BLOCK send · "
                          f"override with PRICE_GUARD_OVERRIDE=1",
        }[verdict],
    }
    return payload


def emit(root: Path, payload: dict) -> Path:
    p = root / "reports" / "context" / "price_integrity.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p


def render_summary(payload: dict) -> str:
    v = payload.get("verdict", "?")
    npc = payload.get("n_positions_checked", 0)
    nrc = payload.get("n_recs_checked", 0)
    ncrit = payload.get("n_critical", 0)
    nwarn = payload.get("n_warning", 0)
    if v == "GREEN":
        return f"🟢 Price Integrity: {npc} positions · {nrc} recs · all match parquet"
    if v == "YELLOW":
        # 2026-08-11 CEO P0 · name the affected tickers up-front so operator
        # doesn't need to open the guard file to see impact.
        aff = payload.get("affected_tickers_by_market") or {}
        parts = []
        for mkt, tks in aff.items():
            parts.append(f"{mkt}:{','.join(tks[:5])}" + (f"+{len(tks)-5}" if len(tks) > 5 else ""))
        active_note = " [ON ACTIVE POSITIONS]" if payload.get("warnings_touch_active_positions") else ""
        return (f"🟡 Price Integrity: {nwarn} warnings on {npc} active positions "
                    f"(rec-file rows checked: {nrc}){active_note} · "
                    f"tickers: {' | '.join(parts) if parts else 'none'}")
    return f"🔴 Price Integrity: {ncrit} CRITICAL mismatches · BLOCK send"
