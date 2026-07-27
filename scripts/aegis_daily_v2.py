"""AEGIS Daily · Phase 2 v2 engines orchestrator.

Runs every Phase 2 v2 module in the correct dependency order, once
per day. The old daily pipeline (india/recommendation_generator.py +
DEV017-DEV031) is unchanged — this script runs AFTER it to produce
the new v2 artifacts on top of the fresh base recommendations.

Dependency order:
  1. adaptive_rec_v2/run.py           (needs learning.parquet)
  2. validation_v2/run.py             (needs recommendations.json + raw prices)
  3. risk_capital_v2/run.py           (needs recommendations.json + global_context.json)
  4. recommendation_dna/run_feedback.py  (needs DNA + learning + recommendations)
  5. knowledge_graph/run.py           (needs recommendations + portfolio + backtest)
  6. adaptive_rec_v2/run_fusion.py    (needs ALL of the above)

Usage:
  python scripts/aegis_daily_v2.py                # run all, fail-fast
  python scripts/aegis_daily_v2.py --continue     # keep going on failure
  python scripts/aegis_daily_v2.py --only fusion  # run only fusion
  python scripts/aegis_daily_v2.py --list         # print the plan and exit
  python scripts/aegis_daily_v2.py --dry-run      # print each command without running

Every step prints a banner + captures stdout/stderr, and the final
summary reports per-step verdict + elapsed time + a full run ledger
appended to reports/aegis_daily_v2_history.jsonl for auditability.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_ROOT = Path(__file__).resolve().parents[1]
LEDGER = _ROOT / "reports" / "aegis_daily_v2_history.jsonl"


# ─── Pipeline definition ────────────────────────────────────────
# Ordered list of steps. Each step declares its script + a short name
# + the artifacts it produces (for post-run verification).
STEPS = [
    # ── Sprint 1B · Data Ingestion (runs BEFORE backend_validation) ─────
    {
        "name": "ingest_fii_dii",
        "desc": "Sprint 1B · FII/DII cash flow ingest (NSE endpoint · appends latest)",
        "script": "india/fii_dii.py",
        "produces": ["data/raw/india/fii_dii.parquet"],
        "requires": [],
        "optional": True,   # network flake shouldn't halt the pipeline
    },
    {
        "name": "ingest_news_sentiment",
        "desc": "Sprint 1B · News sentiment ingest (Google News RSS + FinBERT · EW-30 basket)",
        "script": "india/news_sentiment.py",
        "produces": ["data/raw/india/news_sentiment.parquet"],
        "requires": [],
        "optional": True,   # FinBERT/RSS latency shouldn't halt the pipeline
    },
    {
        "name": "ingest_fundamentals",
        "desc": "Sprint 1B · Fundamentals + earnings calendar ingest (yfinance snapshot)",
        "script": "india/fundamentals_nse.py",
        "produces": ["data/raw/india/fundamentals.parquet"],
        "requires": [],
        "optional": True,
    },
    {
        "name": "ingest_corporate_actions",
        "desc": "Sprint 1B · Corporate actions ingest (dividends + splits, trailing 365d)",
        "script": "india/corporate_actions.py",
        "produces": ["data/raw/india/corporate_actions.parquet"],
        "requires": [],
        "optional": True,
    },
    {
        "name": "backend_validation",
        "desc": "Backend Data Foundation validator (Sprint 1 · freshness+schema+quality+lineage)",
        "script": "india/backend_validation/run.py",
        "produces": ["reports/backend_validation.json",
                       "reports/backend_validation_summary.json"],
        "requires": [],
        "optional": True,   # WARNING/FAIL doesn't halt the pipeline — it's reported to ops_check
    },
    {
        "name": "macro_intel",
        "desc": "Sprint 6.5 · Macro & Intermarket Intelligence (commodities + currencies + bonds + central bank + vol + sector rotation + regime + impact matrix + knowledge graph)",
        "script": "india/macro_intel/run.py",
        "produces": ["reports/macro_regime.json",
                       "reports/commodity_intelligence.json",
                       "reports/currency_intelligence.json",
                       "reports/bond_intelligence.json",
                       "reports/central_bank_state.json",
                       "reports/volatility_intelligence.json",
                       "reports/sector_rotation.json",
                       "reports/commodity_sector_matrix.json",
                       "reports/macro_knowledge_graph.json",
                       "reports/ai_macro_narrative.json",
                       "reports/macro_history.parquet"],
        "requires": [],
        "optional": True,
    },
    {
        "name": "factor_library",
        "desc": "Sprint 7.5 · Factor Library (per-factor per-day rows; substrate for AI pattern search + Research Factory)",
        "script": "india/factor_library/run.py",
        "produces": ["reports/factor_library.json",
                       "reports/factor_library.parquet",
                       "reports/factor_library_history.parquet"],
        "requires": ["reports/commodity_intelligence.json"],
        "optional": True,
    },
    {
        "name": "market_intelligence",
        "desc": "Sprint 2 · Market Intelligence engine + AI narratives (regime, breadth, macro, sector rotation, news/flow pulse)",
        "script": "india/market_intelligence/run.py",
        "produces": ["reports/market_intelligence.json",
                       "reports/market_intelligence_summary.json",
                       "reports/ai_market_narrative.json"],
        "requires": [],
        "optional": True,   # non-blocking for legacy engines
    },
    {
        "name": "feature_store",
        "desc": "Sprint 2.5 · Feature Store snapshot + AI (anomaly + quality + importance + conflict)",
        "script": "india/feature_store/run.py",
        "produces": ["reports/feature_store_summary.json",
                       "reports/ai_feature_narrative.json"],
        "requires": ["reports/market_intelligence.json"],   # market_intel joined into features
        "optional": True,
    },
    {
        "name": "feature_intelligence",
        "desc": "Sprint 2.6 · Feature Intelligence (governance + quality + drift + importance + selection + research)",
        "script": "india/feature_intelligence/run.py",
        "produces": ["reports/feature_intelligence.json",
                       "reports/feature_intelligence_summary.json",
                       "reports/selected_features.json",
                       "reports/ai_feature_research.json"],
        "requires": ["reports/feature_store_summary.json"],
        "optional": True,
    },
    {
        "name": "model_factory",
        "desc": "Sprint 2.7 · Model Factory (11 models + intelligence + ensemble + AI analyst)",
        "script": "india/model_factory/run.py",
        "produces": ["reports/model_factory.json",
                       "reports/model_metrics.json",
                       "reports/ensemble.json",
                       "reports/ai_model_narrative.json"],
        "requires": ["reports/selected_features.json"],
        "optional": True,
    },
    {
        "name": "recommendation_intelligence",
        "desc": "Sprint 3 · Recommendation Intelligence v3 (conflict + calibration + regime + explainer + AI analyst)",
        "script": "india/recommendation_intelligence/run.py",
        "produces": ["reports/recommendations_v3.json",
                       "reports/recommendations_v3_summary.json",
                       "reports/recommendations_v3_conflicts.json",
                       "reports/ai_recommendation_narrative.json"],
        "requires": ["reports/ensemble.json"],
        "optional": True,
    },
    {
        "name": "risk_engine",
        "desc": "Sprint 4 · Risk Engine (Kelly sizing + caps + vol adj + VaR/CVaR + AI risk analyst)",
        "script": "india/risk_engine/run.py",
        "produces": ["reports/sized_positions.json",
                       "reports/risk_report.json",
                       "reports/ai_risk_narrative.json"],
        "requires": ["reports/recommendations_v3.json", "configs/risk_budget.yaml"],
        "optional": True,
    },
    {
        "name": "portfolio_engine",
        "desc": "Sprint 5 · Portfolio Engine (N-name construction + cash policy + rebalance diff + AI analyst)",
        "script": "india/portfolio_engine/run.py",
        "produces": ["reports/portfolio_v3.json",
                       "reports/portfolio_diff.json",
                       "reports/portfolio_state.json",
                       "reports/ai_portfolio_narrative.json"],
        "requires": ["reports/sized_positions.json", "configs/portfolio_config.yaml"],
        "optional": True,
    },
    {
        "name": "learning_engine",
        "desc": "Sprint 6 · Learning Engine (outcome ledger + feature/model attribution + failure clusters + calibration)",
        "script": "india/learning_engine/run.py",
        "produces": ["reports/feature_attribution.json",
                       "reports/model_attribution.json",
                       "reports/failure_clusters.json",
                       "reports/confidence_calibration.json",
                       "reports/ai_learning_narrative.json"],
        "requires": ["configs/learning_config.yaml"],
        "optional": True,
    },
    {
        "name": "execution_simulator",
        "desc": "Sprint 7 · Execution Simulator (fills + slippage + commissions + equity curve + AI analyst)",
        "script": "india/execution_simulator/run.py",
        "produces": ["reports/execution_ledger.parquet",
                       "reports/execution_summary.json",
                       "reports/equity_curve.parquet",
                       "reports/ai_execution_narrative.json"],
        "requires": ["reports/portfolio_diff.json", "configs/execution_config.yaml"],
        "optional": True,
    },
    {
        "name": "adaptive_rec_v2",
        "desc": "Adaptive Rec Engine v2.0 (confidence rebuild + Precision@K)",
        "script": "research/adaptive_rec_v2/run.py",
        "produces": ["reports/adaptive_rec_v2_signal.json"],
        "requires": ["reports/learning.parquet"],
    },
    {
        "name": "validation_v2",
        "desc": "Validation Engine v2.0 (paper harness + drift + opportunity cost)",
        "script": "research/validation_v2/run.py",
        "produces": ["reports/validation_v2_latest.json"],
        "requires": ["reports/recommendations.json"],
    },
    {
        "name": "risk_capital_v2",
        "desc": "Risk & Capital Engine v2.0 (position sizing + budget)",
        "script": "research/risk_capital_v2/run.py",
        "produces": ["reports/risk_capital_v2_latest.json"],
        "requires": ["reports/recommendations.json", "reports/global_context.json"],
    },
    {
        "name": "dna_feedback",
        "desc": "DNA feedback loop v1.5 (pattern priors from DEV028)",
        "script": "research/recommendation_dna/run_feedback.py",
        "produces": ["reports/recommendation_dna_feedback.json"],
        "requires": ["reports/recommendation_dna.parquet"],
    },
    {
        "name": "knowledge_graph",
        "desc": "Knowledge Graph v1.6 (communities + propagation + stress)",
        "script": "research/knowledge_graph/run.py",
        "produces": ["reports/knowledge_graph.json",
                       "reports/stress_scenarios.json",
                       "reports/community_clusters.json"],
        "requires": ["reports/recommendations.json"],
    },
    {
        "name": "fusion",
        "desc": "Adaptive Rec Engine v2.1 (Intelligence Fusion — final decision)",
        "script": "research/adaptive_rec_v2/run_fusion.py",
        "produces": ["reports/investment_intelligence.json",
                       "reports/intelligence_summary.json",
                       "reports/intelligence_conflicts.json"],
        "requires": [],   # will use whatever is available
    },
    {
        "name": "stock_validation",
        "desc": "Per-ticker historical validation rollup",
        "script": "research/validation_v2/run_stock_history.py",
        "produces": ["reports/stock_validation.json"],
        "requires": ["reports/learning.parquet"],
    },
    {
        "name": "price_context",
        "desc": "Per-ticker CMP + 52W high/low from raw data",
        "script": "research/validation_v2/run_price_context.py",
        "produces": ["reports/price_context.json"],
        "requires": ["reports/recommendations.json"],
    },
    {
        "name": "decision_center",
        "desc": "Decision Center v1.0 (overnight diff + exit center + watchlist)",
        "script": "research/decision_center/run.py",
        "produces": ["reports/decision_center_today.json",
                       "reports/decision_center_notifications.json"],
        "requires": [],   # runs even without prior snapshot (baseline mode)
    },
    # ── Wave 5 Phase 9/10 · Capital Intelligence + Portfolio Attribution ──
    # Wave Y wire-in: elevate L1 BUILT → L2 WIRED. Producers only run when
    # upstream artifacts exist (recommendations_v3.json · portfolio_v3.json).
    {
        "name": "capital_rotation",
        "desc": "Capital Rotation Engine v1.0 (Wave 5 P9 · rotation_plan.json)",
        "script": "backend/recommendation/capital_rotation/run.py",
        "script_args": ["--market", "india"],
        "produces": ["reports/rotation_plan.json"],
        "requires": ["reports/recommendations_v3.json", "reports/portfolio_v3.json"],
        "optional": True,
    },
    {
        "name": "opportunity_cost",
        "desc": "Opportunity Cost Engine v1.0 (Wave 5 P9 · every HOLD justifies)",
        "script": "backend/recommendation/opportunity_cost/run.py",
        "script_args": ["--market", "india"],
        "produces": ["reports/opportunity_cost.json"],
        "requires": ["reports/recommendations_v3.json"],
        "optional": True,
    },
    {
        "name": "portfolio_attribution",
        "desc": "Portfolio Attribution Engine v1.0 (Wave 5 P10 · 13-factor)",
        "script": "backend/portfolio/monitoring/run_attribution.py",
        "script_args": ["--market", "india"],
        "produces": ["reports/portfolio_attribution.json"],
        "requires": ["reports/portfolio_v3.json"],
        "optional": True,
    },
    {
        "name": "institutional_memory",
        "desc": "Institutional Memory v1.0 (archive + lifecycle + missed-opps + per-ticker history)",
        "script": "research/institutional_memory/run.py",
        "produces": ["reports/recommendation_lifecycle.json",
                       "reports/missed_opportunities.json",
                       "reports/recommendation_history.json"],
        "requires": ["reports/recommendations.json"],
    },
    {
        "name": "winner_genome",
        "desc": "Recommendation DNA v2.0 · Winner Genome (Alpha Signatures + per-rec match)",
        "script": "research/recommendation_dna/run_winner_genome.py",
        "produces": ["reports/winner_genome.json"],
        "requires": ["reports/learning.parquet", "reports/recommendations.json"],
    },
    {
        "name": "decision_attribution",
        "desc": "Decision Attribution v1.0 (per-rec contributions + subsystem alpha creators/destroyers)",
        "script": "research/decision_attribution/run.py",
        "produces": ["reports/decision_attribution.json"],
        "requires": ["reports/recommendations.json"],
    },
    {
        "name": "benchmark",
        "desc": "Continuous Benchmark v1.0 (AEGIS vs NIFTY + synthetic sector per-trade alpha)",
        "script": "research/benchmark/run.py",
        "produces": ["reports/benchmark.json"],
        "requires": ["reports/learning.parquet", "data/raw/india/NSEI_D1.parquet"],
    },
    {
        "name": "morning_report",
        "desc": "Morning Research Report v1.0 (daily HTML + Markdown digest)",
        "script": "research/morning_report/run.py",
        "produces": ["reports/morning_latest.md", "reports/morning_latest.html"],
        "requires": ["reports/recommendations.json", "reports/benchmark.json"],
    },
    {
        "name": "ops_check",
        "desc": "Operational Hardening (artifact + schema + fingerprint + health rollup)",
        "script": "scripts/aegis_ops_check.py",
        "produces": ["reports/ops_check.json"],
        "requires": [],
    },
    {
        "name": "telegram",
        "desc": "UX030 Telegram delivery (5 messages, opt-in)",
        "script": "scripts/telegram_send_ux030.py",
        "produces": [],   # no reports/*.json artifact; writes delivery ledger
        "requires": [],
        "requires_env": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
        "optional": True,   # gracefully skip if env is missing
    },
]


# ─── Utilities ──────────────────────────────────────────────────
def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now_ist() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S IST")


def _banner(msg: str) -> None:
    print(); print("=" * 78); print(f"  {msg}"); print("=" * 78)


def _mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


def _check_requires(step: dict) -> list[str]:
    missing = []
    for req in step.get("requires", []):
        if not (_ROOT / req).exists():
            missing.append(req)
    return missing


def _check_produced(step: dict, before_mtimes: dict[str, str | None]) -> dict:
    """Verify each declared artifact was refreshed since `before_mtimes` was captured."""
    results = {}
    for art in step.get("produces", []):
        p = _ROOT / art
        after = _mtime_iso(p)
        before = before_mtimes.get(art)
        exists = p.exists()
        refreshed = exists and (before != after)
        results[art] = {"exists": exists, "before": before,
                          "after": after, "refreshed": refreshed}
    return results


def _run_step(step: dict, dry_run: bool = False) -> dict:
    """Run one step, capture verdict + timing."""
    script = _ROOT / step["script"]
    if not script.exists():
        return {
            "name": step["name"], "verdict": "MISSING_SCRIPT",
            "elapsed_s": 0.0, "returncode": None,
            "note": f"script not found: {step['script']}",
        }

    # Optional steps skip gracefully if their env is not configured
    missing_env = [k for k in step.get("requires_env", []) if not os.environ.get(k)]
    if missing_env:
        return {
            "name": step["name"],
            "verdict": "SKIPPED_OPTIONAL" if step.get("optional") else "MISSING_ENV",
            "elapsed_s": 0.0, "returncode": None,
            "missing_env": missing_env,
            "note": f"env vars not set: {', '.join(missing_env)}",
        }

    before_mtimes = {art: _mtime_iso(_ROOT / art) for art in step.get("produces", [])}
    missing_reqs = _check_requires(step)
    if missing_reqs:
        return {
            "name": step["name"], "verdict": "MISSING_INPUTS",
            "elapsed_s": 0.0, "returncode": None,
            "missing_inputs": missing_reqs,
        }

    # Wave Y: optional script_args passed through to the child process.
    _cmd = [sys.executable, str(script)] + list(step.get("script_args", []))

    if dry_run:
        return {
            "name": step["name"], "verdict": "DRY_RUN",
            "elapsed_s": 0.0, "returncode": None,
            "command": _cmd,
        }

    ts_start = _iso_utc()
    t0 = time.perf_counter()
    r = subprocess.run(
        _cmd,
        cwd=str(_ROOT),
        capture_output=True, text=True,
        timeout=600,
    )
    elapsed = time.perf_counter() - t0

    # Echo the child's stdout so operators see everything in the CI log
    for line in (r.stdout or "").splitlines():
        print(f"    | {line}")
    if r.stderr:
        for line in r.stderr.splitlines():
            print(f"  ERR: {line}")

    produced = _check_produced(step, before_mtimes)
    all_refreshed = all(v["refreshed"] for v in produced.values()) if produced else True

    if r.returncode == 0 and all_refreshed:
        verdict = "SUCCESS"
    elif r.returncode == 0 and not all_refreshed:
        verdict = "SUCCESS_NO_REFRESH"
    else:
        verdict = "FAILURE"

    return {
        "name":            step["name"],
        "desc":            step["desc"],
        "verdict":         verdict,
        "ts_start":        ts_start,
        "elapsed_s":       round(elapsed, 2),
        "returncode":      r.returncode,
        "produced":        produced,
        "stdout_tail":     (r.stdout or "").splitlines()[-8:],
        "stderr_tail":     (r.stderr or "").splitlines()[-4:],
    }


def _append_ledger(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ─── Main ───────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--continue", dest="cont", action="store_true",
                     help="continue on step failure (default: fail-fast)")
    ap.add_argument("--only", metavar="NAME",
                     help="run only the named step (repeatable, comma-separated)")
    ap.add_argument("--list", action="store_true",
                     help="print the plan and exit")
    ap.add_argument("--dry-run", action="store_true",
                     help="print each step's command without running")
    args = ap.parse_args()

    only = set()
    if args.only:
        only = set(x.strip() for x in args.only.split(","))

    plan = [s for s in STEPS if not only or s["name"] in only]
    if not plan:
        print(f"no steps match --only={args.only!r}")
        return 2

    _banner("AEGIS DAILY · PHASE 2 v2 · orchestrator")
    print(f"  wall clock (IST): {_now_ist()}")
    print(f"  plan: {' -> '.join(s['name'] for s in plan)}")
    print(f"  mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  continue-on-failure: {args.cont}")

    if args.list:
        for i, s in enumerate(plan, 1):
            print(f"  {i}. {s['name']:<24} {s['desc']}")
        return 0

    results = []
    t_all = time.perf_counter()
    for i, step in enumerate(plan, 1):
        _banner(f"STEP {i}/{len(plan)} · {step['name']} · {step['desc']}")
        result = _run_step(step, dry_run=args.dry_run)
        results.append(result)

        verdict = result["verdict"]
        print(f"    verdict={verdict}  elapsed={result.get('elapsed_s', 0)}s")

        if verdict == "FAILURE" and not args.cont:
            print(f"    fail-fast: aborting remaining steps. Use --continue to override.")
            break
        if verdict == "MISSING_INPUTS":
            print(f"    missing: {result.get('missing_inputs')}")
            if not args.cont:
                print(f"    fail-fast: aborting.")
                break

    total_elapsed = time.perf_counter() - t_all

    _banner("SUMMARY")
    print(f"  {'step':<20} {'verdict':<20} {'elapsed_s':>10}")
    print(f"  {'-' * 55}")
    n_success = 0; n_fail = 0
    for r in results:
        v = r["verdict"]
        if v == "SUCCESS":
            n_success += 1
        elif v in ("FAILURE", "MISSING_SCRIPT", "MISSING_INPUTS"):
            n_fail += 1
        print(f"  {r['name']:<20} {v:<20} {r.get('elapsed_s', 0):>10.2f}")
    print(f"  {'-' * 55}")
    print(f"  {'total':<20} {'':<20} {total_elapsed:>10.2f}")
    print()
    print(f"  {n_success} step(s) succeeded, {n_fail} failed/missing")
    print(f"  ledger: reports/aegis_daily_v2_history.jsonl")

    _append_ledger({
        "run_utc":       _iso_utc(),
        "n_steps":       len(results),
        "n_success":     n_success,
        "n_failure":     n_fail,
        "total_elapsed_s": round(total_elapsed, 2),
        "results":       results,
    })

    if n_fail > 0:
        return 1
    _banner("DONE — dashboards will pick up new data within 60s (auto-refresh) "
              "or on manual refresh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
