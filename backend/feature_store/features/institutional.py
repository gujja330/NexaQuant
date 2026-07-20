"""Institutional features from CanonicalFlow + CanonicalHolding."""
from __future__ import annotations

from datetime import date, timedelta

from backend.canonical.schemas import CanonicalDataset


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str) -> dict[str, dict]:
    out: dict[str, dict] = {t: {} for t in universe}

    # Institutional holders (USA · yfinance top-holders view)
    holdings = canon.get("holding")
    if holdings and holdings.rows:
        pct_by_sym: dict[str, float] = {}
        top_by_sym: dict[str, float] = {}
        for h in holdings.rows:
            if h.symbol not in universe: continue
            if h.pct_out is not None:
                pct_by_sym[h.symbol] = pct_by_sym.get(h.symbol, 0.0) + float(h.pct_out)
                top_by_sym[h.symbol] = max(top_by_sym.get(h.symbol, 0.0), float(h.pct_out))
        for t in universe:
            if t in pct_by_sym:
                out[t]["inst_pct_owned"]      = round(pct_by_sym[t], 4)
                out[t]["inst_top_holder_pct"] = round(top_by_sym[t], 4)

    # Insider flows (USA)
    flows = canon.get("flow")
    if flows and flows.rows and market_name == "usa":
        cutoff = asof - timedelta(days=90)
        buys: dict[str, float] = {}
        sells: dict[str, float] = {}
        for f in flows.rows:
            if f.symbol is None or f.asof < cutoff: continue
            if f.symbol not in universe: continue
            if f.kind == "insider_buy":  buys[f.symbol] = buys.get(f.symbol, 0.0) + f.value_native
            if f.kind == "insider_sell": sells[f.symbol] = sells.get(f.symbol, 0.0) + f.value_native
        for t in universe:
            b = buys.get(t, 0.0); s = sells.get(t, 0.0)
            out[t]["insider_buy_90d"]  = round(b, 2)
            out[t]["insider_sell_90d"] = round(s, 2)
            out[t]["insider_net_90d"]  = round(b - s, 2)

    # FII/DII (India, market-level; broadcast to every ticker)
    if flows and flows.rows and market_name == "india":
        cutoff = asof - timedelta(days=5)
        fii = 0.0; dii = 0.0
        for f in flows.rows:
            if f.asof < cutoff: continue
            if f.kind == "foreign_institutional":  fii += f.value_native
            if f.kind == "domestic_institutional": dii += f.value_native
        for t in universe:
            out[t]["fii_net_5d"] = round(fii, 2)
            out[t]["dii_net_5d"] = round(dii, 2)

    return out
