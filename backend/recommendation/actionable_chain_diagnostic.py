"""Why a universe of scored names produces the actions it produces.

CEO 2026-11-03 · PHASE 1 · and a correction to my own earlier claim
-------------------------------------------------------------------
I previously reported "India produces ZERO actionable recommendations
(228/228 HOLD)". That is wrong. I was reading `action_prior_absolute`,
which is the pre-percentile field, and treating it as the shipped
decision. India ships 92 actionable calls (23 STRONG BUY / 23 BUY /
23 SELL / 23 STRONG SELL) and its registry admits 5-7 new positions on
a normal trading day.

What is actually broken is worse than a HOLD count, which is why this
module exists rather than a threshold edit.

THE CHAIN, AND WHERE IT BREAKS
------------------------------
    per-model scores -> ensemble -> conflict -> calibration
                                 -> regime -> classifier -> action

Two classifiers sit at the end. The ABSOLUTE one is evidence-gated
(`score >= 0.20 AND calibrated_confidence >= 0.50`). The PERCENTILE one
is rank-based (top/bottom 20% act). Measured on live India data:

  - the absolute classifier cannot fire at all. Not "rarely": its
    confidence conjunct is unsatisfiable for every name in the universe.
  - the percentile classifier cannot abstain. Its confidence floor sits
    350x below the market's own median confidence, so it emits the same
    40.35% actionable split on pure noise as on real signal.

So the only gate that consults evidence is dead, and the gate that is
live does not consult evidence. That is the finding. Raising or lowering
a number does not address it, and this module deliberately changes no
production behaviour - it measures, attributes, and names the stage.

ATTRIBUTION, NOT NARRATIVE
--------------------------
Every stage reports the count it removed and the count that survived,
so the reader can follow 228 names down to a decision without taking
any of it on trust. `binding_constraint` names the conjunct that failed
for each name, and `ceiling` reports what the stage could return under
the most favourable input it will ever see - which is how an
unsatisfiable gate is distinguished from a strict one.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

from backend.recommendation.classifier import (
    _MIN_SIGNAL_CONFIDENCE, _MIN_SIGNAL_SCORE)
from backend.recommendation.conflict import (
    DISAGREE_THRESHOLD, NEUTRAL_BAND)
from backend.recommendation.percentile_classifier import (
    MIN_CONFIDENCE_FOR_ACTION)

SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.actionable_chain_diagnostic.v1"

#: The absolute classifier's BUY/SELL arms, lifted from classifier.py so a
#: threshold change there shows up here as a changed ceiling rather than a
#: silently stale copy. (score_abs, confidence) per arm.
ABSOLUTE_ARMS = {
    "STRONG_BUY":  (0.50, 0.70),
    "BUY":         (0.20, 0.50),
    "SELL":        (0.20, 0.50),
    "STRONG_SELL": (0.50, 0.70),
}

#: A model that never leaves the neutral band on any name in the universe
#: is not expressing a cautious opinion, it is not running. The two are
#: indistinguishable downstream, which is the whole problem.
DEAD_MODEL = "DEAD"
SPARSE_MODEL = "SPARSE"
ACTIVE_MODEL = "ACTIVE"

#: Below this share of the universe a model is directionally sparse.
SPARSE_SHARE = 0.10


def reports_dir(root: Path, market: str) -> Path:
    """India writes to reports/, USA to usa/reports/ · repo convention."""
    return Path(root) / ("usa/reports" if str(market).lower() == "usa"
                         else "reports")


def _f(v, default=None) -> Optional[float]:
    """float(v) for real numbers only · JSON null and NaN are missing."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
        return float(v)
    return default


def model_activity(candidates: Sequence[Mapping]) -> dict:
    """Per-model directional activity across the whole universe.

    `weight_share` is filled by the caller because the weights live in the
    ensemble payload, not in the candidate rows.
    """
    names = set()
    for c in candidates:
        names.update((c.get("per_model_score") or {}).keys())
    n = len(candidates)
    out = {}
    for m in sorted(names):
        vals = [_f((c.get("per_model_score") or {}).get(m), 0.0) or 0.0
                for c in candidates]
        directional = sum(1 for v in vals if abs(v) > NEUTRAL_BAND)
        nonzero = sum(1 for v in vals if abs(v) > 1e-9)
        if directional == 0:
            verdict = DEAD_MODEL
        elif n and directional < n * SPARSE_SHARE:
            verdict = SPARSE_MODEL
        else:
            verdict = ACTIVE_MODEL
        out[m] = {
            "n_scored": n,
            "n_nonzero": nonzero,
            "n_directional": directional,
            "max_abs_score": max((abs(v) for v in vals), default=0.0),
            "verdict": verdict,
        }
    return out


