"""DEV021 publish — emit all 6 JSON reports + equity-curve CSV."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
PUBLISH_DIR = _ROOT / "reports"

sys.path.insert(0, str(_ROOT / "research"))
from backtesting.lib import metrics                                                    # noqa: E402
from backtesting.compute import attribution, failure_analysis                            # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


def _sanitize(obj):
    """Recursively convert non-JSON-safe values."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


def build_and_publish(engine_result: dict) -> dict:
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)

    strat_state = engine_result["strat_state"]
    nifty = engine_result["nifty_series"]

    # Convert Nifty prices to daily returns for benchmark comparison
    nifty_ret = nifty.pct_change().dropna() if len(nifty) else pd.Series(dtype=float)

    # Dedup nifty_ret if any duplicate index snuck in
    if not nifty_ret.empty:
        nifty_ret = nifty_ret[~nifty_ret.index.duplicated(keep="last")]

    strategy_summaries = {}
    per_strategy_details = {}
    all_equity_rows = []

    for name, state in strat_state.items():
        daily_ret = state["daily_returns"]
        trade_log = state["trade_log"]
        trade_returns = [t["return_pct"] for t in trade_log]

        if daily_ret.empty:
            strategy_summaries[name] = {"status": "no_returns"}
            continue

        # Align benchmark to strategy date range — restrict to the OVERLAP window
        # (Nifty history from DEV017 is only ~300 days; older backtest dates
        # have no benchmark. Fabricating zeros there would corrupt alpha/beta.)
        if not nifty_ret.empty:
            common = daily_ret.index.intersection(nifty_ret.index)
            if len(common) >= 30:
                bench = nifty_ret.loc[common]
            else:
                bench = None
        else:
            bench = None

        m = metrics.all_metrics(daily_ret, bench, trade_returns)
        # Note that alpha/beta above are computed on OVERLAP window, not full backtest
        strategy_summaries[name] = _sanitize(m)
        if bench is not None:
            strategy_summaries[name]["benchmark_overlap_start"] = str(bench.index.min().date())
            strategy_summaries[name]["benchmark_overlap_end"]   = str(bench.index.max().date())
            strategy_summaries[name]["benchmark_overlap_days"]  = int(len(bench))

        # Turnover proxy (annualised, using rebal log)
        n_rebals = len(state["rebal_log"])
        avg_turnover = np.mean([r["turnover"] for r in state["rebal_log"]]) if state["rebal_log"] else 0.0
        annual_turnover = float(avg_turnover * 12)                             # monthly rebalance
        strategy_summaries[name]["turnover_annualised"] = round(annual_turnover, 3)
        strategy_summaries[name]["n_rebalances"] = n_rebals
        strategy_summaries[name]["avg_positions"] = float(np.mean(
            [r["n_positions"] for r in state["rebal_log"]])) if state["rebal_log"] else 0.0

        # Attribution + failure analysis per strategy
        attr = attribution.attribute_trades(trade_log)
        fail = failure_analysis.analyse_failures(daily_ret, trade_log)

        per_strategy_details[name] = {
            "attribution": _sanitize(attr),
            "failures":    _sanitize(fail),
        }

        # Equity curve rows
        cum = (1 + daily_ret).cumprod() * 100                                   # starts at 100
        for dt, val in cum.items():
            all_equity_rows.append({
                "strategy": name,
                "date":     dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt),
                "equity":   round(float(val), 4),
            })

    # Nifty benchmark equity curve
    if not nifty_ret.empty:
        first_dt = min([pd.to_datetime(state["daily_returns"].index.min())
                          for name, state in strat_state.items()
                          if not state["daily_returns"].empty], default=None)
        if first_dt is not None:
            bench_slice = nifty_ret.loc[nifty_ret.index >= first_dt]
            bench_cum = (1 + bench_slice).cumprod() * 100
            for dt, val in bench_cum.items():
                all_equity_rows.append({
                    "strategy": "BENCHMARK_NIFTY50",
                    "date":     dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt),
                    "equity":   round(float(val), 4),
                })
            bench_metrics = metrics.all_metrics(bench_slice, None, None)
            strategy_summaries["BENCHMARK_NIFTY50"] = _sanitize(bench_metrics)

    # ── 6 JSON deliverables per DEV021 spec ─────────────────────────────────
    backtest_summary = {
        "dev_version":      "DEV021 v0.1",
        "run_utc":          engine_result["run_utc"],
        "code_sha":         engine_result["code_sha"],
        "universe_size":    engine_result["universe_size"],
        "rebal_dates":      engine_result["rebal_dates"],
        "n_rebalances":     len(engine_result["rebal_dates"]),
        "strategies":       list(strat_state.keys()),
        "summary":          strategy_summaries,
    }

    strategy_comparison = {
        "run_utc":  engine_result["run_utc"],
        "strategies": [
            {
                "strategy":            name,
                "cagr":                strategy_summaries.get(name, {}).get("cagr"),
                "annual_volatility":   strategy_summaries.get(name, {}).get("annual_volatility"),
                "sharpe":              strategy_summaries.get(name, {}).get("sharpe_ratio"),
                "sortino":             strategy_summaries.get(name, {}).get("sortino_ratio"),
                "calmar":              strategy_summaries.get(name, {}).get("calmar_ratio"),
                "max_dd_pct":          strategy_summaries.get(name, {}).get("max_drawdown", {}).get("max_dd_pct")
                                         if isinstance(strategy_summaries.get(name, {}).get("max_drawdown"), dict) else None,
                "alpha":               strategy_summaries.get(name, {}).get("alpha"),
                "beta":                strategy_summaries.get(name, {}).get("beta"),
                "info_ratio":          strategy_summaries.get(name, {}).get("information_ratio"),
                "turnover":            strategy_summaries.get(name, {}).get("turnover_annualised"),
                "trade_win_rate":      (strategy_summaries.get(name, {}).get("trade_metrics") or {}).get("win_rate_pct"),
            }
            for name in list(strat_state.keys()) + (["BENCHMARK_NIFTY50"] if not nifty_ret.empty else [])
        ],
    }

    performance_metrics_all = {
        "run_utc": engine_result["run_utc"],
        "per_strategy": strategy_summaries,
    }

    signal_attribution = {
        "run_utc": engine_result["run_utc"],
        "note":    ("v0.1 does trade-level sector/industry attribution. "
                      "Signal-level attribution (which of the 11 dimensions drives alpha) "
                      "is deferred to v0.2 and requires re-scoring with each dimension "
                      "ablated in turn."),
        "per_strategy": {name: per_strategy_details.get(name, {}).get("attribution", {})
                          for name in strat_state},
    }

    failure_analysis_out = {
        "run_utc": engine_result["run_utc"],
        "per_strategy": {name: per_strategy_details.get(name, {}).get("failures", {})
                          for name in strat_state},
    }

    self_improvement = _build_self_improvement(strategy_summaries, per_strategy_details)

    # Write files
    paths = {}
    for name, payload in [
        ("backtest_summary.json",       backtest_summary),
        ("strategy_comparison.json",    strategy_comparison),
        ("performance_metrics.json",    performance_metrics_all),
        ("signal_attribution.json",     signal_attribution),
        ("failure_analysis.json",       failure_analysis_out),
        ("self_improvement.json",       self_improvement),
    ]:
        pth = PUBLISH_DIR / name
        with pth.open("w", encoding="utf-8") as f:
            json.dump(_sanitize(payload), f, indent=2, default=str)
        paths[name] = pth

    # Parquet + equity-curve CSV
    parquet_rows = []
    for name, s in strategy_summaries.items():
        row = {
            "strategy":       name,
            "cagr":           s.get("cagr"),
            "annual_vol":     s.get("annual_volatility"),
            "sharpe":         s.get("sharpe_ratio"),
            "sortino":        s.get("sortino_ratio"),
            "calmar":         s.get("calmar_ratio"),
            "alpha":          s.get("alpha"),
            "beta":           s.get("beta"),
            "info_ratio":     s.get("information_ratio"),
            "max_dd_pct":     s.get("max_drawdown", {}).get("max_dd_pct")
                               if isinstance(s.get("max_drawdown"), dict) else None,
            "turnover":       s.get("turnover_annualised"),
            "n_rebalances":   s.get("n_rebalances"),
            "avg_positions":  s.get("avg_positions"),
        }
        # trade metrics
        tm = s.get("trade_metrics") or {}
        row.update({
            "n_trades":       tm.get("n_trades"),
            "win_rate":       tm.get("win_rate_pct"),
            "profit_factor":  tm.get("profit_factor"),
            "avg_winner":     tm.get("avg_winner_pct"),
            "avg_loser":      tm.get("avg_loser_pct"),
            "expectancy":     tm.get("expectancy_pct"),
        })
        parquet_rows.append(row)
    parquet_path = PUBLISH_DIR / "backtest_summary.parquet"
    pd.DataFrame(parquet_rows).to_parquet(parquet_path, index=False)
    paths["backtest_summary.parquet"] = parquet_path

    csv_path = PUBLISH_DIR / "backtest_equity_curves.csv"
    pd.DataFrame(all_equity_rows).to_csv(csv_path, index=False)
    paths["backtest_equity_curves.csv"] = csv_path

    return {
        "paths": paths,
        "strategy_summaries": strategy_summaries,
    }


