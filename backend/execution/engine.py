"""ExecutionEngine — composes slippage + fills + gaps + corp actions + equity + metrics."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd

from backend.execution.types             import (
    Fill, EquityPoint, ExecutionSummary,
)
from backend.execution.fill_engine       import simulate_fills
from backend.execution.equity_curve      import compute_equity_curve
from backend.statistics                  import (
    sharpe_ratio, sortino_ratio, calmar_ratio, max_drawdown,
    profit_factor, hit_rate,
)


class ExecutionEngine:
    ENGINE_ID       = "aegis.execution.v1"
    ENGINE_VERSION  = "1.0.0"

    def __init__(self, repo_root: Path, market: str,
                    starting_aum: float,
                    min_slippage_bps: float,
                    liquidity_impact_bps: float,
                    vol_impact_bps: float,
                    commission_bps: float,
                    max_daily_participation: float,
                    gap_stop_out_threshold_pct: float,
                    schema_fingerprint: str = "",
                    feature_set_version: str = "",
                    model_stamp: dict | None = None):
        self.repo_root = Path(repo_root)
        self.market = market
        self.starting_aum = float(starting_aum)
        self.min_slippage_bps = float(min_slippage_bps)
        self.liquidity_impact_bps = float(liquidity_impact_bps)
        self.vol_impact_bps = float(vol_impact_bps)
        self.commission_bps = float(commission_bps)
        self.max_daily_participation = float(max_daily_participation)
        self.gap_stop_out_threshold_pct = float(gap_stop_out_threshold_pct)
        self.schema_fingerprint = schema_fingerprint
        self.feature_set_version = feature_set_version
        self.model_stamp = dict(model_stamp) if model_stamp else {}

    def run(self, trade_instructions: list[dict],
              price_provider,
              asof: date | None = None) -> tuple[list[Fill], list[EquityPoint], ExecutionSummary]:
        """Execute one day of trade instructions.

        trade_instructions: list of {ticker, action, prior_weight, new_weight, delta_weight, reason}
                            (Sprint 5 portfolio_diff.json shape)
        price_provider:     object with methods:
                              .mid_price(ticker) → float | None
                              .adv_20d_shares(ticker) → float | None
                              .vol_20d(ticker) → float | None
                              .close_price(date, ticker) → float | None
                              .prior_weight(ticker) → float
        asof:               fill_date

        Returns (fills, equity_curve, summary).
        """
        asof = asof or date.today()

        # Filter out HOLDs — they generate no trade
        executable = [i for i in trade_instructions if str(i.get("action", "HOLD")) != "HOLD"]

        # Simulate fills
        fills = simulate_fills(
            instructions=executable,
            fill_date=asof,
            starting_aum=self.starting_aum,
            get_mid_price=price_provider.mid_price,
            get_adv_20d_shares=price_provider.adv_20d_shares,
            get_vol_20d=price_provider.vol_20d,
            get_prior_weight=price_provider.prior_weight,
            min_slippage_bps=self.min_slippage_bps,
            liquidity_impact_bps=self.liquidity_impact_bps,
            vol_impact_bps=self.vol_impact_bps,
            commission_bps_config=self.commission_bps,
            max_daily_participation=self.max_daily_participation,
            market=self.market,
            model_stamp=self.model_stamp,
        )

        # Equity curve — for today's one-day run this is a single point
        curve = compute_equity_curve(
            fills, self.starting_aum,
            close_price_lookup=price_provider.close_price,
            trade_dates=[asof], market=self.market,
        )

        # Build summary
        summary = self._build_summary(fills, curve, executable, asof)
        return fills, curve, summary

    def _build_summary(self, fills: list[Fill], curve: list[EquityPoint],
                          executable: list[dict], asof: date) -> ExecutionSummary:
        summ = ExecutionSummary(
            market=self.market, asof=asof,
            engine_version=self.ENGINE_VERSION,
            starting_aum=self.starting_aum,
            n_trade_instructions=len(executable),
            n_fills_generated=len(fills),
            n_fills_partial=sum(1 for f in fills if f.partial_fill),
            total_commission=round(sum(f.commission_amount for f in fills), 4),
            total_slippage=round(sum(abs(f.slippage_bps) * f.filled_notional / 10_000
                                        for f in fills), 4),
            model_stamp=self.model_stamp,
            feature_set_version=self.feature_set_version,
            schema_fingerprint=self.schema_fingerprint,
        )

        if curve:
            last = curve[-1]
            summ.equity_value_end = last.equity_value
            summ.cash_end         = last.cash
            summ.long_notional    = last.long_notional
            summ.short_notional   = last.short_notional
            summ.n_open_positions = last.n_positions
        summ.n_closed_positions_today = sum(1 for f in fills if f.action == "CLOSE")

        # Perf metrics (only meaningful with a multi-point curve — otherwise None)
        if len(curve) >= 2:
            daily_returns = [p.daily_return_pct for p in curve]
            equity_series = [p.equity_value for p in curve]
            summ.sharpe_annualised  = sharpe_ratio(daily_returns)
            summ.sortino_annualised = sortino_ratio(daily_returns)
            summ.calmar_ratio       = calmar_ratio(equity_series)
            summ.max_drawdown_pct   = max_drawdown(equity_series)
        if len(fills) >= 1:
            # Turnover proxy: sum |delta_weight|/2
            summ.turnover_today = round(
                sum(abs(f.new_weight - f.prior_weight) for f in fills) / 2.0, 5,
            )

        # Honest-empty labelling
        if len(executable) == 0:
            summ.honest_empty = True
            summ.honest_empty_reason = ("0 executable trade instructions from portfolio_diff.json "
                                          "(all trades were HOLD/no-op). Upstream portfolio produced "
                                          "0 active positions today.")
        elif len(fills) == 0:
            summ.honest_empty = True
            summ.honest_empty_reason = ("Trade instructions present but no fills — check price "
                                          "provider (missing mid_price or vol data for the tickers).")

        summ.notes.append(f"engine v{summ.engine_version} · starting_aum={summ.starting_aum}")
        return summ
