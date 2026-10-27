"""POST-PRODUCTION artifact integrity gate. Runs AFTER the producers.

WHY THIS EXISTS (and why it is not just a move of backend_validation)
---------------------------------------------------------------------
The artifact lifecycle audit found `backend_validation` at orchestrator
step 6 grading artifacts whose producers run at steps 24-26:

    step  6  backend_validation      <- validates sized_positions,
    step 24  risk_engine                portfolio_*, learning_*
    step 25  portfolio_engine
    step 26  learning_engine

So every run it graded the files left over from BEFORE that run. Combined
with the fact that those outputs were never persisted, the leftovers were
permanently 2026-09-04 - which is the entire "35 datasets 28-43 days past
a 1-day SLA" finding and the ops_check CRITICAL verdict.

`backend_validation` is NOT moved. It also validates SOURCE data - price
bars, fundamentals, macro - that genuinely must be checked before scoring.
Relocating it would delete a real pre-flight. The correct separation is
pre-flight source validation (where it is) and post-production artifact
verification (here).

THE EMPTY-PORTFOLIO PROBLEM
---------------------------
On 2026-10-27 the risk engine exits 0 reporting `sized: 0 active` because
all 228 India recommendations are HOLD. That is CORRECT behaviour, and the
pipeline could not distinguish it from a sizing failure, a stale input or a
malformed recommendation file.

Zero positions is valid ONLY when the upstream recommendation set genuinely
contains no actionable BUY. That is the distinguishing evidence, so this
gate reads the recommendation action distribution rather than trusting a
zero count.

STATES
  VALID_EMPTY      inputs fresh and parseable, zero positions, and the
                   recommendation set contains no actionable BUY
  VALID_NONEMPTY   inputs fresh, positions present
  INVALID_INPUT    required input missing, stale or malformed
  OUTPUT_MISSING   expected output absent
  OUTPUT_STALE     output asof does not belong to this run

Exit codes:
  0  every required artifact VALID_EMPTY or VALID_NONEMPTY
  1  one or more INVALID_INPUT / OUTPUT_MISSING / OUTPUT_STALE
  2  the gate could not run (its own inputs unavailable)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

# Required post-production artifacts, with the input whose action
# distribution justifies an empty output.
REQUIRED = {
    "india": [
        {"path": "reports/sized_positions.json",
         "count_key": "n_positions", "empty_justified_by": "recommendations"},
        # 2026-10-27 · count keys verified against the real files:
        # risk_report carries n_positions; portfolio_v3 does NOT (its only
        # count-ish key is run_utc), so it is checked for existence and
        # freshness only rather than pretending to read a count it lacks.
        {"path": "reports/risk_report.json",
         "count_key": "n_positions", "empty_justified_by": "recommendations"},
        {"path": "reports/portfolio_v3.json", "count_key": None},
        {"path": "reports/portfolio_state.json",
         "count_key": "n_positions", "empty_justified_by": "sizing"},
        {"path": "reports/portfolio_history.parquet", "count_key": None,
         "kind": "parquet"},
    ],
}

# Calendar-day budget. 3 absorbs a weekend; the orchestrator verdict and the
# run contract carry the stricter same-day rules.
MAX_AGE_DAYS = 3


def _asof(p: Path) -> Optional[str]:
    try:
        if p.suffix == ".parquet":
            import pandas as pd
            d = pd.read_parquet(p)
            for c in ("asof", "as_of", "date"):
                if c in d.columns and len(d):
                    return str(d[c].max())[:10]
            return None
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return "__MALFORMED__"
    if not isinstance(doc, dict):
        return None
    for k in ("asof", "as_of", "date"):
        v = doc.get(k)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    ru = doc.get("run_utc") or doc.get("generated_utc")
    return str(ru)[:10] if ru else None


def _count(p: Path, key: Optional[str]) -> Optional[int]:
    if not key or p.suffix == ".parquet":
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    v = doc.get(key)
    return int(v) if isinstance(v, (int, float)) else None


def _no_actionable_buy(market: str) -> Optional[bool]:
    """True when the recommendation set genuinely contains no BUY.

    This is the evidence that makes a zero-position portfolio VALID_EMPTY
    rather than a silent failure.
    """
    p = ROOT / "reports" / "recommendations_v3.json"
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    rows = doc.get("recommendations") or doc.get("rows") or []
    if not rows:
        return None
    acts = {str(r.get("action", "")).upper() for r in rows}
    return not ({"BUY", "STRONG_BUY", "ADD", "ACCUMULATE"} & acts)


def classify(market: str, spec: dict, today: date) -> dict:
    rel = spec["path"]
    p = ROOT / rel
    out = {"path": rel, "exists": p.exists()}
    if not p.exists():
        out["state"] = "OUTPUT_MISSING"
        out["why"] = "expected output absent after its producer ran"
        return out

    a = _asof(p)
    out["asof"] = a
    if a == "__MALFORMED__":
        out["state"] = "INVALID_INPUT"
        out["why"] = "file exists but could not be parsed"
        return out

    if a:
        try:
            age = (today - date.fromisoformat(a)).days
            out["age_days"] = age
            if age > MAX_AGE_DAYS:
                out["state"] = "OUTPUT_STALE"
                out["why"] = ("asof %s is %d days old (budget %d) - this does "
                              "not belong to the current run" % (a, age,
                                                                 MAX_AGE_DAYS))
                return out
        except Exception:
            pass

    n = _count(p, spec.get("count_key"))
    out["n"] = n
    if n is None or n > 0:
        out["state"] = "VALID_NONEMPTY"
        if n is None:
            out["why"] = "no count key declared · existence + freshness only"
        return out

    # n == 0 · empty. Valid only with justifying evidence.
    just = spec.get("empty_justified_by")
    if just == "recommendations":
        nb = _no_actionable_buy(market)
        if nb is True:
            out["state"] = "VALID_EMPTY"
            out["why"] = ("zero positions and the recommendation set contains "
                          "no actionable BUY - correct, not a failure")
            return out
        if nb is None:
            out["state"] = "INVALID_INPUT"
            out["why"] = ("zero positions but the recommendation set could not "
                          "be read, so empty cannot be justified")
            return out
        out["state"] = "INVALID_INPUT"
        out["why"] = ("zero positions WHILE actionable BUY recommendations "
                      "exist - this is a sizing failure, not a valid empty")
        return out
    if just == "sizing":
        sp = ROOT / "reports" / "sized_positions.json"
        sn = _count(sp, "n_positions") if sp.exists() else None
        if sn == 0:
            out["state"] = "VALID_EMPTY"
            out["why"] = "zero positions because sizing produced none"
            return out
        out["state"] = "INVALID_INPUT"
        out["why"] = ("zero positions while sizing produced %s - inconsistent"
                      % sn)
        return out
    out["state"] = "VALID_EMPTY"
    out["why"] = "empty with no declared justification requirement"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="india", choices=sorted(REQUIRED))
    ap.add_argument("--asof", default=None)
    a = ap.parse_args()
    today = date.fromisoformat(a.asof) if a.asof else date.today()

    specs = REQUIRED[a.market]
    rows = [classify(a.market, s, today) for s in specs]
    bad = [r for r in rows
           if r["state"] in ("INVALID_INPUT", "OUTPUT_MISSING",
                             "OUTPUT_STALE")]

    print("POST-PRODUCTION ARTIFACT INTEGRITY · %s · asof %s"
          % (a.market, today.isoformat()))
    for r in rows:
        print("  %-16s %-44s %s" % (r["state"], r["path"],
                                    ("asof %s" % r.get("asof"))
                                    if r.get("asof") else ""))
        if r.get("why"):
            print("        %s" % r["why"])

    payload = {
        "schema_version": "aegis.artifact_integrity.v1",
        "market": a.market,
        "asof": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "max_age_days": MAX_AGE_DAYS,
        "verdict": "FAIL" if bad else "PASS",
        "n_checked": len(rows),
        "n_failing": len(bad),
        "artifacts": rows,
        "interpretation": (
            "Runs AFTER the producers, unlike backend_validation at step 6 "
            "which grades pre-run leftovers. VALID_EMPTY requires justifying "
            "evidence from the upstream recommendation set - a zero count "
            "alone is never accepted."),
    }
    out = ROOT / "reports" / "context" / ("artifact_integrity_%s.json"
                                          % a.market)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=1, default=str),
                       encoding="utf-8")
        print("\n  wrote %s" % out.relative_to(ROOT))
    except Exception as e:
        print("\n  (verdict write failed: %s)" % e)

    if bad:
        print("\nFAIL · %d artifact(s) did not belong to this run:" % len(bad))
        for r in bad:
            print("  %-16s %s" % (r["state"], r["path"]))
        return 1
    print("\nPASS · every required artifact belongs to this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
