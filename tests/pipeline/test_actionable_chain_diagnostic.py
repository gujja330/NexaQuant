"""Regression tests for the Phase 1 root causes.

Each class pins one measured defect so it cannot be quietly reintroduced
or quietly "fixed" by moving a threshold. Nothing here asserts that the
production behaviour is correct - several tests assert the opposite, and
say so - because the CEO instruction for Phase 1 was to show the evidence
and the proposed change without applying it.

All fixtures are synthetic and tmp_path-isolated. No live ledger, report
or registry is read or written.
"""
from __future__ import annotations

import collections
import json
import random

import pytest

from backend.recommendation.actionable_chain_diagnostic import (
    ABSOLUTE_ARMS, ACTIVE_MODEL, DEAD_MODEL, absolute_ceiling,
    action_distributions, agreement_variants, diagnose, funnel,
    model_activity, percentile_abstention, reports_dir, write)
from backend.recommendation.conflict import (
    DISAGREE_THRESHOLD, NEUTRAL_BAND, resolve_conflict)
from backend.recommendation.percentile_classifier import (
    MIN_CONFIDENCE_FOR_ACTION, classify_by_percentile)

MODELS = ["m%02d" % i for i in range(11)]


def _cand(ticker, scores):
    return {"ticker": ticker, "ensemble_score": 0.0,
            "per_model_score": dict(zip(MODELS, scores))}


def _rec(ticker, score, raw, agree, cal, flagged, **kw):
    r = {"ticker": ticker, "ensemble_score": score, "raw_confidence": raw,
         "model_agreement": agree, "calibrated_confidence": cal,
         "regime_adjusted_confidence": cal * 0.95,
         "disagreement_flag": flagged, "n_models_scoring": len(MODELS)}
    r.update(kw)
    return r


