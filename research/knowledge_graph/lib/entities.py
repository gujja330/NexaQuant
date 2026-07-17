"""DEV031 · entity extraction from validated AEGIS outputs.

Every entity in the knowledge graph is materialized from a `reports/`
artifact produced by an earlier DEV. No internet scraping. No hardcoded
tenant-specific data."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


ENTITY_TYPES = [
    "Company",
    "Industry",
    "Sector",
    "MarketTheme",
    "Strategy",
    "Recommendation",
    "Portfolio",
    "Signal",
    "RiskFactor",
    "MarketRegime",
]


@dataclass
class Node:
    id:            str                  # canonical, unique
    entity_type:   str
    label:         str
    attributes:    dict


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


def _node_id(entity_type: str, label: str) -> str:
    return f"{entity_type}:{str(label).strip()}"


# ── Companies (from DEV023 recommendations — one row per company) ────────
def extract_companies() -> list[Node]:
    recs = _read_json("recommendations.json").get("recommendations", []) or []
    seen = {}
    for r in recs:
        t = str(r.get("ticker", "")).strip()
        if not t or t in seen:
            continue
        seen[t] = Node(
            id           = _node_id("Company", t),
            entity_type  = "Company",
            label        = t,
            attributes   = {
                "sector":                 r.get("sector"),
                "industry":               r.get("industry"),
                "score":                  r.get("score"),
                "classification":         r.get("classification"),
                "composite_decision_score": r.get("composite_decision_score"),
                "conviction_pct":         r.get("conviction_pct"),
                "confidence":             r.get("confidence"),
                "recommendation":         r.get("recommendation"),
                "overall_rank":           r.get("overall_rank"),
                "sector_rank":            r.get("sector_rank"),
                "industry_rank":          r.get("industry_rank"),
                "currently_held":         r.get("currently_held"),
                "current_weight":         r.get("current_weight"),
            },
        )
    return list(seen.values())


# ── Industries + Sectors (from DEV023 recommendations + DEV018/019 rollups) ─
def extract_industries_and_sectors(companies: list[Node]) -> tuple[list[Node], list[Node]]:
    sector_stats = _read_json("sector_intelligence.json") or {}
    industry_stats = _read_json("industry_intelligence.json") or {}

    industries = {}
    sectors = {}
    for c in companies:
        ind = c.attributes.get("industry")
        sec = c.attributes.get("sector")
        if ind and ind not in industries:
            industries[ind] = Node(
                id           = _node_id("Industry", ind),
                entity_type  = "Industry",
                label        = ind,
                attributes   = _lookup_stats(industry_stats, "industries", ind),
            )
        if sec and sec not in sectors:
            sectors[sec] = Node(
                id           = _node_id("Sector", sec),
                entity_type  = "Sector",
                label        = sec,
                attributes   = _lookup_stats(sector_stats, "sectors", sec),
            )
    return list(industries.values()), list(sectors.values())


def _lookup_stats(bundle: dict, container_key: str, name: str) -> dict:
    if not bundle:
        return {"name": name}
    items = bundle.get(container_key, []) or bundle.get(container_key.rstrip("s") + "_scores", []) or []
    if isinstance(items, dict):
        return {"name": name, **{k: v for k, v in items.get(name, {}).items()
                                    if not isinstance(v, (list, dict))}}
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and (str(it.get("name", "")) == name or
                                              str(it.get("industry", "")) == name or
                                              str(it.get("sector", "")) == name):
                return {"name": name, **{k: v for k, v in it.items()
                                              if not isinstance(v, (list, dict))}}
    return {"name": name}


# ── Portfolios (from DEV022 portfolio.parquet) ────────────────────────────
def extract_portfolios() -> list[Node]:
    df = _read_parquet("portfolio.parquet")
    if df.empty:
        return []
    if "portfolio_type" not in df.columns or "allocator" not in df.columns:
        return []
    grouped = df.groupby(["portfolio_type", "allocator"])
    nodes = []
    for (ptype, allocator), g in grouped:
        label = f"{ptype}·{allocator}"
        nodes.append(Node(
            id           = _node_id("Portfolio", label),
            entity_type  = "Portfolio",
            label        = label,
            attributes   = {
                "portfolio_type": ptype,
                "allocator":      allocator,
                "n_positions":    int(g["ticker"].nunique()),
                "n_sectors":      int(g["sector"].nunique()),
                "n_industries":   int(g["industry"].nunique()),
                "avg_score":      float(g["score"].mean()),
                "avg_confidence": float(g["confidence"].mean()),
            },
        ))
    return nodes


# ── Strategies (from DEV030 challenger_scoreboard) ───────────────────────
def extract_strategies() -> list[Node]:
    board = _read_json("challenger_scoreboard.json").get("leaderboard", []) or []
    nodes = []
    for row in board:
        label = str(row.get("strategy", "")).strip()
        if not label:
            continue
        nodes.append(Node(
            id           = _node_id("Strategy", label),
            entity_type  = "Strategy",
            label        = label,
            attributes   = {
                "rank":            row.get("rank"),
                "composite_score": row.get("composite_score"),
                "sharpe":          row.get("sharpe"),
                "sortino":         row.get("sortino"),
                "calmar":          row.get("calmar"),
                "cagr":            row.get("cagr"),
                "max_dd_pct":      row.get("max_dd_pct"),
                "win_rate":        row.get("win_rate"),
                "info_ratio":      row.get("info_ratio"),
            },
        ))
    return nodes


# ── Recommendations (one node per rec_id or ticker+rec type) ──────────────
def extract_recommendations() -> list[Node]:
    recs = _read_json("recommendations.json").get("recommendations", []) or []
    nodes = []
    for r in recs:
        rec_type = r.get("recommendation")
        ticker = r.get("ticker")
        if not rec_type or not ticker:
            continue
        label = f"{ticker}·{rec_type}"
        nodes.append(Node(
            id           = _node_id("Recommendation", label),
            entity_type  = "Recommendation",
            label        = label,
            attributes   = {
                "ticker":                    ticker,
                "recommendation":            rec_type,
                "action":                    r.get("action"),
                "composite_decision_score":  r.get("composite_decision_score"),
                "conviction_pct":            r.get("conviction_pct"),
                "confidence":                r.get("confidence"),
            },
        ))
    return nodes


# ── Signals (from DEV027 strategy_doctor diagnoses + DEV025 dims) ─────────
def extract_signals() -> list[Node]:
    doctor = _read_json("strategy_doctor.json") or {}
    diagnoses = doctor.get("diagnoses", []) or []
    seen = {}
    for d in diagnoses:
        cat = str(d.get("category", "")).strip()
        if not cat or cat in seen:
            continue
        seen[cat] = Node(
            id           = _node_id("Signal", cat),
            entity_type  = "Signal",
            label        = cat,
            attributes   = {
                "n_occurrences": sum(1 for x in diagnoses if x.get("category") == cat),
                "source":        "strategy_doctor",
            },
        )
    # add DEV025 learning dimensions as signal nodes
    for dim in ["momentum", "trend", "rs_nifty", "volatility", "drawdown", "position_52w"]:
        key = f"dim_{dim}"
        if key not in seen:
            seen[key] = Node(
                id           = _node_id("Signal", key),
                entity_type  = "Signal",
                label        = key,
                attributes   = {"source": "adaptive_learning"},
            )
    return list(seen.values())


# ── Market Regimes (from DEV030 regime_comparison) ────────────────────────
def extract_regimes() -> list[Node]:
    rc = _read_json("regime_comparison.json").get("regime_report", {}) or {}
    windows = rc.get("regime_windows", {}) or {}
    champs  = rc.get("regime_champions", {}) or {}
    nodes = []
    for label in ["Risk-On", "Neutral", "Risk-Off"]:
        nodes.append(Node(
            id           = _node_id("MarketRegime", label),
            entity_type  = "MarketRegime",
            label        = label,
            attributes   = {
                "n_days":            int(windows.get(label, 0)),
                "regime_champion":   (champs.get(label) or {}).get("strategy"),
                "champion_cagr":     (champs.get(label) or {}).get("cagr"),
            },
        ))
    return nodes


# ── Risk factors (from DEV024 portfolio_monitoring) ───────────────────────
def extract_risk_factors() -> list[Node]:
    mon = _read_json("portfolio_monitoring.json") or {}
    alerts = mon.get("alerts", []) or []
    seen = {}
    for a in alerts:
        kind = str(a.get("type", "")).strip()
        if not kind or kind in seen:
            continue
        seen[kind] = Node(
            id           = _node_id("RiskFactor", kind),
            entity_type  = "RiskFactor",
            label        = kind,
            attributes   = {"n_alerts": sum(1 for x in alerts if x.get("type") == kind)},
        )
    return list(seen.values())


# ── Market themes (derived from global_context) ──────────────────────────
def extract_market_themes() -> list[Node]:
    gc = _read_json("global_context.json") or {}
    classes = gc.get("classifications", {}) or {}
    nodes = []
    for k, v in classes.items():
        label = f"{k}={v['label'] if isinstance(v, dict) else v}"
        nodes.append(Node(
            id           = _node_id("MarketTheme", label),
            entity_type  = "MarketTheme",
            label        = label,
            attributes   = {"axis": k, "value": (v if not isinstance(v, dict) else v.get("label"))},
        ))
    return nodes


# ── Aggregate: build all entities ────────────────────────────────────────
def extract_all() -> list[Node]:
    companies = extract_companies()
    industries, sectors = extract_industries_and_sectors(companies)
    portfolios = extract_portfolios()
    strategies = extract_strategies()
    recs = extract_recommendations()
    signals = extract_signals()
    regimes = extract_regimes()
    risks = extract_risk_factors()
    themes = extract_market_themes()
    return companies + industries + sectors + portfolios + strategies + recs + signals + regimes + risks + themes
