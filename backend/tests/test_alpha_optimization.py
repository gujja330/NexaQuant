"""Alpha Optimization + Scale Adapter + DNA Backfill tests · Article 101.2."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.certification.alpha_optimization import (  # noqa: E402
    compute_alpha_report, _spearman_rank_corr, _pearson_corr, _t_stat,
    _suggested_weights, _sector_tilts,
    SCHEMA_FINGERPRINT as AO_FP,
)
from backend.certification.confidence_scale_adapter import (  # noqa: E402
    fit_scale_map, align_runner2_confidence, apply_scale_adapter_to_recs,
    SCHEMA_FINGERPRINT as CSA_FP,
)


# ── Alpha Optimization ──────────────────────────────────────
def test_alpha_report_schema():
    import pandas as pd
    df = pd.DataFrame({"return_pct": [1, -1, 2, -2], "dim_x": [1, 2, 3, 4],
                        "sector": ["A"]*4})
    rep = compute_alpha_report(df)
    assert rep.schema_fingerprint == AO_FP
    assert rep.n_trades == 4


def test_alpha_dimension_analysis_produces_ic():
    import pandas as pd
    df = pd.DataFrame({
        "return_pct": [1, 2, 3, 4, 5, -1, -2, -3, -4, -5]*5,
        "dim_x":      [5, 4, 3, 2, 1, 1, 2, 3, 4, 5]*5,
        "dim_y":      [1, 2, 3, 4, 5, -5, -4, -3, -2, -1]*5,
        "sector":     ["A"]*50,
    })
    rep = compute_alpha_report(df)
    # dim_y strongly positive with return
    assert rep.dimension_analysis["dim_y"]["ic_pearson"] > 0.5
    # dim_x inversely correlated
    assert rep.dimension_analysis["dim_x"]["ic_pearson"] < -0.3


def test_alpha_interaction_effects():
    import pandas as pd
    df = pd.DataFrame({
        "return_pct": [3.0]*30 + [-3.0]*30,
        "dim_a":      [1.0]*30 + [0.0]*30,
        "dim_b":      [1.0]*30 + [0.0]*30,
        "sector":     ["A"]*60,
    })
    rep = compute_alpha_report(df)
    key = next(iter(rep.interaction_effects))
    assert rep.interaction_effects[key]["mean_return_both_high_pct"] > 0
    assert rep.interaction_effects[key]["mean_return_both_low_pct"] < 0


def test_alpha_sector_tilts_classification():
    partition = {
        "AlphaSec": {"n": 50, "win_rate": 0.75, "mean_return_pct": 3.0, "profit_factor": 2.0},
        "MehSec":   {"n": 50, "win_rate": 0.55, "mean_return_pct": 0.5, "profit_factor": 1.0},
        "BadSec":   {"n": 50, "win_rate": 0.35, "mean_return_pct": -2.0, "profit_factor": 0.5},
        "TinySec":  {"n": 5,  "win_rate": 0.60, "mean_return_pct": 1.0, "profit_factor": 1.2},
    }
    tilts = _sector_tilts(partition, min_n=30)
    assert tilts["AlphaSec"]["recommendation"] == "BOOST"
    assert tilts["BadSec"]["recommendation"] == "UNDERWEIGHT"
    assert tilts["TinySec"]["tilt"] == 0.0


def test_alpha_suggested_weights_normalize():
    dim_analysis = {
        "dim_strong": {"ic_pearson": 0.10, "ic_spearman": 0.11, "t_stat": 2.0, "hit_rate_above_median": 0.6, "n": 100},
        "dim_weak":   {"ic_pearson": 0.01, "ic_spearman": 0.02, "t_stat": 0.5, "hit_rate_above_median": 0.5, "n": 100},
        "dim_neg":    {"ic_pearson": -0.08, "ic_spearman": -0.09, "t_stat": -2.5, "hit_rate_above_median": 0.4, "n": 100},
    }
    w = _suggested_weights(dim_analysis)
    assert w["dim_strong"] > 0
    assert w["dim_weak"] == 0.0
    assert w["dim_neg"] > 0
    total = sum(w.values())
    assert abs(total - 1.0) < 0.01


def test_alpha_pearson_and_spearman_agree_on_monotonic():
    x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]
    assert _pearson_corr(x, y) > 0.99
    assert _spearman_rank_corr(x, y) > 0.99


# ── Scale Adapter ───────────────────────────────────────────
def test_scale_map_fingerprint():
    import pandas as pd
    m = fit_scale_map(pd.Series([0.85, 0.9, 0.95, 1.0]))
    from dataclasses import asdict
    assert asdict(m)["schema_fingerprint"] == CSA_FP


def test_scale_map_fits_percentiles():
    import pandas as pd
    m = fit_scale_map(pd.Series([0.8, 0.85, 0.9, 0.92, 0.94, 0.96, 0.98, 1.0]))
    assert m.historical_min == 0.80
    assert m.historical_max == 1.00
    assert m.historical_p50 > 0.9
    assert m.historical_p95 > m.historical_p50


def test_scale_adapter_stretches_to_historical_range():
    from dataclasses import asdict
    import pandas as pd
    m = asdict(fit_scale_map(pd.Series([0.85, 0.9, 0.95, 1.0])))
    aligned_low = align_runner2_confidence(0.0, m)
    aligned_high = align_runner2_confidence(1.0, m)
    aligned_mid = align_runner2_confidence(0.5, m)
    # low should map near P05, high near P95
    assert aligned_low <= aligned_high
    assert m["historical_p05"] <= aligned_low <= aligned_high <= m["historical_p95"]


def test_scale_adapter_enriches_recs():
    from dataclasses import asdict
    import pandas as pd
    m = asdict(fit_scale_map(pd.Series([0.85, 0.9, 0.95, 1.0])))
    recs = [{"ticker": "T", "confidence": 0.004}]
    enriched = apply_scale_adapter_to_recs(recs, m)
    assert "aligned_confidence" in enriched[0]
    assert m["historical_p05"] <= enriched[0]["aligned_confidence"] <= m["historical_p95"]
