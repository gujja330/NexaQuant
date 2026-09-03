"""AEGIS Fundamentals Feature Store

Substrate for every fundamentals-driven signal in R3 (and later R2 upgrades).
Five layers · 18 signals · one row per (market, ticker, asof).

Layer 1 · Quality  · Piotroski / Beneish / Altman / Sloan / InterestCov
Layer 2 · Value    · FCF Yield / EV-EBITDA / TSY / Sector-relative
Layer 3 · Change   · Analyst Rev / Guidance / Earnings Surprise / Insider F4
Layer 4 · Flow     · FII/DII z / Options PCR / Short interest
Layer 5 · Event    · Earnings-calendar window / Promoter pledge (India)

Import a per-layer derivation function to compute one signal at a time
without loading the whole layer.
"""
from backend.research.fundamentals.builder import (
    build_feature_store, load_feature_store, LAYER_MAP,
)

__all__ = ["build_feature_store", "load_feature_store", "LAYER_MAP"]
