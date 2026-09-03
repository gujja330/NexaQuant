"""B1 regime enricher · PIT + no-fabrication invariants."""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research.enrichers.regime import (
    REGIME_VOCAB, MR_TO_PDF_MAP, _pit_lookup, _map,
)


def test_pdf_vocabulary_locked():
    assert REGIME_VOCAB == ["NORMAL", "WEAKENING", "RISK_OFF",
                            "CRASH", "RECOVERY", "UNKNOWN"]


def test_mr_to_pdf_map_stable():
    # Locked mapping · any change is an amendment, not a silent edit
    assert MR_TO_PDF_MAP == {
        "BULL":     "NORMAL",
        "NEUTRAL":  "NORMAL",
        "HIGH_VOL": "RISK_OFF",
        "BEAR":     "WEAKENING",
    }


def test_map_unknown_when_source_missing():
    label, tag = _map(None)
    assert label == "UNKNOWN"
    assert tag == "missing"


def test_map_unknown_when_source_label_unrecognized():
    label, tag = _map("SOMETHING_NEW")
    assert label == "UNKNOWN"
    assert tag.startswith("unmapped:")


def test_pit_lookup_returns_largest_le_entry_date():
    src = {"2026-01-01": "BULL", "2026-06-01": "BEAR", "2026-09-01": "HIGH_VOL"}
    raw, d = _pit_lookup(src, "2026-07-15")
    assert raw == "BEAR"
    assert d == "2026-06-01"


def test_pit_lookup_never_looks_forward():
    src = {"2026-09-01": "HIGH_VOL"}
    raw, d = _pit_lookup(src, "2026-07-15")
    assert raw is None
    assert d is None


def test_pit_lookup_before_source_start_returns_none():
    src = {"2026-06-01": "BULL"}
    raw, d = _pit_lookup(src, "2025-01-01")
    assert raw is None and d is None


def test_pit_exact_match():
    src = {"2026-01-01": "BULL", "2026-06-01": "BEAR"}
    raw, d = _pit_lookup(src, "2026-06-01")
    assert raw == "BEAR"
    assert d == "2026-06-01"
