"""Domain 6 · Industry/sector cycle · REAL execution from parquet history.

Computes cross-sector momentum + relative strength from actual price history.
Full industry-cycle indicators (RBI/CMIE) still BLOCKED · this covers the
sector-momentum + relative-strength side that IS runnable today.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from backend.research.deep._helpers import build_ticket, blocked_result, emit_result


RESEARCH_TICKET = build_ticket(
    ticket_id="D06-INDUSTRY-CYCLE", domain_num=6,
    name="Industry/sector momentum + relative strength (partial coverage)",
    description="Cross-sector 20d + 60d momentum · relative-strength ranks per sector",
    gate_precondition="Parquet history ≥60 trading days per ticker + sector cache",
    additive_extension_id="D06-INDUSTRY-CYCLE",
)


def evaluate(root: Path, market: str) -> dict:
    import pandas as pd
    from backend.research._paths import price_parquet_dir
    d = price_parquet_dir(root, market)
    if not d.exists():
        return blocked_result(RESEARCH_TICKET, market, "parquet dir missing")

    # Load sector cache
    import json
    sector_map = {}
    for sc_path in (root / "data" / "sector_cache.json",
                     root / "reports" / "sector_cache.json"):
        if sc_path.exists():
            try:
                sc = json.loads(sc_path.read_text(encoding="utf-8"))
                # Support either flat or per-market
                if isinstance(sc, dict):
                    sector_map = sc.get(market, sc)
                break
            except Exception: pass

    # For each ticker · compute 20d + 60d return
    from collections import defaultdict
    per_sector_returns = defaultdict(list)
    per_sector_tickers = defaultdict(list)
    files = list(d.glob("*_D1.parquet"))
    tickers_processed = 0
    for f in files:
        ticker = f.stem.replace("_D1", "").upper()
        try:
            df = pd.read_parquet(f)
            if len(df) < 65: continue
            closes = df["close"].to_numpy()
            r20 = (closes[-1] / closes[-21] - 1.0) if closes[-21] > 0 else 0
            r60 = (closes[-1] / closes[-61] - 1.0) if closes[-61] > 0 else 0
            sector = sector_map.get(ticker) or sector_map.get(f"{ticker}.NS") or "UNKNOWN"
            if isinstance(sector, dict): sector = sector.get("sector", "UNKNOWN")
            per_sector_returns[sector].append({"ticker": ticker, "r20": r20, "r60": r60})
            per_sector_tickers[sector].append(ticker)
            tickers_processed += 1
        except Exception: continue

    if tickers_processed < 10:
        return blocked_result(RESEARCH_TICKET, market,
                              f"only {tickers_processed} tickers with ≥65 bars")

    # Sector-level aggregation
    sector_summary = []
    for sec, entries in per_sector_returns.items():
        if len(entries) < 2: continue
        mean_r20 = sum(e["r20"] for e in entries) / len(entries)
        mean_r60 = sum(e["r60"] for e in entries) / len(entries)
        sector_summary.append({
            "sector": sec, "n_tickers": len(entries),
            "mean_r20": round(mean_r20 * 100, 2),
            "mean_r60": round(mean_r60 * 100, 2),
        })
    sector_summary.sort(key=lambda s: -s["mean_r60"])

    top3 = sector_summary[:3]
    bot3 = sector_summary[-3:]
    universe_r60 = sum(s["mean_r60"] * s["n_tickers"] for s in sector_summary) / sum(s["n_tickers"] for s in sector_summary)

    result = {
        "ticket_id": RESEARCH_TICKET["ticket_id"], "domain": 6, "market": market,
        "gate_status": "EXECUTED",
        "coverage_status": "PARTIAL · sector momentum + RS only · industry-cycle indicators BLOCKED",
        "n_tickers_analyzed": tickers_processed,
        "n_sectors": len(sector_summary),
        "universe_mean_r60_pct": round(universe_r60, 2),
        "top_3_sectors_60d": top3,
        "bottom_3_sectors_60d": bot3,
        "all_sectors": sector_summary,
        "verdict": ("EXECUTED · sector rankings computed · industry-cycle indicators "
                    "(RBI/CMIE) still BLOCKED · declared as sub-extension"),
        "governance_note": ("Partial coverage · momentum + RS covered · pricing power · "
                            "capacity utilisation · input cost cycle still BLOCKED external data"),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit_result(root, RESEARCH_TICKET["ticket_id"], market, result)
    return result
