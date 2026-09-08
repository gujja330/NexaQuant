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


def is_investable(action: str) -> bool:
    return (action in CURRENT_ACTIONS
            and str(action).upper() not in NON_INVESTABLE_STATES)


def _num(x, nd=4) -> Optional[float]:
    try:
        return round(float(x), nd) if x is not None else None
    except (TypeError, ValueError):
        return None


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

    current, exits, filtered = [], [], []

    def _conf(o):
        c = getattr(o, "initial_score", None)
        if isinstance(c, (int, float)):
            return round(float(c) * 100, 1) if 0 <= c <= 1 else round(float(c), 1)
        return None

    def _emit_current(o, engine: str):
        action = classify_action(o.status, o.initial_signal,
                                 o.created_date, asof)
        sig = str(o.initial_signal or "")
        if not is_investable(action):
            filtered.append({"ticker": str(o.ticker).upper().split(".", 1)[0],
                             "engine": engine, "action": action,
                             "signal": sig,
                             "reason": "action is not investable"})
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
        dist = round((curr - stop) / curr * 100, 2) if (stop is not None and curr) else None
        worst = round((stop / entry - 1.0) * 100, 2) if (stop is not None and entry) else None
        current.append({
            "market": m.upper(),
            "ticker": str(o.ticker).upper().split(".", 1)[0],
            "engine": engine, "action": action,
            "entry_date": o.created_date or "",
            "entry_price": _num(entry, 2), "current_price": _num(curr, 2),
            "pnl_pct": pnl, "confidence_pct": _conf(o),
            "stop": stop, "stop_basis": basis,
            "dist_to_stop_pct": dist, "max_loss_if_stop_pct": worst,
            "target": _num(target, 2),
            "position_id": getattr(o, "opportunity_id", ""),
            "holding_days": days,
            "reason": ("R1 ADVISORY · stop is SUGGESTED only · never auto-exited"
                       if engine == ENGINE_R1
                       else f"{sig or 'signal'} · held {days if days is not None else '?'}d "
                            f"· stop {basis}"),
            "source": "registry:active",
        })

    for o in (reg_data.get("active") or []):
        _emit_current(o, ENGINE_R2)
    for o in (_load_r1_active_for_investments(root, m) or []):
        _emit_current(o, ENGINE_R1)

    # MOMENTUM · never opens a position. The ledger sets
    # production_impact=null on every entry by design, so a momentum name
    # is investable only once it has become an R2 position - at which
    # point it is already an R2 row above. Nothing is forced in.
    n_mom = 0

    def _emit_exits(opps, engine, source):
        for o in opps or []:
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

    # Deterministic ordering · NEW, ACTIVE+, ACTIVE; R2 > MOMENTUM > R1.
    _a = {ACTION_NEW: 0, ACTION_ACTIVE_PLUS: 1, ACTION_ACTIVE: 2}
    _e = {ENGINE_R2: 0, ENGINE_MOM: 1, ENGINE_R1: 2}
    current.sort(key=lambda r: (_a.get(r["action"], 9), _e.get(r["engine"], 9),
                                -(r["pnl_pct"] or 0), r["ticker"]))
    exits.sort(key=lambda e: (e["exit_date"] or "", e["ticker"]), reverse=True)

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
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "market": m, "asof": asof,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts, "current": current, "exits": exits,
        "filtered_out": filtered,
    }


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
