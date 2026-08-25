# tests/context/test_price_integrity.py
"""AEGIS · executable spec for backend/context/price_integrity_guard.

Every rule is a repeat-source-of-financial-fiction pattern converted to
a test. Failing a test blocks Telegram delivery in CI.

Run local:  pytest tests/context/test_price_integrity.py -v
Run CI:     same · runs before every send via delivery_tests gate
"""
from __future__ import annotations

from pathlib import Path
from datetime import date, timedelta
import pandas as pd
import pytest

from backend.context.price_integrity_guard import (
    check_entry_alignment, check_exit_alignment, check_freshness,
    check_immutability, check_cross_source, check_corporate_actions,
    compute, emit, summary_line,
    validate_price_before_write, save_fingerprints,
    _fingerprint_tail, _load_baseline_fingerprints,
    TOLERANCE_PCT_DEFAULT,
)


# ─────────────────────────────────────────────────────────────────
# Test fixture · build a fake root with one ticker's parquet
# ─────────────────────────────────────────────────────────────────
@pytest.fixture
def synthetic_root(tmp_path: Path) -> Path:
    """Build data/raw/india/TESTA_D1.parquet with 30 known closes."""
    raw = tmp_path / "data" / "raw" / "india"
    raw.mkdir(parents=True)
    dates = pd.date_range("2026-08-01", periods=30, freq="B")
    closes = [100.0 + i for i in range(len(dates))]   # 100, 101, 102, ...
    df = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "tick_volume": [1000] * len(dates),
         "spread": [0.0] * len(dates)},
        index=dates,
    )
    df.index.name = "time"
    df.to_parquet(raw / "TESTA_D1.parquet")
    # A second ticker · TESTB · with slightly different prices
    df2 = df.copy()
    df2["close"] = [200.0 + i * 0.5 for i in range(len(dates))]
    df2.to_parquet(raw / "TESTB_D1.parquet")
    return tmp_path


