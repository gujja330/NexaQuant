"""Trial accounting · declared vs actual · Constitution invariant."""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research.trial_accounting import load_declared_trials

_ROOT = Path(__file__).resolve().parents[2]


def test_trial_matrix_declared_in_schema():
    declared = load_declared_trials(_ROOT)
    # Every P0-P5 + R3 GBM baseline must be declared
    required = {"P0_exit_bridge", "P1_calibration",
                "P2_sector_regime", "P3_kg_gamma",
                "P4_cap_sector_lr", "R3_gbm_baseline"}
    missing = required - set(declared.keys())
    assert not missing, f"Trial matrix missing: {missing}"


def test_trial_counts_match_pasted_plan_matrix():
    """Pasted-plan Sec 28 fixes trial counts · silent drift is a violation."""
    declared = load_declared_trials(_ROOT)
    assert declared.get("P0_exit_bridge") == 1
    assert declared.get("P1_calibration") == 1
    assert declared.get("P2_sector_regime") == 9   # 3x3 alpha,beta grid
    assert declared.get("P3_kg_gamma") == 5        # {0,0.1,0.2,0.3,0.4}
    assert declared.get("P4_cap_sector_lr") == 1
    assert declared.get("R3_gbm_baseline") == 1
