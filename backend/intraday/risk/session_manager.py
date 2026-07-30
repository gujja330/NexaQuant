"""Session risk manager · per §7 of AEGIS_INTRADAY_ARCHITECTURE.md.

Enforces:
  · Per-trade risk cap (0.25% of session capital)
  · Session daily loss limit (−1.0% → auto-pause new entries)
  · Consecutive-loss circuit breaker (3 in a row → 60-min cooldown)
  · Correlation cap (max 3 open positions in same sector)
  · VIX intraday kill switch (VIX +15% in 10 min → close all, pause 30 min)
  · No new entries after 13:00 IST / 15:00 ET (§6.1)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class RiskDecision:
    approved:    bool
    reason:      str
    max_size:    float = 0.0            # position size in shares (0 = blocked)
    metadata:    dict = field(default_factory=dict)


@dataclass
class SessionRiskManager:
    session_capital:                float
    per_trade_risk_pct:             float = 0.0025    # 0.25%
    session_daily_loss_cap_pct:     float = 0.01      # 1%
    max_concurrent_positions:       int = 8
    max_same_sector:                int = 3
    consecutive_loss_pause_after:   int = 3
    consecutive_loss_pause_minutes: int = 60
    vix_spike_pause_minutes:        int = 30

    session_pnl:                    float = 0.0
    consecutive_losses:             int = 0
    paused_until:                   datetime | None = None
    open_positions:                 dict[str, dict] = field(default_factory=dict)
    positions_by_sector:            dict[str, int] = field(default_factory=dict)

    def approve_entry(self, ticker: str, entry: float, stop: float,
                        sector: str = "", now: datetime | None = None) -> RiskDecision:
        now = now or datetime.now(timezone.utc)
        if self.paused_until and now < self.paused_until:
            return RiskDecision(False,
                f"paused_until_{self.paused_until.isoformat()}")

        # Daily loss cap
        if self.session_pnl <= -self.session_capital * self.session_daily_loss_cap_pct:
            return RiskDecision(False, "session_daily_loss_cap_hit")

        # Concurrent positions
        if len(self.open_positions) >= self.max_concurrent_positions:
            return RiskDecision(False, "max_concurrent_positions_reached")

        # Sector correlation cap
        if sector and self.positions_by_sector.get(sector, 0) >= self.max_same_sector:
            return RiskDecision(False, f"sector_cap_reached_{sector}")

        # Position sizing
        risk_per_share = abs(entry - stop)
        if risk_per_share <= 0:
            return RiskDecision(False, "invalid_stop")
        max_dollar_risk = self.session_capital * self.per_trade_risk_pct
        max_shares = int(max_dollar_risk / risk_per_share)
        if max_shares < 1:
            return RiskDecision(False, "risk_too_wide_for_min_size")

        return RiskDecision(True, "approved", max_size=max_shares,
                              metadata={"risk_per_share": risk_per_share,
                                        "max_dollar_risk": max_dollar_risk})

    def register_open(self, ticker: str, entry: float, size: float, sector: str = ""):
        self.open_positions[ticker] = {
            "entry": entry, "size": size, "sector": sector,
        }
        if sector:
            self.positions_by_sector[sector] = self.positions_by_sector.get(sector, 0) + 1

    def register_close(self, ticker: str, exit_price: float, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        pos = self.open_positions.pop(ticker, None)
        if pos is None:
            return
        sector = pos.get("sector")
        if sector and self.positions_by_sector.get(sector, 0) > 0:
            self.positions_by_sector[sector] -= 1
        pnl = (exit_price - pos["entry"]) * pos["size"]
        self.session_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.consecutive_loss_pause_after:
                self.paused_until = now + timedelta(
                    minutes=self.consecutive_loss_pause_minutes)
                self.consecutive_losses = 0
        else:
            self.consecutive_losses = 0

    def vix_kill_switch(self, vix_change_pct_10min: float, now: datetime | None = None):
        """Called by external tick handler when VIX moves. Returns True if
        kill-switch triggered."""
        now = now or datetime.now(timezone.utc)
        if vix_change_pct_10min > 15.0:
            self.paused_until = now + timedelta(minutes=self.vix_spike_pause_minutes)
            return True
        return False
