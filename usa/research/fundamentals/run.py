"""AEGIS USA · Fundamentals Ingestion v1.0.

Pulls fundamental snapshots from yfinance for every ticker in the
active universe. Emits usa/reports/fundamentals.json with:

  Per ticker:
    - pe_ratio, forward_pe, peg_ratio, price_to_book
    - eps_trailing, eps_forward
    - earnings_growth, revenue_growth
    - debt_to_equity, roe, roa, profit_margin
    - market_cap, market_cap_tier (mega/large/mid/small)
    - beta, dividend_yield, payout_ratio, book_value
    - fundamental_score (0-100 composite)
    - fundamental_classification (Strong / Fair / Weak)

Deterministic scoring — no random state.
All values in USD ($).
"""
from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import yfinance as yf
except ImportError:
    print("FATAL: yfinance not installed."); sys.exit(1)

_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]


def _get(info: dict, key: str) -> float | None:
    v = info.get(key)
    if v is None: return None
    try:    return float(v)
    except Exception: return None


def market_cap_tier(mc: float | None) -> str:
    if mc is None: return "unknown"
    if mc >= 200e9: return "mega_cap"
    if mc >= 10e9:  return "large_cap"
    if mc >= 2e9:   return "mid_cap"
    if mc >= 300e6: return "small_cap"
    return "micro_cap"


def _score_0_100(x: float, low_good: float, high_good: float, invert: bool = False) -> float | None:
    """Map x → 0..100 with linear interpolation. If invert=True, LOW x scores high."""
    if x is None: return None
    if high_good == low_good: return 50.0
    if invert:
        low_good, high_good = high_good, low_good
    if x <= low_good:  return 0.0
    if x >= high_good: return 100.0
    return (x - low_good) / (high_good - low_good) * 100.0


def compute_fundamental_score(f: dict) -> tuple[float | None, dict]:
    """6-dimension fundamental composite score (0..100)."""
    dims: dict[str, float | None] = {}

    # Valuation — lower PE/PB score higher (invert)
    pe = f.get("pe_ratio")
    if pe and pe > 0:
        dims["valuation"] = _score_0_100(pe, low_good=15, high_good=50, invert=True)
    else:
        dims["valuation"] = None

    # PEG — lower is better; 1.0 = fair, 0.5 = great, 3.0 = expensive
    peg = f.get("peg_ratio")
    if peg and peg > 0:
        dims["peg"] = _score_0_100(peg, low_good=0.5, high_good=3.0, invert=True)
    else:
        dims["peg"] = None

    # Growth (earnings + revenue combined)
    eg = f.get("earnings_growth"); rg = f.get("revenue_growth")
    growth_vals = [v for v in (eg, rg) if v is not None]
    if growth_vals:
        avg_growth = sum(growth_vals) / len(growth_vals)
        dims["growth"] = _score_0_100(avg_growth, low_good=0.0, high_good=0.25)
    else:
        dims["growth"] = None

    # Profitability — ROE + margins
    roe = f.get("roe"); pm = f.get("profit_margin")
    if roe and pm:
        prof_score = (
            (_score_0_100(roe, low_good=0.05, high_good=0.30) or 0) +
            (_score_0_100(pm, low_good=0.05, high_good=0.30) or 0)
        ) / 2
        dims["profitability"] = prof_score
    else:
        dims["profitability"] = _score_0_100(roe, low_good=0.05, high_good=0.30) or \
                                 _score_0_100(pm, low_good=0.05, high_good=0.30)

    # Leverage — lower D/E scores higher (invert). Note: yfinance stores as %
    de = f.get("debt_to_equity")
    if de is not None:
        # yfinance debtToEquity is often 0-500 range (%)
        de_pct = de if de < 10 else de / 100.0
        dims["leverage"] = _score_0_100(de_pct, low_good=0.1, high_good=2.0, invert=True)
    else:
        dims["leverage"] = None

    # Dividend + payout stability (optional booster)
    dy = f.get("dividend_yield")
    if dy is not None:
        dy_pct = dy if dy < 1 else dy / 100.0
        dims["dividend"] = _score_0_100(dy_pct, low_good=0.0, high_good=0.05)
    else:
        dims["dividend"] = None

    # Weighted composite
    weights = {
        "valuation":     0.25,
        "peg":           0.15,
        "growth":        0.25,
        "profitability": 0.20,
        "leverage":      0.10,
        "dividend":      0.05,
    }
    total_w = 0.0; total_v = 0.0
    for k, w in weights.items():
        v = dims.get(k)
        if v is None: continue
        total_w += w
        total_v += w * v
    composite = round(total_v / total_w, 2) if total_w > 0 else None
    return composite, {k: (round(v, 2) if v is not None else None) for k, v in dims.items()}


