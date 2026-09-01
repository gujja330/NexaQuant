"""Candidate research layer registry.

Discovery-based · new layers are added by extending `LayerRegistry.register()`,
not by editing an enum. Each layer declares:

    · key          · short kebab-case
    · title        · human label
    · category     · A..H per README (or new)
    · data_dep     · list of data-source keys the layer needs
    · rationale    · why this layer is worth measuring
    · walk_forward · required WF acceptance criterion

The registry is IMMUTABLE at runtime after first import. A layer is
`available_for(market, asof)` only when every declared data_dep resolves
to real historical rows on or before `asof`. Otherwise the layer is
UNAVAILABLE for that (market, asof).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Layer:
    key: str
    title: str
    category: str            # A · B · C · ...
    data_dep: tuple[str, ...] = ()
    rationale: str = ""
    walk_forward_criterion: str = ""

    def __post_init__(self):
        if not self.key or not self.title:
            raise ValueError("Layer requires key and title")


class LayerRegistry:
    _layers: dict[str, Layer] = {}

    @classmethod
    def register(cls, layer: Layer) -> None:
        if layer.key in cls._layers:
            raise ValueError(f"duplicate layer key · {layer.key}")
        cls._layers[layer.key] = layer

    @classmethod
    def get(cls, key: str) -> Layer | None:
        return cls._layers.get(key)

    @classmethod
    def all(cls) -> list[Layer]:
        return list(cls._layers.values())

    @classmethod
    def by_category(cls, category: str) -> list[Layer]:
        return [l for l in cls._layers.values() if l.category == category]


# ── Seed candidate layers · CEO 2026-09-01 direction ────────────────
# Discovery-based · NOT hard-coded to seven · every layer is a candidate
# for measurement · never automatically promoted to R2 weights.

LayerRegistry.register(Layer(
    key="A-aegis-baseline",
    title="AEGIS baseline (current recommendation output)",
    category="A",
    data_dep=("reports/recommendations.json",),
    rationale="Establish the null-hypothesis benchmark that every "
                "additional layer must beat on walk-forward metrics.",
    walk_forward_criterion="Sharpe > 0 · max_dd < baseline threshold",
))

LayerRegistry.register(Layer(
    key="B-technical-context",
    title="Technical & context (momentum · volatility · breadth · regime)",
    category="B",
    data_dep=("data/raw/*.parquet", "reports/context/market_breadth.json"),
    rationale="Cross-sectional short-horizon signal · complements the "
                "fundamentally-oriented layers.",
    walk_forward_criterion="Adds > 5% marginal IC after A · not collinear",
))

LayerRegistry.register(Layer(
    key="C-fundamentals",
    title="Fundamentals (earnings · revenue · margins · growth)",
    category="C",
    data_dep=("data/fundamentals/*.parquet",),
    rationale="Structural-value signal · slow-moving · low correlation "
                "with B on daily horizons.",
    walk_forward_criterion="Improves 60d+ hit-rate · reduces drawdown depth",
))

LayerRegistry.register(Layer(
    key="D-valuation",
    title="Valuation (P/E · P/B · EV/EBITDA · DCF-style)",
    category="D",
    data_dep=("data/fundamentals/*.parquet",),
    rationale="Mean-reversion anchor · limits chasing overextended winners.",
    walk_forward_criterion="Cuts tail loss on top-decile momentum picks",
))

LayerRegistry.register(Layer(
    key="E-balance-sheet-quality",
    title="Balance sheet + cash-flow quality",
    category="E",
    data_dep=("data/fundamentals/*.parquet",),
    rationale="Filter for solvency · reduces bankruptcy / dilution risk.",
    walk_forward_criterion="Improves survivorship-adjusted CAGR",
))

LayerRegistry.register(Layer(
    key="F-sector-regime",
    title="Sector / market regime",
    category="F",
    data_dep=("reports/context/sector_news.json",
              "reports/context/global_overnight.json"),
    rationale="Conditional weighting · turns off style factors that "
                "underperform in the current regime.",
    walk_forward_criterion="Regime-tagged Sharpe > unconditional Sharpe",
))

LayerRegistry.register(Layer(
    key="G-interactions",
    title="Feature interactions (combinations · non-linear scores)",
    category="G",
    data_dep=("backend/feature_store",),
    rationale="Non-linear combinations of B..F may reveal joint edges "
                "not visible in any single layer.",
    walk_forward_criterion="Beats sum-of-parts on out-of-sample fold",
))

LayerRegistry.register(Layer(
    key="H-walk-forward-oos",
    title="Walk-forward / out-of-sample robustness",
    category="H",
    data_dep=("reports/backtest/*.jsonl",),
    rationale="Acceptance gate · a layer that passes in-sample but fails "
                "walk-forward is disqualified from R2 promotion.",
    walk_forward_criterion="Consistent metric across 3+ OOS folds",
))
