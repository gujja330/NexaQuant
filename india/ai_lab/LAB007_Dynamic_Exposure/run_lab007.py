# india/ai_lab/LAB007_Dynamic_Exposure/run_lab007.py
"""
LAB007 EXECUTION — one shot, per sealed pre-registration.

Runs N0 + 4 candidates (A, B, C, D) at 3 cost levels × 2 cash-return assumptions.
Reports discovery / confirmation / full-period metrics + regime attribution + gate verdicts.

DO NOT tune parameters. DO NOT add candidates. DO NOT re-run with different settings after
seeing outcomes. Any deviation invalidates the pre-registration.

Run: python india/ai_lab/LAB007_Dynamic_Exposure/run_lab007.py
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
from india.ai_lab.LAB006_Exit_Strategy.exit_lab import read_trial_manifest_count, pbo_across_configs
from india.ai_lab.LAB007_Dynamic_Exposure.exposure_lab import (
    CANDIDATES, simulate_lab007, metric_suite, period_metrics, sharpe_rank_stability,
)

CAPITAL = 100_000
COST_GRID = [15, 30, 50]
CASH_GRID = [0.0, 0.06]                # 0% and 6% annualized — dual primary
DISC_END = pd.Timestamp("2023-10-13")
CONF_START = pd.Timestamp("2024-01-15")

REPORTS = Path(__file__).parent / "reports"
REPORTS.mkdir(exist_ok=True)


def _split(cycles_meta):
    disc = {pd.Timestamp(m["asof"]) for m in cycles_meta if pd.Timestamp(m["asof"]) <= DISC_END}
    conf = {pd.Timestamp(m["asof"]) for m in cycles_meta if pd.Timestamp(m["asof"]) >= CONF_START}
    return disc, conf


def _regime_slice(cycles_meta, regime):
    return {pd.Timestamp(m["asof"]) for m in cycles_meta if m.get("regime") == regime}


def main():
    print("=" * 70)
    print("  LAB007 EXECUTION — per sealed 2026-07-13 pre-registration")
    print("=" * 70)
    n_trials = read_trial_manifest_count()
    print(f"  Trial manifest -> n_trials = {n_trials}")
    print(f"  Loading registry + price panel...")
    reg = pd.read_csv(ROOT / "data" / "aegis_registry.csv")
    closes, *_ = load_panels()

    # Precompute exposure series once (PIT-safe, deterministic)
    exp_series_by_name = {name: fn() for name, (_, fn) in CANDIDATES.items()}

    # Full result store: [cash][cost][name] -> (equity, meta, metrics_full, metrics_disc, metrics_conf, dsr, regime_metrics)
    all_results = {}
    for cash in CASH_GRID:
        all_results[cash] = {}
        for cost in COST_GRID:
            all_results[cash][cost] = {}
            print(f"\n  --- cash={100*cash:.0f}% cost={cost}bps ---")
            for name, (_, _) in CANDIDATES.items():
                eq, meta = simulate_lab007(exp_series_by_name[name], reg, closes,
                                           initial_capital=CAPITAL, cash_return_annual=cash,
                                           cost_bps=cost)
                full = metric_suite(eq, meta)
                disc_asofs, conf_asofs = _split(meta)
                disc = period_metrics(eq, meta, disc_asofs)
                conf = period_metrics(eq, meta, conf_asofs)
                # regime attribution (full period)
                reg_metrics = {r: period_metrics(eq, meta, _regime_slice(meta, r))
                               for r in ("Strong", "Neutral", "Weak")}
                dsr_d = deflated_sharpe(eq.pct_change().dropna(), n_trials=n_trials)
                all_results[cash][cost][name] = {
                    "equity": eq, "meta": meta,
                    "full": full, "disc": disc, "conf": conf,
                    "regime": reg_metrics,
                    "dsr": dsr_d,
                }
                print(f"    {name:>3}: CAGR {full['cagr']*100:+5.2f}%  Sharpe {full['sharpe']:4.2f}  "
                      f"MaxDD {full['max_dd']*100:+5.1f}%  Ulcer {full['ulcer']:4.1f}  "
                      f"avgExp {full['avg_exp']:.2f}  DSR {dsr_d['dsr']:.2f}")

    # PBO across N0 + 4 candidates at canonical 15bps, cash=0% (choose one anchor for CSCV)
    pbo_by_cash = {}
    for cash in CASH_GRID:
        eq_by_name = {name: all_results[cash][15][name]["equity"] for name in CANDIDATES}
        common_idx = None
        for eq in eq_by_name.values():
            common_idx = eq.index if common_idx is None else common_idx.intersection(eq.index)
        if common_idx is not None and len(common_idx) >= 30:
            R = pd.DataFrame({name: eq.reindex(common_idx).pct_change()
                              for name, eq in eq_by_name.items()}).dropna(how="any")
            try:
                pbo_val = pbo_across_configs(R, S=8)
                pbo_by_cash[cash] = ("computed", pbo_val,
                                    f"N=5 configs, S=8 folds. Cash={100*cash:.0f}%.")
            except ValueError as e:
                pbo_by_cash[cash] = ("N/A", np.nan, f"CSCV infeasible: {e}")
        else:
            pbo_by_cash[cash] = ("N/A", np.nan, "Insufficient common index")

    # Sharpe rank stability across folds (informational when PBO is uninterpretable at low N)
    stab_by_cash = {}
    for cash in CASH_GRID:
        eq_by_name = {name: all_results[cash][15][name]["equity"] for name in CANDIDATES}
        ranks_df, top2 = sharpe_rank_stability(eq_by_name, n_folds=4)
        stab_by_cash[cash] = (ranks_df, top2)

    # Gate verdicts (evaluated per candidate; must pass under BOTH cash assumptions)
    verdicts = _evaluate_gates(all_results)

    # Write report
    _write_report(all_results, verdicts, pbo_by_cash, stab_by_cash, n_trials)

    # Print gate-verdict summary
    print("\n" + "=" * 70)
    print("  GATE VERDICTS (must PASS under BOTH cash assumptions)")
    print("=" * 70)
    for name in ("A", "B", "C", "D"):
        v = verdicts[name]
        overall = all(v[cash]["all_pass"] for cash in CASH_GRID)
        # ASCII-only console output (Windows cp1252 can't encode emoji)
        print(f"  {name}: {'PROMOTE-ELIGIBLE' if overall else 'REJECT'}")
        for cash in CASH_GRID:
            g = v[cash]
            print(f"    cash={100*cash:.0f}%: " + " ".join(f"G{i}{'PASS' if g[f'gate_{i}'] else 'FAIL'}" for i in range(1, 7)))


def _pp(a, b):
    """Percentage-point improvement (a - b) where negatives are DD-style (a > b = better)."""
    return (a - b) * 100 if (a == a and b == b) else float("nan")


def _evaluate_gates(all_results):
    """Per candidate × cash assumption, evaluate the 6 sealed promotion gates."""
    verdicts = {}
    for name in ("A", "B", "C", "D"):
        verdicts[name] = {}
        for cash in CASH_GRID:
            n0 = all_results[cash][15]["N0"]
            cand = all_results[cash][15][name]
            n0_50 = all_results[cash][50]["N0"]
            cand_50 = all_results[cash][50][name]

            # Gate 1: Confirmation Ulcer improvement >= 1.0 point
            ulcer_improve = n0["conf"]["ulcer"] - cand["conf"]["ulcer"]
            g1 = ulcer_improve >= 1.0

            # Gate 2: Confirmation MaxDD improvement >= 3pp OR CVaR improvement >= 0.5pp
            dd_improve_pp = _pp(cand["conf"]["max_dd"], n0["conf"]["max_dd"])
            cvar_improve_pp = _pp(cand["conf"]["cvar5"], n0["conf"]["cvar5"])
            g2 = (dd_improve_pp >= 3.0) or (cvar_improve_pp >= 0.5)

            # Gate 3: Full-period CAGR sacrifice <= 2pp
            cagr_delta_pp = _pp(cand["full"]["cagr"], n0["full"]["cagr"])
            g3 = cagr_delta_pp >= -2.0

            # Gate 4: DSR > 0.90
            g4 = cand["dsr"]["dsr"] > 0.90

            # Gate 5: At 50bps, gates 1-3 still hold
            ulcer_improve_50 = n0_50["conf"]["ulcer"] - cand_50["conf"]["ulcer"]
            dd_improve_pp_50 = _pp(cand_50["conf"]["max_dd"], n0_50["conf"]["max_dd"])
            cvar_improve_pp_50 = _pp(cand_50["conf"]["cvar5"], n0_50["conf"]["cvar5"])
            cagr_delta_pp_50 = _pp(cand_50["full"]["cagr"], n0_50["full"]["cagr"])
            g5 = (ulcer_improve_50 >= 1.0) and (
                (dd_improve_pp_50 >= 3.0) or (cvar_improve_pp_50 >= 0.5)
            ) and (cagr_delta_pp_50 >= -2.0)

            # Gate 6: Primary risk improvement attributable to Weak-regime cycles
            weak_ulcer_improve = n0["regime"]["Weak"]["ulcer"] - cand["regime"]["Weak"]["ulcer"] \
                if n0["regime"]["Weak"]["ulcer"] == n0["regime"]["Weak"]["ulcer"] else 0
            strong_ulcer_improve = n0["regime"]["Strong"]["ulcer"] - cand["regime"]["Strong"]["ulcer"] \
                if n0["regime"]["Strong"]["ulcer"] == n0["regime"]["Strong"]["ulcer"] else 0
            g6 = weak_ulcer_improve > strong_ulcer_improve

            verdicts[name][cash] = {
                "gate_1": bool(g1), "gate_1_val": ulcer_improve,
                "gate_2": bool(g2), "gate_2_dd_pp": dd_improve_pp, "gate_2_cvar_pp": cvar_improve_pp,
                "gate_3": bool(g3), "gate_3_val": cagr_delta_pp,
                "gate_4": bool(g4), "gate_4_val": cand["dsr"]["dsr"],
                "gate_5": bool(g5),
                "gate_6": bool(g6), "gate_6_weak": weak_ulcer_improve, "gate_6_strong": strong_ulcer_improve,
                "all_pass": bool(g1 and g2 and g3 and g4 and g5 and g6),
            }
    return verdicts


def _fmt(x, kind="num"):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    if kind == "pct":  return f"{x*100:+.1f}%"
    if kind == "pctabs": return f"{x*100:.1f}%"
    if kind == "num": return f"{x:+.2f}"
    if kind == "raw": return f"{x:.2f}"
    return str(x)


def _write_report(all_results, verdicts, pbo_by_cash, stab_by_cash, n_trials):
    now = datetime.now().date().isoformat()
    lines = [f"# LAB007 Dynamic Exposure — Results Report {now}", "",
             f"_Generated {datetime.now().isoformat(timespec='seconds')}_", "",
             "Sealed pre-registration: `preregistration.md` (2026-07-13). No parameter tuning post-run.", "",
             f"**n_trials from central manifest: {n_trials}** · Cash return: **0% AND 6% annualized (dual primary)** · "
             f"Costs: 15/30/50 bps · Cycles: 10 discovery / 9 confirmation.", ""]

    # Executive summary
    lines.append("## Executive summary")
    lines.append("")
    lines.append("| Candidate | Overall verdict | Cash=0% gates | Cash=6% gates |")
    lines.append("|---|---|---|---|")
    for name in ("A", "B", "C", "D"):
        v = verdicts[name]
        overall = "✅ PROMOTE-ELIGIBLE" if all(v[c]["all_pass"] for c in CASH_GRID) else "❌ REJECT"
        c0 = "".join(("1" if v[0.0][f"gate_{i}"] else "0") for i in range(1, 7))
        c6 = "".join(("1" if v[0.06][f"gate_{i}"] else "0") for i in range(1, 7))
        lines.append(f"| {name} | {overall} | {c0} | {c6} |")
    lines.append("")
    lines.append("(6-digit gate string reads G1..G6 left-to-right; 1=pass, 0=fail. All must be 1 under BOTH cash rows.)")
    lines.append("")

    # Per candidate detail
    for name in ("N0", "A", "B", "C", "D"):
        title = CANDIDATES[name][0]
        lines.append(f"## {name} — {title}")
        lines.append("")
        for cash in CASH_GRID:
            lines.append(f"### Cash return = {100*cash:.0f}% annualized")
            lines.append("")
            r = all_results[cash][15][name]
            lines.append(f"**15 bps** · Full: CAGR {_fmt(r['full']['cagr'],'pct')} · "
                         f"Sharpe {_fmt(r['full']['sharpe'],'raw')} · MaxDD {_fmt(r['full']['max_dd'],'pct')} · "
                         f"Ulcer {_fmt(r['full']['ulcer'],'raw')} · CVaR(5%) {_fmt(r['full']['cvar5'],'pct')} · "
                         f"DSR {_fmt(r['dsr']['dsr'],'raw')}")
            lines.append("")
            lines.append("| Period | CAGR | Sharpe | Sortino | MaxDD | CVaR(5%) | Ulcer | avg exp | min exp |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for pname, pd_ in (("Discovery", r["disc"]), ("Confirmation", r["conf"]), ("Full", r["full"])):
                lines.append(f"| {pname} | {_fmt(pd_['cagr'],'pct')} | {_fmt(pd_['sharpe'],'raw')} | "
                             f"{_fmt(pd_['sortino'],'raw')} | {_fmt(pd_['max_dd'],'pct')} | "
                             f"{_fmt(pd_['cvar5'],'pct')} | {_fmt(pd_['ulcer'],'raw')} | "
                             f"{_fmt(pd_.get('avg_exp'),'raw')} | {_fmt(pd_.get('min_exp'),'raw')} |")
            lines.append("")
            lines.append("Regime attribution (full period):")
            lines.append("| Regime | # cycles | CAGR | MaxDD | Ulcer |")
            lines.append("|---|---|---|---|---|")
            for reg_name in ("Strong", "Neutral", "Weak"):
                rm = r["regime"][reg_name]
                n = sum(1 for m in r["meta"] if m.get("regime") == reg_name)
                lines.append(f"| {reg_name} | {n} | {_fmt(rm['cagr'],'pct')} | {_fmt(rm['max_dd'],'pct')} | {_fmt(rm['ulcer'],'raw')} |")
            lines.append("")
            # Cost sensitivity for THIS candidate
            lines.append("Cost sensitivity (same policy, different friction — NOT PBO input):")
            lines.append("| Cost | CAGR | Sharpe | MaxDD | Ulcer | avg exp |")
            lines.append("|---|---|---|---|---|---|")
            for cost in COST_GRID:
                r2 = all_results[cash][cost][name]
                lines.append(f"| {cost} bps | {_fmt(r2['full']['cagr'],'pct')} | {_fmt(r2['full']['sharpe'],'raw')} | "
                             f"{_fmt(r2['full']['max_dd'],'pct')} | {_fmt(r2['full']['ulcer'],'raw')} | "
                             f"{_fmt(r2['full']['avg_exp'],'raw')} |")
            lines.append("")

    # Gate verdicts per candidate
    lines.append("## Gate verdicts (locked pre-registration)")
    lines.append("")
    for name in ("A", "B", "C", "D"):
        lines.append(f"### {name}")
        for cash in CASH_GRID:
            g = verdicts[name][cash]
            lines.append(f"**Cash={100*cash:.0f}%**")
            lines.append(f"- Gate 1 (Confirmation Ulcer improvement ≥ 1.0): "
                         f"{'✅' if g['gate_1'] else '❌'} actual={g['gate_1_val']:+.2f}")
            lines.append(f"- Gate 2 (Confirmation MaxDD ≥ 3pp OR CVaR ≥ 0.5pp): "
                         f"{'✅' if g['gate_2'] else '❌'} DD={g['gate_2_dd_pp']:+.1f}pp · CVaR={g['gate_2_cvar_pp']:+.2f}pp")
            lines.append(f"- Gate 3 (Full-period CAGR sacrifice ≤ 2pp): "
                         f"{'✅' if g['gate_3'] else '❌'} actual={g['gate_3_val']:+.1f}pp")
            lines.append(f"- Gate 4 (DSR > 0.90 at n_trials={n_trials}): "
                         f"{'✅' if g['gate_4'] else '❌'} actual={g['gate_4_val']:.3f}")
            lines.append(f"- Gate 5 (Gates 1-3 hold at 50 bps): "
                         f"{'✅' if g['gate_5'] else '❌'}")
            lines.append(f"- Gate 6 (Weak-regime Ulcer improvement > Strong-regime): "
                         f"{'✅' if g['gate_6'] else '❌'} Weak={g['gate_6_weak']:+.2f} · Strong={g['gate_6_strong']:+.2f}")
            lines.append(f"- **ALL 6: {'✅ PASS' if g['all_pass'] else '❌ FAIL'}**")
            lines.append("")

    # PBO + Sharpe rank stability
    lines.append("## PBO + Fold Sharpe rank stability")
    lines.append("")
    for cash in CASH_GRID:
        status, pbo_val, note = pbo_by_cash[cash]
        lines.append(f"**Cash={100*cash:.0f}%** · PBO status: **{status}** · " +
                     (f"value = {pbo_val:.3f} · " if status == "computed" else "") + note)
        lines.append("")
        ranks_df, top2 = stab_by_cash[cash]
        if not ranks_df.empty:
            lines.append("Per-fold Sharpe rank (1 = best in fold):")
            lines.append("| Fold | " + " | ".join(ranks_df.columns) + " |")
            lines.append("|" + "|".join(["---"] * (1 + len(ranks_df.columns))) + "|")
            for fold, row in ranks_df.iterrows():
                lines.append(f"| {fold} | " + " | ".join(str(int(v)) for v in row) + " |")
            lines.append("")
            lines.append("Fraction of folds ranked in top-2:")
            lines.append("| " + " | ".join(top2.keys()) + " |")
            lines.append("|" + "|".join(["---"] * len(top2)) + "|")
            lines.append("| " + " | ".join(f"{100*v:.0f}%" for v in top2.values()) + " |")
            lines.append("")

    # Final verdict
    lines.append("## Final LAB007 verdict")
    lines.append("")
    any_promoted = any(all(verdicts[n][c]["all_pass"] for c in CASH_GRID) for n in ("A", "B", "C", "D"))
    if any_promoted:
        promoted = [n for n in ("A", "B", "C", "D") if all(verdicts[n][c]["all_pass"] for c in CASH_GRID)]
        lines.append(f"**PROMOTE-ELIGIBLE (subject to operator approval)**: {', '.join(promoted)}")
    else:
        lines.append("**REJECT — no candidate clears all 6 gates under BOTH cash-return assumptions.**")
        lines.append("")
        lines.append("Current production dynamic exposure policy remains frozen.")
    lines.append("")
    lines.append(f"Cumulative Lab-wide n_trials: {n_trials}. LAB007 outcomes recorded in `trial_manifest.md`.")

    out = REPORTS / f"lab007_{now}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  report -> {out}")

    # Diagnostics CSV — one row per (cash, cost, candidate) with full metrics + gates
    diag_rows = []
    for cash in CASH_GRID:
        for cost in COST_GRID:
            for name in CANDIDATES:
                r = all_results[cash][cost][name]
                row = {"cash_annual": cash, "cost_bps": cost, "candidate": name,
                       "cagr_full": r["full"]["cagr"], "sharpe_full": r["full"]["sharpe"],
                       "max_dd_full": r["full"]["max_dd"], "ulcer_full": r["full"]["ulcer"],
                       "cvar5_full": r["full"]["cvar5"], "avg_exp": r["full"]["avg_exp"],
                       "cagr_disc": r["disc"]["cagr"], "max_dd_disc": r["disc"]["max_dd"],
                       "ulcer_disc": r["disc"]["ulcer"],
                       "cagr_conf": r["conf"]["cagr"], "max_dd_conf": r["conf"]["max_dd"],
                       "ulcer_conf": r["conf"]["ulcer"], "cvar5_conf": r["conf"]["cvar5"],
                       "dsr": r["dsr"]["dsr"],
                       "weak_cagr": r["regime"]["Weak"]["cagr"], "weak_dd": r["regime"]["Weak"]["max_dd"],
                       "weak_ulcer": r["regime"]["Weak"]["ulcer"],
                       }
                diag_rows.append(row)
    pd.DataFrame(diag_rows).to_csv(REPORTS / f"lab007_diagnostics_{now}.csv", index=False)


if __name__ == "__main__":
    main()
