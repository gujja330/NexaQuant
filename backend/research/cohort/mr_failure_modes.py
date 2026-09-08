"""MR FAILURE-MODE CLASSIFICATION · 7F · CEO 2026-09-08.

> "When a recommendation loses badly, was the entry thesis structurally
>  wrong, or did the position have favorable excursion that our exit/stop
>  handling failed to capture?"

ENTRY PROBLEM vs EXIT PROBLEM vs MIXED. Those are different repairs -
selection logic versus stop placement - and conflating them is how a
system ends up tightening filters when the real defect was holding a
winner until it round-tripped.

THE ANCHOR · R-MULTIPLES, NOT ARBITRARY PERCENTAGES
----------------------------------------------------
"Meaningful favourable excursion" cannot be a number someone picked. A
+3% excursion is enormous on a position risking 2% and irrelevant on one
risking 8%. So every excursion is expressed relative to THAT position's
own stop distance:

    R           = stop_distance_pct = (entry - stop) / entry * 100
    MFE_R       = MFE / R      how much the trade offered, in units of risk
    MAE_R       = |MAE| / R    how far it went against, in units of risk

MFE_R >= 1.0 means the position at some point offered at least as much
profit as the risk taken. If it still finished negative, the entry was
not the failure.

MAE_R >= 1.0 means price travelled the full stop distance. If no stop
exit is recorded, the stop did not protect.

TAXONOMY · losers, first match wins
------------------------------------
  ENTRY_FAILURE          MFE_R < 0.5 · never offered meaningful upside.
                         The thesis was wrong from the start. Repair =
                         selection.

  EXIT_FAILURE           MFE_R >= 1.0 · offered a full R or more and still
                         finished negative. The pick was right and the
                         exit gave it back. Repair = profit protection /
                         trailing behaviour.

  PARTIAL_MIXED          0.5 <= MFE_R < 1.0 · some upside, never a full
                         R. Repair = both, weighted by how far it got.

  Orthogonal flags (not exclusive):
  STOP_BREACHED_NOT_EXITED   MAE_R >= 1.0 and no stop exit recorded
  STOP_TOO_TIGHT             winner or recovered name whose MAE_R >= 1.0 -
                             the stop would have ejected a position that
                             went on to work

STATUS · descriptive, family MR_DEPENDENCY_EXPLORATORY_60D_V1. Nothing
here is a production rule. It measures what already happened.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.mr_failure_modes.v1"
FAMILY = "MR_DEPENDENCY_EXPLORATORY_60D_V1"

HORIZON = "fwd_10d_pct"
ENTRY_FAIL_R = 0.5
EXIT_FAIL_R = 1.0

MODE_ENTRY = "ENTRY_FAILURE"
MODE_EXIT = "EXIT_FAILURE"
MODE_MIXED = "PARTIAL_MIXED"


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _r_unit(r) -> Optional[float]:
    ep, st = _num(r.get("entry_price_at_pred")), _num(r.get("stop_at_pred"))
    if not ep or st is None or ep <= 0:
        return None
    d = (ep - st) / ep * 100.0
    return d if d and d > 0 else None


def classify(r) -> dict:
    """One verdict per prediction · every field it rests on is reported."""
    R = _r_unit(r)
    mfe, mae = _num(r.get("mfe_pct")), _num(r.get("mae_pct"))
    ret = _num(r.get(HORIZON))
    out = {
        "ticker": r.get("ticker"), "prediction_date": r.get("prediction_date"),
        "ret_pct": ret, "mfe_pct": mfe, "mae_pct": mae,
        "stop_distance_pct": round(R, 3) if R else None,
        "mfe_r": None, "mae_r": None, "mode": None, "flags": [],
        "confidence_pct": _num(r.get("confidence_pct")),
        "ma200_dist_pct": _num(r.get("ma200_dist_pct")),
        "stop_hit_within_20d": r.get("stop_hit_within_20d"),
    }
    if R is None or ret is None:
        return out
    if mfe is not None:
        out["mfe_r"] = round(mfe / R, 3)
    if mae is not None:
        out["mae_r"] = round(abs(mae) / R, 3)

    if out["mae_r"] is not None and out["mae_r"] >= 1.0 \
            and not r.get("stop_hit_within_20d"):
        out["flags"].append("STOP_BREACHED_NOT_EXITED")

    if ret < 0:
        m = out["mfe_r"]
        if m is None:
            out["mode"] = None
        elif m < ENTRY_FAIL_R:
            out["mode"] = MODE_ENTRY
        elif m >= EXIT_FAIL_R:
            out["mode"] = MODE_EXIT
        else:
            out["mode"] = MODE_MIXED
    else:
        # A winner that first travelled a full R against us would have been
        # ejected by a stop at that distance · that is a cost of the stop,
        # not of the pick.
        if out["mae_r"] is not None and out["mae_r"] >= 1.0:
            out["flags"].append("STOP_TOO_TIGHT")
    return out


def _agg(items: list) -> dict:
    if not items:
        return {"n": 0}
    rets = [i["ret_pct"] for i in items if i["ret_pct"] is not None]
    mfe = [i["mfe_r"] for i in items if i["mfe_r"] is not None]
    mae = [i["mae_r"] for i in items if i["mae_r"] is not None]
    losers = [i for i in items if (i["ret_pct"] or 0) < 0]
    modes = {}
    for i in losers:
        if i["mode"]:
            modes[i["mode"]] = modes.get(i["mode"], 0) + 1
    flags = {}
    for i in items:
        for f in i["flags"]:
            flags[f] = flags.get(f, 0) + 1
    return {
        "n": len(items),
        "n_losers": len(losers),
        "expectancy_pct": round(sum(rets) / len(rets), 3) if rets else None,
        "win_rate_pct": (round(sum(1 for v in rets if v > 0) / len(rets) * 100, 1)
                         if rets else None),
        "mean_mfe_r": round(sum(mfe) / len(mfe), 3) if mfe else None,
        "mean_mae_r": round(sum(mae) / len(mae), 3) if mae else None,
        "loser_modes": modes,
        "loser_mode_pct": {k: round(v / max(1, len(losers)) * 100, 1)
                           for k, v in modes.items()},
        "flags": flags,
    }


def analyse(root: Path, market: str) -> dict:
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    rows = load_cohort(root, market)
    if not rows:
        return {"market": market, "error": "cohort missing"}
    pop = [r for r in rows if _num(r.get(HORIZON)) is not None]
    items = [classify(r) for r in pop]
    scored = [i for i in items if i["mode"] or i["ret_pct"] is not None]

    # CEO-specified cohorts to dissect.
    def zone(lo, hi):
        return [i for i in scored
                if i["ma200_dist_pct"] is not None
                and (lo is None or i["ma200_dist_pct"] >= lo)
                and (hi is None or i["ma200_dist_pct"] < hi)]

    cohorts = {
        "ALL": scored,
        "ma200_-20..-10": zone(-20, -10),
        "ma200_5..10": zone(5, 10),
        "ma200_>=20_conf<55": [i for i in zone(20, None)
                               if (i["confidence_pct"] or 0) < 55],
        "stop_hit": [i for i in scored if i["stop_hit_within_20d"]],
        "no_stop_hit": [i for i in scored
                        if i["stop_hit_within_20d"] is False],
    }

    # The two questions the CEO asked to separate, quantified.
    losers = [i for i in scored if (i["ret_pct"] or 0) < 0 and i["mode"]]
    winners = [i for i in scored if (i["ret_pct"] or 0) > 0]
    exit_fail = [i for i in losers if i["mode"] == MODE_EXIT]
    entry_fail = [i for i in losers if i["mode"] == MODE_ENTRY]
    recoverable = sorted(exit_fail, key=lambda i: -(i["mfe_r"] or 0))[:10]

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "status": "DESCRIPTIVE · no production rule · measures what happened",
        "market": market.lower(),
        "horizon": HORIZON,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "definitions": {
            "R": "stop_distance_pct = (entry - stop)/entry*100",
            "mfe_r": "MFE / R · upside offered in units of risk taken",
            "mae_r": "|MAE| / R · adverse travel in units of risk taken",
            "ENTRY_FAILURE": f"loser with mfe_r < {ENTRY_FAIL_R}",
            "EXIT_FAILURE": f"loser with mfe_r >= {EXIT_FAIL_R}",
            "PARTIAL_MIXED": f"loser with {ENTRY_FAIL_R} <= mfe_r < {EXIT_FAIL_R}",
        },
        "n_population": len(pop),
        "n_classified_losers": len(losers),
        "split": {
            "entry_failures": len(entry_fail),
            "exit_failures": len(exit_fail),
            "partial_mixed": len(losers) - len(entry_fail) - len(exit_fail),
            "entry_failure_pct": round(len(entry_fail) / max(1, len(losers)) * 100, 1),
            "exit_failure_pct": round(len(exit_fail) / max(1, len(losers)) * 100, 1),
        },
        "avoidable_exit_loss_pct": round(
            sum(i["ret_pct"] for i in exit_fail), 2) if exit_fail else 0.0,
        "winners_with_full_R_drawdown": sum(
            1 for i in winners if "STOP_TOO_TIGHT" in i["flags"]),
        "n_winners": len(winners),
        "cohorts": {k: _agg(v) for k, v in cohorts.items()},
        "worst_exit_failures": recoverable,
    }


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "cohort"
            / f"mr_failure_modes_{market.lower()}.json")


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


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="MR failure-mode classification 7F")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in ("india", "usa"):
        rep = analyse(root, m)
        if rep.get("error"):
            print(f"{m}: {rep['error']}")
            continue
        p = emit(root, rep)
        s = rep["split"]
        print(f"failure_modes:{m} · losers {rep['n_classified_losers']} · "
              f"ENTRY {s['entry_failures']} ({s['entry_failure_pct']}%) · "
              f"EXIT {s['exit_failures']} ({s['exit_failure_pct']}%) · "
              f"MIXED {s['partial_mixed']} -> {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
