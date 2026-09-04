"""Section O · Mechanical validators for the Cross-Cutting Evidence Engine.

Covers per CEO prompt:
  · PIT leakage
  · future-universe leakage guard
  · OOS contamination (no train/OOS overlap)
  · embargo correctness (5-day gap)
  · fold chronology (train < embargo < OOS)
  · no random split (deterministic walk-forward only)
  · trial accounting (every experiment records trial_count)
  · bootstrap reproducibility (seeded)
  · Evidence Log append-only (never overwrites)
  · Evidence Clock state-derivation determinism
  · Coverage-Tracker projection completeness
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research.evidence.walk_forward import (
    Fold, generate_folds, assert_no_leakage, fold_manifest,
    TRAIN_DAYS, EMBARGO_DAYS, OOS_DAYS, STEP_DAYS,
)
from backend.research.evidence.statistical_gates import (
    paired_bootstrap, likelihood_ratio_test, deflated_sharpe,
)
from backend.research.evidence.evidence_clock import (
    EvidenceClock, coverage_tracker_projection, STATES,
)
from backend.research.evidence import evidence_log


# ── walk-forward invariants ───────────────────────────────────────────

def test_walk_forward_constants_locked_per_pdf():
    """CEO 2026-09-05 · locked per V2 PDF · never override without authorization."""
    assert TRAIN_DAYS == 252
    assert EMBARGO_DAYS == 5
    assert OOS_DAYS == 63
    assert STEP_DAYS == 21


def test_folds_temporal_ordering():
    """Every fold · train_start < train_end < embargo_end < oos_start ≤ oos_end."""
    folds = list(generate_folds(date(2020, 1, 1), date(2026, 9, 1)))
    assert len(folds) >= 60, f"too few folds generated · {len(folds)}"
    for f in folds:
        assert_no_leakage(f)
        assert f.train_start < f.train_end
        assert f.train_end < f.embargo_end
        assert f.embargo_end < f.oos_start
        assert f.oos_start <= f.oos_end


def test_no_train_oos_overlap():
    """Zero-tolerance · no OOS bar can lie inside any prior fold's train window."""
    folds = list(generate_folds(date(2020, 1, 1), date(2026, 9, 1)))
    for f in folds:
        assert f.oos_start > f.train_end + timedelta(days=EMBARGO_DAYS), \
            f"fold {f.fold_id}: OOS not sufficiently past train_end + embargo"


def test_embargo_gap_minimum():
    """Embargo must span at least EMBARGO_DAYS trading days."""
    folds = list(generate_folds(date(2020, 1, 1), date(2023, 12, 31)))
    for f in folds:
        cur = f.train_end
        trading_gap = 0
        while cur < f.oos_start:
            cur = cur + timedelta(days=1)
            if cur.weekday() < 5:
                trading_gap += 1
        assert trading_gap >= EMBARGO_DAYS, (
            f"fold {f.fold_id}: embargo trading-gap={trading_gap} < {EMBARGO_DAYS}"
        )


def test_fold_manifest_records_leakage_audit_pass():
    """The manifest emitted per item must include the audit stamp."""
    m = fold_manifest(date(2020, 1, 1), date(2023, 12, 31))
    assert "leakage_audit" in m
    assert "PASSED" in m["leakage_audit"]
    assert m["train_days"] == TRAIN_DAYS
    assert m["embargo_days"] == EMBARGO_DAYS


def test_no_random_split_deterministic():
    """Two calls with same inputs must produce identical fold sets."""
    m1 = fold_manifest(date(2020, 1, 1), date(2023, 12, 31))
    m2 = fold_manifest(date(2020, 1, 1), date(2023, 12, 31))
    assert m1["folds"] == m2["folds"], "walk-forward is non-deterministic · random split leaked"


# ── statistical gates ─────────────────────────────────────────────────

def test_bootstrap_reproducible_with_seed():
    """Seeded bootstrap must yield identical results across runs."""
    deltas = [0.01, -0.02, 0.03, 0.005, -0.015, 0.02, 0.008, -0.01, 0.012, 0.003]
    r1 = paired_bootstrap(deltas, n_resamples=1000, seed=42)
    r2 = paired_bootstrap(deltas, n_resamples=1000, seed=42)
    assert r1.mean_delta == r2.mean_delta
    assert r1.ci_low == r2.ci_low
    assert r1.ci_high == r2.ci_high
    assert r1.p_value_two_sided == r2.p_value_two_sided


def test_bootstrap_ci_bounds_sensible():
    """CI_low ≤ mean_delta ≤ CI_high · always."""
    for deltas in ([0.01]*50, [-0.05]*50, [0.02, -0.03, 0.01]*20):
        r = paired_bootstrap(deltas, n_resamples=1000, seed=1)
        assert r.ci_low <= r.mean_delta <= r.ci_high


def test_bootstrap_insufficient_sample_safe():
    """n<3 returns safe zero result · no crash."""
    r = paired_bootstrap([], seed=1)
    assert r.n == 0
    r = paired_bootstrap([0.01], seed=1)
    assert r.n == 1


def test_likelihood_ratio_test_zero_when_no_improvement():
    """LR stat = 0 when full model doesn't improve on reduced · p=1."""
    r = likelihood_ratio_test(loglik_reduced=-100.0, loglik_full=-100.0, df_diff=2)
    assert r["lr_stat"] == 0.0
    assert r["p_value"] == 1.0


