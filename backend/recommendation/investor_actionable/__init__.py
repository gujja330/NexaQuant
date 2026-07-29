"""Investor-Actionable Recommendation Enricher.

Retail investors have TWO orthogonal decisions on any given day for a stock:
  1. Entry Decision       — I don't own it: should I buy?
  2. Existing Position    — I already own it: should I hold / add / trim / exit?

The classic institutional 5-level scale (STRONG_BUY..STRONG_SELL) collapses
both onto one axis and creates ambiguity — HOLD reads as "keep holding" if
you own it but is meaningless if you don't. SELL reads as "short" for a
fund manager but must read as "exit if you own it" for a retail advisory-
only platform (this one).

This module maps the existing 5-level percentile action into the two
orthogonal decisions and enriches every rec with a concrete position plan
(entry zone, stop, targets, horizon bucket, suggested allocation) plus a
top-reasons/top-risks summary derived from existing bull/bear cases.

Article 101.2 compliant · pure enrichment · no new analytics engine.
"""
from .engine import (
    enrich_recommendation, enrich_batch, summarize_batch,
    build_ceo_summary,
    SCHEMA_FINGERPRINT, ENGINE_ID,
    ENTRY_MAP, IF_HOLDING_MAP, HORIZON_BUCKETS, LABEL_MAP,
)

__all__ = [
    "enrich_recommendation", "enrich_batch", "summarize_batch",
    "build_ceo_summary",
    "SCHEMA_FINGERPRINT", "ENGINE_ID",
    "ENTRY_MAP", "IF_HOLDING_MAP", "HORIZON_BUCKETS", "LABEL_MAP",
]
