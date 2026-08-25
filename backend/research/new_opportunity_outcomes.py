# backend/research/new_opportunity_outcomes.py
"""AEGIS · Sprint M.1.3 · Forward-return tracker for NEW opportunities.

CEO directive 2026-08-25 M.1.3: "For each NEW opportunity: Entry → 1D →
3D → 5D → 10D → 20D · then we'll know whether the NEW engine is
producing genuine alpha or churn".

For every NEW recommendation in the Registry, computes:
  · 1D forward return
  · 3D forward return
  · 5D forward return
  · 10D forward return
  · 20D forward return
  · max gain during hold window
  · max drawdown during hold window
  · realized exit P&L (if closed)

Aggregates into:
  · NEW opportunity win rate
  · NEW opportunity expectancy
  · NEW opportunity profit factor
  · NEW opportunity max DD

Also splits by cohort (NEW vs EXISTING vs RE-ENTRY) for M.1.4
comparison. Emits reports/research/new_opportunity_outcomes_{market}.json.

Constitutional invariant · READ ONLY · never mutates R1/R2.
Locks respected · never touches Excel format · lifecycle unchanged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.new_opportunity_outcomes.v1.20260825"

FORWARD_HORIZONS = [1, 3, 5, 10, 20]


@dataclass
class OpportunityOutcome:
    ticker: str
    runner: str
    market: str
    cohort: str                 # NEW / EXISTING / RE-ENTRY
    entry_date: str
    entry_price: float
    n_days_observed: int
    fwd_1d_pct: Optional[float] = None
    fwd_3d_pct: Optional[float] = None
    fwd_5d_pct: Optional[float] = None
    fwd_10d_pct: Optional[float] = None
    fwd_20d_pct: Optional[float] = None
    max_gain_pct: Optional[float] = None
    max_dd_pct: Optional[float] = None
    exit_date: Optional[str] = None
    exit_pnl_pct: Optional[float] = None


@dataclass
class CohortMetrics:
    cohort: str
    n_observations: int = 0
    win_rate_1d: Optional[float] = None
    win_rate_5d: Optional[float] = None
    win_rate_20d: Optional[float] = None
    avg_1d_pct: Optional[float] = None
    avg_5d_pct: Optional[float] = None
    avg_20d_pct: Optional[float] = None
    median_20d_pct: Optional[float] = None
    profit_factor_20d: Optional[float] = None
    expectancy_20d_pct: Optional[float] = None
    avg_max_dd_pct: Optional[float] = None
    avg_max_gain_pct: Optional[float] = None
    confidence: str = "observation-only"


@dataclass
class OutcomesReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_total: int = 0
    n_new: int = 0
    n_existing: int = 0
    n_reentry: int = 0
    cohort_metrics: list = field(default_factory=list)
    outcomes: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────
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


def _forward_return(series, entry_date: str, days: int) -> Optional[float]:
    """Return % from entry_date's close to close +N business days later."""
    if series is None: return None
    idx = list(series.index)
    if entry_date not in idx:
        # fall back to first date on/after entry
        after = [d for d in idx if d >= entry_date]
        if not after: return None
        entry_i = idx.index(after[0])
    else:
        entry_i = idx.index(entry_date)
    if entry_i + days >= len(idx): return None
    e_p = float(series.iloc[entry_i])
    fwd_p = float(series.iloc[entry_i + days])
    if e_p <= 0: return None
    return round((fwd_p - e_p) / e_p * 100, 2)


