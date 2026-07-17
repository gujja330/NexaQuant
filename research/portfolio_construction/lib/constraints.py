"""DEV022 constraint enforcement (v0.2 — respects caps under renormalisation).

Weights are enforced to satisfy simultaneously:
  - Per-stock max/min weight
  - Per-sector max exposure
  - Per-industry max exposure
  - Cash allocation
  - Sum-to-(1 - cash_allocation)

Algorithm:
  1. Normalise input to sum-to-1.
  2. Drop below-min positions.
  3. Iterate: cap stock/sector/industry using cascading scale-downs.
     Any weight freed by capping is redistributed proportionally to positions
     that still have headroom (per-stock AND per-sector AND per-industry).
  4. If total weight still exceeds 1-cash: scale everything down.
     If total falls below 1-cash and no headroom remains: leave shortfall
     as unused cash (documented in violations).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Constraints:
    max_stock_weight: float = 0.30
    min_stock_weight: float = 0.005
    max_sector_exposure: float = 0.35
    max_industry_exposure: float = 0.25
    cash_allocation: float = 0.0
    min_positions: int = 3
    max_positions: int = 30


def apply(weights: dict[str, float],
           ticker_to_sector: dict[str, str],
           ticker_to_industry: dict[str, str],
           constraints: Constraints) -> tuple[dict[str, float], list[str]]:
    violations = []

    if not weights:
        return {}, ["empty_input"]

    weights = {t: float(w) for t, w in weights.items() if w > 0}
    total = sum(weights.values())
    if total <= 0:
        return {}, ["all_positions_zero"]
    # Normalise to 1.0
    weights = {t: w / total for t, w in weights.items()}

    # Drop below min
    dropped = [t for t, w in weights.items() if w < constraints.min_stock_weight]
    for t in dropped:
        violations.append(f"dropped_below_min_weight:{t}")
        del weights[t]
    if not weights:
        return {}, violations + ["no_positions_after_min_filter"]

    # Renormalise after drops
    total = sum(weights.values())
    weights = {t: w / total for t, w in weights.items()}

    target_equity = 1.0 - constraints.cash_allocation

    # Iterative cap + redistribute — fix ONE violation per pass, then re-check
    excess = 0.0
    for iteration in range(60):
        # Recompute totals AFTER any previous fix
        sector_totals = defaultdict(float)
        industry_totals = defaultdict(float)
        for t, w in weights.items():
            sector_totals[ticker_to_sector.get(t, "Unknown")] += w
            industry_totals[ticker_to_industry.get(t, "Unknown")] += w

        # Find the biggest violation (if any)
        worst = None                # ('stock', t, excess_amount) or ('sector', s, amt) etc
        for t, w in weights.items():
            if w > constraints.max_stock_weight + 1e-9:
                exc = w - constraints.max_stock_weight
                if worst is None or exc > worst[2]:
                    worst = ("stock", t, exc)
        for s, v in sector_totals.items():
            if v > constraints.max_sector_exposure + 1e-9:
                exc = v - constraints.max_sector_exposure
                if worst is None or exc > worst[2]:
                    worst = ("sector", s, exc)
        for i, v in industry_totals.items():
            if v > constraints.max_industry_exposure + 1e-9:
                exc = v - constraints.max_industry_exposure
                if worst is None or exc > worst[2]:
                    worst = ("industry", i, exc)

        if worst is None:
            break

        kind, name, exc_amt = worst
        if kind == "stock":
            weights[name] = constraints.max_stock_weight
            excess += exc_amt
            violations.append(f"capped_max_weight:{name}")
        elif kind == "sector":
            current = sector_totals[name]
            scale = constraints.max_sector_exposure / current
            for t in list(weights):
                if ticker_to_sector.get(t) == name:
                    weights[t] *= scale
            excess += exc_amt
            violations.append(f"scaled_sector:{name}")
        else:                          # industry
            current = industry_totals[name]
            scale = constraints.max_industry_exposure / current
            for t in list(weights):
                if ticker_to_industry.get(t) == name:
                    weights[t] *= scale
            excess += exc_amt
            violations.append(f"scaled_industry:{name}")

    # ── Redistribute accumulated excess to positions with headroom ──────
    if excess > 1e-9:
        for redist_iter in range(20):
            # Recompute state
            sector_totals = defaultdict(float)
            industry_totals = defaultdict(float)
            for t, w in weights.items():
                sector_totals[ticker_to_sector.get(t, "Unknown")] += w
                industry_totals[ticker_to_industry.get(t, "Unknown")] += w

            headroom = {}
            for t, w in weights.items():
                sec = ticker_to_sector.get(t, "Unknown")
                ind = ticker_to_industry.get(t, "Unknown")
                stock_room = constraints.max_stock_weight - w
                sec_room = constraints.max_sector_exposure - sector_totals[sec]
                ind_room = constraints.max_industry_exposure - industry_totals[ind]
                r = max(0.0, min(stock_room, sec_room, ind_room))
                if r > 1e-9:
                    headroom[t] = r

            if not headroom or excess < 1e-9:
                break

            room_total = sum(headroom.values())
            to_distribute = min(excess, room_total)
            for t, r in headroom.items():
                weights[t] += to_distribute * (r / room_total)
            excess -= to_distribute

        if excess > 1e-9:
            violations.append(f"unallocated_excess:{excess:.4f}_no_headroom_remaining")

    # Final scale to target_equity if we're over
    total = sum(weights.values())
    if total > target_equity + 1e-9:
        weights = {t: w * target_equity / total for t, w in weights.items()}

    # Position-count discipline
    if len(weights) < constraints.min_positions:
        violations.append(f"below_min_positions:{len(weights)}")
    if len(weights) > constraints.max_positions:
        violations.append(f"above_max_positions:{len(weights)}")

    return weights, violations
