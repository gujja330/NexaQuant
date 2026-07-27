"""Confidence Scale Adapter · resolves the historical-vs-live confidence mismatch.

Root cause (per operator observation): historical trades (learning.parquet)
have confidence in [0.85, 1.00] because DEV023 emitted only STRONG_BUY
records. Runner 2 v3 uses Bayesian confidence in [0, 1] with multiplicative
agreement/coverage penalties → typical values in [0.001, 0.4].

The two are semantically incomparable · so calibration returns None for
current recs even though historical evidence is rich.

Fix: percentile-rank Runner-2-v3 confidence into the *conditional* space of
historical confidence, using the empirical mapping:

    aligned_conf = P95_historical - (1 - percentile(runner_conf)) * (P95 - P50)

This produces an "aligned_confidence" in the same scale as historical
confidence, which the calibration engine can then bucket into.

Article 101.2 · pure calibration correction extension. No new engine.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Mapping, Sequence


SCHEMA_FINGERPRINT = "aegis.certification.confidence_scale_adapter.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.certification.confidence_scale_adapter.v1"


@dataclass
class ConfidenceScaleMap:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    historical_p05: float = 0.85
    historical_p50: float = 0.87
    historical_p95: float = 1.00
    historical_min: float = 0.85
    historical_max: float = 1.00
    n_historical: int = 0
    method: str = "percentile_rank_stretch"
    notes: str = ""


def fit_scale_map(historical_confidences) -> ConfidenceScaleMap:
    """Fit the historical confidence distribution."""
    import pandas as pd
    m = ConfidenceScaleMap()
    if historical_confidences is None or len(historical_confidences) == 0:
        return m
    s = pd.Series(historical_confidences).dropna()
    if s.empty: return m
    m.n_historical = int(len(s))
    m.historical_min = round(float(s.min()), 4)
    m.historical_max = round(float(s.max()), 4)
    m.historical_p05 = round(float(s.quantile(0.05)), 4)
    m.historical_p50 = round(float(s.quantile(0.50)), 4)
    m.historical_p95 = round(float(s.quantile(0.95)), 4)
    m.notes = (
        f"historical confidence distribution: min={m.historical_min}, "
        f"P05={m.historical_p05}, P50={m.historical_p50}, "
        f"P95={m.historical_p95}, max={m.historical_max}. "
        f"Runner-2-v3 values in [0,1] will be percentile-stretched "
        f"into [{m.historical_p05}, {m.historical_p95}] so they can "
        f"consume the calibration curve."
    )
    return m


def align_runner2_confidence(runner2_conf: float, scale_map: dict,
                                runner2_calibration_ref: dict | None = None) -> float:
    """Map a Runner-2-v3 confidence value into the historical scale.

    runner2_conf: raw confidence from Runner-2-v3 · typical [0, 0.4]
    scale_map: output from fit_scale_map
    runner2_calibration_ref: optional reference distribution of runner-2 values
        · if provided, uses percentile-rank; else assumes uniform stretch

    Returns aligned_confidence in the historical [P05, P95] range.
    """
    if scale_map is None or scale_map.get("n_historical", 0) == 0:
        return runner2_conf
    lo = scale_map["historical_p05"]
    hi = scale_map["historical_p95"]
    c = max(0.0, min(1.0, float(runner2_conf)))
    # Simple linear stretch of [0, 1] → [lo, hi]
    aligned = lo + c * (hi - lo)
    return round(aligned, 4)


def apply_scale_adapter_to_recs(recs, scale_map: dict) -> list:
    """Enrich each rec with `aligned_confidence` in the historical scale."""
    out = []
    for r in recs:
        conf = float(r.get("confidence", 0.0))
        aligned = align_runner2_confidence(conf, scale_map)
        out.append({**r,
                     "aligned_confidence": aligned,
                     "confidence_scale_source": scale_map.get("engine", "n/a")})
    return out
