"""PIE episode dataset · identity, point-in-time and isolation.

Every test builds its own registry and its own bars inside tmp_path. None
of them read or write the repository's registry, ledgers, shadow outcomes
or price files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.research.priority_intelligence import episode_dataset as ed  # noqa: E402

BARS_REL = {"india": ("data", "raw", "india"),
            "usa": ("usa", "data", "raw", "us")}


def _bars(root: Path, market: str, ticker: str, n: int = 40,
          start: str = "2026-08-01", step: float = 1.0) -> None:
    d = root.joinpath(*BARS_REL[market])
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, periods=n)
    df = pd.DataFrame({"open": [100.0 + i * step for i in range(n)],
                       "high": [101.0 + i * step for i in range(n)],
                       "low": [99.0 + i * step for i in range(n)],
                       "close": [100.0 + i * step for i in range(n)],
                       "volume": [1000] * n}, index=idx)
    df.to_parquet(d / ("%s_D1.parquet" % ticker))


def _registry(root: Path, events: list) -> None:
    p = root / "reports" / "research" / "opportunity_registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n",
                 encoding="utf-8")


def _ev(oid, ticker, market="india", status="ACTIVE",
        created="2026-08-04", closed="", ts="2026-08-04T12:00:00",
        runner="R2", reason="") -> dict:
    return {"opportunity_id": oid, "market": market, "runner": runner,
            "ticker": ticker, "created_date": created, "status": status,
            "closed_date": closed, "closed_reason": reason,
            "initial_signal": "BUY", "initial_rank": 1, "initial_score": 0.8,
            "last_seen_date": created, "ts_utc": ts}


@pytest.fixture(autouse=True)
def _clear_bar_cache():
    """The resolver caches bars by (root, market, ticker) · keep tests clean."""
    from backend.research.r3_program import outcome_resolver as r
    r._cache.clear()
    yield
    r._cache.clear()


# ── identity ────────────────────────────────────────────────────────

def test_one_row_per_episode_not_per_ticker(tmp_path):
    """The ZBRA shape · two episodes of one name are two rows."""
    _bars(tmp_path, "india", "ZBRA", n=60)
    _registry(tmp_path, [
        _ev("IND-R2-ZBRA-1", "ZBRA", status="CLOSED", created="2026-08-04",
            closed="2026-08-20", ts="2026-08-20T17:00:00",
            reason="Auto-close · orphaned position"),
        _ev("IND-R2-ZBRA-2", "ZBRA", status="ACTIVE", created="2026-09-15",
            ts="2026-09-15T17:00:00"),
    ])
    df, cov = ed.build(tmp_path, "india")
    assert len(df) == 2, df[["episode_id", "ticker"]]
    assert cov["tickers"] == 1 and cov["episodes"] == 2
    assert sorted(df["episode_id"]) == ["IND-R2-ZBRA-1", "IND-R2-ZBRA-2"]
    assert cov["closed"] == 1 and cov["open"] == 1


def test_the_latest_event_wins_per_episode(tmp_path):
    _bars(tmp_path, "india", "SBIN")
    _registry(tmp_path, [
        _ev("IND-R2-SBIN-1", "SBIN", status="ACTIVE", ts="2026-08-04T12:00:00"),
        _ev("IND-R2-SBIN-1", "SBIN", status="CLOSED", closed="2026-08-18",
            ts="2026-08-18T17:00:00", reason="target hit"),
    ])
    df, _ = ed.build(tmp_path, "india")
    assert len(df) == 1
    assert df["is_closed"].iloc[0] is True or bool(df["is_closed"].iloc[0])
    assert df["closed_reason"].iloc[0] == "target hit"


# ── point-in-time ───────────────────────────────────────────────────

def test_entry_price_is_the_bar_after_the_decision(tmp_path):
    """A decision on `asof` cannot transact at that day's close."""
    _bars(tmp_path, "india", "TCS", n=40, start="2026-08-03", step=1.0)
    _registry(tmp_path, [_ev("IND-R2-TCS-1", "TCS", created="2026-08-04")])
    df, _ = ed.build(tmp_path, "india")
    row = df.iloc[0]
    # bars are 08-03=100.0, 08-04=101.0, 08-05=102.0. The decision is dated
    # 08-04, so its own bar is NOT tradeable: the entry is 08-05 at 102.0.
    assert row["entry_bar_date"] == "2026-08-05"
    assert row["entry_price"] == 102.0, row[["entry_bar_date", "entry_price"]]


