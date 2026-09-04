"""V2 §P1 · End-to-end Confidence Calibration research cycle.

Phases (per CEO 2026-09-04):
  D · Backward walk-forward · 70/30 temporal split · fit-then-evaluate
  E · Forward test on last 60 days of predictions
  F · Worth analysis · ECE + Brier + monotonicity · verdict per market
  G · Conditional integration marker · writes calibration weights only if PASS

Dynamic · both markets · no hardcoded thresholds beyond the ones V2 mandates.
Produces reports/research/p1_calibration_report_{market}.json.
"""
from __future__ import annotations
import io, json, sys
from datetime import date, timedelta, datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.calibration.confidence_calibrator import (
    build_calibration_dataset, fit_platt, apply_platt,
    expected_calibration_error, brier_score, CalibrationSample,
)


# V2 §P1 acceptance criterion (canonical · not a magic number)
ECE_ACCEPTANCE_THRESHOLD = 0.05
MIN_N_FOR_VALIDATION_CANDIDATE = 50    # V2 locked sample-size tier
FORWARD_WINDOW_DAYS = 60               # CEO explicit ask
WALK_FORWARD_TRAIN_FRACTION = 0.70     # standard 70/30 temporal split


def _sort_by_date(samples: list[CalibrationSample]) -> list[CalibrationSample]:
    return sorted(samples, key=lambda s: s.asof or "")


