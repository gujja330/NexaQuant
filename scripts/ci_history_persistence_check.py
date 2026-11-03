"""Fail (or flag) a daily run whose recommendation history was not persisted.

CEO 2026-11-03 · WHY THIS EXISTS
--------------------------------
Both daily recommendation runners are configured `"optional": True` in their
orchestrators (scripts/aegis_daily_v2.py:231, usa/scripts/usa_daily.py:240).
A runner that exits FATAL -- "no feature store snapshot", "snapshot empty",
"ensemble.json not found" -- therefore leaves the daily run GREEN and the
history untouched. Measured consequence, over eight months of daily runs:

    India  recommendation_history.parquet   5 daily rows
    USA    recommendation_history.parquet   4 daily rows

while 68 of India's 73 rows and 135 of USA's 139 came from a single replay
batch appended on 2026-07-21. Nobody saw a failure because there was no
failure to see: the append was wrapped in try/except and printed a warning,
and the step that owned it was allowed to be absent.

This check closes that gap. It does not change whether the step may be
optional -- that is the operator's call -- it makes the OUTCOME legible.

STATES
    PERSISTED  the (market, asof) row was verified present after the append
    FAILED     the append did not land the row
    SKIPPED    the payload carried no asof/market
    MISSING    no state file at all - the runner never reached the append

Exit codes:  0 = reported (default, advisory)
             1 = not persisted AND --strict was passed

--strict is off by default deliberately. Turning it on makes a skipped
recommendation step fail the whole daily run, including India's, which
currently passes. That is a production-behaviour change and belongs to the
operator, not to this script's default.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OK_STATES = ("PERSISTED",)

#: A SKIPPED run passes only when it says history was NOT expected and
#: gives a reason from the shared vocabulary. "Nothing to write" is a
#: legitimate outcome; "nothing was written" is not the same statement.
try:
    from backend.persistence import ALLOWED_SKIP_REASONS
except Exception:                                    # pragma: no cover
    ALLOWED_SKIP_REASONS = {}


def state_path(root: Path, market: str) -> Path:
    return root / "reports" / "context" / (
        "history_persistence_%s.json" % market.lower())


def classify(root: Path, market: str, expected_asof: str | None = None) -> dict:
    """Read the state a runner left behind and judge it. Never raises."""
    p = state_path(root, market)
    if not p.exists():
        return {"market": market, "state": "MISSING", "ok": False,
                "detail": "no state file at %s · the runner never reached "
                          "the history append" % p.as_posix()}
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"market": market, "state": "UNREADABLE", "ok": False,
                "detail": "%s: %s" % (type(exc).__name__, exc)}

    out = {"market": market, "state": str(st.get("state") or "UNKNOWN"),
           "asof": st.get("asof"), "rows_before": st.get("rows_before"),
           "rows_after": st.get("rows_after"), "verified": st.get("verified"),
           "history_expected": st.get("history_expected", True),
           "reason": st.get("reason") or "",
           "detail": st.get("detail") or ""}

    if out["state"] == "PERSISTED":
        out["ok"] = bool(st.get("verified"))
        if not out["ok"]:
            out["detail"] = ("state claims PERSISTED but verified is %r · "
                             "the row was never confirmed present"
                             % st.get("verified"))
        # Yesterday's success is not evidence about today.
        if out["ok"] and expected_asof and                 str(out.get("asof") or "")[:10] != expected_asof[:10]:
            out["ok"] = False
            out["state"] = "STALE"
            out["detail"] = ("state file reports asof %s · expected %s"
                             % (out.get("asof"), expected_asof))
        return out

    if out["state"] == "SKIPPED":
        # Passes ONLY as a positive, auditable claim that nothing was due.
        if out["history_expected"]:
            out["ok"] = False
            out["detail"] = ("SKIPPED while history_expected=True · a run "
                             "that owed history and skipped it is a failure")
        elif out["reason"] not in ALLOWED_SKIP_REASONS:
            out["ok"] = False
            out["detail"] = ("SKIPPED with reason %r · not in the allowed "
                             "vocabulary %s · a free-text excuse is not an "
                             "audit trail"
                             % (out["reason"], sorted(ALLOWED_SKIP_REASONS)))
        else:
            out["ok"] = True
            out["detail"] = ("no history was due · %s (%s)"
                             % (out["reason"],
                                ALLOWED_SKIP_REASONS[out["reason"]]))
        return out

    # FAILED / UNKNOWN / anything else
    out["ok"] = False
    if out["state"] == "FAILED" and out["reason"]:
        out["detail"] = "%s · %s" % (out["reason"], out["detail"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=None,
                    help="require the state to be for this date (default: any)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when history was not persisted")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)

    root = Path(a.root)
    markets = ("india", "usa") if a.market == "both" else (a.market,)
    bad = []
    for m in markets:
        r = classify(root, m, a.asof)
        line = ("  [history] %-6s %-10s rows %s -> %s · %s"
                % (m, r["state"], r.get("rows_before"), r.get("rows_after"),
                   r["detail"]))
        print(line)
        if not r["ok"]:
            bad.append(r)

    if not bad:
        return 0

    tag = "::error::" if a.strict else "::warning::"
    for r in bad:
        print("%s[history] %s recommendation history NOT persisted (%s): %s"
              % (tag, r["market"], r["state"], r["detail"]))
    if a.strict:
        print("  A daily run that persists no recommendation history is not a "
              "successful daily run. Failing rather than reporting green.")
        return 1
    print("  Advisory only · pass --strict to make this fail the run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
