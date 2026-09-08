"""AEGIS · CANONICAL DAILY LIFECYCLE · the single transformation point.

CEO 2026-09-08:
> "The two-sheet lifecycle must be a first-class downstream stage of the
>  canonical daily pipeline, not an independent workbook-only
>  transformation. The pipeline must generate the canonical lifecycle
>  dataset first and the XLSX must render only that dataset."

    R1 ─┐
    R2 ─┼─► CANONICAL LIFECYCLE ─┬─► CURRENT
   MOM ─┘   (this module)        └─► EXIT EVENTS

WHY THIS EXISTS
---------------
Every delivery defect this month came from a renderer independently
reconstructing state:

  · 01_Investments and 01_Portfolio each computed an R2 stop, and
    disagreed - one said "EXIT · stop hit", the other "HOLD", same
    position, same day
  · momentum was read from a source frozen 11 days
  · Registry-CLOSED tickers "disappeared" because a checker rebuilt the
    exit set from a renamed sheet
  · orphaned producers left the outcome dataset 18% populated

The common cause is that the answer to "what is investable today?" was
being derived in several places. It is now derived HERE, once, and the
workbook renders the result. A renderer that cannot compute cannot
disagree.

DOWNSTREAM-ONLY · THE HARD RULE
-------------------------------
This layer READS R1, R2, Momentum, the Registry, canonical positions and
canonical exit records. It writes NOTHING back into any engine:

    R2  ────► lifecycle          lifecycle ──X──► R2
    MOM ────► lifecycle          lifecycle ──X──► Momentum
    R1  ────► lifecycle          lifecycle ──X──► R1

It computes no trading signal, opens nothing, closes nothing and changes
no threshold. It classifies and aggregates what the engines already
decided. `test_lifecycle_is_downstream_only` enforces this mechanically.

OUTPUT
------
reports/context/canonical_lifecycle_{market}.json
    { asof, market, current: [...], exits: [...], counts: {...},
      filtered_out: [...] }
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.lifecycle.v1"

ENGINE_R1, ENGINE_R2, ENGINE_MOM = "R1", "R2", "MOMENTUM"
ALLOWED_ENGINES = (ENGINE_R1, ENGINE_R2, ENGINE_MOM)

ACTION_NEW, ACTION_ACTIVE, ACTION_ACTIVE_PLUS = "NEW", "ACTIVE", "ACTIVE+"
ACTION_EXIT = "EXIT"
CURRENT_ACTIONS = (ACTION_NEW, ACTION_ACTIVE_PLUS, ACTION_ACTIVE)

# Canonical strengthening family · legacy sender, verbatim
# (scripts/telegram_command_center_send.py ~1654, ~2128, ~2833).
BUY_FAMILY = {"BUY", "STRONG BUY", "ACCUMULATE", "ADD", "BUY BIG"}

NON_INVESTABLE_STATES = {
    "HOLD", "WATCH", "REVIEW", "AVOID", "IGNORE", "NO SIGNAL", "NO_SIGNAL",
    "PUMP_RISK", "MOMENTUM_WATCH", "NO_EVIDENCE", "REJECTED", "DORMANT",
    "BLOCKED", "RESEARCH", "RESEARCH_ONLY", "INSUFFICIENT_SAMPLE",
    "DATA-REQUIRED", "DATA_REQUIRED", "N/A", "NO_MODEL", "NO-MODEL",
    "NON_INVESTABLE", "SUGGESTED", "SHADOW",
}


def classify_action(status: str, initial_signal: str, created_date: str,
                    asof: str) -> str:
    """Canonical NEW / ACTIVE+ / ACTIVE / EXIT · reused, never invented.

    Order matters and matches the legacy sender: EXIT dominates, a
    same-day entry is NEW, the BUY family is ACTIVE+, else ACTIVE.
    """
    st = str(status or "").upper().strip()
    if st in ("CLOSED", "EXIT"):
        return ACTION_EXIT
    if created_date and asof and str(created_date)[:10] == str(asof)[:10]:
        return ACTION_NEW
    if str(initial_signal or "").upper().strip() in BUY_FAMILY:
        return ACTION_ACTIVE_PLUS
    return ACTION_ACTIVE


def is_investable(action: str, initial_signal: str = "") -> bool:
    """CURRENT is investable-only. For a NEW row that means the SIGNAL too.

    CEO 2026-09-08 · "CURRENT contains only investable names · no
    artificial green stocks."

    The registry creates an entry for EVERY recommendation row, including
    HOLD and EXIT ones. `classify_action` then calls anything created
    today NEW, because NEW is defined by entry date, not by conviction.
    While the permanent exited-set bans were in place this never showed;
    releasing the phantom bans exposed it immediately - India produced 11
    NEW rows of which 10 were HOLD and one was EXIT, every one with no
    stop and 0.0% P&L.

    A NEW row is a new recommendation to BUY. If its signal is not in the
    BUY family it is not one, and HOLD is already a declared
    non-investable state. An EXISTING position on a HOLD signal is
    untouched - it stays visible with its real P&L.
    """
    if action not in CURRENT_ACTIONS:
        return False
    if str(action).upper() in NON_INVESTABLE_STATES:
        return False
    if action == ACTION_NEW:
        sig = str(initial_signal or "").upper().strip()
        return sig in BUY_FAMILY
    return True


BREACH_SOURCE = "lifecycle:stop-breach"


def breach_ledger_path(root: Path, market: str) -> Path:
    return (root / "reports" / "context"
            / f"lifecycle_breach_ledger_{market.lower()}.jsonl")


def load_breach_ledger(root: Path, market: str) -> dict:
    """position_id -> the day its stop was FIRST seen broken.

    A breach is LATCHED, and that is the whole reason this file exists.
    The exit set is rebuilt from scratch on every run, so without a latch
    the transition would be reversible: a position that breached yesterday
    and ticked back above its stop today would silently leave EXIT HISTORY
    and reappear in CURRENT. A permanent record that can un-record an exit
    is not permanent, and that is the same class of silent restatement
    this whole layer exists to remove.

    Recovering back above the stop does not undo the fact that the stop
    was passed. First observation wins and is never rewritten.
    """
    p = breach_ledger_path(root, market)
    out: dict = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue                    # a torn line must not hide a breach
        pid = str(r.get("position_id") or "")
        if pid and pid not in out:
            out[pid] = r
    return out


def record_breaches(root: Path, market: str, rows: list, asof: str) -> int:
    """Append first-time breaches. Idempotent - a position_id is written once.

    This writes lifecycle-owned state only. It opens nothing, closes
    nothing, and touches no engine or registry: the position stays exactly
    as R1/R2 left it.
    """
    known = load_breach_ledger(root, market)
    new = [r for r in rows
           if r.get("position_id") and r["position_id"] not in known]
    if not new:
        return 0
    p = breach_ledger_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in new:
            fh.write(json.dumps({
                "position_id": r["position_id"], "ticker": r["ticker"],
                "market": r["market"], "engine": r["engine"],
                "entry_date": r["entry_date"], "breach_date": str(asof)[:10],
                "stop": r["stop"], "stop_basis": r["stop_basis"],
                "price_at_breach": r["current_price"],
                "pnl_at_breach_pct": r["pnl_pct"],
                "recorded_utc": datetime.now(timezone.utc)
                                .isoformat(timespec="seconds"),
            }, default=str) + "\n")
    return len(new)


def _num(x, nd=4) -> Optional[float]:
    try:
        return round(float(x), nd) if x is not None else None
    except (TypeError, ValueError):
        return None


# Inputs whose staleness would make CURRENT a lie. Each is (label,
# path-template, critical). A CRITICAL input dated before the report's
# as-of means the sheet is presenting old decisions as today's.
_FRESHNESS_INPUTS = (
    ("recommendations_v3", "reports/recommendations_v3.json",
     "usa/reports/recommendations_v3.json", True),
    ("ensemble", "reports/ensemble.json", "usa/reports/ensemble.json", True),
    ("dynamic_risk", "reports/context/dynamic_risk_india.json",
     "reports/context/dynamic_risk_usa.json", True),
)


def _artifact_asof(p: Path):
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    for k in ("asof", "as_of", "date", "reporting_date"):
        v = d.get(k)
        if v:
            return str(v)[:10]
    ru = d.get("run_utc") or d.get("generated_utc")
    return str(ru)[:10] if ru else None


def input_freshness(root: Path, market: str, asof: str) -> list:
    """CEO 2026-09-08 · "Reject stale inputs from becoming CURRENT."

    India's recommendation artifact sat at 2026-09-03 for five days while
    CURRENT was rebuilt every cycle and said nothing. A sheet built from a
    five-day-old decision set is not wrong-looking - it looks exactly like
    a correct sheet, which is why this has to be measured rather than
    noticed.
    """
    out = []
    for label, ind_rel, usa_rel, critical in _FRESHNESS_INPUTS:
        rel = usa_rel if market.lower() == "usa" else ind_rel
        p = root / rel
        a = _artifact_asof(p)
        age = None
        if a:
            try:
                age = (date.fromisoformat(str(asof)[:10])
                       - date.fromisoformat(a)).days
            except Exception:
                age = None
        out.append({
            "input": label, "path": rel, "asof": a,
            "age_days": age, "critical": critical,
            "verdict": ("MISSING" if a is None else
                        "STALE" if (age or 0) > 0 else "FRESH"),
        })
    return out


def compute(root: Path, market: str, asof: str) -> dict:
    """Build the canonical lifecycle dataset for one market."""
    from scripts.build_aegis_3sheet_workbook import (
        _load_registry, _load_r1_active_for_investments, _load_dynamic_risk,
        _close_on_or_before, _normalize_exit_reason, _target_from_registry,
        _atr14_at_date, _target_from_atr_fallback,
    )
    from backend.delivery.canonical.retirement import retired_runners

    m = market.lower()
    retired = retired_runners(root)
    reg_data = _load_registry(root, m, retired)
    # CANONICAL R2 STOP · the one source. Nothing downstream recomputes it.
    dr_by_pid = _load_dynamic_risk(root, m)

    current, exits, filtered, breached = [], [], [], []
    latched = load_breach_ledger(root, m)

    def _conf(o):
        c = getattr(o, "initial_score", None)
        if isinstance(c, (int, float)):
            return round(float(c) * 100, 1) if 0 <= c <= 1 else round(float(c), 1)
        return None

    def _emit_current(o, engine: str):
        action = classify_action(o.status, o.initial_signal,
                                 o.created_date, asof)
        sig = str(o.initial_signal or "")
        if not is_investable(action, o.initial_signal):
            filtered.append({"ticker": str(o.ticker).upper().split(".", 1)[0],
                             "engine": engine, "action": action,
                             "signal": sig,
                             "reason": ("NEW without a BUY-family signal"
                                        if action == ACTION_NEW
                                        else "action is not investable")})
            return
        entry = _close_on_or_before(root, o.ticker, m, o.created_date or "")
        curr = _close_on_or_before(root, o.ticker, m, asof)
        pnl = round((curr / entry - 1.0) * 100, 2) if (entry and curr and entry > 0) else None

        # STOP · engine-bound by governance.
        #   R2 · canonical dynamic_risk_v2, ENFORCED.
        #   R1 · ADVISORY ATR-14 only. R1 carries no dynamic-exit
        #        protection (V2 §18); giving it an enforced stop would turn
        #        R1 into R2. Displayed so the downside is visible, never
        #        enforced.
        stop, basis = None, "none"
        if engine == ENGINE_R2:
            dr = dr_by_pid.get(getattr(o, "opportunity_id", "")) or {}
            stop = _num(dr.get("stop"))
            basis = "dynamic_risk_v2 · ENFORCED" if stop is not None else "none"
        elif engine == ENGINE_R1 and entry:
            atr = _atr14_at_date(root, m, o.ticker, o.created_date or asof)
            if atr and atr > 0:
                stop = _num(float(entry) - 2.0 * float(atr))
                basis = "ATR14 SUGGESTED · advisory · NOT enforced"

        target = _target_from_registry(o)
        if not target and entry:
            target = _target_from_atr_fallback(
                entry, _atr14_at_date(root, m, o.ticker, o.created_date or asof),
                m_target=3.0)
        days = None
        try:
            days = (date.fromisoformat(asof)
                    - date.fromisoformat(o.created_date)).days
        except Exception:
            pass
        # STOP STATE · CEO 2026-09-08, from the visual audit of the first
        # generated workbook.
        #
        # Nine R1 rows were ALREADY BELOW their advisory stop and nothing
        # said so (India LUPIN -12.66% at 9.97% past its stop · USA EIX
        # -20.50% at 16.85% past it). R1 carries no enforced exit by
        # governance and that does not change here - but a breach that is
        # invisible is the difference between "advisory" and "unmonitored".
        # The breach is now an explicit column, NOT a new Action value, so
        # the NEW/ACTIVE/ACTIVE+ contract is preserved exactly.
        dist = round((curr - stop) / curr * 100, 2) if (stop is not None and curr) else None
        if stop is None:
            stop_state = "NO STOP"
        elif dist is not None and dist < 0:
            stop_state = "BREACHED"
        else:
            stop_state = "INTACT"

        # `max_loss_if_stop_pct` answers "how much can I still lose if the
        # stop fires?". That question only has meaning while the stop is
        # INTACT. Once price is through it the stop did not protect, and
        # quoting (stop/entry - 1) understates the damage - LUPIN showed
        # -3.95% against an actual -12.66%. When breached the field is
        # therefore None and the real loss is the P&L column.
        worst = None
        if stop is not None and entry and stop_state == "INTACT":
            worst = round((stop / entry - 1.0) * 100, 2)
        row = {
            "market": m.upper(),
            "ticker": str(o.ticker).upper().split(".", 1)[0],
            "engine": engine, "action": action,
            "entry_date": o.created_date or "",
            "entry_price": _num(entry, 2), "current_price": _num(curr, 2),
            "pnl_pct": pnl, "confidence_pct": _conf(o),
            "stop": stop, "stop_basis": basis, "stop_state": stop_state,
            "dist_to_stop_pct": dist, "max_loss_if_stop_pct": worst,
            "target": _num(target, 2),
            "position_id": getattr(o, "opportunity_id", ""),
            "holding_days": days,
            "reason": (
                ("⚠ STOP BREACHED · REVIEW · " if stop_state == "BREACHED" else "")
                + ("R1 ADVISORY · suggested stop only · never auto-exited"
                   if engine == ENGINE_R1
                   else f"{sig or 'signal'} · held {days if days is not None else '?'}d "
                        f"· stop {basis}")),
            "source": "registry:active",
        }
        # BREACHED IS AN EXIT TRANSITION - CEO 2026-09-08.
        #
        # > "Breached means EXIT transition, not CURRENT. Keeping a
        # >  breached R1 position in CURRENT was wrong for the
        # >  investor-facing lifecycle."
        #
        # CURRENT answers "what is investable now?". A position trading
        # BELOW its stop is not investable, whatever the engine does with
        # it, so it leaves the sheet. This is lifecycle presentation and
        # nothing else: R1 keeps its advisory status, is still never
        # auto-exited, and no registry record is written. The row carries
        # its breach reason and its P&L into EXIT HISTORY so the loss
        # stays visible rather than merely disappearing from the view.
        _latch = latched.get(row["position_id"])
        if stop_state == "BREACHED" or _latch:
            if _latch and stop_state != "BREACHED":
                # Price recovered above the stop after the latch was set.
                # The exit stands - see load_breach_ledger.
                row["stop_state"] = "BREACHED"
                row["breach_recovered"] = True
            breached.append(row)
        else:
            current.append(row)

    for o in (reg_data.get("active") or []):
        _emit_current(o, ENGINE_R2)
    for o in (_load_r1_active_for_investments(root, m) or []):
        _emit_current(o, ENGINE_R1)

    # MOMENTUM · never opens a position. The ledger sets
    # production_impact=null on every entry by design, so a momentum name
    # is investable only once it has become an R2 position - at which
    # point it is already an R2 row above. Nothing is forced in.
    n_mom = 0

    # CEO ruling 2026-09-08 · phantom admissions are registry
    # contamination, not exits.
    #
    # > "They must NOT be recorded as investment exits, stop losses,
    # >  rotation exits, or trading outcomes ... not counted as
    # >  prediction/trading evidence."
    #
    # The 23 HOLD/EXIT positions opened by the admission bug were closed
    # as ADMIN_PHANTOM_ADMISSION_*. They are retained in the registry for
    # audit and excluded from the EXIT HISTORY view, because a position
    # that was never legitimately opened cannot have legitimately exited.
    PHANTOM_CLOSE_PREFIX = "ADMIN_PHANTOM_ADMISSION"
    n_phantom_excluded = 0

    def _emit_exits(opps, engine, source):
        nonlocal n_phantom_excluded
        for o in opps or []:
            if PHANTOM_CLOSE_PREFIX in str(getattr(o, "closed_reason", "") or ""):
                n_phantom_excluded += 1
                continue
            entry = _close_on_or_before(root, o.ticker, m, o.created_date or "")
            exitp = _close_on_or_before(root, o.ticker, m, o.closed_date or "")
            pnl = round((exitp / entry - 1.0) * 100, 2) if (entry and exitp and entry > 0) else None
            days = None
            try:
                days = (date.fromisoformat(o.closed_date)
                        - date.fromisoformat(o.created_date)).days
            except Exception:
                pass
            raw = getattr(o, "closed_reason", "") or ""
            exits.append({
                "exit_date": o.closed_date or "",
                "ticker": str(o.ticker).upper().split(".", 1)[0],
                "market": m.upper(), "engine": engine,
                "entry_date": o.created_date or "",
                "entry_price": _num(entry, 2), "exit_price": _num(exitp, 2),
                "realized_pnl_pct": pnl, "holding_days": days,
                "exit_reason": _normalize_exit_reason(raw) if raw else "",
                "entry_confidence_pct": _conf(o),
                "exit_trigger": raw[:60],
                "position_id": getattr(o, "opportunity_id", ""),
                "source": source,
            })

    _emit_exits(reg_data.get("closed_90d"), ENGINE_R2, "registry:production")
    _emit_exits(reg_data.get("closed_retired_90d"), ENGINE_R1, "registry:advisory")
    _emit_exits(reg_data.get("closed_admin_90d"), ENGINE_R2, "registry:administrative")

    # BREACHED -> EXIT HISTORY.
    #
    # These are MARKS, not fills. The position is still open in its engine
    # (R1 is advisory and never auto-exits), so `exit_price` is today's
    # close and `realized_pnl_pct` is the live P&L. They therefore carry
    # their OWN source: a breach mark must never be mixed into
    # registry:production or registry:advisory, or it would contaminate
    # the realized win-rate and average-return statistics with positions
    # that have not actually been sold.
    n_breach_new = record_breaches(root, m, breached, asof)
    latched = load_breach_ledger(root, m)         # today's latches included
    _closed_pids = {e["position_id"] for e in exits if e.get("position_id")}
    for row in breached:
        pid = row.get("position_id") or ""
        if pid and pid in _closed_pids:
            continue           # a real registry close outranks a mark
        led = latched.get(pid) or {}
        bdate = str(led.get("breach_date") or asof)[:10]
        bdays = None
        try:
            bdays = (date.fromisoformat(bdate)
                     - date.fromisoformat(row["entry_date"])).days
        except Exception:
            pass
        exits.append({
            "exit_date": bdate,
            "ticker": row["ticker"], "market": row["market"],
            "engine": row["engine"], "entry_date": row["entry_date"],
            "entry_price": row["entry_price"],
            "exit_price": row["current_price"],
            "realized_pnl_pct": row["pnl_pct"], "holding_days": bdays,
            "exit_reason": "Stop breached",
            "entry_confidence_pct": row["confidence_pct"],
            "exit_trigger": ("STOP BREACHED - stop %s - %s - MARK, position "
                             "still open in %s"
                             % (row["stop"], row["stop_basis"],
                                row["engine"]))[:120],
            "position_id": pid, "source": BREACH_SOURCE,
            "stop": row["stop"], "stop_basis": row["stop_basis"],
            "breach_recovered": bool(row.get("breach_recovered")),
        })

    # Deterministic ordering · NEW, ACTIVE+, ACTIVE; R2 > MOMENTUM > R1.
    _a = {ACTION_NEW: 0, ACTION_ACTIVE_PLUS: 1, ACTION_ACTIVE: 2}
    _e = {ENGINE_R2: 0, ENGINE_MOM: 1, ENGINE_R1: 2}
    current.sort(key=lambda r: (_a.get(r["action"], 9), _e.get(r["engine"], 9),
                                -(r["pnl_pct"] or 0), r["ticker"]))
    exits.sort(key=lambda e: (e["exit_date"] or "", e["ticker"]), reverse=True)

    # ── canonical sector · attached HERE, at the single transformation
    #    point, so the renderer keeps computing nothing.
    #
    # A19 failed because no exit or current record ever carried a sector
    # at all - it was never "lost in presentation", it was never
    # propagated. The value comes from reports/sector_cache.json, the
    # same canonical source portfolio_source._sector_lookup already uses;
    # no second source is introduced and nothing is derived here.
    #
    # IMPORTANT · this is the CURRENT classification of the company, not
    # the sector as-of the exit date. No PIT sector history exists, and
    # inventing one to fill the column would be fabricating historical
    # data. Unknown stays NOT_AVAILABLE, never guessed.
    _sect = _sector_cache(root, m)
    for _row in current:
        _row["sector"] = _sect.get(_norm_ticker(_row.get("ticker")),
                                   SECTOR_UNAVAILABLE)
    for _row in exits:
        _row["sector"] = _sect.get(_norm_ticker(_row.get("ticker")),
                                   SECTOR_UNAVAILABLE)

    freshness = input_freshness(root, m, asof)
    stale = [f for f in freshness if f["verdict"] != "FRESH"]
    stale_critical = [f for f in stale if f["critical"]]

    counts = {
        "current_total": len(current),
        "r1_investable": sum(1 for r in current if r["engine"] == ENGINE_R1),
        "r2_investable": sum(1 for r in current if r["engine"] == ENGINE_R2),
        "momentum_investable": n_mom,
        "new": sum(1 for r in current if r["action"] == ACTION_NEW),
        "active_plus": sum(1 for r in current if r["action"] == ACTION_ACTIVE_PLUS),
        "active": sum(1 for r in current if r["action"] == ACTION_ACTIVE),
        "exit_history_total": len(exits),
        "filtered_non_investable": len(filtered),
        # Invariant, not a statistic: CURRENT is breach-free by
        # construction. Non-zero here means the routing above broke.
        "stop_breached": sum(1 for r in current if r["stop_state"] == "BREACHED"),
        "no_stop": sum(1 for r in current if r["stop_state"] == "NO STOP"),
        "breach_exits": sum(1 for e in exits if e["source"] == BREACH_SOURCE),
        "breach_exits_r1": sum(1 for e in exits if e["source"] == BREACH_SOURCE
                               and e["engine"] == ENGINE_R1),
        "breach_exits_r2": sum(1 for e in exits if e["source"] == BREACH_SOURCE
                               and e["engine"] == ENGINE_R2),
        "breach_exits_new_today": n_breach_new,
        "phantom_admissions_excluded": n_phantom_excluded,
        "stale_inputs": len(stale),
        "stale_inputs_critical": len(stale_critical),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "market": m, "asof": asof,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts, "current": current, "exits": exits,
        "filtered_out": filtered,
        "input_freshness": freshness,
        "stale_inputs": stale,
    }


# Honest absence · never an empty string, never a guessed sector.
SECTOR_UNAVAILABLE = "NOT_AVAILABLE"


def _norm_ticker(t) -> str:
    return str(t or "").replace(".NS", "").replace(".BO", "").upper().strip()


def _sector_cache(root: Path, market: str) -> dict:
    """The canonical sector map · read-only, never written by this module."""
    import json
    try:
        p = root / "reports" / "sector_cache.json"
        if not p.exists():
            return {}
        d = json.loads(p.read_text(encoding="utf-8"))
        return {_norm_ticker(k): v
                for k, v in (d.get(str(market).lower()) or {}).items() if v}
    except Exception:
        return {}


def artifact_path(root: Path, market: str) -> Path:
    return root / "reports" / "context" / f"canonical_lifecycle_{market.lower()}.json"


def emit(root: Path, rep: dict) -> Path:
    p = artifact_path(root, rep["market"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    """Read the canonical dataset · the ONLY input a renderer may use."""
    p = artifact_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def summary_line(rep: dict) -> str:
    c = rep["counts"]
    return (f"lifecycle:{rep['market']} · CURRENT {c['current_total']} "
            f"(R2 {c['r2_investable']} · MOM {c['momentum_investable']} · "
            f"R1 {c['r1_investable']}) · NEW {c['new']} · ACTIVE+ "
            f"{c['active_plus']} · ACTIVE {c['active']} · EXITS "
            f"{c['exit_history_total']} · filtered {c['filtered_non_investable']}")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AEGIS canonical daily lifecycle")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = compute(root, m, a.asof)
        p = emit(root, rep)
        print(summary_line(rep))
        print(f"    -> {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