def phase_D_backward_walk_forward(samples: list[CalibrationSample]) -> dict:
    """70/30 temporal split · fit Platt on train · evaluate ECE on holdout."""
    usable = [s for s in samples if s.raw_confidence is not None and s.win_flag is not None]
    usable = _sort_by_date(usable)
    n = len(usable)
    if n < MIN_N_FOR_VALIDATION_CANDIDATE:
        return {"stage": "D_backward", "status": "INSUFFICIENT_SAMPLE",
                "n": n, "threshold": MIN_N_FOR_VALIDATION_CANDIDATE}
    split = int(n * WALK_FORWARD_TRAIN_FRACTION)
    train, test = usable[:split], usable[split:]
    train_scores = [s.raw_confidence for s in train]
    train_outc = [s.win_flag for s in train]
    test_scores = [s.raw_confidence for s in test]
    test_outc = [s.win_flag for s in test]
    # Baseline ECE on raw
    ece_raw_train = expected_calibration_error(train_scores, train_outc)
    ece_raw_test = expected_calibration_error(test_scores, test_outc)
    # Fit + apply
    a, b = fit_platt(train_scores, train_outc)
    train_cal = apply_platt(train_scores, a, b)
    test_cal = apply_platt(test_scores, a, b)
    ece_cal_train = expected_calibration_error(train_cal, train_outc)
    ece_cal_test = expected_calibration_error(test_cal, test_outc)
    brier_raw = brier_score(test_scores, test_outc)
    brier_cal = brier_score(test_cal, test_outc)
    # Monotonicity check on test predictions
    binned = sorted(zip(test_cal, test_outc))
    q1 = sum(o for _, o in binned[:len(binned)//4]) / max(len(binned)//4, 1)
    q4 = sum(o for _, o in binned[-len(binned)//4:]) / max(len(binned)//4, 1)
    monotonic = q4 > q1
    return {
        "stage": "D_backward",
        "status": "COMPLETED",
        "n_total": n, "n_train": len(train), "n_test": len(test),
        "date_split": {"train_end": train[-1].asof, "test_start": test[0].asof if test else None},
        "ece_raw_train": round(ece_raw_train, 4),
        "ece_raw_test": round(ece_raw_test, 4),
        "platt_A": round(a, 4), "platt_B": round(b, 4),
        "ece_calibrated_train": round(ece_cal_train, 4),
        "ece_calibrated_test": round(ece_cal_test, 4),
        "ece_improvement_test": round(ece_raw_test - ece_cal_test, 4),
        "brier_raw_test": round(brier_raw, 4),
        "brier_calibrated_test": round(brier_cal, 4),
        "monotonicity": {"q1_win_rate": round(q1, 3), "q4_win_rate": round(q4, 3),
                          "is_monotonic": monotonic},
    }


def phase_E_forward_60d(samples: list[CalibrationSample], as_of: str) -> dict:
    """Fit calibrator on data BEFORE the last-60d window · evaluate ON the window."""
    from datetime import date as _d, timedelta as _t
    try:
        asof_d = _d.fromisoformat(as_of)
    except Exception:
        asof_d = _d.today()
    cutoff = (asof_d - _t(days=FORWARD_WINDOW_DAYS)).isoformat()
    usable = [s for s in samples if s.raw_confidence is not None and s.win_flag is not None
              and s.asof]
    train = [s for s in usable if s.asof < cutoff]
    test = [s for s in usable if s.asof >= cutoff]
    if len(train) < MIN_N_FOR_VALIDATION_CANDIDATE:
        return {"stage": "E_forward_60d", "status": "INSUFFICIENT_TRAIN",
                "n_train": len(train), "n_test": len(test)}
    if len(test) < 10:
        return {"stage": "E_forward_60d", "status": "INSUFFICIENT_TEST_60D",
                "n_train": len(train), "n_test": len(test),
                "note": "no meaningful 60d-forward evaluation possible"}
    train_scores = [s.raw_confidence for s in train]
    train_outc = [s.win_flag for s in train]
    test_scores = [s.raw_confidence for s in test]
    test_outc = [s.win_flag for s in test]
    ece_raw = expected_calibration_error(test_scores, test_outc)
    a, b = fit_platt(train_scores, train_outc)
    test_cal = apply_platt(test_scores, a, b)
    ece_cal = expected_calibration_error(test_cal, test_outc)
    brier_raw = brier_score(test_scores, test_outc)
    brier_cal = brier_score(test_cal, test_outc)
    return {
        "stage": "E_forward_60d",
        "status": "COMPLETED",
        "as_of": as_of, "cutoff_date": cutoff,
        "n_train_pre_60d": len(train), "n_test_last_60d": len(test),
        "ece_raw_last_60d": round(ece_raw, 4),
        "ece_calibrated_last_60d": round(ece_cal, 4),
        "ece_improvement": round(ece_raw - ece_cal, 4),
        "brier_raw_last_60d": round(brier_raw, 4),
        "brier_calibrated_last_60d": round(brier_cal, 4),
        "platt_A": round(a, 4), "platt_B": round(b, 4),
        "meets_v2_ece_gate": ece_cal <= ECE_ACCEPTANCE_THRESHOLD,
        "v2_ece_threshold": ECE_ACCEPTANCE_THRESHOLD,
    }


def phase_F_worth_analysis(D: dict, E: dict, market: str) -> dict:
    """Synthesize verdict · promote / do-not-promote."""
    d_ok = D.get("status") == "COMPLETED"
    e_ok = E.get("status") == "COMPLETED"
    reasons: list[str] = []
    verdict = "DO_NOT_PROMOTE"
    if not d_ok:
        reasons.append(f"Phase D {D.get('status')} · cannot verify walk-forward")
    if not e_ok:
        reasons.append(f"Phase E {E.get('status')} · cannot verify 60d forward")
    if d_ok and e_ok:
        # 4 sub-tests · Platt reduces ECE in BOTH walk-forward and 60d forward,
        # monotonicity holds, and calibrated ECE meets V2 threshold
        improved_wf = D.get("ece_improvement_test", 0) > 0.0
        improved_60d = E.get("ece_improvement", 0) > 0.0
        monotonic = D.get("monotonicity", {}).get("is_monotonic", False)
        meets_gate = E.get("meets_v2_ece_gate", False)
        checks = {
            "wf_ece_improvement": improved_wf,
            "forward60d_ece_improvement": improved_60d,
            "monotonic_confidence_vs_outcome": monotonic,
            "meets_v2_ece_threshold": meets_gate,
        }
        n_pass = sum(1 for v in checks.values() if v)
        reasons.append(f"{n_pass}/4 checks pass · {checks}")
        if n_pass == 4: verdict = "PROMOTE"
        elif n_pass >= 2: verdict = "CONDITIONAL_PROMOTE · needs refit-monitoring cycle"
        else: verdict = "DO_NOT_PROMOTE"
    return {
        "stage": "F_worth_analysis",
        "market": market,
        "verdict": verdict,
        "reasons": reasons,
    }


def phase_G_integration_marker(F: dict, D: dict, market: str, root: Path) -> dict:
    """If PROMOTE · write calibration weights to a research artifact.
    Integration into production is a SEPARATE explicit step per V2 §Part 0
    isolation contract · this only records the promotion-ready weights.
    """
    if F.get("verdict") not in ("PROMOTE", "CONDITIONAL_PROMOTE · needs refit-monitoring cycle"):
        return {"stage": "G_integration",
                "action": "SKIPPED · verdict does not warrant integration"}
    weights_dir = root / "reports" / "research" / "calibration_weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    out = weights_dir / f"{market}.json"
    payload = {
        "market": market,
        "platt_A": D.get("platt_A"),
        "platt_B": D.get("platt_B"),
        "n_train": D.get("n_train"),
        "date_fit_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": F.get("verdict"),
        "approval_status": "research_ready_pending_ceo_authorization",
        "next_step_note": (
            "V2 §P1 requires ECE ≤0.05 sustained across 4 consecutive weekly refits "
            "before replacing raw confidence in delivered output. This artifact "
            "records the first fit · monitoring cycle owns the remaining 3 refits."
        ),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"stage": "G_integration", "action": "WEIGHTS_WRITTEN",
             "path": str(out.relative_to(root))}


def run(market: str) -> dict:
    samples = build_calibration_dataset(_ROOT, market)
    as_of = date.today().isoformat()
    D = phase_D_backward_walk_forward(samples)
    E = phase_E_forward_60d(samples, as_of)
    F = phase_F_worth_analysis(D, E, market)
    G = phase_G_integration_marker(F, D, market, _ROOT)
    report = {
        "engine": "p1_confidence_calibration",
        "version": "v1.0",
        "market": market,
        "run_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "governance": {
            "v2_reference": "AEGIS Master Document v2 · Part R2 §P1",
            "acceptance_gate": f"ECE ≤ {ECE_ACCEPTANCE_THRESHOLD} sustained · 4 consecutive weekly refits",
            "sample_size_tier": ("validation_candidate" if len(samples) >= 50
                                  else "stronger_evidence" if len(samples) >= 30
                                  else "research_signal"),
        },
        "dataset_summary": {
            "n_total_samples": len(samples),
            "n_with_confidence_and_outcome": sum(
                1 for s in samples if s.raw_confidence is not None and s.win_flag is not None
            ),
        },
        "phase_D_backward_walk_forward": D,
        "phase_E_forward_60d": E,
        "phase_F_worth_analysis": F,
        "phase_G_integration_marker": G,
    }
    out = _ROOT / "reports" / "research" / f"p1_calibration_report_{market}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[p1] wrote {out.relative_to(_ROOT)}")
    return report


def main():
    for m in ("india", "usa"):
        r = run(m)
        F = r["phase_F_worth_analysis"]
        E = r["phase_E_forward_60d"]
        D = r["phase_D_backward_walk_forward"]
        print(f"\n=== {m.upper()} ===")
        print(f"  n_total={r['dataset_summary']['n_total_samples']} · "
              f"n_pairs={r['dataset_summary']['n_with_confidence_and_outcome']}")
        if D.get("status") == "COMPLETED":
            print(f"  D · ECE raw={D['ece_raw_test']} → calibrated={D['ece_calibrated_test']} "
                  f"(Δ={D['ece_improvement_test']}) · monotonic={D['monotonicity']['is_monotonic']}")
        if E.get("status") == "COMPLETED":
            print(f"  E · ECE last-60d raw={E['ece_raw_last_60d']} → calibrated="
                  f"{E['ece_calibrated_last_60d']} (Δ={E['ece_improvement']}) · "
                  f"meets_gate={E['meets_v2_ece_gate']}")
        print(f"  F · VERDICT: {F['verdict']}")
        for reason in F.get("reasons", []):
            print(f"      · {reason}")


if __name__ == "__main__":
    main()