# ═════════════════════════════════════════════════════════════════
# PI1 · Entry-price alignment
# ═════════════════════════════════════════════════════════════════
class TestPI1_EntryAlignment:

    def test_quoted_matches_parquet_close_exactly_passes(self, synthetic_root):
        # 2026-08-03 is index 0 (Aug 1 Sat, Aug 2 Sun, Aug 3 Mon)
        # Actually pd.date_range with freq="B" gives: Aug 3, 4, 5, 6, 7, ...
        pos = [{
            "ticker": "TESTA", "entry_date": "2026-08-03",
            "entry_price": 100.0, "status": "ACTIVE",
        }]
        rep = check_entry_alignment(synthetic_root, "india", pos)
        assert rep.status == "PASS"
        assert not rep.violations

    def test_quoted_within_tolerance_passes(self, synthetic_root):
        # 100.4 vs 100.0 = 0.4% < 0.5% tolerance
        pos = [{
            "ticker": "TESTA", "entry_date": "2026-08-03",
            "entry_price": 100.4, "status": "ACTIVE",
        }]
        rep = check_entry_alignment(synthetic_root, "india", pos)
        assert rep.status == "PASS"

    def test_quoted_beyond_tolerance_fails(self, synthetic_root):
        # 105 vs 100 = 5% > 0.5% tolerance
        pos = [{
            "ticker": "TESTA", "entry_date": "2026-08-03",
            "entry_price": 105.0, "status": "ACTIVE",
        }]
        rep = check_entry_alignment(synthetic_root, "india", pos)
        assert rep.status == "FAIL"
        assert len(rep.violations) == 1
        v = rep.violations[0]
        assert v["ticker"] == "TESTA"
        assert v["quoted"] == 105.0
        assert v["actual"] == 100.0
        assert v["delta_pct"] > 4.9

    def test_missing_parquet_row_fails(self, synthetic_root):
        # 2020 is way before parquet coverage
        pos = [{
            "ticker": "TESTA", "entry_date": "2020-01-01",
            "entry_price": 100.0, "status": "ACTIVE",
        }]
        rep = check_entry_alignment(synthetic_root, "india", pos)
        assert rep.status == "FAIL"
        assert rep.violations[0]["actual"] is None
        assert "no parquet" in rep.violations[0]["reason"]

    def test_non_trading_day_falls_back_to_prior_close(self, synthetic_root):
        # 2026-08-02 is a weekend · guard should fall back to
        # 2026-07-31 (or the last available date before) ·
        # but our parquet starts 2026-08-03, so no fallback exists
        # For 2026-08-08 (Sat weekend) · fallback to Fri 2026-08-07
        pos = [{
            "ticker": "TESTA", "entry_date": "2026-08-08",
            "entry_price": 104.0, "status": "ACTIVE",
        }]
        # Aug 3=100, 4=101, 5=102, 6=103, 7=104 · so Sat Aug 8 fallback
        # to Fri Aug 7 = 104. Quoted 104 matches.
        rep = check_entry_alignment(synthetic_root, "india", pos)
        assert rep.status == "PASS"

    def test_multiple_positions_mixed(self, synthetic_root):
        pos = [
            {"ticker": "TESTA", "entry_date": "2026-08-03",
             "entry_price": 100.0, "status": "ACTIVE"},        # OK
            {"ticker": "TESTA", "entry_date": "2026-08-04",
             "entry_price": 999.0, "status": "ACTIVE"},        # FAIL
            {"ticker": "TESTB", "entry_date": "2026-08-03",
             "entry_price": 200.0, "status": "ACTIVE"},        # OK
        ]
        rep = check_entry_alignment(synthetic_root, "india", pos)
        assert rep.status == "FAIL"
        assert len(rep.violations) == 1
        assert rep.violations[0]["ticker"] == "TESTA"

    def test_skips_positions_with_no_entry_data(self, synthetic_root):
        pos = [
            {"ticker": "TESTA", "entry_date": "", "entry_price": 100.0,
             "status": "ACTIVE"},                              # skip · no date
            {"ticker": "TESTA", "entry_date": "2026-08-03",
             "entry_price": None, "status": "ACTIVE"},         # skip · no price
        ]
        rep = check_entry_alignment(synthetic_root, "india", pos)
        assert rep.status == "PASS"
        assert not rep.violations


# ═════════════════════════════════════════════════════════════════
# PI2 · Exit-price alignment
# ═════════════════════════════════════════════════════════════════
class TestPI2_ExitAlignment:

    def test_exit_matches_parquet_passes(self, synthetic_root):
        pos = [{
            "ticker": "TESTA", "exit_date": "2026-08-05",
            "exit_price": 102.0, "status": "EXIT",
        }]
        rep = check_exit_alignment(synthetic_root, "india", pos)
        assert rep.status == "PASS"

    def test_exit_drift_fails(self, synthetic_root):
        pos = [{
            "ticker": "TESTA", "exit_date": "2026-08-05",
            "exit_price": 500.0, "status": "EXIT",
        }]
        rep = check_exit_alignment(synthetic_root, "india", pos)
        assert rep.status == "FAIL"

    def test_non_exit_status_ignored(self, synthetic_root):
        # ACTIVE row with wrong exit_price · PI2 must ignore it
        pos = [{
            "ticker": "TESTA", "exit_date": "2026-08-05",
            "exit_price": 999.0, "status": "ACTIVE",
        }]
        rep = check_exit_alignment(synthetic_root, "india", pos)
        assert rep.status == "PASS"


