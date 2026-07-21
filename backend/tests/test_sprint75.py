"""
Sprint 7.5 · Market Data Persistence & History + Factor Library regression tests.

Runs the persistence layer and factor library in an isolated tmpdir so the
main repo history parquets are never mutated by test runs.
"""
from __future__ import annotations
import io
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

from backend.persistence import (
    append_snapshot_row, load_history, write_snapshot_and_history,
    HISTORY_SCHEMA_VERSION,
)
from backend.factor_library import build_factor_library


_passed = 0
_failed = 0


def _ok(msg: str) -> None:
    global _passed
    _passed += 1
    print(f"  [OK] {msg}")


def _fail(msg: str, exc: Exception) -> None:
    global _failed
    _failed += 1
    print(f"  [FAIL] {msg}: {exc}")


def _run(label: str, fn):
    try:
        fn()
        _ok(label)
    except AssertionError as e:
        _fail(label, e)
    except Exception as e:
        _fail(label, e)


# ── history_writer tests ────────────────────────────────────────

def test_append_snapshot_row_fresh():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    p = {"engine": "t", "market": "india", "asof": "2026-07-21", "regime": "risk_on"}
    r = append_snapshot_row(p, tmp)
    assert r is not None
    df = load_history(tmp)
    assert len(df) == 1
    assert df.iloc[0]["regime"] == "risk_on"
    assert df.iloc[0]["history_schema_version"] == HISTORY_SCHEMA_VERSION
    shutil.rmtree(tmp.parent)


def test_dedupe_same_asof():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    append_snapshot_row({"engine": "t", "market": "india", "asof": "2026-07-21", "regime": "risk_on"}, tmp)
    append_snapshot_row({"engine": "t", "market": "india", "asof": "2026-07-21", "regime": "risk_off"}, tmp)
    df = load_history(tmp)
    assert len(df) == 1, f"expected 1, got {len(df)}"
    assert df.iloc[0]["regime"] == "risk_off", "most-recent write should win"
    shutil.rmtree(tmp.parent)


def test_append_new_date():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    for asof, regime in [("2026-07-19", "a"), ("2026-07-20", "b"), ("2026-07-21", "c")]:
        append_snapshot_row({"engine": "t", "market": "india", "asof": asof, "regime": regime}, tmp)
    df = load_history(tmp)
    assert len(df) == 3
    assert list(df["asof"]) == ["2026-07-19", "2026-07-20", "2026-07-21"]
    shutil.rmtree(tmp.parent)


def test_market_isolation():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    append_snapshot_row({"engine": "t", "market": "india", "asof": "2026-07-21"}, tmp)
    append_snapshot_row({"engine": "t", "market": "usa",   "asof": "2026-07-21"}, tmp)
    india = load_history(tmp, market="india")
    usa   = load_history(tmp, market="usa")
    assert len(india) == 1 and len(usa) == 1
    shutil.rmtree(tmp.parent)


def test_fail_open_missing_keys():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    r = append_snapshot_row({"engine": "t"}, tmp)
    assert r is None, "missing market+asof must return None (fail-open)"
    shutil.rmtree(tmp.parent)


def test_nested_payload_flattens():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    p = {
        "engine": "t", "market": "india", "asof": "2026-07-21",
        "nested": {"a": 1, "b": [1, 2]},
        "list": [1, 2, 3],
    }
    append_snapshot_row(p, tmp)
    df = load_history(tmp)
    assert isinstance(df.iloc[0]["nested"], str)
    assert isinstance(df.iloc[0]["list"], str)
    reparsed = json.loads(df.iloc[0]["nested"])
    assert reparsed["a"] == 1
    shutil.rmtree(tmp.parent)


def test_write_snapshot_and_history_writes_json_and_parquet():
    tmpdir = Path(tempfile.mkdtemp())
    j = tmpdir / "snapshot.json"
    h = tmpdir / "history.parquet"
    p = {"engine": "t", "market": "india", "asof": "2026-07-21", "n": 42}
    write_snapshot_and_history(p, j, h)
    assert j.exists()
    assert h.exists()
    j_reload = json.loads(j.read_text())
    assert j_reload["n"] == 42
    shutil.rmtree(tmpdir)


def test_load_history_missing_file_returns_empty():
    tmp = Path(tempfile.mkdtemp()) / "does_not_exist.parquet"
    df = load_history(tmp)
    assert df.empty
    shutil.rmtree(tmp.parent)


