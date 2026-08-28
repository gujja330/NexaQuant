"""AEGIS · Delivery · Portfolio Source (Registry-ACTIVE) regression tests.

CEO 2026-08-28 · Path A directive:
> "Fix Portfolio to source from Registry ACTIVE (stable current holdings)."

Verifies:
· Registry ACTIVE positions surface in Portfolio · every one · every run
· Determinism: same Registry + snapshot + parquet → identical output
· Missing-tickers-only pattern: caller can compute delta between what's
  already displayed and what Registry says should be there
"""
import json
import pytest
from pathlib import Path


def _bootstrap_registry(tmp_path: Path, positions: list):
    """Write a minimal Registry with `positions` as ACTIVE opportunities.
    positions = [{"ticker": "PLTR", "runner": "R2", "created": "2026-08-10"}, ...]"""
    from backend.research.opportunity_registry import make_opportunity_id
    p = tmp_path / "reports" / "research" / "opportunity_registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for pos in positions:
            pid = make_opportunity_id("usa", pos["runner"], pos["ticker"],
                                       pos["created"])
            row = {
                "opportunity_id": pid, "market": "usa",
                "runner": pos["runner"], "ticker": pos["ticker"],
                "created_date": pos["created"],
                "initial_signal": "BUY", "initial_rank": 1,
                "initial_score": 0.85, "status": "ACTIVE",
                "closed_date": "", "closed_reason": "",
                "last_seen_date": pos["created"],
                "ts_utc": pos.get("ts", f"{pos['created']}T00:00:00+00:00"),
            }
            f.write(json.dumps(row) + "\n")


def _bootstrap_parquet(tmp_path: Path, market: str, ticker: str, closes: list):
    """Write a per-ticker parquet · closes = [(date_iso, price), ...]"""
    import pandas as pd
    base = "usa/data/raw/us" if market == "usa" else "data/raw/india"
    d = tmp_path / base
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime([c[0] for c in closes])
    df = pd.DataFrame({"close": [c[1] for c in closes]}, index=idx)
    df.to_parquet(d / f"{ticker}_D1.parquet")


# ── 1 · Every Registry ACTIVE surfaces in build_active_positions ──


def test_every_registry_active_appears_in_build(tmp_path):
    """3 Registry ACTIVE → 3 rows in build_active_positions."""
    from backend.delivery.portfolio_source import build_active_positions
    _bootstrap_registry(tmp_path, [
        {"ticker": "PLTR", "runner": "R2", "created": "2026-08-10"},
        {"ticker": "MSFT", "runner": "R1", "created": "2026-08-10"},
        {"ticker": "UBER", "runner": "R1", "created": "2026-08-10"},
    ])
    for tk in ("PLTR", "MSFT", "UBER"):
        _bootstrap_parquet(tmp_path, "usa", tk,
                            [("2026-08-10", 100.0), ("2026-08-27", 105.0)])
    rows = build_active_positions(tmp_path, "usa", asof="2026-08-27")
    assert len(rows) == 3
    tickers = {r["ticker"] for r in rows}
    assert tickers == {"PLTR", "MSFT", "UBER"}


# ── 2 · Determinism · same inputs = byte-identical output ──


def test_build_is_deterministic_across_reruns(tmp_path):
    from backend.delivery.portfolio_source import build_active_positions
    _bootstrap_registry(tmp_path, [
        {"ticker": "PLTR", "runner": "R2", "created": "2026-08-10"},
        {"ticker": "MSFT", "runner": "R1", "created": "2026-08-10"},
    ])
    _bootstrap_parquet(tmp_path, "usa", "PLTR",
                        [("2026-08-10", 175.23), ("2026-08-27", 183.86)])
    _bootstrap_parquet(tmp_path, "usa", "MSFT",
                        [("2026-08-10", 498.13), ("2026-08-27", 512.30)])
    outputs = set()
    for _ in range(5):
        r = build_active_positions(tmp_path, "usa", asof="2026-08-27")
        outputs.add(json.dumps(r, sort_keys=True))
    assert len(outputs) == 1, \
        f"build_active_positions not deterministic · {len(outputs)} distinct outputs"


# ── 3 · Portfolio-completeness helper · returns only missing tickers ──


def test_missing_tickers_returns_delta_only(tmp_path):
    """Caller passes set of already-displayed (runner, ticker) · function
    returns Registry ACTIVE minus that set."""
    from backend.delivery.portfolio_source import missing_tickers
    _bootstrap_registry(tmp_path, [
        {"ticker": "PLTR", "runner": "R2", "created": "2026-08-10"},
        {"ticker": "MSFT", "runner": "R1", "created": "2026-08-10"},
        {"ticker": "UBER", "runner": "R1", "created": "2026-08-10"},
    ])
    for tk in ("PLTR", "MSFT", "UBER"):
        _bootstrap_parquet(tmp_path, "usa", tk, [("2026-08-10", 100.0)])
    # Main loop already displayed PLTR/R2 · UBER/R1 is missing
    displayed = {("R2", "PLTR"), ("R1", "MSFT")}
    missing = missing_tickers(tmp_path, "usa", asof="2026-08-10",
                                displayed=displayed)
    assert len(missing) == 1
    assert missing[0]["ticker"] == "UBER"
    assert missing[0]["runner"] == "R1"


# ── 4 · Positions without a parquet close are skipped, not fabricated ──


def test_position_without_parquet_close_is_skipped(tmp_path):
    """If ticker has no parquet at all, position is skipped · never
    fabricated. Matches canonical_entry rule · fail-safe by omission."""
    from backend.delivery.portfolio_source import build_active_positions
    _bootstrap_registry(tmp_path, [
        {"ticker": "DELISTED", "runner": "R2", "created": "2026-08-01"},
    ])
    # No parquet for DELISTED
    rows = build_active_positions(tmp_path, "usa", asof="2026-08-27")
    assert len(rows) == 0


# ── 5 · Sort stability · runner then ticker ──


def test_output_sort_is_stable(tmp_path):
    from backend.delivery.portfolio_source import build_active_positions
    _bootstrap_registry(tmp_path, [
        {"ticker": "ZZZZ", "runner": "R1", "created": "2026-08-10"},
        {"ticker": "AAAA", "runner": "R2", "created": "2026-08-10"},
        {"ticker": "MMMM", "runner": "R1", "created": "2026-08-10"},
    ])
    for tk in ("ZZZZ", "AAAA", "MMMM"):
        _bootstrap_parquet(tmp_path, "usa", tk, [("2026-08-10", 100.0)])
    r = build_active_positions(tmp_path, "usa", asof="2026-08-10")
    assert [x["ticker"] for x in r] == ["MMMM", "ZZZZ", "AAAA"]   # R1 first, then R2 alphabetical
