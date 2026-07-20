"""Morning Report · Recommendation Lifecycle Scoreboard.

For every current recommendation, computes the day-by-day trajectory
from first_seen_date onward. Fields per row:

  ticker · sector · entry_price · day+1 · day+3 · day+5 · day+10 ·
  current · max_gain · max_dd · age_days · expected_hold · status

Pure aggregation. Reads:
  - reports/recommendation_lifecycle.json (for first_seen_date)
  - reports/recommendations.json         (for current action, target, stop, hold)
  - reports/price_context.json           (for latest CMP)
  - data/raw/india/{TICKER}_D1.parquet   (for the price series between
                                          first_seen and today)

No new engine. No new pipeline step. Extension of the Morning Report
per AEGIS_CONSTITUTION.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"
RAW_DIR = _ROOT / "data" / "raw" / "india"


# ── Outcome badge palette
BADGE_WINNER    = "🟢 Winner"
BADGE_ACTIVE    = "🟡 Active"
BADGE_TARGET    = "🔵 Target Hit"
BADGE_STOP      = "🔴 Stopped Out"
BADGE_EXPIRED   = "⚪ Expired"
BADGE_INSUFFICIENT = "⏳ Warming"


def _load_json(name: str) -> dict | None:
    p = REPORTS / name
    if not p.exists(): return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_price_series(ticker: str) -> pd.Series | None:
    p = RAW_DIR / f"{ticker}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
    except Exception:
        return None
    if df.empty: return None
    close_col = next((c for c in df.columns if c.lower() in ("close", "adj close", "adj_close")), None)
    if not close_col: return None
    date_col = next((c for c in df.columns if c.lower() in ("date", "dt", "timestamp", "time")), None)
    if date_col and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).sort_values(date_col).set_index(date_col)
    else:
        try:
            df.index = pd.to_datetime(df.index, errors="coerce")
        except Exception:
            return None
        df = df.sort_index()
    return df[close_col].dropna().astype(float)


def _pct_change(p_from: float | None, p_to: float | None) -> float | None:
    if p_from is None or p_to is None or p_from <= 0:
        return None
    return (p_to - p_from) / p_from


def _price_at_offset(series: pd.Series, entry_dt: pd.Timestamp, offset_days: int) -> float | None:
    """Return the close at `offset_days` trading days after entry_dt, or
    None if we don't yet have enough forward history."""
    forward = series[series.index > entry_dt]
    if len(forward) < offset_days:
        return None
    return float(forward.iloc[offset_days - 1])


def _classify(row: dict, hi: float | None, lo: float | None,
                cmp_val: float | None, target: float | None, stop: float | None,
                age_days: int | None, max_hold: int | None) -> str:
    if hi is None or lo is None or cmp_val is None:
        return BADGE_INSUFFICIENT
    # Target hit if HIGH >= target at any point
    if target and hi >= target:
        return BADGE_TARGET
    # Stop hit if LOW <= stop at any point
    if stop and lo <= stop:
        return BADGE_STOP
    # Expired if past max_hold
    if age_days is not None and max_hold and age_days > max_hold:
        return BADGE_EXPIRED
    # Winner if current return > +5%
    entry = row.get("entry_price")
    if entry and cmp_val and (cmp_val - entry) / entry > 0.05:
        return BADGE_WINNER
    return BADGE_ACTIVE


