"""PortfolioEngine — composes construction + diversification + rebalance + state."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from backend.portfolio.types           import PortfolioSnapshot, PortfolioDiff
from backend.portfolio.construction    import build_portfolio
from backend.portfolio.diversification import compute_diversification_metrics
from backend.portfolio.cash_manager    import compute_cash_reserve
from backend.portfolio.rebalance       import diff_portfolios
from backend.portfolio.state           import load_prior_state


class PortfolioEngine:
    ENGINE_ID       = "aegis.portfolio.v1"
    ENGINE_VERSION  = "1.0.0"

    def __init__(self, repo_root: Path, market: str,
                    target_n_positions: int,
                    min_position_size: float,
                    cash_reserve_min: float,
                    cash_reserve_stress: float,
                    rebalance_threshold_bps: int,
                    regime: str = "unknown",
                    schema_fingerprint: str = "",
                    feature_set_version: str = "",
                    model_stamp: dict | None = None):
        self.repo_root = Path(repo_root)
        self.market = market
        self.target_n_positions = int(target_n_positions)
        self.min_position_size = float(min_position_size)
        self.cash_reserve_min = float(cash_reserve_min)
        self.cash_reserve_stress = float(cash_reserve_stress)
        self.rebalance_threshold_bps = int(rebalance_threshold_bps)
        self.regime = regime
        self.schema_fingerprint = schema_fingerprint
        self.feature_set_version = feature_set_version
        self.model_stamp = dict(model_stamp) if model_stamp else {}

    def run(self, sized_positions: list[dict],
              ticker_sector: dict[str, str] | None = None,
              asof: date | None = None) -> tuple[PortfolioSnapshot, PortfolioDiff]:
        """Build today's portfolio + diff against prior state."""
        asof = asof or date.today()

        # Cash policy
        cash_reserve = compute_cash_reserve(self.regime,
                                              self.cash_reserve_min,
                                              self.cash_reserve_stress)

        # Construct portfolio
        positions = build_portfolio(
            sized_positions,
            target_n=self.target_n_positions,
            min_position_size=self.min_position_size,
            cash_reserve=cash_reserve,
            asof=asof.isoformat(),
            market=self.market,
            ticker_sector=ticker_sector,
            model_stamp=self.model_stamp,
        )

        # Diversification
        div = compute_diversification_metrics(positions)

        total_weight = sum(p.weight for p in positions)
        gross_weight = sum(abs(p.weight) for p in positions)
        cash_pct = max(0.0, 1.0 - gross_weight)

        snap = PortfolioSnapshot(
            market=self.market, asof=asof,
            engine_version=self.ENGINE_VERSION,
            n_positions=len(positions),
            total_weight=round(total_weight, 6),
            cash_pct=round(cash_pct, 6),
            cash_reserve_target=round(cash_reserve, 6),
            positions=positions,
            hhi=div["hhi"],
            effective_n=div["effective_n"],
            top_5_pct=div["top_5_pct"],
            per_sector_pct=div["per_sector_pct"],
            n_sectors=div["n_sectors"],
            schema_fingerprint=self.schema_fingerprint,
            feature_set_version=self.feature_set_version,
            model_stamp=self.model_stamp,
            regime_at_construction=self.regime,
            notes=[f"engine v{self.ENGINE_VERSION} · regime={self.regime} · "
                     f"cash_reserve_target={cash_reserve:.4f} · target_n={self.target_n_positions}"],
        )

        # Prior state + diff
        prior = load_prior_state(self.repo_root, self.market)
        diff = diff_portfolios(prior, snap, self.rebalance_threshold_bps)

        return snap, diff
