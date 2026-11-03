"""PIE scoring · point-in-time correctness, determinism, and abstention.

The tests that matter most here are the ones that would fail if PIE had
inherited R2's defects: a classifier whose output is a function of
universe size, a calibration fitted on its own evaluation data, or a
feature that quietly carries tomorrow's bar.

Every fixture is synthetic and tmp_path-isolated. No live registry,
report or price file is read or written.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from backend.research.priority_intelligence import features as F
from backend.research.priority_intelligence import scoring as S


def _bars(tmp_path, market, ticker, n=400, start="2025-01-01", drift=0.001):
    """A deterministic ascending price series with volume."""
    idx = pd.bdate_range(start, periods=n)
    close = [100.0 * math.exp(drift * i) for i in range(n)]
    df = pd.DataFrame({"open": close, "high": [c * 1.01 for c in close],
                       "low": [c * 0.99 for c in close], "close": close,
                       "tick_volume": [1000 + i for i in range(n)],
                       "spread": [1] * n}, index=idx)
    from backend.research.r3_program import outcome_resolver as res
    p = tmp_path / (res.BARS[market] % ticker)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    res._cache.clear()
    return df


def _row(**kw):
    """A row shaped like production: every bar feature present, the
    structurally-abstaining dimensions absent. Giving sector a value here
    would make the abstention tests pass against a universe that does not
    exist."""
    base = {f: 0.0 for f in S.scored_features()}
    for f in F.STRUCTURAL_ABSTENTIONS:
        base[f] = None
    base.update(kw)
    return base


def _train(n=120, spread=1.0):
    """Training rows spanning a known range, over several entry dates."""
    rows = []
    for i in range(n):
        v = -spread + 2 * spread * (i / max(1, n - 1))
        rows.append({**_row(**{f: v for f in S.scored_features()
                               if f not in F.STRUCTURAL_ABSTENTIONS}),
                     "entry_date": "2026-08-%02d" % (1 + i % 28)})
    return rows


# ------------------------------------------------------------ PIT features

class TestPointInTimeFeatures:
    def test_no_feature_carries_a_bar_after_the_decision_date(self, tmp_path):
        _bars(tmp_path, "india", "AAA", n=400)
        f = F.all_features(tmp_path, "india", "AAA", "2026-01-15",
                           pd.DataFrame())
        F.assert_no_lookahead(f, "2026-01-15")
        for k, v in f.items():
            if v.asof_bar:
                assert pd.Timestamp(v.asof_bar) <= pd.Timestamp("2026-01-15"), k

    def test_a_planted_future_bar_is_caught_not_averaged_away(self, tmp_path):
        f = {"x": F.Feature("x", 1.0, True, "2026-02-01", 10, "bars")}
        with pytest.raises(AssertionError, match="LOOKAHEAD"):
            F.assert_no_lookahead(f, "2026-01-15")

    def test_visible_bars_cuts_before_windowing_not_after(self, tmp_path):
        """The ordering that made R3's historical windows collapse to zero."""
        _bars(tmp_path, "india", "AAA", n=400, start="2025-01-01")
        w = F.visible_bars(tmp_path, "india", "AAA", "2025-06-30")
        assert w is not None and len(w) > 100
        assert w.index.max() <= pd.Timestamp("2025-06-30")

    def test_unavailable_feature_is_absent_never_zero(self, tmp_path):
        _bars(tmp_path, "india", "SHORT", n=30)
        f = F.bar_features(tmp_path, "india", "SHORT", "2025-03-01")
        assert f["sma200_ratio"].available is False
        assert f["sma200_ratio"].value is None
        assert "NEEDS_200_BARS" in f["sma200_ratio"].reason

    def test_asof_before_any_bar_yields_no_bars_not_a_crash(self, tmp_path):
        _bars(tmp_path, "india", "AAA", n=100, start="2025-01-01")
        f = F.bar_features(tmp_path, "india", "AAA", "2024-01-01")
        assert all(not v.available for v in f.values())
        assert f["ret_20d"].reason == "NO_BARS_ON_OR_BEFORE_ASOF"

    def test_feature_values_are_deterministic(self, tmp_path):
        _bars(tmp_path, "india", "AAA", n=400)
        a = F.bar_features(tmp_path, "india", "AAA", "2026-01-15")
        b = F.bar_features(tmp_path, "india", "AAA", "2026-01-15")
        assert {k: v.value for k, v in a.items()} == {k: v.value for k, v in b.items()}


