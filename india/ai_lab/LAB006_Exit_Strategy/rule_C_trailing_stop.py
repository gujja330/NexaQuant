# india/ai_lab/LAB006_Exit_Strategy/rule_C_trailing_stop.py
"""
RULE C — TRAILING STOP (audit-closure edition, scaffold bugs 1-4 fixed).

Hypothesis: a post-entry drawdown from the running high watermark of X% is a genuine downside
signal, and exiting immediately preserves capital better than riding the position to the next
63-day rebalance.

RESEARCH RULES (all applied):

1. GAP-AWARE EXECUTION — close-to-close: trigger day = first day CLOSE < peak_close * (1-stop).
   Execution = NEXT day's CLOSE. No fill-at-stop assumption; every trigger costs one extra day.

2. NO SAME-DAY HIGH/LOW LEAKAGE — daily CLOSE prices only. No intraday HIGH-then-LOW ordering.

3. P2 EXCLUDED FROM PROMOTION analysis due to structural capital-concentration bug. Reported for
   completeness with a clear caveat, but not eligible for the promotion gate.

4. P3 USES PIT-SAFE ACTIVE CHECK — a point-in-time test of "is the drawdown-from-peak still in
   effect at cooldown_end?" using ONLY history from asof to cooldown_end. No forward info.

5. COST SENSITIVITY at 15/30/50 bps — same strategy, different friction. Reported SEPARATELY, NOT
   as inputs to PBO. Cost variants are stress tests of a fixed strategy, not competing strategies.

6. NO THRESHOLD MINING — fixed grid {5%, 8%, 10%, 12%}. Not amended after seeing results.

7. EXIT QUALITY DIAGNOSTICS per stop level: exit-return / hold-to-mature / recovery / false-exit%.

8. PBO across the FULL 12-config candidate matrix (4 stops × 3 policies) — one PBO number, not
   per-config. That's what Bailey-López de Prado CSCV actually measures.

9. DSR n_trials from `trial_manifest.md` — cumulative Lab-wide strategy-search count, NOT hardcoded.

Run: python india/ai_lab/LAB006_Exit_Strategy/rule_C_trailing_stop.py --sweep-costs
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.validation import deflated_sharpe
from india.feature_engine import load_panels
from india.ai_lab.LAB006_Exit_Strategy.exit_lab import (
    run_backtest, run_baseline, simulate_cycle, metric_suite,
    read_trial_manifest_count, pbo_across_configs, REPORTS,
)

STOP_GRID = [0.05, 0.08, 0.10, 0.12]        # FIXED — do NOT modify after seeing results
COST_GRID = [15, 30, 50]                     # cost sensitivity — reported SEPARATELY from PBO


def make_rule(stop_pct):
    """Trailing stop rule with close-to-close execution.
    Trigger: today's CLOSE < peak_close_so_far * (1 - stop_pct).
    Execution: sell at NEXT day's CLOSE (returned trigger index = i+1)."""
    def _rule(sym, entry_px, path, pre_history):
        if len(path) < 3:
            return (False, None, "path too short")
        closes = path.values.astype(float)
        peak = closes[0]
        for i in range(1, len(closes)):
            peak = max(peak, closes[i])
            if closes[i] < peak * (1 - stop_pct):
                if i + 1 >= len(closes):
                    return (False, None, f"trigger on last day (no exec bar)")
                return (True, i + 1, f"DD -{100*(1 - closes[i]/peak):.1f}% at bar {i}")
        return (False, None, "no trigger")
    return _rule


def make_active_check(stop_pct):
    """POINT-IN-TIME active-signal check. Given history from asof through 'now', returns True iff
    the trailing-stop signal is CURRENTLY active — i.e., today's close is below (peak so far) *
    (1-stop_pct). Uses ONLY the passed history — no forward info."""
    def _active(sym, entry_px, history_up_to_now, pre_history):
        if history_up_to_now is None or len(history_up_to_now) < 1:
            return False
        vals = history_up_to_now.values.astype(float)
        peak = float(np.max(vals))
        now = float(vals[-1])
        return now < peak * (1 - stop_pct)
    return _active


