"""
Sprint 7.5 · Factor Library engine.

Reads Sprint 6.5's macro intelligence outputs (which piggy-back on
free data via yfinance/FRED/etc.) and emits ONE row per factor per day.

Design: this engine does NO market lookups of its own — it consumes
what Sprint 6.5 already produced. That keeps the free-data substrate
single-sourced and walk-forward safe.
"""

from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .types import FactorReading, FactorLibraryResult

ENGINE_ID = "aegis.factor_library.v1"
ENGINE_VERSION = "1.0.0"


def _load_json(p: Path) -> Optional[Dict[str, Any]]:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _classify_trend(pct: Optional[float], threshold: float = 2.0) -> Optional[str]:
    if pct is None:
        return None
    if pct >= threshold:
        return "bull"
    if pct <= -threshold:
        return "bear"
    return "sideways"


def _find_by_symbol(items: List[Dict[str, Any]], symbol: str) -> Optional[Dict[str, Any]]:
    for it in items or []:
        if it.get("symbol") == symbol:
            return it
    return None


class FactorLibraryEngine:
    """
    Composes per-factor readings from Sprint 6.5's outputs.

    Inputs (per market):
      commodity_intelligence.json
      currency_intelligence.json
      bond_intelligence.json
      central_bank_state.json
      volatility_intelligence.json
      sector_rotation.json

    Output: FactorLibraryResult with one FactorReading per configured factor.
    """

    def __init__(self, config_path: Path | str):
        self.config_path = Path(config_path)
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.factors_cfg: List[Dict[str, Any]] = self.cfg.get("factors", [])

    def build(self, *, market: str, reports_dir: Path, asof: date) -> FactorLibraryResult:
        commod = _load_json(reports_dir / "commodity_intelligence.json") or {}
        curr = _load_json(reports_dir / "currency_intelligence.json") or {}
        bonds = _load_json(reports_dir / "bond_intelligence.json") or {}
        cb = _load_json(reports_dir / "central_bank_state.json") or {}
        vol = _load_json(reports_dir / "volatility_intelligence.json") or {}
        rot = _load_json(reports_dir / "sector_rotation.json") or {}

        readings: List[FactorReading] = []

        for f in self.factors_cfg:
            name = f["name"]
            source = f["source"]
            unit = f["unit"]
            symbol = f.get("symbol")
            affected = f.get("affected", []) or []

            value: Optional[float] = None
            value_label: Optional[str] = None
            change_1d: Optional[float] = None
            change_1w: Optional[float] = None
            change_1m: Optional[float] = None
            trend: Optional[str] = None
            notes = ""

            if source == "commodity" and symbol:
                item = _find_by_symbol(commod.get("commodities", []), symbol)
                if item:
                    value = item.get("last")
                    change_1w = item.get("chg_1w_pct")
                    change_1m = item.get("chg_1m_pct")
                    trend = item.get("trend") or _classify_trend(change_1w)

            elif source == "currency" and symbol:
                item = _find_by_symbol(curr.get("currencies", []), symbol)
                if item:
                    value = item.get("last")
                    change_1w = item.get("chg_1w_pct")
                    change_1m = item.get("chg_1m_pct")
                    trend = _classify_trend(change_1w)

            elif source == "bond" and symbol:
                item = _find_by_symbol(bonds.get("bonds", []), symbol)
                if item:
                    value = item.get("last")
                    change_1m = item.get("chg_1m_bps")
                    trend = _classify_trend(change_1m, threshold=15.0) if change_1m is not None else None

            elif source == "volatility" and symbol:
                if vol.get("symbol") == symbol:
                    value = vol.get("last")
                    change_1m = vol.get("chg_1m_pct")
                    value_label = vol.get("regime")
                    trend = _classify_trend(change_1m)

            elif source == "central_bank":
                if name == "fed_rate_cycle" and cb.get("bank") == "Fed":
                    value_label = cb.get("rate_cycle")
                    value = cb.get("short_yield_pct")
                elif name == "rbi_rate_cycle" and cb.get("bank") == "RBI":
                    value_label = cb.get("rate_cycle")
                    value = cb.get("short_yield_pct")
                else:
                    notes = "central-bank data unavailable for this market"

            elif source == "derived":
                if name == "yield_curve_slope_10y_2y":
                    value = cb.get("yield_curve_slope")
                    unit = "bps"
                elif name == "yield_curve_inversion":
                    inv = cb.get("inversion")
                    value = 1.0 if inv else 0.0
                    value_label = "inverted" if inv else "normal"
                elif name == "currency_pressure":
                    usd = _find_by_symbol(curr.get("currencies", []), "UUP")
                    inr = _find_by_symbol(curr.get("currencies", []), "USDINR")
                    parts = [x for x in (usd, inr) if x and x.get("chg_1w_pct") is not None]
                    if parts:
                        value = sum(x["chg_1w_pct"] for x in parts) / len(parts)
                        trend = _classify_trend(value)

            elif source == "rotation":
                if name == "sector_rotation_leader":
                    leaders = rot.get("leaders") or []
                    if leaders:
                        value_label = leaders[0] if isinstance(leaders[0], str) else leaders[0].get("sector")
                elif name == "sector_rotation_laggard":
                    laggards = rot.get("laggards") or []
                    if laggards:
                        value_label = laggards[0] if isinstance(laggards[0], str) else laggards[0].get("sector")

            confidence = 1.0 if (value is not None or value_label is not None) else 0.0

            readings.append(FactorReading(
                asof=asof, market=market, factor=name, source=source, unit=unit,
                value=value, value_label=value_label,
                change_1d=change_1d, change_1w=change_1w, change_1m=change_1m,
                trend=trend, confidence=confidence,
                affected_sectors=affected, notes=notes,
            ))

        return FactorLibraryResult(
            engine=ENGINE_ID, version=ENGINE_VERSION,
            market=market, asof=asof,
            n_factors=len(readings), factors=readings,
        )


def build_factor_library(*, market: str, reports_dir: Path, asof: date,
                           config_path: Path | str) -> FactorLibraryResult:
    return FactorLibraryEngine(config_path).build(
        market=market, reports_dir=reports_dir, asof=asof
    )
