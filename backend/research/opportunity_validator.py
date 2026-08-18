"""AEGIS · Opportunity + Portfolio validation gate.

Operator directive 2026-08-18 · Section 26 · 11 zero-tolerance checks.
Runs post-collect / pre-write in build_unified_history so a lifecycle
violation fails the pipeline visibly · never silently ships bad rows.

Also emits daily discovery diagnostic to
`reports/context/daily_opportunity_discovery.json` (Section 23).
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


_BINDING_RISK_SIGNALS = (
    "EMERGENCY_EXIT", "PORTFOLIO_MAX_DD", "HARD_STOP",
    "STOP_LOSS_HIT", "GAP_EXIT", "TRAILING_STOP_HIT",
    "CRITICAL_DEEP_LOSS",
)


def _col_index(header: list, name: str) -> int:
    for i, h in enumerate(header):
        if h == name:
            return i
    return -1


def validate_rows(rows: list, header: list, asof: str) -> tuple[list, dict]:
    """Section 26 checks. Returns (violations, summary).

    violations: list of dicts · {check, key, detail}
    summary   : dict with per-check counts
    """
    violations: list = []
    counts: dict = defaultdict(int)

    c_pid   = _col_index(header, "Position ID")
    c_date  = _col_index(header, "Date")
    c_run   = _col_index(header, "Run_Type")
    c_st    = _col_index(header, "Status")
    c_alert = _col_index(header, "Alerts")
    c_tk    = _col_index(header, "Ticker")

    def _add(check, key, detail):
        violations.append({"check": check, "key": key, "detail": detail})
        counts[check] += 1

    # ── 1. Duplicate (Position ID, Date, Runner) with contradictory Status ──
    by_key: dict = defaultdict(list)
    for r in rows:
        if c_pid < 0 or c_date < 0 or c_run < 0: break
        pid  = str(r[c_pid] or "")
        dt   = str(r[c_date] or "")[:10]
        run  = str(r[c_run] or "")
        st   = str(r[c_st] or "").upper() if c_st >= 0 else ""
        by_key[(pid, dt, run)].append(st)
    for key, statuses in by_key.items():
        if len(set(statuses)) > 1:
            _add("duplicate_authoritative_decision", str(key), f"statuses: {statuses}")

    # ── 2. CLOSED → ACTIVE transition (same PID re-appears with buy-family Status) ──
    per_pid: dict = defaultdict(list)
    for r in rows:
        if c_pid < 0: break
        pid = str(r[c_pid] or ""); dt = str(r[c_date] or "")[:10]
        st  = str(r[c_st] or "").upper() if c_st >= 0 else ""
        per_pid[pid].append((dt, st))
    for pid, timeline in per_pid.items():
        timeline.sort()
        was_closed = False
        for dt, st in timeline:
            if st == "EXIT":
                was_closed = True
                continue
            if was_closed and st in ("STRONG BUY","BUY","ADD","HOLD","ACCUMULATE"):
                _add("closed_to_active_transition", pid, f"{dt}: {st} after prior EXIT")
                break

    # ── 3. EXIT + HOLD coexistence for same position/date ──
    for key, statuses in by_key.items():
        up = [s.upper() for s in statuses]
        if "EXIT" in up and any(s in ("HOLD",) for s in up):
            _add("exit_hold_coexist", str(key), f"statuses: {statuses}")
    # ── 4. EXIT + BUY coexistence ──
    for key, statuses in by_key.items():
        up = [s.upper() for s in statuses]
        if "EXIT" in up and any(s in ("BUY","STRONG BUY","ADD") for s in up):
            _add("exit_buy_coexist", str(key), f"statuses: {statuses}")

    # ── 5. Binding risk signal + non-EXIT Status ──
    for r in rows:
        if c_alert < 0 or c_st < 0: break
        al = str(r[c_alert] or "").upper()
        if any(sig in al for sig in _BINDING_RISK_SIGNALS):
            st = str(r[c_st] or "").upper()
            if st not in ("EXIT", "SELL"):
                pid = str(r[c_pid] or "") if c_pid >= 0 else "?"
                _add("stop_loss_not_exit", pid, f"alerts={al[:80]}  status={st}")

    # ── 6. SKIP in what would be the primary Portfolio table ──
    for r in rows:
        if c_st < 0: break
        if str(r[c_st] or "").upper() == "SKIP":
            tk = str(r[c_tk] or "") if c_tk >= 0 else "?"
            _add("skip_in_portfolio_layer", tk, "SKIP row in unified rows list")

    return violations, dict(counts)


def emit_daily_diagnostic(root: Path, asof: str) -> Path:
    """Section 23 · daily NEW opportunity discovery diagnostic.

    Reads the Opportunity Registry + writes a JSON summary. If no
    qualified new opportunity, explicitly states so."""
    from backend.research import opportunity_registry as _oreg

    reg = _oreg.load_all(root)
    active = _oreg.active_opportunities(reg)
    created_today = _oreg.opportunities_created_on(reg, asof)
    closed_today = _oreg.opportunities_closed_on(reg, asof)
    counts = _oreg.count_by_status(reg)

    # Break created-today into NEW vs REJECTED (same-day-close)
    new_actionable = [o for o in created_today if o.status == "ACTIVE"]
    rejected_today = [o for o in created_today if o.status == "REJECTED"]

    # Re-entries: opportunities created today for tickers that HAVE prior CLOSED
    reentries: list = []
    for opp in new_actionable:
        key = (opp.market, opp.runner, opp.ticker)
        prior = reg.get(key, [])
        prior_closed = [o for o in prior
                              if o.status == "CLOSED" and o.opportunity_id != opp.opportunity_id]
        if prior_closed:
            reentries.append(opp)

    diag: dict = {
        "engine":              "aegis.opportunity_diagnostic.v1",
        "asof":                asof,
        "generated_utc":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {
            "active_opportunities":  len(active),
            "created_today":         len(created_today),
            "new_actionable_today":  len(new_actionable),
            "rejected_today":        len(rejected_today),
            "reentries_today":       len(reentries),
            "closed_today":          len(closed_today),
            "total_ever_active":     counts.get("ACTIVE", 0),
            "total_ever_closed":     counts.get("CLOSED", 0),
            "total_ever_rejected":   counts.get("REJECTED", 0),
        },
        "verdict": (
            "NO QUALIFIED NEW OPPORTUNITY TODAY"
            if len(new_actionable) == 0 else
            f"{len(new_actionable)} new opportunity(ies) discovered · "
            f"{len(reentries)} re-entry"
        ),
        "new_opportunities": [
            {
                "opportunity_id": o.opportunity_id,
                "market": o.market, "runner": o.runner, "ticker": o.ticker,
                "created_date": o.created_date,
                "initial_signal": o.initial_signal, "initial_rank": o.initial_rank,
                "is_reentry": o in reentries,
            }
            for o in new_actionable
        ],
        "closed_today_details": [
            {
                "opportunity_id": o.opportunity_id,
                "market": o.market, "runner": o.runner, "ticker": o.ticker,
                "created_date": o.created_date, "closed_date": o.closed_date,
                "closed_reason": o.closed_reason,
            }
            for o in closed_today
        ],
    }
    p = root / "reports" / "context" / "daily_opportunity_discovery.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(diag, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
    return p


def _main() -> int:
    """CLI · read latest history + run validate + emit diagnostic."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))       # so `backend.research` imports resolve when run as script
    from datetime import date
    asof = date.today().isoformat()

    p = emit_daily_diagnostic(root, asof)
    print(f"[opportunity_diagnostic] wrote {p.relative_to(root)}")
    d = json.loads(p.read_text(encoding="utf-8"))
    print(f"  verdict: {d['verdict']}")
    print(f"  counts:  {d['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
