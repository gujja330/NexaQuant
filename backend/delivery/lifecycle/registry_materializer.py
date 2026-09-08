"""AEGIS · CANDIDATE -> REGISTRY, PROMOTED UPSTREAM · CEO 2026-09-08.

> "registry write -> step 74 · dynamic risk -> step 53 · lifecycle/CURRENT
>  -> step 58. So a genuinely new candidate can be created AFTER the system
>  has already calculated risk and CURRENT. That needs fixing before I
>  would call the daily recommendation pipeline complete."

THE DEFECT
----------
The candidate -> registry transition lived inside `detail_xlsx._rec_to_row`,
which runs in the `telegram` step. That is step 74. But:

    step 53  dynamic_risk_v2        computes the canonical R2 stop
    step 58  canonical_daily_lifecycle  builds CURRENT
    step 74  telegram               <- registry entry created HERE

So a position admitted today did not exist when risk ran and did not exist
when CURRENT was rendered. Two visible consequences:

  · a genuinely new position could never appear on the day it was admitted
  · when one was forced through by hand it arrived with `stop none`,
    because dynamic_risk had already run against a registry that did not
    contain it (JIOFIN, 2026-09-08)

This module runs the SAME transition BEFORE risk and lifecycle.

WHY IT CALLS THE EXISTING PATH INSTEAD OF REIMPLEMENTING IT
-----------------------------------------------------------
Admission is not a trivial rule. It depends on the derived status
(investor_action, percentile_action, if_holding), the exited-set gate, the
re-entry cooling gate and the retired-runner guard. Reimplementing that
here would create a second definition of "is this admissible", and the
entire delivery rewrite this month exists because two places computing the
same thing disagreed.

So this calls `_collect_rows_for_market` - the one code path that already
owns the transition - and discards the rendered rows. Only the registry
side effect is wanted.

IDEMPOTENCE
-----------
`get_or_create` returns an existing ACTIVE opportunity unchanged, with its
immutable created_date preserved. When the telegram step reaches the same
tickers at step 74 it therefore finds them already ACTIVE and changes
nothing. Running the transition twice in one day is a no-op the second
time, which is what makes moving it safe.

NO DECISION LOGIC MOVES WITH IT. No threshold, no gate, no ranking, no
exit rule. Only the MOMENT at which an already-decided admission is
recorded.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.lifecycle.registry_materializer.v1"


def _registry_snapshot(root: Path, market: str) -> dict:
    """ACTIVE ids and today's admissions, before/after comparison."""
    from backend.research import opportunity_registry as _oreg
    try:
        reg = _oreg.load_all(root)
    except Exception:
        return {"active": set(), "by_ticker": {}}
    active, by_ticker = set(), {}
    for (mkt, runner, tk), opps in (reg or {}).items():
        if str(mkt).lower() != market.lower():
            continue
        for o in opps:
            if o.is_active():
                active.add(o.opportunity_id)
                by_ticker[str(tk).upper()] = {
                    "runner": str(runner).upper(),
                    "created_date": str(o.created_date or "")[:10],
                    "initial_signal": str(getattr(o, "initial_signal", "") or ""),
                }
    return {"active": active, "by_ticker": by_ticker}


def materialize(root: Path, market: str, asof: str) -> dict:
    """Run the admission transition and report what it created."""
    before = _registry_snapshot(root, market)
    error = None
    try:
        from backend.delivery.telegram.detail_xlsx import (
            _collect_rows_for_market)
        # Rows are DISCARDED · this call is made for the registry
        # transition it performs, not for its rendering output.
        _collect_rows_for_market(root, market, asof)
    except Exception as e:                       # pragma: no cover
        error = f"{type(e).__name__}: {e}"
    after = _registry_snapshot(root, market)

    created = sorted(set(after["by_ticker"]) - set(before["by_ticker"]))
    admitted_today = sorted(
        t for t, v in after["by_ticker"].items()
        if v["created_date"] == str(asof)[:10])
    return {
        "schema_version": SCHEMA_VERSION,
        "market": market.lower(),
        "asof": str(asof)[:10],
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": error,
        "n_active_before": len(before["active"]),
        "n_active_after": len(after["active"]),
        "n_newly_materialized": len(created),
        "newly_materialized": [
            {"ticker": t, **after["by_ticker"][t]} for t in created],
        "admitted_today": [
            {"ticker": t, **after["by_ticker"][t]} for t in admitted_today],
    }


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "context"
            / f"registry_materialization_{market.lower()}.json")


def emit(root: Path, rep: dict) -> Path:
    p = artifact_path(root, rep["market"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = artifact_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def summary_line(rep: dict) -> str:
    return (f"registry_materializer:{rep['market']} · active "
            f"{rep['n_active_before']} -> {rep['n_active_after']} · newly "
            f"materialized {rep['n_newly_materialized']} · admitted today "
            f"{len(rep['admitted_today'])}"
            + (f" · ERROR {rep['error']}" if rep.get("error") else ""))


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="AEGIS · materialize candidate->registry BEFORE risk "
                    "and lifecycle")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = materialize(root, m, a.asof)
        p = emit(root, rep)
        print(summary_line(rep))
        for r in rep["admitted_today"]:
            print(f"    admitted · {r['ticker']} · {r['runner']} · "
                  f"{r['initial_signal']}")
        print(f"    -> {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