def test_an_unmatured_horizon_is_absent_not_zero(tmp_path):
    """Only 3 bars after entry · 5/10/20d must not report a number."""
    _bars(tmp_path, "india", "ITC", n=5, start="2026-08-03")
    _registry(tmp_path, [_ev("IND-R2-ITC-1", "ITC", created="2026-08-04")])
    df, cov = ed.build(tmp_path, "india")
    row = df.iloc[0]
    for h in ed.HORIZONS:
        assert row["mtm_ret_%dd_resolved" % h] in (False, 0), h
        assert pd.isna(row["mtm_ret_%dd_pct" % h]), h
    assert cov["mtm_5d_unresolved"] == 1


def test_a_matured_horizon_resolves_with_the_right_arithmetic(tmp_path):
    _bars(tmp_path, "india", "WIPRO", n=40, start="2026-08-03", step=1.0)
    _registry(tmp_path, [_ev("IND-R2-WIPRO-1", "WIPRO", created="2026-08-04")])
    df, _ = ed.build(tmp_path, "india")
    row = df.iloc[0]
    assert bool(row["mtm_ret_5d_resolved"])
    # entry 102.0 (08-05), +5 bars -> 107.0
    assert row["mtm_ret_5d_pct"] == pytest.approx(100.0 * 5.0 / 102.0)


# ── the two outcome families stay apart ─────────────────────────────

def test_realized_and_horizon_outcomes_are_separate_columns(tmp_path):
    _bars(tmp_path, "india", "HDFCBANK", n=40, start="2026-08-03", step=1.0)
    _registry(tmp_path, [
        _ev("IND-R2-HDFCBANK-1", "HDFCBANK", status="CLOSED",
            created="2026-08-04", closed="2026-08-11",
            ts="2026-08-11T17:00:00", reason="stop"),
    ])
    df, _ = ed.build(tmp_path, "india")
    row = df.iloc[0]
    assert bool(row["registry_realized_resolved"])
    assert row["registry_realized_exit_date"] <= "2026-08-11"
    # the realized number must not be copied into a horizon column
    assert row["registry_realized_pct"] != row["mtm_ret_20d_pct"]
    assert "registry_realized_pct" in df.columns and "mtm_ret_5d_pct" in df.columns


def test_an_open_episode_has_no_realized_outcome(tmp_path):
    _bars(tmp_path, "india", "INFY", n=40)
    _registry(tmp_path, [_ev("IND-R2-INFY-1", "INFY", status="ACTIVE")])
    df, _ = ed.build(tmp_path, "india")
    row = df.iloc[0]
    assert not bool(row["registry_realized_resolved"])
    assert pd.isna(row["registry_realized_pct"])


# ── coverage · nothing dropped silently ─────────────────────────────

def test_an_episode_with_no_bars_is_kept_and_marked(tmp_path):
    _registry(tmp_path, [_ev("IND-R2-GHOST-1", "GHOST")])
    df, cov = ed.build(tmp_path, "india")
    assert len(df) == 1, "the episode was dropped instead of marked"
    assert df["excluded_reason"].iloc[0] == "NO_BARS"
    assert cov["excluded"] == {"NO_BARS": 1}
    assert cov["episodes"] == 1


