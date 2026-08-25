# backend/research/opportunity_engine.py
"""AEGIS · Sprint M · Phase B · Daily Opportunity Engine.

CEO directive 2026-08-25 v2.0: "I can see the same stock names every
day but nothing is refreshing".

Solves the "same stocks every day" pattern via:

  B11 · daily NEW-opportunity discovery module
  B12 · compare today's qualifying universe with previous recommendations
  B13 · distinguish NEW from RE-ENTRY (Position ID based, not ticker)
  B14 · opportunity freshness ratio (NEW / total)
  B15 · daily R1/R2 discovery counts
  B16 · ensure new opportunities aren't suppressed by existing holdings

Emits reports/context/opportunity_engine_{market}.json with:
  · today's newly qualifying stocks
  · yesterday-vs-today delta
  · freshness ratio
  · R1/R2 daily discovery counts
  · suppression check

Locks respected:
  LOCK 1 · Excel format never touched (read-only)
  LOCK 2 · Lifecycle states are exactly NEW/ACTIVE/ACTIVE+/EXIT/CLOSED
           · re-entry gets NEW Position ID
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.opportunity_engine.v1.20260825"


@dataclass
class OpportunityRow:
    ticker: str
    market: str
    runner: str
    opportunity_state: str      # NEW / EXISTING / RE-ENTRY / CLOSED
    rec_date: str
    position_id: str
    prior_position_id: str = ""      # if RE-ENTRY
    reason: str = ""


@dataclass
class OpportunityEngineReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    # 2026-08-25 · Sprint M.1.2 · data-state semantics · CEO directive
    # "never collapse STALE into 0 opportunities". Report state is one
    # of: VALID / NO_OPPORTUNITY / UNAVAILABLE / STALE / ERROR
    data_state: str = "VALID"
    data_state_reason: str = ""
    recs_asof: str = ""             # asof from source recommendations.json
    recs_stale_days: int = 0
    n_total_today: int = 0
    n_new: int = 0
    n_existing: int = 0
    n_reentry: int = 0
    n_closed_today: int = 0
    n_r1_new: int = 0
    n_r2_new: int = 0
    freshness_ratio: float = 0.0
    yesterday_active: int = 0
    today_active: int = 0
    added_today: list = field(default_factory=list)
    removed_today: list = field(default_factory=list)
    suppression_check: dict = field(default_factory=dict)
    detail: list = field(default_factory=list)


def _load_registry(root: Path):
    from backend.research import opportunity_registry as _oreg
    return _oreg.load_all(root)


def _classify(ticker: str, runner: str, rec_date: str, asof: str,
              history: list) -> tuple[str, str]:
    """Return (state, reason) · uses classifier from lifecycle_stabilization."""
    from backend.research.lifecycle_stabilization import (
        classify_opportunity_state)
    state = classify_opportunity_state(
        ticker=ticker, market="", runner=runner,
        rec_date=rec_date, asof=asof, registry_history=history,
    )
    reason = {
        "NEW":      "first-time recommendation for this (ticker, runner)",
        "EXISTING": "already active in Registry",
        "RE-ENTRY": "previously CLOSED · new Position ID today",
        "CLOSED":   "Registry marks this as closed",
    }.get(state, "")
    return state, reason


# ─────────────────────────────────────────────────────────────────
# B11 + B13 · classify today's opportunities into NEW/EXISTING/RE-ENTRY
# ─────────────────────────────────────────────────────────────────
def classify_today(root: Path, market: str, asof: str) -> list:
    reg = _load_registry(root)
    all_entries = []
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            all_entries.append({
                "ticker": o.ticker, "runner": o.runner,
                "status": o.status, "created_date": o.created_date,
                "closed_date": o.closed_date,
                "opportunity_id": getattr(o, "opportunity_id",
                                          f"{o.ticker}_{o.runner}_{o.created_date}"),
            })
    today = str(asof)[:10]
    rows: list = []
    for e in all_entries:
        rec_dt = str(e.get("created_date", ""))[:10]
        history_before = [h for h in all_entries
                          if (h.get("created_date","") or "") < rec_dt]
        state, reason = _classify(
            ticker=e["ticker"], runner=e["runner"],
            rec_date=rec_dt, asof=today,
            history=history_before,
        )
        # For today's cohort we only tag opportunities created today
        if rec_dt == today:
            prior_pid = ""
            if state == "RE-ENTRY":
                # find the last closed pid for this ticker+runner
                _prior = [h for h in history_before
                          if h.get("ticker","").upper() == e["ticker"].upper()
                          and h.get("runner","").upper().replace("_NEW","") ==
                              e["runner"].upper().replace("_NEW","")
                          and h.get("status") in ("CLOSED","EXIT")]
                if _prior:
                    prior_pid = _prior[-1].get("opportunity_id","")
            rows.append(OpportunityRow(
                ticker=e["ticker"], market=market.lower(),
                runner=e["runner"], opportunity_state=state,
                rec_date=rec_dt, position_id=e["opportunity_id"],
                prior_position_id=prior_pid, reason=reason,
            ))
    return rows


# ─────────────────────────────────────────────────────────────────
# B12 · yesterday-vs-today delta
# ─────────────────────────────────────────────────────────────────
def yesterday_vs_today(root: Path, market: str, asof: str) -> tuple:
    reg = _load_registry(root)
    today = str(asof)[:10]
    try:
        yday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    except ValueError:
        yday = today
    today_active = set(); yday_active = set()
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if not o.is_active(): continue
            key = f"{o.ticker.upper()}|{o.runner.upper().replace('_NEW','')}"
            _ent = str(o.created_date or "")[:10]
            _clo = str(o.closed_date or "")[:10] if o.closed_date else None
            # Active TODAY = created ≤ today, not-yet-closed
            if _ent <= today and (not _clo or _clo > today):
                today_active.add(key)
            if _ent <= yday and (not _clo or _clo > yday):
                yday_active.add(key)
    added = today_active - yday_active
    removed = yday_active - today_active
    return sorted(yday_active), sorted(today_active), sorted(added), sorted(removed)


# ─────────────────────────────────────────────────────────────────
# B15 · daily R1/R2 discovery counts
# ─────────────────────────────────────────────────────────────────
def r1_r2_discovery(rows: list) -> tuple:
    """From today's rows, count NEW / RE-ENTRY per runner."""
    n_r1 = sum(1 for r in rows
               if r.runner.upper().replace("_NEW","") == "R1"
               and r.opportunity_state in ("NEW", "RE-ENTRY"))
    n_r2 = sum(1 for r in rows
               if r.runner.upper().replace("_NEW","") == "R2"
               and r.opportunity_state in ("NEW", "RE-ENTRY"))
    return n_r1, n_r2