def test_deflated_sharpe_records_trials():
    """DSR wrapper must echo n_trials + n_returns so trial accounting is always visible."""
    r = deflated_sharpe(sharpe_observed=1.5, n_trials=10, n_returns=252)
    assert r["n_trials"] == 10
    assert r["n_returns"] == 252
    assert r["input_sharpe"] == 1.5


# ── Evidence Clock ────────────────────────────────────────────────────

def test_evidence_clock_state_derivation_deterministic():
    """Same field values → same state · every time."""
    c = EvidenceClock(item_id="TEST", market="india")
    assert c.derive_state() == "DATA_EXISTS"    # zero historical_n

    c.historical_n = 100
    assert c.derive_state() == "DATA_USABLE"    # no fold yet

    c.oldest_pit_date = "2020-01-02"
    c.fold_count = 5
    assert c.derive_state() == "HISTORICAL_TESTED"

    c.historical_oos_n = 50
    assert c.derive_state() == "OOS_TESTED"

    c.forward_n = 30
    assert c.derive_state() == "FORWARD_RUNNING"

    c.forward_matured_n = 30
    c.statistical_status = "passed"
    c.forward_status = "validated"
    assert c.derive_state() == "FORWARD_VALIDATED"


def test_evidence_clock_all_states_project_to_valid_tracker_stage():
    """Every 6-state clock value must project into a real 13-stage name."""
    valid_stages = {"Mapped", "Data-required", "PIT-ready", "Populated",
                     "Implemented", "Tested", "OOS", "Corrected", "Incremental",
                     "Paper", "Shadow", "Candidate", "Production"}
    for s in STATES:
        projected = coverage_tracker_projection(s)
        assert projected in valid_stages, f"state {s} projects to invalid stage {projected}"


def test_evidence_clock_tick_updates_state_and_timestamp():
    c = EvidenceClock(item_id="TEST", market="usa", historical_n=50,
                       oldest_pit_date="2020-01-02", fold_count=3)
    c.tick()
    assert c.state == "HISTORICAL_TESTED"
    assert c.last_updated_utc.endswith("Z")


# ── Evidence Log ──────────────────────────────────────────────────────

def test_evidence_log_append_only(tmp_path: Path):
    """Two appends must produce two records · not overwrite."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text("abcd1234abcd\n", encoding="utf-8")
    common_args = dict(
        item_id="TEST-ITEM", market="india",
        data_snapshot="2026-09-05", pit_status="clean",
        fold_definition={"n": 5}, trial_count=1,
        parameters={"threshold": 0.5}, sample_size=100,
        metrics={"sharpe": 1.2}, statistical_test={"p": 0.03},
        multiple_testing_correction={"dsr_p": 0.08}, decision="PASS",
        artifact_paths=[],
    )
    exp1 = evidence_log.append_evidence_record(root, **common_args)
    exp2 = evidence_log.append_evidence_record(root, **common_args)
    assert exp1 != exp2
    entries = evidence_log.read_evidence_log(root)
    assert len(entries) == 2, "append_evidence_record overwrote instead of appending"
    assert entries[0]["experiment_id"] == exp1
    assert entries[1]["experiment_id"] == exp2


def test_evidence_log_latest_for_item_returns_last(tmp_path: Path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text("deadbeef1234\n", encoding="utf-8")
    args = dict(item_id="X", market="india", data_snapshot="d", pit_status="p",
                 fold_definition={}, trial_count=1, parameters={}, sample_size=10,
                 metrics={}, statistical_test={}, multiple_testing_correction={},
                 decision="PASS", artifact_paths=[])
    e1 = evidence_log.append_evidence_record(root, **args)
    e2 = evidence_log.append_evidence_record(root, **args)
    latest = evidence_log.latest_for_item(root, "X", "india")
    assert latest is not None
    assert latest["experiment_id"] == e2   # most recent wins


def test_evidence_log_market_filter(tmp_path: Path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text("cafebabe1234\n", encoding="utf-8")
    args_ind = dict(item_id="X", market="india", data_snapshot="d", pit_status="p",
                     fold_definition={}, trial_count=1, parameters={}, sample_size=10,
                     metrics={}, statistical_test={}, multiple_testing_correction={},
                     decision="PASS", artifact_paths=[])
    args_usa = {**args_ind, "market": "usa"}
    evidence_log.append_evidence_record(root, **args_ind)
    evidence_log.append_evidence_record(root, **args_usa)
    assert evidence_log.latest_for_item(root, "X", "india")["market"] == "india"
    assert evidence_log.latest_for_item(root, "X", "usa")["market"] == "usa"


# ── Governance contract ───────────────────────────────────────────────

def test_engine_never_writes_r2_production_paths():
    """Grep evidence module tree · assert no writes to R2 production paths.
    Any evidence-engine code that writes to reports/production/*, reports/telegram/*,
    configs/ensemble_weights*, or backend/recommendation/* is a Part 0 isolation
    violation."""
    forbidden = ("reports/production", "reports/telegram",
                  "configs/ensemble_weights", "backend/recommendation/",
                  "reports/research/opportunity_registry.jsonl")
    ev_root = Path(__file__).resolve().parents[2] / "backend" / "research" / "evidence"
    for py in ev_root.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for f in forbidden:
            # allow if inside a comment or docstring saying "never write"
            for line in text.splitlines():
                if f in line and "never" not in line.lower() and "not" not in line.lower():
                    # heuristic · only flag if line looks like a write
                    if "write" in line.lower() or "to_" in line or "open(" in line:
                        raise AssertionError(f"{py.name}: forbidden production-path reference · {f} in {line}")
