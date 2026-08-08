"""Investability Score aggregator · combines all sub-engines.

Wave 1 weights (4 sub-engines active · using data we have):
    Fundamental:     25%
    Technical:       20%
    Governance-lite: 15%
    Liquidity:        5%
    ------------
    Subtotal:        65%  (of full spec)
    Renormalized to: 100% for Wave 1 scoring

Wave 2 will complete with:
    Ownership:  10%
    Sector:     10%
    Macro:       5%
    News:        5%
    Earnings:    5%

Full spec: Sprint K+ Part 26.

Decision thresholds:
    Investability >= 80  · Excellent · STRONG BUY candidate
    Investability >= 70  · Strong    · BUY candidate
    Investability >= 60  · OK        · HOLD existing · watch
    Investability <  60  · REJECT    · Never recommend
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from backend.investability import fundamental, technical, liquidity, governance
from backend.investability import valuation, risk


THRESHOLD_REJECT      = 60
THRESHOLD_HOLD        = 60
THRESHOLD_BUY         = 70
THRESHOLD_STRONG_BUY  = 80

# Wave 1.5 · 6 sub-engines active · fundamental + technical + governance +
# liquidity + valuation + risk. Renormalized to 100%.
# Weights match Sprint K v1.3 Part 26 spec (22/15/13/4/8/7 · but scaled to
# what's shippable now · other 5 engines added in Wave 2 · Sprint K).
WAVE1_WEIGHTS = {
    "fundamental": 22 / 69,    # 31.9%
    "technical":   15 / 69,    # 21.7%
    "governance":  13 / 69,    # 18.8%
    "liquidity":   4  / 69,    # 5.8%
    "valuation":   8  / 69,    # 11.6% · fixes HDFCBANK-false-reject case
    "risk":        7  / 69,    # 10.1% · captures gap + tail + drawdown
}


@dataclass
class Investability:
    ticker: str
    market: str
    asof: str
    score: float                    # 0-100
    verdict: str                    # REJECT | HOLD | BUY | STRONG BUY
    sub_scores: dict                # {engine: score}
    top_drivers: list               # top 3 positive/negative signals
    debug: dict                     # per-engine detail


def _fetch_info(ticker: str, market: str) -> dict:
    """yfinance ticker.info · returns empty dict on any failure."""
    try:
        import yfinance as yf
    except ImportError:
        return {}
    yf_ticker = f"{ticker}.NS" if market.lower() == "india" and not ticker.endswith(".NS") \
                        else ticker
    try:
        return yf.Ticker(yf_ticker).info or {}
    except Exception:
        return {}


def _verdict(score: float) -> str:
    if score >= THRESHOLD_STRONG_BUY: return "STRONG BUY"
    if score >= THRESHOLD_BUY:        return "BUY"
    if score >= THRESHOLD_HOLD:       return "HOLD"
    return "REJECT"


def _top_drivers(debug: dict, n: int = 3) -> list:
    """Extract top-N contributing signals across all engines."""
    all_signals = []
    for eng_name, eng_debug in debug.items():
        for sig_name, sig_data in (eng_debug.get("signals") or {}).items():
            if isinstance(sig_data, dict) and sig_data.get("ok") is not None:
                # Weight × ok = contribution (positive if hit)
                contrib = float(sig_data.get("weight", 1.0)) * (1 if sig_data.get("ok") else -0.5)
                all_signals.append({
                    "engine":     eng_name,
                    "signal":     sig_name,
                    "ok":         sig_data.get("ok"),
                    "contrib":    round(contrib, 2),
                })
    all_signals.sort(key=lambda s: abs(s["contrib"]), reverse=True)
    return all_signals[:n]


def score_ticker(ticker: str, market: str, root: Path,
                     info: dict | None = None) -> Investability:
    """Compute Investability Score for a single ticker.

    If `info` is None, fetches from yfinance (network call).
    """
    if info is None:
        info = _fetch_info(ticker, market)

    fund_score,  fund_dbg  = fundamental.score(info)
    tech_score,  tech_dbg  = technical.score(ticker, market, root)
    gov_score,   gov_dbg   = governance.score(info)
    liq_score,   liq_dbg   = liquidity.score(ticker, market, root)
    val_score,   val_dbg   = valuation.score(info, market)
    risk_score,  risk_dbg  = risk.score(ticker, market, root, info=info)

    weighted = (
        WAVE1_WEIGHTS["fundamental"] * fund_score +
        WAVE1_WEIGHTS["technical"]   * tech_score +
        WAVE1_WEIGHTS["governance"]  * gov_score +
        WAVE1_WEIGHTS["liquidity"]   * liq_score +
        WAVE1_WEIGHTS["valuation"]   * val_score +
        WAVE1_WEIGHTS["risk"]        * risk_score
    )
    final = round(weighted, 1)

    debug = {
        "fundamental": fund_dbg,
        "technical":   tech_dbg,
        "governance":  gov_dbg,
        "liquidity":   liq_dbg,
        "valuation":   val_dbg,
        "risk":        risk_dbg,
    }

    return Investability(
        ticker=ticker,
        market=market,
        asof=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        score=final,
        verdict=_verdict(final),
        sub_scores={"fundamental": fund_score, "technical": tech_score,
                        "governance": gov_score,   "liquidity": liq_score,
                        "valuation": val_score,    "risk": risk_score},
        top_drivers=_top_drivers(debug),
        debug=debug,
    )


def score_universe(tickers: list, market: str, root: Path,
                       cache_path: Path | None = None) -> dict:
    """Score every ticker in a universe. Caches results by (market, ticker)
    to avoid repeated yfinance calls.

    Returns {ticker: Investability}.
    """
    results = {}
    cache = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    market_cache = cache.setdefault(market.lower(), {})

    for tk in tickers:
        # Try cache first (info fetch is the slow part)
        cached_info = market_cache.get(tk, {}).get("info")
        inv = score_ticker(tk, market, root, info=cached_info)
        results[tk] = inv
        market_cache[tk] = {"score": inv.score, "verdict": inv.verdict,
                                    "asof": inv.asof}

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2, default=str),
                                        encoding="utf-8")

    return results


def emit_report(root: Path, market: str, results: dict) -> Path:
    """Emit investability scores to reports/investability_{market}.json"""
    out = root / "reports" / f"investability_{market.lower()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engine":       "investability.v1.wave1",
        "market":       market,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_scored":     len(results),
        "verdict_counts": {},
        "results":      [asdict(inv) for inv in results.values()],
    }
    counts = {"REJECT": 0, "HOLD": 0, "BUY": 0, "STRONG BUY": 0}
    for inv in results.values():
        counts[inv.verdict] = counts.get(inv.verdict, 0) + 1
    payload["verdict_counts"] = counts
    out.write_text(json.dumps(payload, indent=2, default=str),
                       encoding="utf-8")
    return out