def _exit_quality_meta(cycle_rows, closes_panel, stop_pct):
    """Diagnostics: for each triggered exit in a cycle, record exit-ret / hold-to-mature / recovery."""
    from india.ai_lab.LAB006_Exit_Strategy.exit_lab import _stock_path
    rule = make_rule(stop_pct)
    asof = pd.Timestamp(cycle_rows["asof"].iloc[0])
    mature = pd.Timestamp(cycle_rows["mature_date"].iloc[0])
    diagnostics = []
    for _, r in cycle_rows.iterrows():
        sym = r["symbol"]
        path = _stock_path(closes_panel, sym, asof, mature)
        if len(path) < 3:
            continue
        pre = closes_panel[sym].dropna().loc[:asof].iloc[:-1].tail(180) if sym in closes_panel.columns else pd.Series(dtype=float)
        entry_px = float(path.iloc[0])
        triggered, i, reason = rule(sym, entry_px, path, pre)
        if not triggered:
            continue
        exit_px = float(path.iloc[i])
        hold_to_mature = float(path.iloc[-1])
        post_exit_max = float(path.iloc[i:].max())
        exit_ret = 100 * (exit_px - entry_px) / entry_px
        hold_ret = 100 * (hold_to_mature - entry_px) / entry_px
        recovery_pct = 100 * (post_exit_max / exit_px - 1)
        false_exit = recovery_pct >= 5.0
        diagnostics.append({
            "asof": asof, "symbol": sym, "reason": reason,
            "exit_ret_pct": exit_ret, "hold_to_mature_pct": hold_ret,
            "hold_minus_exit_pp": hold_ret - exit_ret,
            "post_exit_max_recovery_pct": recovery_pct, "false_exit": false_exit,
        })
    return diagnostics