class TestPriorEvidenceDoesNotLeak:
    @staticmethod
    def _eps(rows):
        return pd.DataFrame(rows)

    def test_only_episodes_closed_strictly_before_asof_are_counted(self):
        eps = self._eps([
            {"ticker": "AAA", "closed_date": "2026-01-01",
             "registry_realized_pct": 5.0, "registry_realized_resolved": True},
            {"ticker": "AAA", "closed_date": "2026-01-02",
             "registry_realized_pct": 5.0, "registry_realized_resolved": True},
            {"ticker": "AAA", "closed_date": "2026-01-03",
             "registry_realized_pct": 5.0, "registry_realized_resolved": True},
            {"ticker": "AAA", "closed_date": "2026-06-01",
             "registry_realized_pct": -99.0, "registry_realized_resolved": True},
        ])
        f = F.prior_evidence(eps, "AAA", "2026-02-01")
        assert f["prior_n"].value == 3.0
        assert f["prior_mean_ret"].value == pytest.approx(5.0)
        assert f["prior_win_rate"].value == pytest.approx(100.0)

    def test_an_episode_closing_on_the_decision_date_is_excluded(self):
        """`<` not `<=` · a same-day close is not yet a settled fact."""
        eps = self._eps([
            {"ticker": "AAA", "closed_date": "2026-02-01",
             "registry_realized_pct": 5.0, "registry_realized_resolved": True}
            for _ in range(5)])
        f = F.prior_evidence(eps, "AAA", "2026-02-01")
        assert f["prior_n"].available is False
        assert "ONLY_0_PRIOR_EPISODES" in f["prior_n"].reason

    def test_thin_history_abstains_rather_than_reporting_an_anecdote(self):
        eps = self._eps([
            {"ticker": "AAA", "closed_date": "2026-01-01",
             "registry_realized_pct": 50.0, "registry_realized_resolved": True}])
        f = F.prior_evidence(eps, "AAA", "2026-06-01")
        assert f["prior_win_rate"].available is False
        assert f["prior_win_rate"].value is None

    def test_other_tickers_history_does_not_count(self):
        eps = self._eps([
            {"ticker": "BBB", "closed_date": "2026-01-0%d" % i,
             "registry_realized_pct": 5.0, "registry_realized_resolved": True}
            for i in range(1, 6)])
        f = F.prior_evidence(eps, "AAA", "2026-06-01")
        assert f["prior_n"].available is False

    def test_evidence_timestamp_is_the_last_close_used(self):
        eps = self._eps([
            {"ticker": "AAA", "closed_date": "2026-01-0%d" % i,
             "registry_realized_pct": 1.0, "registry_realized_resolved": True}
            for i in range(1, 5)])
        f = F.prior_evidence(eps, "AAA", "2026-06-01")
        assert f["prior_n"].asof_bar == "2026-01-04"


class TestStructuralAbstentions:
    def test_sector_and_fundamentals_abstain_and_say_why(self):
        f = F.structural_abstentions()
        assert f["sector"].available is False
        assert f["sector"].reason == "SECTOR_EMPTY_IN_BOTH_MARKETS"
        assert f["fundamentals"].available is False
        assert f["fundamentals"].value is None

    def test_they_are_declared_not_silently_omitted(self):
        assert set(F.STRUCTURAL_ABSTENTIONS) == {"sector", "fundamentals"}