def _build_self_improvement(strategy_summaries: dict, details: dict) -> dict:
    """Advisory recommendations. Never auto-applied per ARCH001A Article V."""
    recs = []
    # Rank strategies by Sharpe
    ranked = sorted(strategy_summaries.items(),
                     key=lambda kv: kv[1].get("sharpe_ratio") or -99, reverse=True)
    if ranked:
        best = ranked[0]
        recs.append({
            "type":    "strategy_leaderboard",
            "message": f"Highest-Sharpe strategy on this run: {best[0]} "
                          f"(Sharpe={best[1].get('sharpe_ratio')})",
        })

    # Find any strategy underperforming benchmark on alpha
    for name, s in strategy_summaries.items():
        alpha = s.get("alpha")
        if alpha is not None and alpha < -0.02:
            recs.append({
                "type":    "underperforming_strategy",
                "strategy": name,
                "message": f"{name} has negative alpha ({alpha:.3f}) vs Nifty 50 — "
                              "consider re-weighting or removing dimensions.",
            })

    # High-turnover flag
    for name, s in strategy_summaries.items():
        t = s.get("turnover_annualised")
        if t is not None and t > 4.0:
            recs.append({
                "type":    "high_turnover",
                "strategy": name,
                "message": f"{name} annualised turnover = {t:.2f} — costs may erode alpha; "
                              "consider longer rebalance cadence.",
            })

    return {
        "run_utc": datetime.now(timezone.utc).isoformat() + "Z",
        "note":    "Advisory only. NO parameter auto-adjustment (ARCH001A Article V clause 5.1).",
        "recommendations": recs,
    }