def test_a_one_bar_ticker_is_marked_insufficient(tmp_path):
    """The AVB/EA/EQR/WBD condition."""
    _bars(tmp_path, "usa", "WBD", n=1, start="2026-08-03")
    _registry(tmp_path, [_ev("USA-R2-WBD-1", "WBD", market="usa",
                             created="2026-08-10")])
    df, cov = ed.build(tmp_path, "usa")
    assert df["excluded_reason"].iloc[0] == "INSUFFICIENT_HISTORY"
    assert cov["excluded"] == {"INSUFFICIENT_HISTORY": 1}


def test_coverage_reports_dates_as_the_effective_sample(tmp_path):
    _bars(tmp_path, "india", "A"); _bars(tmp_path, "india", "B")
    _bars(tmp_path, "india", "C")
    _registry(tmp_path, [
        _ev("IND-R2-A-1", "A", created="2026-08-04"),
        _ev("IND-R2-B-1", "B", created="2026-08-04"),
        _ev("IND-R2-C-1", "C", created="2026-08-05"),
    ])
    _, cov = ed.build(tmp_path, "india")
    assert cov["episodes"] == 3 and cov["entry_dates"] == 2
    assert "effective sample is 2 entry DATES, not 3 episodes" in \
        cov["effective_sample_note"]


# ── isolation and determinism ───────────────────────────────────────

def test_india_and_usa_do_not_leak_into_each_other(tmp_path):
    _bars(tmp_path, "india", "SBIN"); _bars(tmp_path, "usa", "AAPL")
    _registry(tmp_path, [
        _ev("IND-R2-SBIN-1", "SBIN", market="india"),
        _ev("USA-R2-AAPL-1", "AAPL", market="usa", created="2026-08-10"),
    ])
    di, _ = ed.build(tmp_path, "india")
    du, _ = ed.build(tmp_path, "usa")
    assert di["ticker"].tolist() == ["SBIN"]
    assert du["ticker"].tolist() == ["AAPL"]
    assert set(di["market"]) == {"india"} and set(du["market"]) == {"usa"}


def test_the_build_is_deterministic_and_idempotent(tmp_path):
    for t in ("A", "B", "C"):
        _bars(tmp_path, "india", t)
    _registry(tmp_path, [
        _ev("IND-R2-C-1", "C", created="2026-08-06"),
        _ev("IND-R2-A-1", "A", created="2026-08-04"),
        _ev("IND-R2-B-1", "B", created="2026-08-05"),
    ])
    a, ca = ed.build(tmp_path, "india")
    b, cb = ed.build(tmp_path, "india")
    pd.testing.assert_frame_equal(a, b)
    assert a["episode_id"].tolist() == ["IND-R2-A-1", "IND-R2-B-1", "IND-R2-C-1"]
    for k in ("episodes", "tickers", "entry_dates", "closed"):
        assert ca[k] == cb[k]


def test_the_evidence_population_is_labelled(tmp_path):
    """R2 registry history must never be readable as R3 or PIE evidence."""
    _bars(tmp_path, "india", "SBIN")
    _registry(tmp_path, [_ev("IND-R2-SBIN-1", "SBIN")])
    df, _ = ed.build(tmp_path, "india")
    assert set(df["evidence_population"]) == {ed.POP_R2_REGISTRY}


def test_write_puts_files_under_the_pie_directory_only(tmp_path):
    _bars(tmp_path, "india", "SBIN")
    _registry(tmp_path, [_ev("IND-R2-SBIN-1", "SBIN")])
    cov = ed.write(tmp_path, "india")
    assert ed.episodes_path(tmp_path, "india").exists()
    assert ed.coverage_path(tmp_path, "india").exists()
    assert cov["episodes"] == 1
    # and nothing was written outside the PIE baseline directory
    written = {p for p in tmp_path.rglob("*")
               if p.is_file() and "priority_intelligence" in p.as_posix()}
    assert written, "no PIE output produced"
    for p in written:
        assert "historical_baseline" in p.as_posix()


def test_an_empty_registry_yields_an_empty_frame_not_a_crash(tmp_path):
    _registry(tmp_path, [])
    df, cov = ed.build(tmp_path, "india")
    assert df.empty and cov["episodes"] == 0 and cov["entry_dates"] == 0
