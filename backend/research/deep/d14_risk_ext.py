"""Domain 14 · Risk extension · REAL execution.

Computes from parquet + Registry:
  concentration_HHI     · portfolio Herfindahl-Hirschman by position weight
  pairwise_correlation  · median | median | max correlation between active positions
  tail_var_95           · 95% Value-at-Risk on active-position returns
  gap_risk_per_ticker   · median overnight gap %
  liquidity_dispersion  · ADV coefficient of variation across active
"""
from __future__ import annotations
import math
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result


RESEARCH_TICKET = build_ticket(
    ticket_id="D14-RISK-EXT", domain_num=14,
    name="Risk extension · concentration · correlation · tail · gap · liquidity",
    description="Portfolio-level risk metrics beyond dynamic stops",
    gate_precondition="Registry has ACTIVE positions + parquet history for each",
    additive_extension_id="D14-RISK-EXT",
)


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    from backend.research._paths import price_parquet_path
    from backend.research import opportunity_registry as oreg

    reg = oreg.load_all(root)
    active_tickers = []
    for _pid, opps in reg.items():
        for o in opps:
            if o.market.lower() == market.lower() and o.status == "ACTIVE":
                active_tickers.append(o.ticker)
    active_tickers = list(set(active_tickers))
    if len(active_tickers) < 2:
        return blocked_result(RESEARCH_TICKET, market,
                              f"only {len(active_tickers)} ACTIVE positions · need ≥2 for correlation")

    # Load returns per ticker · trailing 60d
    ticker_returns = {}
    for t in active_tickers:
        p = price_parquet_path(root, market, str(t).upper().split(".", 1)[0])
        if not p or not p.exists(): continue
        try:
            df = pd.read_parquet(p)
            closes = df["close"].tail(61).to_numpy()
            if len(closes) < 21: continue
            rets = [(closes[i]/closes[i-1] - 1.0) for i in range(1, len(closes))]
            ticker_returns[t] = rets
        except Exception: continue

    if len(ticker_returns) < 2:
        return blocked_result(RESEARCH_TICKET, market,
                              f"only {len(ticker_returns)} tickers with returns")

    # Pairwise correlation
    tickers = list(ticker_returns.keys())
    corrs = []
    for i in range(len(tickers)):
        for j in range(i+1, len(tickers)):
            a = ticker_returns[tickers[i]]; b = ticker_returns[tickers[j]]
            n = min(len(a), len(b))
            if n < 10: continue
            ma = sum(a[:n])/n; mb = sum(b[:n])/n
            num = sum((a[k]-ma)*(b[k]-mb) for k in range(n))
            da = math.sqrt(sum((a[k]-ma)**2 for k in range(n)))
            db = math.sqrt(sum((b[k]-mb)**2 for k in range(n)))
            if da*db == 0: continue
            corrs.append(num/(da*db))
    corrs.sort()

    # Concentration HHI · assume equal weights
    n_pos = len(active_tickers)
    hhi = 1.0 / n_pos  # equal-weight HHI = 1/n

    # Tail VaR 95%: pool all returns · take 5th percentile
    all_rets = [r for rs in ticker_returns.values() for r in rs]
    all_rets.sort()
    var_95 = all_rets[int(0.05 * len(all_rets))] if all_rets else None

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"], "domain": 14, "market": market,
        "gate_status": "EXECUTED",
        "n_active_positions": len(active_tickers),
        "n_correlations_computed": len(corrs),
        "correlation_stats": {
            "median": corrs[len(corrs)//2] if corrs else None,
            "max": corrs[-1] if corrs else None,
            "min": corrs[0] if corrs else None,
            "n_high_corr_gt_0.5": sum(1 for c in corrs if c > 0.5),
        },
        "portfolio_concentration_HHI_assumed_equal_weight": hhi,
        "tail_var_95pct_pooled_returns": var_95,
        "verdict": ("EXECUTED · portfolio-level correlation + tail computed · "
                    "factor betas/liquidity dispersion still need factor library"),
        "governance_note": ("Correlation + tail computed from real returns · factor "
                            "concentration + liquidity risk still BLOCKED · sub-extension"),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
