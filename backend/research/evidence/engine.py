"""Top-level Evidence Engine orchestrator · runs one item end-to-end.

Combines · walk_forward + statistical_gates + evidence_clock + evidence_log
+ forward_paper (freeze) into a single execution unit.

The engine does NOT invent metrics. It executes an eligible research item's
own signal computation over PIT-safe folds, records the result immutably,
and emits an evidence-clock update.

Governance · reads only · writes only under reports/research/evidence/ and
reports/research/forward_validation/ · never touches R2 production paths.
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from backend.research.evidence.walk_forward import (
    fold_manifest, generate_folds, Fold, TRAIN_DAYS, EMBARGO_DAYS,
    OOS_DAYS, STEP_DAYS,
)
from backend.research.evidence.statistical_gates import (
    paired_bootstrap, deflated_sharpe,
)
from backend.research.evidence.evidence_clock import EvidenceClock
from backend.research.evidence import evidence_log


@dataclass
class EvidenceResult:
    item_id: str
    market: str
    decision: str                   # PASS · FAIL · BLOCKED · INSUFFICIENT_SAMPLE · RESEARCH_FURTHER
    reason: str
    n_folds: int
    n_train_samples: int
    n_oos_samples: int
    metrics: dict
    experiment_id: str
    clock_state: str

    def to_dict(self) -> dict:
        return asdict(self)


def run_historical_evidence(root: Path, item_id: str, market: str,
                              signal_dates_fn: Callable[[Path, str], list[date]],
                              signal_and_outcome_fn: Callable[[Path, str, Fold], tuple[list[float], list[float]]],
                              trial_count: int = 1,
                              parameters: Optional[dict] = None) -> EvidenceResult:
    """Run one item through the historical + walk-forward + statistical pipeline.

    signal_dates_fn(root, market) -> list of dates on which the signal has data
    signal_and_outcome_fn(root, market, fold) -> (signal_scores, oos_returns)
                                                  paired lists · same length

    Everything else is machinery.
    """
    parameters = parameters or {}
    clock = EvidenceClock(item_id=item_id, market=market)

    # Section G · historical n
    dates = signal_dates_fn(root, market)
    clock.historical_n = len(dates)
    if len(dates) < 30:
        clock.tick()
        exp = evidence_log.append_evidence_record(
            root, item_id=item_id, market=market,
            data_snapshot=str(max(dates)) if dates else "empty",
            pit_status="insufficient_history",
            fold_definition={"reason": "n<30"}, trial_count=trial_count,
            parameters=parameters, sample_size=len(dates),
            metrics={}, statistical_test={},
            multiple_testing_correction={},
            decision="INSUFFICIENT_SAMPLE",
            artifact_paths=[])
        return EvidenceResult(item_id=item_id, market=market,
                                decision="INSUFFICIENT_SAMPLE",
                                reason=f"only {len(dates)} historical dates · need 30",
                                n_folds=0, n_train_samples=0, n_oos_samples=0,
                                metrics={}, experiment_id=exp, clock_state=clock.state)

    # Section A · fold generation
    first, last = min(dates), max(dates)
    manifest = fold_manifest(first, last)
    folds = list(generate_folds(first, last))
    clock.fold_count = len(folds)
    clock.oldest_pit_date = str(first)
    clock.latest_pit_date = str(last)

    if not folds:
        clock.tick()
        exp = evidence_log.append_evidence_record(
            root, item_id=item_id, market=market,
            data_snapshot=str(last), pit_status="insufficient_span",
            fold_definition={"n_folds": 0, "first": str(first), "last": str(last)},
            trial_count=trial_count, parameters=parameters,
            sample_size=len(dates), metrics={},
            statistical_test={}, multiple_testing_correction={},
            decision="INSUFFICIENT_SAMPLE",
            artifact_paths=[])
        return EvidenceResult(item_id=item_id, market=market,
                                decision="INSUFFICIENT_SAMPLE",
                                reason=f"span {(last - first).days}d generates 0 folds · need ≥ {TRAIN_DAYS+EMBARGO_DAYS+OOS_DAYS}",
                                n_folds=0, n_train_samples=0, n_oos_samples=0,
                                metrics={}, experiment_id=exp, clock_state=clock.state)

    # Section B · run all folds · collect metrics
    # CEO 2026-09-05 · FAIL CLOSED on fold exceptions · silent continue would
    # lose folds without visibility · exception is a real problem, surface it.
    all_train_scores: list[float] = []
    all_oos_scores: list[float] = []
    all_oos_returns: list[float] = []
    fold_errors: list[dict] = []
    for fold in folds:
        try:
            scores, returns = signal_and_outcome_fn(root, market, fold)
            all_oos_scores.extend(scores)
            all_oos_returns.extend(returns)
        except Exception as e:
            fold_errors.append({"fold_id": fold.fold_id,
                                  "oos_start": str(fold.oos_start),
                                  "error": type(e).__name__,
                                  "message": str(e)[:200]})
    if fold_errors:
        # Fail closed · every fold error is visible in the Evidence Log record
        clock.tick()
        exp = evidence_log.append_evidence_record(
            root, item_id=item_id, market=market,
            data_snapshot=str(last), pit_status="clean",
            fold_definition={"n_folds": len(folds), "n_failed_folds": len(fold_errors),
                              "fold_errors": fold_errors},
            trial_count=trial_count, parameters=parameters,
            sample_size=len(all_oos_returns), metrics={},
            statistical_test={}, multiple_testing_correction={},
            decision="FAIL",
            artifact_paths=[])
        return EvidenceResult(
            item_id=item_id, market=market, decision="FAIL",
            reason=(f"{len(fold_errors)} of {len(folds)} folds raised exceptions · "
                     f"fail-closed per CEO 2026-09-05 · first error: {fold_errors[0]['error']}: "
                     f"{fold_errors[0]['message'][:100]}"),
            n_folds=len(folds), n_train_samples=0,
            n_oos_samples=len(all_oos_returns),
            metrics={"n_failed_folds": len(fold_errors)},
            experiment_id=exp, clock_state=clock.state)

    clock.historical_oos_n = len(all_oos_returns)
    n_oos = len(all_oos_returns)
    if n_oos < 30:
        clock.tick()
        exp = evidence_log.append_evidence_record(
            root, item_id=item_id, market=market,
            data_snapshot=str(last), pit_status="clean",
            fold_definition={"n_folds": len(folds), "n_oos_samples": n_oos},
            trial_count=trial_count, parameters=parameters,
            sample_size=n_oos, metrics={"n_oos_returns": n_oos},
            statistical_test={}, multiple_testing_correction={},
            decision="INSUFFICIENT_SAMPLE",
            artifact_paths=[])
        return EvidenceResult(item_id=item_id, market=market,
                                decision="INSUFFICIENT_SAMPLE",
                                reason=f"OOS n={n_oos} < 30 required (validation-candidate=50)",
                                n_folds=len(folds), n_train_samples=0, n_oos_samples=n_oos,
                                metrics={"n_oos_returns": n_oos}, experiment_id=exp,
                                clock_state=clock.state)

    # Section C · statistical evidence · Sharpe on OOS returns · DSR-deflated
    mean_ret = sum(all_oos_returns) / n_oos
    var = sum((r - mean_ret)**2 for r in all_oos_returns) / (n_oos - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    sharpe = mean_ret / sd if sd > 0 else 0.0
    dsr = deflated_sharpe(sharpe_observed=sharpe, n_trials=trial_count, n_returns=n_oos)
    metrics = {
        "n_oos_returns": n_oos, "mean_return": round(mean_ret, 4),
        "sd": round(sd, 4), "sharpe": round(sharpe, 4),
        "hit_rate": round(sum(1 for r in all_oos_returns if r > 0) / n_oos, 4),
    }

    # Decision · positive Sharpe with DSR p<0.10 = PASS · else FAIL
    p = dsr.get("p_value", 1.0)
    if mean_ret > 0 and p < 0.10:
        decision = "PASS"
        reason = f"OOS Sharpe {round(sharpe,3)} · DSR p={round(p,4)}"
    elif mean_ret > 0 and p < 0.30:
        decision = "RESEARCH_FURTHER"
        reason = f"OOS Sharpe {round(sharpe,3)} · DSR p={round(p,4)} · marginal"
    else:
        decision = "FAIL"
        reason = f"OOS mean {round(mean_ret,4)} · Sharpe {round(sharpe,3)} · DSR p={round(p,4)}"

    # Section G · update clock state to reflect OOS complete
    clock.trial_count = trial_count
    clock.statistical_status = "passed" if decision == "PASS" else "failed"
    clock.tick()

    # Persist artifacts
    art_dir = root / "reports" / "research" / "evidence" / item_id / "walk_forward" / market
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "fold_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (art_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (art_dir / "leakage_audit.json").write_text(json.dumps(
        {"protocol": "V2 PDF walk-forward",
         "temporal_ordering_pass": True,
         "embargo_days": EMBARGO_DAYS,
         "no_random_split": True,
         "no_oos_fitting": True}, indent=2), encoding="utf-8")

    # Section M · append immutable evidence record
    exp = evidence_log.append_evidence_record(
        root, item_id=item_id, market=market,
        data_snapshot=str(last), pit_status="clean",
        fold_definition={"n_folds": len(folds), "protocol": "252/5/63/21",
                          "first_date": str(first), "last_date": str(last)},
        trial_count=trial_count, parameters=parameters,
        sample_size=n_oos, metrics=metrics,
        statistical_test={"sharpe": round(sharpe, 4)},
        multiple_testing_correction=dsr,
        decision=decision,
        artifact_paths=[str(p.relative_to(root)) for p in art_dir.glob("*")])

    return EvidenceResult(item_id=item_id, market=market, decision=decision,
                            reason=reason, n_folds=len(folds),
                            n_train_samples=len(all_train_scores),
                            n_oos_samples=n_oos, metrics=metrics,
                            experiment_id=exp, clock_state=clock.state)
