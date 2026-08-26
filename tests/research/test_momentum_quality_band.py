"""AEGIS · momentum quality-band join regression (§14 · §5).

Before fix: _quality_band() only read investability_{market}.json which
scores ~42 India / ~30 USA tickers (R1/R2 narrow universe). Momentum
scans the full ~230 India / ~908 USA parquet universe. Result: 100%
of momentum candidates were UNKNOWN quality → timing engine downgraded
every one to CHASE_RISK/NO_ACTION → 0 momentum rows rendered.

Fix: prefer investability_shadow_{market}.json (full-universe scoring)
with fallback to the narrow file. Verified locally · India 1/7 → 1 WATCH,
7/7 → real quality bands (QUALITY, OK, AVOID).

This test locks the fix behavior · quality_band must return real bands
for tickers scored in shadow file, even when narrow file lacks coverage.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.research.short_term_momentum import _quality_band


@pytest.fixture
def temp_reports(tmp_path):
    p = tmp_path / "reports"
    p.mkdir()
    return tmp_path


def _write_shadow(root: Path, market: str, tickers_verdicts):
    p = root / "reports" / f"investability_shadow_{market}.json"
    p.write_text(json.dumps({
        "engine":  "aegis.investability.shadow.v1",
        "market":  market,
        "results": [{"ticker": t, "market": market, "verdict": v}
                    for t, v in tickers_verdicts],
    }), encoding="utf-8")


def _write_narrow(root: Path, market: str, tickers_verdicts):
    p = root / "reports" / f"investability_{market}.json"
    p.write_text(json.dumps({
        "engine":  "aegis.investability.v1",
        "market":  market,
        "results": [{"ticker": t, "market": market, "verdict": v}
                    for t, v in tickers_verdicts],
    }), encoding="utf-8")


class TestQualityBandJoin:

    def test_uses_shadow_when_present(self, temp_reports):
        _write_shadow(temp_reports, "india",
                      [("APOLLOTYRE", "✓ OK"), ("SAIL", "⚠ MARGINAL")])
        assert _quality_band(temp_reports, "APOLLOTYRE", "india") == "OK"
        assert _quality_band(temp_reports, "SAIL", "india") == "MARGINAL"

    def test_falls_back_to_narrow(self, temp_reports):
        _write_narrow(temp_reports, "india", [("TCS", "🏆 QUALITY")])
        # No shadow file · falls through
        assert _quality_band(temp_reports, "TCS", "india") == "QUALITY"

    def test_shadow_wins_over_narrow(self, temp_reports):
        # Shadow has broader coverage · should be preferred
        _write_shadow(temp_reports, "india", [("MCX", "🏆 QUALITY")])
        _write_narrow(temp_reports, "india", [("MCX", "✗ AVOID")])   # stale
        # Shadow's QUALITY should win
        assert _quality_band(temp_reports, "MCX", "india") == "QUALITY"

    def test_returns_unknown_when_neither_covers(self, temp_reports):
        _write_shadow(temp_reports, "india", [("ONLY_ONE", "✓ OK")])
        # OTHER_TICKER not in shadow · not in narrow → UNKNOWN
        assert _quality_band(temp_reports, "OTHER_TICKER", "india") == "UNKNOWN"

    def test_verdict_parsing_all_bands(self, temp_reports):
        _write_shadow(temp_reports, "india", [
            ("Q1", "🏆 QUALITY"),
            ("Q2", "✓ OK"),
            ("Q3", "⚠ MARGINAL"),
            ("Q4", "✗ AVOID"),
        ])
        assert _quality_band(temp_reports, "Q1", "india") == "QUALITY"
        assert _quality_band(temp_reports, "Q2", "india") == "OK"
        assert _quality_band(temp_reports, "Q3", "india") == "MARGINAL"
        assert _quality_band(temp_reports, "Q4", "india") == "AVOID"

    def test_case_insensitive_ticker(self, temp_reports):
        _write_shadow(temp_reports, "india", [("TCS", "🏆 QUALITY")])
        assert _quality_band(temp_reports, "tcs", "india") == "QUALITY"
        assert _quality_band(temp_reports, "TCS", "india") == "QUALITY"
