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


def unaccounted(market: str) -> set:
    return (_closed_registry(market)
            - _exit_history_tickers(market)
            - _orphan_audit_tickers(market))


def _run(cmd: list) -> int:
    print("    $ %s" % " ".join(cmd[-4:]))
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def heal(market: str, asof: str) -> bool:
    """Regenerate the derived artifacts, then re-check."""
    print("  [self-heal] regenerating lifecycle + workbook for %s (asof %s)"
          % (market, asof))
    _run([sys.executable, "-W", "ignore", "-m",
          "backend.delivery.lifecycle.canonical_daily_lifecycle",
          "--market", market, "--asof", asof])
    _run([sys.executable, "-W", "ignore",
          str(ROOT / "scripts" / "build_aegis_3sheet_workbook.py"),
          "--market", market, "--asof", asof])
    return not unaccounted(market)


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
        if not miss:
            print("  [self-heal] %-6s invariant OK · nothing to repair" % m)
            continue
        print("  [self-heal] %-6s DIVERGENCE · %d registry-CLOSED ticker(s) not "
              "accounted for: %s" % (m, len(miss), sorted(miss)[:10]))
        if heal(m, a.asof):
            print("  [self-heal] %-6s REPAIRED · invariant restored" % m)
        else:
            still = sorted(unaccounted(m))[:10]
            print("::error::[self-heal] %s STILL BROKEN after regeneration: %s"
                  % (m, still))
            print("  This is a genuine defect, not staleness. Failing the run "
                  "rather than shipping an inconsistent workbook.")
            bad = True
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
