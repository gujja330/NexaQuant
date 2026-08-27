"""AEGIS · Sprint M-R · Fundamentals Coverage Gap Check.

CEO handover 2026-08-27:
> "Fix the fundamentals data gap. Otherwise we're pretending to research
>  fundamentals without adequate coverage."

Measures the ACTUAL coverage of the fundamentals parquet against the
universe of predictions in AEGIS Daily. Reports:

  - fundamentals parquet ticker count
  - AEGIS-daily unique ticker count per market
  - overlap ratio (coverage %)
  - per-column non-null coverage
  - closure plan: which broker/source data enrichment fixes the gap

Emits reports/research/mr_fundamentals_gap_{market}.json + a consolidated
FUNDAMENTALS_GAP_PLAN.md.

Under M-R sandbox rules. Reads only, writes only under reports/research/.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from backend.research.mr_runner import ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_fundamentals_gap_check.v0.1"


def _load_fundamentals(root: Path, market: str) -> tuple:
    import pandas as pd
    p = root / ("data/raw/india/fundamentals.parquet" if market.lower()=="india"
                else "usa/data/raw/us/fundamentals.parquet")
    if not p.exists(): return (0, [], {})
    try:
        d = pd.read_parquet(p)
        cols = list(d.columns)
        # Per-column non-null coverage
        coverage: dict = {}
        for c in cols:
            non_null = int(d[c].notna().sum())
            coverage[c] = {"non_null": non_null,
                           "coverage_pct": round(non_null/max(1,len(d))*100, 2)}
        return (len(d), sorted([str(x).upper() for x in d.index]), coverage)
    except Exception:
        return (0, [], {})


def _load_daily_tickers(root: Path, market: str) -> set:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not p.exists(): return set()
    tks = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip(): continue
        try:
            r = json.loads(ln)
            tk = str(r.get("ticker","")).upper()
            if tk: tks.add(tk)
        except Exception: continue
    return tks


def _load_universe_tickers(root: Path, market: str) -> set:
    base = root / ("usa/data/raw/us" if market.lower()=="usa" else "data/raw/india")
    if not base.exists(): return set()
    return {p.stem.replace("_D1","").upper() for p in base.glob("*_D1.parquet")}


def analyze(root: Path, market: str) -> dict:
    n_fund, fund_tickers, coverage = _load_fundamentals(root, market)
    daily_tickers = _load_daily_tickers(root, market)
    universe = _load_universe_tickers(root, market)

    fund_set = set(fund_tickers)
    daily_covered = daily_tickers & fund_set
    universe_covered = universe & fund_set
    daily_uncovered = daily_tickers - fund_set
    universe_uncovered = universe - fund_set

    return {
        "engine":                 ENGINE_ID,
        "market":                 market.upper(),
        "generated_utc":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_fundamentals_tickers": n_fund,
        "n_universe_tickers":     len(universe),
        "n_daily_pred_tickers":   len(daily_tickers),
        "coverage_of_universe_pct":
                                  round(len(universe_covered)/max(1,len(universe))*100, 2),
        "coverage_of_daily_preds_pct":
                                  round(len(daily_covered)/max(1,len(daily_tickers))*100, 2),
        "per_column_coverage":    coverage,
        "sample_uncovered_daily": sorted(daily_uncovered)[:20],
        "sample_uncovered_universe": sorted(universe_uncovered)[:20],
        "closure_plan": {
            "priority_tickers":   sorted(daily_uncovered),
            "n_priority":         len(daily_uncovered),
            "sources_to_pull_from": [
                ("India: yfinance batch pull for uncovered NSE symbols"
                 " (returnOnEquity, profitMargins, earningsGrowth, "
                 "debtToEquity, trailingPE, priceToBook, quality_score) "
                 "using .NS suffix"),
                "India: NSE bhavcopy for missing shares outstanding",
                ("USA: yfinance batch pull for uncovered S&P 500 tickers "
                 "(same schema)"),
                "USA: Compustat quarterly (paid) if free sources insufficient",
            ],
            "target_coverage_pct": 95,
            "verification":       ("Rerun mr_fundamentals_gap_check after "
                                   "each pull batch · block acceptance below "
                                   "95%."),
        },
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_fundamentals_gap_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def render_console(res: dict):
    print(f"\n======== FUNDAMENTALS GAP · {res['market']} ========")
    print(f"  fundamentals parquet:   {res['n_fundamentals_tickers']} tickers")
    print(f"  universe:               {res['n_universe_tickers']} tickers")
    print(f"  daily-pred tickers:     {res['n_daily_pred_tickers']}")
    print(f"  coverage of universe:   {res['coverage_of_universe_pct']}%")
    print(f"  coverage of daily preds:{res['coverage_of_daily_preds_pct']}%")
    print(f"  per-column non-null:")
    for c, v in list(res['per_column_coverage'].items())[:10]:
        print(f"    {c:22s} {v['non_null']:4d} rows  ({v['coverage_pct']}%)")
    print(f"  uncovered priority tickers ({res['closure_plan']['n_priority']}):")
    for tk in sorted(res['closure_plan']['priority_tickers'])[:15]:
        print(f"    · {tk}")


def render_plan(res_i: dict, res_u: dict) -> str:
    L = ["# Fundamentals Coverage Gap · Closure Plan\n"]
    L.append(f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n")
    for res in (res_i, res_u):
        if not res: continue
        L.append(f"## {res['market']}")
        L.append(f"- Fundamentals parquet: **{res['n_fundamentals_tickers']}** tickers")
        L.append(f"- Universe: **{res['n_universe_tickers']}** tickers")
        L.append(f"- Daily-pred coverage: **{res['coverage_of_daily_preds_pct']}%**")
        L.append(f"- Uncovered daily-pred priority tickers: "
                 f"**{res['closure_plan']['n_priority']}**")
        L.append(f"\n**Closure sources:**")
        for s in res['closure_plan']['sources_to_pull_from']:
            L.append(f"- {s}")
        L.append(f"\n**Target coverage:** {res['closure_plan']['target_coverage_pct']}% "
                 f"of daily-pred tickers")
        L.append(f"\n**Priority ticker list (first 30):**")
        L.append("```")
        for tk in sorted(res['closure_plan']['priority_tickers'])[:30]:
            L.append(f"  {tk}")
        L.append("```\n")
    L.append("\n## Contract\n")
    L.append("- No production changes.")
    L.append("- Data pulls emit into `data/raw/india/fundamentals.parquet` and "
             "`usa/data/raw/us/fundamentals.parquet` under existing schema.")
    L.append("- Rerun `mr_fundamentals_gap_check` after each batch.")
    L.append("- Block M2 fundamentals studies until coverage >= 95% on daily-pred set.")
    return "\n".join(L)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    results = {}
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        res = analyze(root, m)
        p = emit(root, m, res)
        render_console(res)
        print(f"[fundamentals_gap:{m}] -> {p.name}")
        results[m] = res
    # Consolidated plan
    plan = render_plan(results.get("india", {}), results.get("usa", {}))
    plan_p = root / ALLOWED_WRITE_ROOT / "FUNDAMENTALS_GAP_PLAN.md"
    plan_p.write_text(plan, encoding="utf-8")
    print(f"\n[fundamentals_gap] plan -> {plan_p.name}")
