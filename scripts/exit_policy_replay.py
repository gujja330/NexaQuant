"""Exit policy replay - calibrates the dynamic exit advisor. Both markets.

Runs automatically inside scripts/aegis_run_all.py (stage
`exit-calibration:<market>`), in live mode, before the contract:

    --live --if-older-than 5

so it only recalibrates when the last replay is 5+ days old (a
skip costs about a second), and only computes what the live advisor reads.
It never blocks delivery: if it fails, the run continues on the previous
calibration and the failure is logged.

Manual full research report (all policy families, head-to-head):

    python scripts/exit_policy_replay.py --market both

Writes reports/research/exit_policy_replay_<market>.json under the folder
this script runs from, which publication copies back into prism.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.research import exit_policy_replay as R  # noqa: E402


def _age_days(path: Path, asof: str):
    try:
        rep = json.loads(path.read_text(encoding="utf-8"))
        return (date.fromisoformat(asof[:10])
                - date.fromisoformat(str(rep.get("asof"))[:10])).days
    except Exception:
        return None


def recommend(root: Path, m: str, asof: str, eps: list) -> dict:
    """The policy the live advisor uses: TB family, chosen on ALL mature
    data, published only when its held-out verdict is SUPPORTED."""
    tb = R.run_cv(root, m, asof, eps=eps, kinds={"TB"})
    out = {"tb_verdict": tb.get("verdict"), "tb_nested_cv": tb,
           "recommended_policy": None}
    if tb.get("verdict") == "SUPPORTED":
        mat = [e for e in eps if R._mature(e)]
        base = R.measure(mat, R.baseline_results(mat))
        pick = R._choose(mat, R.COST_BPS.get(m, 10.0), base.severe_rate, kinds={"TB"})
        if pick:
            out["recommended_policy"] = {
                **pick[0], "label": R.label(pick[0]),
                "evidence": "TB nested CV SUPPORTED %d/%d blocks"
                % (tb["folds_improved"], tb["n_folds"])}
    return out


def run_market(root: Path, m: str, asof: str, live: bool) -> dict:
    eps = R.build_episodes(root, m, asof)
    rep = {"market": m, "asof": asof, "mode": "live" if live else "full",
           "population": {"episodes": len(eps),
                          "entry_dates": len({e.entry_date for e in eps})}}
    rep.update(recommend(root, m, asof, eps))
    if not live:
        rep["split_report"] = R.run(root, m, asof)
        rep["nested_cv"] = R.run_cv(root, m, asof, eps=eps)
        rep["head_to_head"] = {fam: R.run_cv(root, m, asof, eps=eps, kinds={fam})
                               for fam in ("TB", "TB_RUN", "TB_ADAPT")}
    return rep


def _print(rep: dict) -> None:
    m, pol = rep["market"], rep.get("recommended_policy")
    print("[exit_calibration:%s] %d episodes · %d entry dates · TB held-out %s"
          % (m, rep["population"]["episodes"], rep["population"]["entry_dates"],
             rep.get("tb_verdict")))
    print("   live advisor: %s" % (("%s (%s)" % (pol["label"], pol["evidence"])) if pol
                                   else "dynamic barriers OFF - not supported"))
    for fam, cv in (rep.get("head_to_head") or {}).items():
        o = cv.get("out_of_fold") or {}
        if o:
            print("   HEAD-TO-HEAD %-8s date-mean %+.2f%% %.1fd severe %.1f%% worst %.1f "
                  "· %d/%d blocks · %s"
                  % (fam, o["date_mean_ret"], o["mean_days"], o["severe_rate"],
                     o["worst"], cv["folds_improved"], cv["n_folds"], cv["verdict"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--root", default=str(_ROOT),
                    help="folder holding the registry and price bars")
    ap.add_argument("--live", action="store_true",
                    help="only what the live advisor reads (pipeline mode)")
    ap.add_argument("--if-older-than", type=int, default=None, metavar="DAYS",
                    help="skip a market whose replay is newer than DAYS")
    a = ap.parse_args()
    out_dir = _ROOT / "reports" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        p = out_dir / ("exit_policy_replay_%s.json" % m)
        age = _age_days(p, a.asof)
        if a.if_older_than is not None and age is not None and age < a.if_older_than:
            print("[exit_calibration:%s] fresh (%d day(s) old, refresh at %d) · skipped"
                  % (m, age, a.if_older_than))
            continue
        rep = run_market(Path(a.root), m, a.asof, a.live)
        p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
        _print(rep)
        print("   -> %s" % p.relative_to(_ROOT))
    return 0


if __name__ == "__main__":
    # Calibration must never cost a delivery: on any internal error the run
    # continues on the previous calibration (exit_advisor falls back to it,
    # then to config) and the failure is logged loudly instead.
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("[exit_calibration] FAILED · delivery continues on the previous "
              "calibration", file=sys.stderr)
        raise SystemExit(0)
