"""AEGIS · FIVE-SHEET WORKBOOK · CEO 2026-09-07.

Replaces the 8-tab workbook (00_Health · 01_Investments · 01_Portfolio ·
02_Today_Momentum · 03_Exit_History · 04_Daily_Portfolio_History ·
05_R1_Advisory · 06_Composite_Signals) with exactly five surfaces:

    R1                    advisory positions · loss / stop-breach review
    R2                    production holdings · canonical dynamic stop
    MOMENTUM              universe -> evaluated -> candidates -> states
    DAILY RECOMMENDATION  consolidated "what do I need to do today"
    EXIT                  unified realized exits across R1 · R2 · Momentum

Directive:
> "The five sheets are presentation surfaces, not five separate engines."
> "Do not duplicate calculations between these sheets."

ARCHITECTURE · the reason this module exists at all
---------------------------------------------------
Every number rendered by all five sheets is computed EXACTLY ONCE, in
`build_views()`, and the emitters below are pure formatters over that
result. This is not stylistic. The BATAINDIA / CHAMBLFERT / ITC incident
happened because `01_Investments` and `01_Portfolio` each computed an R2
stop independently: Portfolio read the trailed stop from dynamic_risk_v2
while Investments recomputed a fresh entry-anchored ATR stop, so on
2026-09-07 one sheet said "EXIT · stop hit" and the other said "HOLD" for
the same position on the same day. A single computation is the structural
fix; anything else is a convention that erodes.

If you are adding a sheet or a column: read it off a `PositionView`.
Do NOT recompute a price, a P&L, or a stop in an emitter.

GOVERNANCE
----------
Deliberate contract changes carried by this redesign, both CEO-authorized:
  · The 8-sheet HARD LOCK is superseded by the explicit five-sheet directive.
  · C19 (workbook-wide R1-zero) is scoped out for the EXIT sheet, which is
    now required to show "All exits - R1, R2, Momentum". R1 rows are
    labelled `R1 · ADVISORY` and are excluded from every production P&L
    aggregate, so R1 results still never contaminate R2 performance.

Unchanged by directive: R2 logic, R2 thresholds, ensemble weights, the
risk/exit engine, momentum thresholds, R1 production behaviour, R3,
evidence gates, PIT requirements.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

FIVE_SHEETS = ["R1", "R2", "MOMENTUM", "DAILY RECOMMENDATION", "EXIT"]

# ── Loss / stop escalation ladder · CEO 2026-09-07 ────────────────────
# R1 carries NO dynamic-exit protection and must never auto-exit (V2 §18 /
# §R1.9). Before this ladder existed an R1 position could sit 12% underwater
# through a breached advisory stop and render as a neutral "HOLD" row. These
# states are DISPLAY states: they escalate operator attention, they never
# close a position and they feed no engine.
STATE_NORMAL = "NORMAL"
STATE_WATCH = "WATCH"
STATE_BREACH = "STOP BREACH"
STATE_DEEP_LOSS = "DEEP LOSS"

DEEP_LOSS_PCT = -15.0        # unrealized loss at/below this is DEEP LOSS
WATCH_LOSS_PCT = -8.0        # unrealized loss at/below this is WATCH
WATCH_STOP_DISTANCE_PCT = 3.0   # within this % of the stop is WATCH

_STATE_ICON = {
    STATE_NORMAL: "🟢",
    STATE_WATCH: "🟡",
    STATE_BREACH: "🔴",
    STATE_DEEP_LOSS: "🔴",
}


def escalation_state(pnl_pct: Optional[float],
                     current_price: Optional[float],
                     stop: Optional[float],
                     stop_distance_pct: Optional[float]) -> str:
    """NORMAL / WATCH / STOP BREACH / DEEP LOSS · display-only.

    Order matters: a position that is BOTH deeply underwater and through its
    stop reports DEEP LOSS, the more severe of the two.
    """
    if pnl_pct is not None and pnl_pct <= DEEP_LOSS_PCT:
        return STATE_DEEP_LOSS
    if (current_price is not None and stop is not None
            and current_price <= stop):
        return STATE_BREACH
    if pnl_pct is not None and pnl_pct <= WATCH_LOSS_PCT:
        return STATE_WATCH
    if (stop_distance_pct is not None
            and 0 <= stop_distance_pct <= WATCH_STOP_DISTANCE_PCT):
        return STATE_WATCH
    return STATE_NORMAL


@dataclass
class PositionView:
    """One position, computed once, rendered by any sheet that needs it."""
    source: str                      # "R1" | "R2"
    pid: str
    ticker: str
    sector: str
    entry_date: str
    entry_price: Optional[float]
    current_price: Optional[float]
    pnl_pct: Optional[float]
    holding_days: Optional[int]
    stop: Optional[float]
    stop_type: str
    stop_source: str
    stop_distance_pct: Optional[float]
    target: Optional[float]
    confidence: Optional[float]
    # WHERE the confidence number came from, or why there is none.
    # CEO 2026-09-07 · a bare "—" in the Confidence column read as a broken
    # cell. It was not: the Registry schema has `initial_score` but NOTHING
    # populates it, and the momentum ledger has no confidence field at all
    # (the previous sheet read `e.get("confidence")`, a key that has never
    # existed). So held positions genuinely carry no captured entry
    # confidence. That is a data-capture gap and it is now stated on the
    # face of the sheet instead of being rendered as an empty value.
    confidence_source: str
    target_distance_pct: Optional[float]
    rr: Optional[float]
    state: str
    action: str
    reason: str

    @property
    def icon(self) -> str:
        return _STATE_ICON.get(self.state, "")

    @property
    def status_cell(self) -> str:
        return f"{self.icon} {self.state}".strip()


@dataclass
class ExitView:
    source: str                      # "R1" | "R2" | "MOMENTUM"
    pid: str
    ticker: str
    sector: str
    entry_date: str
    exit_date: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    realized_pnl_pct: Optional[float]
    exit_reason: str
    holding_days: Optional[int]
    subsequent_return_pct: Optional[float]
    relative_pp: Optional[float]
    classification: str              # production | administrative | advisory


@dataclass
class Views:
    market: str
    asof: str
    r1: list = field(default_factory=list)
    r2: list = field(default_factory=list)
    r1_new: list = field(default_factory=list)
    momentum: dict = field(default_factory=dict)
    daily_recs: dict = field(default_factory=dict)
    exits: list = field(default_factory=list)
    reconciliation: dict = field(default_factory=dict)
    blockers: list = field(default_factory=list)


# ── Shared loaders ────────────────────────────────────────────────────

def _r1_picks(root: Path, market: str) -> list:
    """Today's R1 advisory picks from the daily CSV.

    USA must NOT fall back to `data/aegis_today.csv` · that file is India's
    daily R1 output and loading it into USA misattributes India picks.
    """
    candidates = [root / "data" / f"aegis_today_{market.lower()}.csv"]
    if market.lower() == "india":
        candidates.append(root / "data" / "aegis_today.csv")
    for p in candidates:
        if not p.exists():
            continue
        try:
            import pandas as pd
            df = pd.read_csv(p)
            if "runner" in df.columns:
                df = df[df["runner"].astype(str).str.upper() == "R1"]
            if "Stock" in df.columns and "ticker" not in df.columns:
                df = df.rename(columns={
                    "Stock": "ticker", "Sector": "sector",
                    "Strength": "action", "Score /100": "score",
                    "Buy Range": "entry_zone", "Why": "bull_case",
                    "Rec Confidence %": "confidence", "Hist Target": "target",
                })
            rows = df.head(25).to_dict("records")
            if rows:
                return rows
        except Exception:
            continue
    return []


CONFIDENCE_NOT_CAPTURED = "NOT CAPTURED"


def _money(x: Optional[float]) -> Optional[float]:
    """Round a price for display · raw parquet floats render as
    284.8500061035156, which reads as noise in an operator sheet."""
    try:
        return round(float(x), 2) if x is not None else None
    except (TypeError, ValueError):
        return None


def _r1_confidence_map(root: Path, market: str) -> dict:
    """{TICKER: (confidence_pct, source)} from today's R1 picks CSV.

    This is the ONLY live per-name confidence AEGIS currently produces.
    India publishes it; USA has no R1 daily CSV producer, so USA R1 rows
    correctly report NOT CAPTURED rather than borrowing India's numbers.
    """
    out = {}
    for row in _r1_picks(root, market):
        tk = str(row.get("ticker") or "").upper().split(".", 1)[0]
        if not tk:
            continue
        for key, label in (("confidence", "r1_daily_picks:Rec Confidence %"),
                            ("score", "r1_daily_picks:Score /100")):
            v = row.get(key)
            if v is None:
                continue
            try:
                out[tk] = (round(float(v), 1), label)
                break
            except (TypeError, ValueError):
                continue
    return out


def _daily_recommendations(root: Path, market: str) -> dict:
    """Canonical daily recommendation output · both markets.

    Source: reports/recommendations.json (India) ·
            usa/reports/recommendations.json (USA)
    Producer: the adaptive recommendation engine, published through the
    SSoT bridge. Every record carries a per-ticker `confidence` and an
    `action`, where NEW_POSITION is the engine's INVESTABLE verdict.

    CEO 2026-09-07 · this artifact is the reason two defects existed at
    once: the workbook showed no confidence anywhere (it was reading
    `initial_score`, which nothing populates, and a momentum `confidence`
    key that has never existed), and USA showed no new daily
    recommendations (the USA producer had not run since 2026-09-03 while
    the workbook reported as-of 2026-09-07). Both are fixed by consuming
    this file and by REPORTING its as-of instead of assuming it is fresh.

    Returns {"by_ticker": {...}, "new_positions": [...], "asof": str,
             "n": int, "path": str, "stale": bool}
    """
    import datetime as _dt
    p = (root / "usa" / "reports" / "recommendations.json"
         if market.lower() == "usa"
         else root / "reports" / "recommendations.json")
    out = {"by_ticker": {}, "new_positions": [], "asof": None, "n": 0,
           "path": str(p), "stale": None}
    if not p.exists():
        return out
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return out
    recs = d.get("recommendations") or []
    asof = d.get("asof")
    if not asof:
        # This artifact does not always stamp `asof` · fall back to the run
        # timestamp, then to file mtime, so freshness is ALWAYS reportable.
        ru = str(d.get("run_utc") or "")
        asof = ru[:10] if len(ru) >= 10 else _dt.date.fromtimestamp(
            p.stat().st_mtime).isoformat()
    out["asof"] = asof
    out["n"] = len(recs)
    for r in recs:
        tk = str(r.get("ticker") or "").upper().split(".", 1)[0]
        if not tk:
            continue
        out["by_ticker"][tk] = r
        if str(r.get("action") or "").upper() == "NEW_POSITION":
            out["new_positions"].append(r)
    # Highest conviction first · the operator reads the top of the list.
    out["new_positions"].sort(
        key=lambda r: -(r.get("composite_decision_score") or 0))

    # CEO 2026-09-07 · confidence SATURATION check.
    # A confidence column is only useful if it discriminates. India's engine
    # currently returns 1.00 for 76% of names with a floor of 0.88, so a
    # "100%" cell there means "the engine did not separate this name from
    # any other", not "certain". That is an engine calibration issue and the
    # engine is out of scope for this batch · so it is DISCLOSED on the
    # sheet rather than silently rescaled, which would fabricate spread that
    # the underlying model does not have.
    cs = [r.get("confidence") for r in recs
          if isinstance(r.get("confidence"), (int, float))]
    if cs:
        at_max = sum(1 for c in cs if c >= 1.0)
        out["confidence_stats"] = {
            "n": len(cs), "min": round(min(cs), 3), "max": round(max(cs), 3),
            "mean": round(sum(cs) / len(cs), 3),
            "pct_at_max": round(at_max / len(cs) * 100, 1),
        }
        out["confidence_saturated"] = (at_max / len(cs)) >= 0.5
    else:
        out["confidence_stats"] = {}
        out["confidence_saturated"] = False
    return out


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """(a/b - 1) * 100 · None-safe."""
    try:
        if not a or not b or float(b) <= 0:
            return None
        return round((float(a) / float(b) - 1.0) * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _days_between(a: str, b: str) -> Optional[int]:
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except Exception:
        return None


# ── THE single computation ────────────────────────────────────────────

def build_views(root: Path, market: str, asof: str, reg_data: dict,
                momentum_ledger: dict) -> Views:
    """Compute every number all five sheets render · exactly once."""
    from scripts.build_aegis_3sheet_workbook import (
        _load_sector_cache, _sector_for, _close_on_or_before,
        _load_dynamic_risk, _atr14_at_date, _target_from_atr_fallback,
        _target_from_registry, _normalize_exit_reason, _extract_relative_pp,
        _load_r1_active_for_investments,
    )
    m = market.lower()
    v = Views(market=m, asof=asof)
    sector_cache = _load_sector_cache(root)
    r1_conf = _r1_confidence_map(root, m)
    v.daily_recs = _daily_recommendations(root, m)
    _rec_by_tk = v.daily_recs["by_ticker"]
    if v.daily_recs["asof"] and v.daily_recs["asof"] != asof:
        v.daily_recs["stale"] = True
        v.blockers.append(
            "DAILY RECOMMENDATIONS STALE · %s is as-of %s but this report is "
            "as-of %s · today's new opportunities are NOT in this workbook. "
            "Producer: usa/research/recommendations/run.py (USA) · "
            "research/recommendations/run.py (India)"
            % (v.daily_recs["path"], v.daily_recs["asof"], asof))
    else:
        v.daily_recs["stale"] = False

    def _rec_confidence(ticker: str):
        """(pct, source) from the canonical daily recommendation record."""
        r = _rec_by_tk.get(str(ticker).upper().split(".", 1)[0])
        if not r:
            return None
        c = r.get("confidence")
        try:
            c = float(c)
        except (TypeError, ValueError):
            return None
        if 0 <= c <= 1:
            c *= 100
        return round(c, 1), "recommendations.json:confidence"

    def _resolve_confidence(o, live) -> tuple:
        """(value, source) · Registry first, then today's live signal.

        Registry `initial_score` is checked first because an entry-time
        score is the honest number for a held position. In practice it is
        None for every row today · nothing writes it · so `live` (today's
        R1 pick confidence, matched by ticker) is used as a clearly-labelled
        second best, and anything else reports NOT CAPTURED rather than a
        blank cell that reads like a rendering fault.
        """
        raw = getattr(o, "initial_score", None)
        if isinstance(raw, (int, float)):
            val = float(raw)
            if 0 <= val <= 1:
                val *= 100
            return round(val, 1), "registry:initial_score"
        # Canonical daily engine · covers both markets and every scored
        # ticker, so this is what actually populates the column today.
        rec = _rec_confidence(getattr(o, "ticker", ""))
        if rec:
            return rec
        if live:
            return live[0], live[1]
        return None, CONFIDENCE_NOT_CAPTURED

    # CANONICAL R2 STOP · the one and only source. Loaded once, shared by
    # the R2 sheet and DAILY RECOMMENDATION. No sheet recomputes it.
    dr_by_pid = _load_dynamic_risk(root, m)
    if not dr_by_pid:
        v.blockers.append(
            "CANONICAL STOP MISSING · reports/context/dynamic_risk_%s.json "
            "absent or empty · R2 rows cannot show an authoritative stop. "
            "Producer: scripts/run_dynamic_risk_v2.py" % m)

    # ── R2 · production ───────────────────────────────────────────────
    for o in (reg_data.get("active") or []):
        pid = getattr(o, "opportunity_id", "")
        entry_p = _close_on_or_before(root, o.ticker, m, o.created_date or "")
        curr_p = _close_on_or_before(root, o.ticker, m, asof)
        dr = dr_by_pid.get(pid) or {}
        stop = dr.get("stop")
        try:
            stop = float(stop) if stop is not None else None
        except (TypeError, ValueError):
            stop = None
        stop_dist = None
        if stop is not None and curr_p:
            stop_dist = round((curr_p - stop) / curr_p * 100, 2)
        target = _target_from_registry(o)
        if not target and entry_p:
            atr = _atr14_at_date(root, m, o.ticker, o.created_date or asof)
            target = _target_from_atr_fallback(entry_p, atr, m_target=3.0)
        pnl = _pct(curr_p, entry_p)
        state = escalation_state(pnl, curr_p, stop, stop_dist)
        if stop is None:
            action, reason = "REVIEW", "no canonical dynamic_risk_v2 stop"
        elif state == STATE_BREACH:
            action, reason = "EXIT", "canonical stop breached"
        elif state == STATE_DEEP_LOSS:
            action, reason = "REVIEW", "deep unrealized loss · stop intact"
        elif state == STATE_WATCH:
            action, reason = "HOLD", "approaching canonical stop"
        else:
            action, reason = "HOLD", "canonical dynamic stop intact"
        conf, conf_src = _resolve_confidence(o, None)
        tgt_dist = None
        if target and curr_p:
            tgt_dist = round((float(target) - curr_p) / curr_p * 100, 2)
        rr = None
        if stop is not None and target and curr_p:
            _risk, _reward = curr_p - stop, float(target) - curr_p
            if _risk > 0 and _reward > 0:
                rr = round(_reward / _risk, 2)
        v.r2.append(PositionView(
            source="R2", pid=pid, ticker=str(o.ticker).upper().split(".", 1)[0],
            sector=_sector_for(sector_cache, m, o.ticker),
            entry_date=o.created_date or "—",
            entry_price=_money(entry_p), current_price=_money(curr_p),
            pnl_pct=pnl,
            holding_days=_days_between(o.created_date or "", asof),
            # NOT _money() · the canonical stop is a DECISION THRESHOLD and
            # is rendered exactly as dynamic_risk_v2 produced it. Rounding it
            # for looks (403.0428 -> 403.04) breaks the hard requirement that
            # every sheet show the same stop as the engine, and can move the
            # displayed threshold across the current price.
            stop=stop, stop_type=dr.get("type") or "—",
            stop_source="dynamic_risk_v2" if stop is not None else "MISSING",
            stop_distance_pct=stop_dist, target=_money(target),
            confidence=conf, confidence_source=conf_src,
            target_distance_pct=tgt_dist, rr=rr,
            state=state, action=action, reason=reason,
        ))

    # ── R1 · advisory · NEVER auto-exit ───────────────────────────────
    # R1 has no dynamic-exit protection, so its stop is an ATR-14 SUGGESTION
    # computed here for visibility only. It is deliberately NOT sourced from
    # dynamic_risk_v2 · publishing a canonical-looking stop for a runner that
    # cannot act on it would misrepresent R1 as protected.
    for o in (_load_r1_active_for_investments(root, m) or []):
        pid = getattr(o, "opportunity_id", "")
        entry_p = _close_on_or_before(root, o.ticker, m, o.created_date or "")
        curr_p = _close_on_or_before(root, o.ticker, m, asof)
        atr = _atr14_at_date(root, m, o.ticker, o.created_date or asof)
        stop = None
        if entry_p and atr and atr > 0:
            stop = round(float(entry_p) - 2.0 * float(atr), 4)
        stop_dist = None
        if stop is not None and curr_p:
            stop_dist = round((curr_p - stop) / curr_p * 100, 2)
        pnl = _pct(curr_p, entry_p)
        state = escalation_state(pnl, curr_p, stop, stop_dist)
        # R1 NEVER auto-exits · the most severe action available is REVIEW.
        action = "REVIEW" if state in (STATE_BREACH, STATE_DEEP_LOSS) else (
            "WATCH" if state == STATE_WATCH else "HOLD")
        reason = {
            STATE_BREACH: "R1 advisory stop breached · no auto-exit",
            STATE_DEEP_LOSS: "R1 deep unrealized loss · no auto-exit",
            STATE_WATCH: "R1 approaching advisory stop",
            STATE_NORMAL: "R1 advisory · within suggested stop",
        }[state]
        _tk = str(o.ticker).upper().split(".", 1)[0]
        conf, conf_src = _resolve_confidence(o, r1_conf.get(_tk))
        v.r1.append(PositionView(
            source="R1", pid=pid, ticker=_tk,
            sector=_sector_for(sector_cache, m, o.ticker),
            entry_date=o.created_date or "—",
            entry_price=_money(entry_p), current_price=_money(curr_p),
            pnl_pct=pnl,
            holding_days=_days_between(o.created_date or "", asof),
            stop=stop, stop_type="atr14_suggested" if stop else "—",
            stop_source="atr14_suggested_advisory" if stop else "MISSING",
            stop_distance_pct=stop_dist, target=None,
            confidence=conf, confidence_source=conf_src,
            target_distance_pct=None, rr=None,
            state=state, action=action, reason=reason,
        ))

    # ── NEW TODAY · investable daily recommendations ──────────────────
    # CEO 2026-09-07: "next day daily should go into respective sheets if
    # investable". The engine's INVESTABLE verdict is action=NEW_POSITION.
    #
    # These are rendered on R1 (the advisory runner this engine feeds) and
    # on DAILY RECOMMENDATION. They are deliberately NOT written into R2:
    # an R2 entry must pass R2 eligibility, and copying a recommendation
    # straight onto the production sheet is exactly the bypass the
    # reconciliation block exists to detect.
    _seen_new = set()
    for rec in v.daily_recs["new_positions"][:25]:
        tk = str(rec.get("ticker") or "").upper().split(".", 1)[0]
        if not tk or tk in _seen_new:
            continue
        _seen_new.add(tk)
        curr = _close_on_or_before(root, tk, m, asof)
        conf, conf_src = (_rec_confidence(tk) or (None, CONFIDENCE_NOT_CAPTURED))
        _reasons = rec.get("reasons_for")
        if isinstance(_reasons, list):
            _reasons = " · ".join(str(x) for x in _reasons[:2])
        v.r1_new.append(PositionView(
            source="R1", pid="—", ticker=tk,
            sector=str(rec.get("sector") or "UNKNOWN"),
            entry_date=asof, entry_price=_money(curr), current_price=_money(curr),
            pnl_pct=None, holding_days=0, stop=None, stop_type="—",
            stop_source="—", stop_distance_pct=None, target=None,
            confidence=conf, confidence_source=conf_src,
            target_distance_pct=None, rr=None,
            state=STATE_NORMAL,
            action="NEW · %s" % str(rec.get("recommendation") or "BUY").upper(),
            reason=str(_reasons or rec.get("classification")
                       or "engine verdict NEW_POSITION")[:90],
        ))

    # R1 NEW picks · today's advisory CSV signals (India only producer)
    for p in _r1_picks(root, m):
        tk = str(p.get("ticker", "")).upper().split(".", 1)[0]
        if not tk or tk in _seen_new:
            continue
        strength = str(p.get("action") or p.get("recommendation") or "").upper()
        if "BUY" not in strength:
            continue
        _seen_new.add(tk)
        curr = _close_on_or_before(root, tk, m, asof)
        conf, conf_src = r1_conf.get(tk, (None, CONFIDENCE_NOT_CAPTURED))
        v.r1_new.append(PositionView(
            source="R1", pid="—", ticker=tk,
            sector=str(p.get("sector") or "UNKNOWN"),
            entry_date=asof, entry_price=_money(curr), current_price=_money(curr),
            pnl_pct=None, holding_days=0, stop=None, stop_type="—",
            stop_source="—", stop_distance_pct=None, target=None,
            confidence=conf, confidence_source=conf_src,
            target_distance_pct=None, rr=None,
            state=STATE_NORMAL, action="ADVISORY BUY",
            reason=str(p.get("bull_case") or p.get("reason") or "R1 advisory")[:90],
        ))

    # ── MOMENTUM ──────────────────────────────────────────────────────
    v.momentum = _momentum_view(root, m, asof, momentum_ledger)
    if v.momentum.get("stale"):
        v.blockers.append(
            "MOMENTUM STALE · producer asof=%s but reporting asof=%s · "
            "candidates below are not today's market."
            % (v.momentum.get("producer_asof"), asof))

    # ── EXIT · unified across R1 · R2 · Momentum ──────────────────────
    def _exit_rows(opps, source, classification):
        out = []
        for o in opps or []:
            entry_p = _close_on_or_before(root, o.ticker, m, o.created_date or "")
            exit_p = _close_on_or_before(root, o.ticker, m, o.closed_date or "")
            curr_p = _close_on_or_before(root, o.ticker, m, asof)
            raw = getattr(o, "closed_reason", "") or "—"
            out.append(ExitView(
                source=source, pid=getattr(o, "opportunity_id", ""),
                ticker=str(o.ticker).upper().split(".", 1)[0],
                sector=_sector_for(sector_cache, m, o.ticker),
                entry_date=o.created_date or "—", exit_date=o.closed_date or "—",
                entry_price=entry_p, exit_price=exit_p,
                realized_pnl_pct=_pct(exit_p, entry_p),
                exit_reason=_normalize_exit_reason(raw),
                holding_days=_days_between(o.created_date or "", o.closed_date or ""),
                # Did exiting turn out right? Price move since the exit.
                subsequent_return_pct=_pct(curr_p, exit_p),
                relative_pp=_extract_relative_pp(raw),
                classification=classification,
            ))
        return out

    v.exits = (_exit_rows(reg_data.get("closed_90d"), "R2", "production")
               + _exit_rows(reg_data.get("closed_retired_90d"), "R1", "advisory")
               + _exit_rows(reg_data.get("closed_admin_90d"), "R2", "administrative"))
    v.exits.sort(key=lambda e: e.exit_date or "", reverse=True)

    # ── Momentum -> R2 lifecycle reconciliation ───────────────────────
    v.reconciliation = _reconcile(root, m, asof, v, momentum_ledger)
    return v


def _momentum_view(root: Path, market: str, asof: str, ledger: dict) -> dict:
    """Truthful momentum funnel · declared vs evaluated vs candidates.

    `n_universe_scanned` in the ledger is a DEPRECATED alias that actually
    holds the in-universe candidate count · rendering it as "scanned" is what
    printed "scanned universe=1" on a 230-ticker run. It is not read here.
    """
    src = root / "reports" / "research" / ("short_term_momentum_%s.json" % market)
    producer = {}
    if src.exists():
        try:
            producer = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            producer = {}
    funnel = ledger.get("producer_funnel") or {}
    producer_asof = ledger.get("producer_asof") or producer.get("asof")
    states = ledger.get("by_terminal_state") or {}

    # Candidates the producer found that the production-universe filter
    # removed · surfaced explicitly so "0 candidates" is never ambiguous
    # between "quiet market" and "everything was out of universe".
    in_universe_tickers = {
        str(e.get("ticker", "")).upper().split(".", 1)[0]
        for e in (ledger.get("entries") or [])
    }
    out_of_universe = [
        c for c in (producer.get("candidates") or [])
        if str(c.get("ticker", "")).upper().split(".", 1)[0] not in in_universe_tickers
    ]
    return {
        "producer_asof": producer_asof,
        "reporting_asof": asof,
        "stale": bool(producer_asof and producer_asof != asof),
        "n_declared_universe": funnel.get("n_declared_universe")
                               or producer.get("n_universe"),
        "n_unreadable": funnel.get("n_unreadable"),
        "n_insufficient_history": funnel.get("n_insufficient_history"),
        "n_evaluated": funnel.get("n_evaluated"),
        "n_ignored_no_momentum": funnel.get("n_ignored_no_momentum"),
        "n_candidates": funnel.get("n_candidates"),
        "n_production_universe": ledger.get("n_production_universe"),
        "n_out_of_universe_dropped": ledger.get("n_out_of_universe_dropped"),
        "n_in_universe_candidates": len(ledger.get("entries") or []),
        "n_accepted": states.get("ACCEPTED", 0),
        "n_watch": states.get("WATCH", 0),
        "n_rejected": states.get("REJECTED", 0),
        "n_no_evidence": states.get("NO_EVIDENCE", 0),
        "conservation_ok": ledger.get("conservation_ok"),
        "entries": ledger.get("entries") or [],
        "out_of_universe": out_of_universe,
        "thresholds": producer.get("thresholds") or {},
    }


def _reconcile(root: Path, market: str, asof: str, v: Views,
               ledger: dict) -> dict:
    """Momentum -> R2 eligibility -> Registry -> R2 sheet -> Daily Rec.

    Reports WHERE candidates disappear and WHY. A stage that drops
    everything is a finding, not a silent zero.
    """
    mv = v.momentum
    accepted = [e for e in (ledger.get("entries") or [])
                if str(e.get("terminal_state", "")).upper() == "ACCEPTED"]
    accepted_tickers = {str(e.get("ticker", "")).upper().split(".", 1)[0]
                        for e in accepted}
    # Registry R2 opportunities created TODAY · the only legitimate way a
    # momentum candidate becomes a position. Momentum is never copied
    # directly into R2 · it must pass R2 eligibility first.
    registry_new = [p for p in v.r2 if p.entry_date == asof]
    registry_new_tickers = {p.ticker for p in registry_new}
    r2_active_tickers = {p.ticker for p in v.r2}

    stages = [
        ("1 · Declared universe", mv.get("n_declared_universe"), ""),
        ("2 · Actually evaluated", mv.get("n_evaluated"),
         "unreadable=%s · insufficient history=%s"
         % (mv.get("n_unreadable"), mv.get("n_insufficient_history"))),
        ("3 · Momentum candidates", mv.get("n_candidates"),
         "%s evaluated tickers showed no momentum signal"
         % mv.get("n_ignored_no_momentum")),
        ("4 · In production universe", mv.get("n_in_universe_candidates"),
         "%s candidate(s) dropped as outside the %s-name production universe"
         % (mv.get("n_out_of_universe_dropped"), mv.get("n_production_universe"))),
        ("5 · ACCEPTED by ledger", len(accepted),
         "WATCH=%s · REJECTED=%s · NO_EVIDENCE=%s"
         % (mv.get("n_watch"), mv.get("n_rejected"), mv.get("n_no_evidence"))),
        ("6 · Registry R2 NEW today", len(registry_new),
         "accepted momentum tickers not opened: %s"
         % (", ".join(sorted(accepted_tickers - registry_new_tickers)) or "none")),
        ("7 · R2 sheet ACTIVE", len(v.r2), ""),
    ]
    mismatches = []
    if accepted and not registry_new:
        mismatches.append(
            "%d momentum candidate(s) ACCEPTED but 0 R2 positions opened "
            "today · candidates: %s. Momentum ACCEPT is NOT an R2 entry · "
            "R2 eligibility is a separate gate and this is only a defect if "
            "R2 eligibility passed."
            % (len(accepted), ", ".join(sorted(accepted_tickers))))
    leaked = registry_new_tickers - accepted_tickers
    if leaked and accepted:
        mismatches.append(
            "R2 opened %s today without a matching momentum ACCEPT · verify "
            "the entry came from R2 eligibility, not a direct momentum copy."
            % ", ".join(sorted(leaked)))
    if mv.get("conservation_ok") is False:
        mismatches.append(
            "LEDGER CONSERVATION BROKEN · candidates do not equal the sum of "
            "terminal states · entries are disappearing silently.")
    return {
        "stages": stages,
        "mismatches": mismatches,
        "accepted_tickers": sorted(accepted_tickers),
        "r2_active_tickers": sorted(r2_active_tickers),
    }


# ── Emitters · pure formatters over Views ─────────────────────────────

def _fmt(x, dash="—"):
    return dash if x is None else x


def _confidence_legend(v) -> str:
    """One honest sentence about what the Confidence column is worth today."""
    st = (v.daily_recs or {}).get("confidence_stats") or {}
    base = ("Confidence % · from the canonical daily recommendation engine "
            "(recommendations.json) · NOT CAPTURED where no source scored "
            "the name.")
    if not st:
        return base
    spread = ("range %s–%s · mean %s · %s%% of scored names sit at the "
              "maximum" % (st.get("min"), st.get("max"), st.get("mean"),
                            st.get("pct_at_max")))
    if (v.daily_recs or {}).get("confidence_saturated"):
        return (base + " ⚠ SATURATED: " + spread + " · a high value here "
                "means the engine did not separate this name from the rest, "
                "not that the call is certain. Treat it as low-information "
                "until the engine is recalibrated.")
    return base + " Distribution: " + spread + "."


def emit_r1(wb, v: Views):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    # Column order follows how the row is read: IDENTITY, then POSITION,
    # then MONEY, then RISK, then VERDICT, then EVIDENCE. "Runner" is
    # explicit even though this sheet is R1-only · the delivery validator
    # resolves runner-contamination checks through that column, and without
    # it those checks find nothing and pass on empty data.
    hdr = [
        # identity
        "Stock", "Runner", "Sector",
        # position
        "Entry Date", "Holding Days",
        # money
        "Entry Price", "Current Price", "Unrealized P&L %",
        # risk
        "Suggested Stop", "Distance to Stop %",
        # verdict
        "Review State", "Action",
        # evidence
        "Confidence %", "Confidence Source", "Reason", "Position ID",
    ]
    ws = wb.create_sheet("R1")
    _banner(ws, "AEGIS %s · R1 · ADVISORY ONLY · as of %s"
            % (v.market.upper(), v.asof), len(hdr))
    _sub(ws, ("⚠ R1 IS ADVISORY · RETIRED FROM PRODUCTION · it carries NO "
              "dynamic-exit protection and is NEVER auto-exited. Stops below "
              "are ATR-14 SUGGESTIONS for operator review only."), len(hdr), 2)
    breaches = [p for p in v.r1 if p.state in (STATE_BREACH, STATE_DEEP_LOSS)]
    _sub(ws, ("Held: %d · today's advisory BUY signals: %d · needing review "
              "(stop breach or deep loss): %d"
              % (len(v.r1), len(v.r1_new), len(breaches))), len(hdr), 3)
    _header(ws, hdr, 5)
    for i, w in enumerate([12, 8, 18, 12, 12, 12, 13, 15, 14, 17, 15, 10,
                            12, 30, 42, 30], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 6
    # Most severe first · a stop breach must never sort below a healthy row.
    order = {STATE_DEEP_LOSS: 0, STATE_BREACH: 1, STATE_WATCH: 2, STATE_NORMAL: 3}
    for p in sorted(v.r1, key=lambda x: (order.get(x.state, 9), x.pnl_pct or 0)):
        _write_row(ws, [
            p.ticker, "R1", p.sector,
            p.entry_date, _fmt(p.holding_days),
            _fmt(p.entry_price), _fmt(p.current_price), _fmt(p.pnl_pct),
            _fmt(p.stop), _fmt(p.stop_distance_pct),
            p.status_cell, p.action,
            _fmt(p.confidence, CONFIDENCE_NOT_CAPTURED), p.confidence_source,
            p.reason, p.pid,
        ], r, pnl_col_idx=8)
        r += 1
    if not v.r1:
        ws.cell(r, 1, "No R1 advisory positions held.").font = FONT_BODY
        r += 1
    if v.r1_new:
        r += 1
        _sub(ws, "TODAY'S R1 ADVISORY SIGNALS · not positions · no auto-entry",
             len(hdr), r)
        r += 1
        for p in v.r1_new:
            _write_row(ws, [
                p.ticker, "R1", p.sector,
                p.entry_date, 0,
                _fmt(p.entry_price), _fmt(p.current_price), "—",
                "—", "—",
                "ADVISORY SIGNAL", p.action,
                _fmt(p.confidence, CONFIDENCE_NOT_CAPTURED),
                p.confidence_source, p.reason, "—",
            ], r)
            r += 1
    r += 2
    _legend(ws, [
        "R1 is RETIRED_ADVISORY · shown for operator awareness · it opens and "
        "closes nothing automatically.",
        "Suggested Stop · Entry − 2×ATR14 at entry · a SUGGESTION · it is NOT "
        "the canonical dynamic_risk_v2 stop and is not enforced.",
        "Review State · %s NORMAL · %s WATCH (within %s%% of stop or ≤%s%% P&L) "
        "· %s STOP BREACH (price at/below suggested stop) · %s DEEP LOSS "
        "(≤%s%% P&L)." % (_STATE_ICON[STATE_NORMAL], _STATE_ICON[STATE_WATCH],
                          WATCH_STOP_DISTANCE_PCT, WATCH_LOSS_PCT,
                          _STATE_ICON[STATE_BREACH], _STATE_ICON[STATE_DEEP_LOSS],
                          DEEP_LOSS_PCT),
        "Action never exceeds REVIEW · R1 auto-exit is prohibited by V2 §18.",
        "R1 P&L is never mixed into R2 production performance.",
        _confidence_legend(v),
        "Confidence Source · names exactly where the number came from · a value with no stated source is not trustworthy.",
    ], r, len(hdr))
    return len(v.r1)


def emit_r2(wb, v: Views):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    # Same reading order as R1 (identity · position · money · risk ·
    # verdict · evidence) so an operator moving between the two sheets does
    # not have to re-learn the layout. See the R1 note on "Runner".
    hdr = [
        # identity
        "Stock", "Runner", "Sector",
        # position
        "Entry Date", "Holding Days",
        # money
        "Entry Price", "Current Price", "Unrealized P&L %",
        # risk · canonical stop first, it is the decision input
        "Dynamic Stop", "Stop Type", "Distance to Stop %",
        "Target", "Upside to Target %", "Risk:Reward",
        # verdict
        "Status", "Action",
        # evidence
        "Confidence %", "Confidence Source", "Reason", "Position ID",
        "Provenance",
    ]
    ws = wb.create_sheet("R2")
    _banner(ws, "AEGIS %s · R2 · PRODUCTION · as of %s"
            % (v.market.upper(), v.asof), len(hdr))
    _sub(ws, ("Dynamic Stop is the CANONICAL dynamic_risk_v2 value · this "
              "workbook never computes a competing R2 stop."), len(hdr), 2)
    n_missing = sum(1 for p in v.r2 if p.stop is None)
    n_breach = sum(1 for p in v.r2 if p.state == STATE_BREACH)
    _sub(ws, ("Holdings: %d · stop breaches: %d · missing canonical stop: %d"
              % (len(v.r2), n_breach, n_missing)), len(hdr), 3)
    _header(ws, hdr, 5)
    for i, w in enumerate([12, 8, 18, 12, 12, 12, 13, 15, 13, 12, 17,
                            12, 17, 12, 15, 10, 12, 30, 34, 30, 26], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 6
    order = {STATE_DEEP_LOSS: 0, STATE_BREACH: 1, STATE_WATCH: 2, STATE_NORMAL: 3}
    for p in sorted(v.r2, key=lambda x: (order.get(x.state, 9), x.pnl_pct or 0)):
        _write_row(ws, [
            p.ticker, "R2", p.sector,
            p.entry_date, _fmt(p.holding_days),
            _fmt(p.entry_price), _fmt(p.current_price), _fmt(p.pnl_pct),
            _fmt(p.stop, "UNAVAILABLE"), p.stop_type,
            _fmt(p.stop_distance_pct),
            _fmt(p.target), _fmt(p.target_distance_pct), _fmt(p.rr),
            p.status_cell, p.action,
            _fmt(p.confidence, CONFIDENCE_NOT_CAPTURED), p.confidence_source,
            p.reason, p.pid,
            "canonical:Registry+%s+prices" % p.stop_source,
        ], r, pnl_col_idx=8)
        r += 1
    if not v.r2:
        ws.cell(r, 1, "No R2 production holdings.").font = FONT_BODY
        r += 1
    r += 2
    _legend(ws, [
        "R2 is the PRODUCTION runner · these are real tracked positions.",
        "Dynamic Stop · canonical dynamic_risk_v2 output · the single "
        "authoritative stop. R2 and DAILY RECOMMENDATION read the same value; "
        "neither recomputes it.",
        "UNAVAILABLE stop → Action REVIEW · a missing canonical stop is "
        "reported, never replaced with a locally invented number.",
        "Distance to Stop % · (Current − Stop) / Current · sortable risk buffer.",
        "Action · HOLD · EXIT (canonical stop breached) · REVIEW (deep loss or "
        "no canonical stop).",
        "Upside to Target % · (Target − Current) / Current.",
        "Risk:Reward · (Target − Current) / (Current − Stop) · shown only when both the canonical stop and a target exist.",
        _confidence_legend(v),
        "Confidence Source · names exactly where the number came from · a value with no stated source is not trustworthy.",
    ], r, len(hdr))
    return len(v.r2)


def emit_momentum(wb, v: Views):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    mv = v.momentum
    hdr = ["Stock", "Sector", "Category", "Quality", "1d %", "3d %", "5d %",
           "20d %", "RSI-14", "Volume ×", "Engine Verdict", "Terminal State",
           "Reason", "In Production Universe"]
    ws = wb.create_sheet("MOMENTUM")
    _banner(ws, "AEGIS %s · MOMENTUM · upstream research · as of %s"
            % (v.market.upper(), v.asof), len(hdr))
    fresh = "🔴 STALE" if mv.get("stale") else "🟢 FRESH"
    _sub(ws, ("Producer as-of: %s · reporting as-of: %s · %s"
              % (mv.get("producer_asof"), mv.get("reporting_asof"), fresh)),
         len(hdr), 2)
    _sub(ws, ("Momentum is RESEARCH · it never opens a position. A candidate "
              "must pass R2 eligibility to become an R2 entry."), len(hdr), 3)

    # Funnel · declared universe is NEVER labelled "scanned".
    r = 5
    _sub(ws, "UNIVERSE FUNNEL · each stage explains the one below it", len(hdr), r)
    r += 1
    _header(ws, ["Stage", "Count", "Note"], r)
    r += 1
    for label, count, note in [
        ("Declared universe", mv.get("n_declared_universe"),
         "tickers in the configured momentum universe"),
        ("Unreadable price data", mv.get("n_unreadable"),
         "parquet missing or failed to load"),
        ("Insufficient history", mv.get("n_insufficient_history"),
         "fewer than 22 bars · cannot compute 20d return"),
        ("ACTUALLY EVALUATED", mv.get("n_evaluated"),
         "tickers that were genuinely scored"),
        ("No momentum signal", mv.get("n_ignored_no_momentum"),
         "evaluated but below every momentum threshold · a quiet market"),
        ("Momentum candidates", mv.get("n_candidates"),
         "passed a momentum threshold"),
        ("Production universe size", mv.get("n_production_universe"),
         "names R2 is permitted to trade"),
        ("Dropped · outside production universe",
         mv.get("n_out_of_universe_dropped"),
         "candidate had momentum but is not R2-tradable"),
        ("IN-UNIVERSE CANDIDATES", mv.get("n_in_universe_candidates"),
         "carried into the ledger below"),
        ("→ ACCEPTED", mv.get("n_accepted"), "momentum verdict: entry-worthy"),
        ("→ WATCH", mv.get("n_watch"), "monitor · not entry-worthy today"),
        ("→ AVOID / REJECTED", mv.get("n_rejected"), "explicitly rejected"),
        ("→ NO EVIDENCE", mv.get("n_no_evidence"),
         "insufficient quality evidence to classify"),
    ]:
        _write_row(ws, [label, _fmt(count), note], r)
        r += 1
    r += 1
    _sub(ws, ("Conservation check (candidates == sum of terminal states): %s"
              % ("PASS" if mv.get("conservation_ok") else "FAIL")), len(hdr), r)
    r += 2

    _sub(ws, "IN-UNIVERSE CANDIDATES · classified", len(hdr), r)
    r += 1
    _header(ws, hdr, r)
    for i, w in enumerate([12, 18, 16, 10, 9, 9, 9, 9, 9, 10, 18, 16, 44, 20], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r += 1
    for e in mv.get("entries") or []:
        _write_row(ws, [
            str(e.get("ticker", "")).upper().split(".", 1)[0],
            _fmt(e.get("sector")), _fmt(e.get("category")),
            _fmt(e.get("quality_band")), _fmt(e.get("return_1d_pct")),
            _fmt(e.get("return_3d_pct")), _fmt(e.get("return_5d_pct")),
            _fmt(e.get("return_20d_pct")), _fmt(e.get("rsi_14")),
            _fmt(e.get("volume_ratio")), _fmt(e.get("verdict_engine")),
            _fmt(e.get("terminal_state")), _fmt(e.get("reason_text")), "YES",
        ], r)
        r += 1
    if not (mv.get("entries") or []):
        ws.cell(r, 1, ("No in-universe momentum candidates today.")).font = FONT_BODY
        r += 1

    # Out-of-universe candidates · shown so "0 candidates" is never ambiguous
    # between a quiet market and a universe filter removing everything.
    oou = mv.get("out_of_universe") or []
    if oou:
        r += 1
        _sub(ws, ("CANDIDATES FOUND BUT OUTSIDE THE PRODUCTION UNIVERSE · %d · "
                  "real momentum · not R2-tradable · shown so a zero above is "
                  "never mistaken for a quiet market" % len(oou)), len(hdr), r)
        r += 1
        for c in oou:
            _write_row(ws, [
                str(c.get("ticker", "")).upper().split(".", 1)[0],
                _fmt(c.get("sector")), _fmt(c.get("category")),
                _fmt(c.get("quality_band")), _fmt(c.get("return_1d_pct")),
                _fmt(c.get("return_3d_pct")), _fmt(c.get("return_5d_pct")),
                _fmt(c.get("return_20d_pct")), _fmt(c.get("rsi_14")),
                _fmt(c.get("volume_ratio")), _fmt(c.get("verdict")),
                "NOT CLASSIFIED", _fmt(c.get("reason")), "NO",
            ], r)
            r += 1
    r += 2
    th = mv.get("thresholds") or {}
    _legend(ws, [
        "'Declared universe' is NOT 'scanned' · only ACTUALLY EVALUATED "
        "counts tickers that were genuinely scored.",
        "Thresholds are UNCHANGED production values and are never lowered to "
        "manufacture candidates: %s" % (json.dumps(th) if th else "unavailable"),
        "Momentum never opens a position · production_impact is null by design.",
        "A candidate reaches R2 only through R2 eligibility · see the "
        "reconciliation block on DAILY RECOMMENDATION.",
        "STALE means the producer's as-of date is older than this report's "
        "as-of date · the rows are not today's market.",
    ], r, len(hdr))
    return mv.get("n_in_universe_candidates") or 0


def emit_daily_recommendation(wb, v: Views):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    hdr = ["Source", "Stock", "Sector", "Status",
           "Current Price", "P&L %",
           "Stop", "Distance to Stop %", "Target",
           "Action", "Lifecycle", "Confidence %", "Why"]
    ws = wb.create_sheet("DAILY RECOMMENDATION")
    _banner(ws, "AEGIS %s · DAILY RECOMMENDATION · what to do today · %s"
            % (v.market.upper(), v.asof), len(hdr))

    rows = []
    # Precedence when the same stock appears twice: R2 (production, real
    # money) outranks R1 (advisory) outranks Momentum (research). One stock,
    # one recommendation row.
    seen = set()
    for p in sorted(v.r2, key=lambda x: (x.state != STATE_DEEP_LOSS,
                                          x.state != STATE_BREACH,
                                          x.pnl_pct or 0)):
        seen.add(p.ticker)
        rows.append(["R2", p.ticker, p.sector, p.status_cell,
                     _fmt(p.current_price), _fmt(p.pnl_pct),
                     _fmt(p.stop, "UNAVAILABLE"), _fmt(p.stop_distance_pct),
                     _fmt(p.target), p.action,
                     "R2 ACTIVE · held %s d" % _fmt(p.holding_days),
                     _fmt(p.confidence, CONFIDENCE_NOT_CAPTURED), p.reason])
    for p in sorted(v.r1, key=lambda x: (x.state != STATE_DEEP_LOSS,
                                          x.state != STATE_BREACH,
                                          x.pnl_pct or 0)):
        if p.ticker in seen:
            continue
        seen.add(p.ticker)
        rows.append(["R1", p.ticker, p.sector, p.status_cell,
                     _fmt(p.current_price), _fmt(p.pnl_pct),
                     _fmt(p.stop), _fmt(p.stop_distance_pct), "—", p.action,
                     "R1 ADVISORY · held %s d" % _fmt(p.holding_days),
                     _fmt(p.confidence, CONFIDENCE_NOT_CAPTURED), p.reason])
    for p in v.r1_new:
        if p.ticker in seen:
            continue
        seen.add(p.ticker)
        # CEO 2026-09-07 · today's INVESTABLE recommendations must be
        # identifiable as NEW on the daily sheet, not blended into the
        # held-position rows. Lifecycle states plainly that they are
        # candidates so no one reads them as open positions.
        rows.append(["R1", p.ticker, p.sector, "🟢 NEW · INVESTABLE",
                     _fmt(p.current_price), "—", "—", "—", "—",
                     p.action if str(p.action).upper().startswith("NEW")
                     else "NEW · REVIEW",
                     "NEW CANDIDATE · not a position · no auto-entry",
                     _fmt(p.confidence, CONFIDENCE_NOT_CAPTURED), p.reason])
    for e in (v.momentum.get("entries") or []):
        tk = str(e.get("ticker", "")).upper().split(".", 1)[0]
        if tk in seen:
            continue
        seen.add(tk)
        st = str(e.get("terminal_state", "")).upper()
        icon = {"ACCEPTED": "🟢", "WATCH": "🟡"}.get(st, "⚪")
        rows.append(["Momentum", tk, str(e.get("sector") or "UNKNOWN"),
                     "%s %s" % (icon, st or "UNCLASSIFIED"),
                     "—", "—", "—", "—", "—",
                     "REVIEW" if st == "ACCEPTED" else "WATCH",
                     "Momentum candidate · upstream research · not an R2 entry",
                     CONFIDENCE_NOT_CAPTURED,
                     str(e.get("reason_text") or "")[:90]])

    attention = sum(1 for p in v.r1 + v.r2
                    if p.state in (STATE_BREACH, STATE_DEEP_LOSS))
    _sub(ws, ("%d row(s) · %d position(s) need attention (stop breach or deep "
              "loss) · R2 production %d · R1 advisory %d · momentum candidates %d"
              % (len(rows), attention, len(v.r2), len(v.r1),
                 v.momentum.get("n_in_universe_candidates") or 0)), len(hdr), 2)
    dr = v.daily_recs or {}
    _rec_line = ("Daily recommendations · as-of %s · %s scored · %s investable "
                 "(NEW_POSITION) · %s"
                 % (dr.get("asof"), dr.get("n"),
                    len(dr.get("new_positions") or []),
                    "🔴 STALE" if dr.get("stale") else "🟢 FRESH"))
    _sub(ws, _rec_line, len(hdr), 3)
    r_note = 4
    if v.blockers:
        _sub(ws, "⚠ BLOCKERS: " + " || ".join(v.blockers), len(hdr), r_note)
    else:
        _sub(ws, "✅ No data blockers · every canonical source present and fresh.",
             len(hdr), r_note)
    _header(ws, hdr, 5)
    for i, w in enumerate([12, 12, 18, 20, 13, 11, 13, 17, 12, 10, 30,
                            12, 46], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 6
    for row in rows:
        _write_row(ws, row, r, pnl_col_idx=6)
        r += 1
    if not rows:
        ws.cell(r, 1, "Nothing actionable today.").font = FONT_BODY
        r += 1

    # Momentum -> R2 lifecycle reconciliation · embedded here rather than in
    # its own tab, per the five-sheet directive.
    rec = v.reconciliation
    r += 2
    _sub(ws, "MOMENTUM → R2 LIFECYCLE RECONCILIATION", len(hdr), r)
    r += 1
    _header(ws, ["Stage", "Count", "Where the rest went"], r)
    r += 1
    for label, count, note in rec.get("stages", []):
        _write_row(ws, [label, _fmt(count), note], r)
        r += 1
    r += 1
    if rec.get("mismatches"):
        for msg in rec["mismatches"]:
            _sub(ws, "⚠ " + msg, len(hdr), r)
            r += 1
    else:
        _sub(ws, "✅ No unexplained losses between momentum and R2.", len(hdr), r)
        r += 1
    r += 2
    _legend(ws, [
        "This is the primary daily sheet · one stock, one recommendation row.",
        "Source · R2 production (real positions) · R1 advisory (no auto-exit) "
        "· Momentum upstream research (never a position).",
        "Stop for R2 rows is the canonical dynamic_risk_v2 value · identical to "
        "the R2 sheet by construction, not by convention.",
        "R1 rows show a SUGGESTED stop · advisory only · never auto-exited.",
        "Momentum ACCEPTED is not an R2 entry · R2 eligibility is a separate "
        "gate and is never bypassed by copying momentum into R2.",
        "Reconciliation shows every stage from declared universe to R2 ACTIVE "
        "so a candidate can never disappear silently.",
        "NEW rows are the daily engine's INVESTABLE verdict (action = "
        "NEW_POSITION). They are candidates, NOT positions · nothing is "
        "opened automatically, and they never enter R2 without passing R2 "
        "eligibility.",
        _confidence_legend(v),
    ], r, len(hdr))
    return len(rows)


def emit_exit(wb, v: Views):
    from scripts.build_aegis_3sheet_workbook import (
        _banner, _sub, _header, _write_row, _legend, FONT_BODY)
    from openpyxl.utils import get_column_letter

    hdr = [
        # identity
        "Source", "Stock", "Sector",
        # position
        "Entry Date", "Exit Date", "Holding Days",
        # money
        "Entry Price", "Exit Price", "Realized P&L %",
        # outcome
        "Exit Reason", "Return Since Exit %",
        "Relative Opportunity vs Rotation (pp)",
        # evidence
        "Classification", "Position ID",
    ]
    ws = wb.create_sheet("EXIT")
    _banner(ws, "AEGIS %s · EXIT · unified realized history · 90d · as of %s"
            % (v.market.upper(), v.asof), len(hdr))
    n_r2 = sum(1 for e in v.exits if e.source == "R2" and e.classification == "production")
    n_r1 = sum(1 for e in v.exits if e.source == "R1")
    n_admin = sum(1 for e in v.exits if e.classification == "administrative")
    _sub(ws, ("Total %d · R2 production %d · R1 advisory %d · administrative %d "
              "· Momentum 0 (momentum never opens a position, so it can never "
              "produce an exit)"
              % (len(v.exits), n_r2, n_r1, n_admin)), len(hdr), 2)
    _sub(ws, ("R1 and administrative rows are shown for completeness and are "
              "EXCLUDED from R2 production performance."), len(hdr), 3)
    _header(ws, hdr, 5)
    for i, w in enumerate([10, 12, 18, 12, 12, 12, 12, 12, 15, 26, 18, 20,
                            16, 30], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 6
    for e in v.exits:
        _write_row(ws, [
            "R1 · ADVISORY" if e.source == "R1" else e.source,
            e.ticker, e.sector,
            e.entry_date, e.exit_date, _fmt(e.holding_days),
            _fmt(_money(e.entry_price), "UNAVAILABLE"),
            _fmt(_money(e.exit_price), "UNAVAILABLE"),
            _fmt(e.realized_pnl_pct),
            e.exit_reason, _fmt(e.subsequent_return_pct), _fmt(e.relative_pp),
            e.classification, e.pid,
        ], r, pnl_col_idx=9)
        r += 1
    if not v.exits:
        ws.cell(r, 1, "No exits in the last 90 days.").font = FONT_BODY
        r += 1

    # MONTHLY SUMMARY · embedded here rather than on its own tab, per the
    # five-sheet directive. Delivery Contract v1 required this to be a
    # SEPARATE sheet specifically so it could never be mistaken for more
    # Exit History rows; under the five-sheet layout it is a clearly
    # headed block instead. R2 production only · R1 advisory and
    # administrative events are excluded so they cannot inflate production
    # win rate.
    prod = [e for e in v.exits
            if e.source == "R2" and e.classification == "production"
            and e.realized_pnl_pct is not None]
    by_month: dict = {}
    for e in prod:
        key = (e.exit_date or "")[:7]
        if len(key) != 7:
            continue
        by_month.setdefault(key, []).append(e.realized_pnl_pct)
    r += 2
    _sub(ws, ("MONTHLY SUMMARY · realized R2 production exits only · "
              "R1 advisory and administrative events excluded"), len(hdr), r)
    r += 1
    _header(ws, ["Month", "Exits", "Wins", "Losses", "Win Rate %",
                 "Avg Realized P&L %", "Best %", "Worst %"], r)
    r += 1
    for month in sorted(by_month, reverse=True):
        vals = by_month[month]
        wins = sum(1 for x in vals if x > 0)
        losses = sum(1 for x in vals if x < 0)
        _write_row(ws, [
            month, len(vals), wins, losses,
            round(wins / len(vals) * 100, 1) if vals else "—",
            round(sum(vals) / len(vals), 2) if vals else "—",
            round(max(vals), 2) if vals else "—",
            round(min(vals), 2) if vals else "—",
        ], r, pnl_col_idx=6)
        r += 1
    if not by_month:
        ws.cell(r, 1, ("No priced R2 production exits in the window · "
                       "no monthly summary to compute.")).font = FONT_BODY
        r += 1
    r += 2
    _legend(ws, [
        "One unified exit history across R1 · R2 · Momentum · 90-day rolling.",
        "MONTHLY SUMMARY covers realized R2 production exits only · this is a "
        "'realized 90d' scope, NOT a count of current holdings.",
        "Realized P&L % · (Exit − Entry) / Entry · the trade's own result.",
        "Return Since Exit % · price move from the exit price to today · "
        "positive means the stock kept rising after we sold (exit cost us) · "
        "negative means the exit protected capital.",
        "Relative Opportunity pp · rotation benefit vs the closed position · "
        "percentage points · this is NOT the trade's own P&L.",
        "Classification · production (R2 real trade) · advisory (R1 · never "
        "counted in production P&L) · administrative (same-day / zero-delta "
        "bookkeeping event · not a real trade).",
        "UNAVAILABLE means the canonical price source had no value · never "
        "fabricated and never silently zeroed.",
        "Momentum contributes no exits by design · it is research-only and "
        "opens no positions.",
    ], r, len(hdr))
    return len(v.exits)


def build_five_sheet_workbook(market: str, root: Path, asof: str,
                              reg_data: dict, momentum_ledger: dict) -> dict:
    """Build the five-sheet workbook · returns a summary dict."""
    from openpyxl import Workbook

    v = build_views(root, market, asof, reg_data, momentum_ledger)
    wb = Workbook()
    wb.remove(wb.active)
    n_r1 = emit_r1(wb, v)
    n_r2 = emit_r2(wb, v)
    n_mom = emit_momentum(wb, v)
    n_daily = emit_daily_recommendation(wb, v)
    n_exit = emit_exit(wb, v)

    assert wb.sheetnames == FIVE_SHEETS, (
        "five-sheet contract violated: %s" % wb.sheetnames)

    return {
        "workbook": wb,
        "views": v,
        "market": market.lower(),
        "asof": asof,
        "sheets": list(wb.sheetnames),
        "r1_positions": n_r1,
        "r1_signals_today": len(v.r1_new),
        "r2_positions": n_r2,
        "momentum_candidates": n_mom,
        "daily_recommendation_rows": n_daily,
        "exit_rows": n_exit,
        "r1_stop_breaches": sum(
            1 for p in v.r1 if p.state in (STATE_BREACH, STATE_DEEP_LOSS)),
        "r2_stop_breaches": sum(1 for p in v.r2 if p.state == STATE_BREACH),
        "r2_missing_canonical_stop": sum(1 for p in v.r2 if p.stop is None),
        "momentum_stale": bool(v.momentum.get("stale")),
        "momentum_producer_asof": v.momentum.get("producer_asof"),
        "reconciliation_mismatches": v.reconciliation.get("mismatches", []),
        "blockers": v.blockers,
    }
