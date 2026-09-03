"""Fundamentals · Layer 5 extension · items 20-21 · Related-Party + Transcript.

Adds two PDF-required L5 signals that the base layer5_event.py did not
implement (they need external data sources not yet ingested).

Signals:
    related_party_txn_freq · #_related_party_txns_ttm  (India-focused)
    transcript_tone_prep   · sentiment of prepared-remarks (SEPARATE per V2 §5)
    transcript_tone_qa     · sentiment of Q&A portion (SEPARATE)
    transcript_hedging_pct
    transcript_qoq_tone_change

Data status: NOT-AVAILABLE (both markets · no ingest wired). Returns None
with source_tag "NOT_AVAILABLE" per V2 §36 gap policy.
"""
from __future__ import annotations

from typing import Optional

from backend.research.r3.tier2.transcript_tone import score_transcript


def related_party_txn_freq(fin: dict) -> Optional[float]:
    """#_related_party_txns in trailing 12 months / market_cap (normalized)."""
    for k in ("related_party_txn_count_ttm", "market_cap"):
        if k not in fin or fin[k] is None:
            return None
    try:
        mc = float(fin["market_cap"])
        if mc <= 0: return None
        return round(float(fin["related_party_txn_count_ttm"]) / mc * 1e12, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def transcript_tone_bundle(fin: dict) -> dict:
    """Return the 6 transcript signals · Q&A separate from prepared remarks.

    Requires fin["prepared_remarks_text"] and/or fin["qa_text"] · both are
    typically absent today (transcript ingest not wired).
    """
    prep = fin.get("prepared_remarks_text")
    qa = fin.get("qa_text")
    prior = fin.get("transcript_prior_combined_tone")
    if not prep and not qa:
        # No source → return all None with explicit gap flag
        return {
            "prepared_remarks_tone": None,
            "qa_tone": None,
            "hedging_language_pct": None,
            "uncertainty_pct": None,
            "headwinds_mention_count": None,
            "qoq_tone_change": None,
            "source_tag": "NOT_AVAILABLE:transcript_ingest_not_wired",
        }
    result = score_transcript(prep, qa, prior)
    result["source_tag"] = "lexicon_stub:v1"
    return result


LAYER5_EXTENDED_FUNCTIONS = {
    "related_party_txn_freq": related_party_txn_freq,
    # transcript_tone_bundle emits a dict · caller expands into individual columns
    "transcript_tone_bundle": transcript_tone_bundle,
}
