# backend/research/loss_avoidance_guard.py
"""AEGIS · Loss Avoidance Guard · forward-looking for CURRENT losers.

CEO directive 2026-08-25: "can u explore and build and push into testing
to see for future data and active portfolio which are in losses".

Companion to loss_attribution_v2 (post-mortem). This engine looks at
every ACTIVE position that is currently in loss and assesses whether to:

  HOLD           · loss is within tolerance and trend still intact
  TIGHTEN_STOP   · trend showing damage · shrink stop to lock in less loss
  EXIT           · multiple warning signs · get out today
  REVIEW         · borderline · operator judgment call

Signals used (pure · no AI dependency · deterministic):

  Technicals (from parquet):
    · price vs 20-day MA
    · price vs 50-day MA
    · 5-day return (short-term momentum)
    · 20-day return (medium-term momentum)
    · distance from stop (how much room left)

  Fundamentals proxy (from investability_{market}.json):
    · current quality band (QUALITY / OK / MARGINAL / AVOID)
    · quality trajectory · comparing to entry quality where available

  Sector context (from sector_context / sector_rotation JSONs):
    · is sector rotating out?
    · is sector a laggard right now?

Verdict rules · deterministic ladder:
  1. If price < stop → EXIT (stop was hit intraday, protect)
  2. If quality dropped from QUALITY/OK to AVOID → EXIT
  3. If price < MA20 AND price < MA50 AND sector rotating out → EXIT
  4. If price < MA20 AND 5-day return < -3% → TIGHTEN_STOP
  5. If quality band = MARGINAL AND pnl < -5% → TIGHTEN_STOP
  6. If pnl < -3% AND days_held < 10 → REVIEW (early damage · unusual)
  7. Else HOLD

Non-blocking · emits reports/context/loss_avoidance_{market}.json for
operator review · never mutates recommendations automatically.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.loss_avoidance.v1.20260825"


@dataclass
class LoserVerdict:
    ticker: str
    market: str
    entry_date: str
    days_held: int
    entry_price: float
    current_price: float
    stop_price: Optional[float]
    pnl_pct: float
    ma20: Optional[float]
    ma50: Optional[float]
    return_5d: Optional[float]
    return_20d: Optional[float]
    quality_band: str
    sector: str
    sector_status: str          # LEADER / LAGGARD / NEUTRAL / UNKNOWN
    verdict: str                # HOLD / TIGHTEN_STOP / EXIT / REVIEW
    signals_fired: list = field(default_factory=list)
    recommendation: str = ""


@dataclass
class AvoidanceReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_active: int = 0
    n_losers: int = 0
    n_hold: int = 0
    n_tighten: int = 0
    n_exit: int = 0
    n_review: int = 0
    verdicts: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Signal computation
# ─────────────────────────────────────────────────────────────────
def _parquet_series(root: Path, ticker: str, market: str):
    if market.lower() == "usa":
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "usa" / "data" / "raw" / "us" / f"{tk}_D1.parquet"
    else:
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "data" / "raw" / "india" / f"{tk}_D1.parquet"
    if not p.exists(): return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df[col].astype(float)
    except Exception:
        return None


def _tech_signals(root: Path, ticker: str, market: str):
    """Compute MA20 / MA50 / 5d return / 20d return for the ticker."""
    s = _parquet_series(root, ticker, market)
    if s is None or len(s) < 25:
        return None, None, None, None, None
    last = float(s.iloc[-1])
    ma20 = float(s.tail(20).mean()) if len(s) >= 20 else None
    ma50 = float(s.tail(50).mean()) if len(s) >= 50 else None
    ret5 = None
    ret20 = None
    if len(s) >= 6:
        p5 = float(s.iloc[-6])
        ret5 = round((last - p5) / p5 * 100, 2) if p5 else None
    if len(s) >= 21:
        p20 = float(s.iloc[-21])
        ret20 = round((last - p20) / p20 * 100, 2) if p20 else None
    return last, ma20, ma50, ret5, ret20


def _quality_band_for(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / f"investability_{market.lower()}.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        tk = str(ticker).upper()
        for r in (d.get("results") or []):
            if str(r.get("ticker") or "").upper() == tk:
                _v = str(r.get("verdict") or "").upper()
                if "QUALITY" in _v: return "QUALITY"
                if "OK" in _v:       return "OK"
                if "MARGINAL" in _v: return "MARGINAL"
                if "AVOID" in _v:    return "AVOID"
                return _v or "UNKNOWN"
    except Exception:
        pass
    return "UNKNOWN"


def _sector_status(root: Path, ticker: str, market: str) -> str:
    """LEADER / LAGGARD / NEUTRAL from sector_context."""
    p = root / "reports" / "context" / f"sector_context_{market.lower()}.json"
    if not p.exists():
        p = root / "reports" / "sector_context.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        # Best-effort · map ticker → sector → status
        sec = _sector_for(root, ticker, market)
        if sec == "UNKNOWN": return "UNKNOWN"
        secs = d.get("sectors") or d.get("data") or {}
        if isinstance(secs, dict):
            entry = secs.get(sec) or {}
            if entry.get("is_leader"):  return "LEADER"
            if entry.get("is_laggard"): return "LAGGARD"
            return "NEUTRAL"
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _sector_for(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / "sector_cache.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        bucket = d.get(market.lower(), {})
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        return bucket.get(tk) or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


# ─────────────────────────────────────────────────────────────────
# Verdict ladder · deterministic
# ─────────────────────────────────────────────────────────────────
def assess_loser(
    *, ticker: str, market: str, entry_date: str, days_held: int,
    entry_price: float, current_price: float, stop_price: Optional[float],
    ma20: Optional[float], ma50: Optional[float],
    return_5d: Optional[float], return_20d: Optional[float],
    quality_band: str, sector: str, sector_status: str,
) -> LoserVerdict:
    pnl = ((current_price - entry_price) / entry_price * 100
           if entry_price > 0 else 0.0)
    signals = []
    verdict = "HOLD"

    # 1. Stop breached · immediate EXIT
    if isinstance(stop_price, (int, float)) and stop_price > 0 \
       and current_price <= stop_price:
        signals.append(f"price ₹{current_price:.2f} ≤ stop ₹{stop_price:.2f}")
        verdict = "EXIT"

    # 2. Quality collapsed to AVOID · EXIT
    if quality_band == "AVOID" and verdict == "HOLD":
        signals.append("investability degraded to AVOID")
        verdict = "EXIT"

    # 3. Below both MAs + sector rotating out · EXIT
    if (verdict == "HOLD" and ma20 and ma50
        and current_price < ma20 and current_price < ma50
        and sector_status == "LAGGARD"):
        signals.append("price < MA20 < MA50 · sector LAGGARD")
        verdict = "EXIT"

    # 4. Below MA20 + short-term momentum bad · TIGHTEN_STOP
    if (verdict == "HOLD" and ma20 and current_price < ma20
        and return_5d is not None and return_5d < -3):
        signals.append(f"price < MA20 · 5d return {return_5d:+.1f}%")
        verdict = "TIGHTEN_STOP"

    # 5. Marginal quality + real loss · TIGHTEN_STOP
    if (verdict == "HOLD" and quality_band == "MARGINAL"
        and pnl < -5):
        signals.append(f"MARGINAL quality · pnl {pnl:+.1f}%")
        verdict = "TIGHTEN_STOP"

    # 6. Early damage · REVIEW
    if (verdict == "HOLD" and pnl < -3 and days_held < 10):
        signals.append(f"early damage · pnl {pnl:+.1f}% in {days_held}d")
        verdict = "REVIEW"

    rec = {
        "EXIT":         "sell today · signals too strong to hold",
        "TIGHTEN_STOP": "raise stop to protect · give one more day",
        "REVIEW":       "look at chart + news · decide today",
        "HOLD":         "loss within normal band · thesis intact",
    }.get(verdict, "")

    return LoserVerdict(
        ticker=ticker.upper(), market=market.lower(),
        entry_date=entry_date, days_held=days_held,
        entry_price=round(entry_price, 2),
        current_price=round(current_price, 2),
        stop_price=(round(stop_price, 2)
                    if isinstance(stop_price, (int, float)) else None),
        pnl_pct=round(pnl, 2),
        ma20=(round(ma20, 2) if ma20 else None),
        ma50=(round(ma50, 2) if ma50 else None),
        return_5d=return_5d, return_20d=return_20d,
        quality_band=quality_band, sector=sector,
        sector_status=sector_status,
        verdict=verdict, signals_fired=signals, recommendation=rec,
    )


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str,
            active_positions: list) -> AvoidanceReport:
    """`active_positions` is a list of dicts:
       {ticker, entry_date, entry_price, current_price, stop_price}"""
    rep = AvoidanceReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    rep.n_active = len(active_positions)
    for pos in active_positions:
        tk = pos.get("ticker")
        entry = pos.get("entry_price")
        curr = pos.get("current_price")
        if not (tk and isinstance(entry, (int, float)) and entry > 0
                and isinstance(curr, (int, float)) and curr > 0):
            continue
        pnl = (curr - entry) / entry * 100
        if pnl >= 0: continue     # skip winners
        rep.n_losers += 1
        _, ma20, ma50, r5, r20 = _tech_signals(root, tk, market)
        qb = _quality_band_for(root, tk, market)
        sec = _sector_for(root, tk, market)
        ss = _sector_status(root, tk, market)
        try:
            _dh = (date.today() - date.fromisoformat(
                str(pos.get("entry_date", ""))[:10])).days
        except Exception:
            _dh = pos.get("days_held", 0) or 0
        v = assess_loser(
            ticker=tk, market=market,
            entry_date=str(pos.get("entry_date", ""))[:10],
            days_held=_dh,
            entry_price=entry, current_price=curr,
            stop_price=pos.get("stop_price"),
            ma20=ma20, ma50=ma50, return_5d=r5, return_20d=r20,
            quality_band=qb, sector=sec, sector_status=ss,
        )
        rep.verdicts.append(asdict(v))
        if v.verdict == "HOLD":         rep.n_hold += 1
        elif v.verdict == "TIGHTEN_STOP": rep.n_tighten += 1
        elif v.verdict == "EXIT":       rep.n_exit += 1
        elif v.verdict == "REVIEW":     rep.n_review += 1
    return rep


def emit(root: Path, report: AvoidanceReport) -> Path:
    p = (root / "reports" / "context"
         / f"loss_avoidance_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: AvoidanceReport) -> str:
    return (f"loss_avoidance · {rep.n_losers} losers · "
            f"EXIT {rep.n_exit} · TIGHTEN {rep.n_tighten} · "
            f"REVIEW {rep.n_review} · HOLD {rep.n_hold}")
