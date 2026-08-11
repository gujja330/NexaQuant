"""AEGIS USA · Adaptive Recommendation Engine.

Emits usa/reports/recommendations.json matching India's schema shape.
Deterministic, technicals-only (no fundamentals/news pipeline, same
as India in practice).

All prices in USD ($).
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from recommendations.lib import technicals, entry_exit                                  # noqa: E402


_ROOT = Path(__file__).resolve().parents[3]
_USA  = Path(__file__).resolve().parents[2]


# ── Action mapping — same buckets as India's Investment Decision Score
def score_to_action(score: float | None) -> str:
    if score is None: return "Hold"
    if score >= 80:   return "Strong-Buy"
    if score >= 70:   return "Buy"
    if score >= 60:   return "Accumulate"
    if score >= 45:   return "Hold"
    if score >= 30:   return "Reduce"
    return "Sell"


def score_to_classification(score: float | None) -> str:
    if score is None: return "Neutral"
    if score >= 80:   return "Strong-Bullish"
    if score >= 65:   return "Bullish"
    if score >= 45:   return "Neutral"
    if score >= 30:   return "Bearish"
    return "Strong-Bearish"


def confidence_from_dims(dims: dict) -> float:
    """Confidence 0..1 — higher when all 6 dims agree (low dispersion)."""
    vals = [v for v in dims.values() if isinstance(v, (int, float))]
    if len(vals) < 4: return 0.5
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    # High variance → low confidence. Var can reach ~2500 for extremes.
    conf = max(0.3, min(1.0, 1.0 - (var / 2500)))
    return round(conf, 2)


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Adaptive Recommendation Engine")
    print("=" * 70)

    universe_path = _USA / "reports" / "universe.json"
    if not universe_path.exists():
        print("FATAL: universe.json missing. Run build_universe.py first.")
        return 1

    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    tickers  = universe.get("tickers") or []
    if not tickers:
        print("FATAL: no tickers in universe.")
        return 1

    spx = technicals.load_spx()
    if spx is None:
        print("WARN: ^GSPC index not on disk — RS dimension will fall back to neutral.")

    recs: list[dict] = []
    for i, spec in enumerate(sorted(tickers, key=lambda x: str(x.get("symbol"))), 1):
        symbol   = str(spec.get("symbol"))
        sector   = spec.get("sector") or "?"
        industry = spec.get("industry") or "?"
        exchange = spec.get("exchange") or "?"

        close = technicals.load_close(symbol)
        if close is None:
            print(f"  [{i:>2}/{len(tickers)}] {symbol:<8} SKIP · no price data")
            continue

        dims = technicals.compute_dimensions(close, spx)
        score = technicals.technical_score(dims)
        action = score_to_action(score)
        classification = score_to_classification(score)
        confidence = confidence_from_dims(dims)
        ee = entry_exit.compute_levels(close, score, action)

        # Sector / industry scores derived from ticker's own tech score by
        # sector-mean rollup (computed in a second pass below)
        rec = {
            "ticker":                 symbol,
            "sector":                 sector,
            "industry":               industry,
            "exchange":               exchange,
            "recommendation":         action,
            "classification":         classification,
            "composite_decision_score": score,
            "conviction_pct":         score,
            "confidence":             confidence,
            "score":                  score,
            "action":                 "NEW_POSITION" if action in ("Strong-Buy", "Buy") else "HOLD",
            "sector_score":           None,        # filled in pass 2
            "sector_classification":  None,        # filled in pass 2
            "industry_score":         None,        # filled in pass 2
            "industry_classification": None,       # filled in pass 2
            "global_posture":         "Neutral",
            "global_score":           50.0,
            "overall_rank":           None,        # filled after sort
            "sector_rank":            None,
            "industry_rank":          None,
            "in_target_portfolios":   [],
            "currently_held":         False,
            "current_weight":         None,
            "unrealised_pnl_pct":     None,
            "reasons_for":            [],
            "reasons_against":        [],
            "entry_exit":             ee,
        }

        # Reasons — humanized flags for the Decision Card
        if score is not None and score >= 80:
            rec["reasons_for"].append(f"company_score_top_decile:{score}")
        if dims.get("dim_momentum") and dims["dim_momentum"] >= 70:
            rec["reasons_for"].append(f"positive_momentum:{dims['dim_momentum']}")
        if dims.get("dim_trend") and dims["dim_trend"] >= 70:
            rec["reasons_for"].append(f"trend_up:{dims['dim_trend']}")
        if dims.get("dim_rs_spx") and dims["dim_rs_spx"] >= 70:
            rec["reasons_for"].append(f"beating_spx:{dims['dim_rs_spx']}")
        if dims.get("dim_volatility") and dims["dim_volatility"] >= 70:
            rec["reasons_for"].append(f"volatility_moderate:{dims['dim_volatility']}")

        if score is not None and score < 40:
            rec["reasons_against"].append(f"weak_composite:{score}")
        if dims.get("dim_drawdown") and dims["dim_drawdown"] < 40:
            rec["reasons_against"].append(f"deep_drawdown:{dims['dim_drawdown']}")
        if dims.get("dim_rs_spx") and dims["dim_rs_spx"] < 30:
            rec["reasons_against"].append(f"underperforming_spx:{dims['dim_rs_spx']}")
        if dims.get("dim_volatility") and dims["dim_volatility"] < 30:
            rec["reasons_against"].append(f"high_volatility:{dims['dim_volatility']}")

        # Attach dims for downstream consumers (Fusion, DA)
        rec["dimensions"] = dims

        recs.append(rec)
        # 2026-08-06 · defensive None-formatting fix · score/confidence can
        # be None for tickers with insufficient data · crashed USA pipeline
        _score_str = f"{score:>5}" if score is not None else "  —  "
        _conf_str = f"{confidence:.2f}" if confidence is not None else " — "
        print(f"  [{i:>2}/{len(tickers)}] {symbol:<8} {sector:<24} "
              f"score={_score_str}  {action:<11}  conf={_conf_str}")

    # ── Pass 2: sector / industry rollups
    from collections import defaultdict
    sector_scores: dict[str, list[float]] = defaultdict(list)
    industry_scores: dict[str, list[float]] = defaultdict(list)
    for r in recs:
        if r["composite_decision_score"] is not None:
            sector_scores[r["sector"]].append(r["composite_decision_score"])
            industry_scores[r["industry"]].append(r["composite_decision_score"])

    sector_mean = {k: round(sum(v) / len(v), 2) for k, v in sector_scores.items()}
    industry_mean = {k: round(sum(v) / len(v), 2) for k, v in industry_scores.items()}
    for r in recs:
        r["sector_score"]           = sector_mean.get(r["sector"])
        r["sector_classification"]  = score_to_classification(r["sector_score"])
        r["industry_score"]         = industry_mean.get(r["industry"])
        r["industry_classification"] = score_to_classification(r["industry_score"])

    # Sort by composite desc, then assign ranks
    recs.sort(key=lambda r: (r["composite_decision_score"] or -1), reverse=True)
    for i, r in enumerate(recs, 1):
        r["overall_rank"] = i

    # Per-sector rank
    sector_counts: dict[str, int] = defaultdict(int)
    for r in recs:
        sector_counts[r["sector"]] += 1
        r["sector_rank"] = sector_counts[r["sector"]]
    # Per-industry rank
    industry_counts: dict[str, int] = defaultdict(int)
    for r in recs:
        industry_counts[r["industry"]] += 1
        r["industry_rank"] = industry_counts[r["industry"]]

    # Summary
    action_counts: dict[str, int] = defaultdict(int)
    for r in recs:
        action_counts[r["recommendation"]] += 1

    # ─────────────────────────────────────────────────────────────
    # 2026-08-11 CEO P0 pipeline hygiene · make universe semantics
    # explicit. This file (usa/reports/recommendations.json) is a
    # WHOLE-UNIVERSE SCAN of every S&P ticker with a technical score.
    # It is NOT the actionable selected set. The canonical selected
    # set is emitted by Sprint 3 Recommendation Intelligence v3 into
    # usa/reports/recommendations_v3.json (currently 15 tickers).
    #
    # Downstream code (P0 outcome dataset, attribution, portfolio
    # construction, delivery) MUST read `universe_role` and behave
    # accordingly. See docs/AEGIS_UNIVERSE_ROLES.md.
    # ─────────────────────────────────────────────────────────────
    out = {
        "engine":                  "usa_adaptive_recommendations",
        "version":                 "v1.0",
        "market":                  "USA",
        "currency":                "USD",
        "currency_symbol":         "$",
        "run_utc":                 datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "universe_role":           "universe_scan",
        "actionable_selection_file": "recommendations_v3.json",
        "universe_role_note":      (
            "Whole-universe technical scan. NOT the actionable selected "
            "set. Selected set = recommendations_v3.json (Sprint 3 "
            "Recommendation Intelligence). P0 outcome dataset ingests "
            "position_store + rank_history only — never this file."
        ),
        "n_companies_evaluated":   len(recs),
        "n_currently_held":        0,
        "n_in_target_portfolios":  0,
        "min_target_sharpe":       None,
        "action_counts":           dict(action_counts),
        "sector_scores":           sector_mean,
        "recommendations":         recs,
    }

    out_path = _USA / "reports" / "recommendations.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print()
    print(f"  actions:  {dict(action_counts)}")
    print(f"  written:  {out_path.relative_to(_ROOT)} ({out_path.stat().st_size / 1024:.1f} KB)")
    print(f"  elapsed:  {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
