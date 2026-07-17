"""DEV031 · edge extraction / relationship materialisation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


RELATION_TYPES = [
    "COMPANY_TO_INDUSTRY",
    "INDUSTRY_TO_SECTOR",
    "COMPANY_TO_PORTFOLIO",
    "PORTFOLIO_TO_STRATEGY",
    "RECOMMENDATION_TO_COMPANY",
    "RECOMMENDATION_TO_OUTCOME",
    "COMPANY_TO_COMPETITOR",
    "SECTOR_TO_REGIME",
    "SIGNAL_TO_RECOMMENDATION",
    "COMPANY_TO_THEME",
]


@dataclass
class Edge:
    src:            str
    dst:            str
    relation:       str
    weight:         float
    attributes:     dict


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


def _nid(entity_type: str, label: str) -> str:
    return f"{entity_type}:{str(label).strip()}"


# ── company → industry, industry → sector ────────────────────────────────
def edges_company_industry_sector(recs: list[dict]) -> list[Edge]:
    seen_ci, seen_is = set(), set()
    edges: list[Edge] = []
    for r in recs:
        t = str(r.get("ticker", "")).strip()
        ind = r.get("industry")
        sec = r.get("sector")
        if not t:
            continue
        if ind and (t, ind) not in seen_ci:
            edges.append(Edge(
                src=_nid("Company", t), dst=_nid("Industry", ind),
                relation="COMPANY_TO_INDUSTRY", weight=1.0, attributes={},
            ))
            seen_ci.add((t, ind))
        if ind and sec and (ind, sec) not in seen_is:
            edges.append(Edge(
                src=_nid("Industry", ind), dst=_nid("Sector", sec),
                relation="INDUSTRY_TO_SECTOR", weight=1.0, attributes={},
            ))
            seen_is.add((ind, sec))
    return edges


# ── company → portfolio, portfolio → strategy ────────────────────────────
def edges_company_portfolio() -> list[Edge]:
    df = _read_parquet("portfolio.parquet")
    if df.empty:
        return []
    edges = []
    for _, row in df.iterrows():
        label = f"{row['portfolio_type']}·{row['allocator']}"
        w = float(row.get("weight", 0.0) or 0.0)
        edges.append(Edge(
            src=_nid("Company", row["ticker"]),
            dst=_nid("Portfolio", label),
            relation="COMPANY_TO_PORTFOLIO",
            weight=round(w, 5),
            attributes={"weight_pct": round(w * 100, 3)},
        ))
    return edges


def edges_portfolio_strategy() -> list[Edge]:
    """Portfolio→Strategy edges via the DEV030 strategy_leaderboard.
    Each portfolio is linked to the champion strategy by default (weak edge)."""
    board = _read_json("challenger_scoreboard.json").get("leaderboard", []) or []
    if not board:
        return []
    df = _read_parquet("portfolio.parquet")
    if df.empty:
        return []
    champ = board[0].get("strategy") if board else None
    if not champ:
        return []
    edges = []
    for (ptype, allocator), _ in df.groupby(["portfolio_type", "allocator"]):
        edges.append(Edge(
            src=_nid("Portfolio", f"{ptype}·{allocator}"),
            dst=_nid("Strategy", champ),
            relation="PORTFOLIO_TO_STRATEGY",
            weight=0.5,
            attributes={"note": "champion default; refine per-portfolio backtest in future"},
        ))
    return edges


# ── recommendation → company, recommendation → outcome ───────────────────
def edges_recommendation_company(recs: list[dict]) -> list[Edge]:
    edges = []
    for r in recs:
        t = str(r.get("ticker", "")).strip()
        rtype = r.get("recommendation")
        if not t or not rtype:
            continue
        label = f"{t}·{rtype}"
        edges.append(Edge(
            src=_nid("Recommendation", label),
            dst=_nid("Company", t),
            relation="RECOMMENDATION_TO_COMPANY",
            weight=float(r.get("confidence", 0.5) or 0.5),
            attributes={"conviction_pct": r.get("conviction_pct")},
        ))
    return edges


def edges_recommendation_outcome() -> list[Edge]:
    """Recommendation -> Outcome via DEV025 learning.parquet.
    Outcome node ids are Signal:winner or Signal:loser + we aggregate per rec.
    For simplicity we materialise one Outcome node per (winner|loser) and
    connect only representative recommendations to keep the graph focused."""
    df = _read_parquet("learning.parquet")
    if df.empty:
        return []

    # Attach outcome to Recommendation nodes; skip if no matching rec node
    recs_json = _read_json("recommendations.json").get("recommendations", []) or []
    valid_rec_labels = set()
    for r in recs_json:
        t = r.get("ticker"); rt = r.get("recommendation")
        if t and rt:
            valid_rec_labels.add(f"{t}·{rt}")

    # Aggregate per ticker (learning has no rec-type column)
    if "ticker" not in df.columns or "is_winner" not in df.columns:
        return []
    grouped = df.groupby("ticker")["is_winner"].agg(["mean", "count"]).reset_index()

    edges = []
    for _, row in grouped.iterrows():
        t = row["ticker"]
        rate = float(row["mean"] or 0.0)
        n = int(row["count"] or 0)
        outcome = "winner" if rate >= 0.5 else "loser"
        # Match ANY rec_label with this ticker prefix
        matches = [lb for lb in valid_rec_labels if lb.startswith(f"{t}·")]
        for lb in matches:
            edges.append(Edge(
                src=_nid("Recommendation", lb),
                dst=_nid("Signal", outcome),
                relation="RECOMMENDATION_TO_OUTCOME",
                weight=round(rate, 4),
                attributes={"n_trades": n, "win_rate": round(rate, 4)},
            ))
    return edges


# ── company → competitor (same industry + top score similarity) ──────────
def edges_company_competitor(recs: list[dict], top_k: int = 3) -> list[Edge]:
    """For each company, list top-K peers in the same industry as competitors.
    Edge weight = inverse score gap normalised."""
    by_industry: dict[str, list[dict]] = {}
    for r in recs:
        ind = r.get("industry")
        if not ind:
            continue
        by_industry.setdefault(ind, []).append(r)

    edges = []
    for ind, members in by_industry.items():
        if len(members) < 2:
            continue
        scores = [(m.get("ticker"), float(m.get("score") or 0)) for m in members]
        for t, s in scores:
            peers = sorted([(t2, s2) for (t2, s2) in scores if t2 != t],
                              key=lambda ts: abs(ts[1] - s))[:top_k]
            for pt, ps in peers:
                gap = abs(s - ps)
                strength = 1.0 / (1.0 + gap)
                edges.append(Edge(
                    src=_nid("Company", t),
                    dst=_nid("Company", pt),
                    relation="COMPANY_TO_COMPETITOR",
                    weight=round(strength, 4),
                    attributes={"industry": ind, "score_gap": round(gap, 2)},
                ))
    return edges


# ── sector → regime ──────────────────────────────────────────────────────
def edges_sector_regime(recs: list[dict]) -> list[Edge]:
    """Weak informational edge: link every sector to the current regime.
    This lets queries surface 'which sectors are exposed to Risk-Off?'"""
    gc = _read_json("global_context.json") or {}
    classes = gc.get("classifications", {}) or {}
    posture = classes.get("global_posture")
    if isinstance(posture, dict):
        posture = posture.get("label")
    if not posture:
        # try champion output fallback
        champ = _read_json("champion_strategy.json") or {}
        cr = (champ.get("current_regime") or {}).get("global_posture")
        posture = cr if isinstance(cr, str) else (cr or {}).get("label") if isinstance(cr, dict) else None
    if not posture:
        return []
    sectors = set()
    for r in recs:
        s = r.get("sector")
        if s:
            sectors.add(s)
    return [Edge(
        src=_nid("Sector", s),
        dst=_nid("MarketRegime", posture),
        relation="SECTOR_TO_REGIME",
        weight=1.0,
        attributes={"context": "current"},
    ) for s in sectors]


# ── signal → recommendation (strategy_doctor findings) ───────────────────
def edges_signal_recommendation() -> list[Edge]:
    doctor = _read_json("strategy_doctor.json") or {}
    diagnoses = doctor.get("diagnoses", []) or []
    recs_json = _read_json("recommendations.json").get("recommendations", []) or []
    rec_labels_by_ticker: dict[str, list[str]] = {}
    for r in recs_json:
        t = r.get("ticker"); rt = r.get("recommendation")
        if t and rt:
            rec_labels_by_ticker.setdefault(t, []).append(f"{t}·{rt}")

    edges = []
    for d in diagnoses:
        cat = str(d.get("category", "")).strip()
        t = str(d.get("ticker", "")).strip()
        if not cat or not t:
            continue
        for lb in rec_labels_by_ticker.get(t, []):
            edges.append(Edge(
                src=_nid("Signal", cat),
                dst=_nid("Recommendation", lb),
                relation="SIGNAL_TO_RECOMMENDATION",
                weight=0.5,
                attributes={"diagnosis_detail": d.get("detail", "")[:200]},
            ))
    return edges


# ── company → market theme (weak, current-context) ───────────────────────
def edges_company_theme(recs: list[dict]) -> list[Edge]:
    gc = _read_json("global_context.json") or {}
    classes = gc.get("classifications", {}) or {}
    theme_ids = []
    for k, v in classes.items():
        label = f"{k}={v['label'] if isinstance(v, dict) else v}"
        theme_ids.append(_nid("MarketTheme", label))
    edges = []
    if not theme_ids:
        return edges
    # Only link the top-K by score to themes to keep the graph tractable
    top = sorted(recs, key=lambda r: -float(r.get("composite_decision_score") or 0))[:20]
    for r in top:
        t = str(r.get("ticker", "")).strip()
        if not t:
            continue
        for theme_id in theme_ids:
            edges.append(Edge(
                src=_nid("Company", t),
                dst=theme_id,
                relation="COMPANY_TO_THEME",
                weight=0.3,
                attributes={"note": "current-context exposure (top-20 by decision score)"},
            ))
    return edges


# ── aggregate ─────────────────────────────────────────────────────────────
def build_all_edges() -> list[Edge]:
    recs = _read_json("recommendations.json").get("recommendations", []) or []
    return (
        edges_company_industry_sector(recs)
        + edges_company_portfolio()
        + edges_portfolio_strategy()
        + edges_recommendation_company(recs)
        + edges_recommendation_outcome()
        + edges_company_competitor(recs)
        + edges_sector_regime(recs)
        + edges_signal_recommendation()
        + edges_company_theme(recs)
    )
