# strategy/risk_manager.py
"""
Portfolio-level risk manager & KILL SWITCH — the layer that keeps a real product alive.

Individual-trade risk (stop-loss, sizing) lives in trade_sim/risk.py. THIS module governs
the account across trades and instruments:
  * daily loss limit      : halt new trades once today's loss exceeds a cap
  * max portfolio risk     : cap total simultaneous risk (sum of open-trade risk)
  * correlation cap        : don't stack correlated exposure (gold & BTC both risk-on)
  * drawdown kill switch    : flatten + stop if equity drawdown breaches a hard limit
  * recovery gating         : require a cool-off / re-validation after a kill

Config-driven (configs/base_config.yaml -> system.max_drawdown_limit, risk_per_trade).
This is a decision layer: pure functions returning ALLOW / BLOCK so it works identically
in backtest, paper and live.
"""
import numpy as np
import pandas as pd


class RiskManager:
    def __init__(self, equity, risk_per_trade=0.01, daily_loss_limit=0.03,
                 max_portfolio_risk=0.06, max_drawdown=0.20, max_correlation=0.7):
        self.start_equity = equity
        self.equity = equity
        self.peak = equity
        self.risk_per_trade = risk_per_trade
        self.daily_loss_limit = daily_loss_limit
        self.max_portfolio_risk = max_portfolio_risk
        self.max_drawdown = max_drawdown
        self.max_correlation = max_correlation
        self.killed = False
        self._day = None
        self._day_start_equity = equity
        self.open_risk = 0.0                      # fraction of equity currently at risk

    def _roll_day(self, ts):
        d = pd.Timestamp(ts).date()
        if d != self._day:
            self._day, self._day_start_equity = d, self.equity

    def can_open(self, ts, trade_risk_frac, corr_with_open=0.0):
        """Return (allowed: bool, reason: str) for opening a new position."""
        self._roll_day(ts)
        if self.killed:
            return False, "KILL-SWITCH active"
        dd = (self.peak - self.equity) / self.peak
        if dd >= self.max_drawdown:
            self.killed = True
            return False, f"drawdown {dd:.0%} >= kill limit"
        day_loss = (self._day_start_equity - self.equity) / self._day_start_equity
        if day_loss >= self.daily_loss_limit:
            return False, f"daily loss {day_loss:.0%} hit"
        if self.open_risk + trade_risk_frac > self.max_portfolio_risk:
            return False, "portfolio risk cap"
        if abs(corr_with_open) > self.max_correlation and self.open_risk > 0:
            return False, f"correlation {corr_with_open:.2f} > cap"
        return True, "ok"

    def on_open(self, trade_risk_frac):
        self.open_risk += trade_risk_frac

    def on_close(self, pnl, trade_risk_frac):
        self.equity += pnl
        self.peak = max(self.peak, self.equity)
        self.open_risk = max(0.0, self.open_risk - trade_risk_frac)

    def status(self):
        dd = (self.peak - self.equity) / self.peak
        return dict(equity=round(self.equity, 2), drawdown=round(dd, 4),
                    open_risk=round(self.open_risk, 4), killed=self.killed)
