"""DEV022 portfolio builder.

Orchestrates:
  1. Load DEV020 company_context.json (scored + ranked companies)
  2. For each portfolio type × sizing method, produce a portfolio
  3. Apply constraints
  4. Compute risk analytics
  5. Run stress tests
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from portfolio_construction.lib import allocators, constraints, stress_tests           # noqa: E402
from company_intelligence.lib import company_catalog                                    # noqa: E402


COMPANY_BUNDLE = _ROOT / "reports" / "company_context.json"
CONSTITUENT_PARQ_DIR = _ROOT / "data" / "raw" / "india"


# ── Portfolio types (universe → candidate list) ──────────────────────────────
@dataclass
class PortfolioType:
    key: str
    display_name: str
    top_n: int
    min_confidence: float = 0.5
    min_score: float = 45.0
    allowed_classifications: list[str] = field(default_factory=lambda: [
        "Strong-Bullish", "Bullish", "Neutral"])
    description: str = ""


PORTFOLIO_TYPES: list[PortfolioType] = [
    PortfolioType("top_10",       "Top 10",       10, min_score=55.0),
    PortfolioType("top_20",       "Top 20",       20, min_score=50.0),
    PortfolioType("top_30",       "Top 30",       30, min_score=45.0),
    PortfolioType("concentrated", "Concentrated (Top 5)", 5, min_score=65.0,
                    allowed_classifications=["Strong-Bullish", "Bullish"]),
    PortfolioType("aggressive",   "Aggressive (Top 15 high-momentum)", 15, min_score=60.0,
                    allowed_classifications=["Strong-Bullish", "Bullish"],
                    description="Higher-conviction, higher-turnover configuration"),
    PortfolioType("balanced",     "Balanced (Top 20 diversified)", 20, min_score=50.0),
    PortfolioType("conservative", "Conservative (Top 25, low-vol favoured)", 25,
                    min_score=45.0,
                    allowed_classifications=["Strong-Bullish", "Bullish", "Neutral"]),
    PortfolioType("quality",      "Quality (Top 15 by score×confidence)", 15,
                    min_score=55.0, min_confidence=0.7),
    PortfolioType("momentum",     "Momentum (Top 15 with positive RS)", 15,
                    min_score=60.0,
                    allowed_classifications=["Strong-Bullish", "Bullish"]),
]


def load_price_data() -> dict[str, pd.Series]:
    """Load close series for the whole universe."""
    out = {}
    for parq in CONSTITUENT_PARQ_DIR.glob("*_D1.parquet"):
        ticker = parq.stem.replace("_D1", "")
        try:
            df = pd.read_parquet(parq)
            if not df.empty and "close" in df.columns:
                out[ticker] = df["close"].dropna()
        except Exception:
            continue
    return out


def load_company_context() -> dict | None:
    if not COMPANY_BUNDLE.exists():
        return None
    try:
        return json.load(COMPANY_BUNDLE.open("r", encoding="utf-8"))
    except Exception:
        return None


def _extract_candidates(company_ctx: dict, ptype: PortfolioType) -> list[dict]:
    """Filter and rank candidates for a given portfolio type."""
    scored = [c for c in company_ctx.get("companies", []) if c.get("status") == "computed"]
    # Apply filters
    filtered = [c for c in scored
                 if c["confidence"] >= ptype.min_confidence
                 and c["score"] >= ptype.min_score
                 and c["classification"] in ptype.allowed_classifications]
    # Rank by overall_rank ascending
    filtered.sort(key=lambda c: c["rankings"]["overall_rank"])
    top = filtered[: ptype.top_n]

    # Convert to allocator-friendly dicts
    candidates = []
    for c in top:
        candidates.append({
            "ticker":     c["ticker"],
            "score":      c["score"],
            "confidence": c["confidence"],
            "sector":     c["hierarchy"]["sector_display"],
            "industry":   c["hierarchy"]["industry_display"],
            "overall_rank": c["rankings"]["overall_rank"],
        })
    return candidates


# ── Portfolio construction ───────────────────────────────────────────────────

def build_portfolio(company_ctx: dict, ptype: PortfolioType, allocator_name: str,
                     price_data: dict[str, pd.Series],
                     constr: constraints.Constraints) -> dict:
    """Build a single portfolio."""
    candidates = _extract_candidates(company_ctx, ptype)
    if not candidates:
        return {"portfolio_type": ptype.key, "allocator": allocator_name,
                "status": "no_candidates", "n_candidates": 0}

    allocator_fn = allocators.ALLOCATORS.get(allocator_name)
    if allocator_fn is None:
        return {"portfolio_type": ptype.key, "allocator": allocator_name,
                "status": "unknown_allocator"}

    raw_weights = allocator_fn(candidates, price_data=price_data)
    if not raw_weights:
        return {"portfolio_type": ptype.key, "allocator": allocator_name,
                "status": "allocator_returned_empty"}

    # Build sector/industry lookup
    ticker_to_sector = {c["ticker"]: c["sector"] for c in candidates}
    ticker_to_industry = {c["ticker"]: c["industry"] for c in candidates}

    adjusted, violations = constraints.apply(raw_weights, ticker_to_sector,
                                                ticker_to_industry, constr)

    # Enrich with candidate metadata
    positions = []
    for ticker, weight in sorted(adjusted.items(), key=lambda kv: kv[1], reverse=True):
        cand = next((c for c in candidates if c["ticker"] == ticker), None)
        if cand is None:
            continue
        positions.append({
            "ticker":     ticker,
            "weight":     round(weight, 6),
            "score":      cand["score"],
            "confidence": cand["confidence"],
            "sector":     cand["sector"],
            "industry":   cand["industry"],
            "overall_rank": cand["overall_rank"],
        })

    return {
        "portfolio_type":       ptype.key,
        "portfolio_display":    ptype.display_name,
        "allocator":            allocator_name,
        "status":               "built",
        "n_positions":          len(positions),
        "n_candidates":         len(candidates),
        "cash_allocation_pct":  round(constr.cash_allocation * 100, 2),
        "total_equity_weight":  round(sum(p["weight"] for p in positions), 4),
        "constraints_applied":  asdict(constr),
        "violations":           violations,
        "positions":            positions,
    }


def build_all(company_ctx: dict, allocator_names: list[str],
                portfolio_types: list[PortfolioType],
                price_data: dict[str, pd.Series],
                constr: constraints.Constraints) -> list[dict]:
    """Build every (portfolio_type × allocator) combo."""
    out = []
    for ptype in portfolio_types:
        for allocator in allocator_names:
            p = build_portfolio(company_ctx, ptype, allocator, price_data, constr)
            out.append(p)
    return out
