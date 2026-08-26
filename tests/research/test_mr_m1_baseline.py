"""AEGIS · M-R · M1 baseline measurement · tests.

Verifies M1 measurement isolation, arithmetic, statistical-verdict
thresholds, and India+USA parallel-emit contract.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import pytest


def test_statistical_verdict_thresholds():
    from backend.research.mr_m1_baseline import _statistical_verdict
    assert _statistical_verdict(0)   == "OBSERVATION_ONLY"
    assert _statistical_verdict(19)  == "OBSERVATION_ONLY"
    assert _statistical_verdict(20)  == "INSUFFICIENT_EVIDENCE"
    assert _statistical_verdict(99)  == "INSUFFICIENT_EVIDENCE"
    assert _statistical_verdict(100) == "PRODUCTION_CANDIDATE"


def test_wilson_ci_symmetry_near_half():
    from backend.research.mr_m1_baseline import _wilson_95
    lo, hi = _wilson_95(50, 100)
    assert lo < 50 and hi > 50
    assert abs((hi - 50) - (50 - lo)) < 5     # roughly symmetric near 0.5


def test_wilson_ci_zero_and_full():
    from backend.research.mr_m1_baseline import _wilson_95
    lo0, hi0 = _wilson_95(0, 10)
    assert lo0 == 0.0 and hi0 > 0
    lo1, hi1 = _wilson_95(10, 10)
    assert hi1 == 100.0 and lo1 < 100


def test_wilson_ci_n_zero():
    from backend.research.mr_m1_baseline import _wilson_95
    lo, hi = _wilson_95(0, 0)
    assert lo is None and hi is None


def test_metrics_empty_cohort():
    from backend.research.mr_m1_baseline import _metrics
    m = _metrics("EMPTY", [])
    assert m.n == 0
    assert m.win_rate_pct is None
    assert m.statistical_verdict == "OBSERVATION_ONLY"


def test_metrics_arithmetic():
    from backend.research.mr_m1_baseline import _metrics
    trades = [
        {"pnl_pct":  5.0, "hold_days": 10},
        {"pnl_pct": -3.0, "hold_days":  8},
        {"pnl_pct": 10.0, "hold_days": 20},
        {"pnl_pct": -2.0, "hold_days":  5},
        {"pnl_pct":  0.0, "hold_days":  1},
    ]
    m = _metrics("TEST", trades)
    assert m.n == 5
    assert m.n_win == 2      # >0.5
    assert m.n_loss == 2     # <-0.5
    assert m.n_flat == 1
    assert abs(m.avg_return_pct - 2.0) < 0.01
    assert m.profit_factor == round((5+10) / (3+2), 3)   # 3.0
    assert m.avg_hold_days == round((10+8+20+5+1)/5, 1)


def test_m1_emit_only_under_research(tmp_path):
    from backend.research.mr_m1_baseline import emit
    rep = {"engine":"test","market":"india","cohorts":{}}
    p = emit(tmp_path, "india", rep)
    assert str(p).replace("\\","/").endswith(
        "reports/research/mr_m1_baseline_india.json")


def test_m1_emit_global_only_under_global(tmp_path):
    from backend.research.mr_m1_baseline import emit_global
    per_market = {
        "india": {"cohorts": {"ALL": {"n":0, "win_rate_pct":None,
                  "win_rate_ci_low_pct":None,"win_rate_ci_high_pct":None,
                  "avg_return_pct":None,"profit_factor":None,
                  "statistical_verdict":"OBSERVATION_ONLY"}}}
    }
    p = emit_global(tmp_path, per_market)
    assert str(p).replace("\\","/").endswith(
        "reports/global/mr_m1_baseline_comparison.json")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "verdict_by_market" in d
    assert d["verdict_by_market"]["india"] == "OBSERVATION_ONLY"
