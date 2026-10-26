"""The price-bar denominator must be the UNIVERSE, not the files present.

CEO 2026-10-26. Asked "is data refresh happening daily for all stocks?",
the certification answered "508/508 files (universe)" for USA and
"225/225" for India. Both read as complete coverage. Neither was:

  india   universe 228 · 225 have bars · LTIM, PEL, TATAMOTORS have none
  usa     universe 516 · 508 have bars · BRK.B, BF.B, GGP, IQVIA, LVMH,
                                         MBIA, SCANA, TSYS have none

The denominator was computed from what was on disk rather than what the
universe requires, so eleven names with no data at all were invisible.

Separately, the freshness gate keys on the MAXIMUM bar date across all
files, so a single current ticker satisfies it while an individual name
rots - GUJGASLTD sat 55 days stale and EA 83.

Both facts are now MEASURED AND REPORTED. Neither blocks: a delisted or
renamed upstream name is a universe-maintenance decision, not a
data-pipeline verdict, and failing the run over one would stop delivery
for a reason the pipeline cannot fix.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("india", "usa")


@pytest.mark.parametrize("market", MARKETS)
def test_coverage_is_measured_against_the_universe(market):
    from backend.pipeline.contract.readiness import (_price_bars_truth,
                                                     _universe_list)
    uni = _universe_list(ROOT, market)
    if not uni:
        pytest.skip("universe not resolvable for %s" % market)
    b = _price_bars_truth(ROOT, market, uni)

    assert b.get("n_universe") == len(uni), (
        "the denominator must be the universe size, not the file count")
    assert b.get("n_universe_missing") is not None, (
        "names with NO bars must be counted, or coverage reads as complete "
        "while tickers are silently absent")
    assert b["n_universe_missing"] == len(b.get("universe_missing") or [])
    # the count must be consistent with the parts
    assert b["n_files"] + b["n_universe_missing"] == b["n_universe"], (
        "files-present plus names-missing must account for the whole "
        "universe; a mismatch means the scope filter is dropping names "
        "silently")


@pytest.mark.parametrize("market", MARKETS)
def test_per_ticker_lag_is_measured_not_just_the_max(market):
    """One fresh ticker must not be able to vouch for the whole book."""
    from backend.pipeline.contract.readiness import (_price_bars_truth,
                                                     _universe_list)
    uni = _universe_list(ROOT, market)
    if not uni:
        pytest.skip("universe not resolvable for %s" % market)
    b = _price_bars_truth(ROOT, market, uni)
    assert b.get("n_behind_lead") is not None, (
        "names trailing the leading bar date must be counted - the "
        "freshness gate keys on the MAXIMUM date, so without this a single "
        "current ticker makes the whole book look fresh")
    for r in (b.get("behind_lead") or []):
        assert "ticker" in r and "newest_bar" in r


def test_certification_reports_the_universe_denominator():
    src = (ROOT / "backend/pipeline/contract/certification.py").read_text(
        encoding="utf-8")
    assert "n_universe" in src, (
        "the certification is back to printing the file count as its own "
        "denominator, which always reads 100%")
    assert "no bars at all" in src, "missing names must be named"
    assert "behind leading bar" in src, "trailing names must be named"