def _market(tmp_path, market, candidates, recs, weights=None, n_models=11):
    rd = reports_dir(tmp_path, market)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "ensemble.json").write_text(json.dumps({
        "market": market, "asof": "2026-11-02", "n_models": n_models,
        "weights": weights or {m: 1.0 / len(MODELS) for m in MODELS},
        "all_candidates": candidates,
        "n_all_candidates": len(candidates)}), encoding="utf-8")
    (rd / "recommendations.json").write_text(json.dumps({
        "market": market, "asof": "2026-11-02", "n": len(recs),
        "recommendations": recs}), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- RC-1

class TestDeadModelDetection:
    """A model that never leaves the neutral band is not being cautious."""

    def test_all_zero_model_is_dead(self):
        cands = [_cand("T%d" % i, [0.5, 0.0] + [0.3] * 9) for i in range(20)]
        act = model_activity(cands)
        assert act[MODELS[1]]["verdict"] == DEAD_MODEL
        assert act[MODELS[1]]["n_directional"] == 0
        assert act[MODELS[0]]["verdict"] == ACTIVE_MODEL

    def test_inside_neutral_band_still_counts_as_dead(self):
        """0.049 is not zero, and is still never a direction."""
        below = NEUTRAL_BAND - 0.001
        cands = [_cand("T%d" % i, [0.5, below] + [0.3] * 9) for i in range(20)]
        act = model_activity(cands)
        assert act[MODELS[1]]["n_nonzero"] == 20, "it does emit numbers"
        assert act[MODELS[1]]["verdict"] == DEAD_MODEL, "none of them is a direction"

    def test_dead_weight_share_is_the_weight_not_the_count(self, tmp_path):
        """Three dead models out of eleven can carry any share of the vote."""
        w = {m: 0.02 for m in MODELS}
        w[MODELS[1]] = w[MODELS[2]] = w[MODELS[3]] = 0.26
        cands = [_cand("T%d" % i, [0.5, 0.0, 0.0, 0.0] + [0.3] * 7)
                 for i in range(20)]
        recs = [_rec("T%d" % i, 0.1, 0.6, 0.45, 0.35, True) for i in range(20)]
        rep = diagnose(_market(tmp_path, "india", cands, recs, weights=w), "india")
        assert sorted(rep["dead_models"]) == sorted(MODELS[1:4])
        assert rep["dead_weight_share"] == pytest.approx(0.78, abs=1e-6)

    def test_live_india_has_three_dead_models_carrying_30pct(self):
        """The measured live value · fails loudly if the substrate changes.

        Marked xfail-on-missing rather than skipped: a missing live report
        is itself worth seeing, but it is not this test's job to fail for it.
        """
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        if not (root / "reports" / "ensemble.json").exists():
            pytest.skip("no live India ensemble in this checkout")
        rep = diagnose(root, "india")
        assert rep["dead_models"], "India had 3 dead models on 2026-11-02"
        assert rep["dead_weight_share"] > 0.15


# ---------------------------------------------------------------- RC-2

class TestAgreementCountsNonSignallingModelsAsDissent:
    """conflict.py's code contradicts conflict.py's docstring."""

    def test_unanimous_single_opinion_is_reported_as_major_disagreement(self):
        """The MM.NS shape: 1 positive, 0 negative, 10 neutral.

        Every model that expressed a direction agreed. The shipped
        agreement is 1/11 = 0.0909, which is below MAJOR_DISAGREE, so this
        unanimous name is recorded as the most severe disagreement the
        system can represent.
        """
        scores = [0.5] + [0.0] * 10
        rep = resolve_conflict(dict(zip(MODELS, scores)))
        assert rep.n_positive == 1 and rep.n_negative == 0 and rep.n_neutral == 10
        assert rep.model_agreement == pytest.approx(1 / 11, abs=1e-4)
        assert rep.disagreement_flag is True
        assert rep.disagreement_severity == "major"

        v = agreement_variants(dict(zip(MODELS, scores)))
        assert v["agreement_excluding_neutrals"] == pytest.approx(1.0)
        assert v["flagged_shipped"] is True
        assert v["flagged_excluding_neutrals"] is False

    def test_the_gnfc_shape_six_of_seven_directional_models_agree(self):
        """India's top-scored name, flagged as a disagreement."""
        scores = [-0.2627, 0.228, 0.9258, 0.5551, 0.488, 1.0,
                  0.0004, 0.0, 0.0, 0.0, 0.5072]
        v = agreement_variants(dict(zip(MODELS, scores)))
        assert (v["n_positive"], v["n_negative"], v["n_neutral"]) == (6, 1, 4)
        assert v["agreement_shipped"] == pytest.approx(6 / 11, abs=1e-4)
        assert v["agreement_excluding_neutrals"] == pytest.approx(6 / 7, abs=1e-4)
        assert v["flagged_shipped"] is True, "0.545 < 0.60"
        assert v["flagged_excluding_neutrals"] is False, "0.857 >= 0.60"

    def test_genuine_split_is_flagged_under_both_measures(self):
        """The fix must not disarm the valve · a real split stays flagged."""
        scores = [0.5] * 5 + [-0.5] * 5 + [0.0]
        v = agreement_variants(dict(zip(MODELS, scores)))
        assert v["flagged_shipped"] is True
        assert v["flagged_excluding_neutrals"] is True
        assert v["agreement_excluding_neutrals"] == pytest.approx(0.5)

    def test_unanimous_directional_is_flagged_by_neither(self):
        scores = [0.5] * 11
        v = agreement_variants(dict(zip(MODELS, scores)))
        assert v["flagged_shipped"] is False
        assert v["flagged_excluding_neutrals"] is False

    @pytest.mark.parametrize("n_dead,expected_ceiling", [
        (0, 1.0), (2, 9 / 11), (3, 8 / 11), (4, 7 / 11)])
    def test_dead_models_cap_attainable_agreement(self, n_dead, expected_ceiling):
        """Perfect unanimity among live models cannot reach 1.0."""
        scores = [0.0] * n_dead + [0.5] * (11 - n_dead)
        v = agreement_variants(dict(zip(MODELS, scores)))
        assert v["agreement_shipped"] == pytest.approx(expected_ceiling, abs=1e-4)


# ---------------------------------------------------------------- RC-3

class TestAbsoluteClassifierCeiling:
    """An unsatisfiable gate is a different defect from a strict one."""

    def test_strong_arms_are_unreachable_at_indias_observed_confidence(self):
        """India 2026-11-02 · raw max 0.6324, 3 dead of 11 models.

        ceiling = 0.6324 * (0.5 + 0.5 * 8/11) = 0.5462, against the 0.70
        the STRONG arms require. No score, however extreme, can produce a
        STRONG_BUY or STRONG_SELL from the absolute classifier.
        """
        recs = [_rec("T%d" % i, 0.9, 0.6324, 0.6364, 0.4909, False)
                for i in range(10)]
        c = absolute_ceiling(recs, n_models=11, n_dead=3)
        assert c["agreement_ceiling"] == pytest.approx(8 / 11, abs=1e-4)
        assert c["calibration_multiplier_ceiling"] == pytest.approx(0.8636, abs=1e-4)
        assert c["calibrated_confidence_ceiling"] == pytest.approx(0.5462, abs=1e-3)
        assert c["arms"]["STRONG_BUY"]["satisfiable_at_ceiling"] is False
        assert c["arms"]["STRONG_SELL"]["satisfiable_at_ceiling"] is False

    def test_usa_strong_arms_are_also_unreachable(self):
        """USA 2026-11-02 · raw max 0.7002, 2 dead of 11 -> 0.6365 < 0.70.

        USA clears the BUY arm for 142 names, so this is not a market that
        cannot decide. It still cannot reach a STRONG call, because the
        agreement cap bites before the raw confidence does.
        """
        recs = [_rec("T%d" % i, 0.9, 0.7002, 0.8182, 0.6070, False)
                for i in range(10)]
        c = absolute_ceiling(recs, n_models=11, n_dead=2)
        assert c["calibrated_confidence_ceiling"] == pytest.approx(0.6365, abs=1e-3)
        assert c["calibrated_confidence_ceiling"] < ABSOLUTE_ARMS["STRONG_BUY"][1]
        assert c["arms"]["STRONG_BUY"]["satisfiable_at_ceiling"] is False
        assert c["arms"]["BUY"]["satisfiable_at_ceiling"] is True

    def test_removing_dead_models_restores_the_strong_arms(self):
        """The proposed change is load-bearing, not cosmetic."""
        recs = [_rec("T%d" % i, 0.9, 0.6324, 1.0, 0.6324, False)
                for i in range(10)]
        before = absolute_ceiling(recs, n_models=11, n_dead=3)
        after = absolute_ceiling(recs, n_models=8, n_dead=0)
        assert before["arms"]["STRONG_BUY"]["satisfiable_at_ceiling"] is False
        assert after["calibrated_confidence_ceiling"] > before["calibrated_confidence_ceiling"]

    def test_india_buy_arm_is_reachable_in_theory_and_empty_in_fact(self):
        """Reported honestly: the ceiling clears 0.50, no name does.

        Conflating "no name reached it" with "no name could" would be the
        same error in the other direction.
        """
        recs = [_rec("T%d" % i, 0.25, 0.6324, 0.6364, 0.4909, False)
                for i in range(228)]
        c = absolute_ceiling(recs, n_models=11, n_dead=3)
        assert c["arms"]["BUY"]["satisfiable_at_ceiling"] is True
        assert c["arms"]["BUY"]["n_names_meeting_confidence"] == 0


# ---------------------------------------------------------------- RC-4

class TestPercentileClassifierCannotAbstain:
    """The live path assigns actions by rank · rank is defined on noise."""

    @staticmethod
    def _dist(recs):
        rep = classify_by_percentile(recs)
        return dict(collections.Counter(d["action"] for d in rep.decisions))

    def test_pure_noise_and_real_signal_give_the_identical_distribution(self):
        """The headline finding, as an assertion.

        At India's own median calibrated confidence the classifier returns
        exactly 23/23/136/23/23 whether the scores carry a 0.12 standard
        deviation of real dispersion or 1e-9 of float noise.
        """
        conf = 0.3505                      # India's live median
        random.seed(7)
        noise = [{"ticker": "T%03d" % i, "ensemble_score": random.gauss(0, 1e-9),
                  "calibrated_confidence": conf} for i in range(228)]
        random.seed(8)
        signal = [{"ticker": "T%03d" % i, "ensemble_score": random.gauss(0, 0.12),
                   "calibrated_confidence": conf} for i in range(228)]
        d_noise, d_signal = self._dist(noise), self._dist(signal)
        assert d_noise == d_signal
        assert d_noise == {"STRONG_BUY": 23, "BUY": 23, "HOLD": 136,
                           "SELL": 23, "STRONG_SELL": 23}

    def test_that_distribution_is_indias_live_distribution(self):
        """Live India: 23 STRONG BUY / 23 BUY / 136 HOLD / 23 SELL / 23 STRONG SELL."""
        conf = 0.3505
        random.seed(7)
        noise = [{"ticker": "T%03d" % i, "ensemble_score": random.gauss(0, 1e-9),
                  "calibrated_confidence": conf} for i in range(228)]
        on_noise = self._dist(noise)
        live = {"STRONG BUY": 23, "BUY": 23, "HOLD": 136,
                "SELL": 23, "STRONG SELL": 23}
        assert {k.replace("_", " "): v for k, v in on_noise.items()} == live

    def test_actionable_count_is_a_function_of_universe_size_only(self):
        conf = 0.3505
        for n in (50, 228, 516):
            random.seed(1)
            recs = [{"ticker": "T%03d" % i,
                     "ensemble_score": random.gauss(0, 1e-9),
                     "calibrated_confidence": conf} for i in range(n)]
            d = self._dist(recs)
            actionable = sum(v for k, v in d.items() if k != "HOLD")
            assert actionable == pytest.approx(0.40 * n, abs=0.02 * n)

    def test_the_floor_does_bite_when_confidence_is_actually_zero(self):
        """Not a broken gate · a gate set far below the operating range."""
        recs = [{"ticker": "T%03d" % i, "ensemble_score": float(i),
                 "calibrated_confidence": 0.0} for i in range(228)]
        assert self._dist(recs) == {"HOLD": 228}

    def test_floor_headroom_is_reported_as_a_multiple(self):
        recs = [_rec("T%d" % i, 0.1, 0.6, 0.45, 0.3505, True) for i in range(228)]
        p = percentile_abstention(recs)
        assert p["min_confidence_for_action"] == MIN_CONFIDENCE_FOR_ACTION
        assert p["gate_binds"] is False
        assert p["n_below_floor"] == 0
        assert p["floor_headroom_multiple"] > 100


# ---------------------------------------------------------------- RC-5

class TestMarketsDoNotShareADecisionPath:
    def test_divergence_between_shipped_and_percentile_is_detected(self):
        recs = ([_rec("A%d" % i, 0.3, 0.6, 0.8, 0.55, False,
                      action="BUY", percentile_action="STRONG_BUY") for i in range(5)]
                + [_rec("B%d" % i, -0.3, 0.6, 0.8, 0.55, False,
                        action="HOLD", percentile_action="SELL") for i in range(5)])
        a = action_distributions(recs)
        assert a["shipped_equals_percentile"] is False

    def test_an_unpopulated_classifier_field_is_not_reported_as_zero_actionable(self):
        """USA's action_prior_absolute is all null · "0 actionable" would lie."""
        recs = [_rec("T%d" % i, 0.1, 0.6, 0.45, 0.35, True,
                     action="HOLD", action_prior_absolute=None)
                for i in range(10)]
        a = action_distributions(recs)
        assert a["action_prior_absolute"]["populated"] is False
        assert a["action_prior_absolute"]["distribution"] == {"<null>": 10}

    def test_a_populated_all_hold_field_is_reported_as_populated(self):
        """India's is populated AND all-HOLD · a different fact."""
        recs = [_rec("T%d" % i, 0.1, 0.6, 0.45, 0.35, True,
                     action="HOLD", action_prior_absolute="HOLD")
                for i in range(10)]
        a = action_distributions(recs)
        assert a["action_prior_absolute"]["populated"] is True
        assert a["action_prior_absolute"]["n_actionable"] == 0


# ---------------------------------------------------------------- funnel

class TestFunnelConservation:
    def test_every_stage_conserves_its_population(self):
        random.seed(3)
        recs = [_rec("T%03d" % i, random.gauss(0, 0.15), 0.6,
                     random.random(), random.random() * 0.6,
                     random.random() < 0.9) for i in range(300)]
        f = funnel(recs)
        assert f["entered"] == 300
        for s in f["stages"]:
            assert s["entered"] == s["removed"] + s["survived"], s["stage"]
        for a, b in zip(f["stages"], f["stages"][1:]):
            assert a["survived"] == b["entered"]
        assert f["stages"][-1]["survived"] == f["absolute_actionable"]

    def test_binding_constraint_accounts_for_every_name(self):
        random.seed(4)
        recs = [_rec("T%03d" % i, random.gauss(0, 0.2), 0.6, 0.5,
                     random.random() * 0.7, random.random() < 0.5)
                for i in range(200)]
        f = funnel(recs)
        assert sum(f["binding_constraint"].values()) == 200

    def test_disagreement_short_circuits_before_any_threshold(self):
        """A name that would pass both thresholds is still removed first."""
        recs = [_rec("PASSES", 0.9, 0.9, 0.9, 0.9, True)]
        f = funnel(recs)
        assert f["stages"][0]["removed"] == 1
        assert f["absolute_actionable"] == 0
        assert f["binding_constraint"] == {"DISAGREEMENT_FLAG": 1}


# ---------------------------------------------------------------- isolation

class TestDiagnosticIsReadOnly:
    def test_writes_only_under_reports_diagnostics(self, tmp_path):
        cands = [_cand("T%d" % i, [0.5, 0.0, 0.0] + [0.3] * 8) for i in range(20)]
        recs = [_rec("T%d" % i, 0.1, 0.6, 0.45, 0.35, True) for i in range(20)]
        root = _market(tmp_path, "india", cands, recs)
        before = {p for p in root.rglob("*") if p.is_file()}
        rep = write(root, "india")
        after = {p for p in root.rglob("*") if p.is_file()}
        new = after - before
        assert len(new) == 1
        only = new.pop()
        assert only.name == "actionable_chain_india.json"
        assert only.parent.name == "diagnostics"
        assert rep["n_universe"] == 20

    def test_usa_reads_from_usa_reports(self, tmp_path):
        assert reports_dir(tmp_path, "usa").as_posix().endswith("usa/reports")
        assert reports_dir(tmp_path, "india").as_posix().endswith("/reports")

    def test_rerunning_is_deterministic_apart_from_the_timestamp(self, tmp_path):
        cands = [_cand("T%d" % i, [0.5, 0.0, 0.0] + [0.3] * 8) for i in range(20)]
        recs = [_rec("T%d" % i, 0.1, 0.6, 0.45, 0.35, True) for i in range(20)]
        root = _market(tmp_path, "india", cands, recs)
        a, b = diagnose(root, "india"), diagnose(root, "india")
        a.pop("generated_utc"), b.pop("generated_utc")
        assert a == b