def build_scoreboard(top_n: int = 10) -> list[dict]:
    """Build the lifecycle scoreboard for today's Top-N recommendations.

    Returns a list of dicts, one per ticker, sorted by the same ordering
    as the Top Opportunities table (Investment Decision Score desc).
    Handles day-1 baseline gracefully (all forward-return columns null).
    """
    recs   = _load_json("recommendations.json")           or {}
    intel  = _load_json("investment_intelligence.json")   or {}
    lc     = _load_json("recommendation_lifecycle.json")  or {}
    prices = _load_json("price_context.json")             or {}

    lc_by_ticker    = lc.get("by_ticker") or {}
    intel_by_ticker = {str(r.get("ticker")): r for r in (intel.get("reports") or [])}
    price_tickers   = prices.get("tickers") or {}

    # Recommendations.json's run_utc can carry both "+00:00" and a trailing "Z"
    # (belt-and-suspenders serialization from an older engine); strip the Z so
    # pandas can parse it cleanly.
    run_utc = recs.get("run_utc") or ""
    if run_utc.endswith("Z") and "+" in run_utc:
        run_utc = run_utc[:-1]
    try:
        today_dt = pd.to_datetime(run_utc) if run_utc else pd.Timestamp.now()
    except Exception:
        today_dt = pd.Timestamp.now()
    today_dt = today_dt.tz_localize(None) if today_dt.tzinfo else today_dt

    # Filter to actionable buys and take top_n by composite_decision_score
    all_recs = list(recs.get("recommendations") or [])
    buys = [r for r in all_recs
            if r.get("recommendation") in ("Strong-Buy", "Buy", "Accumulate")]
    buys.sort(key=lambda r: r.get("composite_decision_score") or 0, reverse=True)
    top = buys[:top_n]

    rows: list[dict] = []
    for r in top:
        t = str(r.get("ticker") or "")
        if not t: continue
        ee = r.get("entry_exit") or {}
        lci = lc_by_ticker.get(t) or {}
        pc  = price_tickers.get(t) or {}
        ii  = intel_by_ticker.get(t) or {}

        first_seen = lci.get("first_seen_date")
        first_seen_dt = pd.to_datetime(first_seen) if first_seen else None
        entry_price   = ee.get("latest_close")
        target        = ee.get("target_1")
        stop          = ee.get("stop_loss")
        max_hold      = ee.get("maximum_holding_days") or ee.get("expected_holding_days")
        expected_hold = ee.get("expected_holding_days")
        cmp_val       = pc.get("cmp") if pc.get("available") else entry_price

        # Load price series once and slice
        series = _load_price_series(t)
        d1 = d3 = d5 = d10 = current_ret = mfe_pct = mae_pct = None
        hi = lo = None
        age_days = None

        if series is not None and first_seen_dt is not None:
            entry_close = None
            entry_slice = series[series.index <= first_seen_dt]
            if not entry_slice.empty:
                entry_close = float(entry_slice.iloc[-1])
            # Forward window
            forward = series[series.index > first_seen_dt]

            if entry_close and not forward.empty:
                # Interval forward returns
                for off, key in ((1, "d1"), (3, "d3"), (5, "d5"), (10, "d10")):
                    p_at = _price_at_offset(series, first_seen_dt, off)
                    val = _pct_change(entry_close, p_at)
                    if   key == "d1":  d1  = val
                    elif key == "d3":  d3  = val
                    elif key == "d5":  d5  = val
                    elif key == "d10": d10 = val

                # Current return + MFE/MAE across the window seen so far
                hi = float(forward.max())
                lo = float(forward.min())
                mfe_pct = _pct_change(entry_close, hi)
                mae_pct = _pct_change(entry_close, lo)
                current_ret = _pct_change(entry_close, cmp_val)

            # Age in calendar days. Clamp to non-negative — if the run_utc
            # on recommendations.json predates the first archive day, we
            # can end up with a negative delta that reads confusingly.
            try:
                age_days = max(0, int((today_dt - first_seen_dt).days))
            except Exception:
                age_days = None

        status = _classify(
            {"entry_price": entry_price},
            hi, lo, cmp_val, target, stop, age_days, max_hold,
        )

        rows.append({
            "ticker":         t,
            "sector":         r.get("sector") or "—",
            "action":         r.get("recommendation"),
            "first_seen":     first_seen,
            "entry_price":    entry_price,
            "cmp":            cmp_val,
            "target":         target,
            "stop":           stop,
            "d1":             d1,
            "d3":             d3,
            "d5":             d5,
            "d10":            d10,
            "current_return": current_ret,
            "max_gain":       mfe_pct,
            "max_dd":         mae_pct,
            "age_days":       age_days,
            "expected_hold":  expected_hold,
            "max_hold":       max_hold,
            "score":          r.get("composite_decision_score"),
            "confidence":     r.get("confidence"),
            "intel_score":    ii.get("intelligence_score"),
            "status":         status,
        })

    return rows
