"""Fundamentals · Layer 4 · Flow / Sentiment (3 signals)

FII/DII net-flow z-score · Options PCR · Short interest %.

Flow signals are institutional-participation proxies · they lead price
in India (FII/DII) and matter in USA (PCR, SI) around inflection points.
"""
from __future__ import annotations

import math
from typing import Optional


def fii_dii_net_flow_z(fin: dict) -> Optional[float]:
    """z-score of FII+DII net flow over trailing 20 trading days.

    fin["net_flow_series_20d"] · list of daily net flows (₹ crores or $M).
    """
    series = fin.get("net_flow_series_20d")
    if not series or len(series) < 5:
        return None
    try:
        vals = [float(x) for x in series]
        latest = vals[-1]
        mu = sum(vals) / len(vals)
        var = sum((x - mu) ** 2 for x in vals) / max(1, len(vals) - 1)
        sd = math.sqrt(var)
        if sd == 0:
            return 0.0
        return round((latest - mu) / sd, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def options_pcr(fin: dict) -> Optional[float]:
    """Put open interest / Call open interest.

    Contrarian short-term (very high PCR → oversold), momentum medium-term.
    Prefer single-name PCR if available, else fall back to sector PCR.
    """
    if fin.get("put_oi_single_name") is not None and fin.get("call_oi_single_name") is not None:
        try:
            c = float(fin["call_oi_single_name"])
            if c <= 0: return None
            return round(float(fin["put_oi_single_name"]) / c, 4)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    if fin.get("put_oi_sector") is not None and fin.get("call_oi_sector") is not None:
        try:
            c = float(fin["call_oi_sector"])
            if c <= 0: return None
            return round(float(fin["put_oi_sector"]) / c, 4)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    return None


def short_interest_pct(fin: dict) -> Optional[float]:
    """Short_Interest_shares / Float_shares · reported monthly (USA) / approx (India)."""
    for k in ("short_interest_shares", "float_shares"):
        if k not in fin or fin[k] is None:
            return None
    try:
        fl = float(fin["float_shares"])
        if fl <= 0: return None
        return round(float(fin["short_interest_shares"]) / fl, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


LAYER4_FUNCTIONS = {
    "fii_dii_net_flow_z": fii_dii_net_flow_z,
    "options_pcr":        options_pcr,
    "short_interest_pct": short_interest_pct,
}
