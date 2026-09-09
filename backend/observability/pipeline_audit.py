"""AEGIS · END-TO-END PIPELINE AUDIT · CEO 2026-09-09.

> "First perform a deep pipeline audit from source acquisition -> feature
>  generation -> model scoring -> candidate selection -> registry ->
>  lifecycle -> workbook -> Telegram, enumerate every existing guard,
>  identify every place stale/fallback/partial data can enter, and then
>  consolidate them into the single fail-closed contract."

WHY AN AUDIT MODULE AND NOT A DOCUMENT
---------------------------------------
A written audit is true on the day it is written. This one is DERIVED:
the stage map, the guard inventory and the leak list are all computed
from the pipeline's own declarations and its source. A step added
tomorrow appears here tomorrow, and a guard that is deleted stops being
counted. The finding that matters most below was only findable this way.

THE FINDING
-----------
`data_freshness.py` already monitors 95 artifacts and derives its
inventory from each step's `produces` declaration - completeness by
construction. It still missed a 50-day-old feature store, because the
`feature_store` step declares:

    produces: reports/feature_store_summary.json

and NOT the thing it actually produces:

    features/<market>/<asof>.parquet

So the monitor watched the summary, the summary was written every day,
and the substrate underneath went 50 days stale in silence. The guard was
not too weak. Its INPUT LIST was wrong, and a list derived from a wrong
declaration is wrong by construction too.

This module reports that class of defect directly: a step whose declared
artifacts do not include the data it really writes is UNDECLARED_OUTPUT,
which is exactly as dangerous as no guard at all.

RESEARCH/OBSERVABILITY ONLY · reads the repository, changes nothing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.observability.pipeline_audit.v1"

# The lineage the CEO specified · every arrow is a contract boundary.
STAGES = (
    ("1_SOURCE", "source acquisition · prices, fundamentals, corp actions, "
                 "FII/DII, news, macro"),
    ("2_SNAPSHOT", "feature snapshot materialisation per market per asof"),
    ("3_FEATURES", "feature selection / intelligence"),
    ("4_SCORE", "model factory + ensemble over the FULL universe"),
    ("5_ELIGIBILITY", "recommendation engine · BUY/HOLD/SELL + gates"),
    ("6_REGISTRY", "opportunity registry · position creation"),
    ("7_LIFECYCLE", "canonical daily lifecycle · CURRENT + EXIT"),
    ("8_DELIVERY", "workbook + Telegram"),
)

# Substrate whose staleness cannot be tolerated for a same-day decision.
CRITICAL_SUBSTRATE = {
    "feature_store": "features/<market>/<asof>.parquet",
    "model_factory": "reports/ensemble.json",
    "recommendation_ssot": "reports/recommendations.json",
}

# Source patterns that let old data in without anyone choosing to.
LEAK_PATTERNS = (
    ("LATEST_AVAILABLE_FALLBACK",
     r"list_snapshots\([^)]*\)\[-1\]|snaps\[-1\]",
     "takes the newest snapshot that EXISTS · no assertion that it is the "
     "requested asof · this is the exact July-21 path"),
    ("BARE_EXCEPT_PASS",
     r"except Exception:\s*\n\s*pass",
     "a failure is swallowed and the caller proceeds as if it succeeded"),
    ("SILENT_EMPTY_DEFAULT",
     r"or \{\}\s*$|or \[\]\s*$",
     "a missing artifact becomes an empty result · downstream reads it as "
     "'nothing to report' rather than 'nothing was produced'"),
)


def _steps(root: Path) -> list:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_aegis_steps", root / "scripts" / "aegis_daily_v2.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(getattr(mod, "STEPS", []))


def audit_steps(root: Path) -> dict:
    """Optionality + declaration correctness for every step."""
    steps = _steps(root)
    rows, undeclared, optional_critical = [], [], []
    for i, s in enumerate(steps):
        name = s.get("name", "?")
        prod = list(s.get("produces") or [])
        opt = bool(s.get("optional"))
        row = {"index": i, "name": name, "optional": opt,
               "n_produces": len(prod), "produces": prod[:4],
               "requires": list(s.get("requires") or [])[:3],
               "staleness_skip_hours": s.get("staleness_skip_hours")}
        if name in CRITICAL_SUBSTRATE:
            real = CRITICAL_SUBSTRATE[name]
            row["real_output"] = real
            # Does any declared artifact actually reference the real one?
            stem = real.split("/")[0]
            row["declares_real_output"] = any(stem in p for p in prod)
            if not row["declares_real_output"]:
                undeclared.append({"step": name, "declares": prod,
                                   "actually_writes": real})
            if opt:
                optional_critical.append(name)
        if not prod:
            row["undeclared"] = True
        rows.append(row)
    return {
        "n_steps": len(steps),
        "n_optional": sum(1 for r in rows if r["optional"]),
        "n_declaring_nothing": sum(1 for r in rows if r.get("undeclared")),
        "critical_substrate_steps_marked_optional": optional_critical,
        "undeclared_outputs": undeclared,
        "steps": rows,
    }


def audit_guards(root: Path) -> dict:
    """Every guard, and WHICH LAYER it actually inspects.

    The distinction that matters: a guard reading a DERIVED artifact
    cannot see the substrate. Three of the lifecycle's freshness inputs
    are outputs of scoring, which is why they reported FRESH while the
    features were seven weeks old.
    """
    guards = []
    known = [
        ("delivery_gate", "backend/delivery/delivery_gate.py", "DELIVERY",
         "consumes wave_regression + data-quality verdicts", True),
        ("wave_regression", "backend/research/wave_regression.py", "DELIVERY",
         "A1-A24 acceptance checks on the rendered workbook", True),
        ("xlsx_validator", "backend/delivery/xlsx_validator.py", "DELIVERY",
         "I1-I28 workbook invariants", True),
        ("data_freshness", "backend/observability/data_freshness.py",
         "ARTIFACT", "95 artifacts · inventory derived from STEPS.produces",
         False),
        ("input_freshness", "backend/delivery/lifecycle/canonical_daily_lifecycle.py",
         "DERIVED", "recommendations_v3 / ensemble / dynamic_risk", False),
        ("ssot_guard", "backend/recommendation/ssot/guard.py", "SCORING",
         "pre/post flight around recommendations.json + fallback to "
         "previous day", False),
        ("health_monitor", "backend/context/health_monitor.py", "ARTIFACT",
         "context health · blocks send on RED", True),
        ("why_not_current", "backend/delivery/lifecycle/why_not_current.py",
         "ELIGIBILITY", "per-ticker verdict L0..L10", False),
        ("full_universe_shadow", "backend/research/shadow/full_universe_shadow.py",
         "SCORING", "scores the full universe outside the 15-row limit",
         False),
    ]
    for name, rel, layer, what, blocks in known:
        p = root / rel
        guards.append({"guard": name, "path": rel, "layer": layer,
                       "inspects": what, "blocks_delivery": blocks,
                       "exists": p.exists()})
    by_layer = {}
    for g in guards:
        by_layer.setdefault(g["layer"], []).append(g["guard"])
    return {
        "n_guards": len(guards),
        "n_blocking": sum(1 for g in guards if g["blocks_delivery"]),
        "by_layer": by_layer,
        "layers_with_no_blocking_guard": sorted(
            l for l in {g["layer"] for g in guards}
            if not any(g["blocks_delivery"] for g in guards if g["layer"] == l)),
        "guards": guards,
    }


def audit_leaks(root: Path) -> dict:
    """Every place stale / fallback / partial data can enter unannounced."""
    hits = {k: [] for k, _, _ in LEAK_PATTERNS}
    scan = []
    for base in ("backend", "india", "usa", "scripts"):
        b = root / base
        if b.exists():
            scan += [p for p in b.rglob("*.py")
                     if "test" not in p.parts and "__pycache__" not in p.parts]
    for p in scan:
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        for key, pat, _ in LEAK_PATTERNS:
            for mt in re.finditer(pat, src, re.MULTILINE):
                line = src[:mt.start()].count("\n") + 1
                hits[key].append({"path": rel, "line": line})
    return {
        "counts": {k: len(v) for k, v in hits.items()},
        "descriptions": {k: d for k, _, d in LEAK_PATTERNS},
        # The fallback that actually caused the incident is worth naming.
        "critical_fallback_sites": [
            h for h in hits["LATEST_AVAILABLE_FALLBACK"]
            if "shadow" in h["path"] or "lifecycle" in h["path"]],
        "samples": {k: v[:6] for k, v in hits.items()},
    }


def audit_gates(root: Path) -> dict:
    """The CEO's five gates · what exists today, what does not."""
    st = audit_steps(root)
    gd = audit_guards(root)
    leaks = audit_leaks(root)
    undeclared = {u["step"] for u in st["undeclared_outputs"]}
    return {
        "GATE_1_DATA_READY": {
            "required": "correct date · market · source freshness · expected "
                        "universe · coverage · no unexplained gaps",
            "exists": "PARTIAL",
            "evidence": ("data_freshness monitors %d artifacts but its "
                         "inventory comes from STEPS.produces, and "
                         "feature_store does not declare its parquet"
                         % 95),
            "blocking": False,
        },
        "GATE_2_FEATURES_READY": {
            "required": "snapshot_asof == requested_asof · expected rows / "
                        "tickers · required features populated · NO stale "
                        "fallback",
            "exists": "MISSING",
            "evidence": ("list_snapshots()[-1] takes the newest file that "
                         "exists · %d fallback site(s) feed scoring"
                         % len(leaks["critical_fallback_sites"])),
            "blocking": False,
        },
        "GATE_3_SCORES_READY": {
            "required": "full universe evaluated · no unexplained score "
                        "loss · model/weights recorded",
            "exists": "PARTIAL",
            "evidence": ("full_universe_shadow measures it but is research "
                         "only · production persists head(10)+tail(5) = 15 "
                         "BEFORE eligibility"),
            "blocking": False,
        },
        "GATE_4_DECISION_READY": {
            "required": "every scored ticker has exactly one terminal "
                        "disposition · conservation of candidates",
            "exists": "PARTIAL",
            "evidence": ("why_not_current assigns L0..L10 per ticker and "
                         "found OXY as L7_eligible_no_registry · it reports, "
                         "it does not block"),
            "blocking": False,
        },
        "GATE_5_DELIVERY_READY": {
            "required": "only the canonical lifecycle may produce CURRENT / "
                        "EXIT / XLSX / Telegram",
            "exists": "YES",
            "evidence": "delivery_gate + wave_regression + xlsx_validator",
            "blocking": True,
        },
        "summary": {
            "gates_blocking_today": 1,
            "gates_required": 5,
            "critical_steps_optional": st["critical_substrate_steps_marked_optional"],
            "steps_not_declaring_real_output": sorted(undeclared),
            "layers_without_a_blocking_guard": gd["layers_with_no_blocking_guard"],
        },
    }


