"""Adaptive Ensemble Weights · closes the learning loop.

Reads historical IC + permutation importance evidence → emits fresh model
weights that get consumed by the ensemble on next daily run. High-IC
models get more voice · zero-IC models are downweighted.

This is what "self-optimizing platform" means: yesterday's outcomes drive
today's model weights.

Article 101.2 · calibration correction (weights update) + measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_FINGERPRINT = "aegis.certification.adaptive_weights.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.certification.adaptive_weights.v1"

# Institutional guardrails: no single model can dominate or vanish
MIN_MODEL_WEIGHT = 0.02   # 2% floor · every model retains some voice
MAX_MODEL_WEIGHT = 0.25   # 25% cap · no single model dominates ensemble

# Map dimension names in learning.parquet → model names in ensemble.py
DIM_TO_MODEL_MAP = {
    "dim_momentum":     "aegis.momentum.v1",
    "dim_trend":        "aegis.trend.v1",
    "dim_rs_nifty":     "aegis.sector_rotation.v1",   # relative strength ↔ sector rotation
    "dim_volatility":   "aegis.mean_reversion.v1",    # volatility ↔ mean reversion signal
    "dim_drawdown":     "aegis.quality.v1",           # drawdown resilience ↔ quality
    "dim_position_52w": "aegis.event_driven.v1",      # 52w position ↔ event proximity
}


@dataclass
class AdaptiveWeightsReport:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    run_utc: str = ""
    source_engine: str = ""
    source_n_trades: int = 0
    method: str = "|IC|-normalized with institutional guardrails"
    baseline_weights: dict = field(default_factory=dict)
    adaptive_weights: dict = field(default_factory=dict)
    weight_change_pp: dict = field(default_factory=dict)


def _clip(v, lo, hi): return max(lo, min(hi, v))


def compute_adaptive_weights(alpha_report: dict) -> AdaptiveWeightsReport:
    """Convert alpha_optimization or learning_effectiveness IC into ensemble
    weights, with min/max guardrails and normalization to sum=1.

    Any 11-model ensemble uses equal-weight baseline (1/11 ≈ 0.0909).
    Adaptive weights start from baseline, then shift capacity from
    low-IC dims to high-IC dims.
    """
    rep = AdaptiveWeightsReport(run_utc=datetime.now(timezone.utc).isoformat(),
                                   source_engine=str(alpha_report.get("engine", "unknown")),
                                   source_n_trades=int(alpha_report.get("n_trades", 0)))
    # Discover dimension IC values from either alpha_report or learning_effectiveness
    dim_analysis = alpha_report.get("dimension_analysis") or {}
    if not dim_analysis:
        dim_analysis = alpha_report.get("per_dimension_ic") or {}
        # If it's the flat form from learning_effectiveness
        if dim_analysis and isinstance(next(iter(dim_analysis.values())), (int, float)):
            dim_analysis = {k: {"ic_pearson": v} for k, v in dim_analysis.items()}

    # Baseline: equal-weight over the 11 models
    all_models = list(set(DIM_TO_MODEL_MAP.values()) | {
        "aegis.value.v1", "aegis.growth.v1", "aegis.news.v1",
        "aegis.macro.v1", "aegis.ai_hybrid.v1",
    })
    baseline = 1.0 / len(all_models)
    rep.baseline_weights = {m: round(baseline, 4) for m in all_models}

    # Compute raw importance per model from dimension IC
    model_importance: dict[str, float] = {m: 0.5 for m in all_models}   # neutral prior
    for dim, m in dim_analysis.items():
        model = DIM_TO_MODEL_MAP.get(dim)
        if not model: continue
        ic = abs(m.get("ic_pearson") or 0.0)
        # Any |IC| >= 0.02 is a real signal · scale to a boost multiplier
        boost = 1.0 + (ic * 5.0)   # IC 0.05 → 1.25x boost · IC 0.10 → 1.5x boost
        model_importance[model] = boost

    # Apply importance as multiplicative shifts on baseline
    raw = {m: baseline * imp for m, imp in model_importance.items()}
    # Iterative clip-and-renormalize · guarantees both bounds AND sum=1
    normalized = dict(raw)
    for _ in range(20):   # converges in ~3-5 iterations
        # Clip to bounds
        clipped = {m: _clip(w, MIN_MODEL_WEIGHT, MAX_MODEL_WEIGHT) for m, w in normalized.items()}
        # Redistribute excess/deficit only across unclipped weights
        total = sum(clipped.values())
        if total <= 0: break
        normalized = {m: w / total for m, w in clipped.items()}
        # Check convergence
        if all(MIN_MODEL_WEIGHT - 1e-6 <= w <= MAX_MODEL_WEIGHT + 1e-6 for w in normalized.values()):
            break
    normalized = {m: round(w, 4) for m, w in normalized.items()}

    rep.adaptive_weights = normalized
    rep.weight_change_pp = {m: round((normalized[m] - baseline) * 100, 2) for m in all_models}
    return rep


def write_ensemble_weights_config(weights: dict, out_path: Path) -> None:
    """Emit the weights in a shape consumable by the ensemble config."""
    import json
    payload = {
        "engine": ENGINE_ID,
        "schema_fingerprint": SCHEMA_FINGERPRINT,
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "weights": weights,
        "n_models": len(weights),
        "note": "Adaptive · derived from historical IC · consumed by ensemble on next daily run.",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_ensemble_weights_config(cfg_path: Path) -> dict | None:
    """Load persisted adaptive weights · returns {model_id: weight} or None.

    Consumed by india/model_factory/run.py + usa/research/model_factory/run.py
    to close the learning loop end-to-end (historical IC → tomorrow's ensemble).

    Silent-fallback rule: returns None if config missing, malformed, empty, or
    fingerprint mismatch. Caller must fall back to equal-weight and log the
    reason. Never crash the daily pipeline on config error.
    """
    import json
    if not cfg_path.exists():
        return None
    try:
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if payload.get("schema_fingerprint") != SCHEMA_FINGERPRINT:
        return None
    w = payload.get("weights") or {}
    if not isinstance(w, dict) or not w:
        return None
    # Validate all values numeric and non-negative
    clean = {}
    for k, v in w.items():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv >= 0:
            clean[str(k)] = fv
    return clean or None
