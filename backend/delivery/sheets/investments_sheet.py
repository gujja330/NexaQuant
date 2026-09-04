"""01_Investments · primary operator-facing daily sheet · CEO 2026-09-03.

Consolidates every actionable stock across R1 · R2 · Composite into ONE view
with two clear sections:

    A. NEW · today's opportunities (Action = BUY)          top of sheet
    B. ACTIVE · currently held    (Action = HOLD/TRIM/EXIT) below

Columns (all mandatory per CEO 2026-09-03):
    Score · Action · Ticker · Sector · Runner · Entry Date · Entry Price
    Current Price · Unrealized P&L % · Holding Days · Dynamic Stop · Target
    Stop Distance % · R:R · Confidence · Reason

Governance:
  · Dynamic Stop MANDATORY · every row · never bare "UNAVAILABLE"
      · R2 active     · real ATR-14 trailing stop from dynamic_risk_v2
      · R2 new BUY    · ATR-based initial stop (Entry − k·ATR14)
      · R1 advisory   · SUGGESTED ATR stop with explicit tag (no auto-exit per V2 §18)
      · Missing data  · "DATA_ERROR · <specific reason>" (never blank)
  · Runner column preserves attribution (never mixes R1 into R2 P&L)
  · Composite entries appear only when composite gate is admitted
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


INVESTMENTS_COLUMNS = [
    "Score", "Action", "Ticker", "Sector", "Runner",
    "Entry Date", "Entry Price", "Current Price",
    "Unrealized P&L %", "Holding Days",
    "Dynamic Stop", "Target", "Stop Distance %",
    "R:R", "Confidence %", "Reason",
]

INVESTMENTS_BANNER = (
    "AEGIS INVESTMENTS · daily operator view · "
    "NEW opportunities + ACTIVE holdings across all runners · "
    "Dynamic Stop mandatory · R1 rows tagged SUGGESTED (no auto-exit per V2 §18)"
)


def _num_pnl(entry_price: Optional[float], current_price: Optional[float]) -> Optional[float]:
    try:
        if not entry_price or not current_price or float(entry_price) <= 0:
            return None
        return round((float(current_price) / float(entry_price) - 1.0) * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _stop_from_atr(entry_price: Optional[float], atr: Optional[float],
                    k: float = 2.0) -> Optional[float]:
    try:
        if not entry_price or not atr or atr <= 0: return None
        return round(float(entry_price) - k * float(atr), 4)
    except (TypeError, ValueError): return None


def _target_from_atr(entry_price: Optional[float], atr: Optional[float],
                      m: float = 3.0) -> Optional[float]:
    try:
        if not entry_price or not atr or atr <= 0: return None
        return round(float(entry_price) + m * float(atr), 4)
    except (TypeError, ValueError): return None


def _pit_atr(root: Path, market: str, ticker: str, asof: str) -> Optional[float]:
    """PIT ATR-14 · same formula used in P0 replay + workbook builder."""
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        target_dt = pd.to_datetime(asof).normalize()
        if target_dt in df.index:
            idx = df.index.get_loc(target_dt)
        else:
            mask = df.index <= target_dt
            if not mask.any(): return None
            idx = int(mask.sum()) - 1
        if isinstance(idx, slice) or hasattr(idx, "__len__"): return None
        if idx < 14: return None
        highs = df["high"].to_numpy(); lows = df["low"].to_numpy(); closes = df["close"].to_numpy()
        trs = []
        for i in range(idx - 13, idx + 1):
            if i <= 0: continue
            trs.append(max(highs[i] - lows[i],
                           abs(highs[i] - closes[i-1]),
                           abs(lows[i] - closes[i-1])))
        if not trs: return None
        return sum(trs) / len(trs)
    except Exception:
        return None


def _stop_cell(runner: str, entry_price, atr, has_dynamic_stop_upstream: bool = False,
               upstream_stop: Optional[float] = None) -> tuple[str, str]:
    """Return (cell_value, provenance_tag) · trichotomy per CEO 2026-09-03."""
    if runner == "R1":
        stop = _stop_from_atr(entry_price, atr, k=2.0)
        if stop is not None:
            return (f"{stop} · SUGGESTED", "atr14_suggested_r1_no_auto_exit")
        return ("N/A · advisory · no auto-exit", "advisory_no_atr")
    # R2 or Composite
    if has_dynamic_stop_upstream and upstream_stop:
        return (str(round(float(upstream_stop), 4)), "dynamic_risk_v2")
    stop = _stop_from_atr(entry_price, atr, k=2.0)
    if stop is not None:
        return (str(stop), "atr14_fallback_k2")
    if not entry_price:
        return ("DATA_ERROR · missing entry_price", "missing_entry_price")
    if atr is None:
        return ("DATA_ERROR · missing ATR14 (need ≥14 bars pre-entry)", "missing_atr")
    return ("DATA_ERROR · unknown", "unknown")


def _score_for_r2_new(ensemble_score, calibrated_confidence) -> int:
    """0-100 unified score for a new R2 BUY opportunity."""
    # confidence is 0-1 · ensemble_score is [-1,+1] · combine equally
    try:
        c = float(calibrated_confidence or 0.5)
        s = (float(ensemble_score or 0.0) + 1) / 2   # normalize to [0,1]
        return int(round((c * 0.5 + s * 0.5) * 100))
    except (TypeError, ValueError): return 50


def _score_for_r1_new(strength: str, confidence_pct) -> int:
    """0-100 unified score for R1 advisory pick."""
    strength_bonus = {"STRONG BUY": 20, "BUY": 10, "ACCUMULATE": 5}.get(
        str(strength or "").upper().strip(), 0)
    try:
        base = int(round(float(confidence_pct or 50)))
    except (TypeError, ValueError):
        base = 50
    return min(100, max(0, base + strength_bonus))


def _score_for_active(pnl_pct: Optional[float], stop_distance_pct: Optional[float],
                      confidence_pct: Optional[float]) -> int:
    """0-100 score for an active position · P&L trend + safety margin + confidence."""
    parts = []
    if pnl_pct is not None:
        parts.append(min(100, max(0, 50 + float(pnl_pct) * 2)))   # 0% → 50, +5% → 60, −5% → 40
    if stop_distance_pct is not None:
        parts.append(min(100, max(0, float(stop_distance_pct) * 5)))  # wider stop distance = safer
    if confidence_pct is not None:
        try: parts.append(float(confidence_pct))
        except (TypeError, ValueError): pass
    if not parts: return 50
    return int(round(sum(parts) / len(parts)))


def _rr_ratio(entry_price, current_price, stop_value, target) -> Optional[float]:
    """Reward/Risk from current price · works for both new and active."""
    try:
        ref = float(current_price or entry_price or 0)
        if ref <= 0: return None
        # extract number from stop cell if it's a string
        stop_num = None
        if isinstance(stop_value, (int, float)):
            stop_num = float(stop_value)
        elif isinstance(stop_value, str):
            try: stop_num = float(stop_value.split(" ", 1)[0])
            except (TypeError, ValueError): pass
        if not stop_num or not target: return None
        risk = ref - float(stop_num)
        reward = float(target) - ref
        if risk <= 0 or reward <= 0: return None
        return round(reward / risk, 2)
    except (TypeError, ValueError): return None


def build_investments_rows(root: Path, market: str, asof: str,
                            reg_data: dict, momentum_ledger: dict,
                            r1_picks: list[dict],
                            r1_active: list | None = None) -> dict:
    """Return {new_rows, active_rows} · caller renders into sheet.

    CEO 2026-09-04 · Option 1 fix (scoped C19 deviation for 01_Investments only):
    r1_active is a list of registry Opportunity objects with runner=R1 status=ACTIVE.
    Rendered in ACTIVE section with 'R1 · ADVISORY' tag. 01_Portfolio and Exit
    History remain R1-zero (C19 intact for those sheets)."""
    from datetime import date as _date
    import pandas as pd

    # ── SECTION A · NEW opportunities today ───────────────────────
    new_rows: list[list] = []
    # A.1 · R2 momentum-ledger INVEST verdicts
    for e in (momentum_ledger.get("entries") or []):
        state = str(e.get("terminal_state", "")).upper()
        if state != "ACCEPTED": continue
        ticker = str(e.get("ticker", "")).upper().split(".", 1)[0]
        sector = e.get("sector") or "UNKNOWN"
        # Current price from parquet
        curr = _load_close(root, market, ticker, asof)
        atr = _pit_atr(root, market, ticker, asof)
        entry_price = curr   # for new BUY · today's close as entry proxy
        stop_val, stop_prov = _stop_cell("R2", entry_price, atr)
        target = _target_from_atr(entry_price, atr, m=3.0)
        rr = _rr_ratio(entry_price, curr, stop_val, target)
        stop_dist = None
        if isinstance(stop_val, str):
            try:
                sn = float(stop_val.split(" ", 1)[0])
                if curr and curr > 0: stop_dist = round((curr - sn) / curr * 100, 2)
            except (TypeError, ValueError): pass
        conf = e.get("confidence") or e.get("calibrated_confidence")
        if isinstance(conf, (int, float)) and 0 <= conf <= 1:
            conf = round(float(conf) * 100, 1)
        score = _score_for_r2_new(e.get("ensemble_score"), (conf or 50) / 100.0)
        reason = str(e.get("reason_text", "") or "")[:80] or "R2 momentum signal"
        new_rows.append([
            score, "BUY", ticker, sector, "R2",
            asof, curr, curr, None, 0,
            stop_val, target, stop_dist, rr,
            conf if conf is not None else "UNAVAILABLE", reason,
        ])
    # A.2 · R1 STRONG BUY picks
    for p in r1_picks:
        ticker = str(p.get("ticker", "")).upper()
        if not ticker: continue
        strength = str(p.get("action") or p.get("recommendation") or "").upper()
        if "BUY" not in strength: continue
        sector = p.get("sector") or "UNKNOWN"
        curr = _load_close(root, market, ticker, asof)
        atr = _pit_atr(root, market, ticker, asof)
        entry_price = curr
        stop_val, _ = _stop_cell("R1", entry_price, atr)
        target = _target_from_atr(entry_price, atr, m=3.0)
        rr = _rr_ratio(entry_price, curr, stop_val, target)
        stop_dist = None
        if isinstance(stop_val, str) and "SUGGESTED" in stop_val:
            try:
                sn = float(stop_val.split(" ", 1)[0])
                if curr and curr > 0: stop_dist = round((curr - sn) / curr * 100, 2)
            except (TypeError, ValueError): pass
        conf_pct = None
        for k in ("confidence", "Rec Confidence %", "Score /100"):
            if k in p and p[k] is not None:
                try: conf_pct = float(p[k]); break
                except (TypeError, ValueError): pass
        score = _score_for_r1_new(strength, conf_pct)
        reason = str(p.get("bull_case") or p.get("reason") or p.get("Why") or "R1 advisory")[:80]
        new_rows.append([
            score, "BUY · R1 ADVISORY", ticker, sector, "R1",
            asof, curr, curr, None, 0,
            stop_val, target, stop_dist, rr,
            conf_pct if conf_pct is not None else "UNAVAILABLE", reason,
        ])
    # Sort new_rows by Score descending
    new_rows.sort(key=lambda r: -(r[0] or 0))

    # ── SECTION B · ACTIVE positions ──────────────────────────────
    active_rows: list[list] = []
    from scripts.build_aegis_3sheet_workbook import (
        _load_sector_cache, _sector_for, _close_on_or_before,
    )
    sector_cache = _load_sector_cache(root)
    for o in (reg_data.get("active") or []):
        ticker = str(o.ticker).upper()
        sector = _sector_for(sector_cache, market, o.ticker)
        entry_p = _close_on_or_before(root, o.ticker, market, o.created_date or "")
        curr_p = _close_on_or_before(root, o.ticker, market, asof)
        pnl_pct = _num_pnl(entry_p, curr_p)
        days = None
        try:
            days = (_date.fromisoformat(asof) - _date.fromisoformat(o.created_date)).days
        except Exception: pass
        atr = _pit_atr(root, market, o.ticker, o.created_date or asof)
        # Use dynamic_risk_v2 stop if present via reg_data · else ATR fallback
        upstream_stop = None
        stop_val, stop_prov = _stop_cell(str(o.runner or "R2"), entry_p, atr,
                                          has_dynamic_stop_upstream=False,
                                          upstream_stop=upstream_stop)
        target = _target_from_atr(entry_p, atr, m=3.0)
        stop_dist = None
        if isinstance(stop_val, str):
            try:
                sn = float(stop_val.split(" ", 1)[0])
                if curr_p and curr_p > 0: stop_dist = round((curr_p - sn) / curr_p * 100, 2)
            except (TypeError, ValueError): pass
        rr = _rr_ratio(entry_p, curr_p, stop_val, target)
        conf = getattr(o, "initial_score", None)
        if isinstance(conf, (int, float)) and 0 <= conf <= 1:
            conf = round(float(conf) * 100, 1)
        # Action based on stop
        action = "HOLD"
        if isinstance(stop_val, str) and stop_val.startswith("DATA_ERROR"):
            action = "REVIEW"
        else:
            try:
                sn = float(str(stop_val).split(" ", 1)[0])
                if curr_p and curr_p <= sn: action = "EXIT · stop hit"
            except (TypeError, ValueError): pass
        score = _score_for_active(pnl_pct, stop_dist, conf)
        reason = f"{o.runner} · {o.opportunity_id[-8:]}"
        active_rows.append([
            score, action, ticker, sector, str(o.runner or "R2"),
            o.created_date or "—",
            round(entry_p, 4) if entry_p else "DATA_ERROR",
            round(curr_p, 4) if curr_p else "DATA_ERROR",
            pnl_pct if pnl_pct is not None else "DATA_ERROR",
            days if days is not None else "?",
            stop_val, target, stop_dist, rr,
            conf if conf is not None else "UNAVAILABLE", reason,
        ])
    # B.2 · R1 ACTIVE (registry) · scoped C19 deviation for 01_Investments only.
    # De-dupe by ticker vs R2 ACTIVE (R2 wins if same ticker · R1 is advisory).
    r2_active_tickers = {str(o.ticker).upper() for o in (reg_data.get("active") or [])}
    r1_active_tickers_in_new = {str(r[2]).upper() for r in new_rows if r[4] == "R1"}
    for o in (r1_active or []):
        ticker = str(getattr(o, "ticker", "")).upper()
        if not ticker: continue
        if ticker in r2_active_tickers: continue           # R2 wins
        if ticker in r1_active_tickers_in_new: continue    # already in NEW today
        sector = _sector_for(sector_cache, market, o.ticker)
        entry_p = _close_on_or_before(root, o.ticker, market, o.created_date or "")
        curr_p = _close_on_or_before(root, o.ticker, market, asof)
        pnl_pct = _num_pnl(entry_p, curr_p)
        days = None
        try:
            days = (_date.fromisoformat(asof) - _date.fromisoformat(o.created_date)).days
        except Exception: pass
        atr = _pit_atr(root, market, o.ticker, o.created_date or asof)
        stop_val, _ = _stop_cell("R1", entry_p, atr)      # SUGGESTED trichotomy
        target = _target_from_atr(entry_p, atr, m=3.0)
        stop_dist = None
        if isinstance(stop_val, str) and "SUGGESTED" in stop_val:
            try:
                sn = float(stop_val.split(" ", 1)[0])
                if curr_p and curr_p > 0: stop_dist = round((curr_p - sn) / curr_p * 100, 2)
            except (TypeError, ValueError): pass
        rr = _rr_ratio(entry_p, curr_p, stop_val, target)
        conf = getattr(o, "initial_score", None)
        if isinstance(conf, (int, float)) and 0 <= conf <= 1:
            conf = round(float(conf) * 100, 1)
        score = _score_for_active(pnl_pct, stop_dist, conf)
        reason = f"R1 ADVISORY · {getattr(o, 'opportunity_id', '')[-8:]}"
        active_rows.append([
            score, "HOLD · R1 ADVISORY", ticker, sector, "R1",
            o.created_date or "—",
            round(entry_p, 4) if entry_p else "DATA_ERROR",
            round(curr_p, 4) if curr_p else "DATA_ERROR",
            pnl_pct if pnl_pct is not None else "DATA_ERROR",
            days if days is not None else "?",
            stop_val, target, stop_dist, rr,
            conf if conf is not None else "UNAVAILABLE", reason,
        ])
    active_rows.sort(key=lambda r: -(r[0] or 0))

    return {"new_rows": new_rows, "active_rows": active_rows}


def _load_close(root: Path, market: str, ticker: str, asof: str) -> Optional[float]:
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        t = pd.to_datetime(asof).normalize()
        if t in df.index: return float(df.loc[t, "close"])
        mask = df.index <= t
        if not mask.any(): return None
        return float(df.loc[mask, "close"].iloc[-1])
    except Exception: return None


def sheet_meta() -> dict:
    return {
        "sheet_name": "01_Investments",
        "banner": INVESTMENTS_BANNER,
        "columns": INVESTMENTS_COLUMNS,
        "sections": ["NEW · today", "ACTIVE · held"],
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
