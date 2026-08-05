"""Runner 3 · Tier 1 · free-feature adapters.

Reads institutional-flow signals from FREE data sources (no vendor spend):
    · FII/DII net flows                       · NSE published bulletins
    · Earnings calendar (days-to-next)        · exchange corporate bulletins
    · Options PCR + open interest change      · NSE F&O free feed

Every adapter is DEFENSIVE:
    · returns neutral (0.0) when data is missing · never crashes
    · marks a `data_available: bool` flag so downstream can weight-down
    · never writes back to the source · read-only

All values normalised to a comparable [-1, +1] score so the model treats
them symmetrically. Raw values also preserved for audit.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Mapping


def _reports_dir(root: Path, market: str) -> Path:
    return root / ("usa/reports" if market == "usa" else "reports")


# ──────────────────────────────────────────────────────────────────────
# FII/DII flows
# ──────────────────────────────────────────────────────────────────────

def fii_dii_signal(root: Path, market: str, asof: str) -> dict:
    """Return {net_flow_crore, fii_score, dii_score, combined_score, available}.

    FII/DII flow files are already ingested by aegis_daily_v2.py step
    `ingest_fii_dii` (India only · reports/fii_dii_flow.json). USA has no
    equivalent · returns neutral.
    """
    if market != "india":
        return {"net_flow_crore": 0.0, "fii_score": 0.0, "dii_score": 0.0,
                    "combined_score": 0.0, "available": False,
                    "reason": "no USA FII/DII equivalent"}
    p = _reports_dir(root, market) / "fii_dii_flow.json"
    if not p.exists():
        return {"net_flow_crore": 0.0, "fii_score": 0.0, "dii_score": 0.0,
                    "combined_score": 0.0, "available": False,
                    "reason": "reports/fii_dii_flow.json missing"}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        # File shape: {"asof", "fii_net_crore", "dii_net_crore", ...}
        fii = float(d.get("fii_net_crore") or 0)
        dii = float(d.get("dii_net_crore") or 0)
        total = fii + dii
        # Normalise · ~2000 crore = strong single-day flow · clip at ±1
        fii_s = max(-1.0, min(1.0, fii / 2000.0))
        dii_s = max(-1.0, min(1.0, dii / 2000.0))
        combined = max(-1.0, min(1.0, total / 4000.0))
        return {"net_flow_crore": round(total, 2),
                    "fii_score": round(fii_s, 3),
                    "dii_score": round(dii_s, 3),
                    "combined_score": round(combined, 3),
                    "available": True, "asof": d.get("asof")}
    except Exception as e:
        return {"net_flow_crore": 0.0, "fii_score": 0.0, "dii_score": 0.0,
                    "combined_score": 0.0, "available": False,
                    "reason": f"parse error: {type(e).__name__}"}


# ──────────────────────────────────────────────────────────────────────
# Earnings calendar
# ──────────────────────────────────────────────────────────────────────

def earnings_signal(root: Path, market: str, ticker: str, asof: str) -> dict:
    """Return {days_to_next_earnings, event_risk_flag, available}.

    Earnings data lands in `usa/data/raw/us/earnings.parquet` (USA · already
    ingested) and `reports/earnings.json` (India · if available). Returns
    neutral when file/ticker missing.
    """
    reports = _reports_dir(root, market)
    if market == "usa":
        p = reports / ".." / "data" / "raw" / "us" / "earnings.parquet"
        p = p.resolve()
        if not p.exists():
            return {"days_to_next_earnings": None, "event_risk_flag": 0,
                        "available": False, "reason": "earnings.parquet missing"}
        try:
            import pandas as pd
            df = pd.read_parquet(p)
            row = df[df["ticker"] == ticker.upper()]
            if row.empty:
                return {"days_to_next_earnings": None, "event_risk_flag": 0,
                            "available": False, "reason": "ticker not in earnings"}
            next_dt = str(row.iloc[0].get("next_earnings_date") or "")
            if not next_dt:
                return {"days_to_next_earnings": None, "event_risk_flag": 0,
                            "available": False, "reason": "no next date"}
            days = (date.fromisoformat(next_dt[:10]) - date.fromisoformat(asof)).days
            return {"days_to_next_earnings": days,
                        "event_risk_flag": 1 if 0 <= days <= 3 else 0,
                        "available": True}
        except Exception as e:
            return {"days_to_next_earnings": None, "event_risk_flag": 0,
                        "available": False, "reason": f"parse error: {type(e).__name__}"}
    p = reports / "earnings.json"
    if not p.exists():
        return {"days_to_next_earnings": None, "event_risk_flag": 0,
                    "available": False, "reason": "reports/earnings.json missing"}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        per = (d.get("per_ticker") or {}).get(ticker) or {}
        next_dt = per.get("next_earnings_date")
        if not next_dt:
            return {"days_to_next_earnings": None, "event_risk_flag": 0,
                        "available": False, "reason": "ticker missing next date"}
        days = (date.fromisoformat(next_dt[:10]) - date.fromisoformat(asof)).days
        return {"days_to_next_earnings": days,
                    "event_risk_flag": 1 if 0 <= days <= 3 else 0,
                    "available": True}
    except Exception as e:
        return {"days_to_next_earnings": None, "event_risk_flag": 0,
                    "available": False, "reason": f"parse error: {type(e).__name__}"}


# ──────────────────────────────────────────────────────────────────────
# Options PCR (put-call ratio)
# ──────────────────────────────────────────────────────────────────────

def options_pcr_signal(root: Path, market: str, ticker: str, asof: str) -> dict:
    """Return {pcr, pcr_score, iv_percentile, available}.

    Options data lands in `reports/options_chain.json` (India NSE F&O · if
    ingested by future step) OR is unavailable. Returns neutral defensively.
    Score: pcr < 0.7 = bullish sentiment · pcr > 1.3 = bearish · 1.0 = neutral.
    """
    reports = _reports_dir(root, market)
    p = reports / "options_chain.json"
    if not p.exists():
        return {"pcr": None, "pcr_score": 0.0, "iv_percentile": None,
                    "available": False, "reason": "options_chain.json missing"}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        per = (d.get("per_ticker") or {}).get(ticker) or {}
        pcr = per.get("pcr")
        if pcr is None:
            return {"pcr": None, "pcr_score": 0.0, "iv_percentile": None,
                        "available": False, "reason": "ticker missing pcr"}
        # Score: 1.0 = neutral · 0.7 = bullish (+0.5) · 1.3 = bearish (-0.5)
        pcr_score = max(-1.0, min(1.0, (1.0 - pcr) * 1.67))
        return {"pcr": round(pcr, 3), "pcr_score": round(pcr_score, 3),
                    "iv_percentile": per.get("iv_percentile"),
                    "available": True}
    except Exception as e:
        return {"pcr": None, "pcr_score": 0.0, "iv_percentile": None,
                    "available": False, "reason": f"parse error: {type(e).__name__}"}


# ──────────────────────────────────────────────────────────────────────
# Aggregate feature vector for one ticker
# ──────────────────────────────────────────────────────────────────────

def build_feature_vector(root: Path, market: str, ticker: str, asof: str,
                              tech_features: Mapping | None = None) -> dict:
    """Return the full feature dict for one (ticker, asof) · Tier 1 features
    only. `tech_features` is the reused technical set from the feature store
    · adapter here layers institutional-flow signals on top."""
    flows = fii_dii_signal(root, market, asof)
    earn = earnings_signal(root, market, ticker, asof)
    pcr = options_pcr_signal(root, market, ticker, asof)

    fv: dict = dict(tech_features or {})
    fv.update({
        # Institutional flow (market-level · same value for all tickers today)
        "flow_combined":           flows["combined_score"],
        "flow_fii":                flows["fii_score"],
        "flow_dii":                flows["dii_score"],
        "flow_available":          int(bool(flows["available"])),
        # Earnings event risk (ticker-level)
        "earn_days_to_next":       earn.get("days_to_next_earnings") or 999,
        "earn_event_risk_flag":    earn.get("event_risk_flag") or 0,
        "earn_available":          int(bool(earn.get("available"))),
        # Options PCR (ticker-level · India F&O only when available)
        "pcr":                     pcr.get("pcr") or 1.0,
        "pcr_score":               pcr.get("pcr_score") or 0.0,
        "pcr_available":           int(bool(pcr.get("available"))),
    })
    return fv
