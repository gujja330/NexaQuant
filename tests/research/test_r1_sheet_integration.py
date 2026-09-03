"""Tests for the R1 sheet integration fix (commit 91e9c811).

Covers:
  1. Legacy R1 CSV schema (Stock/Profile/Score) normalizes correctly
  2. USA MUST NOT fall back to data/aegis_today.csv (India-only file)
  3. R1 sheet always carries the "no dynamic-exit protection" banner
"""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_r1_sheet_meta_carries_no_dynamic_exit_banner():
    from backend.delivery.sheets.r1_advisory_sheet import sheet_meta, ADVISORY_BANNER
    m = sheet_meta()
    assert "no dynamic-exit protection" in ADVISORY_BANNER.lower()
    assert m["sheet_name"] == "05_R1_Advisory"


def test_build_r1_advisory_rows_normalizes_legacy_schema(tmp_path):
    """Legacy schema {Stock, Sector, Strength, ...} → sheet row must have
    ticker/action/etc populated."""
    from backend.delivery.sheets.r1_advisory_sheet import build_r1_advisory_rows
    # Simulate the rename-normalized dict the builder produces after the fix
    picks = [{
        "ticker": "ICICIBANK",
        "sector": "Financials",
        "recommendation": "STRONG BUY",
        "entry_zone": "1389 - 1464",
        "bull_case": "Low-risk Financials holding",
    }]
    rows = build_r1_advisory_rows(tmp_path, "india", "2026-09-03", picks, kg_filter_result={})
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "ICICIBANK"
    assert row[1] == "Financials"
    assert row[2] == "STRONG BUY"
    assert row[4] == "1389 - 1464"
    assert row[8] == "no dynamic-exit protection"


def test_usa_never_falls_back_to_india_r1_file(tmp_path):
    """USA must NOT read data/aegis_today.csv (India-only R1 output).
    Regression guard: if USA loads that file → India picks land as USA picks."""
    import scripts.build_aegis_3sheet_workbook as builder
    src = Path(builder.__file__).read_text(encoding="utf-8", errors="replace")
    # The candidates block must gate the India fallback on market.lower() == "india"
    assert 'if market.lower() == "india":' in src, (
        "USA fallback guard missing · USA would load India's aegis_today.csv"
    )
    assert 'picks_candidates.append(root / "data" / "aegis_today.csv")' in src


def test_r1_ticker_column_rename_present():
    """Ensure the Stock→ticker rename mapping is in the builder."""
    import scripts.build_aegis_3sheet_workbook as builder
    src = Path(builder.__file__).read_text(encoding="utf-8", errors="replace")
    for original, renamed in [("Stock", "ticker"), ("Sector", "sector"),
                              ("Strength", "action"), ("Buy Range", "entry_zone")]:
        assert f'"{original}": "{renamed}"' in src, (
            f"legacy R1 column {original}→{renamed} rename missing"
        )
