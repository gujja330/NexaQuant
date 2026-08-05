"""Global overnight signals ingest · uses yfinance (free).

Daily output: reports/context/global_overnight.json with the last-close
vs prior-close % move for 8 global reference indices + a per-sector
implication map.

Idempotent per asof · defensive if yfinance is throttled.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path


# (yf_ticker, display_name, sector_implications_when_down_pct_gt_1)
# sector_implications: dict of {indian_sector: drag_multiplier}
INDICES = [
    ("^GSPC",  "S&P 500",
     {"Technology": -1.0, "Financials": -0.8, "Industrials": -0.6, "Consumer Discretionary": -0.7}),
    ("^IXIC",  "NASDAQ",
     {"Technology": -1.5, "Communication Services": -1.0, "Consumer Discretionary": -0.5}),
    ("^DJI",   "Dow Jones",
     {"Industrials": -0.8, "Financials": -0.7, "Healthcare": -0.4}),
    ("^N225",  "Nikkei 225",
     {"Consumer Discretionary": -0.4, "Materials": -0.6, "Industrials": -0.5}),
    ("^HSI",   "Hang Seng",
     {"Technology": -0.5, "Materials": -0.7, "Real Estate": -0.4}),
    ("^FTSE",  "FTSE 100",
     {"Energy": -0.6, "Materials": -0.5, "Financials": -0.4}),
    ("^GDAXI", "DAX",
     {"Industrials": -0.5, "Consumer Discretionary": -0.4}),
    ("^NSEI",  "Nifty 50",
     {}),  # India benchmark · no self-drag routing
]


def _yf_latest_change(ticker: str) -> tuple[float | None, str | None]:
    """Return (pct_change, asof_str) for the latest available close."""
    try:
        import yfinance as yf
    except ImportError:
        return None, None
    try:
        # 5 days lookback so we always have prior close even on Monday
        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist.empty or len(hist) < 2:
            return None, None
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        if prev == 0: return None, None
        pct = (last - prev) / prev * 100.0
        asof_str = hist.index[-1].strftime("%Y-%m-%d")
        return round(pct, 3), asof_str
    except Exception:
        return None, None


def ingest_daily(root: Path, asof: str) -> dict:
    """Fetch overnight moves · compute per-Indian-sector implied drag ·
    persist to reports/context/global_overnight.json."""
    now = datetime.now(timezone.utc).isoformat()
    per_index = {}
    sector_drag: dict[str, float] = {}       # cumulative per-sector context pts

    for yft, name, impl in INDICES:
        pct, dt = _yf_latest_change(yft)
        per_index[yft] = {
            "name": name, "pct_change": pct, "close_asof": dt,
            "available": pct is not None,
        }
        # Apply sector implications when the index moved > 1% down
        if pct is not None and pct < -1.0:
            magnitude = min(abs(pct), 5.0)     # cap at 5% for stability
            for sector, mult in impl.items():
                # mult is negative when down → produces negative drag
                drag = magnitude * mult
                sector_drag[sector] = sector_drag.get(sector, 0.0) + drag

    # Round for output
    sector_drag = {k: round(v, 2) for k, v in sector_drag.items()}

    payload = {
        "engine":         "aegis.context.global_overnight.v0.1",
        "asof":           asof,
        "generated_utc":  now,
        "n_indices":      len(INDICES),
        "n_available":    sum(1 for v in per_index.values() if v["available"]),
        "per_index":      per_index,
        "sector_drag":    sector_drag,
        "note":           "Daily overnight close vs prior close · negative sector_drag values reduce confidence for that Indian sector",
    }
    p = root / "reports" / "context" / "global_overnight.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return payload
