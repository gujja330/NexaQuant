"""R3 Tier-2 · Earnings Transcript Tone · PDF R3 Tier-2.

**CRITICAL PER V2 §5:** prepared remarks and Q&A tone are SEPARATE signals.
Never collapse into one score.

Signals emitted:
  prepared_remarks_tone  · management-scripted portion sentiment
  qa_tone                · analyst Q&A live portion sentiment
  hedging_language_pct   · fraction of sentences using hedging markers
  uncertainty_pct        · uncertainty-marker fraction
  headwinds_mention_count · explicit "headwind" mentions
  qoq_tone_change        · Δ vs prior quarter (combined score)

USA + India both supported (transcript source availability varies).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.research.r3.tier2._ticket_helpers import (
    build_ticket, r3_shadow_ready, blocked_result,
)

RESEARCH_TICKET = build_ticket(
    ticket_id="R3-T2-TRANSCRIPT-TONE",
    tier=2,
    name="Earnings transcript tone (prepared vs Q&A SEPARATE)",
    description="Six-signal earnings-call NLP · prepared and Q&A never combined",
    gate_precondition="R3 shadow ≥20 picks + transcript ingest wired (SeekingAlpha / seeking-alpha / bamsec / MoneyControl)",
    pdf_reference="V2 §5 L5 item 21 · Q&A SEPARATE from prepared · R3 Tier-2",
    additive_extension_id="TRANSCRIPT_TONE_SIGNAL",
)

# Simple lexicon-based tone scorer (Loughran-McDonald-style stub · replace
# with real fine-tuned model when transcripts ingest lands)
_POS_WORDS = {"strong", "grew", "growth", "improved", "outperform", "beat",
              "record", "achieved", "expanded", "gained", "increased", "robust"}
_NEG_WORDS = {"decline", "declined", "weak", "missed", "shortfall", "loss",
              "impairment", "restructure", "delay", "pressure", "challenges",
              "headwind", "headwinds"}
_HEDGE_WORDS = {"may", "might", "could", "possibly", "potentially", "likely",
                "somewhat", "approximately", "around", "roughly"}
_UNCERTAIN_WORDS = {"uncertain", "unclear", "difficult", "volatile",
                    "unpredictable", "murky", "cautious"}


def _tokenize(text: str) -> list[str]:
    if not text: return []
    return [w.strip(".,;:!?()\"'").lower() for w in text.split() if w.strip()]


def _score_tone(tokens: list[str]) -> float:
    if not tokens: return 0.0
    p = sum(1 for t in tokens if t in _POS_WORDS)
    n = sum(1 for t in tokens if t in _NEG_WORDS)
    return (p - n) / max(1, len(tokens))


def _fraction(tokens: list[str], vocab: set[str]) -> float:
    if not tokens: return 0.0
    return sum(1 for t in tokens if t in vocab) / len(tokens)


def score_transcript(prepared_remarks_text: Optional[str],
                     qa_text: Optional[str],
                     prior_combined_tone: Optional[float] = None) -> dict:
    """Return dict with six signals · prepared and Q&A NEVER combined."""
    pt = _tokenize(prepared_remarks_text or "")
    qt = _tokenize(qa_text or "")
    prepared_tone = _score_tone(pt) if pt else None
    qa_tone_val = _score_tone(qt) if qt else None
    hedge = _fraction(qt, _HEDGE_WORDS) if qt else _fraction(pt, _HEDGE_WORDS)
    uncertain = _fraction(qt, _UNCERTAIN_WORDS) if qt else _fraction(pt, _UNCERTAIN_WORDS)
    headwinds = sum(1 for t in (pt + qt) if t in {"headwind", "headwinds"})
    combined = ((prepared_tone or 0.0) + (qa_tone_val or 0.0)) / 2.0 if (pt or qt) else None
    qoq = None
    if combined is not None and prior_combined_tone is not None:
        qoq = round(combined - float(prior_combined_tone), 4)
    return {
        "prepared_remarks_tone":   round(prepared_tone, 4) if prepared_tone is not None else None,
        "qa_tone":                 round(qa_tone_val, 4) if qa_tone_val is not None else None,
        "hedging_language_pct":    round(hedge, 4) if (pt or qt) else None,
        "uncertainty_pct":         round(uncertain, 4) if (pt or qt) else None,
        "headwinds_mention_count": int(headwinds),
        "qoq_tone_change":         qoq,
        "no_fabrication_note":     ("prepared and Q&A remain SEPARATE per V2 §5 · "
                                     "combined only shown for QoQ change trending"),
    }


def evaluate(root: Path, market: str) -> dict:
    ok, reason = r3_shadow_ready(root, min_picks=20)
    if not ok:
        return blocked_result(RESEARCH_TICKET, market, reason,
                              extra_artifacts=[
                                  f"reports/research/r3/tier2/transcript_tone_{market}.json",
                              ])
    return {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "market": market,
        "gate_status": "READY-TO-FIT",
        "next_step": "Wire transcript ingest · run score_transcript per (ticker, quarter) · treat prepared + Q&A as separate features",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
