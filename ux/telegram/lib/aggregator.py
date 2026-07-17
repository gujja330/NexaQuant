"""UX030 · aggregate DEV017-DEV030 outputs into a single context object.

The aggregator reads from `reports/` at runtime and produces a tenant-generic
`Context` object that the renderer + commands consume. No hardcoded tickers or
sectors — everything is pulled from the live outputs of the earlier DEVs."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


def _read_json(name: str) -> dict:
    p = REPORTS / name
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _read_parquet(name: str) -> pd.DataFrame:
    p = REPORTS / name
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


@dataclass
class Context:
    run_utc:                str = ""
    global_context:         dict = field(default_factory=dict)
    recommendations:        dict = field(default_factory=dict)
    portfolio:              dict = field(default_factory=dict)
    monitoring:             dict = field(default_factory=dict)
    learning:               dict = field(default_factory=dict)
    strategy_doctor:        dict = field(default_factory=dict)
    calibration:            dict = field(default_factory=dict)
    champion:               dict = field(default_factory=dict)
    challenger_scoreboard:  dict = field(default_factory=dict)
    regime_comparison:      dict = field(default_factory=dict)
    promotion:              dict = field(default_factory=dict)
    drift:                  dict = field(default_factory=dict)


def load_context() -> Context:
    return Context(
        run_utc = pd.Timestamp.now(tz="UTC").isoformat(),
        global_context =         _read_json("global_context.json"),
        recommendations =        _read_json("recommendations.json"),
        portfolio =              _read_json("portfolio.json"),
        monitoring =             _read_json("portfolio_monitoring.json"),
        learning =               _read_json("learning_summary.json"),
        strategy_doctor =        _read_json("strategy_doctor.json"),
        calibration =            _read_json("confidence_calibration.json"),
        champion =               _read_json("champion_strategy.json"),
        challenger_scoreboard =  _read_json("challenger_scoreboard.json"),
        regime_comparison =      _read_json("regime_comparison.json"),
        promotion =              _read_json("promotion_recommendation.json"),
        drift =                  _read_json("drift_report.json"),
    )


# ── shape helpers used by renderer/commands ──────────────────────────────
def top_buys(ctx: Context, n: int = 5) -> list[dict]:
    recs = ctx.recommendations.get("recommendations", []) or []
    buys = [r for r in recs if r.get("recommendation") in ("Strong-Buy", "Buy", "Accumulate")]
    buys.sort(key=lambda r: (
        -float(r.get("composite_decision_score") or 0),
        -float(r.get("conviction_pct") or 0),
    ))
    return buys[:n]


def exits(ctx: Context, n: int = 20) -> list[dict]:
    recs = ctx.recommendations.get("recommendations", []) or []
    outs = [r for r in recs if r.get("recommendation") in ("Sell", "Reduce")
                                 and r.get("currently_held")]
    return outs[:n]


def current_holdings(ctx: Context) -> list[dict]:
    recs = ctx.recommendations.get("recommendations", []) or []
    return [r for r in recs if r.get("currently_held")]


def portfolio_summary(ctx: Context) -> dict:
    portfolios = ctx.portfolio.get("portfolios", []) or []
    # pick the balanced/hrp portfolio as the default reference if present
    ref = None
    for p in portfolios:
        if p.get("portfolio_type") == "balanced" and p.get("allocator") == "hrp":
            ref = p; break
    if ref is None and portfolios:
        ref = portfolios[0]
    if ref is None:
        return {"n_positions": 0, "cash_allocation_pct": 0.0, "top5_share": 0.0}
    positions = ref.get("positions", []) or []
    positions_sorted = sorted(positions, key=lambda x: -float(x.get("weight") or 0.0))
    top5 = sum(float(p.get("weight") or 0.0) for p in positions_sorted[:5])
    return {
        "portfolio_type":       ref.get("portfolio_display", ref.get("portfolio_type", "n/a")),
        "allocator":            ref.get("allocator", "n/a"),
        "n_positions":          int(ref.get("n_positions", len(positions))),
        "cash_allocation_pct":  float(ref.get("cash_allocation_pct", 0.0)),
        "top5_share":           round(top5, 4),
    }


def champion_summary(ctx: Context) -> dict:
    champ = ctx.champion.get("champion", {}) or {}
    return {
        "strategy":        champ.get("strategy", "unknown"),
        "composite_score": champ.get("composite_score"),
        "sharpe":          champ.get("sharpe"),
        "cagr":            champ.get("cagr"),
        "max_dd_pct":      champ.get("max_dd_pct"),
        "win_rate":        champ.get("win_rate"),
    }


def regime_label(ctx: Context) -> str:
    gc = ctx.global_context.get("classifications", {}) or {}
    posture = gc.get("global_posture")
    if isinstance(posture, dict):
        return str(posture.get("label", "Unknown"))
    if isinstance(posture, str):
        return posture
    # fallback: champion output stores it too
    cr = ctx.champion.get("current_regime", {}) or {}
    p2 = cr.get("global_posture")
    if isinstance(p2, dict):
        return str(p2.get("label", "Unknown"))
    if isinstance(p2, str):
        return p2
    return "Unknown"


def calibration_note(ctx: Context) -> dict:
    c = ctx.calibration or {}
    return {
        "best_method":  c.get("best_method"),
        "raw_ece":      (c.get("raw_metrics") or {}).get("ece"),
        "cal_ece":      (c.get("calibrated_metrics") or {}).get("ece"),
        "governance":   c.get("governance"),
    }
