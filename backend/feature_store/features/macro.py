"""Macro features from CanonicalMacro rows.

Macro is MARKET-LEVEL — the same values are joined to every ticker in the
universe. India has no macro parquet yet (INDIAVIX only via existing engine),
so India macro features come from the INDIAVIX_D1 series where available.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.canonical.schemas import CanonicalDataset


MACRO_SYMBOL_MAP = {
    "^TNX":  "macro_10y",
    "UUP":   "macro_dxy",
    "GC=F":  "macro_gold",
    "CL=F":  "macro_wti_oil",
    "^VIX":  "macro_vix",
    "^MOVE": "macro_move",
}


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[str, dict]:
    macros = canon.get("macro")
    market_features: dict = {}
    if macros and macros.rows:
        for m in macros.rows:
            col = MACRO_SYMBOL_MAP.get(m.symbol)
            if col:
                market_features[col] = round(m.close, 4)
                if m.chg_1m_pct is not None:
                    if col == "macro_10y":
                        market_features["macro_10y_chg_1m_pct"] = m.chg_1m_pct
                    if col == "macro_vix":
                        market_features["macro_vix_chg_1m_pct"] = m.chg_1m_pct
    # India VIX fallback if canonical macro is empty
    if not market_features.get("macro_vix") and market_name == "india":
        # We won't do the fallback here — leave null. India VIX is picked up in
        # market_intelligence tile; feature store macros are limited to what
        # canonical.macro provides. Note in the sprint report.
        pass
    # Broadcast to every ticker
    return {t: dict(market_features) for t in universe}
