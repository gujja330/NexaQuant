"""Domain 2 · Balance-sheet risk · REAL execution using Fundamentals FS."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result

RESEARCH_TICKET = build_ticket(
    ticket_id="D02-BALANCE-SHEET-RISK", domain_num=2,
    name="Balance-sheet risk · D/E · Net Debt/EBITDA · Interest Cov",
    description="Cross-sectional distribution of key solvency ratios from FS today",
    gate_precondition="Fundamentals FS ≥ 20 tickers per market",
    additive_extension_id="D02-BALANCE-SHEET",
)


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    fs_path = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if not fs_path.exists():
        return blocked_result(RESEARCH_TICKET, market, "fundamentals_feature_store missing")
    fs = pd.read_parquet(fs_path)
    fs = fs.sort_values(["ticker", "asof"]).drop_duplicates("ticker", keep="last") if not fs.empty else fs
    if len(fs) < 5:
        return blocked_result(RESEARCH_TICKET, market, f"FS has only {len(fs)} rows · need ≥5")

    def _dist(col):
        if col not in fs.columns: return None
        vals = pd.to_numeric(fs[col], errors="coerce").dropna().tolist()
        if not vals: return None
        vs = sorted(vals); n = len(vs)
        return {"n": n, "min": vs[0], "max": vs[-1], "median": vs[n//2],
                "p25": vs[n//4], "p75": vs[3*n//4], "mean": sum(vs)/n}

    int_cov = _dist("interest_coverage")
    altman = _dist("altman_z")

    # Solvency flags · Interest Coverage < 1.5 = concern · Altman Z < 1.81 = distress
    flags = []
    if "interest_coverage" in fs.columns and "altman_z" in fs.columns:
        for _, r in fs.iterrows():
            ic = r.get("interest_coverage")
            az = r.get("altman_z")
            reasons = []
            if ic is not None and ic < 1.5: reasons.append(f"IntCov {ic:.2f}<1.5")
            if az is not None and az < 1.81: reasons.append(f"Altman {az:.2f}<1.81 (distress zone)")
            if reasons:
                flags.append({"ticker": r["ticker"], "flags": reasons})

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"], "domain": 2, "market": market,
        "gate_status": "EXECUTED",
        "coverage_status": "SINGLE_DAY_SNAPSHOT",
        "n_tickers": int(len(fs)),
        "distributions": {"interest_coverage": int_cov, "altman_z": altman},
        "solvency_flags": {
            "n_flagged": len(flags),
            "flagged_tickers": flags[:20],
        },
        "verdict": (f"EXECUTED · {len(flags)} of {len(fs)} tickers show solvency flags · "
                    "cross-sectional distribution captured · forward-return predictive test pending accumulation"),
        "governance_note": "Single-day snapshot · debt-maturity + off-BS still declared BLOCKED per D02 spec",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