def _build_config_returns_matrix(main_results_equity):
    """Given a dict {config_name: equity_series}, return a T x N DataFrame of daily returns
    aligned on the intersection of all indices. This is the CANDIDATE MATRIX for PBO."""
    common_idx = None
    for eq in main_results_equity.values():
        idx = eq.index
        common_idx = idx if common_idx is None else common_idx.intersection(idx)
    if common_idx is None or len(common_idx) < 30:
        return pd.DataFrame()
    df = pd.DataFrame({name: eq.reindex(common_idx).pct_change() for name, eq in main_results_equity.items()})
    return df.dropna(how="any")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--sweep-costs", action="store_true", help="also sweep cost_bps ∈ {15,30,50}")
    a = ap.parse_args()

    n_trials = read_trial_manifest_count()
    print(f"  trial manifest -> n_trials={n_trials} (strategy-search trials only)")
    print(f"  loading registry + price panel...")
    reg = pd.read_csv(ROOT / "data" / "aegis_registry.csv")
    closes, *_ = load_panels()

    print(f"  running BASELINE (hold to mature)...")
    base_eq, base_meta = run_baseline(reg, closes, initial_capital=a.capital, cost_bps=15)
    base_metrics = metric_suite(base_eq, base_meta)
    print(f"    baseline: CAGR {base_metrics['cagr']*100:+.2f}% · Sharpe {base_metrics['sharpe']:.2f} "
          f"· MaxDD {base_metrics['max_dd']*100:+.1f}% · Ulcer {base_metrics['ulcer']:.1f}")

    # Main sweep — full 12-config matrix at 15bps
    equity_by_config = {"baseline": base_eq}
    main_results = []
    all_diagnostics = []
    for stop_pct in STOP_GRID:
        rule = make_rule(stop_pct)
        active_check = make_active_check(stop_pct)      # for P3
        for policy in ("P1", "P2", "P3"):
            config_name = f"stop{100*stop_pct:.0f}_{policy}"
            print(f"  RULE C {config_name} cost=15bps...")
            eq, meta = run_backtest(rule, config_name, policy, reg, closes,
                                    initial_capital=a.capital, cost_bps=15,
                                    active_check_fn=active_check)
            m = metric_suite(eq, meta)
            equity_by_config[config_name] = eq
            dsr_d = deflated_sharpe(eq.pct_change().dropna(), n_trials=n_trials)
            main_results.append({
                "stop_pct": stop_pct, "policy": policy, "cost_bps": 15,
                "config": config_name, "excluded_from_promotion": (policy == "P2"),
                "cagr": m["cagr"], "sharpe": m["sharpe"], "sortino": m["sortino"],
                "max_dd": m["max_dd"], "cvar5": m["cvar5"], "ulcer": m["ulcer"],
                "recovery_days": m["recovery_days"],
                "total_exits": m["total_exits"], "cycles_with_any_exit": m["cycles_with_any_exit"],
                "false_exit_rate": m["false_exit_rate"], "opportunity_cost": m["opportunity_cost"],
                "dsr": dsr_d["dsr"],
            })
            fe = m['false_exit_rate']
            print(f"    CAGR {m['cagr']*100:+.2f}% · Sharpe {m['sharpe']:.2f} · MaxDD {m['max_dd']*100:+.1f}% "
                  f"· Ulcer {m['ulcer']:.1f} · exits {m['total_exits']} · false-exit "
                  f"{100*fe if fe==fe else 0:.0f}% · DSR {dsr_d['dsr']:.2f}")

        # Exit-quality diagnostics for this stop level (same across policies — depends only on trigger)
        cycles = reg[(reg["source"] == "historical") & (reg["scored"] == 1)]
        for _, grp in cycles.groupby("rec_id", sort=False):
            all_diagnostics.extend([{"stop_pct": stop_pct, **d}
                                    for d in _exit_quality_meta(grp, closes, stop_pct)])

    # Full-matrix PBO across the 12 (stop, policy) configs (baseline excluded from candidate set)
    non_baseline = {k: v for k, v in equity_by_config.items() if k != "baseline"}
    matrix = _build_config_returns_matrix(non_baseline)
    try:
        pbo_all = pbo_across_configs(matrix, S=8)
        print(f"  FULL-MATRIX PBO (12 configs, S=8 folds) = {pbo_all:.3f}")
    except ValueError as e:
        pbo_all = float("nan")
        print(f"  PBO computation failed: {e}")

    # Cost sensitivity — reported SEPARATELY, NOT PBO inputs
    cost_results = []
    if a.sweep_costs:
        # take top 3 by Sharpe from non-P2 configs (per exclusion rule)
        eligible = [r for r in main_results if r["policy"] != "P2"]
        best3 = sorted(eligible, key=lambda r: -r["sharpe"])[:3]
        for cfg in best3:
            rule = make_rule(cfg["stop_pct"])
            active_check = make_active_check(cfg["stop_pct"])
            for cost_bps in COST_GRID:
                if cost_bps == 15:
                    continue
                print(f"  cost stress: {cfg['config']} cost={cost_bps}bps...")
                eq, meta = run_backtest(rule, cfg["config"], cfg["policy"], reg, closes,
                                        initial_capital=a.capital, cost_bps=cost_bps,
                                        active_check_fn=active_check)
                m = metric_suite(eq, meta)
                cost_results.append({
                    "config": cfg["config"], "cost_bps": cost_bps,
                    "cagr": m["cagr"], "sharpe": m["sharpe"], "max_dd": m["max_dd"], "ulcer": m["ulcer"],
                    "total_exits": m["total_exits"], "false_exit_rate": m["false_exit_rate"],
                })

    _write_report(base_metrics, main_results, cost_results, all_diagnostics, pbo_all, n_trials)


def _fmt(x, kind="num"):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    if kind == "pct": return f"{x*100:+.1f}%"
    if kind == "pctabs": return f"{x*100:.1f}%"
    if kind == "int": return f"{int(x)}"
    return f"{x:+.2f}"