# ═════════════════════════════════════════════════════════════════
# PI5 · Freshness
# ═════════════════════════════════════════════════════════════════
class TestPI5_Freshness:

    def test_recent_data_passes(self, synthetic_root):
        # Parquet ends around 2026-09-11 (30 business days from 2026-08-03)
        # asof close to that date · should be fresh
        rep = check_freshness(
            synthetic_root, "india", ["TESTA"], "2026-09-11")
        assert rep.status == "PASS"

    def test_stale_data_fails(self, synthetic_root):
        # asof 2027-01-01 · parquet's last row was months ago
        rep = check_freshness(
            synthetic_root, "india", ["TESTA"], "2027-01-01")
        assert rep.status == "FAIL"
        assert rep.violations[0]["ticker"] == "TESTA"
        assert "stale" in rep.violations[0]["reason"]

    def test_missing_parquet_fails(self, synthetic_root):
        rep = check_freshness(
            synthetic_root, "india", ["NOSUCH"], "2026-09-11")
        assert rep.status == "FAIL"
        assert rep.violations[0]["reason"] == "no parquet on disk"

    def test_multiple_tickers_partial_fail(self, synthetic_root):
        rep = check_freshness(
            synthetic_root, "india", ["TESTA", "NOSUCH"], "2026-09-11")
        assert rep.status == "FAIL"
        assert len(rep.violations) == 1


# ═════════════════════════════════════════════════════════════════
# compute() · full integration + emit
# ═════════════════════════════════════════════════════════════════
class TestComputeAndEmit:

    def test_all_pass_gives_verdict_pass(self, synthetic_root):
        # Seed PI3 baseline first · else first-run WARN would trip verdict
        save_fingerprints(synthetic_root, "india", ["TESTA", "TESTB"], asof="2026-09-11")
        positions = [
            {"ticker": "TESTA", "entry_date": "2026-08-03",
             "entry_price": 100.0, "status": "ACTIVE"},
            {"ticker": "TESTB", "entry_date": "2026-08-04",
             "entry_price": 200.5, "status": "ACTIVE"},
        ]
        rep = compute(synthetic_root, "india", positions, "2026-09-11")
        # PI4 + PI6 may still emit "PASS · skipped" text in detail but
        # status is PASS · verdict remains PASS. Warn/Fail come from
        # PI1-3-5 only in this synthetic fixture.
        assert rep.verdict == "PASS", (
            f"expected PASS, got {rep.verdict} · checks: "
            f"{[(c.code, c.status) for c in rep.checks]}")
        assert rep.n_positions_checked == 2
        assert rep.n_active_checked == 2
        assert rep.n_exits_checked == 0

    def test_single_fail_bubbles_verdict(self, synthetic_root):
        positions = [{
            "ticker": "TESTA", "entry_date": "2026-08-03",
            "entry_price": 999.0, "status": "ACTIVE",
        }]
        rep = compute(synthetic_root, "india", positions, "2026-09-11")
        assert rep.verdict == "FAIL"

    def test_emit_writes_json(self, synthetic_root):
        positions = [{
            "ticker": "TESTA", "entry_date": "2026-08-03",
            "entry_price": 100.0, "status": "ACTIVE",
        }]
        rep = compute(synthetic_root, "india", positions, "2026-09-11")
        p = emit(synthetic_root, rep)
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        assert "PI1" in content
        assert "verdict" in content


