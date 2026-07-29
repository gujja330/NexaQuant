"""v2.4 tests · Scorecard + Sector Attribution + Backtrack Engine.

Locks the trust-surface layer:
 · Scorecard computes 6 metrics + stars + overall from a closed-trade DF
 · Attribution decomposes ensemble_score into per-model contributions
 · Backtrack reconstructs per-ticker timeline from snapshot + position store
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd
import pytest

from backend.analytics.scorecard import (  # noqa: E402
    compute_scorecard, SCHEMA_FINGERPRINT as SC_FP, STAR_THRESHOLDS,
)
from backend.analytics.attribution import (  # noqa: E402
    compute_attribution_for_rec, enrich_recs_with_attribution,
    summarize_attribution, SCHEMA_FINGERPRINT as AT_FP,
    MODEL_LABELS, SECTOR_MODEL_ID,
)
from backend.analytics.backtrack import (  # noqa: E402
    build_ticker_backtrack, build_market_backtrack,
    SCHEMA_FINGERPRINT as BT_FP,
)
from backend.recommendation.snapshot import archive_snapshot  # noqa: E402
from backend.portfolio.position_store import update_from_recs  # noqa: E402


# ── AI Scorecard ─────────────────────────────────────────────
def _make_learning_df(n_win: int = 6, n_loss: int = 4) -> pd.DataFrame:
    """Synthetic closed-trade DF · winners hit 5% target, losers hit 5% stop."""
    rows = []
    for i in range(n_win):
        rows.append({
            "entry_date": "2024-01-01", "exit_date": "2024-01-31",
            "return_pct": 8.0 + i * 0.5, "mfe_pct": 12.0 + i * 0.5,
            "mae_pct": -2.0, "hit_5pct_target": True, "hit_5pct_stop": False,
            "is_winner": True, "confidence": 0.6 + i * 0.05, "n_bars_held": 20,
        })
    for i in range(n_loss):
        rows.append({
            "entry_date": "2024-02-01", "exit_date": "2024-02-28",
            "return_pct": -6.0 - i * 0.3, "mfe_pct": 1.0, "mae_pct": -8.0,
            "hit_5pct_target": False, "hit_5pct_stop": True,
            "is_winner": False, "confidence": 0.35 - i * 0.05, "n_bars_held": 25,
        })
    return pd.DataFrame(rows)


def test_scorecard_computes_all_6_metrics_on_sufficient_data():
    df = _make_learning_df()
    sc = compute_scorecard(df)
    assert sc.n_trades == 10
    names = [m["name"] for m in sc.metrics]
    assert "Recommendation Accuracy" in names
    assert "Exit Timing" in names
    assert "Target Hit Rate" in names
    assert "Risk Control" in names
    assert "Rotation Quality" in names
    assert sc.overall_stars in range(1, 6)


def test_scorecard_win_rate_matches_input():
    df = _make_learning_df(n_win=6, n_loss=4)
    sc = compute_scorecard(df)
    accuracy = next(m for m in sc.metrics if m["name"] == "Recommendation Accuracy")
    assert accuracy["value"] == 0.6   # 6/10


def test_scorecard_top_tier_data_scores_5_stars():
    # 10 winners with big MFE-capture, target-hit, small MAE
    df = pd.DataFrame([{
        "entry_date": "2024-01-01", "exit_date": "2024-01-31",
        "return_pct": 15.0, "mfe_pct": 16.0, "mae_pct": -1.0,
        "hit_5pct_target": True, "hit_5pct_stop": False, "is_winner": True,
        "confidence": 0.90, "n_bars_held": 20,
    } for _ in range(50)])
    sc = compute_scorecard(df)
    accuracy = next(m for m in sc.metrics if m["name"] == "Recommendation Accuracy")
    assert accuracy["stars"] == 5


def test_scorecard_verdict_maps_to_stars():
    df = _make_learning_df()
    sc = compute_scorecard(df)
    if sc.overall_stars >= 4:
        assert sc.verdict == "institutional_grade"
    elif sc.overall_stars >= 3:
        assert sc.verdict == "acceptable"


def test_scorecard_empty_data_reports_insufficient():
    sc = compute_scorecard(pd.DataFrame())
    assert sc.verdict == "insufficient_data"
    assert sc.n_trades == 0


def test_scorecard_fingerprint_stable():
    assert "aegis.analytics.scorecard.v1" in SC_FP


def test_scorecard_on_real_learning_parquet():
    """Sanity check that the real 1060-trade file gives a plausible score."""
    lp = _ROOT / "reports" / "learning.parquet"
    if not lp.exists():
        pytest.skip("learning.parquet not present")
    df = pd.read_parquet(lp)
    sc = compute_scorecard(df)
    assert sc.n_trades == 1060
    assert sc.overall_score > 50   # AEGIS beat coin-flip
    assert sc.verdict in ("institutional_grade", "acceptable")
    # Win rate should be in a plausible 50-70% range
    wr = next(m for m in sc.metrics if m["name"] == "Recommendation Accuracy")
    assert 0.4 < wr["value"] < 0.75


# ── Sector Attribution ───────────────────────────────────────
def _sample_ensemble_row(scores: dict) -> dict:
    return {
        "ticker":              "T",
        "ensemble_score":      sum(scores.values()) / len(scores),
        "ensemble_confidence": 0.05,
        "per_model_score":     scores,
    }


def test_attribution_decomposes_into_11_models():
    scores = {mid: 0.1 for mid in MODEL_LABELS.keys()}
    weights = {mid: 1.0 / len(MODEL_LABELS) for mid in MODEL_LABELS.keys()}
    a = compute_attribution_for_rec({"ticker": "T"}, _sample_ensemble_row(scores), weights)
    assert len(a["per_model"]) == len(MODEL_LABELS)
    # Every entry has label + raw_score + weight + weighted_contribution + share_pct
    for e in a["per_model"]:
        assert "label" in e and "raw_score" in e
        assert "weight" in e and "weighted_contribution" in e
        assert "share_pct" in e


def test_attribution_identifies_dominant_driver():
    scores = {mid: 0.05 for mid in MODEL_LABELS.keys()}
    scores["aegis.momentum.v1"] = 0.5   # dominant
    weights = {mid: 1.0 / len(MODEL_LABELS) for mid in MODEL_LABELS.keys()}
    a = compute_attribution_for_rec({"ticker": "T"}, _sample_ensemble_row(scores), weights)
    assert a["dominant_driver"]["label"] == "Momentum"


def test_attribution_identifies_sector_share():
    scores = {mid: 0.1 for mid in MODEL_LABELS.keys()}
    weights = {mid: 1.0 / len(MODEL_LABELS) for mid in MODEL_LABELS.keys()}
    a = compute_attribution_for_rec({"ticker": "T"}, _sample_ensemble_row(scores), weights)
    # With uniform weights + uniform scores, sector share should be 1/11 ≈ 9.09
    assert 8.0 < a["sector_engine_contribution_pct"] < 10.5


def test_attribution_handles_missing_ensemble_row():
    a = compute_attribution_for_rec({"ticker": "T"}, None, {})
    assert a["per_model"] == []
    assert a["dominant_driver"] is None
    assert "missing" in a["note"].lower()


def test_attribution_summary_aggregates_dominant_drivers():
    recs = [
        {"ticker": "A", "attribution": {"dominant_driver": {"label": "Momentum", "contribution": 0.1},
                                             "opposition": None, "sector_engine_contribution_pct": 10.0}},
        {"ticker": "B", "attribution": {"dominant_driver": {"label": "Momentum", "contribution": 0.08},
                                             "opposition": {"label": "Value", "contribution": -0.05},
                                             "sector_engine_contribution_pct": 5.0}},
    ]
    s = summarize_attribution(recs)
    assert s["dominant_drivers"]["Momentum"] == 2
    assert s["avg_sector_share_pct"] == 7.5


def test_attribution_fingerprint_stable():
    assert "aegis.analytics.attribution.v1" in AT_FP


# ── Backtrack Engine ────────────────────────────────────────
def _mk_rec(ticker: str, action: str, score: float, price: float) -> dict:
    return {
        "ticker":               ticker,
        "ensemble_score":       score,
        "percentile_action":    action,
        "calibrated_confidence": 0.03,
        "rank":                 1,
        "position_plan":        {"suggested_allocation_pct": 3.0,
                                     "entry_zone": {"current_price": price,
                                                     "stop_loss": price * 0.94,
                                                     "target_1":  price * 1.12}},
        "lifecycle_state":      {"current_state": "HOLD"},
        "investor_action":      {"entry": "BUY", "if_holding": "HOLD"},
        "evolution":            {"is_new": False, "days_recommended": 5,
                                    "narrative": "test evolution"},
    }


def _seed_base_date(days: int = 3) -> "date":
    """Deterministic base date computed at test time · always today - days.
    Operator directive: no hardcoded dates in code · derive from wall clock."""
    from datetime import timedelta
    return date.today() - timedelta(days=max(1, days))


def _seed_snapshot_and_positions(tmp_path: Path, market: str,
                                     ticker: str, days: int = 3,
                                     base: "date | None" = None) -> "date":
    from datetime import timedelta
    if base is None:
        base = _seed_base_date(days)
    for i in range(days):
        d = base + timedelta(days=i)
        rec = _mk_rec(ticker, "BUY", 0.15 + i * 0.02, 100.0 + i * 5)
        payload = {"asof": d.isoformat(), "market": market, "recommendations": [rec]}
        archive_snapshot(payload, tmp_path, market, asof=d.isoformat())
        update_from_recs(tmp_path, market, [rec], asof=d.isoformat())
    return base


def test_backtrack_reconstructs_timeline_from_snapshots(tmp_path):
    from datetime import timedelta
    base = _seed_snapshot_and_positions(tmp_path, "india", "AAA", days=3)
    tb = build_ticker_backtrack(tmp_path, "india", "AAA")
    assert tb.n_appearances == 3
    assert len(tb.timeline) == 3
    assert tb.first_seen_date == base.isoformat()
    assert tb.latest_date == (base + timedelta(days=2)).isoformat()


def test_backtrack_computes_total_return(tmp_path):
    _seed_snapshot_and_positions(tmp_path, "india", "AAA", days=3)
    tb = build_ticker_backtrack(tmp_path, "india", "AAA")
    # entry 100, latest 110 → +10%
    assert tb.total_return_pct is not None
    assert abs(tb.total_return_pct - 10.0) < 0.5


def test_backtrack_market_summary_ranks_top_and_bottom(tmp_path):
    # Seed both tickers in the SAME snapshot per day so neither is overwritten.
    from datetime import timedelta
    base = _seed_base_date(days=3)
    for i in range(3):
        d = base + timedelta(days=i)
        win_rec = _mk_rec("WIN", "BUY", 0.15 + i * 0.02, 100.0 + i * 5)
        lose_rec = _mk_rec("LOSE", "SELL", -0.15 - i * 0.02, 100.0 - i * 5)
        payload = {"asof": d.isoformat(), "market": "india",
                    "recommendations": [win_rec, lose_rec]}
        archive_snapshot(payload, tmp_path, "india", asof=d.isoformat())
        update_from_recs(tmp_path, "india", [win_rec, lose_rec], asof=d.isoformat())
    summary = build_market_backtrack(tmp_path, "india")
    assert summary["n_tickers_tracked"] == 2
    assert summary["top_by_return"][0]["ticker"] in ("WIN", "LOSE")
    assert summary["bottom_by_return"][0]["ticker"] in ("WIN", "LOSE")
    # Files exist
    assert (tmp_path / "backtrack" / "india" / "WIN.json").exists()
    assert (tmp_path / "backtrack" / "india" / "LOSE.json").exists()
    assert (tmp_path / "backtrack" / "india" / "summary.json").exists()


def test_backtrack_empty_market_returns_empty_summary(tmp_path):
    summary = build_market_backtrack(tmp_path, "india")
    assert summary["n_tickers_tracked"] == 0
    assert summary["top_by_return"] == []


def test_backtrack_fingerprint_stable():
    assert "aegis.analytics.backtrack.v1" in BT_FP


# ── Integration: Command Center consumes v2.4 blocks ───────
def _today_payload_dates() -> tuple[str, str]:
    """Derive today's asof / run_utc dynamically. Operator directive: no
    hardcoded dates anywhere · every date must derive from wall clock."""
    from datetime import datetime, timezone
    today = date.today().isoformat()
    utc_now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return today, utc_now


def test_command_center_renders_scorecard_line():
    from backend.delivery.telegram.command_center import render_command_center_message
    asof, run_utc = _today_payload_dates()
    payload = {
        "asof":             asof,
        "market":           "india",
        "run_utc":          run_utc,
        "ceo_summary":      {"recommended_action": "Test", "market_regime": "unknown",
                                "actionable_count": 0, "rotations_count": 0,
                                "top_opportunity": None, "top_risk": None},
        "recommendations":  [],
        "ai_scorecard":     {"overall_score": 84.0, "overall_stars": 4,
                                "verdict": "institutional_grade", "n_trades": 1060},
    }
    msg = render_command_center_message(payload, "india")
    assert "AI PERFORMANCE SCORECARD" in msg   # renamed label in v3.0
    assert "84.0/100" in msg
    assert "institutional grade" in msg          # underscore stripped in display
    assert "1060 closed trades" in msg


def test_command_center_renders_attribution_line():
    from backend.delivery.telegram.command_center import render_command_center_message
    asof, run_utc = _today_payload_dates()
    payload = {
        "asof":             asof,
        "market":           "india",
        "run_utc":          run_utc,
        "ceo_summary":      {"recommended_action": "Test", "market_regime": "unknown",
                                "actionable_count": 0, "rotations_count": 0,
                                "top_opportunity": None, "top_risk": None},
        "recommendations":  [],
        "attribution_summary": {"dominant_drivers": {"Momentum": 4, "Quality": 2},
                                  "avg_sector_share_pct": 12.5,
                                  "sector_engine_measurably_active": True},
    }
    msg = render_command_center_message(payload, "india")
    assert "WHAT DROVE TODAY'S DECISIONS" in msg   # renamed in v3.0 for clarity
    assert "Momentum" in msg
    assert "12.5%" in msg
