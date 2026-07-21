"""Sprint 6.5 · Macro & Intermarket Intelligence Engine.

Sits between Canonical Data and Market Intelligence (pipeline order).
Feeds macro features into every downstream engine.

Modules:
  commodities.py     — WTI, Brent, gold, copper, ...
  currencies.py      — DXY, USDINR, ...
  bonds.py           — yields + curve + inversion
  central_bank.py    — infer rate cycle from yield movements
  volatility.py      — VIX regime classifier
  sector_rotation.py — daily sector flow score
  macro_regime.py    — combined risk-on/risk-off/inflation/etc
  impact_matrix.py   — commodity → sector impact template
  knowledge_graph.py — macro factor → affected sectors/industries
  engine.py          — composes everything

Contracts:
  - Deterministic
  - Walk-forward safe
  - Human-in-the-loop (aegis.macro_intel.v1 registered EXPERIMENTAL)
  - AI Macro Analyst never promotes
"""
from backend.macro_intel.types            import (                                            # noqa: F401
    CommodityReading, CurrencyReading, BondReading, VolatilityReading,
    SectorRotationReading, MacroRegimeReading, CentralBankState,
    CommodityImpact, MacroKnowledgeGraphEntry, MacroIntelligenceResult,
    RegimeLabel,
)
from backend.macro_intel.commodities      import read_commodities                            # noqa: F401
from backend.macro_intel.currencies       import read_currencies                             # noqa: F401
from backend.macro_intel.bonds            import read_bonds, compute_yield_curve             # noqa: F401
from backend.macro_intel.central_bank     import infer_central_bank_state                    # noqa: F401
from backend.macro_intel.volatility       import classify_volatility_regime                  # noqa: F401
from backend.macro_intel.sector_rotation  import compute_sector_rotation                     # noqa: F401
from backend.macro_intel.macro_regime     import classify_macro_regime                       # noqa: F401
from backend.macro_intel.impact_matrix    import (                                            # noqa: F401
    COMMODITY_IMPACT_MATRIX, apply_impact_matrix,
)
from backend.macro_intel.knowledge_graph  import (                                            # noqa: F401
    build_macro_knowledge_graph,
)
from backend.macro_intel.engine           import MacroIntelligenceEngine                     # noqa: F401
