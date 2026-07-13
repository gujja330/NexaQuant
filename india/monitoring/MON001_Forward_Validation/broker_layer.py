"""
MON001 broker fill integration — currently PAPER_ONLY (read-only interface).

Per `india/broker_angelone.py` module comment ("Orders are NOT placed here (paper/live
runner comes next, after validation)."), the production system does not place broker
orders. There is no reliable broker fill history to ingest.

MON001 defines the fill-ingestion interface here so that when ENG003 (execution
calibration) later wires in real fills, the plumbing exists. Until then, `available()`
returns False and `fetch_fills()` returns an empty list.

The broker layer is STRICTLY READ-ONLY from MON001's perspective. It cannot place, modify,
or cancel orders. Any attempt to call an order-placement method raises RuntimeError.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BrokerFill:
    order_id: str
    fill_id: str
    symbol: str
    fill_price: float
    fill_qty: int
    fill_ts_utc: str
    side: str          # "BUY" or "SELL"
    fees_paid: float = 0.0


@dataclass(frozen=True)
class BrokerStatus:
    available: bool
    reason: str
    fills_count: int = 0
    orders_count: int = 0


class PaperOnlyBrokerLayer:
    """Read-only broker layer. Currently reports PAPER_ONLY (no fills available)."""

    def status(self) -> BrokerStatus:
        return BrokerStatus(
            available=False,
            reason="broker_angelone.py order placement is disabled; no fill history "
                   "ingested. MON001 remains PAPER_ONLY at seal time.",
            fills_count=0,
            orders_count=0,
        )

    def available(self) -> bool:
        return self.status().available

    def fetch_fills(self, since_asof: str) -> list[BrokerFill]:
        return []

    def fetch_orders(self, since_asof: str) -> list[dict[str, Any]]:
        return []

    # --- explicit denial of order-placement surface ---
    def place_order(self, *args, **kwargs):
        raise RuntimeError(
            "MON001 broker layer is READ-ONLY. Order placement is not authorized under "
            "MON001. Any order placement requires a separate, explicitly authorized "
            "execution layer (ENG003 or later).")

    def modify_order(self, *args, **kwargs):
        raise RuntimeError(
            "MON001 broker layer is READ-ONLY. Order modification is not authorized.")

    def cancel_order(self, *args, **kwargs):
        raise RuntimeError(
            "MON001 broker layer is READ-ONLY. Order cancellation is not authorized.")


def make_broker_layer() -> PaperOnlyBrokerLayer:
    """Factory. Returns the PAPER_ONLY layer at MON001 seal time. Later versions may
    return an AngelBrokerLayer when broker fills are integrated."""
    return PaperOnlyBrokerLayer()
