"""R3 EVIDENCE CLOCK · is the evidence actually accumulating.

The registry answers "is this branch ready". It cannot answer "did today
move anything", and that is the question evidence accumulation lives or
dies on. A pipeline can certify green every morning while the evidence
base sits still - or quietly shrinks - and nothing in a per-run
certification would notice.

So this compares the current state against the previous certified
snapshot and reports the DELTA. It also refuses to let a delta be
flattering by accident.

WHY REGRESSION IS A FAILURE AND NOT A CURIOSITY
------------------------------------------------
Every artifact loss this project has had was silent. The fundamental
substrate was swept three times by a stash. The shadow ledger was hidden
by a .gitignore wildcard. Global context froze for three months while
every downstream report stayed green. In each case the evidence base went
backwards and the only symptom was a number nobody was comparing.

So a decrease in matured outcomes, unique predictions, quarterly periods
or persisted registry records fails certification. Going backwards is not
"a smaller number today"; it is data loss until proven otherwise.

DEDUPLICATION IS NOT LOSS, AND THE DIFFERENCE IS MEASURABLE
------------------------------------------------------------
On 2026-09-09 India's ledger fell from 63 rows to 53. That was the
read-time identity fix collapsing ten duplicate predictions, not ten lost
ones. The two are distinguished by counting RAW physical rows separately
from UNIQUE identities: dedup lowers raw-vs-unique divergence while
leaving unique identities intact. Only a fall in UNIQUE identities is
loss.

NO-NEW-MODEL GUARD
------------------
When READY_FOR_EVALUATION is NONE, `may_train()` returns False with the
reason. It exists so "should we try a model today" is answered by the
evidence base rather than by enthusiasm.

RESEARCH ONLY · reads artifacts, writes one report, changes no behaviour.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.r3.evidence_clock.v1"

MARKETS = ("india", "usa")

# Horizons a prediction must mature through before it can be scored.
MATURITY_DAYS = {"fwd_1d": 1, "fwd_3d": 3, "fwd_5d": 5,
                 "fwd_10d": 10, "fwd_20d": 20}
FIRST_EVAL_HORIZON = "fwd_5d"

# Counters that may never fall without an explicit documented reset.
CONSERVED = ("unique_predictions", "matured_outcomes", "fundamental_periods",
             "tickers_ge_8q", "registry_families")


def _shadow_counts(root: Path, market: str) -> dict:
    from backend.research.r3_program import shadow
    raw = shadow.load_ledger(root, market, raw=True)
    ded = shadow.load_ledger(root, market)
    p = (root / "reports" / "research" / "r3" / "shadow"
         / ("outcomes_%s.jsonl" % market))
    matured = 0
    if p.exists():
        matured = sum(1 for l in p.read_text(encoding="utf-8").splitlines()
                      if l.strip())
    dates = sorted({r.get("as_of") for r in ded if r.get("as_of")})
    return {
        "raw_rows": len(raw),
        "unique_predictions": len(ded),
        "duplicate_rows_collapsed": len(raw) - len(ded),
        "unique_tickers": len({r.get("ticker") for r in ded}),
        "prediction_dates": dates,
        "matured_outcomes": matured,
    }


def _fundamental_counts(root: Path, market: str) -> dict:
    from backend.research.substrate import fundamental_timeseries as ft
    tk = (ft.load(root, market) or {}).get("tickers") or {}
    per = sorted(len(v.get("periods") or []) for v in tk.values())
    n = len(per)
    return {
        "tickers": n,
        "fundamental_periods": sum(per),
        "median_quarters": per[n // 2] if n else 0,
        "tickers_ge_8q": sum(1 for x in per if x >= 8),
    }


def _next_eval_date(dates: list, horizon: str = FIRST_EVAL_HORIZON
                    ) -> Optional[str]:
    """Earliest date on which the OLDEST prediction can first be scored.

    Trading days, approximated by calendar days plus a weekend allowance.
    An approximation is honest here; claiming an exact market-calendar
    date would imply a precision the estimate does not have.
    """
    if not dates:
        return None
    try:
        d0 = date.fromisoformat(str(min(dates))[:10])
    except Exception:
        return None
    n = MATURITY_DAYS.get(horizon, 5)
    return (d0 + timedelta(days=n + 2 * (n // 5))).isoformat()


def _calibration(root: Path) -> dict:
    """Calibration cannot begin before a model emits a probability.

    Every R3 decision is ABSTAIN with no probability, so there is nothing
    to calibrate. Reporting 0/4 weeks is more truthful than reporting a
    calibration error computed over an empty set.
    """
    from backend.research.r3_program import shadow
    n_prob = 0
    for m in MARKETS:
        for r in shadow.load_ledger(root, m):
            if isinstance(r.get("take_probability"), (int, float)):
                n_prob += 1
    return {
        "status": ("NOT_STARTED · no probability emitted" if not n_prob
                   else "ACCUMULATING"),
        "eligible_weekly_observations": 0,
        "required_weeks": 4,
        "ece_threshold": 0.05,
        "predictions_carrying_a_probability": n_prob,
        "why": ("every R3 decision is ABSTAIN and deliberately carries no "
                "probability · calibration begins only when a specialist "
                "emits one"),
    }


def snapshot(root: Path) -> dict:
    from backend.research.r3_program import evidence_registry as er
    reg = er.load(root) or er.build(root)
    per = {}
    for m in MARKETS:
        s = _shadow_counts(root, m)
        f = _fundamental_counts(root, m)
        per[m] = {**s, **f}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof": date.today().isoformat(),
        "markets": per,
        "registry_families": reg.get("n_families", 0),
        "ready_for_evaluation": reg.get("ready_for_evaluation") or [],
        "calibration": _calibration(root),
    }


def _prev_path(root: Path) -> Path:
    return (root / "reports" / "research" / "r3"
            / "R3_EVIDENCE_CLOCK_PREVIOUS.json")


def deltas(cur: dict, prev: Optional[dict]) -> dict:
    """Run-to-run movement · never manufactured, never flattered."""
    if not prev:
        return {"first_run": True,
                "note": "no previous certified snapshot · nothing to compare"}
    out, regressions = {}, []
    for m in MARKETS:
        c, p = cur["markets"].get(m, {}), prev.get("markets", {}).get(m, {})
        d = {}
        for k in ("raw_rows", "unique_predictions", "unique_tickers",
                  "matured_outcomes", "fundamental_periods", "tickers",
                  "tickers_ge_8q", "median_quarters"):
            d[k] = int(c.get(k, 0)) - int(p.get(k, 0))
        # A fall in UNIQUE identities is loss. A fall in RAW rows while
        # unique holds is deduplication, which is a repair.
        d["dedup_not_loss"] = bool(d["raw_rows"] < 0
                                   and d["unique_predictions"] >= 0)
        out[m] = d
        for k in CONSERVED:
            if k in d and d[k] < 0 and not (k == "unique_predictions"
                                            and d["dedup_not_loss"]):
                regressions.append("%s.%s %+d" % (m, k, d[k]))
    fam = cur["registry_families"] - prev.get("registry_families", 0)
    out["registry_families"] = fam
    if fam < 0:
        regressions.append("registry_families %+d" % fam)
    out["regressions"] = regressions
    out["conserved"] = not regressions
    return out


def guards(cur: dict, d: dict) -> dict:
    """§4 · evidence conservation. A regression fails certification."""
    failures = []
    for r in d.get("regressions", []):
        failures.append({"code": "EVIDENCE_REGRESSION", "detail": r})
    # A frozen or rejected branch may not become ready without its gate.
    from backend.research.r3_program import evidence_registry as er
    reg = er.load(Path(".")) or {}
    for f in reg.get("families", []):
        if f.get("ready_for_evaluation") and f.get("current_verdict") in (
                "FROZEN", "REJECTED", "NO_INCREMENTAL_VALUE"):
            failures.append({
                "code": "DISPOSED_BRANCH_MARKED_READY",
                "detail": "%s:%s is %s and must not be READY"
                          % (f["research_id"], f["market"],
                             f["current_verdict"])})
    return {"pass": not failures, "failures": failures,
            "rule": ("matured outcomes, unique predictions, fundamental "
                     "periods and persisted registry records may never fall "
                     "without an explicit documented reset · deduplication "
                     "is distinguished by raw-vs-unique divergence")}


def may_train(cur: dict) -> dict:
    """§8 · the no-new-model guard."""
    ready = cur.get("ready_for_evaluation") or []
    return {
        "may_train": bool(ready),
        "ready": ready,
        "reason": ("%d family/families ready · run their PREDEFINED "
                   "evaluation, not a new exploration" % len(ready)
                   if ready else
                   "READY_FOR_EVALUATION is NONE · accumulate PIT data, "
                   "fundamentals, macro, R2 and R3 predictions and forward "
                   "outcomes only · do not train or evaluate a new branch"),
    }


def build(root: Path) -> dict:
    cur = snapshot(root)
    prev = None
    p = _prev_path(root)
    if p.exists():
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            prev = None
    d = deltas(cur, prev)
    g = guards(cur, d)

    clock = {}
    for m in MARKETS:
        s = cur["markets"][m]
        clock.setdefault("R3-K-META", {})[m] = {
            "predictions": s["raw_rows"],
            "unique_predictions": s["unique_predictions"],
            "matured_outcomes": s["matured_outcomes"],
            "required_matured_outcomes": 50,
            "earliest_next_evaluation_date": _next_eval_date(
                s["prediction_dates"]),
            "prediction_dates": len(s["prediction_dates"]),
        }
        clock.setdefault("R3-D-FCST", {})[m] = {
            "tickers_ge_8q": s["tickers_ge_8q"],
            "required_tickers": 30,
            "effective_observations": s["tickers_ge_8q"],
            "required_observations": 50,
            "median_quarters": s["median_quarters"],
            "next_substrate_milestone": (
                "%d more quarter(s) of accumulation to reach the 8-quarter "
                "floor at the current median of %d"
                % (max(0, 8 - s["median_quarters"]), s["median_quarters"])),
        }
    clock["CALIBRATION"] = cur["calibration"]
    clock["READY_FOR_EVALUATION"] = cur["ready_for_evaluation"] or "NONE"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": cur["generated_utc"],
        "asof": cur["asof"],
        "clock": clock,
        "deltas": d,
        "conservation": g,
        "no_new_model_guard": may_train(cur),
        "snapshot": cur,
    }


def emit(root: Path, rep: dict) -> Path:
    d = root / "reports" / "research" / "r3"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "R3_EVIDENCE_CLOCK.json"
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    # The comparison baseline for the NEXT run · written only when
    # conservation passed, so a corrupt run cannot become the baseline
    # that hides the next regression.
    if rep["conservation"]["pass"]:
        _prev_path(root).write_text(
            json.dumps(rep["snapshot"], indent=2, default=str),
            encoding="utf-8")
    return p


def load(root: Path) -> Optional[dict]:
    p = root / "reports" / "research" / "r3" / "R3_EVIDENCE_CLOCK.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def render(rep: dict) -> str:
    c = rep["clock"]
    L = ["═" * 72, "R3 EVIDENCE CLOCK   ·   %s" % rep["asof"], "═" * 72,
         "", "R3-K-META"]
    for m in MARKETS:
        k = c["R3-K-META"][m]
        L.append("  %-6s predictions %-4d unique %-4d matured %d/%d · "
                 "next eval %s"
                 % (m, k["predictions"], k["unique_predictions"],
                    k["matured_outcomes"], k["required_matured_outcomes"],
                    k["earliest_next_evaluation_date"] or "—"))
    L.append("")
    L.append("R3-D-FCST")
    for m in MARKETS:
        k = c["R3-D-FCST"][m]
        L.append("  %-6s >=8q %d/%d · median %dq · obs %d/%d"
                 % (m, k["tickers_ge_8q"], k["required_tickers"],
                    k["median_quarters"], k["effective_observations"],
                    k["required_observations"]))
    cal = c["CALIBRATION"]
    L += ["", "CALIBRATION",
          "  %s · %d/%d weeks · ECE threshold %.2f"
          % (cal["status"], cal["eligible_weekly_observations"],
             cal["required_weeks"], cal["ece_threshold"]),
          "", "READY_FOR_EVALUATION: %s"
          % (c["READY_FOR_EVALUATION"]
             if c["READY_FOR_EVALUATION"] != [] else "NONE"),
          "", "DELTAS vs previous certified snapshot"]
    d = rep["deltas"]
    if d.get("first_run"):
        L.append("  first run · no baseline")
    else:
        for m in MARKETS:
            x = d.get(m, {})
            L.append("  %-6s pred %+d · unique %+d · tickers %+d · matured "
                     "%+d · periods %+d · >=8q %+d%s"
                     % (m, x.get("raw_rows", 0), x.get("unique_predictions", 0),
                        x.get("unique_tickers", 0),
                        x.get("matured_outcomes", 0),
                        x.get("fundamental_periods", 0),
                        x.get("tickers_ge_8q", 0),
                        "  (dedup, not loss)" if x.get("dedup_not_loss") else ""))
    g = rep["conservation"]
    L += ["", "CONSERVATION: %s" % ("PASS" if g["pass"] else "FAIL")]
    for f in g["failures"]:
        L.append("  ✗ %s · %s" % (f["code"], f["detail"]))
    L += ["", "NO-NEW-MODEL GUARD: may_train=%s"
          % rep["no_new_model_guard"]["may_train"],
          "  %s" % rep["no_new_model_guard"]["reason"], "═" * 72]
    return "\n".join(L)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3 evidence clock")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    rep = build(root)
    emit(root, rep)
    print(render(rep))
    return 0 if rep["conservation"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