def _max_gain_dd(series, entry_date: str, window_days: int = 20) -> tuple:
    """Return (max_gain_pct, max_dd_pct) over window_days from entry."""
    if series is None: return (None, None)
    idx = list(series.index)
    if entry_date not in idx:
        after = [d for d in idx if d >= entry_date]
        if not after: return (None, None)
        entry_i = idx.index(after[0])
    else:
        entry_i = idx.index(entry_date)
    end_i = min(entry_i + window_days, len(idx) - 1)
    if end_i <= entry_i: return (None, None)
    e_p = float(series.iloc[entry_i])
    window = series.iloc[entry_i:end_i + 1]
    if e_p <= 0: return (None, None)
    max_p = float(window.max())
    min_p = float(window.min())
    max_gain = round((max_p - e_p) / e_p * 100, 2)
    max_dd = round((min_p - e_p) / e_p * 100, 2)
    return (max_gain, max_dd)


# ─────────────────────────────────────────────────────────────────
# Cohort assignment · uses lifecycle_stabilization classifier
# ─────────────────────────────────────────────────────────────────
def _classify_cohort(entry_data: dict, all_entries: list) -> str:
    """Classify NEW / EXISTING / RE-ENTRY based on prior history."""
    from backend.research.lifecycle_stabilization import classify_opportunity_state
    _ent = entry_data["created_date"]
    prior = [h for h in all_entries
             if (h.get("created_date","") or "") < _ent]
    state = classify_opportunity_state(
        ticker=entry_data["ticker"], market="",
        runner=entry_data["runner"],
        rec_date=_ent, asof=entry_data.get("closed_date") or _ent,
        registry_history=prior,
    )
    if state in ("NEW", "EXISTING", "RE-ENTRY"): return state
    return "NEW"


# ─────────────────────────────────────────────────────────────────
# Cohort aggregation
# ─────────────────────────────────────────────────────────────────
def _confidence_band(n: int) -> str:
    if n < 20: return "observation-only"
    if n < 50: return "directional"
    if n < 100: return "research-candidate"
    return "production-candidate"


