"""M2 · conditional cohort analyzer property tests."""
from backend.research.mr_conditional_cohorts import (
    _tag, _cohort_stats, enumerate_combos, FEATURES, MIN_COMBO_N,
)


def test_tag_returns_none_when_any_feature_missing():
    row = {"runner":"R1"}  # missing band
    assert _tag(row, ["runner","band"]) is None


def test_tag_returns_ordered_tuple():
    row = {"runner":"R2", "investability_band":"MARGINAL"}
    t = _tag(row, ["runner","band"])
    assert t == ("runner=R2","band=MARGINAL")


def test_cohort_stats_returns_zero_when_empty():
    assert _cohort_stats([])["n"] == 0


def test_cohort_stats_computes_wr():
    rows = [{"fwd_5d_pct": 1.0}, {"fwd_5d_pct": 1.0}, {"fwd_5d_pct": -1.0}]
    s = _cohort_stats(rows)
    assert s["n"] == 3
    assert s["wr_pct"] == round(2/3*100, 2)


def test_enumerate_combos_respects_min_n():
    # Make 15 rows so 1 combo passes and one bucket doesn't
    rows = ([{"runner":"R1","investability_band":"QUALITY","fwd_5d_pct":+1.0}] * 25
            + [{"runner":"R2","investability_band":"OK","fwd_5d_pct":-1.0}] * 10)
    combos = enumerate_combos(rows, 2, baseline_wr=50.0, multiple_tests=1)
    # Only the R1+QUALITY combo should meet MIN_COMBO_N=20
    tags = [tuple(c["combo"]) for c in combos]
    assert ("runner=R1","band=QUALITY") in tags
    assert ("runner=R2","band=OK") not in tags


def test_enumerate_combos_orders_by_edge():
    rows = ([{"runner":"R1","investability_band":"QUALITY","fwd_5d_pct":+1.0}] * 25
            + [{"runner":"R1","investability_band":"OK","fwd_5d_pct":-1.0}] * 25)
    combos = enumerate_combos(rows, 2, baseline_wr=50.0, multiple_tests=1)
    # First returned should have highest edge
    assert combos[0]["edge_vs_baseline_pp"] >= combos[-1]["edge_vs_baseline_pp"]


def test_features_registry_has_expected_keys():
    for k in ("runner","band","sector","cap","trend","rank_slot","rsi",
              "conf","vol","ma20","mom20"):
        assert k in FEATURES
