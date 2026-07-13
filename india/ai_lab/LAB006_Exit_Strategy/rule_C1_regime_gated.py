# india/ai_lab/LAB006_Exit_Strategy/rule_C1_regime_gated.py
"""
RULE C1 — regime-gated trailing stop (5% + P3 + Weak-regime-only).

Sealed pre-registration: rule_C1_preregistration.md (2026-07-13, amended same day pre-run).

WHAT THIS DOES:
- Trailing stop = 5% (single frozen value, no grid, no threshold mining)
- Re-entry policy = P3 (cooldown 20d + PIT-safe active-check)
- Regime gate = rule ACTIVE only when confidence_engine.current_regime() at cycle asof == "Weak"
- Cost stress @ 15/30/50 bps reported SEPARATELY (NOT PBO inputs)
- Three-period metrics: discovery (2022) / confirmation (2021 + 2023-2026) / full (2021-2026)
- DSR from trial_manifest (n_trials=29 including C1 itself)
- No PBO reported for standalone single-strategy pre-registration

The regime label at each cycle asof is queried from evidence.probability_matrix.regime_state_series,
which returns only pre-asof data by construction. No forward info.

Run: python india/ai_lab/LAB006_Exit_Strategy/rule_C1_regime_gated.py
"""
import sys
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.validation import deflated_sharpe
from india.feature_engine import load_panels
from india.evidence.probability_matrix import regime_state_series
from india.ai_lab.LAB006_Exit_Strategy.exit_lab import (
    run_backtest, run_baseline, metric_suite, read_trial_manifest_count, REPORTS,
)
from india.ai_lab.LAB006_Exit_Strategy.rule_C_trailing_stop import make_rule, make_active_check

STOP_PCT = 0.05                # LOCKED — from pre-registration
POLICY = "P3"                   # LOCKED
COST_GRID = [15, 30, 50]        # cost stress — reported separately, NOT PBO input
CAPITAL = 100_000
DISCOVERY_YEAR = 2022           # LOCKED — the year that inspired the hypothesis

RULE_C1_NAME = "C1(5%_P3_Weak-only)"


def _regime_at_asof(regime_series):
    """Return a closure(asof_date) -> True iff regime is 'Weak' at asof.
    Uses forward-fill on the regime series — reindex+ffill so any asof gets the last known label
    on or before that date. Never returns future info."""
    def _is_weak(asof):
        try:
            r = regime_series.reindex([pd.Timestamp(asof)], method="ffill").iloc[0]
        except Exception:
            return False
        return str(r) == "Weak"
    return _is_weak


def _period_slice(equity, mask_dates):
    """Slice an equity curve to the dates in mask_dates. Preserves order."""
    idx = equity.index[equity.index.isin(mask_dates)]
    return equity.reindex(idx)


def _period_metrics(equity, cycles_meta, cycle_asofs_in_period):
    """Compute metric suite restricted to cycles whose asof lies in `cycle_asofs_in_period`.
    Restricts the equity curve to those cycles' date windows AND filters cycles_meta similarly."""
    if not cycle_asofs_in_period:
        return {k: np.nan for k in ("cagr", "sharpe", "sortino", "max_dd", "cvar5", "ulcer",
                                    "recovery_days", "total_exits", "cycles_with_any_exit",
                                    "false_exit_rate", "opportunity_cost", "total_ret", "years")}
    date_windows = []
    for m in cycles_meta:
        if pd.Timestamp(m["asof"]) in cycle_asofs_in_period:
            date_windows.append((m["asof"], m["mature"]))
    if not date_windows:
        return {k: np.nan for k in ("cagr", "sharpe", "sortino", "max_dd", "cvar5", "ulcer",
                                    "recovery_days", "total_exits", "cycles_with_any_exit",
                                    "false_exit_rate", "opportunity_cost", "total_ret", "years")}
    # Concat the equity slices belonging to these cycles, rebase to start-of-period = 1.0
    slices = []
    for start, end in date_windows:
        seg = equity.loc[pd.Timestamp(start):pd.Timestamp(end)]
        slices.append(seg)
    if not slices:
        return {k: np.nan for k in ("cagr", "sharpe", "sortino", "max_dd", "cvar5", "ulcer",
                                    "recovery_days", "total_exits", "cycles_with_any_exit",
                                    "false_exit_rate", "opportunity_cost", "total_ret", "years")}
    # Rebase each segment to compound continuously — treat gaps as no-return
    combined = []
    running = 1.0
    for seg in slices:
        seg_norm = (seg / seg.iloc[0]) * running
        combined.append(seg_norm)
        running = seg_norm.iloc[-1]
    period_eq = pd.concat(combined)
    period_eq = period_eq[~period_eq.index.duplicated(keep="last")].sort_index()
    period_meta = [m for m in cycles_meta if pd.Timestamp(m["asof"]) in cycle_asofs_in_period]
    return metric_suite(period_eq, period_meta)