def _write_report(base, main_results, cost_results, diagnostics, pbo_all, n_trials):
    now = datetime.now().date().isoformat()
    lines = [f"# Rule C (trailing stop) — Audit-closure Report {now}",
             "",
             f"_Generated {datetime.now().isoformat(timespec='seconds')}_", "",
             "> **This is the fixed-scaffold rerun.** Supersedes the 2026-07-13 provisional report.",
             "> Bugs fixed: (1) per-exit false-exit denominator; (2) PIT-safe P3 active-check; "
             "(3) full-matrix PBO across all 12 configs; (4) DSR n_trials from trial_manifest.",
             "> P2 results included FOR COMPLETENESS but excluded from promotion analysis due to "
             "structural capital-concentration.",
             "",
             "## Baseline",
             f"CAGR **{base['cagr']*100:+.2f}%** · Sharpe **{base['sharpe']:.2f}** · MaxDD **{base['max_dd']*100:+.1f}%** · "
             f"Ulcer {base['ulcer']:.1f} · CVaR(5%) {base['cvar5']*100:+.2f}%",
             "",
             "## Full-matrix PBO",
             f"**PBO = {pbo_all:.3f}** across the 12 (stop × policy) configs, S=8 folds. "
             f"DSR n_trials = {n_trials} (from trial_manifest.md).",
             "Interpretation: PBO < 0.10 = robust config selection; > 0.50 = overfit.",
             "",
             "## Main sweep — cost=15bps",
             "| Stop | Policy | Notes | CAGR | Sharpe | Sortino | MaxDD | CVaR(5%) | Ulcer | Recovery | Exits | False-exit | Opp cost | DSR |",
             "|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|"]

    for r in main_results:
        note = "⚠ excluded (P2 concentration)" if r["excluded_from_promotion"] else ""
        lines.append(f"| {100*r['stop_pct']:.0f}% | {r['policy']} | {note} | "
                     f"{_fmt(r['cagr'], 'pct')} | {_fmt(r['sharpe'])} | {_fmt(r['sortino'])} | "
                     f"{_fmt(r['max_dd'], 'pct')} | {_fmt(r['cvar5'], 'pct')} | {_fmt(r['ulcer'])} | "
                     f"{_fmt(r['recovery_days'], 'int')} | {_fmt(r['total_exits'], 'int')} | "
                     f"{_fmt(r['false_exit_rate'], 'pctabs')} | {_fmt(r['opportunity_cost'])} | "
                     f"{_fmt(r['dsr'])} |")

    lines.append("")
    if cost_results:
        lines.append("## Cost sensitivity — top 3 non-P2 configs")
        lines.append("(Same strategy under different friction — **NOT a PBO input**)")
        lines.append("| Config | Cost (bps) | CAGR | Sharpe | MaxDD | Ulcer | Exits | False-exit |")
        lines.append("|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|")
        for r in cost_results:
            lines.append(f"| {r['config']} | {r['cost_bps']} | {_fmt(r['cagr'], 'pct')} | "
                         f"{_fmt(r['sharpe'])} | {_fmt(r['max_dd'], 'pct')} | {_fmt(r['ulcer'])} | "
                         f"{_fmt(r['total_exits'], 'int')} | {_fmt(r['false_exit_rate'], 'pctabs')} |")
        lines.append("")

    lines.append("## Exit-quality diagnostics (per stop level, across all triggered exits)")
    if diagnostics:
        d = pd.DataFrame(diagnostics)
        lines.append("| Stop | # exits | Avg exit ret | Avg hold-to-mature | Avg missed recovery | False-exit % |")
        lines.append("|:-:|:-:|:-:|:-:|:-:|:-:|")
        for stop_pct in STOP_GRID:
            g = d[d["stop_pct"] == stop_pct]
            if g.empty:
                continue
            n = len(g)
            avg_exit = g["exit_ret_pct"].mean()
            avg_hold = g["hold_to_mature_pct"].mean()
            avg_rec = g["post_exit_max_recovery_pct"].mean()
            false_rate = 100 * g["false_exit"].mean()
            lines.append(f"| {100*stop_pct:.0f}% | {n} | {avg_exit:+.1f}% | {avg_hold:+.1f}% | "
                         f"+{avg_rec:.1f}% | {false_rate:.0f}% |")
    lines.append("")

    out = REPORTS / f"rule_C_audit_closure_{now}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  report -> {out}")
    if diagnostics:
        pd.DataFrame(diagnostics).to_csv(REPORTS / f"rule_C_exit_diagnostics_{now}.csv", index=False)


if __name__ == "__main__":
    main()