def classify(score: float | None) -> str:
    if score is None: return "unrated"
    if score >= 70: return "Strong"
    if score >= 50: return "Fair"
    if score >= 30: return "Weak"
    return "Very Weak"


def fetch_one(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception as e:
        return {"symbol": symbol, "available": False, "error": str(e)[:120]}
    if not info or info.get("regularMarketPrice") is None:
        return {"symbol": symbol, "available": False, "error": "empty info"}

    de = _get(info, "debtToEquity")
    dy = _get(info, "dividendYield")

    f = {
        "symbol":            symbol,
        "available":         True,
        "as_of_utc":         datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "pe_ratio":          _get(info, "trailingPE"),
        "forward_pe":        _get(info, "forwardPE"),
        "peg_ratio":         _get(info, "pegRatio"),
        "price_to_book":     _get(info, "priceToBook"),
        "eps_trailing":      _get(info, "trailingEps"),
        "eps_forward":       _get(info, "forwardEps"),
        "earnings_growth":   _get(info, "earningsGrowth"),
        "revenue_growth":    _get(info, "revenueGrowth"),
        "debt_to_equity":    de,
        "roe":               _get(info, "returnOnEquity"),
        "roa":               _get(info, "returnOnAssets"),
        "profit_margin":     _get(info, "profitMargins"),
        "market_cap":        _get(info, "marketCap"),
        "beta":              _get(info, "beta"),
        "dividend_yield":    dy,
        "payout_ratio":      _get(info, "payoutRatio"),
        "book_value":        _get(info, "bookValue"),
    }
    f["market_cap_tier"] = market_cap_tier(f["market_cap"])
    composite, dims = compute_fundamental_score(f)
    f["fundamental_score"] = composite
    f["fundamental_dimensions"] = dims
    f["fundamental_classification"] = classify(composite)
    return f


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Fundamentals Ingestion v1.0")
    print("=" * 70)

    universe = json.loads((_USA / "reports" / "universe.json").read_text(encoding="utf-8"))
    tickers = sorted(set(str(t.get("symbol")) for t in (universe.get("tickers") or [])))

    print(f"  tickers:  {len(tickers)}")
    print(f"  source:   yfinance")
    print()

    result = {}
    for i, sym in enumerate(tickers, 1):
        f = fetch_one(sym)
        result[sym] = f
        score = f.get("fundamental_score")
        cls = f.get("fundamental_classification", "?")
        mc_tier = f.get("market_cap_tier", "?")
        if f.get("available"):
            print(f"  [{i:>2}/{len(tickers)}] {sym:<8} score={score if score is not None else '—':>6}  {cls:<10}  {mc_tier}")
        else:
            print(f"  [{i:>2}/{len(tickers)}] {sym:<8} SKIP · {f.get('error', 'no data')}")
        time.sleep(0.2)   # gentle rate-limit

    # Aggregate summary
    scored = [v for v in result.values() if v.get("fundamental_score") is not None]
    by_tier = {}
    for v in result.values():
        by_tier[v.get("market_cap_tier", "?")] = by_tier.get(v.get("market_cap_tier", "?"), 0) + 1

    out = {
        "engine":       "usa_fundamentals",
        "version":      "v1.0",
        "market":       "USA",
        "currency":     "USD",
        "run_utc":      datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "n_tickers":    len(result),
        "n_scored":     len(scored),
        "by_market_cap_tier": by_tier,
        "avg_score":    round(sum(v["fundamental_score"] for v in scored) / len(scored), 2) if scored else None,
        "tickers":      result,
    }
    (_USA / "reports" / "fundamentals.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")

    print()
    print(f"  scored:    {len(scored)}/{len(result)}")
    print(f"  avg score: {out['avg_score']}")
    print(f"  cap tiers: {by_tier}")
    print(f"  elapsed:   {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