def main():
    n_trials = read_trial_manifest_count()
    # Pre-registration counts C1 as trial #29; the manifest returns 29 with the C1 line added.
    print(f"  trial manifest -> n_trials={n_trials} (strategy-search only; cost variants excluded)")
    print(f"  loading registry + price panel + regime series...")
    reg = pd.read_csv(ROOT / "data" / "aegis_registry.csv")
    closes, *_ = load_panels()
    reg_series = regime_state_series()
    is_weak = _regime_at_asof(reg_series)

    # ============ BASELINE (all cycles, no rule) ============
    print(f"  BASELINE (hold to mature, all cycles)...")
    base_eq, base_meta = run_baseline(reg, closes, initial_capital=CAPITAL, cost_bps=15)
    base_metrics = metric_suite(base_eq, base_meta)
    print(f"    baseline: CAGR {base_metrics['cagr']*100:+.2f}% · Sharpe {base_metrics['sharpe']:.2f} "
          f"· MaxDD {base_metrics['max_dd']*100:+.1f}% · Ulcer {base_metrics['ulcer']:.1f}")

    # ============ C1 (Weak-regime-gated 5% P3) at 15/30/50 bps ============
    rule = make_rule(STOP_PCT)
    active_check = make_active_check(STOP_PCT)
    c1_results = {}
    for cost_bps in COST_GRID:
        print(f"  {RULE_C1_NAME} cost={cost_bps}bps...")
        eq, meta = run_backtest(rule, RULE_C1_NAME, POLICY, reg, closes,
                                initial_capital=CAPITAL, cost_bps=cost_bps,
                                active_check_fn=active_check, cycle_filter=is_weak)
        m = metric_suite(eq, meta)
        dsr_d = deflated_sharpe(eq.pct_change().dropna(), n_trials=n_trials)
        c1_results[cost_bps] = {"eq": eq, "meta": meta, "metrics": m, "dsr": dsr_d}
        print(f"    CAGR {m['cagr']*100:+.2f}% · Sharpe {m['sharpe']:.2f} · MaxDD {m['max_dd']*100:+.1f}% "
              f"· Ulcer {m['ulcer']:.1f} · exits {m['total_exits'] or 0} "
              f"· false-exit {100*(m['false_exit_rate'] or 0):.0f}% · DSR {dsr_d['dsr']:.2f}")

    # ============ Three-period reporting (using 15bps as canonical) ============
    canonical = c1_results[15]
    eq_c1 = canonical["eq"]; meta_c1 = canonical["meta"]

    discovery_asofs = set()
    confirmation_asofs = set()
    for m in meta_c1:
        yr = pd.Timestamp(m["asof"]).year
        if yr == DISCOVERY_YEAR:
            discovery_asofs.add(pd.Timestamp(m["asof"]))
        else:
            confirmation_asofs.add(pd.Timestamp(m["asof"]))

    print(f"  three-period slice: discovery={len(discovery_asofs)} cycles, "
          f"confirmation={len(confirmation_asofs)} cycles")

    disc_c1 = _period_metrics(eq_c1, meta_c1, discovery_asofs)
    conf_c1 = _period_metrics(eq_c1, meta_c1, confirmation_asofs)
    full_c1 = canonical["metrics"]

    disc_base = _period_metrics(base_eq, base_meta, discovery_asofs)
    conf_base = _period_metrics(base_eq, base_meta, confirmation_asofs)
    full_base = base_metrics

    # Regime attribution: split by regime of each cycle's asof
    regime_buckets = {"Strong": set(), "Neutral": set(), "Weak": set()}
    for m in meta_c1:
        try:
            r = str(reg_series.reindex([pd.Timestamp(m["asof"])], method="ffill").iloc[0])
            if r in regime_buckets:
                regime_buckets[r].add(pd.Timestamp(m["asof"]))
        except Exception:
            continue
    regime_attribution = {r: (_period_metrics(eq_c1, meta_c1, cycles),
                              _period_metrics(base_eq, base_meta, cycles),
                              len(cycles))
                          for r, cycles in regime_buckets.items()}

    _write_report(base_metrics, c1_results, disc_c1, disc_base, conf_c1, conf_base,
                  full_c1, full_base, regime_attribution, n_trials, is_weak, meta_c1)


