"""Signal Silence trigger + MVS floor + relaxation cap tests."""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research.governance import (
    evaluate_signal_silence, evaluate_mvs_floor, RelaxationTracker,
)


def test_silence_fires_when_streak_ge_10_and_baseline_nonzero():
    r = evaluate_signal_silence("R2", 12, 2.0, False)
    assert r["fired"] is True


def test_silence_never_fires_when_all_runners_silent():
    r = evaluate_signal_silence("R2", 30, 5.0, True)
    assert r["fired"] is False


def test_silence_doesnt_fire_below_threshold():
    r = evaluate_signal_silence("R2", 7, 2.0, False)
    assert r["fired"] is False


def test_mvs_below_floor_relaxes_gate():
    r = evaluate_mvs_floor(1, min_signals=3)
    assert r["below_floor"] is True
    assert r["action"] == "GATE_RELAXED_RERUN_OPERATOR_FLAG"


def test_mvs_above_floor_normal():
    r = evaluate_mvs_floor(5, min_signals=3)
    assert r["below_floor"] is False


def test_relaxation_cap_15_per_90d(tmp_path):
    tr = RelaxationTracker(tmp_path)
    for i in range(15):
        tr.record_relaxation("2026-09-03", "india", f"test{i}")
    r = tr.can_relax("2026-09-03")
    assert r["remaining"] == 0
    assert r["allowed"] is False