def test_history_deterministic_across_calls():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    p = {"engine": "t", "market": "india", "asof": "2026-07-21", "regime": "risk_on"}
    append_snapshot_row(p, tmp)
    r1 = load_history(tmp)
    append_snapshot_row(p, tmp)
    r2 = load_history(tmp)
    assert len(r1) == len(r2) == 1
    assert r1.iloc[0]["regime"] == r2.iloc[0]["regime"]
    shutil.rmtree(tmp.parent)


def test_model_stamp_captured_separately():
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    p = {
        "engine": "t", "market": "india", "asof": "2026-07-21",
        "model_stamp": {"model_id": "x", "version": "1.0.0"},
    }
    append_snapshot_row(p, tmp)
    df = load_history(tmp)
    assert "model_stamp_json" in df.columns
    assert "model_stamp" not in df.columns, "raw dict field should not leak into flat row"
    assert json.loads(df.iloc[0]["model_stamp_json"])["model_id"] == "x"
    shutil.rmtree(tmp.parent)


# ── factor library tests ─────────────────────────────────────────

def test_factor_library_end_to_end():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "commodity_intelligence.json").write_text(json.dumps({
        "commodities": [
            {"symbol": "CL=F", "last": 80.0, "chg_1w_pct": 3.0, "chg_1m_pct": 5.0, "trend": "bull"},
            {"symbol": "GC=F", "last": 2000.0, "chg_1w_pct": 0.5, "trend": "sideways"},
        ]
    }))
    (tmp / "currency_intelligence.json").write_text(json.dumps({
        "currencies": [{"symbol": "UUP", "last": 28.0, "chg_1w_pct": -0.5}]
    }))
    (tmp / "bond_intelligence.json").write_text(json.dumps({
        "bonds": [{"symbol": "^TNX", "last": 4.2, "chg_1m_bps": 5}]
    }))
    (tmp / "central_bank_state.json").write_text(json.dumps({
        "bank": "Fed", "rate_cycle": "neutral", "short_yield_pct": 4.1,
        "yield_curve_slope": 30, "inversion": False,
    }))
    (tmp / "volatility_intelligence.json").write_text(json.dumps({
        "symbol": "^VIX", "last": 18.5, "regime": "normal", "chg_1m_pct": -2.5,
    }))
    (tmp / "sector_rotation.json").write_text(json.dumps({
        "leaders": ["Financials"], "laggards": ["Technology"],
    }))

    result = build_factor_library(
        market="usa", reports_dir=tmp, asof=date(2026, 7, 21),
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    assert result.n_factors > 0
    by_name = {f.factor: f for f in result.factors}
    assert by_name["oil_wti"].value == 80.0
    assert by_name["oil_wti"].trend == "bull"
    assert by_name["gold"].value == 2000.0
    assert by_name["vix"].value == 18.5
    assert by_name["vix"].value_label == "normal"
    assert by_name["fed_rate_cycle"].value_label == "neutral"
    assert by_name["yield_curve_inversion"].value == 0.0
    assert by_name["sector_rotation_leader"].value_label == "Financials"
    shutil.rmtree(tmp)


def test_factor_library_no_data_all_low_confidence():
    tmp = Path(tempfile.mkdtemp())
    result = build_factor_library(
        market="india", reports_dir=tmp, asof=date(2026, 7, 21),
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    assert result.n_factors > 0
    n_zero_conf = sum(1 for f in result.factors if f.confidence == 0.0)
    assert n_zero_conf >= result.n_factors * 0.9, "missing inputs should yield low-confidence rows, not crashes"
    shutil.rmtree(tmp)


def test_factor_library_deterministic():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "volatility_intelligence.json").write_text(json.dumps({
        "symbol": "^VIX", "last": 20.0, "regime": "normal",
    }))
    r1 = build_factor_library(
        market="usa", reports_dir=tmp, asof=date(2026, 7, 21),
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    r2 = build_factor_library(
        market="usa", reports_dir=tmp, asof=date(2026, 7, 21),
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    assert r1.n_factors == r2.n_factors
    for a, b in zip(r1.factors, r2.factors):
        assert a.value == b.value and a.value_label == b.value_label and a.trend == b.trend
    shutil.rmtree(tmp)


def test_factor_library_no_promotion_keys():
    tmp = Path(tempfile.mkdtemp())
    result = build_factor_library(
        market="usa", reports_dir=tmp, asof=date(2026, 7, 21),
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    banned = {"buy", "sell", "target_price", "recommendation", "action", "promoted", "approved"}
    for f in result.factors:
        d = f.__dict__ if hasattr(f, "__dict__") else vars(f)
        for k in d:
            assert k.lower() not in banned, f"factor {f.factor} has banned key {k}"
    shutil.rmtree(tmp)


def test_factor_library_covers_all_source_types():
    tmp = Path(tempfile.mkdtemp())
    result = build_factor_library(
        market="usa", reports_dir=tmp, asof=date(2026, 7, 21),
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    sources = {f.source for f in result.factors}
    for expected in ("commodity", "currency", "bond", "volatility", "central_bank", "derived", "rotation"):
        assert expected in sources, f"missing source {expected}"
    shutil.rmtree(tmp)


def test_factor_library_walk_forward_asof_honored():
    tmp = Path(tempfile.mkdtemp())
    d1 = date(2026, 3, 15)
    d2 = date(2026, 7, 21)
    r1 = build_factor_library(
        market="usa", reports_dir=tmp, asof=d1,
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    r2 = build_factor_library(
        market="usa", reports_dir=tmp, asof=d2,
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    assert r1.asof == d1 and r2.asof == d2
    shutil.rmtree(tmp)


def test_factor_taxonomy_populated():
    """Every factor row must carry the config-declared source/unit/affected metadata."""
    tmp = Path(tempfile.mkdtemp())
    result = build_factor_library(
        market="usa", reports_dir=tmp, asof=date(2026, 7, 21),
        config_path=_ROOT / "configs" / "factor_library_config.yaml",
    )
    for f in result.factors:
        assert f.factor, "factor name required"
        assert f.source, f"source required for {f.factor}"
        assert f.unit, f"unit required for {f.factor}"
    shutil.rmtree(tmp)


def test_history_writer_survives_repeat_appends():
    """Simulate 60 days of daily appends — history should reach 60 rows deterministically."""
    tmp = Path(tempfile.mkdtemp()) / "h.parquet"
    from datetime import date, timedelta
    start = date(2026, 5, 1)
    for i in range(60):
        d = start + timedelta(days=i)
        append_snapshot_row(
            {"engine": "t", "market": "india", "asof": d.isoformat(), "n": i},
            tmp,
        )
    df = load_history(tmp)
    assert len(df) == 60
    assert df.iloc[0]["n"] == 0 and df.iloc[-1]["n"] == 59
    shutil.rmtree(tmp.parent)


# ── run all ─────────────────────────────────────────────────────

TESTS = [
    ("append_snapshot_row fresh", test_append_snapshot_row_fresh),
    ("dedupe same asof (latest wins)", test_dedupe_same_asof),
    ("append new date sorted", test_append_new_date),
    ("market isolation", test_market_isolation),
    ("fail-open on missing keys", test_fail_open_missing_keys),
    ("nested payload flattens to JSON columns", test_nested_payload_flattens),
    ("write_snapshot_and_history writes JSON + parquet", test_write_snapshot_and_history_writes_json_and_parquet),
    ("load_history missing file returns empty", test_load_history_missing_file_returns_empty),
    ("history writes deterministic across calls", test_history_deterministic_across_calls),
    ("model_stamp captured in dedicated column", test_model_stamp_captured_separately),
    ("factor library end-to-end (all sources present)", test_factor_library_end_to_end),
    ("factor library resilient to no data (low confidence)", test_factor_library_no_data_all_low_confidence),
    ("factor library deterministic (same inputs → same outputs)", test_factor_library_deterministic),
    ("factor library no-promotion contract", test_factor_library_no_promotion_keys),
    ("factor library covers all source taxonomies", test_factor_library_covers_all_source_types),
    ("factor library honors walk-forward asof cutoff", test_factor_library_walk_forward_asof_honored),
    ("factor taxonomy metadata populated", test_factor_taxonomy_populated),
    ("history survives 60-day daily replay", test_history_writer_survives_repeat_appends),
]


def main() -> int:
    print("=" * 70)
    print("  SPRINT 7.5 · Persistence & Factor Library · Regression Tests")
    print("=" * 70)
    for label, fn in TESTS:
        _run(label, fn)
    total = _passed + _failed
    print()
    print(f"  {_passed} passed, {_failed} failed of {total}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