# ------------------------------------------------------------ calibration

class TestCalibrationUsesOnlyTheTrainingFold:
    def test_grid_contains_only_training_values(self):
        train = [{**_row(ret_20d=float(i)), "entry_date": "2026-08-01"}
                 for i in range(10)]
        cal = S.fit(train)
        assert cal.feature_grid["ret_20d"] == [float(i) for i in range(10)]
        assert cal.n_train_rows == 10

    def test_a_test_value_beyond_training_support_clamps(self):
        cal = S.fit([{**_row(ret_20d=float(i)), "entry_date": "2026-08-01"}
                     for i in range(10)])
        assert S._pct_in_grid(1e9, cal.feature_grid["ret_20d"]) == 1.0
        assert S._pct_in_grid(-1e9, cal.feature_grid["ret_20d"]) == 0.0

    def test_missing_values_do_not_enter_the_grid_as_zero(self):
        train = ([{**_row(ret_20d=5.0), "entry_date": "2026-08-01"}] * 3
                 + [{**_row(), "entry_date": "2026-08-02", "ret_20d": None}] * 7)
        cal = S.fit(train)
        assert cal.feature_grid["ret_20d"] == [5.0, 5.0, 5.0]

    def test_fingerprint_is_stable_for_an_identical_fit(self):
        t = _train()
        assert S.fit(t).fingerprint() == S.fit(t).fingerprint()

    def test_fingerprint_changes_when_the_training_data_changes(self):
        a = S.fit(_train(n=100))
        b = S.fit(_train(n=101))
        assert a.fingerprint() != b.fingerprint()

    def test_bands_come_from_training_scores_only(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        assert set(cal.bands) == {"P1", "P2", "WATCH"}
        assert cal.bands["P1"] >= cal.bands["P2"] >= cal.bands["WATCH"]
        assert cal.n_band_rows > 0


class TestScoringIsDeterministic:
    def test_same_row_same_calibration_same_score(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        r = _row(**{f: 0.3 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS})
        a, b = S.score_row(r, cal), S.score_row(r, cal)
        assert a["score"] == b["score"]
        assert a["pie_class"] == b["pie_class"]

    def test_dimension_detail_reports_presence_and_weight(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        out = S.score_row(_row(ret_20d=0.5), cal)
        d = out["dimensions"]
        assert d["momentum"]["available"] is True
        assert d["sector"]["available"] is False
        assert d["sector"]["score"] is None
        assert sum(v["weight"] for v in d.values()) == pytest.approx(1.0)

    def test_available_weight_excludes_abstaining_dimensions(self):
        """Both live cases · 0.85 with prior evidence, 0.70 without.

        These are the only two values the India run produces (measured:
        available_weight min 0.70, max 0.85 over 247 episodes), because
        sector and fundamentals abstain for every name.
        """
        cal = S.fit_bands(S.fit(_train()), _train())
        with_evidence = S.score_row(_row(), cal)
        assert with_evidence["available_weight"] == pytest.approx(0.85, abs=1e-6)
        assert with_evidence["designed_weight"] == pytest.approx(1.0)

        r = _row()
        r["prior_win_rate"] = r["prior_mean_ret"] = None
        without = S.score_row(r, cal)
        assert without["available_weight"] == pytest.approx(0.70, abs=1e-6)
        assert without["dimensions"]["evidence"]["available"] is False

    def test_higher_is_better_for_positive_sign_features(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        lo = S.score_row(_row(**{f: -1.0 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS}), cal)
        hi = S.score_row(_row(**{f: 1.0 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS}), cal)
        assert hi["score"] > lo["score"]

    def test_volatility_is_scored_with_a_negative_sign(self):
        """More volatility must not raise the score."""
        cal = S.fit_bands(S.fit(_train()), _train())
        calm = S.score_row(_row(vol_20d=-1.0), cal)
        wild = S.score_row(_row(vol_20d=1.0), cal)
        assert calm["dimensions"]["risk"]["score"] > wild["dimensions"]["risk"]["score"]


class TestAbstention:
    def test_below_the_weight_floor_the_verdict_is_abstain_not_a_low_score(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        only_liquidity = {f: None for f in S.scored_features()}
        only_liquidity["liquidity_20d"] = 0.5
        out = S.score_row(only_liquidity, cal)
        assert out["pie_class"] == S.CLASS_ABSTAIN
        assert out["score"] is None, "abstain must not carry a score"
        assert "BELOW" in out["abstain_reason"]

    def test_abstain_is_not_counted_as_actionable(self):
        rows = [{"pie_class": S.CLASS_ABSTAIN}] * 10
        c = S.class_counts(rows)
        assert c["n_actionable"] == 0 and c["ABSTAIN"] == 10

    def test_a_row_with_no_features_at_all_abstains(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        out = S.score_row({f: None for f in S.scored_features()}, cal)
        assert out["pie_class"] == S.CLASS_ABSTAIN


class TestClassificationIsNotAFunctionOfUniverseSize:
    """The property R2's percentile classifier does not have.

    Phase 1 proved R2 returns 40.35% actionable on pure noise as on real
    signal. PIE's cutoffs are absolute and fitted on training folds, so
    the actionable count must move with the quality of the test names.
    """

    @staticmethod
    def _share(cal, rows):
        res = [S.score_row(r, cal) for r in rows]
        return S.class_counts(res)["actionable_share"]

    def test_a_uniformly_poor_test_fold_yields_few_or_no_actionables(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        poor = [_row(**{f: -1.0 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS})
                for _ in range(200)]
        assert self._share(cal, poor) == 0.0

    def test_a_uniformly_strong_test_fold_yields_many(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        strong = [_row(**{f: 1.0 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS})
                  for _ in range(200)]
        assert self._share(cal, strong) == 1.0

    def test_the_share_is_independent_of_how_many_names_are_scored(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        poor = _row(**{f: -1.0 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS})
        for n in (10, 100, 1000):
            assert self._share(cal, [poor] * n) == 0.0

    def test_doubling_the_universe_does_not_double_the_actionables(self):
        cal = S.fit_bands(S.fit(_train()), _train())
        mixed = ([_row(**{f: 1.0 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS})] * 10
                 + [_row(**{f: -1.0 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS})] * 90)
        a = S.class_counts([S.score_row(r, cal) for r in mixed])
        b = S.class_counts([S.score_row(r, cal) for r in mixed * 2])
        assert b["n_actionable"] == 2 * a["n_actionable"]
        assert a["actionable_share"] == pytest.approx(b["actionable_share"])

    def test_this_is_the_opposite_of_the_r2_percentile_behaviour(self):
        """Side by side, on the same uniformly-poor input.

        The percentile classifier promotes the top 20% of a uniformly bad
        universe. PIE promotes none of it. That difference is the entire
        justification for PIE having its own classification.
        """
        from backend.recommendation.percentile_classifier import (
            classify_by_percentile)
        poor_pct = [{"ticker": "T%03d" % i, "ensemble_score": -5.0 + i * 1e-6,
                     "calibrated_confidence": 0.35} for i in range(200)]
        r2 = classify_by_percentile(poor_pct)
        r2_actionable = sum(1 for d in r2.decisions if d["action"] != "HOLD")
        assert r2_actionable > 0, "R2 acts on a uniformly bad universe"

        cal = S.fit_bands(S.fit(_train()), _train())
        poor = [_row(**{f: -1.0 for f in S.scored_features() if f not in F.STRUCTURAL_ABSTENTIONS})
                for _ in range(200)]
        pie_actionable = S.class_counts(
            [S.score_row(r, cal) for r in poor])["n_actionable"]
        assert pie_actionable == 0, "PIE declines the same universe"
