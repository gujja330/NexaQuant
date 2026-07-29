"""SSoT bridge · publish Runner 2 v3 output as legacy `recommendations.json`.

Translates the Sprint 3 v3 rec schema to the DEV023 Runner 1 legacy schema
that 8+ downstream consumers require. Bridge is idempotent, deterministic,
and schema-fingerprinted.

Consumers unblocked by this bridge:
  - research/fusion               (validation_v2 + adaptive_rec_v2 fusion)
  - research/knowledge_graph      (entity network + stress scenarios)
  - research/institutional_memory (recommendation lifecycle + missed opps)
  - research/decision_attribution (per-rec attribution)
  - research/recommendation_dna/run_winner_genome.py
  - research/price_context
  - research/morning_report
  - scripts/telegram_send_ux030.py
  - scripts/aegis_ops_check.py
  - india/aegis_dashboard.py
  - india/backend_validation/datasets.yaml
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_FINGERPRINT = "aegis.recommendation_ssot.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.recommendation.ssot.v1"

# Action canonicalization — accept every synonym, normalize to legacy vocab
ACTION_MAP = {
    "STRONG_BUY":         "STRONG BUY",
    "STRONGBUY":          "STRONG BUY",
    "STRONG-BUY":         "STRONG BUY",
    "BUY":                "BUY",
    "ACCUMULATE":         "BUY",
    "ADD":                "ADD",
    "HOLD":               "HOLD",
    "WATCH":              "HOLD",
    "TRIM":               "TRIM",
    "REDUCE":             "TRIM",
    "SELL":               "SELL",
    "STRONG_SELL":        "STRONG SELL",
    "STRONGSELL":         "STRONG SELL",
    "STRONG-SELL":        "STRONG SELL",
    "EXIT":               "EXIT",
    "NEW_POSITION":       "BUY",
    "INSUFFICIENT_DATA":  "INSUFFICIENT DATA",
}


def _canonical_action(raw) -> str:
    if raw is None: return "HOLD"
    return ACTION_MAP.get(str(raw).upper().strip(), "HOLD")


def _v3_to_legacy_score(ensemble_score) -> float:
    """Runner 2 v3 uses [-1,+1] · Runner 1 legacy uses [0,100].
    Map linearly: -1 → 0 · 0 → 50 · +1 → 100."""
    try:
        s = float(ensemble_score)
    except (TypeError, ValueError):
        return 50.0
    s = max(-1.0, min(1.0, s))
    return round((s + 1.0) * 50.0, 4)


def translate_v3_to_legacy(v3_rec: dict, rank: int) -> dict:
    """Translate one Runner-2-v3 rec into legacy schema.

    Legacy schema (from DEV023 · read by fusion + KG + institutional_memory + …):
        ticker · sector · industry · recommendation · composite_decision_score
        · confidence · plus preserved v3 fields
    """
    ticker = v3_rec.get("ticker", "")
    action = _canonical_action(v3_rec.get("action"))
    score_v3 = v3_rec.get("ensemble_score", v3_rec.get("score", 0.0))
    conf = float(v3_rec.get("calibrated_confidence",
                              v3_rec.get("regime_adjusted_confidence",
                                          v3_rec.get("raw_confidence", 0.5))))
    sector = v3_rec.get("sector", "")
    industry = v3_rec.get("industry", sector)  # fallback: sector as industry
    return {
        # Legacy schema (contract-preserving)
        "ticker":                    ticker,
        "sector":                    sector,
        "industry":                  industry,
        "recommendation":            action,
        "action":                    action,  # v3 alias
        "composite_decision_score":  _v3_to_legacy_score(score_v3),
        "confidence":                round(conf, 4),
        "rank":                      rank,
        # Preserved v3 richness
        "ensemble_score":            v3_rec.get("ensemble_score"),
        "raw_confidence":            v3_rec.get("raw_confidence"),
        "calibrated_confidence":     v3_rec.get("calibrated_confidence"),
        "regime_adjusted_confidence":v3_rec.get("regime_adjusted_confidence"),
        "model_agreement":           v3_rec.get("model_agreement"),
        "disagreement_flag":         v3_rec.get("disagreement_flag"),
        "n_models_scoring":          v3_rec.get("n_models_scoring"),
        "top_models":                v3_rec.get("top_models"),
        "top_features":              v3_rec.get("top_features"),
        "bull_case":                 v3_rec.get("bull_case"),
        "bear_case":                 v3_rec.get("bear_case"),
        "key_risks":                 v3_rec.get("key_risks"),
        "suggested_holding_period_days": v3_rec.get("suggested_holding_period_days"),
        "entry_zone":                v3_rec.get("entry_zone"),
        "exit_conditions":           v3_rec.get("exit_conditions"),
        "model_stamp":               v3_rec.get("model_stamp"),
        "provenance":                "aegis.recommendation.ssot.v1 (bridged from Runner 2 v3)",
        # Institutional Completion Program · explainability enrichment
        "explainability": {
            "top_features_count":    len(v3_rec.get("top_features") or []),
            "n_models_scoring":      v3_rec.get("n_models_scoring", 0),
            "model_agreement":       v3_rec.get("model_agreement", 0.0),
            "disagreement":          bool(v3_rec.get("disagreement_flag", False)),
            "confidence_reason":     _confidence_reason(v3_rec),
            "action_reason":         _action_reason(action, v3_rec),
        },
        # Institutional Completion Program · signal quality flag
        "signal_quality": _classify_signal_quality(v3_rec),
    }


def _classify_signal_quality(v3_rec: dict) -> str:
    """Categorize the substrate quality behind this rec."""
    s = abs(float(v3_rec.get("ensemble_score", 0.0)))
    c = float(v3_rec.get("calibrated_confidence", 0.0))
    if s < 0.001 and c < 0.01:
        return "INSUFFICIENT"   # substrate depleted
    if s < 0.05 or c < 0.10:
        return "WEAK"           # signal present but faint
    if s < 0.20 or c < 0.40:
        return "MODERATE"
    return "STRONG"


def _confidence_reason(v3_rec: dict) -> str:
    c = float(v3_rec.get("calibrated_confidence", 0.0))
    raw = float(v3_rec.get("raw_confidence", 0.0))
    agree = float(v3_rec.get("model_agreement", 0.0))
    if c < 0.01:
        return f"insufficient confidence · raw {raw:.4f} · agreement {agree:.2f} — substrate depleted"
    if v3_rec.get("disagreement_flag"):
        return f"models disagree · calibrated confidence {c:.3f} dampened"
    if c < 0.20:
        return f"low confidence · raw {raw:.3f} → calibrated {c:.3f}"
    return f"confidence {c:.3f} · agreement {agree:.2f}"


def _action_reason(action: str, v3_rec: dict) -> str:
    s = float(v3_rec.get("ensemble_score", 0.0))
    if action == "INSUFFICIENT DATA":
        return "action deferred · ensemble produced ~0 signal with ~0 confidence · not a HOLD decision"
    if action == "HOLD":
        return (f"HOLD · score {s:+.3f} inside neutral band"
                + (" · plus disagreement" if v3_rec.get("disagreement_flag") else ""))
    return f"{action} · ensemble score {s:+.3f}"


def _apply_opportunity_cost(recs: list[dict]) -> None:
    """Every HOLD gets oc_next_best_ticker · oc_expected_alpha_delta ·
    oc_reason_not_to_rotate fields (Wave 5 Opp Cost engine consumer wire-in).
    In-place mutation."""
    try:
        from backend.recommendation.opportunity_cost.engine import enrich_holds
    except Exception:
        return
    holds = [{"ticker": r["ticker"], "current_score": r.get("composite_decision_score", 50.0),
              "sector": r.get("sector", "")} for r in recs if r.get("recommendation") == "HOLD"]
    candidates = [{"ticker": r["ticker"], "score": r.get("composite_decision_score", 50.0),
                   "sector": r.get("sector", "")} for r in recs]
    if not holds:
        return
    enrichments = enrich_holds(holds, candidates)
    by_ticker = {e["hold_ticker"]: e for e in enrichments}
    for r in recs:
        e = by_ticker.get(r["ticker"])
        if e:
            r["oc_next_best_ticker"]     = e["oc_next_best_ticker"]
            r["oc_next_best_score"]      = e["oc_next_best_score"]
            r["oc_expected_alpha_delta"] = e["oc_expected_alpha_delta"]
            r["oc_reason_not_to_rotate"] = e["oc_reason_not_to_rotate"]


def publish_ssot(v3_path: Path,
                  out_path: Path,
                  market: str = "india",
                  asof: date | str | None = None,
                  run_utc: str | None = None,
                  apply_opportunity_cost: bool = True) -> dict:
    """Read v3 · translate every rec · write legacy-schema output.

    Institutional Completion Program: also applies Opportunity Cost
    enrichment to every HOLD (each answers "why not rotate?").

    Returns the emitted payload dict."""
    if not v3_path.exists():
        raise FileNotFoundError(f"v3 source missing: {v3_path}")
    v3 = json.loads(v3_path.read_text(encoding="utf-8"))
    v3_recs = v3.get("recommendations", []) if isinstance(v3, dict) else \
              (v3 if isinstance(v3, list) else [])
    # Rank by ensemble_score descending (deterministic)
    v3_sorted = sorted(v3_recs,
                        key=lambda r: -float(r.get("ensemble_score",
                                                     r.get("score", 0.0))))
    legacy_recs = [translate_v3_to_legacy(r, rank=i + 1)
                   for i, r in enumerate(v3_sorted)]

    # Institutional Completion Program · consume Opportunity Cost engine
    if apply_opportunity_cost:
        _apply_opportunity_cost(legacy_recs)

    # Aggregate signal quality tallies for the payload header
    quality_counts = {"STRONG": 0, "MODERATE": 0, "WEAK": 0, "INSUFFICIENT": 0}
    action_counts: dict[str, int] = {}
    for r in legacy_recs:
        quality_counts[r.get("signal_quality", "WEAK")] = quality_counts.get(r.get("signal_quality", "WEAK"), 0) + 1
        action_counts[r.get("recommendation")] = action_counts.get(r.get("recommendation"), 0) + 1

    payload = {
        "engine":              ENGINE_ID,
        "version":             "1.0.0",
        "schema_version":      SCHEMA_VERSION,
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "market":              market,
        "asof":                asof.isoformat() if isinstance(asof, date) else (asof or date.today().isoformat()),
        "run_utc":             run_utc or datetime.now(timezone.utc).isoformat(),
        "source":              str(v3_path.name),
        "n":                   len(legacy_recs),
        # Schema-compat alias · ops_check (scripts/aegis_ops_check.py +
        # usa/scripts/usa_ops_check.py) and both markets' backend_validation
        # datasets.yaml require this exact key.
        "n_companies_evaluated": len(legacy_recs),
        "n_currently_held":      0,
        "n_source":            len(v3_recs),
    }
    # Schema-compat: legacy scripts/aegis_ops_check.py expects every rec to
    # carry an `entry_exit` field. Compose it from the enriched fields our
    # cycle 3-4 investor_action + position_plan blocks emit.
    for r in legacy_recs:
        ez = None
        pp = r.get("position_plan") if isinstance(r, dict) else None
        if pp and isinstance(pp, dict):
            ez = pp.get("entry_zone")
        ia = r.get("investor_action") if isinstance(r, dict) else None
        r["entry_exit"] = {
            "entry_zone":    ez or r.get("entry_zone") or {},
            "if_holding":    (ia or {}).get("if_holding"),
            "entry":         (ia or {}).get("entry"),
            "exit_reason":   (r.get("exit_conditions") or [None])[0] if r.get("exit_conditions") else None,
        }
    payload = {
        **payload,
        "signal_quality_dist": quality_counts,
        "action_distribution": action_counts,
        "recommendations":     legacy_recs,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload
