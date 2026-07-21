"""Macro & Intermarket Intelligence data types — Sprint 6.5."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class RegimeLabel(str, Enum):
    RISK_ON            = "risk_on"
    RISK_OFF           = "risk_off"
    INFLATIONARY       = "inflationary"
    DEFLATIONARY       = "deflationary"
    COMMODITY_BULL     = "commodity_bull"
    COMMODITY_BEAR     = "commodity_bear"
    EXPANSION          = "expansion"
    RECESSION_WARNING  = "recession_warning"
    UNKNOWN            = "unknown"


@dataclass
class CommodityReading:
    symbol:              str
    label:               str
    last:                float
    chg_1d_pct:          float | None = None
    chg_1w_pct:          float | None = None
    chg_1m_pct:          float | None = None
    trend:               str = "unknown"        # bull / bear / sideways
    vol_20d_annualised:  float | None = None


@dataclass
class CurrencyReading:
    symbol:              str
    label:               str
    last:                float
    chg_1d_pct:          float | None = None
    chg_1w_pct:          float | None = None
    chg_1m_pct:          float | None = None
    trend:               str = "unknown"


@dataclass
class BondReading:
    symbol:              str
    label:               str
    yield_pct:           float
    chg_1d_bps:          float | None = None
    chg_1w_bps:          float | None = None
    chg_1m_bps:          float | None = None


@dataclass
class VolatilityReading:
    market:              str
    symbol:              str
    last:                float
    regime:              str                    # calm / elevated / stress / panic
    chg_1m_pct:          float | None = None


@dataclass
class SectorRotationReading:
    market:              str
    asof:                date
    sector_returns:      dict = field(default_factory=dict)     # sector → 1m return
    leaders:             list = field(default_factory=list)     # top-3
    laggards:            list = field(default_factory=list)     # bottom-3
    rotation_strength:   float = 0.0             # 0..1, higher = more dispersion


@dataclass
class CentralBankState:
    market:              str
    bank:                str                     # "RBI" | "Fed"
    rate_cycle:          str                     # tightening / easing / neutral
    short_yield_pct:     float | None = None
    long_yield_pct:      float | None = None
    yield_curve_slope:   float | None = None    # long - short in bps
    inversion:           bool = False
    liquidity_score:     float = 0.0             # -1..+1, higher = looser
    notes:               list = field(default_factory=list)


@dataclass
class MacroRegimeReading:
    market:              str
    asof:                date
    primary_regime:      str                     # RegimeLabel value
    secondary_regime:    str | None = None
    confidence:          float = 0.0
    evidence:            dict = field(default_factory=dict)
    macro_score:         float = 0.0             # composite -1..+1 (risk-off to risk-on)


@dataclass
class CommodityImpact:
    """One commodity → sector impact row (from the template matrix)."""
    commodity:           str
    direction:           str                     # "up" | "down"
    positive_sectors:    list = field(default_factory=list)
    negative_sectors:    list = field(default_factory=list)
    mixed_sectors:       list = field(default_factory=list)
    confidence:          float = 0.75
    rationale:           str = ""


@dataclass
class MacroKnowledgeGraphEntry:
    factor:              str
    factor_kind:         str                     # commodity / currency / rate / vol
    current_state:       str                     # up / down / neutral
    affected_sectors:    list = field(default_factory=list)
    affected_industries: list = field(default_factory=list)
    affected_tickers:    list = field(default_factory=list)
    direction:           str = "mixed"           # positive / negative / mixed
    evidence:            str = ""


@dataclass
class MacroIntelligenceResult:
    market:              str
    asof:                date
    engine_version:      str = "v1.0"
    commodities:         list = field(default_factory=list)     # CommodityReading[]
    currencies:          list = field(default_factory=list)
    bonds:               list = field(default_factory=list)
    volatility:          VolatilityReading | None = None
    sector_rotation:     SectorRotationReading | None = None
    central_bank:        CentralBankState | None = None
    macro_regime:        MacroRegimeReading | None = None
    active_impacts:      list = field(default_factory=list)      # CommodityImpact[]
    knowledge_graph:     list = field(default_factory=list)      # MacroKnowledgeGraphEntry[]
    # Provenance
    schema_fingerprint:  str = ""
    feature_set_version: str = ""
    model_stamp:         dict = field(default_factory=dict)
    notes:               list = field(default_factory=list)
