"""Portfolio-construction strategies for DEV021 backtesting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Portfolio:
    """A dict-like portfolio of ticker -> weight (weights sum to 1.0)."""
    weights: dict[str, float]
    name: str

    def __post_init__(self):
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6 and total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}


def top_n_equal_weight(scored_tickers: list[tuple[str, float]], n: int) -> Portfolio:
    """Take top N by score; equal weights."""
    sorted_desc = sorted(scored_tickers, key=lambda x: x[1], reverse=True)
    top = sorted_desc[:n]
    if not top:
        return Portfolio(weights={}, name=f"top_{n}_ew_empty")
    w = 1.0 / len(top)
    return Portfolio(weights={t: w for t, _ in top}, name=f"top_{n}_ew")


def top_n_score_weighted(scored_tickers: list[tuple[str, float]], n: int,
                          min_score: float = 50.0) -> Portfolio:
    """Take top N by score above min_score; weight ∝ (score - min_score)."""
    sorted_desc = sorted(scored_tickers, key=lambda x: x[1], reverse=True)
    top = [(t, s) for t, s in sorted_desc[:n] if s > min_score]
    if not top:
        return Portfolio(weights={}, name=f"top_{n}_sw_empty")
    total = sum(s - min_score for _, s in top)
    if total <= 0:
        return top_n_equal_weight(scored_tickers, n)
    return Portfolio(
        weights={t: (s - min_score) / total for t, s in top},
        name=f"top_{n}_sw",
    )


def equal_weight_universe(scored_tickers: list[tuple[str, float]]) -> Portfolio:
    """Equal-weight all tickers in the scored universe. Serves as one benchmark."""
    if not scored_tickers:
        return Portfolio(weights={}, name="ew_universe_empty")
    w = 1.0 / len(scored_tickers)
    return Portfolio(weights={t: w for t, _ in scored_tickers}, name="ew_universe")


STRATEGIES: dict[str, Callable[[list[tuple[str, float]]], Portfolio]] = {
    "top_5_ew":       lambda s: top_n_equal_weight(s, 5),
    "top_10_ew":      lambda s: top_n_equal_weight(s, 10),
    "top_20_ew":      lambda s: top_n_equal_weight(s, 20),
    "top_10_sw":      lambda s: top_n_score_weighted(s, 10, min_score=50.0),
    "top_20_sw":      lambda s: top_n_score_weighted(s, 20, min_score=50.0),
    "ew_universe":    equal_weight_universe,
}