# ═════════════════════════════════════════════════════════════════
# PI3 · Historical immutability
# ═════════════════════════════════════════════════════════════════
class TestPI3_Immutability:

    def test_no_baseline_yet_warns_first_run(self, synthetic_root):
        rep = check_immutability(
            synthetic_root, "india", ["TESTA"], "2026-09-11")
        assert rep.status == "WARN"
        assert "baseline" in rep.detail.lower()

    def test_seeded_baseline_matches_next_run(self, synthetic_root):
        # First run · seed baseline
        save_fingerprints(synthetic_root, "india", ["TESTA", "TESTB"], asof="2026-09-11")
        # Second run · same parquet · should PASS
        rep = check_immutability(
            synthetic_root, "india", ["TESTA", "TESTB"], "2027-01-01")
        assert rep.status == "PASS"

    def test_tampered_parquet_warns(self, synthetic_root):
        # Seed baseline
        save_fingerprints(synthetic_root, "india", ["TESTA"], asof="2027-01-01")
        # Tamper: overwrite parquet with different closes
        raw = synthetic_root / "data" / "raw" / "india"
        dates = pd.date_range("2026-08-01", periods=30, freq="B")
        closes = [500.0 + i for i in range(len(dates))]  # different
        df = pd.DataFrame(
            {"open": closes, "high": closes, "low": closes,
             "close": closes, "tick_volume": [1000] * len(dates),
             "spread": [0.0] * len(dates)},
            index=dates,
        )
        df.index.name = "time"
        df.to_parquet(raw / "TESTA_D1.parquet")
        # Clear parquet cache · same path but different mtime
        from backend.context.price_integrity_guard import _PARQUET_CACHE
        _PARQUET_CACHE.clear()
        rep = check_immutability(
            synthetic_root, "india", ["TESTA"], "2027-01-01")
        assert rep.status == "WARN"
        assert len(rep.violations) == 1
        assert rep.violations[0]["ticker"] == "TESTA"


# ═════════════════════════════════════════════════════════════════
# PI4 · Cross-source · best-effort · runs but should skip gracefully
#   in the test environment (no Angel secrets).
# ═════════════════════════════════════════════════════════════════
class TestPI4_CrossSource:

    def test_empty_tickers_passes(self, synthetic_root):
        rep = check_cross_source(synthetic_root, "india", [], "2026-09-11")
        assert rep.status == "PASS"

    def test_usa_market_skips(self, synthetic_root):
        rep = check_cross_source(synthetic_root, "usa", ["AAPL"], "2026-09-11")
        assert rep.status == "PASS"
        assert "USA" in rep.detail or "single-source" in rep.detail

    def test_india_probe_fails_gracefully(self, synthetic_root):
        # Without Angel creds, PI4 must PASS with a skip note (never
        # blocks) rather than raising or FAILing.
        rep = check_cross_source(
            synthetic_root, "india", ["TESTA"], "2026-09-11")
        assert rep.status == "PASS"


# ═════════════════════════════════════════════════════════════════
# PI6 · Corporate actions · gracefully skip when yfinance unavailable
# ═════════════════════════════════════════════════════════════════
class TestPI6_CorporateActions:

    def test_no_positions_passes(self, synthetic_root):
        rep = check_corporate_actions(
            synthetic_root, "india", [], "2026-09-11")
        assert rep.status == "PASS"

    def test_exit_positions_ignored(self, synthetic_root):
        # EXIT positions are not checked (no forward-looking risk)
        rep = check_corporate_actions(
            synthetic_root, "india",
            [{"ticker": "TESTA", "entry_date": "2026-08-03",
              "status": "EXIT"}],
            "2026-09-11")
        assert rep.status == "PASS"


# ═════════════════════════════════════════════════════════════════
# PREVENTION · validate_price_before_write
# ═════════════════════════════════════════════════════════════════
class TestValidatePriceBeforeWrite:

    def test_matching_price_ok(self, synthetic_root):
        ok, delta, actual = validate_price_before_write(
            synthetic_root, "india", "TESTA", 100.0, "2026-08-03")
        assert ok is True
        assert actual == 100.0
        assert abs(delta) < 0.001

    def test_drifted_price_rejected(self, synthetic_root):
        ok, delta, actual = validate_price_before_write(
            synthetic_root, "india", "TESTA", 105.0, "2026-08-03")
        assert ok is False
        assert actual == 100.0
        assert delta and delta > 4.9

    def test_missing_parquet_rejected(self, synthetic_root):
        ok, delta, actual = validate_price_before_write(
            synthetic_root, "india", "NOSUCH", 100.0, "2026-08-03")
        assert ok is False
        assert actual is None
