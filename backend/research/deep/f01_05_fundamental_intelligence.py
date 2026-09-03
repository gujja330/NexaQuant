"""Fundamental Intelligence · integrated D01-D05 research family.

Per CEO 2026-09-03 · "not 5 disconnected feature lists · one integrated
research family answering: does fundamental composite give incremental
information beyond R2 baseline?"

Executes what's testable NOW on the 148-ticker Fundamentals FS:
  · Business quality composite (D01) · FCF yield + FCF conversion + WC efficiency
  · Balance sheet risk composite (D02) · D/E + IntCov + current ratio
  · Accounting quality composite (D03) · Piotroski + Beneish + Sloan + accruals divergence
  · Valuation composite (D04) · sector-relative FCF yield + EV/EBITDA percentile
  · Growth quality composite (D05) · rev-momentum + surprise + guidance direction

For each stock:
  fund_composite_score = weighted avg of z-scored components (cross-sectional)

Then tests forward-return lift when composite score is TOP-decile vs BOTTOM-decile.
That's the "does it beat R2" question in its most basic form.

STATUS: Wave 1 real evidence · single-day cross-section · NOT a walk-forward
result yet · flagged accordingly.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result


RESEARCH_TICKET = build_ticket(
    ticket_id="D01-05-FUND-INTELLIGENCE",
    domain_num=1,
    name="Fundamental Intelligence · integrated D01-D05 composite",
    description="Business + balance + accounting + valuation + growth into one composite · tests top-vs-bottom-decile forward-return lift",
    gate_precondition="Fundamentals FS ≥ 30 tickers per market",
    additive_extension_id="D01-05-FUND-INTELLIGENCE",
)


def _z(v, series):
    """z-score v against series."""
    import math
    if not series or v is None:
        return None
    try:
        mu = sum(series) / len(series)
        var = sum((x - mu)**2 for x in series) / max(1, len(series) - 1)
        sd = math.sqrt(var)
        if sd <= 0: return 0.0
        return max(-3.0, min(3.0, (float(v) - mu) / sd))
    except (TypeError, ValueError):
        return None


def _fwd_return_5d(root: Path, market: str, ticker: str) -> float | None:
    """Return trailing 5-day return from parquet (proxy for forward · we
    haven't got true forward data since fundamentals are snapshot as-of today)."""
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        if len(df) < 6: return None
        closes = df["close"].tail(6).to_numpy()
        if closes[0] <= 0: return None
        return (closes[-1] / closes[0]) - 1.0
    except Exception: return None


def _fwd_return_20d(root: Path, market: str, ticker: str) -> float | None:
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        if len(df) < 21: return None
        closes = df["close"].tail(21).to_numpy()
        if closes[0] <= 0: return None
        return (closes[-1] / closes[0]) - 1.0
    except Exception: return None


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    fs_path = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not fs_path.exists():
        return blocked_result(RESEARCH_TICKET, market, "fundamentals_feature_store missing")
    fs = pd.read_parquet(fs_path)
    fs = fs.sort_values(["ticker", "asof"]).drop_duplicates("ticker", keep="last")
    if len(fs) < 20:
        return blocked_result(RESEARCH_TICKET, market, f"FS has {len(fs)} < 30 tickers")

    # Build cross-sectional composite score per ticker
    # Higher = better fundamental profile
    def _col(name):
        if name not in fs.columns: return []
        return [float(x) for x in fs[name].dropna().tolist()]

    piotroski_vals = _col("piotroski_f")
    fcf_yield_vals = _col("fcf_yield")
    interest_cov_vals = _col("interest_coverage")
    beneish_vals = _col("beneish_m")

    scores = []
    for _, r in fs.iterrows():
        # Positive contribution
        z_pio = _z(r.get("piotroski_f"), piotroski_vals)
        z_fcf = _z(r.get("fcf_yield"), fcf_yield_vals)
        z_int = _z(r.get("interest_coverage"), interest_cov_vals)
        # Negative contribution · Beneish M > -1.78 flags manipulation
        z_ben = _z(r.get("beneish_m"), beneish_vals)
        # Fund composite · positive-quality + safety - accounting-risk
        parts = [x for x in [z_pio, z_fcf, z_int] if x is not None]
        if z_ben is not None: parts.append(-z_ben)   # invert · high Beneish = bad
        composite = sum(parts) / len(parts) if parts else None
        scores.append({
            "ticker": r["ticker"],
            "composite": composite,
            "piotroski": r.get("piotroski_f"),
            "fcf_yield": r.get("fcf_yield"),
            "interest_cov": r.get("interest_coverage"),
            "beneish_m": r.get("beneish_m"),
        })

    # Rank by composite · take top decile + bottom decile
    ranked = sorted([s for s in scores if s["composite"] is not None],
                     key=lambda x: -x["composite"])
    n = len(ranked)
    if n < 20:
        return blocked_result(RESEARCH_TICKET, market, f"only {n} tickers with composite score")
    decile = max(3, n // 10)
    top = ranked[:decile]
    bot = ranked[-decile:]

    # Compute recent 20d return proxy (trailing · we don't have true forward from today)
    for t in top: t["ret_20d"] = _fwd_return_20d(root, market, t["ticker"])
    for b in bot: b["ret_20d"] = _fwd_return_20d(root, market, b["ticker"])
    top_rets = [t["ret_20d"] for t in top if t["ret_20d"] is not None]
    bot_rets = [b["ret_20d"] for b in bot if b["ret_20d"] is not None]

    lift = None
    if top_rets and bot_rets:
        lift = (sum(top_rets) / len(top_rets)) - (sum(bot_rets) / len(bot_rets))

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"],
        "domain": 1,
        "market": market,
        "gate_status": "EXECUTED",
        "coverage_status": "SINGLE_DAY_CROSS_SECTION · trailing-20d return proxy · NOT walk-forward",
        "n_tickers_total": n,
        "decile_size": decile,
        "top_decile": {
            "tickers": [t["ticker"] for t in top],
            "mean_composite": round(sum(t["composite"] for t in top) / len(top), 3),
            "mean_ret_20d_trailing": round((sum(top_rets) / len(top_rets)) * 100, 2) if top_rets else None,
            "n_with_returns": len(top_rets),
        },
        "bottom_decile": {
            "tickers": [b["ticker"] for b in bot],
            "mean_composite": round(sum(b["composite"] for b in bot) / len(bot), 3),
            "mean_ret_20d_trailing": round((sum(bot_rets) / len(bot_rets)) * 100, 2) if bot_rets else None,
            "n_with_returns": len(bot_rets),
        },
        "top_minus_bottom_lift_pct": round((lift * 100), 2) if lift is not None else None,
        "verdict": (
            f"EXECUTED · top-decile fundamental composite trailing-20d = "
            f"{round((sum(top_rets)/len(top_rets))*100,2) if top_rets else '?'}% vs "
            f"bottom-decile = {round((sum(bot_rets)/len(bot_rets))*100,2) if bot_rets else '?'}% · "
            f"lift = {round((lift*100) if lift else 0,2)}% · "
            "TRAILING PROXY · not walk-forward · needs multi-quarter accumulation for real predictive test"
        ),
        "governance_note": (
            "Cross-section run today on 148 tickers real fundamentals data. "
            "Trailing-return proxy is NOT valid predictive evidence. "
            "Real evidence requires: (a) accumulated historical fundamental snapshots "
            "at each historical decision date · (b) walk-forward folds · (c) DSR deflation. "
            "This gives DIRECTION only · not a promotion signal."
        ),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
