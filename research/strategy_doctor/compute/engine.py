"""DEV027 orchestration.

Reads DEV025's trade history, runs every diagnostic on every trade,
aggregates into root-cause tables + patterns + improvement plan.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from strategy_doctor.lib import diagnostics                                          # noqa: E402


REPORTS_DIR = _ROOT / "reports"
LEARNING_PARQUET = REPORTS_DIR / "learning.parquet"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _load_context() -> tuple[dict | None, dict | None]:
    """Load global + sector context for regime/sector diagnostics."""
    global_ctx = None
    sector_ctx = None
    for name, target in [("global_context.json", "global"), ("sector_context.json", "sector")]:
        p = REPORTS_DIR / name
        if p.exists():
            try:
                data = json.load(p.open("r", encoding="utf-8"))
                if target == "global":
                    global_ctx = data
                else:
                    sector_ctx = data
            except Exception:
                pass
    return global_ctx, sector_ctx


def _run_diagnostics_for_trade(trade: dict, cohort: list[dict],
                                 global_ctx: dict | None,
                                 sector_ctx: dict | None) -> list[diagnostics.Diagnosis]:
    """Run all diagnostics on one trade. Return only firing diagnoses."""
    results = []

    # Company-level diagnostics
    for fn in (diagnostics.wrong_company, diagnostics.late_entry, diagnostics.early_exit,
                 diagnostics.weak_conviction, diagnostics.overconfidence,
                 diagnostics.underconfidence, diagnostics.stop_loss_ineffective,
                 diagnostics.liquidity_shock, diagnostics.volatility_risk):
        d = fn(trade)
        if d.fires:
            results.append(d)

    # Sector diagnostics
    d = diagnostics.wrong_sector(trade, sector_ctx or {})
    if d.fires:
        results.append(d)

    # Regime diagnostics
    d = diagnostics.wrong_regime(trade, global_ctx or {})
    if d.fires:
        results.append(d)

    # Cohort-level diagnostics
    for fn in (diagnostics.high_correlation, diagnostics.excess_concentration,
                 diagnostics.macro_shock):
        d = fn(trade, cohort)
        if d.fires:
            results.append(d)

    return results


def run(verbose: bool = True) -> dict:
    if not LEARNING_PARQUET.exists():
        return {"error": f"{LEARNING_PARQUET} missing — run DEV025 first"}

    trades_df = pd.read_parquet(LEARNING_PARQUET)
    if trades_df.empty:
        return {"error": "learning.parquet is empty"}

    if verbose:
        print(f"  loaded {len(trades_df)} trades from DEV025 cache")

    global_ctx, sector_ctx = _load_context()

    # Group by cohort (entry_date)
    cohorts: dict[str, list[dict]] = defaultdict(list)
    for t in trades_df.to_dict(orient="records"):
        cohorts[t.get("entry_date", "unknown")].append(t)

    # Per-trade diagnostics
    per_trade_rows = []
    all_diagnoses: list[dict] = []
    poor_div_by_cohort: dict[str, dict | None] = {}

    for cohort_date, cohort_trades in cohorts.items():
        # Poor diversification is a cohort-level flag
        pd_diag = diagnostics.poor_diversification(cohort_trades)
        if pd_diag.fires:
            poor_div_by_cohort[cohort_date] = {
                "cohort_date": cohort_date,
                "evidence": pd_diag.evidence, "severity": pd_diag.severity,
            }

        for trade in cohort_trades:
            diags = _run_diagnostics_for_trade(trade, cohort_trades, global_ctx, sector_ctx)
            categories = [d.category for d in diags]
            per_trade_rows.append({
                "entry_date":       trade.get("entry_date"),
                "exit_date":        trade.get("exit_date"),
                "ticker":           trade.get("ticker"),
                "sector":           trade.get("sector"),
                "industry":         trade.get("industry"),
                "return_pct":       trade.get("return_pct"),
                "is_winner":        trade.get("is_winner"),
                "n_diagnoses":      len(diags),
                "categories":       ",".join(categories) if categories else "",
                "primary_severity": diags[0].severity if diags else "NONE",
            })
            for d in diags:
                all_diagnoses.append({
                    "ticker": trade.get("ticker"),
                    "entry_date": trade.get("entry_date"),
                    "return_pct": trade.get("return_pct"),
                    "category": d.category,
                    "evidence": d.evidence,
                    "severity": d.severity,
                    "trade_outcome": "winner" if trade.get("is_winner") else "loser",
                })

    if verbose:
        print(f"  diagnostics: {len(all_diagnoses)} firings across {len(trades_df)} trades")

    # ── Root cause aggregation per losing trade ──────────────────────────
    losing_trades = [t for t in per_trade_rows if not t["is_winner"]]
    winning_trades = [t for t in per_trade_rows if t["is_winner"]]

    # ── Failure patterns: count categories across losing trades ──────────
    failure_counts: dict[str, int] = defaultdict(int)
    failure_by_sector: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for d in all_diagnoses:
        if d["trade_outcome"] == "loser":
            failure_counts[d["category"]] += 1
            sec = next((t.get("sector") for t in per_trade_rows
                          if t["ticker"] == d["ticker"] and t["entry_date"] == d["entry_date"]),
                         "Unknown")
            failure_by_sector[sec][d["category"]] += 1

    failure_patterns = sorted(
        [{"category": k, "count": v} for k, v in failure_counts.items()],
        key=lambda r: r["count"], reverse=True,
    )

    # ── Success patterns: which winning combos ──────────────────────────
    winning_sector_counts: dict[str, int] = defaultdict(int)
    winning_industry_counts: dict[str, int] = defaultdict(int)
    for t in winning_trades:
        if t.get("sector"): winning_sector_counts[t["sector"]] += 1
        if t.get("industry"): winning_industry_counts[t["industry"]] += 1

    success_patterns = {
        "top_winning_sectors":   sorted(winning_sector_counts.items(),
                                          key=lambda kv: kv[1], reverse=True)[:5],
        "top_winning_industries": sorted(winning_industry_counts.items(),
                                            key=lambda kv: kv[1], reverse=True)[:5],
    }

    # ── Improvement plan (advisory) ──────────────────────────────────────
    improvement_plan = _build_improvement_plan(failure_counts, failure_by_sector,
                                                  poor_div_by_cohort)

    return {
        "run_utc":            datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":           _git_sha(),
        "dev_version":        "DEV027 v0.1",
        "n_trades":           len(trades_df),
        "n_winners":          len(winning_trades),
        "n_losers":           len(losing_trades),
        "n_diagnoses_fired":  len(all_diagnoses),
        "per_trade":          per_trade_rows,
        "all_diagnoses":      all_diagnoses,
        "failure_patterns":   failure_patterns,
        "failure_by_sector":  {k: dict(v) for k, v in failure_by_sector.items()},
        "success_patterns":   success_patterns,
        "poor_div_cohorts":   list(poor_div_by_cohort.values()),
        "improvement_plan":   improvement_plan,
    }


def _build_improvement_plan(failure_counts: dict, failure_by_sector: dict,
                              poor_div_by_cohort: dict) -> list[dict]:
    """Turn top failure patterns into concrete advisory suggestions."""
    plan = []

    # Top 3 failure categories -> improvement item each
    sorted_failures = sorted(failure_counts.items(), key=lambda kv: kv[1], reverse=True)
    for cat, count in sorted_failures[:5]:
        if count < 5:                                          # noise floor
            continue
        item = {
            "priority":   count,
            "failure_category": cat,
            "n_occurrences":    count,
        }
        # Category-specific advisory
        if cat == "overconfidence":
            item["evidence"] = f"{count} trades lost while confidence >= 0.85"
            item["action"] = "Add isotonic-regression post-processing to DEV020 confidence output"
            item["target_module"] = "DEV020 confidence -> DEV029 Confidence Calibration (planned)"
        elif cat == "wrong_sector":
            item["evidence"] = f"{count} losing trades entered while parent sector was Weak"
            item["action"] = "Add sector-score gate to DEV023 recommendation rules"
            item["target_module"] = "DEV023"
        elif cat == "wrong_regime":
            item["evidence"] = f"{count} losing trades under Risk-Off regime"
            item["action"] = "Reduce Buy criteria strictness during Risk-Off"
            item["target_module"] = "DEV023"
        elif cat == "excess_concentration":
            item["evidence"] = f"{count} losing trades in over-concentrated cohorts"
            item["action"] = "Tighten DEV022 sector cap from 35% to 25%"
            item["target_module"] = "DEV022"
        elif cat == "high_correlation":
            item["evidence"] = f"{count} losing trades in same-sector concurrent bets"
            item["action"] = "Apply correlation cap in DEV022 min-var / hrp allocation"
            item["target_module"] = "DEV022"
        elif cat == "late_entry":
            item["evidence"] = f"{count} trades peaked early then reverted"
            item["action"] = "Add momentum-decay filter to DEV023 entry timing"
            item["target_module"] = "DEV023 entry_exit"
        elif cat == "macro_shock":
            item["evidence"] = f"{count} trades hit by market-wide events"
            item["action"] = "Track macro-shock cohorts separately — do not "
            item["action"] += "attribute cause to stock selection"
            item["target_module"] = "monitoring / DEV017"
        else:
            item["evidence"] = f"{count} occurrences of {cat}"
            item["action"] = f"Investigate {cat} pattern; propose module fix"
            item["target_module"] = "TBD"

        plan.append(item)

    if len(poor_div_by_cohort) >= 3:
        plan.append({
            "priority":         len(poor_div_by_cohort),
            "failure_category": "poor_diversification",
            "n_occurrences":    len(poor_div_by_cohort),
            "evidence":         f"{len(poor_div_by_cohort)} cohorts had <=3 sectors",
            "action":           "Enforce minimum-4-sector constraint in DEV022",
            "target_module":    "DEV022 constraints",
        })

    plan.sort(key=lambda x: x["priority"], reverse=True)
    return plan
