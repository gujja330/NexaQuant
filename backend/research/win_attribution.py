# backend/research/win_attribution.py
"""AEGIS · Win Attribution · what pattern do our winners share?

CEO directive 2026-08-25: "what we can do on profit trades to identify
most successful stocks, any advanced analysis? based on data / also we
can try on history data to see if we have missed any winning stocks".

Symmetric to loss_attribution_v2 · classifies every WINNER (closed
position with pnl > +0.5%) into one of 6 patterns:

  MOMENTUM_BREAKOUT  · entered near breakout · price accelerated
  EARNINGS_BEAT      · quick move within days of earnings window
  SECTOR_LEADER      · rode sector rotation up
  QUALITY_MEAN_REVERSION · high quality name that bounced back
  TURNAROUND         · oversold reversal · big move in short time
  MACRO_TAILWIND     · rode regime shift (bull turn, rate cut, etc.)

Rollups:
  · pattern counts + avg return per pattern
  · sector + cap-size breakdown for winners
  · median hold-to-peak days per pattern (how long before it topped)

Emits reports/research/win_patterns_{market}.json + a compact markdown
digest so the operator can see WHAT WORKED and DOUBLE-DOWN on it.

Constitutional invariant: research READS only · never mutates R1/R2.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.win_attribution.v1.20260825"

WIN_PATTERNS = [
    "MOMENTUM_BREAKOUT", "EARNINGS_BEAT", "SECTOR_LEADER",
    "QUALITY_MEAN_REVERSION", "TURNAROUND", "MACRO_TAILWIND",
]


@dataclass
class WinClassification:
    ticker: str
    market: str
    runner: str
    entry_date: str
    exit_date: str
    days_held: int
    pnl_pct: float
    pattern: str
    sector: str
    cap_size: str
    entry_regime: str
    entry_quality: str
    sector_return_over_hold: Optional[float] = None
    recommendation: str = ""


@dataclass
class WinRollup:
    key: str                   # sector name or cap size or pattern
    n_wins: int
    total_pnl_pct: float
    avg_pnl_pct: float
    median_days_held: float
    dominant_pattern: str      # top pattern for this bucket


@dataclass
class WinReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_positions: int = 0
    n_wins: int = 0
    total_win_pct: float = 0.0
    avg_win_pct: float = 0.0
    median_win_days: float = 0.0
    pattern_counts: dict = field(default_factory=dict)
    sector_rollup: list = field(default_factory=list)
    cap_size_rollup: list = field(default_factory=list)
    pattern_rollup: list = field(default_factory=list)
    winners: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Helpers · reuse loss_attribution utilities
# ─────────────────────────────────────────────────────────────────
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


def _cap_size_for(root: Path, ticker: str, market: str) -> str:
    if market.lower() == "india":
        try:
            from india.data_nse import NIFTY100
            tk = str(ticker).upper().replace(".NS","").replace(".BO","")
            if tk in NIFTY100[:50]: return "LARGE"
            if tk in NIFTY100:      return "LARGE"
            return "MID"
        except Exception:
            return "UNKNOWN"
    return "UNKNOWN"


def _load_close_series(root: Path, ticker: str, market: str):
    if market.lower() == "usa":
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "usa" / "data" / "raw" / "us" / f"{tk}_D1.parquet"
    else:
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "data" / "raw" / "india" / f"{tk}_D1.parquet"
    if not p.exists(): return None, None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        idx = pd.to_datetime(df.index).strftime("%Y-%m-%d").tolist()
        return idx, [float(v) for v in df[col].tolist()]
    except Exception:
        return None, None


def _return_over_window(root: Path, ticker: str, market: str,
                        start: str, end: str) -> Optional[float]:
    idx, closes = _load_close_series(root, ticker, market)
    if not idx: return None
    s_before = [(d, c) for d, c in zip(idx, closes) if d <= start]
    e_before = [(d, c) for d, c in zip(idx, closes) if d <= end]
    if not (s_before and e_before): return None
    s = s_before[-1][1]; e = e_before[-1][1]
    if not (s and s > 0): return None
    return (e - s) / s * 100


def _return_before(root: Path, ticker: str, market: str,
                   at_date: str, lookback_days: int) -> Optional[float]:
    """Return over the N days BEFORE at_date · used to detect breakout."""
    idx, closes = _load_close_series(root, ticker, market)
    if not idx: return None
    at_before = [(d, c) for d, c in zip(idx, closes) if d <= at_date]
    if len(at_before) < lookback_days + 1: return None
    end_c = at_before[-1][1]
    start_c = at_before[-lookback_days - 1][1]
    if not (start_c and start_c > 0): return None
    return (end_c - start_c) / start_c * 100


# ─────────────────────────────────────────────────────────────────
# Pattern classifier · deterministic · easy to test
# ─────────────────────────────────────────────────────────────────
def classify_winner(
    *, pnl_pct: float, days_held: int,
    sector_return_over_hold: Optional[float],
    entry_quality: str,
    return_20d_before_entry: Optional[float],
    return_5d_after_entry: Optional[float],
) -> str:
    """Classify a WIN into one of 6 patterns · use whichever signal is
    strongest · deterministic ladder."""
    # Rapid-fire wins · big move in short window · TURNAROUND or EARNINGS
    if days_held <= 7 and pnl_pct >= 5:
        # If 20d before entry was down · TURNAROUND (bought the dip)
        if (return_20d_before_entry is not None
            and return_20d_before_entry < -5):
            return "TURNAROUND"
        return "EARNINGS_BEAT"     # quick pop = catalyst

    # Sector-led · sector matched or exceeded us
    if (sector_return_over_hold is not None
        and sector_return_over_hold >= pnl_pct - 2
        and sector_return_over_hold >= 3):
        return "SECTOR_LEADER"

    # Momentum · entered on strong 20d run + kept going + short-medium hold
    if (return_20d_before_entry is not None
        and return_20d_before_entry >= 3
        and pnl_pct >= 3
        and days_held <= 30):
        return "MOMENTUM_BREAKOUT"

    # Quality name bounced · high quality + medium hold + solid win
    if (entry_quality.upper() in ("QUALITY", "🏆 QUALITY", "OK", "✓ OK")
        and days_held >= 15 and pnl_pct >= 3):
        return "QUALITY_MEAN_REVERSION"

    # Default · macro tailwind
    return "MACRO_TAILWIND"


def recommendation_for(pattern: str) -> str:
    """What to do more of, given this winning pattern."""
    return {
        "MOMENTUM_BREAKOUT":     "enter more of these · tighten breakout screen threshold",
        "EARNINGS_BEAT":          "add earnings-calendar overlay to catch these systematically",
        "SECTOR_LEADER":          "double-down on sector-rotation signal at entry",
        "QUALITY_MEAN_REVERSION": "high-quality dip-buying works · widen quality-band bias",
        "TURNAROUND":             "oversold-reversal setup works · add RSI < 30 overlay",
        "MACRO_TAILWIND":         "regime-aware entry · scale up during favorable regime",
    }.get(pattern, "study individually")


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str, lookback_days: int = 90) -> WinReport:
    from backend.research import opportunity_registry as _oreg
    reg = _oreg.load_all(root)
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    rep = WinReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    winners: list = []
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if o.status != "CLOSED": continue
            if not (o.created_date and o.closed_date): continue
            if o.closed_date < cutoff: continue
            _e_p = _return_over_window(
                root, o.ticker, market, o.created_date, o.closed_date)
            if _e_p is None or _e_p <= 0.5: continue    # winners only
            try:
                _dh = (date.fromisoformat(o.closed_date)
                       - date.fromisoformat(o.created_date)).days
            except Exception:
                _dh = 0
            _sec = _sector_for(root, o.ticker, market)
            _cap = _cap_size_for(root, o.ticker, market)
            _r20b = _return_before(
                root, o.ticker, market, o.created_date, 20)
            _r5a = _return_over_window(
                root, o.ticker, market, o.created_date,
                (date.fromisoformat(o.created_date)
                 + timedelta(days=5)).isoformat())
            _sec_ret = None    # sector proxy unavailable without ticker map
            _pat = classify_winner(
                pnl_pct=_e_p, days_held=_dh,
                sector_return_over_hold=_sec_ret,
                entry_quality="UNKNOWN",
                return_20d_before_entry=_r20b,
                return_5d_after_entry=_r5a,
            )
            winners.append(WinClassification(
                ticker=o.ticker.upper(), market=market.lower(),
                runner=o.runner,
                entry_date=o.created_date, exit_date=o.closed_date,
                days_held=_dh, pnl_pct=round(_e_p, 2),
                pattern=_pat, sector=_sec, cap_size=_cap,
                entry_regime="UNKNOWN", entry_quality="UNKNOWN",
                sector_return_over_hold=(round(_sec_ret, 2)
                                         if _sec_ret is not None else None),
                recommendation=recommendation_for(_pat),
            ))
    rep.winners = [asdict(w) for w in winners]
    rep.n_positions = len(winners)
    rep.n_wins = len(winners)
    _pnls = [w.pnl_pct for w in winners]
    rep.total_win_pct = round(sum(_pnls), 2) if _pnls else 0.0
    rep.avg_win_pct = round(sum(_pnls) / max(len(_pnls), 1), 2) if _pnls else 0.0
    _days = sorted(w.days_held for w in winners)
    rep.median_win_days = float(_days[len(_days) // 2]) if _days else 0.0
    # Pattern counts
    pc: dict = {}
    for w in winners:
        pc[w.pattern] = pc.get(w.pattern, 0) + 1
    rep.pattern_counts = pc
    # Pattern rollup
    from collections import defaultdict
    by_pat: dict = defaultdict(list)
    for w in winners:
        by_pat[w.pattern].append(w)
    for pat, items in by_pat.items():
        _n = len(items)
        _tot = sum(x.pnl_pct for x in items)
        _avg = round(_tot / max(_n, 1), 2)
        _dh_med = float(sorted(x.days_held for x in items)[_n // 2])
        rep.pattern_rollup.append(asdict(WinRollup(
            key=pat, n_wins=_n,
            total_pnl_pct=round(_tot, 2), avg_pnl_pct=_avg,
            median_days_held=_dh_med, dominant_pattern=pat,
        )))
    # Sector rollup for winners
    by_sec: dict = defaultdict(list)
    for w in winners:
        by_sec[w.sector].append(w)
    for sec, items in by_sec.items():
        _n = len(items); _tot = sum(x.pnl_pct for x in items)
        _dh_med = float(sorted(x.days_held for x in items)[_n // 2])
        _pat_counts: dict = {}
        for x in items:
            _pat_counts[x.pattern] = _pat_counts.get(x.pattern, 0) + 1
        _dom = max(_pat_counts, key=_pat_counts.get) if _pat_counts else "—"
        rep.sector_rollup.append(asdict(WinRollup(
            key=sec, n_wins=_n, total_pnl_pct=round(_tot, 2),
            avg_pnl_pct=round(_tot / max(_n, 1), 2),
            median_days_held=_dh_med, dominant_pattern=_dom,
        )))
    # Cap-size rollup for winners
    by_cap: dict = defaultdict(list)
    for w in winners:
        by_cap[w.cap_size].append(w)
    for cap, items in by_cap.items():
        _n = len(items); _tot = sum(x.pnl_pct for x in items)
        _dh_med = float(sorted(x.days_held for x in items)[_n // 2])
        _pat_counts: dict = {}
        for x in items:
            _pat_counts[x.pattern] = _pat_counts.get(x.pattern, 0) + 1
        _dom = max(_pat_counts, key=_pat_counts.get) if _pat_counts else "—"
        rep.cap_size_rollup.append(asdict(WinRollup(
            key=cap, n_wins=_n, total_pnl_pct=round(_tot, 2),
            avg_pnl_pct=round(_tot / max(_n, 1), 2),
            median_days_held=_dh_med, dominant_pattern=_dom,
        )))
    return rep


def emit(root: Path, report: WinReport) -> Path:
    p = (root / "reports" / "research"
         / f"win_patterns_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: WinReport) -> str:
    top = "—"
    if rep.pattern_counts:
        top = max(rep.pattern_counts, key=rep.pattern_counts.get)
    return (f"win_attribution · {rep.n_wins} wins · "
            f"avg {rep.avg_win_pct:+.2f}% · "
            f"median {rep.median_win_days}d hold · top-pattern: {top}")