# ─────────────────────────────────────────────────────────────────
# B14 · freshness ratio
# ─────────────────────────────────────────────────────────────────
def freshness(rows: list) -> float:
    if not rows: return 0.0
    n_new = sum(1 for r in rows
                if r.opportunity_state in ("NEW", "RE-ENTRY"))
    return round(n_new / len(rows) * 100, 1)


# ─────────────────────────────────────────────────────────────────
# B16 · suppression check · are new opps blocked by existing holdings?
# ─────────────────────────────────────────────────────────────────
def suppression_check(root: Path, market: str, asof: str) -> dict:
    """If today's Registry has ZERO new discoveries but investability
    shadow diagnostic shows quality picks, we're suppressed by existing
    holdings."""
    reg = _load_registry(root)
    today = str(asof)[:10]
    n_new_today = 0
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if str(o.created_date or "")[:10] == today and o.is_active():
                n_new_today += 1
    # Look at investability shadow · how many high-quality picks are
    # NOT in today's Registry?
    shadow_p = (root / "reports" / "context"
                / f"investability_shadow_diagnostic_{market.lower()}.json")
    n_shadow_picks = 0
    n_shadow_missed = 0
    try:
        if shadow_p.exists():
            d = json.loads(shadow_p.read_text(encoding="utf-8"))
            picks = d.get("top_discoveries") or []
            n_shadow_picks = len(picks)
            # missed = pick not currently active in Registry
            active_tks = set()
            for opps in reg.values():
                for o in opps:
                    if o.market.lower() != market.lower(): continue
                    if o.is_active():
                        active_tks.add(o.ticker.upper())
            for pk in picks:
                if str(pk.get("ticker","")).upper() not in active_tks:
                    n_shadow_missed += 1
    except Exception:
        pass
    return {
        "n_new_today": n_new_today,
        "n_shadow_picks": n_shadow_picks,
        "n_shadow_missed": n_shadow_missed,
        "suppression_score": (round(n_shadow_missed / max(n_shadow_picks, 1) * 100, 1)
                              if n_shadow_picks else 0.0),
        "verdict": ("SUPPRESSED · shadow has picks not in Registry"
                    if n_shadow_missed > 0 and n_new_today == 0
                    else "OK"),
    }


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def _check_data_state(root: Path, market: str, asof: str,
                      stale_threshold_days: int = 3) -> tuple:
    """M.1.2 · Determine data state · returns (state, reason, recs_asof,
    stale_days). CEO directive: never collapse STALE into 0 opportunities."""
    recs_p = (root / ("usa/reports/recommendations.json"
                      if market.lower() == "usa"
                      else "reports/recommendations.json"))
    if not recs_p.exists():
        return ("UNAVAILABLE",
                "recommendations.json missing · upstream pipeline failed",
                "", 999)
    try:
        d = json.loads(recs_p.read_text(encoding="utf-8"))
        recs_asof = str(d.get("asof", ""))[:10]
        n_recs = len(d.get("recommendations", []))
        if not recs_asof:
            return ("ERROR", "recommendations.json missing asof field",
                    "", 999)
        if n_recs == 0:
            return ("NO_OPPORTUNITY",
                    "recommendations.json exists but empty", recs_asof, 0)
        try:
            _rec_d = date.fromisoformat(recs_asof)
            _stale = (date.fromisoformat(str(asof)[:10]) - _rec_d).days
        except ValueError:
            return ("ERROR", f"invalid asof format '{recs_asof}'", recs_asof, 999)
        if _stale > stale_threshold_days:
            return ("STALE",
                    f"recommendations.json asof={recs_asof} is "
                    f"{_stale} days behind today · upstream refresh needed",
                    recs_asof, _stale)
        return ("VALID", "", recs_asof, _stale)
    except Exception as e:
        return ("ERROR", f"read failed · {type(e).__name__}: {e}", "", 999)


