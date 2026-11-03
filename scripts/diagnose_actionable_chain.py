"""CLI · why this market produced the actions it produced.

    python scripts/diagnose_actionable_chain.py --market both

Writes reports/diagnostics/actionable_chain_<market>.json and prints the
funnel. Read-only with respect to every production report; it decides
nothing and changes no threshold.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# `python scripts/x.py` puts scripts/ on sys.path, not the repo root, so
# `from backend...` fails without this. Same trap that made my delivery
# classifier swallow an ImportError and report a workbook fault.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.recommendation.actionable_chain_diagnostic import write  # noqa: E402


def _show(rep: dict) -> None:
    m = rep["market"].upper()
    print("=" * 78)
    print("%-6s asof=%s  universe=%d" % (m, rep["asof"], rep["n_universe"]))
    print("=" * 78)

    dead = rep["dead_models"]
    print("  models emitting no direction on ANY name: %d of %d  (weight %.2f%%)"
          % (len(dead), rep["absolute_ceiling"]["n_models"],
             100 * rep["dead_weight_share"]))
    for d in dead:
        print("      %-28s weight=%.4f" % (d, rep["model_activity"][d]["weight"]))

    am = rep["agreement_measurement"]
    print("\n  agreement measurement")
    print("      docstring: %s" % am["docstring_says"])
    print("      code     : %s" % am["code_does"])
    print("      names flagged ONLY because neutrals are in the base: %d"
          % am["n_flagged_only_because_neutrals_are_in_the_base"])
    w = am["worst_example"]
    if w:
        print("      worst   : %s  %d pos / %d neg / %d neutral -> shipped %.4f"
              " vs %.4f excluding neutrals"
              % (w["ticker"], w["n_positive"], w["n_negative"], w["n_neutral"],
                 w["agreement_shipped"], w["agreement_excluding_neutrals"]))

    c = rep["absolute_ceiling"]
    print("\n  absolute classifier ceiling")
    print("      agreement ceiling            %.4f   (%d live of %d models)"
          % (c["agreement_ceiling"], c["n_models"] - c["n_dead_models"],
             c["n_models"]))
    print("      calibration multiplier cap   %.4f" % c["calibration_multiplier_ceiling"])
    print("      best attainable calibrated   %.4f   (observed max %.4f)"
          % (c["calibrated_confidence_ceiling"],
             c["calibrated_confidence_max_observed"] or 0.0))
    for arm, a in c["arms"].items():
        print("      %-12s needs c>=%.2f -> %s   names meeting it: %d"
              % (arm, a["confidence_required"],
                 "SATISFIABLE" if a["satisfiable_at_ceiling"]
                 else "UNSATISFIABLE", a["n_names_meeting_confidence"]))

    f = rep["funnel"]
    print("\n  funnel (absolute path)")
    print("      entered %d" % f["entered"])
    for s in f["stages"]:
        print("      %-22s entered=%-4d removed=%-4d survived=%-4d  %s"
              % (s["stage"], s["entered"], s["removed"], s["survived"], s["rule"]))
    print("      absolute actionable: %d" % f["absolute_actionable"])
    print("      binding constraint: %s" % f["binding_constraint"])

    p = rep["percentile_abstention"]
    print("\n  percentile classifier abstention")
    print("      confidence floor %.4f vs market median %.4f  (%sx headroom)"
          % (p["min_confidence_for_action"], p["median_calibrated_confidence"],
             p["floor_headroom_multiple"]))
    print("      gate binds: %s  (removes %d names)"
          % (p["gate_binds"], p["n_below_floor"]))

    a = rep["actions"]
    print("\n  actions")
    for k in ("action", "percentile_action", "action_prior_absolute"):
        v = a[k]
        print("      %-22s actionable=%-4d %s"
              % (k, v["n_actionable"],
                 "" if v["populated"] else "(FIELD NOT POPULATED)"))
        print("          %s" % v["distribution"])
    print("      shipped action == percentile_action: %s"
          % a["shipped_equals_percentile"])
    print("\n  written: %s" % rep["_written_to"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=str(_ROOT))
    a = ap.parse_args(argv)
    markets = ("india", "usa") if a.market == "both" else (a.market,)
    for m in markets:
        _show(write(Path(a.root), m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
