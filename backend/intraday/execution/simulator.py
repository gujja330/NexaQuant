"""Execution simulator · marketable-limit fills with slippage + commissions.

Per §8 of AEGIS_INTRADAY_ARCHITECTURE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Fill:
    ticker:        str
    side:          str        # "BUY" | "SELL"
    price:         float
    size:          int
    ts_utc:        str
    slippage_bps:  float
    commission:    float
    reject_reason: Optional[str] = None


@dataclass
class ExecutionSimulator:
    market:              str = "india"
    slippage_bps_base:   float = 5.0      # base 5 bps
    slippage_bps_per_spread: float = 20.0 # per-1%-spread additional bps
    reject_rate:         float = 0.05     # 5% base reject rate
    commission_pct:      float = 0.0003   # India ~0.03% · USA effectively 0

    def _commission(self, price: float, size: int) -> float:
        if self.market == "india":
            gross = price * size
            return gross * self.commission_pct
        return 0.0     # USA · zero broker commission (SEC fees ignored for paper)

    def submit_marketable_limit(self, ticker: str, side: str, size: int,
                                  mid: float, spread_pct: float = 0.001,
                                  now: datetime | None = None) -> Fill:
        now = now or datetime.now(timezone.utc)
        # Reject when spread too wide
        if spread_pct > 0.002:
            return Fill(ticker=ticker, side=side, price=0, size=0,
                          ts_utc=now.isoformat(),
                          slippage_bps=0, commission=0,
                          reject_reason=f"spread_too_wide_{spread_pct*100:.2f}pct")
        # Slippage model
        slip = self.slippage_bps_base + self.slippage_bps_per_spread * spread_pct * 100
        slip_pct = slip / 10000
        if side == "BUY":
            fill_price = mid * (1 + slip_pct)
        else:
            fill_price = mid * (1 - slip_pct)
        return Fill(
            ticker=ticker, side=side, price=round(fill_price, 4), size=size,
            ts_utc=now.isoformat(),
            slippage_bps=round(slip, 2),
            commission=round(self._commission(fill_price, size), 2),
        )
