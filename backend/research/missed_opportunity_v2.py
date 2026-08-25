# backend/research/missed_opportunity_v2.py
"""AEGIS · Sprint M.1 · Missed Opportunity Analysis (successful rejection
vs missed winner).

CEO directive 2026-08-25: "Every day: Universe → AEGIS selected →
AEGIS rejected · then look forward · Rejected + up 8% = MISSED WINNER ·
Rejected + down 7% = SUCCESSFUL REJECTION".

Extends win_discovery with a 4-category classifier:

  MISSED_WINNER      · not recommended · went UP > 5%   in 5 days
  MISSED_STRONG_WIN  · not recommended · went UP > 15%  in 20 days
  SUCCESSFUL_REJECT  · not recommended · went DOWN < -5% in 20 days
  IGNORED_NEUTRAL    · not recommended · flat (-5% to +5% at 20d)

Aggregates by sector + cap + rejection-reason to answer:
  "Are we too conservative (missing winners)?"
  or
  "Are we correctly conservative (avoiding losers)?"

CEO KPI: successful_reject_rate = SUCCESSFUL_REJECT / (MISSED + REJECT)
Higher = engine is correctly filtering.

Emits reports/research/rejection_analysis_{market}.json.
Constitutional invariant · READ ONLY.
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.missed_opportunity_v2.v1.20260825"


@dataclass
class RejectionOutcome:
    ticker: str
    market: str
    sector: str
    return_5d_pct: Optional[float]
    return_20d_pct: Optional[float]
    category: str          # MISSED_WINNER / MISSED_STRONG_WIN / SUCCESSFUL_REJECT / IGNORED_NEUTRAL
    reason: str = ""       # why this was rejected (best-effort)


@dataclass
class RejectionReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    lookback_days: int = 30
    n_universe: int = 0
    n_recommended: int = 0
    n_rejected: int = 0
    n_missed_winner: int = 0
    n_missed_strong_win: int = 0
    n_successful_reject: int = 0
    n_ignored_neutral: int = 0
    successful_reject_rate_pct: float = 0.0
    missed_winner_rate_pct: float = 0.0
    top_missed_winners: list = field(default_factory=list)
    top_successful_rejects: list = field(default_factory=list)
    sector_breakdown: list = field(default_factory=list)


def _series(root: Path, ticker: str, market: str):
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


def _return_over_last(series, days: int):
    if series is None or len(series) < days + 1: return None
    end_p = float(series.iloc[-1])
    start_p = float(series.iloc[-(days + 1)])
    if start_p <= 0: return None
    return round((end_p - start_p) / start_p * 100, 2)


def _universe(root: Path, market: str) -> list:
    if market.lower() == "usa":
        pat = str(root / "usa" / "data" / "raw" / "us" / "*_D1.parquet")
    else:
        pat = str(root / "data" / "raw" / "india" / "*_D1.parquet")
    return sorted(Path(f).stem.replace("_D1","") for f in glob.glob(pat))


def _was_recommended(root: Path, ticker: str, market: str,
                     since: str) -> bool:
    try:
        from backend.research import opportunity_registry as _oreg
        reg = _oreg.load_all(root)
        for opps in reg.values():
            for o in opps:
                if o.market.lower() != market.lower(): continue
                if o.ticker.upper() != ticker.upper(): continue
                if str(o.created_date or "") >= since: return True
        return False
    except Exception:
        return False


def _sector_for(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / "sector_cache.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get(market.lower(), {}).get(ticker.upper()) or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _classify(r5: Optional[float], r20: Optional[float]) -> str:
    """Deterministic ladder · uses whichever horizon has data."""
    _r = r20 if r20 is not None else r5
    if _r is None: return "IGNORED_NEUTRAL"
    if r20 is not None and r20 > 15: return "MISSED_STRONG_WIN"
    if r5 is not None and r5 > 5: return "MISSED_WINNER"
    if r20 is not None and r20 > 5: return "MISSED_WINNER"
    if r20 is not None and r20 < -5: return "SUCCESSFUL_REJECT"
    if r5 is not None and r5 < -7: return "SUCCESSFUL_REJECT"
    return "IGNORED_NEUTRAL"


def _rejection_reason(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / f"investability_{market.lower()}.json"
    if not p.exists(): return "not in investability sample"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in (d.get("results") or []):
            if str(r.get("ticker","")).upper() == ticker.upper():
                _v = str(r.get("verdict","")).upper()
                if "AVOID" in _v: return f"quality-gate: {r.get('verdict','')}"
                if "MARGINAL" in _v: return f"marginal quality: {r.get('verdict','')}"
                _sc = r.get("score", 0)
                if isinstance(_sc, (int, float)):
                    return f"score {_sc:.1f} below top-pick bar"
                return "watchlist but not top pick"
        return "not in current sample"
    except Exception:
        return "rejection reason unknown"


def compute(root: Path, market: str, lookback_days: int = 30) -> RejectionReport:
    universe = _universe(root, market)
    rep = RejectionReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        lookback_days=lookback_days,
    )
    rep.n_universe = len(universe)
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    rejections: list = []
    n_rec = 0
    for tk in universe:
        was_rec = _was_recommended(root, tk, market, since)
        if was_rec:
            n_rec += 1
            continue
        s = _series(root, tk, market)
        if s is None: continue
        r5 = _return_over_last(s, 5)
        r20 = _return_over_last(s, lookback_days)
        cat = _classify(r5, r20)
        _sec = _sector_for(root, tk, market)
        _rsn = _rejection_reason(root, tk, market)
        rejections.append(RejectionOutcome(
            ticker=tk.upper(), market=market.lower(),
            sector=_sec, return_5d_pct=r5, return_20d_pct=r20,
            category=cat, reason=_rsn,
        ))
    rep.n_recommended = n_rec
    rep.n_rejected = len(rejections)
    rep.n_missed_winner = sum(1 for r in rejections if r.category == "MISSED_WINNER")
    rep.n_missed_strong_win = sum(1 for r in rejections if r.category == "MISSED_STRONG_WIN")
    rep.n_successful_reject = sum(1 for r in rejections if r.category == "SUCCESSFUL_REJECT")
    rep.n_ignored_neutral = sum(1 for r in rejections if r.category == "IGNORED_NEUTRAL")
    _decisive = rep.n_missed_winner + rep.n_missed_strong_win + rep.n_successful_reject
    if _decisive > 0:
        rep.successful_reject_rate_pct = round(
            rep.n_successful_reject / _decisive * 100, 1)
        rep.missed_winner_rate_pct = round(
            (rep.n_missed_winner + rep.n_missed_strong_win) / _decisive * 100, 1)
    # Top lists
    missed = [r for r in rejections
              if r.category in ("MISSED_STRONG_WIN", "MISSED_WINNER")]
    missed.sort(key=lambda x: -(x.return_20d_pct or x.return_5d_pct or 0))
    rep.top_missed_winners = [asdict(r) for r in missed[:20]]
    reject = sorted([r for r in rejections if r.category == "SUCCESSFUL_REJECT"],
                    key=lambda x: (x.return_20d_pct or 0))
    rep.top_successful_rejects = [asdict(r) for r in reject[:20]]
    # Sector breakdown
    from collections import defaultdict
    by_sec_missed: dict = defaultdict(int)
    by_sec_rejected: dict = defaultdict(int)
    for r in rejections:
        if r.category in ("MISSED_WINNER", "MISSED_STRONG_WIN"):
            by_sec_missed[r.sector] += 1
        elif r.category == "SUCCESSFUL_REJECT":
            by_sec_rejected[r.sector] += 1
    all_secs = set(by_sec_missed) | set(by_sec_rejected)
    for sec in sorted(all_secs, key=lambda s: -by_sec_missed.get(s, 0)):
        rep.sector_breakdown.append({
            "sector": sec,
            "n_missed": by_sec_missed.get(sec, 0),
            "n_successfully_rejected": by_sec_rejected.get(sec, 0),
        })
    return rep


def emit(root: Path, rep: RejectionReport) -> Path:
    p = (root / "reports" / "research"
         / f"rejection_analysis_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: RejectionReport) -> str:
    return (f"rejection_analysis · {rep.n_universe} universe · "
            f"recommended {rep.n_recommended} · rejected {rep.n_rejected} · "
            f"MISSED {rep.n_missed_winner + rep.n_missed_strong_win} · "
            f"SUCCESSFUL_REJECT {rep.n_successful_reject} · "
            f"reject_rate {rep.successful_reject_rate_pct}%")
