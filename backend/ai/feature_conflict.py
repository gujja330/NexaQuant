"""AI Feature Conflict Agent v1.0.

Flags tickers where the feature vector shows internally inconsistent signals.
E.g. very strong 1-month momentum AND very poor fundamentals — not necessarily
wrong, but downstream engines should know the picture is mixed. No recommendations.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from backend.ai.base import AgentOutput

VERSION = "v1.0"

CONFLICT_RULES = [
    # (name, description, predicate function using feature dict)
    ("momentum_vs_fundamentals",
      "strong momentum but weak fundamentals",
      lambda r: (r.get("return_20d_pct") or 0) > 8 and (r.get("fund_quality_score") or 50) < 30),
    ("fundamentals_vs_momentum",
      "strong fundamentals but negative momentum",
      lambda r: (r.get("fund_quality_score") or 50) > 70 and (r.get("return_20d_pct") or 0) < -8),
    ("news_vs_price",
      "positive news but price declining",
      lambda r: (r.get("news_sentiment") or 0) > 0.3 and (r.get("return_5d_pct") or 0) < -5),
    ("news_vs_price_neg",
      "negative news but price rising",
      lambda r: (r.get("news_sentiment") or 0) < -0.3 and (r.get("return_5d_pct") or 0) > 5),
    ("insider_vs_sentiment",
      "heavy insider selling but positive sentiment (USA)",
      lambda r: (r.get("insider_net_90d") or 0) < -50_000_000 and (r.get("news_sentiment") or 0) > 0.2),
    ("overbought_extended",
      "overbought (RSI>75) AND far above 52W high (>0)",
      lambda r: (r.get("rsi_14") or 0) > 75 and (r.get("distance_from_52w_high_pct") or -100) > -2),
    ("oversold_extended",
      "oversold (RSI<25) AND deep drawdown (<-20%)",
      lambda r: (r.get("rsi_14") or 100) < 25 and (r.get("max_drawdown_60d_pct") or 0) < -20),
]


def run(df: pd.DataFrame, market_name: str, asof: date | None = None,
         top_k: int = 20) -> AgentOutput:
    if df is None or df.empty:
        return AgentOutput(agent="feature_conflict", version=VERSION, market=market_name,
                             asof=asof or date.today(),
                             headline="No snapshot to check",
                             narrative="Feature Store snapshot empty.",
                             confidence=0.0, caveats=["Empty"])

    findings: list[dict] = []
    for _, row in df.iterrows():
        r = row.to_dict()
        tk = r.get("ticker") or "?"
        for rule_name, desc, pred in CONFLICT_RULES:
            try:
                if pred(r):
                    findings.append({
                        "ticker":       str(tk),
                        "conflict":     rule_name,
                        "description":  desc,
                        # Include the offending values (not a recommendation)
                        "return_20d_pct": r.get("return_20d_pct"),
                        "quality_score":  r.get("fund_quality_score"),
                        "news_sentiment": r.get("news_sentiment"),
                        "return_5d_pct":  r.get("return_5d_pct"),
                        "rsi_14":         r.get("rsi_14"),
                    })
            except Exception:
                continue

    # Top-k by ticker (a ticker with N conflicts is more interesting than a ticker with 1)
    by_ticker: dict[str, int] = {}
    for f in findings:
        by_ticker[f["ticker"]] = by_ticker.get(f["ticker"], 0) + 1
    top_tickers = sorted(by_ticker.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    if not findings:
        head = "No feature conflicts detected."
        narr = ("Every ticker's feature vector reads consistently across momentum · fundamentals · "
                 "news · flows for this snapshot.")
    else:
        head = f"{len(findings)} conflict signal(s) across {len(by_ticker)} tickers."
        lines = [f"  · {tk}: {n} conflict{'s' if n != 1 else ''}"
                  for tk, n in top_tickers[:10]]
        narr = (head + "\n\n" + "\n".join(lines) +
                 "\n\nA conflict is not a verdict — it's a signal that the picture is mixed and "
                 "the downstream engine should weigh the evidence rather than take any single "
                 "dimension at face value.")

    return AgentOutput(
        agent="feature_conflict", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=head, narrative=narr,
        findings=findings[:200],   # cap serialised finding count
        evidence={"n_conflicts": len(findings), "n_tickers_with_conflict": len(by_ticker),
                    "n_rules": len(CONFLICT_RULES)},
        citations=["backend/feature_store"],
        confidence=0.9 if len(df) > 20 else 0.5,
        caveats=[],
        determinism="template",
    )