def _cohort_metrics(outcomes: list, cohort: str) -> CohortMetrics:
    items = [o for o in outcomes if o.cohort == cohort]
    n = len(items)
    if n == 0:
        return CohortMetrics(cohort=cohort, n_observations=0)

    def _wr(field_name):
        vals = [getattr(o, field_name) for o in items
                if getattr(o, field_name) is not None]
        if not vals: return None
        return round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1)

    def _avg(field_name):
        vals = [getattr(o, field_name) for o in items
                if getattr(o, field_name) is not None]
        if not vals: return None
        return round(sum(vals) / len(vals), 2)

    wins20 = [o.fwd_20d_pct for o in items
              if o.fwd_20d_pct is not None and o.fwd_20d_pct > 0]
    losses20 = [o.fwd_20d_pct for o in items
                if o.fwd_20d_pct is not None and o.fwd_20d_pct < 0]
    avg_w = sum(wins20) / len(wins20) if wins20 else 0
    avg_l = sum(losses20) / len(losses20) if losses20 else 0
    pf = round(abs(avg_w / avg_l), 2) if avg_l else 0.0
    all_20d = [o.fwd_20d_pct for o in items if o.fwd_20d_pct is not None]
    med = None
    if all_20d:
        s = sorted(all_20d)
        med = round(s[len(s) // 2], 2)
    win_rate_20d = _wr("fwd_20d_pct")
    exp_20d = None
    if win_rate_20d is not None:
        exp_20d = round((win_rate_20d / 100) * avg_w
                        + (1 - win_rate_20d / 100) * avg_l, 2)
    return CohortMetrics(
        cohort=cohort,
        n_observations=n,
        win_rate_1d=_wr("fwd_1d_pct"),
        win_rate_5d=_wr("fwd_5d_pct"),
        win_rate_20d=win_rate_20d,
        avg_1d_pct=_avg("fwd_1d_pct"),
        avg_5d_pct=_avg("fwd_5d_pct"),
        avg_20d_pct=_avg("fwd_20d_pct"),
        median_20d_pct=med,
        profit_factor_20d=pf,
        expectancy_20d_pct=exp_20d,
        avg_max_dd_pct=_avg("max_dd_pct"),
        avg_max_gain_pct=_avg("max_gain_pct"),
        confidence=_confidence_band(n),
    )


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str, lookback_days: int = 90) -> OutcomesReport:
    from backend.research import opportunity_registry as _oreg
    reg = _oreg.load_all(root)
    all_entries = []
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            all_entries.append({
                "ticker": o.ticker, "runner": o.runner,
                "status": o.status,
                "created_date": o.created_date,
                "closed_date": o.closed_date,
                "opportunity_id": getattr(
                    o, "opportunity_id",
                    f"{o.ticker}_{o.runner}_{o.created_date}"),
            })
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    outcomes: list = []
    for e in all_entries:
        _ent = str(e["created_date"])[:10]
        if _ent < cutoff: continue
        cohort = _classify_cohort(e, all_entries)
        s = _series(root, e["ticker"], market)
        if s is None: continue
        idx = list(s.index)
        # entry price
        _first_after = [d for d in idx if d >= _ent]
        if not _first_after: continue
        _ep = float(s.iloc[idx.index(_first_after[0])])
        if _ep <= 0: continue
        # forward returns
        fwd = {}
        for h in FORWARD_HORIZONS:
            fwd[f"fwd_{h}d_pct"] = _forward_return(s, _first_after[0], h)
        mg, mdd = _max_gain_dd(s, _first_after[0], 20)
        # exit if any
        exit_pnl = None; exit_date = None
        if e.get("closed_date"):
            _xd = str(e["closed_date"])[:10]
            exit_date = _xd
            _x_after = [d for d in idx if d >= _xd]
            if _x_after:
                _xp = float(s.iloc[idx.index(_x_after[0])])
                exit_pnl = round((_xp - _ep) / _ep * 100, 2)
        outcomes.append(OpportunityOutcome(
            ticker=e["ticker"].upper(),
            runner=e["runner"].upper().replace("_NEW",""),
            market=market.lower(), cohort=cohort,
            entry_date=_ent, entry_price=round(_ep, 2),
            n_days_observed=len([d for d in idx if d >= _ent]),
            fwd_1d_pct=fwd["fwd_1d_pct"],
            fwd_3d_pct=fwd["fwd_3d_pct"],
            fwd_5d_pct=fwd["fwd_5d_pct"],
            fwd_10d_pct=fwd["fwd_10d_pct"],
            fwd_20d_pct=fwd["fwd_20d_pct"],
            max_gain_pct=mg, max_dd_pct=mdd,
            exit_date=exit_date, exit_pnl_pct=exit_pnl,
        ))
    rep = OutcomesReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    rep.outcomes = [asdict(o) for o in outcomes]
    rep.n_total = len(outcomes)
    rep.n_new = sum(1 for o in outcomes if o.cohort == "NEW")
    rep.n_existing = sum(1 for o in outcomes if o.cohort == "EXISTING")
    rep.n_reentry = sum(1 for o in outcomes if o.cohort == "RE-ENTRY")
    for c in ("NEW", "EXISTING", "RE-ENTRY"):
        rep.cohort_metrics.append(asdict(_cohort_metrics(outcomes, c)))
    return rep


def emit(root: Path, rep: OutcomesReport) -> Path:
    p = (root / "reports" / "research"
         / f"new_opportunity_outcomes_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: OutcomesReport) -> str:
    lines = [f"new_opportunity_outcomes · {rep.n_total} entries · "
             f"NEW={rep.n_new} EXISTING={rep.n_existing} RE-ENTRY={rep.n_reentry}"]
    for cm in rep.cohort_metrics:
        if cm.get("n_observations", 0) > 0:
            lines.append(
                f"  {cm['cohort']:8} · "
                f"n={cm['n_observations']} · "
                f"20d_wr={cm.get('win_rate_20d','?')}% · "
                f"exp={cm.get('expectancy_20d_pct','?')}% · "
                f"PF={cm.get('profit_factor_20d','?')} · "
                f"conf={cm.get('confidence','?')}")
    return "\n".join(lines)
