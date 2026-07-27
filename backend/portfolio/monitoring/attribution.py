"""Portfolio Attribution Engine · Constitution-compliant.

Decompose every position's return into 13 factor contributions:
  Momentum · Value · Quality · Growth · Sector · Macro · Risk ·
  Fundamentals · News · Corp Actions · Execution · Learning · Residual

Given model contributions (from ensemble.py) + realized return,
solves an additive attribution such that sum(contributions) == realized_return.

Deterministic. Schema-fingerprinted. Walk-forward safe.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from enum import Enum
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.portfolio_attribution.v1.20260727"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.portfolio_attribution.v1"

ATTRIBUTION_FACTORS = (
    "momentum", "value", "quality", "growth",
    "sector", "macro", "risk",
    "fundamentals", "news", "corp_actions",
    "execution", "learning", "residual",
)


class AttributionSource(str, Enum):
    MODEL_ENSEMBLE = "model_ensemble"
    SECTOR_CONTEXT = "sector_context"
    MACRO_REGIME   = "macro_regime"
    RISK_ENGINE    = "risk_engine"
    EXECUTION_LEDGER = "execution_ledger"
    LEARNING_LEDGER  = "learning_ledger"
    RESIDUAL       = "residual"


@dataclass(frozen=True)
class PositionAttribution:
    ticker: str
    realized_return_pct: float
    contributions: dict[str, float]        # keys ⊆ ATTRIBUTION_FACTORS
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    schema_version: str = SCHEMA_VERSION


@dataclass
class PortfolioAttribution:
    engine: str = ENGINE_ID
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    market: str = ""
    asof: str = ""
    run_utc: str = ""
    n_positions: int = 0
    total_realized_return_pct: float = 0.0
    aggregate_contributions: dict[str, float] = field(default_factory=dict)
    positions: list[dict] = field(default_factory=list)


def _split_realized_across_factors(realized: float,
                                     factor_weights: Mapping[str, float]) -> dict[str, float]:
    """Deterministic additive split of realized_return across factors.

    factor_weights: {factor_name: weight_scalar}  weight ~ model contribution
        (positive weight means factor pushed BUY direction).
    Returns dict of factor -> contribution_pct, sum == realized (residual absorbs remainder).
    """
    known = {k: float(v) for k, v in factor_weights.items() if k in ATTRIBUTION_FACTORS and k != "residual"}
    tot_abs = sum(abs(v) for v in known.values())
    contribs: dict[str, float] = {f: 0.0 for f in ATTRIBUTION_FACTORS}
    if tot_abs <= 1e-12:
        # No signal; entire return is residual
        contribs["residual"] = round(realized, 6)
        return contribs
    for k, w in known.items():
        share = (w / tot_abs) * realized  # signed share
        contribs[k] = round(share, 6)
    total_attributed = sum(contribs[k] for k in known)
    contribs["residual"] = round(realized - total_attributed, 6)
    return contribs


class PortfolioAttributionEngine:
    """Deterministic Portfolio Attribution Engine."""

    def __init__(self, market: str) -> None:
        if not market:
            raise ValueError("market required")
        self.market = market

    def run(self,
             positions: Sequence[Mapping],
             asof: date | str,
             run_utc: str | None = None) -> PortfolioAttribution:
        """positions: list of dicts with keys:
            ticker · realized_return_pct · factor_weights (Mapping[str, float])"""
        asof_str = asof.isoformat() if isinstance(asof, date) else str(asof)
        rep = PortfolioAttribution(
            market=self.market,
            asof=asof_str,
            run_utc=run_utc or datetime.now(timezone.utc).isoformat(),
            n_positions=len(positions),
        )
        agg: dict[str, float] = {f: 0.0 for f in ATTRIBUTION_FACTORS}
        total_ret = 0.0
        for p in positions:
            realized = float(p.get("realized_return_pct", 0.0))
            weights = p.get("factor_weights", {}) or {}
            contribs = _split_realized_across_factors(realized, weights)
            rep.positions.append(asdict(PositionAttribution(
                ticker=p["ticker"],
                realized_return_pct=round(realized, 6),
                contributions=contribs,
            )))
            for k, v in contribs.items():
                agg[k] += v
            total_ret += realized
        rep.aggregate_contributions = {k: round(v, 6) for k, v in agg.items()}
        rep.total_realized_return_pct = round(total_ret, 6)
        return rep


def compute_attribution(market: str,
                          positions: Sequence[Mapping],
                          asof: date | str,
                          run_utc: str | None = None) -> PortfolioAttribution:
    """Convenience one-shot API."""
    return PortfolioAttributionEngine(market).run(positions, asof, run_utc)
