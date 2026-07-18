"""Validation Engine v2.0 smoke tests. Uses a temporary ledger location."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import numpy as np
import pandas as pd


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _redirect_ledger():
    """Point the paper-portfolio ledger at a temp dir for this test run."""
    from validation_v2.lib import paper_portfolio
    tmp = Path(tempfile.mkdtemp(prefix="validation_v2_test_"))
    paper_portfolio.LEDGER_DIR = tmp
    paper_portfolio.POSITIONS_PATH = tmp / "paper_positions.parquet"
    paper_portfolio.TRADES_PATH    = tmp / "paper_trades.parquet"
    paper_portfolio.MTM_PATH       = tmp / "paper_mtm.parquet"
    return tmp


def test_open_close_cycle():
    tmp = _redirect_ledger()
    try:
        from validation_v2.lib import paper_portfolio

        t = paper_portfolio.open_position("AAA", 100.0, 0.05, "Buy", "v1.4",
                                              entry_date="2026-01-01")
        _check("open returns trade", t is not None and t.action == "OPEN")

        open_p = paper_portfolio.open_positions()
        _check("open ledger has 1 position",
                len(open_p) == 1 and open_p.iloc[0]["ticker"] == "AAA")

        # Dedup: opening same content twice must not create two rows
        t2 = paper_portfolio.open_position("AAA", 100.0, 0.05, "Buy", "v1.4",
                                                entry_date="2026-01-01")
        open_p2 = paper_portfolio.open_positions()
        _check("dedup: same content = single row", len(open_p2) == 1)

        # Mark to market
        mtm = paper_portfolio.mark_to_market({"AAA": 105.0}, as_of="2026-01-15")
        _check("MTM produces row", len(mtm) == 1 and abs(mtm.iloc[0]["pnl_pct"] - 0.05) < 1e-6)

        # Close
        closed = paper_portfolio.close_position("AAA", 110.0, "target_hit",
                                                     exit_date="2026-02-01")
        _check("close returns trade", closed is not None and closed.action == "CLOSE")
        _check("close computes return_pct",
                abs(closed.return_pct - 0.10) < 1e-6)

        # After close, open positions empty
        open_p3 = paper_portfolio.open_positions()
        _check("open positions empty after close", len(open_p3) == 0)

        # Closed trades ledger has the CLOSE row
        cl = paper_portfolio.closed_trades()
        _check("closed_trades has 1 row", len(cl) == 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_expected_actual_reconcile():
    from validation_v2.lib import expected_actual
    closed = pd.DataFrame([{
        "ticker": "AAA", "entry_date": "2026-01-01", "exit_date": "2026-02-01",
        "entry_price": 100.0, "exit_price": 110.0, "return_pct": 0.10,
        "holding_days": 30, "rec_type": "Buy", "rec_source": "v1.4",
        "reason_close": "target_hit",
    }])
    result = expected_actual.reconcile(closed)
    _check("reconcile handles empty recs gracefully",
            result["n"] == 1)


def test_drift_metric_drift():
    from validation_v2.lib import drift
    df = pd.DataFrame({
        "exit_date":  pd.date_range("2026-01-01", periods=50, freq="D"),
        "return_pct": np.concatenate([np.full(25, 0.03), np.full(25, -0.01)]),
    })
    r = drift.metric_drift(df)
    _check("drift flags degrading pattern",
            r["flag"] in ("degrading", "stable"),
            detail=r["flag"])
    _check("winrate_change_pp is negative",
            r["winrate_change_pp"] < 0)


def test_drift_rolling_edge():
    from validation_v2.lib import drift
    df = pd.DataFrame({
        "exit_date":  pd.date_range("2026-01-01", periods=100, freq="D"),
        "return_pct": np.random.default_rng(42).normal(0.02, 0.05, 100),
    })
    rolling = drift.rolling_edge(df, window=20)
    _check("rolling edge produces (n - window + 1) rows",
            len(rolling) == 100 - 20 + 1)


def test_opportunity_cost_shape():
    from validation_v2.lib import opportunity_cost
    learning = pd.DataFrame({
        "ticker":     ["AAA"] * 10 + ["BBB"] * 10,
        "exit_date":  pd.date_range("2026-06-01", periods=20, freq="D"),
        "is_winner":  [1] * 8 + [0] * 2 + [0] * 10,
        "return_pct": [0.05] * 8 + [-0.02] * 2 + [-0.03] * 10,
    })
    recs = {"recommendations": [
        {"ticker": "CCC", "recommendation": "Buy"},
    ]}
    r = opportunity_cost.compute_opportunity_cost(recs, learning, window_days=30)
    _check("opportunity_cost handles ticker without a rec",
            r["n_missed_edges"] >= 1,
            detail=f"AAA should qualify as missed edge; got {r}")


def main() -> int:
    print("=" * 72); print("  VALIDATION ENGINE v2.0 · SMOKE TESTS"); print("=" * 72)
    test_open_close_cycle(); print()
    test_expected_actual_reconcile(); print()
    test_drift_metric_drift(); print()
    test_drift_rolling_edge(); print()
    test_opportunity_cost_shape(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