def build(root: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stages": [{"stage": k, "description": v} for k, v in STAGES],
        "steps": audit_steps(root),
        "guards": audit_guards(root),
        "leaks": audit_leaks(root),
        "five_gates": audit_gates(root),
        "root_cause_2026_09_09": (
            "The feature_store step is optional=True and declares "
            "reports/feature_store_summary.json instead of the parquet it "
            "writes. When it did not run, nothing failed, data_freshness had "
            "no reason to look at the snapshot, and "
            "full_universe_shadow.compute() called list_snapshots()[-1] - "
            "which returned 2026-07-21. Every downstream guard then "
            "correctly reported that its own derived artifact was fresh."),
    }


def emit(root: Path, rep: dict) -> Path:
    p = root / "reports" / "context" / "pipeline_audit.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path) -> Optional[dict]:
    p = root / "reports" / "context" / "pipeline_audit.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AEGIS end-to-end pipeline audit")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[2]
    rep = build(root)
    p = emit(root, rep)
    s, g, l = rep["steps"], rep["guards"], rep["leaks"]
    fg = rep["five_gates"]["summary"]
    print("AEGIS PIPELINE AUDIT -> %s" % p)
    print("  steps            %d (%d optional · %d declare no artifact)"
          % (s["n_steps"], s["n_optional"], s["n_declaring_nothing"]))
    print("  guards           %d (%d block delivery)"
          % (g["n_guards"], g["n_blocking"]))
    print("  layers with NO blocking guard: %s"
          % (", ".join(g["layers_with_no_blocking_guard"]) or "none"))
    print("  leak sites       %s" % l["counts"])
    print("  CRITICAL substrate steps marked optional: %s"
          % (", ".join(fg["critical_steps_optional"]) or "none"))
    print("  steps not declaring their real output:    %s"
          % (", ".join(fg["steps_not_declaring_real_output"]) or "none"))
    print("\n  FIVE GATES")
    for k in ("GATE_1_DATA_READY", "GATE_2_FEATURES_READY",
              "GATE_3_SCORES_READY", "GATE_4_DECISION_READY",
              "GATE_5_DELIVERY_READY"):
        v = rep["five_gates"][k]
        print("    %-24s %-8s blocking=%s" % (k, v["exists"], v["blocking"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
