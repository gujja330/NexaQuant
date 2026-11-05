"""CI SELF-HEAL — reconcile the lifecycle with the registry BEFORE validation.

WHY THIS EXISTS
---------------
On 2026-10-02 the USA pipeline entered a deadlock that silenced Telegram for
both markets for a month:

    the opportunity registry closed PLTR (10-09) and BMY (10-12)
      -> canonical_lifecycle_usa.json was frozen at 10-08 and did not know
      -> A23 compared a CURRENT registry against a FROZEN exit history
      -> A23 reported both tickers "silently lost" and failed the delivery tests
      -> the delivery failure skipped the commit that would have refreshed the
         lifecycle
      -> the next run started from the same frozen state and failed identically

The commit condition is now fixed, so state advances again. This script is the
second line of defence: it makes the pipeline SELF-CORRECTING rather than
merely unblocked. Before the delivery tests run, it checks the one invariant
that deadlocked us and repairs it if broken.

    A23:  REGISTRY_CLOSED  -  EXIT_HISTORY  -  ORPHAN_AUDIT  ==  empty
    I6:   REGISTRY_CLOSED  (by position id)  INTERSECT  CURRENT  ==  empty

CEO 2026-10-31 · the second invariant was added after USA was blocked a
second time by the same shape of staleness. A23 alone could not see it: it
compares TICKER strings, and both offending names already appeared in exit
history under an earlier, orphan-closed episode. Keying on the position id
makes a re-entry's close visible, because a position id is unique per
episode and cannot be satisfied by another episode of the same name.

WHAT IT WILL AND WILL NOT DO
----------------------------
It regenerates DERIVED artifacts only - the canonical lifecycle and the
workbook rendered from it - both of which are pure functions of sources the
pipeline already owns. It never edits the registry, never invents an exit,
never changes a price, and never weakens the A23 check itself. If the repair
does not restore the invariant it says so and exits non-zero, because a
divergence that regeneration cannot explain is a real defect that must stop
the run rather than be papered over.

Exit codes:  0 = invariant holds (healed or already clean)
             1 = still broken after repair - genuine defect, fail loudly
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _closed_registry(market: str) -> set:
    """Registry tickers that A23 expects to be accounted for."""
    sys.path.insert(0, str(ROOT))
    from backend.delivery.canonical.retirement import retired_runners
    from backend.research import opportunity_registry as oreg
    from scripts.build_aegis_3sheet_workbook import (_close_on_or_before,
                                                     _is_administrative_exit)
    reg, retired, out = oreg.load_all(ROOT), retired_runners(ROOT), set()
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market or o.status != "CLOSED":
                continue
            if o.runner in retired:
                continue
            ep = _close_on_or_before(ROOT, o.ticker, market, o.created_date or "")
            xp = _close_on_or_before(ROOT, o.ticker, market, o.closed_date or "")
            if _is_administrative_exit(o, ep, xp):
                continue
            out.add(str(o.ticker).upper())
    return out


def _exit_history_tickers(market: str) -> set:
    from openpyxl import load_workbook
    from backend.delivery.xlsx_contract import resolve_exit_history_sheet
    p = ROOT / "reports" / "telegram" / ("aegis_history_%s.xlsx" % market)
    if not p.exists():
        return set()
    wb = load_workbook(p, read_only=False, data_only=False)
    name = resolve_exit_history_sheet(wb)
    if name is None:
        wb.close()
        return set()
    ws = wb[name]
    hdr = [str(ws.cell(4, c).value or "").strip()
           for c in range(1, ws.max_column + 1)]
    tcol = (hdr.index("Ticker") + 1) if "Ticker" in hdr else 2
    out = set()
    for r in range(5, ws.max_row + 1):
        v = ws.cell(r, tcol).value
        if v:
            out.add(str(v).upper().strip())
    wb.close()
    return out


def _orphan_audit_tickers(market: str) -> set:
    p = ROOT / "reports" / "delivery" / ("orphan_audit_%s.jsonl" % market)
    if not p.exists():
        return set()
    out = set()
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.strip():
            try:
                t = str(json.loads(ln).get("ticker", "")).upper()
                if t:
                    out.add(t)
            except Exception:
                pass
    return out


def _closed_position_ids(market: str) -> dict:
    """{opportunity_id: Opportunity} for every CLOSED registry episode.

    Keyed by the EPISODE, not the ticker. _closed_registry() above compares
    ticker strings, and that is precisely why a re-entry's close can be
    invisible to it: the SAME ticker's earlier orphan close is already in
    exit history, so the ticker reads as "accounted for" while the newer
    position stays in CURRENT. Position ids are unique per episode, so this
    map cannot be satisfied by a different episode of the same name.
    """
    sys.path.insert(0, str(ROOT))
    from backend.research import opportunity_registry as oreg
    out: dict = {}
    for opps in oreg.load_all(ROOT).values():
        for o in opps:
            if str(o.market).lower() != market or o.status != "CLOSED":
                continue
            if o.opportunity_id:
                out[str(o.opportunity_id)] = o
    return out


def closed_in_current(market: str) -> list:
    """I6's condition · a registry-CLOSED episode still rendered in CURRENT.

    CEO 2026-10-31 · On 2026-10-30 the registry closed ZBRA and DDOG at
    21:48:55. canonical_lifecycle_usa.json had been generated at 21:43:18 -
    five minutes and thirty-seven seconds earlier - so CURRENT still carried
    both. The workbook rendered from it showed two closed positions as live,
    I6 refused the send, and USA delivered nothing. The A23 check above saw
    no divergence because both tickers already appear in exit history under
    their August orphan episodes.

    Returns [(ticker, position_id), ...] so the operator sees WHICH position,
    not just which name.
    """
    p = ROOT / "reports" / "context" / ("canonical_lifecycle_%s.json" % market)
    if not p.exists():
        return []
    try:
        life = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        # a lifecycle we cannot parse is a different defect · the run's own
        # gates own it · self-heal must not crash the workflow over it
        return []
    closed = _closed_position_ids(market)
    out = []
    for r in life.get("current") or []:
        if not isinstance(r, dict):
            continue
        pid = str(r.get("position_id") or "")
        if pid and pid in closed:
            out.append((str(r.get("ticker") or "?"), pid))
    return sorted(out)


def unaccounted(market: str) -> set:
    return (_closed_registry(market)
            - _exit_history_tickers(market)
            - _orphan_audit_tickers(market))


def _run(cmd: list) -> int:
    print("    $ %s" % " ".join(cmd[-4:]))
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def heal(market: str, asof: str) -> bool:
    """Regenerate the derived artifacts, then re-check."""
    print("  [self-heal] regenerating lifecycle + reconciler + workbook for "
          "%s (asof %s)" % (market, asof))
    _run([sys.executable, "-W", "ignore", "-m",
          "backend.delivery.lifecycle.canonical_daily_lifecycle",
          "--market", market, "--asof", asof])
    # CEO 2026-11-05 · THE RECONCILER DESCRIBES WHICHEVER CURRENT IT READ.
    #
    # heal() regenerated the lifecycle and the workbook but not
    # why_not_current, so after a repair the reconciler still described
    # the PREVIOUS state. Measured on 2026-11-05 after this healer
    # removed PLD from CURRENT:
    #
    #   test_current_rows_reconcile_to_the_lifecycle_dataset[usa]
    #   CURRENT and the reconciler disagree
    #     only in CURRENT: []   only in reconciler: ['PLD']
    #
    # backend/pipeline/contract/runner.py already documents this exact
    # order and why it matters - "the lifecycle produces the state; the
    # funnel explains it" - so a repair that regenerates one and not the
    # other reintroduces the disagreement the ordering exists to remove.
    # Same class as the defect this healer is repairing: two artifacts
    # describing two different moments.
    _run([sys.executable, "-W", "ignore", "-m",
          "backend.delivery.lifecycle.why_not_current",
          "--market", market])
    _run([sys.executable, "-W", "ignore",
          str(ROOT / "scripts" / "build_aegis_3sheet_workbook.py"),
          "--market", market, "--asof", asof])
    return not unaccounted(market) and not closed_in_current(market)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    # asof defaults to TODAY so nothing in this path is ever date-pinned
    ap.add_argument("--asof", default=date.today().isoformat())
    a = ap.parse_args()
    markets = ("india", "usa") if a.market == "both" else (a.market,)

    bad = False
    for m in markets:
        miss = unaccounted(m)
        shown = closed_in_current(m)
        if not miss and not shown:
            print("  [self-heal] %-6s invariants OK · nothing to repair" % m)
            continue
        if miss:
            print("  [self-heal] %-6s DIVERGENCE · %d registry-CLOSED ticker(s) not "
                  "accounted for: %s" % (m, len(miss), sorted(miss)[:10]))
        if shown:
            print("  [self-heal] %-6s STALE CURRENT · %d registry-CLOSED position(s) "
                  "still rendered as live: %s"
                  % (m, len(shown), ["%s (%s)" % t for t in shown[:10]]))
        if heal(m, a.asof):
            print("  [self-heal] %-6s REPAIRED · invariant restored" % m)
        else:
            still_a23 = sorted(unaccounted(m))[:10]
            still_cur = closed_in_current(m)[:10]
            print("::error::[self-heal] %s STILL BROKEN after regeneration · "
                  "unaccounted=%s · closed-in-CURRENT=%s"
                  % (m, still_a23, ["%s (%s)" % t for t in still_cur]))
            print("  This is a genuine defect, not staleness. Failing the run "
                  "rather than shipping an inconsistent workbook.")
            bad = True
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