def compute(root: Path, market: str, asof: str) -> OpportunityEngineReport:
    rep = OpportunityEngineReport(
        market=market.lower(),
        asof=str(asof)[:10],
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    # M.1.2 · classify data state FIRST · so 0 opps doesn't masquerade as "no picks"
    state, reason, recs_asof, stale_days = _check_data_state(
        root, market, str(asof)[:10])
    rep.data_state = state
    rep.data_state_reason = reason
    rep.recs_asof = recs_asof
    rep.recs_stale_days = stale_days
    rows = classify_today(root, market, str(asof)[:10])
    rep.detail = [asdict(r) for r in rows]
    rep.n_total_today = len(rows)
    rep.n_new = sum(1 for r in rows if r.opportunity_state == "NEW")
    rep.n_existing = sum(1 for r in rows if r.opportunity_state == "EXISTING")
    rep.n_reentry = sum(1 for r in rows if r.opportunity_state == "RE-ENTRY")
    rep.n_closed_today = sum(1 for r in rows if r.opportunity_state == "CLOSED")
    rep.n_r1_new, rep.n_r2_new = r1_r2_discovery(rows)
    rep.freshness_ratio = freshness(rows)
    yday_a, today_a, added, removed = yesterday_vs_today(root, market, str(asof)[:10])
    rep.yesterday_active = len(yday_a)
    rep.today_active = len(today_a)
    rep.added_today = added
    rep.removed_today = removed
    rep.suppression_check = suppression_check(root, market, str(asof)[:10])
    return rep


def emit(root: Path, report: OpportunityEngineReport) -> Path:
    p = (root / "reports" / "context"
         / f"opportunity_engine_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: OpportunityEngineReport) -> str:
    # M.1.2 · surface data_state prominently so operator never confuses
    # STALE with NO_OPPORTUNITY
    if rep.data_state != "VALID":
        return (f"opportunity_engine · state={rep.data_state} · "
                f"recs_asof={rep.recs_asof} · stale {rep.recs_stale_days}d · "
                f"{rep.data_state_reason[:60]}")
    return (f"opportunity_engine · state=VALID · today {rep.n_total_today} opps · "
            f"NEW {rep.n_new} · RE-ENTRY {rep.n_reentry} · "
            f"EXISTING {rep.n_existing} · freshness {rep.freshness_ratio}% · "
            f"R1_new {rep.n_r1_new} R2_new {rep.n_r2_new} · "
            f"suppression: {rep.suppression_check.get('verdict','?')}")
