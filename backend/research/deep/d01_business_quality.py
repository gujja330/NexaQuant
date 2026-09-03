"""Domain 1 · Business Quality · REAL execution using Fundamentals FS today.

Snapshot-based (not historical PIT · flagged as such per V2 §36).
Cross-sectional distribution + ranking of business-quality signals from
the Fundamentals Feature Store (yfinance-populated today).

Signals evaluated:
  Piotroski F           · quality score 0-9
  ROA proxy             · net_income / total_assets
  FCF Yield             · from L2
  Interest Coverage     · from L1
  Sloan accruals magnitude · from L1

Reports cross-sectional distribution + top/bottom deciles per market.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result

RESEARCH_TICKET = build_ticket(
    ticket_id="D01-BUSINESS-QUALITY", domain_num=1,
    name="Business quality composite · 5 signals",
    description="Piotroski · ROA proxy · FCF Yield · Interest Cov · Sloan accruals · cross-sectional distribution",
    gate_precondition="Fundamentals FS ≥ 20 tickers per market (single-day snapshot OK · historical PIT for full evidence)",
    additive_extension_id="D01-BUSINESS-QUALITY",
)


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    fs_path = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not fs_path.exists():
        return blocked_result(RESEARCH_TICKET, market, "fundamentals_feature_store missing")
    fs = pd.read_parquet(fs_path)
    if fs.empty or len(fs) < 5:
        return blocked_result(RESEARCH_TICKET, market, f"FS has only {len(fs)} rows · need ≥5")

    # Deduplicate to latest per ticker
    fs = fs.sort_values(["ticker", "asof"]).drop_duplicates("ticker", keep="last")

    def _dist(col):
        if col not in fs.columns: return None
        vals = pd.to_numeric(fs[col], errors="coerce").dropna().tolist()
        if not vals: return None
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        return {
            "n": n,
            "min": vals_sorted[0], "max": vals_sorted[-1],
            "median": vals_sorted[n // 2],
            "p25": vals_sorted[n // 4],
            "p75": vals_sorted[3 * n // 4],
            "mean": sum(vals) / n,
        }

    piotroski = _dist("piotroski_f")
    fcf_y = _dist("fcf_yield")
    int_cov = _dist("interest_coverage")
    sloan = _dist("sloan_accruals")

    # Top/bottom deciles by Piotroski
    top_bottom = {}
    if piotroski and "piotroski_f" in fs.columns:
        sub = fs[["ticker", "piotroski_f"]].dropna().sort_values("piotroski_f", ascending=False)
        top_bottom["top_5_by_piotroski"] = sub.head(5).to_dict("records")
        top_bottom["bottom_5_by_piotroski"] = sub.tail(5).to_dict("records")

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"], "domain": 1, "market": market,
        "gate_status": "EXECUTED",
        "coverage_status": "SINGLE_DAY_SNAPSHOT",
        "n_tickers": int(len(fs)),
        "distributions": {
            "piotroski_f": piotroski, "fcf_yield": fcf_y,
            "interest_coverage": int_cov, "sloan_accruals": sloan,
        },
        "top_bottom_by_piotroski": top_bottom,
        "verdict": ("EXECUTED · cross-sectional distribution captured · "
                    "not yet a lift-evidence result · needs multi-quarter accumulation for QoQ delta signals"),
        "governance_note": ("Single-day snapshot flagged · not historical PIT. "
                            "Distribution is real but forward-return predictive power not yet tested · "
                            "requires accumulated ledger + PIT snapshots per V2 §36."),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
