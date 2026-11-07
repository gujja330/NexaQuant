"""Every delivery blocker, in one place, before the send · CEO 2026-11-07.

WHY THIS EXISTS
---------------
India failed for five consecutive days and each day produced ONE
blocker, fixed, only for the next to appear on the next run:

    2026-11-05  A23 - rotation closes aged out of the 90-day window
    2026-11-06  A23 - same, cohort grown from 3 tickers to 6
    2026-11-07  A23 - lineage recorded, then TRUNCATED by the sender

That is not five defects, it is one missing capability: nothing
evaluated the whole blocking surface at once, so the pipeline could only
ever reveal the first blocker it hit. Fixing one gate per day is not a
fix.

This evaluates EVERY blocking input to the delivery decision, from FRESH
evidence, and reports all of them together with the reason for each.

It also draws the failure boundary the ambiguity kept hiding. Run
`--phase pre` before the sender and `--phase post` after it, and
"India failed" resolves into exactly one of three states:

    1  LEDGER MUTATED      lineage rows/records dropped during the send
    2  LINEAGE INTACT, GATE BLOCKED   accounting or another gate refused
    3  GATE ALLOWED, DELIVERY FAILED  the send or notifier itself failed

Before this, all three looked identical from the outside.

WHAT IT DOES NOT DO
-------------------
It does not weaken, bypass or override any gate, and it cannot allow a
send. It recomputes evidence and reports. A blocked delivery stays
blocked - the point is that the operator learns every reason at once
instead of one per day.

Recomputing matters: delivery_gate reads PERSISTED reports, so a stale
wave_regression_<market>.json blocks on yesterday's evidence. Measured
2026-11-07: india reported A23 FAIL from a report written while the
lineage was truncated; recomputing turned the same gate to ALLOW.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SCHEMA = "aegis.delivery.preflight.v1"

STATE_LEDGER_MUTATED = "LEDGER_MUTATED"
STATE_GATE_BLOCKED = "GATE_BLOCKED"
STATE_GATE_ALLOWED = "GATE_ALLOWED"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_path(root: Path, market: str) -> Path:
    return (root / "reports" / "context"
            / ("delivery_preflight_%s.json" % str(market).lower()))


# ─────────────────────────────────────────────────────────────
# lineage integrity · the thing the sender silently destroyed
# ─────────────────────────────────────────────────────────────

def lineage_state(root: Path, market: str) -> dict:
    """Rows, lineage-record count and hash of the durable audit sink.

    The sender rewrote this file with mode "w" from its own set,
    deleting 11 episode-lineage records (37 rows -> 26) and sending A23
    straight back to FAIL. A hash before and after makes that visible
    instead of mysterious.
    """
    from backend.delivery.lineage import episode_lineage as EL
    p = EL.audit_path(root, market)
    if not p.exists():
        return {"path": str(p), "exists": False, "rows": 0,
                "lineage_records": 0, "sha256": None, "episode_ids": []}
    raw = p.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]
    ids = []
    for l in lines:
        try:
            o = json.loads(l)
        except Exception:
            continue
        oid = str(o.get("opportunity_id") or o.get("position_id") or "")
        if oid:
            ids.append(oid)
    return {
        "path": str(p.relative_to(root).as_posix()),
        "exists": True,
        "rows": len(lines),
        "lineage_records": text.count(EL.KIND),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "episode_ids": sorted(ids),
    }


# ─────────────────────────────────────────────────────────────
# the whole blocking surface, from fresh evidence
# ─────────────────────────────────────────────────────────────

def evaluate(root: Path, market: str, asof: str,
             recompute: bool = True) -> dict:
    mk = str(market).lower()
    rep = {
        "schema": SCHEMA, "market": mk, "asof": str(asof)[:10],
        "generated_utc": _utc(), "recomputed": bool(recompute),
        "blockers": [], "checks": {},
    }

    # 1 · settle the durable lineage first · idempotent, and an episode
    #     still inside retention is deliberately NOT papered over.
    try:
        from backend.delivery.lineage import episode_lineage as EL
        man = EL.reconcile(root, mk, asof)
        rep["checks"]["episode_lineage"] = {
            "recorded": man["n_selected"],
            "unaccounted_before": man["unaccounted_before"],
            "unaccounted_after": man["unaccounted_after"],
        }
        if man["unaccounted_after"]:
            rep["blockers"].append({
                "code": "LINEAGE:UNACCOUNTED",
                "reason": "%d accountable CLOSED episode(s) remain "
                          "unaccounted after reconciliation"
                          % man["unaccounted_after"]})
    except Exception as e:
        rep["checks"]["episode_lineage"] = {
            "error": "%s: %s" % (type(e).__name__, e)}
        rep["blockers"].append({
            "code": "LINEAGE:ERROR",
            "reason": "lineage reconciliation failed · %s: %s"
                      % (type(e).__name__, e)})

    # 2 · recompute acceptance evidence · the gate reads PERSISTED
    #     reports, so stale evidence blocks on yesterday's state.
    if recompute:
        try:
            from backend.research import wave_regression as W
            wr = W.compute(root, mk, str(asof)[:10])
            W.emit(root, wr)
            fails = [c for c in wr.checks if c.get("status") == "FAIL"]
            rep["checks"]["wave_regression"] = {
                "verdict": wr.verdict, "n_fail": len(fails),
                "fails": [{"code": c["code"], "detail": str(c.get("detail"))[:200]}
                          for c in fails],
            }
        except Exception as e:
            rep["checks"]["wave_regression"] = {
                "error": "%s: %s" % (type(e).__name__, e)}

    # 3 · the authoritative decision · never recomputed here, only read
    try:
        from backend.delivery.delivery_gate import decide
        g = decide(root, mk)
        rep["checks"]["delivery_gate"] = {
            "verdict": "BLOCK" if g.blocking_codes else "ALLOW",
            "blocking_codes": list(g.blocking_codes),
            "reasons": [str(r)[:220] for r in (g.reasons or [])],
        }
        for code, reason in zip(g.blocking_codes,
                                (g.reasons or []) + [""] * len(g.blocking_codes)):
            rep["blockers"].append({"code": code, "reason": str(reason)[:220]})
    except Exception as e:
        rep["checks"]["delivery_gate"] = {
            "error": "%s: %s" % (type(e).__name__, e)}
        rep["blockers"].append({
            "code": "GATE:ERROR",
            "reason": "the delivery gate could not be evaluated · %s: %s"
                      % (type(e).__name__, e)})

    rep["lineage"] = lineage_state(root, mk)
    rep["verdict"] = STATE_GATE_BLOCKED if rep["blockers"] else STATE_GATE_ALLOWED
    return rep


def compare_post(root: Path, market: str, pre: dict) -> dict:
    """The failure boundary · did the send destroy the lineage?"""
    now = lineage_state(root, market)
    before = (pre or {}).get("lineage") or {}
    lost = sorted(set(before.get("episode_ids") or [])
                  - set(now.get("episode_ids") or []))
    mutated = bool(lost) or (now.get("lineage_records", 0)
                             < before.get("lineage_records", 0))
    return {
        "schema": SCHEMA, "market": str(market).lower(),
        "phase": "post", "generated_utc": _utc(),
        "lineage_before": {k: before.get(k) for k in
                           ("rows", "lineage_records", "sha256")},
        "lineage_after": {k: now.get(k) for k in
                          ("rows", "lineage_records", "sha256")},
        "episodes_lost": lost,
        "n_episodes_lost": len(lost),
        "ledger_mutated": mutated,
        "verdict": STATE_LEDGER_MUTATED if mutated else "LEDGER_INTACT",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="AEGIS · every delivery blocker, before the send")
    ap.add_argument("--market", required=True,
                    choices=["india", "usa", "both"])
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--root", default=str(_ROOT))
    ap.add_argument("--phase", default="pre", choices=["pre", "post"])
    ap.add_argument("--no-recompute", action="store_true")
    ap.add_argument("--report-only", action="store_true",
                    help="print the blockers but always exit 0")
    a = ap.parse_args(argv)

    root = Path(a.root)
    markets = ["india", "usa"] if a.market == "both" else [a.market]
    worst = 0

    for mk in markets:
        sp = state_path(root, mk)
        if a.phase == "post":
            pre = {}
            if sp.exists():
                try:
                    pre = json.loads(sp.read_text(encoding="utf-8"))
                except Exception:
                    pre = {}
            res = compare_post(root, mk, pre)
            print("  [postflight:%s] lineage %s -> %s rows · %s -> %s records"
                  % (mk, res["lineage_before"].get("rows"),
                     res["lineage_after"].get("rows"),
                     res["lineage_before"].get("lineage_records"),
                     res["lineage_after"].get("lineage_records")))
            if res["ledger_mutated"]:
                print("::error::[postflight:%s] LEDGER MUTATED during the "
                      "send · %d episode(s) lost: %s · this is failure mode "
                      "1 (a component truncated the audit sink)"
                      % (mk, res["n_episodes_lost"],
                         ", ".join(res["episodes_lost"][:6])))
                worst = max(worst, 1)
            else:
                print("  [postflight:%s] LEDGER INTACT · any failure is "
                      "downstream of accounting" % mk)
            try:
                (root / "reports" / "context"
                 / ("delivery_postflight_%s.json" % mk)).write_text(
                    json.dumps(res, indent=2, default=str), encoding="utf-8")
            except Exception:
                pass
            continue

        rep = evaluate(root, mk, a.asof, recompute=not a.no_recompute)
        try:
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(json.dumps(rep, indent=2, default=str),
                          encoding="utf-8")
        except Exception:
            pass

        ln = rep["lineage"]
        print("  [preflight:%s] asof=%s · lineage %s rows / %s records · "
              "sha=%s" % (mk, rep["asof"], ln.get("rows"),
                          ln.get("lineage_records"),
                          str(ln.get("sha256"))[:12]))
        wr = rep["checks"].get("wave_regression") or {}
        if "verdict" in wr:
            print("  [preflight:%s] acceptance recomputed · verdict=%s · "
                  "%d FAIL" % (mk, wr["verdict"], wr.get("n_fail", 0)))
            for f in wr.get("fails") or []:
                print("      FAIL %s · %s" % (f["code"], f["detail"][:120]))
        if not rep["blockers"]:
            print("  [preflight:%s] NO BLOCKERS · delivery gate ALLOW" % mk)
            continue
        # EVERY blocker, together. One per day is how five days happen.
        print("::error::[preflight:%s] %d BLOCKER(S) · delivery will be "
              "refused:" % (mk, len(rep["blockers"])))
        for b in rep["blockers"]:
            print("::error::  [%s] %s" % (b["code"], b["reason"][:200]))
        worst = max(worst, 1)

    if a.report_only:
        return 0
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
