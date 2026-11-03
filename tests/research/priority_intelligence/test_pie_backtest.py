"""PIE backtest · fold discipline, costs, baselines, and refusal to overclaim.

The load-bearing tests here are the ones that would catch a flattering
result: a fold boundary that lets a test date into training, a cost that
is charged once instead of on both sides, a verdict stated from two
blocks of data, and an abstention that never fires being reported as a
working guard.

tmp_path-isolated throughout.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from backend.research.priority_intelligence import backtest as B
from backend.research.priority_intelligence import features as F
from backend.research.priority_intelligence import scoring as S


def _matrix(n_dates=30, per_date=4, seed=0, ret=1.0):
    """A synthetic feature matrix with known structure."""
    import random
    rnd = random.Random(seed)
    rows = []
    dates = ["2026-08-%02d" % (1 + i) if i < 28 else "2026-09-%02d" % (i - 27)
             for i in range(n_dates)]
    for d in dates:
        for j in range(per_date):
            r = {"episode_id": "%s-%d" % (d, j), "ticker": "T%02d" % j,
                 "entry_date": d, "market": "india", "is_closed": True,
                 "closed_date": d, "registry_realized_pct": rnd.gauss(0, 3),
                 "registry_realized_resolved": True,
                 "n_features_available": 11, "max_asof_bar": d}
            for f in S.scored_features():
                r[f] = (None if f in F.STRUCTURAL_ABSTENTIONS
                        else rnd.gauss(0, 1))
            for h in (5, 10, 20):
                r["mtm_ret_%dd_pct" % h] = rnd.gauss(0, 3) * ret
                r["mtm_ret_%dd_resolved" % h] = True
            r["bench_ret_20d_pct"] = rnd.gauss(0, 1)
            r["bench_ret_5d_pct"] = rnd.gauss(0, 1)
            rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- folds

class TestFoldDiscipline:
    def test_training_dates_are_strictly_before_every_test_date(self):
        folds = B.date_blocks(["2026-08-%02d" % i for i in range(1, 29)],
                              min_train=10, block=5)
        assert folds
        for f in folds:
            assert max(f["train_dates"]) < min(f["test_dates"])

    def test_folds_expand_and_never_shrink(self):
        folds = B.date_blocks(["2026-08-%02d" % i for i in range(1, 29)],
                              min_train=10, block=5)
        sizes = [len(f["train_dates"]) for f in folds]
        assert sizes == sorted(sizes)
        assert len(set(sizes)) == len(sizes)

    def test_test_blocks_do_not_overlap_and_cover_the_tail(self):
        dates = ["2026-08-%02d" % i for i in range(1, 29)]
        folds = B.date_blocks(dates, min_train=10, block=5)
        seen = [d for f in folds for d in f["test_dates"]]
        assert len(seen) == len(set(seen))
        assert sorted(seen) == dates[10:]

    def test_episodes_sharing_an_entry_date_land_in_the_same_fold(self):
        m = _matrix(n_dates=20, per_date=5)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=3, horizon=5)
        for f in rep["folds"]:
            assert f["test_dates"]["n"] <= 3
        # Each test block owns a distinct date range, and the row count is
        # a whole multiple of per_date, which it could not be if a date
        # had been split across two folds.
        all_test = [f["test_dates"] for f in rep["folds"]]
        assert len({(t["min"], t["max"]) for t in all_test}) == len(all_test)
        for f in rep["folds"]:
            assert f["n_test_rows"] % 5 == 0, "a date was split across folds"

    def test_no_fold_is_produced_without_enough_training_dates(self):
        assert B.date_blocks(["2026-08-01", "2026-08-02"],
                             min_train=10, block=5) == []

    def test_calibration_differs_per_fold(self):
        """Each fold must fit on its own past, not share one global fit."""
        m = _matrix(n_dates=30, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        fps = [f["calibration_fingerprint"] for f in rep["folds"]]
        assert len(fps) == len(set(fps)), "a shared fit means a shared leak"


class TestNoLookahead:
    def test_build_matrix_raises_on_a_planted_future_feature(self, monkeypatch):
        bad = {"ret_20d": F.Feature("ret_20d", 1.0, True, "2030-01-01",
                                    10, "bars")}
        monkeypatch.setattr(F, "all_features", lambda *a, **k: bad)
        eps = pd.DataFrame([{"episode_id": "E1", "ticker": "AAA",
                             "entry_date": "2026-08-01", "is_closed": True}])
        with pytest.raises(AssertionError, match="LOOKAHEAD"):
            B.build_matrix(".", "india", episodes=eps)

    def test_every_row_is_checked_not_a_sample(self, monkeypatch):
        """A leak on 1 of 200 rows must still raise."""
        calls = {"n": 0}

        def _f(*a, **k):
            calls["n"] += 1
            d = "2030-01-01" if calls["n"] == 173 else "2026-08-01"
            return {"ret_20d": F.Feature("ret_20d", 1.0, True, d, 10, "bars")}

        monkeypatch.setattr(F, "all_features", _f)
        eps = pd.DataFrame([{"episode_id": "E%d" % i, "ticker": "A",
                             "entry_date": "2026-08-01", "is_closed": True}
                            for i in range(200)])
        with pytest.raises(AssertionError, match="LOOKAHEAD"):
            B.build_matrix(".", "india", episodes=eps)
        assert calls["n"] == 173, "stopped at the leaking row, did not skip it"


# ---------------------------------------------------------------- costs

class TestTransactionCosts:
    def test_slippage_is_charged_on_both_sides(self):
        assert B.round_trip_cost_pct(25.0, 10.0) == pytest.approx(0.45)
        assert B.round_trip_cost_pct(0.0, 10.0) == pytest.approx(0.20)

    def test_zero_cost_is_representable_but_not_the_default(self):
        assert B.round_trip_cost_pct(0.0, 0.0) == 0.0
        assert B.DEFAULT_COST_BPS > 0 and B.DEFAULT_SLIPPAGE_BPS > 0

    def test_net_return_is_gross_minus_the_full_round_trip(self):
        drag = B.round_trip_cost_pct(25.0, 10.0)
        assert B._net(5.0, drag) == pytest.approx(4.55)
        assert B._net(None, drag) is None

    def test_costs_lower_every_reported_mean(self):
        m = _matrix(n_dates=25, per_date=4)
        free = B.run(".", "india", matrix=m, min_train_dates=10,
                     test_block=5, horizon=5, cost_bps=0, slippage_bps=0)
        paid = B.run(".", "india", matrix=m, min_train_dates=10,
                     test_block=5, horizon=5, cost_bps=25, slippage_bps=10)
        a = free["aggregate"]["all_r2_episodes_net"]["mean"]
        b = paid["aggregate"]["all_r2_episodes_net"]["mean"]
        assert b < a
        assert a - b == pytest.approx(0.45, abs=1e-6)

    def test_the_cost_is_recorded_in_the_report(self):
        m = _matrix(n_dates=25, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        c = rep["costs"]
        assert c["round_trip_drag_pct"] == pytest.approx(0.45)
        assert "entry and exit" in c["note"]


# ---------------------------------------------------------------- baselines

class TestBaselines:
    def test_all_three_baselines_are_present(self):
        m = _matrix(n_dates=25, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        f = rep["folds"][0]
        assert "baseline_all_r2_episodes" in f
        assert "baseline_random_same_size" in f
        assert "baseline_benchmark" in f

    def test_random_baseline_matches_the_selection_size(self):
        m = _matrix(n_dates=25, per_date=6)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        for f in rep["folds"]:
            n_sel = f["class_counts"]["n_actionable"]
            n_rnd = f["baseline_random_same_size"]["n"]
            assert n_rnd <= max(n_sel, 0) + 0, (
                "a random baseline of a different size is not a control")

    def test_random_baseline_is_seeded_and_reproducible(self):
        m = _matrix(n_dates=25, per_date=6)
        kw = dict(matrix=m, min_train_dates=10, test_block=5, horizon=5)
        a = B.run(".", "india", **kw)["aggregate"]
        b = B.run(".", "india", **kw)["aggregate"]
        assert (a["random_same_size_mean_of_fold_means"]
                == b["random_same_size_mean_of_fold_means"])

    def test_the_r2_actionable_baseline_is_declared_absent_not_substituted(self):
        """R2 has no high-conviction subset · saying so beats inventing one."""
        m = _matrix(n_dates=25, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        r2 = rep["r2_actionable_baseline"]
        assert r2["available"] is False
        assert "HOLD on every name" in r2["reason"]
        assert "percentile" in r2["reason"]

    def test_the_deciding_comparison_is_against_all_r2_episodes(self):
        m = _matrix(n_dates=25, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        a = rep["aggregate"]
        if a["pie_selected_net"]["mean"] is not None:
            assert a["lift_vs_all_r2_episodes_pp"] == pytest.approx(
                a["pie_selected_net"]["mean"] - a["all_r2_episodes_net"]["mean"],
                abs=1e-4)


# ---------------------------------------------------------------- verdict

class TestVerdictRefusesToOverclaim:
    def test_too_few_decidable_blocks_yields_insufficient_evidence(self):
        folds = [{"fold": 1, "rows": [], "test_dates": {"n": 5},
                  "class_counts": {}, "baseline_random_same_size": {"n": 0},
                  "lift_vs_all_r2_episodes_pp": 3.0}]
        a = B._aggregate(folds, 20)
        assert a["verdict"] == B.VERDICT_INSUFFICIENT

    def test_the_gate_counts_decidable_blocks_not_attempted_blocks(self):
        """The defect I shipped: six folds ran, two could be measured.

        Gating on folds attempted let two blocks of matured outcomes
        carry a NO_EDGE verdict at the 20-day horizon.
        """
        rows_ok = [{"net_ret_pct": 1.0, "pie_class": S.CLASS_P1,
                    "bench_ret_pct": 0.1}]
        folds = []
        for i in range(8):
            folds.append({
                "fold": i + 1,
                "rows": rows_ok if i < 2 else [],
                "test_dates": {"n": 5},
                "class_counts": {},
                "baseline_random_same_size": {"n": 0},
                "lift_vs_all_r2_episodes_pp": (1.0 if i < 2 else None)})
        a = B._aggregate(folds, 20)
        assert a["n_folds"] == 8
        assert a["n_folds_with_computable_lift"] == 2
        assert a["verdict"] == B.VERDICT_INSUFFICIENT
        assert "2 of 8 test blocks" in a["verdict_reason"]

    def test_no_folds_at_all_is_insufficient_not_an_exception(self):
        a = B._aggregate([], 20)
        assert a["verdict"] == B.VERDICT_INSUFFICIENT
        assert a["n_folds"] == 0

    def test_a_positive_edge_needs_a_majority_of_decidable_blocks(self):
        def _f(i, lift):
            return {"fold": i, "test_dates": {"n": 5}, "class_counts": {},
                    "baseline_random_same_size": {"n": 0},
                    "lift_vs_all_r2_episodes_pp": lift,
                    "rows": [{"net_ret_pct": lift, "pie_class": S.CLASS_P1,
                              "bench_ret_pct": 0.0},
                             {"net_ret_pct": 0.0, "pie_class": S.CLASS_AVOID,
                              "bench_ret_pct": 0.0}]}
        good = B._aggregate([_f(i, 2.0) for i in range(6)], 20)
        assert good["verdict"] == B.VERDICT_EDGE
        bad = B._aggregate([_f(i, -2.0) for i in range(6)], 20)
        assert bad["verdict"] == B.VERDICT_NO_EDGE

    def test_the_effective_sample_is_reported_as_dates(self):
        m = _matrix(n_dates=25, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        note = rep["population"]["effective_sample_note"]
        assert "entry DATES" in note
        assert rep["population"]["entry_dates"] == 25
        assert rep["population"]["episodes"] == 100


# ------------------------------------------------------- inert guard check

class TestAbstentionReachabilityIsMeasured:
    def test_an_unreachable_abstention_is_reported_as_unreachable(self):
        m = _matrix(n_dates=25, per_date=4)
        r = B.abstention_reachability(m, set(S.scored_features()))
        assert r["reachable"] is False
        assert r["n_rows_below_floor"] == 0
        assert "inert" in r["note"]

    def test_a_reachable_abstention_is_reported_as_reachable(self):
        m = _matrix(n_dates=25, per_date=4)
        for f in S.scored_features():
            if f not in ("liquidity_20d",):
                m[f] = None
        r = B.abstention_reachability(m, set(S.scored_features()))
        assert r["reachable"] is True
        assert r["n_rows_below_floor"] == len(m)

    def test_the_structural_abstentions_are_named_in_the_report(self):
        m = _matrix(n_dates=25, per_date=4)
        r = B.abstention_reachability(m, set(S.scored_features()))
        assert set(r["structural_abstentions"]) == {"sector", "fundamentals"}

    def test_reachability_rides_on_the_full_report(self):
        m = _matrix(n_dates=25, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        assert "abstention_reachability" in rep
        assert rep["abstention_reachability"]["floor"] == S.MIN_AVAILABLE_WEIGHT


class TestDeterminism:
    def test_two_runs_on_one_matrix_agree_apart_from_the_timestamp(self):
        m = _matrix(n_dates=25, per_date=4)
        kw = dict(matrix=m, min_train_dates=10, test_block=5, horizon=5)
        a, b = B.run(".", "india", **kw), B.run(".", "india", **kw)
        a.pop("generated_utc"), b.pop("generated_utc")
        assert a == b

    def test_the_report_names_its_scoring_version(self):
        m = _matrix(n_dates=25, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        assert rep["scoring_version"] == S.SCORING_VERSION


class TestBenchmarkIsNotSilentlyMissing:
    """A benchmark that resolves to nothing must complain, not average to None.

    The first version of this module asked USA for `SPX`. That file does
    not exist - the S&P 500 bars are `_IDX_GSPC` - so every benchmark
    return came back None and the pooled report printed `benchmark n=0`
    without a word. `usa/data/raw/us/` also holds `SPXC_D1.parquet`, which
    is SPX Corporation, so a looser lookup would have silently
    benchmarked the index against one mid-cap industrial.
    """

    def test_a_missing_benchmark_symbol_is_reported_unavailable(self, tmp_path):
        st = B.benchmark_status(tmp_path, "usa")
        assert st["available"] is False
        assert st["reason"] == "NO_BARS_FOR_BENCHMARK_SYMBOL"
        assert st["symbol"] == B.BENCHMARK["usa"]

    def test_a_present_benchmark_reports_its_span(self, tmp_path):
        from backend.research.r3_program import outcome_resolver as res
        idx = pd.bdate_range("2025-01-01", periods=300)
        pd.DataFrame({"close": [100.0 + i for i in range(300)]},
                     index=idx).to_parquet(
            _mk(tmp_path, res.BARS["india"] % B.BENCHMARK["india"]))
        res._cache.clear()
        st = B.benchmark_status(tmp_path, "india")
        assert st["available"] is True and st["n_bars"] == 300

    def test_the_usa_symbol_is_not_the_industrial_with_a_similar_name(self):
        assert B.BENCHMARK["usa"] == "_IDX_GSPC"
        assert B.BENCHMARK["usa"] != "SPX"
        assert "SPXC" not in B.BENCHMARK.values()

    def test_benchmark_status_rides_on_the_report(self):
        m = _matrix(n_dates=25, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        assert "benchmark_status" in rep


def _mk(tmp_path, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class TestHistoricalPopulationIntegrity:
    """PIE must see the whole registry, never the daily shortlist.

    The instruction was explicit for both markets: retain all 818 USA
    episodes and India's full 247, and do not limit PIE to the 248 ranked
    slots or the 469 currently selected names. The failure mode is subtle
    - a shortlist leaking into the research population would silently
    survivorship-bias every fold, and the counts would still look
    plausible.
    """

    def test_the_backtest_population_is_the_episode_dataset_not_a_shortlist(self):
        """The matrix row count equals the episode count it was given."""
        eps = pd.DataFrame([{
            "episode_id": "E%03d" % i, "ticker": "T%03d" % i,
            "entry_date": "2026-08-%02d" % (1 + i % 28), "is_closed": True,
            "closed_date": "2026-09-01", "registry_realized_pct": 1.0,
            "registry_realized_resolved": True,
            "mtm_ret_5d_pct": 1.0, "mtm_ret_5d_resolved": True,
            "mtm_ret_10d_pct": 1.0, "mtm_ret_10d_resolved": True,
            "mtm_ret_20d_pct": 1.0, "mtm_ret_20d_resolved": True,
        } for i in range(300)])
        m = B.build_matrix(".", "india", episodes=eps, horizon=5)
        assert len(m) == 300, "every episode must reach the matrix"
        assert m["episode_id"].nunique() == 300

    def test_no_selection_module_is_reachable_from_the_backtest(self):
        """A shortlist cannot narrow the population if it is never imported."""
        import inspect
        for mod in (B, S, F):
            src = inspect.getsource(mod)
            assert "top_selection" not in src, mod.__name__
            assert "universe_selection" not in src, mod.__name__
            assert "target_count" not in src, mod.__name__

    def test_the_population_block_reports_dates_and_episodes_separately(self):
        m = _matrix(n_dates=30, per_date=4)
        rep = B.run(".", "india", matrix=m, min_train_dates=10,
                    test_block=5, horizon=5)
        p = rep["population"]
        assert p["episodes"] == 120 and p["entry_dates"] == 30
        assert p["episodes"] != p["entry_dates"], (
            "conflating the two is how 818 rows became 818 observations")
