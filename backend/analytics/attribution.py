"""Per-model / per-dimension attribution for every recommendation.

Consumes the `per_model_score` dict already present on every rec in
`reports/ensemble.json` (each ensemble rec has the raw score contribution
of the 11 models). Also uses the adaptive weights YAML to compute
weight-adjusted contributions.

Answers the operator's Article-33 question:
    "For every recommendation, decompose the final score into
     Sector +X · Momentum +Y · Fundamental +Z · Quality +W ..."

Outputs per rec:
    attribution = {
      per_model: [{model_id, raw_score, weight, weighted_contribution, share_pct}],
      dominant_driver: model_id with largest positive contribution,
      opposition: model_id with largest negative contribution,
      sector_engine_contribution_pct: share attributable to sector model,
      total_positive: sum of positive weighted contributions,
      total_negative: sum of negative weighted contributions,
    }

Article 101.2 · pure attribution over existing scores. No new model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence, MutableMapping

SCHEMA_FINGERPRINT = "aegis.analytics.attribution.v1.20260729"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.analytics.attribution.v1"

# Human-facing labels for the 11 model_ids so the operator sees
# "Sector +12" not "aegis.sector_rotation.v1 +12".
MODEL_LABELS = {
    "aegis.momentum.v1":         "Momentum",
    "aegis.trend.v1":            "Trend",
    "aegis.value.v1":            "Value",
    "aegis.growth.v1":           "Growth",
    "aegis.quality.v1":          "Quality",
    "aegis.mean_reversion.v1":   "MeanReversion",
    "aegis.news.v1":             "News",
    "aegis.macro.v1":            "Macro",
    "aegis.sector_rotation.v1":  "Sector",
    "aegis.event_driven.v1":     "Event",
    "aegis.ai_hybrid.v1":        "AI-Hybrid",
}
SECTOR_MODEL_ID = "aegis.sector_rotation.v1"


def _label(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, model_id.split(".")[-2] if "." in model_id else model_id)


def _load_weights(root: Path) -> dict:
    """Load adaptive ensemble weights if available · else return uniform."""
    p = root / "configs" / "ensemble_weights_adaptive.yaml"
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        return payload.get("weights") or {}
    except Exception:
        return {}


def _load_ensemble_by_ticker(reports_root: Path) -> dict:
    """Return {ticker: {per_model_score, ensemble_score, ...}}."""
    p = reports_root / "ensemble.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for row in (d.get("top_10") or []) + (d.get("bottom_5") or []):
        t = str(row.get("ticker") or "")
        if t:
            out[t] = row
    return out


def compute_attribution_for_rec(rec: Mapping,
                                    ensemble_row: Mapping | None,
                                    weights: Mapping) -> dict:
    """Compute the attribution block for a single rec.

    ensemble_row is the matching entry from ensemble.json (has per_model_score).
    weights is the {model_id: weight} adaptive-weights dict (uniform-fallback).
    """
    if not ensemble_row:
        return {
            "per_model":                       [],
            "dominant_driver":                 None,
            "opposition":                      None,
            "sector_engine_contribution_pct":  None,
            "total_positive":                  0.0,
            "total_negative":                  0.0,
            "note":                            "ensemble.json row missing for ticker",
        }
    per_model_raw = ensemble_row.get("per_model_score") or {}
    if not per_model_raw:
        return {
            "per_model":                       [],
            "dominant_driver":                 None,
            "opposition":                      None,
            "sector_engine_contribution_pct":  None,
            "total_positive":                  0.0,
            "total_negative":                  0.0,
            "note":                            "per_model_score not present in ensemble row",
        }

    # Uniform weight fallback if adaptive weights not loaded
    n_models = max(1, len(per_model_raw))
    default_w = 1.0 / n_models

    entries = []
    total_pos = 0.0
    total_neg = 0.0
    for model_id, raw in per_model_raw.items():
        try:
            raw_f = float(raw)
        except (TypeError, ValueError):
            continue
        w = float(weights.get(model_id, default_w))
        contrib = round(raw_f * w, 6)
        if contrib > 0: total_pos += contrib
        elif contrib < 0: total_neg += contrib
        entries.append({
            "model_id":              model_id,
            "label":                 _label(model_id),
            "raw_score":             round(raw_f, 4),
            "weight":                round(w, 4),
            "weighted_contribution": contrib,
        })

    # Compute shares (percent of |total contribution|)
    denom = sum(abs(e["weighted_contribution"]) for e in entries) or 1e-9
    for e in entries:
        e["share_pct"] = round(abs(e["weighted_contribution"]) / denom * 100, 2)

    # Sort dominant→opposition
    entries.sort(key=lambda e: -e["weighted_contribution"])
    dominant = entries[0] if entries else None
    opposition = entries[-1] if entries and entries[-1]["weighted_contribution"] < 0 else None
    sector_entry = next((e for e in entries if e["model_id"] == SECTOR_MODEL_ID), None)
    sector_share = sector_entry["share_pct"] if sector_entry else None

    return {
        "per_model":                       entries,
        "dominant_driver":                 {"label": dominant["label"], "contribution": dominant["weighted_contribution"]} if dominant else None,
        "opposition":                      {"label": opposition["label"], "contribution": opposition["weighted_contribution"]} if opposition else None,
        "sector_engine_contribution_pct":  sector_share,
        "total_positive":                  round(total_pos, 4),
        "total_negative":                  round(total_neg, 4),
    }


def enrich_recs_with_attribution(recs: Sequence[MutableMapping],
                                     reports_root: Path,
                                     repo_root: Path) -> Sequence[MutableMapping]:
    """Add `attribution` block to each rec in-place · returns the same list."""
    weights = _load_weights(repo_root)
    ensemble_by_ticker = _load_ensemble_by_ticker(reports_root)
    for r in recs:
        t = str(r.get("ticker") or "")
        row = ensemble_by_ticker.get(t)
        r["attribution"] = compute_attribution_for_rec(r, row, weights)
    return recs


def summarize_attribution(recs: Sequence[Mapping]) -> dict:
    """Cross-rec rollup for the Command Center + operator dashboard.

    Which models are consistently driving decisions today? Which are
    persistently opposing?
    """
    from collections import Counter
    driver_counts: Counter = Counter()
    opposition_counts: Counter = Counter()
    sector_shares = []
    for r in recs:
        a = r.get("attribution") or {}
        d = (a.get("dominant_driver") or {}).get("label")
        o = (a.get("opposition") or {}).get("label")
        if d:
            driver_counts[d] += 1
        if o:
            opposition_counts[o] += 1
        s = a.get("sector_engine_contribution_pct")
        if s is not None:
            sector_shares.append(float(s))
    avg_sector_share = round(sum(sector_shares) / len(sector_shares), 2) if sector_shares else None
    return {
        "engine":                        ENGINE_ID,
        "schema_fingerprint":            SCHEMA_FINGERPRINT,
        "n_recs":                        len(recs),
        "dominant_drivers":              dict(driver_counts.most_common(5)),
        "persistent_opposition":         dict(opposition_counts.most_common(5)),
        "avg_sector_share_pct":          avg_sector_share,
        "sector_engine_measurably_active": (avg_sector_share is not None and avg_sector_share >= 5.0),
    }