def agreement_variants(per_model: Mapping) -> dict:
    """The shipped agreement, and the one the docstring describes.

    conflict.py says "Agreement = max fraction on any one side (excluding
    neutrals from the base)" and then divides by the full model count. The
    difference is not cosmetic when a third of the models never express a
    direction: it is the difference between "6 of 7 directional models
    agree" and "6 of 11 models agree", i.e. 0.857 vs 0.545 against a 0.60
    disagreement threshold.

    Reported side by side. Neither is applied to anything here.
    """
    vals = [_f(v) for v in (per_model or {}).values()]
    vals = [v for v in vals if v is not None]
    n = len(vals)
    n_pos = sum(1 for v in vals if v > NEUTRAL_BAND)
    n_neg = sum(1 for v in vals if v < -NEUTRAL_BAND)
    n_neu = n - n_pos - n_neg
    directional = max(n_pos, n_neg)
    shipped = (directional / n) if n else 0.0
    expressed = (directional / (n_pos + n_neg)) if (n_pos + n_neg) else 0.0
    return {
        "n_models": n,
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n_neutral": n_neu,
        "agreement_shipped": round(shipped, 4),
        "agreement_excluding_neutrals": round(expressed, 4),
        "flagged_shipped": shipped < DISAGREE_THRESHOLD,
        "flagged_excluding_neutrals": expressed < DISAGREE_THRESHOLD,
    }


def absolute_ceiling(recs: Sequence[Mapping], n_models: int,
                     n_dead: int) -> dict:
    """What the absolute classifier could return on its best possible input.

    A gate that no attainable input satisfies is a different defect from a
    gate that is merely strict, and only the ceiling tells them apart. The
    calibration identity is
        calibrated = raw * (0.5 + 0.5*agreement) * max(0.5, coverage)
    so with `n_dead` models stuck in the neutral band the agreement term is
    capped at (n_models - n_dead)/n_models however strong the signal is.
    """
    live = max(0, n_models - n_dead)
    agr_cap = (live / n_models) if n_models else 0.0
    cal_mult_cap = 0.5 + 0.5 * agr_cap
    raws = [_f(r.get("raw_confidence")) for r in recs]
    raws = [v for v in raws if v is not None]
    raw_max = max(raws) if raws else 0.0
    cals = [_f(r.get("calibrated_confidence")) for r in recs]
    cals = [v for v in cals if v is not None]
    out = {
        "n_models": n_models,
        "n_dead_models": n_dead,
        "agreement_ceiling": round(agr_cap, 4),
        "calibration_multiplier_ceiling": round(cal_mult_cap, 4),
        "raw_confidence_max_observed": round(raw_max, 4),
        "calibrated_confidence_ceiling": round(raw_max * cal_mult_cap, 4),
        "calibrated_confidence_max_observed": round(max(cals), 4) if cals else None,
        "arms": {},
    }
    for arm, (_s_req, c_req) in ABSOLUTE_ARMS.items():
        out["arms"][arm] = {
            "confidence_required": c_req,
            "raw_confidence_required": (round(c_req / cal_mult_cap, 4)
                                        if cal_mult_cap else None),
            "satisfiable_at_ceiling": bool(raw_max * cal_mult_cap >= c_req),
            "n_names_meeting_confidence": sum(1 for v in cals if v >= c_req),
        }
    return out


def _binding(score: Optional[float], cal: Optional[float],
             flagged: bool) -> str:
    """Which conjunct actually stopped this name from being actionable."""
    s = abs(score) if score is not None else 0.0
    c = cal if cal is not None else 0.0
    if s < _MIN_SIGNAL_SCORE and c < _MIN_SIGNAL_CONFIDENCE:
        return "INSUFFICIENT_SIGNAL"
    if flagged:
        return "DISAGREEMENT_FLAG"
    s_ok = s >= ABSOLUTE_ARMS["BUY"][0]
    c_ok = c >= ABSOLUTE_ARMS["BUY"][1]
    if s_ok and c_ok:
        return "NONE"
    if s_ok and not c_ok:
        return "CONFIDENCE"
    if c_ok and not s_ok:
        return "SCORE"
    return "SCORE_AND_CONFIDENCE"


def funnel(recs: Sequence[Mapping]) -> dict:
    """228 names down to a decision, one removal reason at a time.

    The absolute classifier short-circuits on disagreement before it looks
    at any threshold, so the stages are reported in that same order. A
    reader who adds the removals must land on the survivors.
    """
    n = len(recs)
    stages, reasons = [], {}
    survivors = []
    removed_disagree = 0
    for r in recs:
        if r.get("disagreement_flag"):
            removed_disagree += 1
        else:
            survivors.append(r)
    stages.append({"stage": "disagreement_valve", "entered": n,
                   "removed": removed_disagree, "survived": len(survivors),
                   "rule": "conflict.disagreement_flag -> HOLD"})

    after_score, removed_score = [], 0
    for r in survivors:
        s = abs(_f(r.get("ensemble_score"), 0.0) or 0.0)
        if s >= ABSOLUTE_ARMS["BUY"][0]:
            after_score.append(r)
        else:
            removed_score += 1
    stages.append({"stage": "absolute_score", "entered": len(survivors),
                   "removed": removed_score, "survived": len(after_score),
                   "rule": "abs(ensemble_score) >= %.2f" % ABSOLUTE_ARMS["BUY"][0]})

    after_conf, removed_conf = [], 0
    for r in after_score:
        c = _f(r.get("calibrated_confidence"), 0.0) or 0.0
        if c >= ABSOLUTE_ARMS["BUY"][1]:
            after_conf.append(r)
        else:
            removed_conf += 1
    stages.append({"stage": "absolute_confidence", "entered": len(after_score),
                   "removed": removed_conf, "survived": len(after_conf),
                   "rule": "calibrated_confidence >= %.2f" % ABSOLUTE_ARMS["BUY"][1]})

    for r in recs:
        b = _binding(_f(r.get("ensemble_score")),
                     _f(r.get("calibrated_confidence")),
                     bool(r.get("disagreement_flag")))
        reasons[b] = reasons.get(b, 0) + 1
    return {"entered": n, "stages": stages,
            "absolute_actionable": len(after_conf),
            "binding_constraint": dict(sorted(reasons.items()))}


