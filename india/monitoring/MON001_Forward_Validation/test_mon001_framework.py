"""
MON001 adversarial framework tests — 20+ scenarios.

Uses ONLY synthetic ledgers and temporary directories. Never touches:
- data/aegis_registry.csv
- india/monitoring/MON001_Forward_Validation/ledger/*
- india/monitoring/MON001_Forward_Validation/reports/*
- LAB001-LAB010 evidence
- production files

Run: python india/monitoring/MON001_Forward_Validation/test_mon001_framework.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.monitoring.MON001_Forward_Validation.forward_ledger import (
    ForwardLedger, make_observation_row, DataIntegrityFailure,
)
from india.monitoring.MON001_Forward_Validation.fingerprint import (
    compute_fingerprint, is_drift, format_drift_report,
)
from india.monitoring.MON001_Forward_Validation.baseline_envelope import (
    build_envelope, load_or_cache,
)
from india.monitoring.MON001_Forward_Validation.broker_layer import (
    make_broker_layer, PaperOnlyBrokerLayer,
)
from india.monitoring.MON001_Forward_Validation.monitor import (
    MetricEvidence, DriftAlert, evaluate_concentration,
    evaluate_data_drift, assemble_global_state, evaluate_metric_evidence,
)


BOUNDARY = "2026-03-28"
FP = "sealed_fp_hash_1234567890abcdef"
FP_B = "different_fp_hash_deadbeef"


def _mk_ledger(tmp: Path):
    return ForwardLedger(tmp / "ledger.jsonl", tmp / "corrections.jsonl", BOUNDARY)


def _mk_obs(asof: str, rec_id: str, symbol: str, sector: str = "Financials",
             weight: float = 0.1, fp: str = FP, quality: str = "OK"):
    return make_observation_row(
        asof=asof, rec_id=rec_id, fingerprint_hash=fp, symbol=symbol,
        portfolio_cycle=f"{asof}_63", buy_price=100.0, intended_weight=weight,
        sector=sector, regime_label="Weak", exposure_multiplier=0.6,
        benchmark_ref=25000.0, data_quality=quality)


# ---------------------------- Tests ----------------------------

def test_1_clean_paper_observation():
    with tempfile.TemporaryDirectory() as tmp:
        led = _mk_ledger(Path(tmp))
        h = led.append(_mk_obs("2026-06-25", "REC-1", "RELIANCE"))
        assert h.startswith("") and len(h) == 64
        assert len(led.rows()) == 1
        assert led.verify_chain()["ok"]
    print("  TEST 1 PASS: clean paper observation")


def test_2_rejects_pre_boundary_asof():
    with tempfile.TemporaryDirectory() as tmp:
        led = _mk_ledger(Path(tmp))
        try:
            led.append(_mk_obs("2026-03-27", "REC-2", "RELIANCE"))
        except ValueError as e:
            assert "forward_boundary" in str(e)
        else:
            raise AssertionError("expected ValueError for pre-boundary asof")
    print("  TEST 2 PASS: rejects pre-boundary asof (leakage guard)")


def test_3_duplicate_rec_id_same_fingerprint():
    with tempfile.TemporaryDirectory() as tmp:
        led = _mk_ledger(Path(tmp))
        led.append(_mk_obs("2026-06-25", "REC-DUP", "RELIANCE"))
        led.append(_mk_obs("2026-06-25", "REC-DUP", "RELIANCE"))
        dups = led.duplicate_rec_ids()
        assert dups == ["REC-DUP"]
    print("  TEST 3 PASS: duplicate rec_id under same fingerprint detected")


def test_4_retroactive_mutation_detected():
    with tempfile.TemporaryDirectory() as tmp:
        led = _mk_ledger(Path(tmp))
        led.append(_mk_obs("2026-06-25", "REC-A", "RELIANCE"))
        led.append(_mk_obs("2026-06-26", "REC-B", "TCS"))
        # Retroactively mutate the FIRST row's buy_price.
        text = led.path.read_text(encoding="utf-8").splitlines()
        first = json.loads(text[0])
        first["buy_price"] = 999.99
        text[0] = json.dumps(first, ensure_ascii=False)
        led.path.write_text("\n".join(text) + "\n", encoding="utf-8")
        integrity = led.verify_chain()
        assert not integrity["ok"], f"expected chain break, got {integrity}"
        assert "mutation" in integrity["reason"] or "mismatch" in integrity["reason"]
    print("  TEST 4 PASS: retroactive mutation detected (hash chain integrity)")


def test_5_paper_broker_field_separation():
    # PAPER mode must reject broker fields.
    try:
        make_observation_row(
            asof="2026-06-25", rec_id="REC-Q", fingerprint_hash=FP, symbol="X",
            portfolio_cycle="2026-06-25_63", buy_price=100, intended_weight=0.1,
            sector="Financials", regime_label="Weak", exposure_multiplier=0.6,
            benchmark_ref=25000, source_mode="PAPER", broker_order_id="Q-1")
    except ValueError as e:
        assert "PAPER" in str(e)
    else:
        raise AssertionError("expected PAPER mode to reject broker fields")
    # BROKER mode without broker fields must reject.
    try:
        make_observation_row(
            asof="2026-06-25", rec_id="REC-Q", fingerprint_hash=FP, symbol="X",
            portfolio_cycle="2026-06-25_63", buy_price=100, intended_weight=0.1,
            sector="Financials", regime_label="Weak", exposure_multiplier=0.6,
            benchmark_ref=25000, source_mode="BROKER")
    except ValueError as e:
        assert "BROKER" in str(e)
    print("  TEST 5 PASS: PAPER/BROKER lifecycle stages strictly separated")


def test_6_fingerprint_matches_when_no_change():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "file.py"
        f.write_text("HOLD = 63\n")
        fp1 = compute_fingerprint(Path(tmp), ["file.py"], {"HOLD": 63})
        fp2 = compute_fingerprint(Path(tmp), ["file.py"], {"HOLD": 63})
        assert fp1["hash"] == fp2["hash"]
    print("  TEST 6 PASS: fingerprint stable across identical inputs")


def test_7_fingerprint_detects_file_change():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "file.py"
        f.write_text("HOLD = 63\n")
        fp1 = compute_fingerprint(Path(tmp), ["file.py"], {"HOLD": 63})
        f.write_text("HOLD = 84\n")
        fp2 = compute_fingerprint(Path(tmp), ["file.py"], {"HOLD": 63})
        assert fp1["hash"] != fp2["hash"]
        assert is_drift(fp2, fp1["hash"])
    print("  TEST 7 PASS: fingerprint detects file mutation (CONFIG_DRIFT D1)")


def test_8_fingerprint_detects_constant_change():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "file.py"
        f.write_text("HOLD = 63\n")
        fp1 = compute_fingerprint(Path(tmp), ["file.py"], {"HOLD": 63})
        fp2 = compute_fingerprint(Path(tmp), ["file.py"], {"HOLD": 84})
        assert fp1["hash"] != fp2["hash"]
    print("  TEST 8 PASS: fingerprint detects baseline constant change (HOLD 63 to 84)")


def test_9_fingerprint_missing_file_raises():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            compute_fingerprint(Path(tmp), ["nonexistent.py"], {})
        except FileNotFoundError as e:
            assert "nonexistent.py" in str(e)
        else:
            raise AssertionError("expected FileNotFoundError")
    print("  TEST 9 PASS: fingerprint raises on missing baseline file")


def test_10_envelope_matches_lab009_diagnostics():
    diag = ROOT / "india/ai_lab/LAB009_Horizon_Phase_Recalibration/reports/lab009_period_corrected_diagnostics_2026-07-13.csv"
    if not diag.exists():
        print("  TEST 10 SKIP: LAB009 diagnostics not present")
        return
    env = build_envelope(diag, "N0", 63, 15.0, [0.0, 0.06])
    assert "envelope_hash" in env
    assert "metrics" in env
    assert "sharpe_full" in env["metrics"]
    # Envelope must contain both cash levels
    assert "0.0" in env["metrics"]["sharpe_full"]
    assert "0.06" in env["metrics"]["sharpe_full"]
    # N=4 phases per cash
    assert env["metrics"]["sharpe_full"]["0.0"]["n_phases"] == 4
    print(f"  TEST 10 PASS: envelope built from LAB009 diagnostics "
           f"(hash={env['envelope_hash'][:12]})")


def test_11_envelope_cache_byte_identity_or_raise():
    diag = ROOT / "india/ai_lab/LAB009_Horizon_Phase_Recalibration/reports/lab009_period_corrected_diagnostics_2026-07-13.csv"
    if not diag.exists():
        print("  TEST 11 SKIP: LAB009 diagnostics not present")
        return
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache.json"
        env1 = load_or_cache(cache, diag, "N0", 63, 15.0, [0.0, 0.06])
        env2 = load_or_cache(cache, diag, "N0", 63, 15.0, [0.0, 0.06])
        assert env1["envelope_hash"] == env2["envelope_hash"]
        # Now tamper with the cache — should raise.
        cache.write_text(cache.read_text().replace(env1["envelope_hash"][:10], "aaaaaaaaaa"))
        try:
            load_or_cache(cache, diag, "N0", 63, 15.0, [0.0, 0.06])
        except RuntimeError as e:
            assert "envelope drift" in str(e)
        else:
            raise AssertionError("expected envelope-drift RuntimeError on tampered cache")
    print("  TEST 11 PASS: envelope cache tamper triggers refuse-to-run")


def test_12_broker_layer_paper_only():
    b = make_broker_layer()
    assert isinstance(b, PaperOnlyBrokerLayer)
    assert b.available() is False
    assert b.fetch_fills("2026-06-25") == []
    for method in ("place_order", "modify_order", "cancel_order"):
        try:
            getattr(b, method)()
        except RuntimeError as e:
            assert "READ-ONLY" in str(e)
        else:
            raise AssertionError(f"{method} must refuse; broker layer is read-only")
    print("  TEST 12 PASS: broker layer strictly read-only (PAPER_ONLY)")


def test_13_concentration_detects_name_cap_breach():
    rows = [_mk_obs("2026-06-25", "R-1", "RELIANCE", weight=0.32),
             _mk_obs("2026-06-25", "R-2", "TCS", weight=0.10, sector="IT")]
    alert = evaluate_concentration(rows, name_cap=0.30, sector_cap=2,
                                     tolerance=0.05, over_by=1)
    assert alert is not None and alert.level == "DIVERGED"
    assert "intended_weight" in alert.reason
    print("  TEST 13 PASS: D7 concentration name_cap breach detected")


def test_14_concentration_detects_sector_breach():
    rows = [
        _mk_obs("2026-06-25", f"R-{i}", f"S{i}", sector="Financials", weight=0.09)
        for i in range(5)
    ]
    alert = evaluate_concentration(rows, name_cap=0.30, sector_cap=2,
                                     tolerance=0.05, over_by=1)
    assert alert is not None and alert.level == "DIVERGED"
    assert "sector cap" in alert.reason
    print("  TEST 14 PASS: D7 sector_cap breach detected")


def test_15_data_drift_stale_and_missing():
    rows = [_mk_obs("2026-06-25", f"R-{i}", f"S{i}", quality="STALE")
            for i in range(10)]
    rows.append(_mk_obs("2026-06-25", "R-11", "S11", quality="MISSING_PRICE"))
    alert = evaluate_data_drift(rows, 0.05, 0.10, 0.10, 0.20)
    assert alert is not None
    assert alert.level in ("WATCH", "DIVERGED")
    print("  TEST 15 PASS: D8 data drift stale+missing detected")


def test_16_correction_appended_not_mutated():
    with tempfile.TemporaryDirectory() as tmp:
        led = _mk_ledger(Path(tmp))
        h1 = led.append(_mk_obs("2026-06-25", "REC-C1", "RELIANCE"))
        h2 = led.append_correction(h1, "typo in weight", {"intended_weight": 0.12})
        assert h1 != h2
        # Ledger row 1 must be UNCHANGED
        integrity = led.verify_chain()
        assert integrity["ok"]
        assert (Path(tmp) / "corrections.jsonl").exists()
    print("  TEST 16 PASS: corrections appended to separate file; original row unchanged")


def test_17_insufficient_evidence_state():
    # No metric evidence + no alerts + clean fingerprint → INSUFFICIENT_EVIDENCE
    state, halt, reason = assemble_global_state(
        "OK", {"ok": True, "reason": ""},
        [MetricEvidence("sharpe_forward", None, None, None, None, 5, 30,
                        "INSUFFICIENT_EVIDENCE", "only 5 days")],
        [])
    assert state == "INSUFFICIENT_EVIDENCE" and halt is False
    print("  TEST 17 PASS: INSUFFICIENT_EVIDENCE state when no metrics evaluable")


def test_18_config_drift_forces_halt():
    state, halt, reason = assemble_global_state(
        "DRIFT", {"ok": True, "reason": ""},
        [], [])
    assert state == "HALT_REVIEW_REQUIRED" and halt is True
    assert "CONFIG_DRIFT" in reason
    print("  TEST 18 PASS: D1 CONFIG_DRIFT forces HALT_REVIEW_REQUIRED")


def test_19_data_integrity_failure_forces_halt():
    state, halt, reason = assemble_global_state(
        "OK", {"ok": False, "reason": "chain break at row 3"},
        [], [])
    assert state == "DATA_INTEGRITY_FAILURE" and halt is True
    print("  TEST 19 PASS: D10 DATA_INTEGRITY_FAILURE forces HALT")


def test_20_diverged_needs_four_weeks_for_halt():
    # A single DIVERGED alert should NOT immediately trigger HALT.
    a = DriftAlert("D3_RISK_DRIFT", "DIVERGED", "MaxDD out of envelope")
    state, halt, reason = assemble_global_state(
        "OK", {"ok": True, "reason": ""}, [], [a])
    assert state == "DIVERGED" and halt is False
    assert "4 consecutive" in reason
    print("  TEST 20 PASS: DIVERGED requires 4-consecutive-week persistence for HALT")


def test_21_ledger_boundary_leak_detection():
    # Directly write a pre-boundary row bypassing append(), then verify_chain must catch it.
    with tempfile.TemporaryDirectory() as tmp:
        led = _mk_ledger(Path(tmp))
        led.append(_mk_obs("2026-06-25", "REC-Y", "RELIANCE"))
        # Bypass the guard by writing directly. Simulate an adversarial addition.
        bad = _mk_obs("2020-01-01", "REC-Y2", "TCS")
        bad["schema_version"] = 1
        bad["snapshot_ts_utc"] = "2020-01-02T00:00:00+00:00"
        bad["prev_row_hash"] = led.last_hash()
        from india.monitoring.MON001_Forward_Validation.forward_ledger import _hash_row
        bad["row_hash"] = _hash_row({k: v for k, v in bad.items() if k != "row_hash"})
        with led.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(bad) + "\n")
        integrity = led.verify_chain()
        assert not integrity["ok"] and "forward boundary" in integrity["reason"]
    print("  TEST 21 PASS: hand-inserted pre-boundary row detected by verify_chain")


def test_22_lab_evidence_files_readonly():
    # MON001 must never write into LAB folders. Sanity-check the LAB009 CSV exists but
    # has not been modified by importing our modules.
    diag = ROOT / "india/ai_lab/LAB009_Horizon_Phase_Recalibration/reports/lab009_period_corrected_diagnostics_2026-07-13.csv"
    if not diag.exists():
        print("  TEST 22 SKIP: LAB009 diagnostics not present")
        return
    before = diag.stat().st_mtime_ns
    _ = build_envelope(diag, "N0", 63, 15.0, [0.0, 0.06])
    after = diag.stat().st_mtime_ns
    assert before == after, "MON001 must NOT modify LAB009 evidence files"
    print("  TEST 22 PASS: MON001 envelope build does not modify LAB009 evidence")


def test_23_metric_evaluation_returns_insufficient_below_threshold():
    # Feed 10 daily returns — below the 30-day threshold → INSUFFICIENT_EVIDENCE for Sharpe.
    fake_daily = pd.Series(np.random.RandomState(42).randn(10) * 0.01,
                            index=pd.date_range("2026-06-01", periods=10))
    fake_env = {
        "metrics": {
            "sharpe_full": {"0.0": {"min": 1.0, "median": 1.2, "max": 1.4,
                                      "phases": [1.0, 1.1, 1.2, 1.4], "n_phases": 4}},
            "max_dd_full": {"0.0": {"min": -0.17, "median": -0.15, "max": -0.10,
                                      "phases": [-0.17, -0.16, -0.14, -0.10], "n_phases": 4}},
        },
        "median_row": {"0.0": {}},
    }
    cfg = {"daily_metrics_days": 30, "maxdd_days": 126}
    ev = evaluate_metric_evidence(fake_daily, fake_env, cfg)
    sharpe_ev = next(e for e in ev if e.metric == "sharpe_forward")
    assert sharpe_ev.status == "INSUFFICIENT_EVIDENCE"
    print("  TEST 23 PASS: Sharpe reports INSUFFICIENT_EVIDENCE below 30-day threshold")


def test_24_cumulative_strategy_search_unchanged():
    manifest_path = ROOT / "india/ai_lab/trial_manifest.md"
    text = manifest_path.read_text(encoding="utf-8", errors="ignore")
    assert "cumulative_strategy_search: 38" in text, (
        "MON001 must not have incremented cumulative_strategy_search")
    print("  TEST 24 PASS: cumulative_strategy_search unchanged at 38")


def test_25_production_constants_unchanged():
    reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    assert "HOLD = 63" in reg, "HOLD must remain 63"
    assert "rebal=63" in gen, "rebal must remain 63"
    print("  TEST 25 PASS: HOLD=63 and rebal=63 remain in production code")


TESTS = [
    test_1_clean_paper_observation,
    test_2_rejects_pre_boundary_asof,
    test_3_duplicate_rec_id_same_fingerprint,
    test_4_retroactive_mutation_detected,
    test_5_paper_broker_field_separation,
    test_6_fingerprint_matches_when_no_change,
    test_7_fingerprint_detects_file_change,
    test_8_fingerprint_detects_constant_change,
    test_9_fingerprint_missing_file_raises,
    test_10_envelope_matches_lab009_diagnostics,
    test_11_envelope_cache_byte_identity_or_raise,
    test_12_broker_layer_paper_only,
    test_13_concentration_detects_name_cap_breach,
    test_14_concentration_detects_sector_breach,
    test_15_data_drift_stale_and_missing,
    test_16_correction_appended_not_mutated,
    test_17_insufficient_evidence_state,
    test_18_config_drift_forces_halt,
    test_19_data_integrity_failure_forces_halt,
    test_20_diverged_needs_four_weeks_for_halt,
    test_21_ledger_boundary_leak_detection,
    test_22_lab_evidence_files_readonly,
    test_23_metric_evaluation_returns_insufficient_below_threshold,
    test_24_cumulative_strategy_search_unchanged,
    test_25_production_constants_unchanged,
]


def main():
    print("=" * 70)
    print("  MON001 FRAMEWORK TESTS — 25 adversarial scenarios")
    print("=" * 70)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__} FAIL: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(TESTS)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
