"""ENG001 full-repo regression harness.

Runs every existing test suite via subprocess AND verifies invariance:
- MON001 fingerprint is byte-identical to seal
- HOLD, rebal, sector_cap, name_cap, method unchanged
- cumulative_strategy_search unchanged at 38
- LAB001-LAB010 folder contents unchanged
- forward boundary unchanged

Run:
    python nexaquant/tests/test_regression.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


SUITES = [
    ("MON001 core",           ROOT / "india/monitoring/MON001_Forward_Validation/test_mon001_framework.py"),
    ("MON001 ops",            ROOT / "india/monitoring/MON001_Forward_Validation/test_mon001_ops.py"),
    ("LAB010 framework",      ROOT / "india/ai_lab/LAB010_H84_Robustness_Validation/test_lab010_framework.py"),
    ("Core lab framework",    ROOT / "india/ai_lab/tests/test_lab_framework.py"),
    ("LAB009 maturity",       ROOT / "india/ai_lab/LAB009_Horizon_Phase_Recalibration/test_maturity_correction.py"),
    ("ENG001 lib unit tests", ROOT / "nexaquant/tests/test_lib.py"),
]


def _run(label: str, path: Path) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True,
                        cwd=str(ROOT))
    tail = (r.stdout + r.stderr).strip().splitlines()[-4:]
    return r.returncode == 0, "\n".join(tail)


def test_suites_pass():
    print("=" * 70)
    print("  ENG001 REGRESSION — run every test suite in the repo")
    print("=" * 70)
    all_pass = True
    for label, path in SUITES:
        ok, tail = _run(label, path)
        icon = "OK" if ok else "FAIL"
        print(f"  [{icon}] {label:<25}  ({path.name})")
        if not ok:
            for line in tail.splitlines():
                print(f"        {line}")
            all_pass = False
    if not all_pass:
        raise AssertionError("one or more upstream suites failed")
    print("\n  All suites PASS.")


def test_mon001_fingerprint_matches_seal():
    from india.monitoring.MON001_Forward_Validation.fingerprint import compute_fingerprint
    import yaml
    with (ROOT / "india/monitoring/MON001_Forward_Validation/mon001.yaml").open() as f:
        cfg = yaml.safe_load(f)
    sealed = json.loads((ROOT / "india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json").read_text(encoding="utf-8"))
    current = compute_fingerprint(ROOT, cfg["baseline_files"], cfg["baseline_constants"])
    assert current["hash"] == sealed["hash"], (
        f"CONFIG_DRIFT: sealed {sealed['hash']} vs current {current['hash']}")
    print(f"  fingerprint: OK ({current['hash'][:16]}... == sealed)")


def test_production_constants():
    reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    assert "HOLD = 63" in reg
    assert "rebal=63" in gen
    assert "sector_cap=2" in gen
    assert "name_cap=0.30" in gen
    assert 'method="hrp"' in gen
    print("  production constants: HOLD=63, rebal=63, sector_cap=2, name_cap=0.30, method=hrp — OK")


def test_trial_manifest():
    m = (ROOT / "india/ai_lab/trial_manifest.md").read_text(encoding="utf-8", errors="ignore")
    assert "cumulative_strategy_search: 38" in m
    print("  cumulative_strategy_search = 38 — OK")


def test_mon001_forward_boundary():
    import yaml
    with (ROOT / "india/monitoring/MON001_Forward_Validation/mon001.yaml").open() as f:
        cfg = yaml.safe_load(f)
    assert cfg["forward_boundary_asof"] == "2026-03-28"
    print("  MON001 forward_boundary_asof = 2026-03-28 — OK")


def test_no_sealed_files_modified_by_eng001():
    """Every file listed here MUST have zero uncommitted diff vs HEAD.
    A change to any of these would trip MON001 or invalidate lab evidence."""
    r = subprocess.run(["git", "diff", "HEAD", "--name-only"],
                        cwd=str(ROOT), capture_output=True, text=True)
    changed = set(line.strip().replace("\\", "/") for line in r.stdout.splitlines() if line.strip())
    forbidden = {
        "india/recommendation_registry.py",
        "india/recommendation_generator.py",
        "india/confidence_engine.py",
        "india/arjuna_v2.py",
        "india/data_nse.py",
        "india/monitoring/MON001_Forward_Validation/preregistration.md",
        "india/monitoring/MON001_Forward_Validation/mon001.yaml",
        "india/monitoring/MON001_Forward_Validation/monitor.py",
        "india/monitoring/MON001_Forward_Validation/forward_ledger.py",
        "india/monitoring/MON001_Forward_Validation/fingerprint.py",
        "india/monitoring/MON001_Forward_Validation/baseline_envelope.py",
        "india/monitoring/MON001_Forward_Validation/broker_layer.py",
    }
    lab_paths = [p for p in changed if p.startswith("india/ai_lab/")
                 and not p.endswith("__pycache__")]
    forbidden_touched = forbidden & changed
    assert not forbidden_touched, f"ENG001 modified sealed files: {sorted(forbidden_touched)}"
    assert not lab_paths, f"ENG001 modified LAB001-LAB010 artifacts: {lab_paths}"
    print(f"  sealed + LAB files unchanged (changed_files={len(changed)}, sealed_touched=0, lab_touched=0)")


def main():
    print()
    test_suites_pass()
    print()
    print("=" * 70)
    print("  ENG001 INVARIANCE GUARDS")
    print("=" * 70)
    test_mon001_fingerprint_matches_seal()
    test_production_constants()
    test_trial_manifest()
    test_mon001_forward_boundary()
    test_no_sealed_files_modified_by_eng001()
    print("\n  ALL INVARIANCE GUARDS HOLD.")


if __name__ == "__main__":
    main()