def percentile_abstention(recs: Sequence[Mapping]) -> dict:
    """Can the live classifier ever say "no opinion"?

    It abstains only below `MIN_CONFIDENCE_FOR_ACTION`. Compared against
    the confidence the market actually produces, that answers the question
    without needing a simulation - though the test suite runs one anyway.
    """
    cals = [_f(r.get("calibrated_confidence")) for r in recs]
    cals = [v for v in cals if v is not None]
    cals_sorted = sorted(cals)
    median = (cals_sorted[len(cals_sorted) // 2] if cals_sorted else 0.0)
    below = sum(1 for v in cals if v < MIN_CONFIDENCE_FOR_ACTION)
    return {
        "min_confidence_for_action": MIN_CONFIDENCE_FOR_ACTION,
        "median_calibrated_confidence": round(median, 4),
        "floor_headroom_multiple": (round(median / MIN_CONFIDENCE_FOR_ACTION, 1)
                                    if MIN_CONFIDENCE_FOR_ACTION else None),
        "n_below_floor": below,
        "gate_binds": below > 0,
        "note": ("The confidence floor removes %d of %d names. A floor that "
                 "removes none cannot distinguish signal from noise, because "
                 "rank is defined on any input." % (below, len(cals))),
    }


def distributions(recs: Sequence[Mapping]) -> dict:
    """Quantiles for every field the chain decides on."""
    fields = ("ensemble_score", "composite_decision_score", "raw_confidence",
              "calibrated_confidence", "regime_adjusted_confidence",
              "model_agreement", "score_percentile", "n_models_scoring")
    out = {}
    for f in fields:
        v = sorted(x for x in (_f(r.get(f)) for r in recs) if x is not None)
        if not v:
            out[f] = {"n": 0}
            continue
        n = len(v)
        q = lambda p: v[min(n - 1, int(p * n))]  # noqa: E731
        out[f] = {"n": n, "min": round(v[0], 4), "p10": round(q(.10), 4),
                  "p50": round(q(.50), 4), "p90": round(q(.90), 4),
                  "max": round(v[-1], 4)}
    return out


def action_distributions(recs: Sequence[Mapping]) -> dict:
    """Shipped action vs each candidate classifier, so divergence is visible.

    USA and India do not agree on which of these becomes `action`, and that
    only shows when all three are counted next to each other.
    """
    out = {}
    for f in ("action", "recommendation", "percentile_action",
              "action_prior_absolute"):
        c = {}
        for r in recs:
            k = r.get(f)
            k = "<null>" if k is None else str(k)
            c[k] = c.get(k, 0) + 1
        actionable = sum(v for k, v in c.items()
                         if k not in ("HOLD", "<null>", "INSUFFICIENT_DATA"))
        out[f] = {"distribution": dict(sorted(c.items())),
                  "n_actionable": actionable,
                  "populated": any(k != "<null>" for k in c)}
    shipped = out["action"]["distribution"]
    pct = out["percentile_action"]["distribution"]
    out["shipped_equals_percentile"] = (
        {k.replace(" ", "_"): v for k, v in shipped.items()} == pct)
    return out


def diagnose(root: Path, market: str) -> dict:
    """Read the market's live ensemble + recommendations and attribute."""
    rd = reports_dir(root, market)
    ens = json.loads((rd / "ensemble.json").read_text(encoding="utf-8"))
    rec = json.loads((rd / "recommendations.json").read_text(encoding="utf-8"))
    cands = ens.get("all_candidates") or []
    recs = rec.get("recommendations") or []
    weights = ens.get("weights") or {}

    activity = model_activity(cands)
    for m, info in activity.items():
        info["weight"] = round(_f(weights.get(m), 0.0) or 0.0, 6)
    dead = [m for m, i in activity.items() if i["verdict"] == DEAD_MODEL]
    n_models = int(ens.get("n_models") or len(activity) or 0)

    worst = None
    for c in cands:
        v = agreement_variants(c.get("per_model_score") or {})
        if v["flagged_shipped"] and not v["flagged_excluding_neutrals"]:
            if worst is None or v["n_neutral"] > worst[1]["n_neutral"]:
                worst = (c.get("ticker"), v)

    flips = 0
    for c in cands:
        v = agreement_variants(c.get("per_model_score") or {})
        if v["flagged_shipped"] and not v["flagged_excluding_neutrals"]:
            flips += 1

    return {
        "engine": ENGINE_ID,
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": str(market).lower(),
        "asof": rec.get("asof"),
        "ensemble_asof": ens.get("asof"),
        "n_universe": len(recs),
        "n_candidates": len(cands),
        "model_activity": activity,
        "dead_models": dead,
        "dead_weight_share": round(
            sum(_f(weights.get(m), 0.0) or 0.0 for m in dead), 4),
        "agreement_measurement": {
            "neutral_band": NEUTRAL_BAND,
            "disagree_threshold": DISAGREE_THRESHOLD,
            "n_flagged_only_because_neutrals_are_in_the_base": flips,
            "worst_example": (None if worst is None
                              else {"ticker": worst[0], **worst[1]}),
            "docstring_says": ("Agreement = max fraction on any one side "
                               "(excluding neutrals from the base)"),
            "code_does": "max(n_pos, n_neg) / n_total  (neutrals INCLUDED)",
        },
        "absolute_ceiling": absolute_ceiling(recs, n_models, len(dead)),
        "funnel": funnel(recs),
        "percentile_abstention": percentile_abstention(recs),
        "distributions": distributions(recs),
        "actions": action_distributions(recs),
    }


def out_path(root: Path, market: str) -> Path:
    return (Path(root) / "reports" / "diagnostics"
            / ("actionable_chain_%s.json" % str(market).lower()))


def write(root: Path, market: str) -> dict:
    rep = diagnose(Path(root), market)
    p = out_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    rep["_written_to"] = str(p)
    return rep
