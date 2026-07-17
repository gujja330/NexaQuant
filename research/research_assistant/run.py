"""DEV026 — AI Investment Research Assistant · CLI.

Deterministic, grounded, no-network Q&A over all DEV017-025 reports.

Usage:
    python research/research_assistant/run.py --executive-summary
    python research/research_assistant/run.py --explain-stock INFY
    python research/research_assistant/run.py --compare HDFCBANK ICICIBANK
    python research/research_assistant/run.py --sector-report Pharma
    python research/research_assistant/run.py --portfolio-report
    python research/research_assistant/run.py --memo IPCALAB
    python research/research_assistant/run.py --all             (produce all standard reports)

Produces (per query type):
    reports/executive_summary.json
    reports/company_report.json           (--explain-stock)
    reports/comparison_report.json         (--compare)
    reports/sector_report.json             (--sector-report)
    reports/portfolio_report.json          (--portfolio-report)
    reports/investment_memo.json           (--memo)
    reports/investment_committee_report.json (--all)
    reports/research_memo.json             (--all)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from research_assistant.lib import loaders                                              # noqa: E402
from research_assistant.compute import assistant                                         # noqa: E402
from research_assistant.publish import bundle                                              # noqa: E402


ROOT = HERE.parents[1]


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def _banner(msg: str) -> None:
    print(); print("=" * 70); print(f"  {msg}"); print("=" * 70)


def main() -> int:
    ap = argparse.ArgumentParser(description="DEV026 AI Investment Research Assistant")
    ap.add_argument("--executive-summary", action="store_true")
    ap.add_argument("--explain-stock", metavar="TICKER")
    ap.add_argument("--compare", nargs=2, metavar=("TICKER_A", "TICKER_B"))
    ap.add_argument("--sector-report", metavar="SECTOR")
    ap.add_argument("--portfolio-report", action="store_true")
    ap.add_argument("--memo", metavar="TICKER")
    ap.add_argument("--all", action="store_true",
                     help="Generate a full suite of standard reports")
    args = ap.parse_args()

    t0 = time.time()
    _banner("DEV026 - AI INVESTMENT RESEARCH ASSISTANT")
    print(f"  time (IST): {_now_ist()}")
    print(f"  code_sha:   {_git_sha()}")

    state = loaders.load_all()
    coverage = loaders.state_summary(state)
    print(f"\n  Data coverage from reports/:")
    for k, v in coverage.items():
        print(f"    {'[y]' if v else '[n]'} {k}")

    outputs = []

    if args.executive_summary or args.all:
        r = assistant.answer(state, "executive_summary")
        p = bundle.write("executive_summary.json", r)
        outputs.append(p)
        _print_exec_summary(r["answer"])

    if args.explain_stock:
        r = assistant.answer(state, "explain_stock", ticker=args.explain_stock)
        p = bundle.write("company_report.json", r)
        outputs.append(p)
        _print_stock_explanation(r["answer"])

    if args.compare:
        r = assistant.answer(state, "compare", ticker_a=args.compare[0], ticker_b=args.compare[1])
        p = bundle.write("comparison_report.json", r)
        outputs.append(p)
        _print_comparison(r["answer"])

    if args.sector_report:
        r = assistant.answer(state, "sector_report", sector=args.sector_report)
        p = bundle.write("sector_report.json", r)
        outputs.append(p)
        _print_sector(r["answer"])

    if args.portfolio_report or args.all:
        r = assistant.answer(state, "portfolio_report")
        p = bundle.write("portfolio_report.json", r)
        outputs.append(p)
        _print_portfolio(r["answer"])

    if args.memo:
        r = assistant.answer(state, "investment_memo", ticker=args.memo)
        p = bundle.write("investment_memo.json", r)
        outputs.append(p)

    if args.all:
        # Top-3 memos + IC report
        if state.recommendations:
            top = [r for r in state.recommendations.get("recommendations", [])
                    if r.get("recommendation") in ("Strong-Buy", "Buy")][:3]
            for r_rec in top:
                r = assistant.answer(state, "investment_memo", ticker=r_rec["ticker"])
                p = bundle.write(f"investment_memo_{r_rec['ticker']}.json", r)
                outputs.append(p)

        # IC report = exec summary + top-5 memos condensed
        exec_r = assistant.answer(state, "executive_summary")
        top_5_recs = []
        if state.recommendations:
            top_5_recs = state.recommendations.get("recommendations", [])[:5]
        ic_report = {
            "dev_version":    "DEV026 v0.1",
            "generated_utc":  datetime.now(timezone.utc).isoformat() + "Z",
            "report_type":    "investment_committee_report",
            "executive_summary": exec_r["answer"],
            "top_5_recommendations": top_5_recs,
        }
        p = bundle.write("investment_committee_report.json", ic_report)
        outputs.append(p)

        research_memo = {
            "dev_version":    "DEV026 v0.1",
            "generated_utc":  datetime.now(timezone.utc).isoformat() + "Z",
            "report_type":    "research_memo",
            "state_snapshot": coverage,
            "executive_summary": exec_r["answer"],
        }
        p = bundle.write("research_memo.json", research_memo)
        outputs.append(p)

    _banner("OUTPUTS")
    if outputs:
        for p in outputs:
            print(f"  - {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}")
    else:
        print("  No query specified. Use --executive-summary, --explain-stock, --compare, etc.")

    _banner("DEV026 · DONE")
    print(f"  elapsed:  {time.time() - t0:.1f}s")
    return 0


def _print_exec_summary(a: dict):
    print()
    if a.get("global"):
        g = a["global"]
        print(f"  Global posture:     {g.get('posture')} (risk score {g.get('risk_score')}, "
                f"conf {g.get('confidence')})")
    if a.get("sectors"):
        s = a["sectors"]
        print(f"  Sectors computed:   {s.get('n_computed')} · class dist {s.get('class_distribution')}")
    if a.get("companies"):
        c = a["companies"]
        print(f"  Companies scored:   {c.get('n_computed')} · class dist {c.get('class_distribution')}")
    if a.get("recommendations_counts"):
        print(f"  Recommendations:    {a['recommendations_counts']}")
    if a.get("portfolio_snapshot"):
        p = a["portfolio_snapshot"]
        print(f"  Portfolio snapshot: {p.get('portfolio_id')} · "
                f"P&L {p.get('pnl_pct'):+.2f}% · health {p.get('health_score')}/100")
    if a.get("learning"):
        l = a["learning"]
        print(f"  Learning: {l.get('trades_analysed')} trades · "
                f"WR {l.get('win_rate_pct'):.1f}% · Brier {l.get('brier_score')}")
    if a.get("highlights"):
        print(f"  Highlights:")
        for h in a["highlights"]:
            print(f"    - {h}")


def _print_stock_explanation(a: dict):
    if a.get("status") == "not_found":
        print(f"  {a.get('message')}")
        return
    print()
    print(f"  {a['ticker']}   score {a['composite_score']:.1f}   {a['classification']}")
    print(f"    Recommendation: {a['recommendation']} · confidence {a['confidence']:.2f}")
    print(f"    Sector:   {a['hierarchy']['sector']} ({a['hierarchy']['sector_class']}) score {a['hierarchy']['sector_score']}")
    print(f"    Industry: {a['hierarchy']['industry']} ({a['hierarchy']['industry_class']})")
    print(f"    Rank:     overall {a['rankings']['overall_rank']} · sector {a['rankings']['sector_rank']} · industry {a['rankings']['industry_rank']}")
    ee = a.get("entry_exit") or {}
    if ee:
        print(f"    Entry:    latest INR {ee.get('latest_close')} · target INR {ee.get('target_1')} · stop INR {ee.get('stop_loss')}")
    print(f"\n  {a.get('narrative')}")


def _print_comparison(a: dict):
    if a.get("status") == "not_found":
        print(f"  {a.get('message')}")
        return
    print()
    for tk, row in a["comparison"].items():
        print(f"  {tk}: score {row['score']:.1f} · {row['classification']} · "
                f"sector {row['sector']} ({row['sector_score']}) · rank {row['overall_rank']}")
    print(f"\n  Verdict: {a['verdict']}")


def _print_sector(a: dict):
    if a.get("status") == "not_found":
        print(f"  Sector '{a.get('sector')}' not found in sector_context.json")
        return
    print()
    print(f"  {a['sector']}: score {a['sector_score']} · {a['classification']} · conf {a['confidence']}")
    print(f"  Allocation recommendation: {a.get('allocation_pct')}%")
    print(f"  {len(a['industries'])} industries mapped · {a['n_companies_in_sector']} companies")
    print(f"\n  Top companies in {a['sector']}:")
    for c in a["top_10_companies"][:5]:
        print(f"    {c['ticker']:<12} score {c['score']:5.1f}  {c['classification']:<14}  {c['industry']}")


def _print_portfolio(a: dict):
    if a.get("status") == "no_active_portfolio":
        print(f"  {a.get('message')}")
        return
    print()
    print(f"  Portfolio ID:    {a['portfolio_id']}")
    print(f"  P&L:             {a.get('pnl_pct', 0):+.2f}%")
    print(f"  Health:          {a.get('health_score')}/100")
    print(f"  Positions:       {a.get('n_positions')}")
    print(f"  Top sector:      {a.get('top_sector')} @ {(a.get('top_sector_share') or 0)*100:.1f}%")
    print(f"\n  {a.get('narrative')}")


if __name__ == "__main__":
    sys.exit(main())