def _fmt(x, kind="num"):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    if kind == "pct":  return f"{x*100:+.1f}%"
    if kind == "pctabs": return f"{x*100:.1f}%"
    if kind == "int":  return f"{int(x)}"
    return f"{x:+.2f}"


def _write_report(base, c1_results, disc_c1, disc_base, conf_c1, conf_base,
                  full_c1, full_base, regime_attr, n_trials, is_weak_fn, meta_c1):
    now = datetime.now().date().isoformat()
    weak_cycles = [m for m in meta_c1 if is_weak_fn(m["asof"])]
    lines = [
        f"# Rule C1 — Regime-Gated Trailing Stop (5% + P3 + Weak-only)", "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_", "",
        f"Sealed pre-registration: `rule_C1_preregistration.md` (amended pre-run 2026-07-13).", "",
        "## What C1 is",
        f"- Stop: **{100*STOP_PCT:.0f}%** trailing (close-to-close, PIT-safe, gap-aware)",
        f"- Re-entry policy: **{POLICY}** with PIT-safe active check at cooldown_end",
        f"- Regime gate: rule ACTIVE only when `regime_state_series` at cycle asof == 'Weak'",
        f"- Cycles where rule fired: **{len(weak_cycles)} / {len(meta_c1)}** Weak cycles",
        f"- DSR n_trials = **{n_trials}** (from trial_manifest.md)",
        f"- PBO: **N/A** (single frozen pre-registered strategy — CSCV requires ≥4 distinct strategies)",
        "",
        "## FULL PERIOD 2021-2026 (descriptive)",
        "| Metric | Baseline | C1 (15bps) | Δ |",
        "|---|---|---|---|",
        f"| CAGR | {_fmt(full_base['cagr'],'pct')} | {_fmt(full_c1['cagr'],'pct')} | {_fmt(full_c1['cagr']-full_base['cagr'],'pct')} |",
        f"| Sharpe | {_fmt(full_base['sharpe'])} | {_fmt(full_c1['sharpe'])} | {_fmt(full_c1['sharpe']-full_base['sharpe'])} |",
        f"| MaxDD | {_fmt(full_base['max_dd'],'pct')} | {_fmt(full_c1['max_dd'],'pct')} | {_fmt(full_c1['max_dd']-full_base['max_dd'],'pct')} |",
        f"| Ulcer | {_fmt(full_base['ulcer'])} | {_fmt(full_c1['ulcer'])} | {_fmt(full_c1['ulcer']-full_base['ulcer'])} |",
        f"| CVaR(5%) | {_fmt(full_base['cvar5'],'pct')} | {_fmt(full_c1['cvar5'],'pct')} | {_fmt(full_c1['cvar5']-full_base['cvar5'],'pct')} |",
        f"| Total exits | 0 | {_fmt(full_c1['total_exits'],'int')} |  |",
        f"| False-exit % | — | {_fmt(full_c1['false_exit_rate'],'pctabs')} |  |",
        f"| DSR (n_trials={n_trials}) | — | {c1_results[15]['dsr']['dsr']:.3f} |  |",
        "",
        "## CONFIRMATION SAMPLE — 2021 + 2023-2026 (primary promotion evidence)",
        "| Metric | Baseline | C1 (15bps) | Δ |",
        "|---|---|---|---|",
        f"| CAGR | {_fmt(conf_base['cagr'],'pct')} | {_fmt(conf_c1['cagr'],'pct')} | {_fmt(conf_c1['cagr']-conf_base['cagr'],'pct')} |",
        f"| Sharpe | {_fmt(conf_base['sharpe'])} | {_fmt(conf_c1['sharpe'])} | {_fmt(conf_c1['sharpe']-conf_base['sharpe'])} |",
        f"| MaxDD | {_fmt(conf_base['max_dd'],'pct')} | {_fmt(conf_c1['max_dd'],'pct')} | {_fmt(conf_c1['max_dd']-conf_base['max_dd'],'pct')} |",
        f"| Ulcer | {_fmt(conf_base['ulcer'])} | {_fmt(conf_c1['ulcer'])} | {_fmt(conf_c1['ulcer']-conf_base['ulcer'])} |",
        f"| CVaR(5%) | {_fmt(conf_base['cvar5'],'pct')} | {_fmt(conf_c1['cvar5'],'pct')} | {_fmt(conf_c1['cvar5']-conf_base['cvar5'],'pct')} |",
        f"| False-exit % | — | {_fmt(conf_c1['false_exit_rate'],'pctabs')} |  |",
        "",
        "**Promotion evidence must come from THIS table, not the discovery table below.**",
        "",
        "## DISCOVERY PERIOD — 2022 only (hypothesis-generation; not confirmation evidence)",
        "| Metric | Baseline | C1 (15bps) | Δ |",
        "|---|---|---|---|",
        f"| CAGR | {_fmt(disc_base['cagr'],'pct')} | {_fmt(disc_c1['cagr'],'pct')} | {_fmt(disc_c1['cagr']-disc_base['cagr'],'pct')} |",
        f"| Sharpe | {_fmt(disc_base['sharpe'])} | {_fmt(disc_c1['sharpe'])} | {_fmt(disc_c1['sharpe']-disc_base['sharpe'])} |",
        f"| MaxDD | {_fmt(disc_base['max_dd'],'pct')} | {_fmt(disc_c1['max_dd'],'pct')} | {_fmt(disc_c1['max_dd']-disc_base['max_dd'],'pct')} |",
        f"| Ulcer | {_fmt(disc_base['ulcer'])} | {_fmt(disc_c1['ulcer'])} | {_fmt(disc_c1['ulcer']-disc_base['ulcer'])} |",
        "",
        "## Cost stress test — same strategy, different friction",
        "(NOT a PBO input. Confirms robustness to India trading friction.)",
        "| Cost (bps) | CAGR | Sharpe | MaxDD | Ulcer | Exits | False-exit |",
        "|:-:|:-:|:-:|:-:|:-:|:-:|:-:|",
    ]
    for cost_bps in COST_GRID:
        m = c1_results[cost_bps]["metrics"]
        lines.append(f"| {cost_bps} | {_fmt(m['cagr'],'pct')} | {_fmt(m['sharpe'])} | "
                     f"{_fmt(m['max_dd'],'pct')} | {_fmt(m['ulcer'])} | "
                     f"{_fmt(m['total_exits'],'int')} | {_fmt(m['false_exit_rate'],'pctabs')} |")
    lines.append("")

    lines.append("## Regime attribution (portfolio metrics restricted to each regime's cycles)")
    lines.append("| Regime | # cycles | C1 CAGR | Baseline CAGR | C1 MaxDD | Baseline MaxDD |")
    lines.append("|---|---|---|---|---|---|")
    for reg_name in ("Strong", "Neutral", "Weak"):
        c1_m, base_m, n = regime_attr[reg_name]
        lines.append(f"| {reg_name} | {n} | {_fmt(c1_m['cagr'],'pct')} | {_fmt(base_m['cagr'],'pct')} | "
                     f"{_fmt(c1_m['max_dd'],'pct')} | {_fmt(base_m['max_dd'],'pct')} |")
    lines.append("")

    # Promotion gate evaluation (from pre-registration)
    lines.append("## Promotion gate evaluation")
    def check(label, actual, threshold, op="<"):
        ok = (actual < threshold) if op == "<" else (actual > threshold)
        return f"- {'✅' if ok else '❌'} **{label}**: actual={actual}, gate {op} {threshold}"

    dsr_val = c1_results[15]["dsr"]["dsr"]
    # MaxDD is a negative decimal; IMPROVEMENT = c1 - baseline (positive when c1 is less negative)
    conf_dd_improve_pp = (conf_c1["max_dd"] - conf_base["max_dd"]) * 100 \
        if (conf_c1["max_dd"] == conf_c1["max_dd"] and conf_base["max_dd"] == conf_base["max_dd"]) else float("nan")
    full_dd_improve_pp = (full_c1["max_dd"] - full_base["max_dd"]) * 100
    conf_fe = conf_c1["false_exit_rate"] if conf_c1["false_exit_rate"] == conf_c1["false_exit_rate"] else 1.0

    lines.append(f"- DSR gate: {'✅' if dsr_val > 0.90 else '❌'} DSR={dsr_val:.3f}, gate > 0.90")
    lines.append(f"- Confirmation MaxDD improvement ≥ 5pp: {'✅' if conf_dd_improve_pp >= 5 else '❌'} "
                 f"actual={conf_dd_improve_pp:+.1f}pp")
    lines.append(f"- Full-period MaxDD improvement ≥ 3pp: {'✅' if full_dd_improve_pp >= 3 else '❌'} "
                 f"actual={full_dd_improve_pp:+.1f}pp")
    lines.append(f"- Confirmation false-exit < 40%: {'✅' if conf_fe < 0.40 else '❌'} "
                 f"actual={100*conf_fe:.0f}%")
    # Cost-robust check: does the 50bps variant still improve MaxDD vs baseline (loosely, ≥ 3pp)?
    try:
        cost50_dd_improve_pp = (c1_results[50]["metrics"]["max_dd"] - full_base["max_dd"]) * 100
        lines.append(f"- Cost-robust at 50bps (full-period MaxDD improvement ≥ 3pp): "
                     f"{'✅' if cost50_dd_improve_pp >= 3 else '❌'} actual={cost50_dd_improve_pp:+.1f}pp")
    except Exception:
        lines.append(f"- Cost-robust at 50bps: — (unable to compute)")
    # Regime attribution — does DD improvement come primarily from Weak-regime cycles?
    try:
        weak_c1, weak_base, _ = regime_attr["Weak"]
        weak_dd_improve_pp = (weak_c1["max_dd"] - weak_base["max_dd"]) * 100
        lines.append(f"- Weak-regime MaxDD improvement (rule mechanism sanity): "
                     f"{'✅' if weak_dd_improve_pp >= 3 else '❌'} actual={weak_dd_improve_pp:+.1f}pp")
    except Exception:
        pass
    lines.append("")
    lines.append("Overall: **PROMOTE** only if ALL gates pass. Operator confirms.")
    lines.append("")

    lines.append("## Reproducibility")
    lines.append(f"- Trial manifest n_trials = {n_trials} (recorded 2026-07-13)")
    lines.append(f"- Pre-registration: rule_C1_preregistration.md, amended pre-run same day")
    lines.append(f"- All parameters LOCKED before this run — no adjustment after seeing results")

    out = REPORTS / f"rule_C1_regime_gated_{now}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  report -> {out}")


if __name__ == "__main__":
    main()
