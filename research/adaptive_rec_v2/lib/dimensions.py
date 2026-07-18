"""Adaptive Rec Engine v2.1 · dimension scorers.

Ten dimensions of investment intelligence, one per source engine.
Each scorer reads its engine's published artifacts and returns a
score in [0, 100] per ticker plus an explanation string.

Every scorer is deterministic — same artifacts in, same score out.
Every scorer degrades gracefully when its source is absent:
returns None (never a fabricated score)."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


@dataclass
class DimensionScore:
    name:        str
    score:       float | None    # [0, 100] or None if source unavailable
    explanation: str
    source:      str             # which reports/*.json produced it
    weight_hint: float           # default weight; caller may override


# ────────────────────────────────────────────────────────────────
# LOADERS
# ────────────────────────────────────────────────────────────────
def _read_json(name: str):
    p = REPORTS / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_parquet(name: str) -> pd.DataFrame:
    p = REPORTS / name
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(x)))


# ────────────────────────────────────────────────────────────────
# 1. RESEARCH STRENGTH — Company + Industry + Sector + Global rollup
# ────────────────────────────────────────────────────────────────
def score_research(rec: dict) -> DimensionScore:
    company     = rec.get("score")
    industry    = rec.get("industry_score")
    sector      = rec.get("sector_score")
    global_s    = rec.get("global_score")

    parts = [(w, s) for w, s in [(0.4, company), (0.25, industry),
                                     (0.20, sector), (0.15, global_s)]
                if s is not None]
    if not parts:
        return DimensionScore("research", None,
                                "no research scores available", "recommendations.json", 0.15)
    total_w = sum(w for w, _ in parts)
    weighted = sum(w * float(s) for w, s in parts) / total_w
    score = _clamp(weighted)

    return DimensionScore(
        "research", round(score, 2),
        f"company {company} · industry {industry} · sector {sector} · global {global_s}"
        f" -> weighted {score:.1f}",
        "recommendations.json (rollup DEV017-DEV020)",
        0.15,
    )


# ────────────────────────────────────────────────────────────────
# 2. HISTORICAL STRENGTH — DEV025 learning.parquet per ticker
# ────────────────────────────────────────────────────────────────
def score_historical(rec: dict, learning: pd.DataFrame | None = None) -> DimensionScore:
    ticker = str(rec.get("ticker", ""))
    if learning is None:
        learning = _read_parquet("learning.parquet")
    if learning.empty or ticker not in learning["ticker"].astype(str).values:
        return DimensionScore("historical", None,
                                "no historical trades on file for this ticker",
                                "learning.parquet (DEV025)", 0.10)

    hist = learning[learning["ticker"].astype(str) == ticker]
    n_trades = int(len(hist))
    win_rate = float(hist["is_winner"].mean()) if n_trades else 0.5
    avg_return = float(hist["return_pct"].mean()) if n_trades else 0.0

    # Score combines win-rate lift over 0.5 base + expectancy signal + sample size
    win_component = _clamp((win_rate - 0.5) * 200 + 50, 0, 100)   # 0.5 -> 50, 1.0 -> 150 clamped 100
    exp_component = _clamp(50 + avg_return * 500, 0, 100)          # +10% -> 100, -10% -> 0
    # Sample-size confidence multiplier: 5 trades -> 0.5, 30+ -> 1.0
    sample_conf = min(1.0, n_trades / 30.0)
    raw = (0.6 * win_component + 0.4 * exp_component)
    # If sample too thin, bias toward neutral 50
    score = _clamp(sample_conf * raw + (1 - sample_conf) * 50, 0, 100)

    return DimensionScore(
        "historical", round(score, 2),
        f"n_trades={n_trades} · win_rate={win_rate:.3f} · avg_return={avg_return:.4f}"
        f" · sample_confidence={sample_conf:.2f} -> {score:.1f}",
        "learning.parquet (DEV025)", 0.15,
    )


# ────────────────────────────────────────────────────────────────
# 3. VALIDATION STRENGTH — Validation Engine v2.0 paper harness
# ────────────────────────────────────────────────────────────────
def score_validation(rec: dict, validation: dict | None = None) -> DimensionScore:
    if validation is None:
        validation = _read_json("validation_v2_latest.json")
    if not validation:
        return DimensionScore("validation", None,
                                "no validation harness output — Validation v2.0 not yet running",
                                "validation_v2_latest.json", 0.10)

    reconciliation = validation.get("reconciliation") or {}
    drift = validation.get("metric_drift") or {}
    n_reconciled = int(reconciliation.get("n") or 0)
    within_tol = reconciliation.get("within_5pp_tolerance")
    drift_flag = drift.get("flag") or "insufficient_evidence"

    # If reconciliation is not yet meaningful, defer to a neutral 50 with note
    if n_reconciled < 5:
        return DimensionScore(
            "validation", 55.0,
            f"only {n_reconciled} reconciled trades so far · drift={drift_flag}"
            f" · giving neutral bias 55 pending more evidence",
            "validation_v2_latest.json (v2.0)", 0.10,
        )

    # Reconciliation quality
    within_score = 80 if within_tol else 40
    drift_score = {"stable": 80, "improving": 90, "degrading": 30,
                     "insufficient_evidence": 55}.get(drift_flag, 55)
    score = _clamp(0.6 * within_score + 0.4 * drift_score, 0, 100)

    return DimensionScore(
        "validation", round(score, 2),
        f"n_reconciled={n_reconciled} · within_tolerance={within_tol}"
        f" · drift={drift_flag} -> {score:.1f}",
        "validation_v2_latest.json (v2.0)", 0.10,
    )


# ────────────────────────────────────────────────────────────────
# 4. RISK STRENGTH — Risk & Capital v2.0 sizing verdict
# ────────────────────────────────────────────────────────────────
def score_risk(rec: dict, risk_latest: dict | None = None) -> DimensionScore:
    if risk_latest is None:
        risk_latest = _read_json("risk_capital_v2_latest.json")
    if not risk_latest:
        return DimensionScore("risk", None,
                                "no Risk & Capital v2.0 output",
                                "risk_capital_v2_latest.json", 0.10)

    ticker = str(rec.get("ticker", ""))
    sizing_rows = risk_latest.get("sizing", []) or []
    match = next((r for r in sizing_rows if r.get("ticker") == ticker), None)

    if match is None:
        # Not in top-K sized universe — infer from portfolio verdict
        pr = risk_latest.get("portfolio_risk") or {}
        v = pr.get("verdict")
        default = {"PASS": 55, "WARNING": 40, "BLOCK": 20}.get(v, 45)
        return DimensionScore(
            "risk", default,
            f"ticker not in top-K sized universe · portfolio verdict={v}"
            f" -> default {default}",
            "risk_capital_v2_latest.json (v2.0)", 0.10,
        )

    verdict = match.get("verdict") or "PASS"
    target = float(match.get("target_weight") or 0.05)

    # Verdict maps to base score
    verdict_score = {"PASS": 80, "WARNING": 50, "BLOCK": 15}.get(verdict, 50)
    # Small targets (near floor) mean the risk system says "don't push it here"
    size_score = _clamp((target / 0.10) * 100, 20, 100)   # 10% -> 100, 1% -> 20
    score = _clamp(0.7 * verdict_score + 0.3 * size_score, 0, 100)

    return DimensionScore(
        "risk", round(score, 2),
        f"sizing verdict={verdict} · target={target*100:.2f}% -> {score:.1f}",
        "risk_capital_v2_latest.json (v2.0)", 0.15,
    )


# ────────────────────────────────────────────────────────────────
# 5. PORTFOLIO FIT — DEV022 portfolio inclusion count
# ────────────────────────────────────────────────────────────────
def score_portfolio_fit(rec: dict) -> DimensionScore:
    in_ports = rec.get("in_target_portfolios") or []
    if isinstance(in_ports, list):
        n = len(in_ports)
    elif isinstance(in_ports, int):
        n = in_ports
    else:
        n = 0

    # 99 portfolio constructions available; score = share
    score = _clamp((n / 99.0) * 100 + 30 * (1 if n >= 5 else 0), 0, 100)
    return DimensionScore(
        "portfolio_fit", round(score, 2),
        f"included in {n} of 99 portfolio constructions -> {score:.1f}",
        "recommendations.json (DEV022 rollup)", 0.10,
    )


# ────────────────────────────────────────────────────────────────
# 6. KNOWLEDGE GRAPH STRENGTH — DEV031 top influencers + centrality
# ────────────────────────────────────────────────────────────────
def score_knowledge_graph(rec: dict, entity_network: dict | None = None) -> DimensionScore:
    if entity_network is None:
        entity_network = _read_json("entity_network.json")
    if not entity_network:
        return DimensionScore("knowledge_graph", None,
                                "no entity_network.json — DEV031 not run",
                                "entity_network.json", 0.05)

    ticker = str(rec.get("ticker", ""))
    node_id = f"Company:{ticker}"
    match = next((n for n in (entity_network.get("nodes") or [])
                    if n.get("id") == node_id), None)
    if match is None:
        return DimensionScore("knowledge_graph", 40.0,
                                f"{ticker} not in the graph — orphan",
                                "entity_network.json (DEV031)", 0.05)

    influence = float(match.get("influence") or 0.0)
    degree_c  = float(match.get("degree_centrality") or 0.0)

    # Influence scores span roughly 0.001 - 0.05 in live data.
    # Normalise to 0-100 via a soft scale.
    infl_score = _clamp(np.tanh(influence * 200) * 100, 0, 100)
    deg_score  = _clamp(degree_c * 300 + 40, 0, 100)

    score = _clamp(0.7 * infl_score + 0.3 * deg_score, 0, 100)
    return DimensionScore(
        "knowledge_graph", round(score, 2),
        f"influence={influence:.4f} · degree_centrality={degree_c:.4f}"
        f" -> {score:.1f}",
        "entity_network.json (DEV031-B)", 0.05,
    )


# ────────────────────────────────────────────────────────────────
# 7. DNA STRENGTH — v1.5 pattern prior
# ────────────────────────────────────────────────────────────────
def score_dna(rec: dict, dna_feedback: dict | None = None) -> DimensionScore:
    if dna_feedback is None:
        dna_feedback = _read_json("recommendation_dna_feedback.json")
    if not dna_feedback:
        return DimensionScore("dna", None,
                                "no DNA feedback — v1.5 not yet run",
                                "recommendation_dna_feedback.json", 0.10)

    ticker = str(rec.get("ticker", ""))
    priors = dna_feedback.get("priors_all") or []
    match = next((p for p in priors if p.get("ticker") == ticker), None)

    if match is None or not match.get("hist_evidence"):
        return DimensionScore("dna", 50.0,
                                f"no historical DNA pattern for {ticker} — neutral",
                                "recommendation_dna_feedback.json (v1.5)", 0.10)

    prior_wr = float(match.get("prior_win_rate") or 0.5)
    prior_exp = float(match.get("prior_expectancy") or 0.0)
    n_hist = int(match.get("n_historical") or 0)

    win_component = _clamp((prior_wr - 0.5) * 200 + 50, 0, 100)
    exp_component = _clamp(50 + prior_exp * 500, 0, 100)
    sample_conf = min(1.0, n_hist / 20.0)
    raw = 0.6 * win_component + 0.4 * exp_component
    score = _clamp(sample_conf * raw + (1 - sample_conf) * 50, 0, 100)

    return DimensionScore(
        "dna", round(score, 2),
        f"pattern win_rate={prior_wr:.3f} · expectancy={prior_exp:.4f}"
        f" · n_hist={n_hist} -> {score:.1f}",
        "recommendation_dna_feedback.json (v1.5)", 0.10,
    )


# ────────────────────────────────────────────────────────────────
# 8. CALIBRATION STRENGTH — DEV029 ECE improvement
# ────────────────────────────────────────────────────────────────
def score_calibration(rec: dict, calibration: dict | None = None) -> DimensionScore:
    if calibration is None:
        calibration = _read_json("confidence_calibration.json")
    if not calibration:
        return DimensionScore("calibration", None,
                                "no confidence_calibration.json — DEV029 not run",
                                "confidence_calibration.json", 0.05)

    raw = (calibration.get("raw_metrics") or {}).get("ece")
    cal = (calibration.get("calibrated_metrics") or {}).get("ece")
    if raw is None or cal is None:
        return DimensionScore("calibration", 50.0,
                                "calibration metrics incomplete", "confidence_calibration.json", 0.05)

    # Score reflects trust in the confidence machinery, not per-ticker.
    # Small ECE = high trust in the calibration system.
    trust = _clamp(100 - float(cal) * 500, 20, 100)   # cal=0.002 -> 99, cal=0.05 -> 75, cal=0.20 -> 0
    # Small penalty if raw was very miscalibrated (indicates the underlying
    # signal was noise) — signals that calibration is a correction, not a real signal.
    raw_penalty = _clamp(float(raw) * 100, 0, 30)
    score = _clamp(trust - raw_penalty, 0, 100)

    return DimensionScore(
        "calibration", round(score, 2),
        f"raw_ece={raw:.4f} · cal_ece={cal:.4f} · trust={trust:.1f} · raw_penalty={raw_penalty:.1f}"
        f" -> {score:.1f}",
        "confidence_calibration.json (DEV029)", 0.05,
    )


# ────────────────────────────────────────────────────────────────
# 9. LEARNING STRENGTH — DEV025 learning corpus coverage
# ────────────────────────────────────────────────────────────────
def score_learning(rec: dict, learning: pd.DataFrame | None = None) -> DimensionScore:
    if learning is None:
        learning = _read_parquet("learning.parquet")
    if learning.empty:
        return DimensionScore("learning", None,
                                "learning.parquet missing", "learning.parquet", 0.05)

    ticker = str(rec.get("ticker", ""))
    sector = rec.get("sector")
    industry = rec.get("industry")

    # Coverage = how much data we have on similar trades (same sector / industry)
    same_ticker = int((learning["ticker"].astype(str) == ticker).sum())
    same_sector = int((learning["sector"].astype(str) == str(sector)).sum()) if sector else 0
    same_industry = int((learning["industry"].astype(str) == str(industry)).sum()) if industry else 0

    # 0 -> 0, 20+ -> 100, sigmoid-like curve on total
    total_evidence = same_ticker * 5 + same_sector + same_industry
    score = _clamp(np.tanh(total_evidence / 30) * 100, 0, 100)

    return DimensionScore(
        "learning", round(score, 2),
        f"same_ticker={same_ticker} · same_industry={same_industry}"
        f" · same_sector={same_sector} -> {score:.1f}",
        "learning.parquet (DEV025)", 0.05,
    )


# ────────────────────────────────────────────────────────────────
# 10. EXPLAINABILITY STRENGTH — DEV031-B recommendation_paths
# ────────────────────────────────────────────────────────────────
def score_explainability(rec: dict, rec_paths: dict | None = None) -> DimensionScore:
    if rec_paths is None:
        rec_paths = _read_json("recommendation_paths.json")
    if not rec_paths:
        return DimensionScore("explainability", None,
                                "no recommendation_paths.json — DEV031-B not run",
                                "recommendation_paths.json", 0.05)

    ticker = str(rec.get("ticker", ""))
    paths = rec_paths.get("paths") or []
    match = next((p for p in paths if p.get("ticker") == ticker), None)
    if match is None or not match.get("found"):
        return DimensionScore("explainability", 40.0,
                                f"no evidence path for {ticker}",
                                "recommendation_paths.json (DEV031-B)", 0.05)

    # Full path = 4 nodes (Company, Industry, Sector, MarketRegime)
    # Champion linked = +20
    # Outcome linked = +10
    # Signals >=3 = +10
    path_len = len(match.get("primary_path") or [])
    has_champion = bool(match.get("champion"))
    has_outcome = bool(match.get("outcome"))
    n_signals = len(match.get("signals") or [])

    score = 0.0
    score += (path_len / 4) * 60
    if has_champion: score += 20
    if has_outcome: score += 10
    if n_signals >= 3: score += 10
    score = _clamp(score, 0, 100)

    return DimensionScore(
        "explainability", round(score, 2),
        f"path_len={path_len}/4 · champion={has_champion} · outcome={has_outcome}"
        f" · signals={n_signals} -> {score:.1f}",
        "recommendation_paths.json (DEV031-B)", 0.05,
    )


# ────────────────────────────────────────────────────────────────
# BATCH SCORER
# ────────────────────────────────────────────────────────────────
def score_all_dimensions(rec: dict, ctx: dict | None = None) -> list[DimensionScore]:
    """Compute all 10 dimensions for a single recommendation.

    ctx (optional pre-loaded artifacts) enables efficient batch use:
      {'learning': DataFrame, 'validation': dict, 'risk': dict,
       'entity_network': dict, 'dna_feedback': dict, 'calibration': dict,
       'rec_paths': dict}"""
    ctx = ctx or {}
    return [
        score_research(rec),
        score_historical(rec, ctx.get("learning")),
        score_validation(rec, ctx.get("validation")),
        score_risk(rec, ctx.get("risk")),
        score_portfolio_fit(rec),
        score_knowledge_graph(rec, ctx.get("entity_network")),
        score_dna(rec, ctx.get("dna_feedback")),
        score_calibration(rec, ctx.get("calibration")),
        score_learning(rec, ctx.get("learning")),
        score_explainability(rec, ctx.get("rec_paths")),
    ]


def dimensions_to_dict(dims: list[DimensionScore]) -> list[dict]:
    return [asdict(d) for d in dims]
