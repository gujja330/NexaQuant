"""AEGIS USA · Daily Orchestrator (Phase 1 skeleton).

Sequential runner for the USA pipeline. Mirrors India's
scripts/aegis_daily_v2.py shape so future phases can plug in
engines in the same style.

Phase 1 steps:
  1. build_universe        — read configs/universe.yaml → reports/universe.json
  2. refresh_market_data   — yfinance → data/raw/us/*.parquet

Later phases will add:
  3. recommendation engine    (Phase 2)
  4. validation, risk         (Phase 2)
  5. fusion, DNA, graph       (Phase 3)
  6. IM, winner genome, DA    (Phase 4)
  7. benchmark vs S&P 500     (Phase 4)
  8. morning report           (Phase 5)
  9. dashboard, telegram      (Phase 5)
 10. ops_check                (Phase 6)

This file is scaffolded so Phase-2 engineers add ONE dict to STEPS.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_ROOT = Path(__file__).resolve().parents[2]
_USA  = Path(__file__).resolve().parents[1]
LEDGER = _USA / "reports" / "usa_daily_history.jsonl"


# ─── Pipeline definition ────────────────────────────────────────
STEPS = [
    {
        "name":     "build_universe",
        "desc":     "Resolve active universe → usa/reports/universe.json",
        "script":   "usa/scripts/build_universe.py",
        "produces": ["usa/reports/universe.json"],
        "requires": ["usa/configs/universe.yaml"],
    },
    {
        "name":     "refresh_market_data",
        "desc":     "Fetch OHLCV from yfinance → usa/data/raw/us/*.parquet",
        "script":   "usa/scripts/refresh_market_data.py",
        "produces": ["usa/reports/market_data_freshness.json"],
        "requires": ["usa/reports/universe.json"],
    },
    # ── Sprint 1B · Data Ingestion (fundamentals + news + earnings + insider + flows + macro + actions + 13F) ─
    {
        "name":     "ingest_fundamentals",
        "desc":     "Sprint 1B · USA fundamentals ingest (yfinance PE/PB/ROE/EPS + earnings growth)",
        "script":   "usa/research/fundamentals/run.py",
        "produces": ["usa/reports/fundamentals.json"],
        "requires": ["usa/reports/universe.json"],
        "optional": True,
    },
    {
        "name":     "ingest_news",
        "desc":     "Sprint 1B · USA news sentiment ingest (Google News RSS + lexicon score)",
        "script":   "usa/research/news/run.py",
        "produces": ["usa/data/raw/us/news_sentiment.parquet",
                       "usa/reports/news_sentiment_summary.json"],
        "requires": ["usa/reports/universe.json"],
        "optional": True,
        "timeout_s": 900,    # 2026-08-05 · Google News RSS per-ticker fetch slow on 918-ticker universe
    },
    {
        "name":     "ingest_earnings",
        "desc":     "Sprint 1B · USA earnings calendar (next date + last-quarter surprise)",
        "script":   "usa/research/earnings/run.py",
        "produces": ["usa/data/raw/us/earnings.parquet",
                       "usa/reports/earnings_summary.json"],
        "requires": ["usa/reports/universe.json"],
        "optional": True,
        "timeout_s": 1200,   # 2026-08-05 · yfinance earnings-endpoint slow · was hitting 600s default
    },
    {
        "name":     "ingest_insider",
        "desc":     "Sprint 1B · USA insider Form 4 transactions (trailing 90d, net flow)",
        "script":   "usa/research/insider/run.py",
        "produces": ["usa/data/raw/us/insider_transactions.parquet",
                       "usa/reports/insider_summary.json"],
        "requires": ["usa/reports/universe.json"],
        "optional": True,
    },
    {
        "name":     "ingest_etf_flows",
        "desc":     "Sprint 1B · USA ETF flow proxy (sector + broad market ETF dollar volume)",
        "script":   "usa/research/etf_flows/run.py",
        "produces": ["usa/data/raw/us/etf_flows.parquet",
                       "usa/reports/etf_flows_summary.json"],
        "requires": [],
        "optional": True,
    },
    {
        "name":     "ingest_macro",
        "desc":     "Sprint 1B · USA macro (rates + DXY + gold + oil + VIX + MOVE)",
        "script":   "usa/research/macro/run.py",
        "produces": ["usa/data/raw/us/macro.parquet",
                       "usa/reports/macro_summary.json"],
        "requires": [],
        "optional": True,
    },
    {
        "name":     "ingest_corporate_actions",
        "desc":     "Sprint 1B · USA corporate actions ingest (dividends + splits, trailing 365d)",
        "script":   "usa/research/corporate_actions/run.py",
        "produces": ["usa/data/raw/us/corporate_actions.parquet",
                       "usa/reports/corporate_actions_summary.json"],
        "requires": ["usa/reports/universe.json"],
        "optional": True,
    },
    {
        "name":     "ingest_sec_13f",
        "desc":     "Sprint 1B · USA SEC 13F top-holders ingest (yfinance view · full EDGAR deferred)",
        "script":   "usa/research/sec_13f/run.py",
        "produces": ["usa/data/raw/us/institutional_holders.parquet",
                       "usa/reports/sec_13f_summary.json"],
        "requires": ["usa/reports/universe.json"],
        "optional": True,
    },
    {
        "name":     "backend_validation",
        "desc":     "USA Backend Data Foundation validator (Sprint 1)",
        "script":   "usa/backend_validation/run.py",
        "produces": ["usa/reports/backend_validation.json",
                       "usa/reports/backend_validation_summary.json"],
        "requires": [],
        "optional": True,
    },
    {
        "name":     "macro_intel",
        "desc":     "Sprint 6.5 · USA Macro & Intermarket Intelligence (commodities+currencies+bonds+CB+vol+rotation+regime, USD)",
        "script":   "usa/research/macro_intel/run.py",
        "produces": ["usa/reports/macro_regime.json",
                       "usa/reports/commodity_intelligence.json",
                       "usa/reports/currency_intelligence.json",
                       "usa/reports/bond_intelligence.json",
                       "usa/reports/central_bank_state.json",
                       "usa/reports/volatility_intelligence.json",
                       "usa/reports/sector_rotation.json",
                       "usa/reports/commodity_sector_matrix.json",
                       "usa/reports/macro_knowledge_graph.json",
                       "usa/reports/ai_macro_narrative.json",
                       "usa/reports/macro_history.parquet"],
        "requires": [],
        "optional": True,
    },
    {
        "name":     "factor_library",
        "desc":     "Sprint 7.5 · USA Factor Library (per-factor per-day rows, USD)",
        "script":   "usa/research/factor_library/run.py",
        "produces": ["usa/reports/factor_library.json",
                       "usa/reports/factor_library.parquet",
                       "usa/reports/factor_library_history.parquet"],
        "requires": ["usa/reports/commodity_intelligence.json"],
        "optional": True,
    },
    {
        "name":     "market_intelligence",
        "desc":     "Sprint 2 · USA Market Intelligence + AI narratives (USD)",
        "script":   "usa/research/market_intelligence/run.py",
        "produces": ["usa/reports/market_intelligence.json",
                       "usa/reports/market_intelligence_summary.json",
                       "usa/reports/ai_market_narrative.json"],
        "requires": [],
        "optional": True,
    },
    {
        "name":     "feature_store",
        "desc":     "Sprint 2.5 · USA Feature Store snapshot + AI (anomaly + quality + importance + conflict)",
        "script":   "usa/research/feature_store/run.py",
        "produces": ["usa/reports/feature_store_summary.json",
                       "usa/reports/ai_feature_narrative.json"],
        "requires": ["usa/reports/market_intelligence.json"],
        "optional": True,
    },
    {
        "name":     "feature_intelligence",
        "desc":     "Sprint 2.6 · USA Feature Intelligence (governance + quality + drift + importance + selection + research)",
        "script":   "usa/research/feature_intelligence/run.py",
        "produces": ["usa/reports/feature_intelligence.json",
                       "usa/reports/feature_intelligence_summary.json",
                       "usa/reports/selected_features.json",
                       "usa/reports/ai_feature_research.json"],
        "requires": ["usa/reports/feature_store_summary.json"],
        "optional": True,
    },
    {
        "name":     "model_factory",
        "desc":     "Sprint 2.7 · USA Model Factory (11 models + intelligence + ensemble + AI analyst)",
        "script":   "usa/research/model_factory/run.py",
        "produces": ["usa/reports/model_factory.json",
                       "usa/reports/model_metrics.json",
                       "usa/reports/ensemble.json",
                       "usa/reports/ai_model_narrative.json"],
        "requires": ["usa/reports/selected_features.json"],
        "optional": True,
    },
    {
        "name":     "recommendation_intelligence",
        "desc":     "Sprint 3 · USA Recommendation Intelligence v3 (USD)",
        "script":   "usa/research/recommendation_intelligence/run.py",
        "produces": ["usa/reports/recommendations_v3.json",
                       "usa/reports/recommendations_v3_summary.json",
                       "usa/reports/recommendations_v3_conflicts.json",
                       "usa/reports/ai_recommendation_narrative.json"],
        "requires": ["usa/reports/ensemble.json"],
        "optional": True,
    },
    {
        "name":     "risk_engine",
        "desc":     "Sprint 4 · USA Risk Engine (Kelly + caps + vol + VaR/CVaR, USD)",
        "script":   "usa/research/risk_engine/run.py",
        "produces": ["usa/reports/sized_positions.json",
                       "usa/reports/risk_report.json",
                       "usa/reports/ai_risk_narrative.json"],
        "requires": ["usa/reports/recommendations_v3.json", "configs/risk_budget.yaml"],
        "optional": True,
    },
    {
        "name":     "portfolio_engine",
        "desc":     "Sprint 5 · USA Portfolio Engine (N-name construction + cash + rebalance diff, USD)",
        "script":   "usa/research/portfolio_engine/run.py",
        "produces": ["usa/reports/portfolio_v3.json",
                       "usa/reports/portfolio_diff.json",
                       "usa/reports/portfolio_state.json",
                       "usa/reports/ai_portfolio_narrative.json"],
        "requires": ["usa/reports/sized_positions.json", "configs/portfolio_config.yaml"],
        "optional": True,
    },
    {
        "name":     "learning_engine",
        "desc":     "Sprint 6 · USA Learning Engine (outcome ledger + attributions + calibration, USD)",
        "script":   "usa/research/learning_engine/run.py",
        "produces": ["usa/reports/feature_attribution.json",
                       "usa/reports/model_attribution.json",
                       "usa/reports/failure_clusters.json",
                       "usa/reports/confidence_calibration.json",
                       "usa/reports/ai_learning_narrative.json"],
        "requires": ["configs/learning_config.yaml"],
        "optional": True,
    },
    {
        "name":     "execution_simulator",
        "desc":     "Sprint 7 · USA Execution Simulator (fills + slippage + equity curve, USD)",
        "script":   "usa/research/execution_simulator/run.py",
        "produces": ["usa/reports/execution_ledger.parquet",
                       "usa/reports/execution_summary.json",
                       "usa/reports/equity_curve.parquet",
                       "usa/reports/ai_execution_narrative.json"],
        "requires": ["usa/reports/portfolio_diff.json", "configs/execution_config.yaml"],
        "optional": True,
    },
    {
        "name":     "recommendations",
        "desc":     "USA Adaptive Recommendation Engine (technicals-based)",
        "script":   "usa/research/recommendations/run.py",
        "produces": ["usa/reports/recommendations.json"],
        "requires": ["usa/reports/market_data_freshness.json"],
    },
    {
        "name":     "validation",
        "desc":     "USA Validation Engine (paper harness + drift)",
        "script":   "usa/research/validation/run.py",
        "produces": ["usa/reports/validation_latest.json", "usa/reports/stock_validation.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "risk",
        "desc":     "USA Risk & Capital Engine (sizing + sector caps + verdict)",
        "script":   "usa/research/risk/run.py",
        "produces": ["usa/reports/risk_latest.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "fusion",
        "desc":     "USA Intelligence Fusion (10-dim aggregate + conflicts)",
        "script":   "usa/research/fusion/run.py",
        "produces": ["usa/reports/investment_intelligence.json",
                       "usa/reports/intelligence_summary.json",
                       "usa/reports/intelligence_conflicts.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "price_context",
        "desc":     "USA Price Context (CMP + 52W bounds per ticker)",
        "script":   "usa/research/price_context/run.py",
        "produces": ["usa/reports/price_context.json"],
        "requires": ["usa/reports/universe.json"],
    },
    # ── FINAL PLATFORM COMPLETION · Phase 1 · SSoT Bridge (USA) ──
    {
        "name":     "recommendation_ssot",
        "desc":     "USA Recommendation SSoT bridge · publishes fresh recommendations.json from Runner 2 v3",
        "script":   "backend/recommendation/ssot/run.py",
        "script_args": ["--market", "usa"],
        "produces": ["usa/reports/recommendations.json"],
        "requires": ["usa/reports/recommendations_v3.json"],
        "optional": True,
    },
    {
        "name":     "recommendation_lifecycle",
        "desc":     "USA Recommendation Lifecycle state machine (Phase 2 · L2 WIRED)",
        "script":   "backend/recommendation/lifecycle/run.py",
        "script_args": ["--market", "usa"],
        "produces": ["usa/reports/recommendation_lifecycle.json"],
        "requires": ["usa/reports/recommendations.json"],
        "optional": True,
    },
    # v3.0 lock · USA trust-surface parity with India
    {
        "name":     "institutional_optimization",
        "desc":     "USA v2.4 trust surfaces · percentile classifier + attribution + backtrack",
        "script":   "backend/certification/institutional_optimization_run.py",
        "script_args": ["--market", "usa"],
        "produces": ["usa/reports/percentile_classification.json"],
        "requires": ["usa/reports/recommendations.json"],
        "optional": True,
    },
    {
        "name":     "recommendation_deltas",
        "desc":     "USA Recommendation Delta engine (Phase 3 · L2 WIRED)",
        "script":   "backend/recommendation/delta/run.py",
        "script_args": ["--market", "usa"],
        "produces": ["usa/reports/recommendation_deltas.json"],
        "requires": ["usa/reports/recommendations.json"],
        "optional": True,
    },
    {
        "name":     "dynamic_holding",
        "desc":     "USA Dynamic Holding Engine (Phase 4 · L2 WIRED)",
        "script":   "backend/recommendation/dynamic_holding/run.py",
        "script_args": ["--market", "usa"],
        "produces": ["usa/reports/dynamic_holding.json"],
        "requires": ["usa/reports/recommendations.json"],
        "optional": True,
    },
    # ── Wave 5 P9/P10 · Capital Intelligence + Portfolio Attribution (USA) ──
    # Wave Y wire-in · elevate L1 BUILT → L2 WIRED for USA market.
    {
        "name":     "capital_rotation",
        "desc":     "USA Capital Rotation Engine v1.0",
        "script":   "backend/recommendation/capital_rotation/run.py",
        "script_args": ["--market", "usa"],
        "produces": ["usa/reports/rotation_plan.json"],
        "requires": ["usa/reports/recommendations_v3.json", "usa/reports/portfolio_v3.json"],
        "optional": True,
    },
    {
        "name":     "opportunity_cost",
        "desc":     "USA Opportunity Cost Engine v1.0",
        "script":   "backend/recommendation/opportunity_cost/run.py",
        "script_args": ["--market", "usa"],
        "produces": ["usa/reports/opportunity_cost.json"],
        "requires": ["usa/reports/recommendations_v3.json"],
        "optional": True,
    },
    {
        "name":     "portfolio_attribution",
        "desc":     "USA Portfolio Attribution Engine v1.0",
        "script":   "backend/portfolio/monitoring/run_attribution.py",
        "script_args": ["--market", "usa"],
        "produces": ["usa/reports/portfolio_attribution.json"],
        "requires": ["usa/reports/portfolio_v3.json"],
        "optional": True,
    },
    {
        "name":     "institutional_memory",
        "desc":     "USA Institutional Memory (archive + lifecycle + missed-opps + history)",
        "script":   "usa/research/institutional_memory/run.py",
        "produces": ["usa/reports/recommendation_lifecycle.json",
                       "usa/reports/missed_opportunities.json",
                       "usa/reports/recommendation_history.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "winner_genome",
        "desc":     "USA Winner Genome (Alpha Signatures)",
        "script":   "usa/research/winner_genome/run.py",
        "produces": ["usa/reports/winner_genome.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "decision_attribution",
        "desc":     "USA Decision Attribution (per-rec + subsystem accuracy)",
        "script":   "usa/research/decision_attribution/run.py",
        "produces": ["usa/reports/decision_attribution.json"],
        "requires": ["usa/reports/recommendations.json",
                       "usa/reports/investment_intelligence.json"],
    },
    {
        "name":     "benchmark",
        "desc":     "USA Continuous Benchmark (vs S&P 500)",
        "script":   "usa/research/benchmark/run.py",
        "produces": ["usa/reports/benchmark.json"],
        "requires": ["usa/reports/recommendations.json"],
    },
    {
        "name":     "morning_report",
        "desc":     "USA Morning Research Report (MD + HTML, USD)",
        "script":   "usa/research/morning_report/run.py",
        "produces": ["usa/reports/morning_latest.md", "usa/reports/morning_latest.html"],
        "requires": ["usa/reports/recommendations.json", "usa/reports/benchmark.json"],
    },
    {
        "name":     "ops_check",
        "desc":     "USA Operational Hardening (artifacts + schemas + verdict)",
        "script":   "usa/scripts/usa_ops_check.py",
        "produces": ["usa/reports/ops_check.json"],
        "requires": [],
    },
    {
        "name":     "telegram",
        "desc":     "USA Telegram delivery (USD, 5 messages, opt-in)",
        "script":   "usa/scripts/telegram_send.py",
        "produces": [],
        "requires": [],
        "optional": True,
    },
    {
        "name":     "comparison_report",
        "desc":     "India vs USA cross-market comparison report",
        "script":   "compare/build_comparison.py",
        "produces": ["compare/reports/comparison_latest.md",
                       "compare/reports/comparison_latest.html"],
        "requires": [],
    },
]


def _banner(msg: str) -> None:
    print(); print("=" * 78); print(f"  {msg}"); print("=" * 78)


def _run_step(step: dict) -> dict:
    script = _ROOT / step["script"]
    if not script.exists():
        return {"name": step["name"], "verdict": "MISSING_SCRIPT", "elapsed_s": 0.0}

    # Verify required inputs exist
    for req in step.get("requires", []):
        if not (_ROOT / req).exists():
            return {
                "name": step["name"],
                "verdict": "MISSING_INPUT",
                "elapsed_s": 0.0,
                "missing": req,
            }

    # Wave Y: optional script_args passthrough.
    _cmd = [sys.executable, step["script"]] + list(step.get("script_args", []))

    # 2026-08-05 · timeout was crashing the whole orchestrator when a single
    # step hung (subprocess.TimeoutExpired was unhandled · killed the parent
    # even for `optional: True` steps · earnings-ingest hit this 3 days
    # running). Two fixes:
    #   1. per-step timeout override via step["timeout_s"] (default 600s)
    #   2. TimeoutExpired caught + treated as FAILED verdict → the existing
    #      `optional: True` check then skips + pipeline continues
    step_timeout = int(step.get("timeout_s") or 600)

    t0 = time.time()
    try:
        r = subprocess.run(
            _cmd,
            cwd=str(_ROOT), capture_output=True, text=True, timeout=step_timeout,
        )
        elapsed = time.time() - t0
        # Stream stdout live to operator
        if r.stdout:
            print(r.stdout.rstrip())
        if r.returncode != 0 and r.stderr:
            print(r.stderr[:1200])
        verdict = "SUCCESS" if r.returncode == 0 else "FAILED"
        rc = r.returncode
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - t0
        # Print whatever partial output was captured before timeout
        if e.stdout:
            partial = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else str(e.stdout)
            print(partial[:2000])
        print(f"  [{step['name']}] TIMEOUT after {step_timeout}s · "
                 f"treating as FAILED (optional={step.get('optional', False)})")
        verdict = "FAILED"
        rc = 124        # conventional shell timeout exit code
    return {
        "name":       step["name"],
        "verdict":    verdict,
        "elapsed_s":  round(elapsed, 2),
        "returncode": rc,
    }


def main() -> int:
    _banner("AEGIS USA · Daily Orchestrator (Phase 1)")
    print(f"  UTC now:  {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"  steps:    {len(STEPS)}")
    print(f"  currency: USD ($)")

    results: list[dict] = []
    t_total = time.time()

    for i, step in enumerate(STEPS, 1):
        _banner(f"[{i}/{len(STEPS)}] {step['name']} · {step['desc']}")
        res = _run_step(step)
        results.append(res)
        print(f"\n  verdict: {res['verdict']}  ·  elapsed: {res['elapsed_s']}s")
        if res["verdict"] == "FAILED":
            if step.get("optional"):
                print(f"  {step['name']} failed but is optional — continuing pipeline.")
                continue
            print(f"  aborting pipeline — required step {step['name']} failed.")
            break

    total_elapsed = round(time.time() - t_total, 2)
    n_ok  = sum(1 for r in results if r["verdict"] == "SUCCESS")

    # Exit-code logic (fixed): the pipeline is green as long as every
    # non-optional step succeeded. Optional-step failures are logged but
    # do NOT fail the CI job — that is the entire point of `optional: True`.
    # Previously we returned 1 whenever n_ok < len(STEPS), which meant a
    # single rate-limited yfinance ingest killed the whole pipeline.
    step_by_name = {s["name"]: s for s in STEPS}
    required_failures = [
        r for r in results
        if r["verdict"] != "SUCCESS"
        and not step_by_name.get(r["name"], {}).get("optional")
    ]
    optional_failures = [
        r for r in results
        if r["verdict"] != "SUCCESS"
        and step_by_name.get(r["name"], {}).get("optional")
    ]

    _banner("SUMMARY")
    print(f"  steps:    {n_ok}/{len(STEPS)} ok")
    print(f"  required failures: {len(required_failures)}")
    if required_failures:
        for rf in required_failures[:8]:
            print(f"    ✗ {rf['name']} · verdict={rf['verdict']}")
    print(f"  optional failures: {len(optional_failures)} (non-fatal)")
    if optional_failures:
        for of in optional_failures[:8]:
            print(f"    ! {of['name']} · verdict={of['verdict']}")
    print(f"  elapsed:  {total_elapsed}s")

    # Append to ledger
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_utc":            datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "phase":              1,
        "n_steps":            len(STEPS),
        "n_success":          n_ok,
        "n_failure":          len(results) - n_ok,
        "n_required_failure": len(required_failures),
        "n_optional_failure": len(optional_failures),
        "total_elapsed_s":    total_elapsed,
        "results":            results,
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    print(f"  ledger:   {LEDGER.relative_to(_ROOT)}")

    # Pipeline is green iff every required step succeeded.
    return 0 if not required_failures else 1


if __name__ == "__main__":
    sys.exit(main())
