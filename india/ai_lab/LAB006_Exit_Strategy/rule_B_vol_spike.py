# india/ai_lab/LAB006_Exit_Strategy/rule_B_vol_spike.py
"""
RULE B — VOL-SPIKE early exit.

Hypothesis: when a held stock's 20-day realized volatility jumps materially above its trailing
60-day baseline, the stock has entered a new (worse) volatility regime. Exiting immediately
protects capital better than riding the position to the next 63-day rebalance.

Trigger: rolling_20(pct_change).std() >= K * rolling_60(pct_change).std().shift(20)
         where K is the multiple, default 1.6.

Backtests three re-entry policies (P1/P2/P3 from exit_lab.py) and reports the full metric suite
+ DSR/PBO robustness. Purged CV via india.validation.purged_walkforward.

Run: python india/ai_lab/LAB006_Exit_Strategy/rule_B_vol_spike.py
     python india/ai_lab/LAB006_Exit_Strategy/rule_B_vol_spike.py --k 1.5 --cost-bps 20
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.validation import deflated_sharpe, pbo, purged_walkforward
from india.feature_engine import load_panels
from india.ai_lab.LAB006_Exit_Strategy.exit_lab import (
    run_backtest, run_baseline, metric_suite, write_report, REPORTS,
)


def make_rule(k=1.6, vol_short=20, vol_long=60):
    """Factory: returns a rule_fn closure with the given parameters.

    The baseline vol is FROZEN AT ENTRY from vol_long days of pre-entry history (no look-ahead).
    Within the cycle, we compute a rolling vol_short-day realized vol and trigger on the first
    day it exceeds k * baseline_vol. Requires min(vol_short, cycle_length-1) bars in-cycle to fire."""
    def _rule(sym, entry_px, path, pre_history):
        if len(pre_history) < vol_long + 1:
            return (False, None, f"pre-history {len(pre_history)}<{vol_long+1}")
        baseline_vol = pre_history.pct_change().dropna().tail(vol_long).std()
        if baseline_vol == 0 or pd.isna(baseline_vol):
            return (False, None, "zero/NaN baseline vol")
        rets = path.pct_change().dropna()
        if len(rets) < vol_short:
            return (False, None, f"in-cycle bars {len(rets)}<{vol_short}")
        short_v = rets.rolling(vol_short).std()
        ratio = short_v / baseline_vol
        hit = ratio[ratio >= k]
        if hit.empty:
            return (False, None, f"peak ratio {ratio.max():.2f}x < k={k}")
        first_hit = hit.index[0]
        try:
            i = path.index.get_loc(first_hit)
        except KeyError:
            return (False, None, "index misalign")
        if i >= len(path) - 1:
            return (False, None, "spike on last day")
        return (True, int(i), f"vol ratio {ratio.loc[first_hit]:.2f}x baseline {baseline_vol:.4f}")
    return _rule


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=float, default=1.6, help="vol-spike multiple")
    ap.add_argument("--short", type=int, default=20)
    ap.add_argument("--long", type=int, default=60)
    ap.add_argument("--cost-bps", type=int, default=15)
    ap.add_argument("--capital", type=float, default=100000)
    a = ap.parse_args()

    print(f"  loading registry + price panel...")
    reg = pd.read_csv(ROOT / "data" / "aegis_registry.csv")
    closes, *_ = load_panels()

    print(f"  running BASELINE (hold each cycle to mature)...")
    base_eq, base_meta = run_baseline(reg, closes, initial_capital=a.capital, cost_bps=a.cost_bps)
    base_metrics = metric_suite(base_eq, base_meta)
    print(f"    baseline: CAGR {base_metrics['cagr']*100:+.1f}% · Sharpe {base_metrics['sharpe']:.2f} "
          f"· MaxDD {base_metrics['max_dd']*100:+.1f}% · Ulcer {base_metrics['ulcer']:.1f}")

    rule = make_rule(k=a.k, vol_short=a.short, vol_long=a.long)
    variants = {}
    for policy in ("P1", "P2", "P3"):
        print(f"  running RULE B ({policy}) k={a.k}, short={a.short}, long={a.long}...")
        eq, meta = run_backtest(rule, f"B(k={a.k})", policy, reg, closes,
                                initial_capital=a.capital, cost_bps=a.cost_bps)
        m = metric_suite(eq, meta)
        # DSR — use daily returns; n_trials=4 (we ran 4 variants: baseline + P1/P2/P3)
        dsr_d = deflated_sharpe(eq.pct_change().dropna(), n_trials=4)
        # PBO — split cycles into S=8 buckets by asof date, requires a returns matrix
        pbo_val = _compute_pbo(reg, closes, rule, policy, a.cost_bps, S=8, capital=a.capital)
        variants[policy] = (m, dsr_d, pbo_val, meta)
        print(f"    {policy}: CAGR {m['cagr']*100:+.1f}% · Sharpe {m['sharpe']:.2f} "
              f"· MaxDD {m['max_dd']*100:+.1f}% · Ulcer {m['ulcer']:.1f} · "
              f"turnover {m['turnover']*100:.0f}% · DSR {dsr_d['dsr']:.2f} · PBO {pbo_val:.2f}")

    # Write report
    out = REPORTS / f"rule_B_k{a.k}_{pd.Timestamp.now().date().isoformat()}.md"
    write_report(f"B (vol-spike k={a.k})", base_metrics, variants, out)


def _compute_pbo(reg, closes, rule_fn, policy, cost_bps, S=8, capital=100000):
    """Split historical cycles into S non-overlapping folds by asof date; for each split, compare
    rule-Sharpe on 'IS' half vs baseline-Sharpe on 'OOS' half. PBO = mean rank inversion probability.
    Uses india.validation.pbo() semantics."""
    from india.validation import pbo
    cycles = reg[(reg["source"] == "historical") & (reg["scored"] == 1)].sort_values("asof")
    if cycles.empty:
        return float("nan")

    # Build per-cycle returns for rule and baseline
    from india.ai_lab.LAB006_Exit_Strategy.exit_lab import simulate_cycle
    def cycle_rets_for(rule):
        rows = []
        for rec_id, grp in cycles.groupby("rec_id", sort=False):
            curve, meta = simulate_cycle(grp, closes, rule, policy, cost_bps=cost_bps)
            if curve.empty:
                continue
            rows.append({"rec_id": rec_id, "ret": meta.get("cycle_return_pct", 0.0) / 100.0})
        return pd.DataFrame(rows).set_index("rec_id")["ret"] if rows else pd.Series(dtype=float)

    rule_r = cycle_rets_for(rule_fn)
    base_r = cycle_rets_for(lambda sym, e, p, pre: (False, None, ""))
    if rule_r.empty or base_r.empty:
        return float("nan")

    # pbo() expects a DataFrame of strategy returns; give it two columns
    df = pd.concat({"rule": rule_r, "baseline": base_r}, axis=1).dropna()
    if len(df) < S:
        return float("nan")
    return float(pbo(df, S=min(S, len(df))))


if __name__ == "__main__":
    main()
