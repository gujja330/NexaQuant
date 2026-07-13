# india/ai_lab/LAB006_Exit_Strategy/exit_lab.py
"""
LAB006 SCAFFOLD — common utilities every exit-rule experiment shares.

Provides:
  * metric_suite()          — CAGR, Sharpe, Sortino, MaxDD, CVaR, Ulcer, recovery, turnover, false-exit
  * simulate_cycle()        — per-cycle portfolio walk given a rule + re-entry policy
  * three re-entry policies — P1 cash-until-rebalance, P2 rotate-to-next, P3 cooldown-then-reenter
  * write_report()          — markdown summary table + per-cycle CSV

Uses india.validation for DSR/PBO/purged_walkforward (already vetted by prior labs).

Everything is REGISTRY-DRIVEN — we replay the frozen strategy's real historical picks (source=='historical',
scored==1) and only overlay the exit rule. No selection re-optimization; that would break the freeze.
"""
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
REPORTS = Path(__file__).parent / "reports"
REPORTS.mkdir(exist_ok=True)


# ------------------------------- METRICS -----------------------------------

def _daily_from_curve(equity):
    """Convert an equity curve to daily returns (pct_change)."""
    return equity.pct_change().dropna()


def metric_suite(equity, cycles_meta=None, trading_days=252):
    """Compute the full metric suite for one strategy (rule OR baseline).
    equity: pd.Series indexed by date, values = portfolio value.
    cycles_meta: optional list of per-cycle dicts. Each may include:
        - 'exited' (bool) — did the rule fire at least once in this cycle?
        - 'n_exits' (int) — number of triggered exits in this cycle
        - 'n_false_exits' (int) — number of those exits that recovered >= 5% post-exit within cycle
        - 'opportunity_pct' (float) — average missed-return-if-held for triggered exits this cycle
    Metrics that count exits use TOTAL exits across all cycles (per-exit denominator), NOT
    the cycle-level flag. Cycle-level flags are reported separately if present."""
    r = _daily_from_curve(equity)
    if len(r) < 30:
        return {k: np.nan for k in ("cagr", "sharpe", "sortino", "max_dd", "cvar5", "ulcer",
                                    "recovery_days", "turnover", "false_exit_rate", "opportunity_cost")}

    T = len(r); years = T / trading_days
    total_ret = float(equity.iloc[-1] / equity.iloc[0] - 1)
    cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0.0

    sr_daily = r.mean() / (r.std(ddof=1) + 1e-12)
    sharpe = sr_daily * np.sqrt(trading_days)

    downside = r[r < 0]
    sortino = (r.mean() / (downside.std(ddof=1) + 1e-12) * np.sqrt(trading_days)) if len(downside) else np.nan

    peak = equity.cummax()
    dd = (equity / peak - 1)
    max_dd = float(dd.min())

    var5 = float(np.percentile(r, 5))
    cvar5 = float(r[r <= var5].mean()) if (r <= var5).any() else var5

    # Ulcer Index — RMS of drawdowns
    ulcer = float(np.sqrt(((dd ** 2)).mean()) * 100)

    # Recovery time from max DD (days from trough back to prior peak)
    trough_idx = dd.idxmin()
    after = equity.loc[trough_idx:]
    peak_val = peak.loc[trough_idx]
    recovered = after[after >= peak_val]
    recovery_days = int((recovered.index[0] - trough_idx).days) if len(recovered) else np.nan

    # Turnover + false-exit + opportunity cost from cycles metadata.
    # NOTE: false_exit_rate is PER-EXIT (denominator = total triggered exits across all cycles),
    # NOT per-cycle. The per-cycle variant is reported as `cycles_with_any_exit` separately.
    turnover_cycles = np.nan
    total_exits = np.nan
    false_exit_rate = np.nan
    opportunity_cost = np.nan
    cycles_with_any_exit = np.nan
    if cycles_meta:
        cm = pd.DataFrame(cycles_meta)
        if "exited" in cm and len(cm):
            cycles_with_any_exit = float(cm["exited"].mean())
        if "n_exits" in cm:
            total_exits = int(cm["n_exits"].sum())
            # per-exit turnover: average exits per cycle divided by picks per cycle (~15)
            turnover_cycles = float(cm["n_exits"].sum() / max(len(cm), 1))
        if "n_exits" in cm and "n_false_exits" in cm:
            denom = int(cm["n_exits"].sum())
            if denom > 0:
                false_exit_rate = float(cm["n_false_exits"].sum() / denom)
        if "opportunity_pct" in cm:
            triggered = cm[cm["exited"] == True]
            if len(triggered):
                opportunity_cost = float(triggered["opportunity_pct"].mean())

    return {"cagr": cagr, "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd,
            "cvar5": cvar5, "ulcer": ulcer, "recovery_days": recovery_days,
            "turnover_cycles": turnover_cycles, "cycles_with_any_exit": cycles_with_any_exit,
            "total_exits": total_exits, "false_exit_rate": false_exit_rate,
            "opportunity_cost": opportunity_cost, "total_ret": total_ret, "years": years}


# ------------------------------- SIMULATOR -----------------------------------

def _stock_path(closes, sym, start, end):
    """Daily price series for one symbol between start and end (both inclusive if possible)."""
    if sym not in closes.columns:
        return pd.Series(dtype=float)
    s = closes[sym].dropna()
    return s.loc[start:end]


def simulate_cycle(cycle_rows, closes, rule_fn, reentry_policy, cost_bps=15,
                   pre_history_days=180, active_check_fn=None):
    """Simulate one 63-day cycle with the rule + a re-entry policy.

    cycle_rows: DataFrame of registry rows for ONE rec_id (all symbols picked that cycle).

    rule_fn: callable(sym, entry_price, path, pre_history) -> (triggered, day_idx, reason).
             Called ONCE at cycle start to find the first trigger point.
             `path` = daily prices asof..mature (inclusive) — the ONLY place forward info is used.
             `pre_history` = daily prices ending on asof (exclusive), pre_history_days long.

    active_check_fn: OPTIONAL callable(sym, entry_price, history_up_to_now, pre_history) -> bool.
             POINT-IN-TIME check: is the signal currently active AT the last bar of history_up_to_now?
             Used by P3 to decide whether the cooldown-end reentry may happen. history_up_to_now MUST
             NOT contain any bars after the query time. If None, P3 falls back to unconditional
             re-entry after cooldown (safe: no leak, but no signal-clearing guard either).

    reentry_policy: one of "P1" (cash), "P2" (rotate-to-next), "P3" (cooldown-then-reenter).
    cost_bps: per side trade cost applied on rule-triggered exits + P2/P3 re-entries.

    Returns: (equity_series, cycles_meta_row_dict)
    """
    asof = pd.Timestamp(cycle_rows["asof"].iloc[0])
    mature = pd.Timestamp(cycle_rows["mature_date"].iloc[0])
    picks = cycle_rows.set_index("symbol")
    weights = pd.to_numeric(picks["weight"], errors="coerce").fillna(0.0)
    weights = weights / weights.sum() if weights.sum() > 0 else weights

    # Full date span
    all_dates = closes.loc[asof:mature].index
    if len(all_dates) < 2:
        return pd.Series(dtype=float), {}

    port_value = pd.Series(1.0, index=all_dates)
    n_exits = 0; n_false_exits = 0; opp_pcts = []
    turnover_cost_total = 0.0

    per_symbol_paths = {}
    for sym, w in weights.items():
        if w <= 0:
            continue
        path = _stock_path(closes, sym, asof, mature)
        if len(path) < 2:
            continue
        entry_px = float(path.iloc[0])
        # pre-entry history for rules needing baseline stats
        pre = closes[sym].dropna().loc[:asof]
        pre = pre.iloc[:-1].tail(pre_history_days) if len(pre) > 1 else pre.iloc[:0]
        triggered, trigger_i, reason = rule_fn(sym, entry_px, path, pre)

        # normalized asset curve (1.0 at entry)
        norm = (path / entry_px)

        if not triggered or trigger_i is None or trigger_i <= 0:
            # ride the position all cycle
            per_symbol_paths[sym] = (w, norm, None, None, False)
            continue

        # Trigger fires — exit at trigger day price
        exit_day = norm.index[trigger_i]
        exit_val = float(norm.iloc[trigger_i])
        # what would this stock have returned if held to mature? (opportunity check)
        hold_to_mature = float(norm.iloc[-1])
        opp = 100 * (hold_to_mature - exit_val) / max(exit_val, 1e-9)   # positive = missed upside
        opp_pcts.append(opp)
        n_exits += 1
        # false-exit if the stock recovered >=5% within the SAME cycle after exit
        remaining = norm.loc[exit_day:]
        peak_after = float(remaining.max())
        if peak_after / exit_val - 1 >= 0.05:
            n_false_exits += 1

        # Build the position value with re-entry policy applied
        cost_ratio = 1.0 - (cost_bps / 10000.0)
        exit_realized = exit_val * cost_ratio             # apply cost on exit
        turnover_cost_total += cost_bps / 10000.0

        after = pd.Series(exit_realized, index=norm.loc[exit_day:].index)  # default = cash forever
        if reentry_policy == "P1":
            pass  # after already = flat cash
        elif reentry_policy == "P2":
            # rotate to the NEXT ranked candidate NOT already in the portfolio, from the current cycle.
            # In lieu of a full candidate scoring backtest, we approximate: use the highest-weight
            # OTHER pick in the cycle as the rotation target.
            others = [s for s in picks.index if s != sym and s in closes.columns]
            if others:
                # pick the next-highest-weight name
                cand = max(others, key=lambda s: float(picks.loc[s, "weight"]) if pd.notna(picks.loc[s, "weight"]) else 0)
                cand_path = _stock_path(closes, cand, exit_day, mature)
                if len(cand_path) >= 2:
                    cand_norm = cand_path / float(cand_path.iloc[0])
                    after = exit_realized * cand_norm * (1.0 - cost_bps / 10000.0)   # cost on re-entry
                    turnover_cost_total += cost_bps / 10000.0
        elif reentry_policy == "P3":
            # Cooldown 20 trading days then MAYBE re-enter, gated by a POINT-IN-TIME signal check.
            # PIT SAFETY: the active-check only sees prices up to and including cooldown_end.
            # It NEVER receives forward bars. If no active_check_fn was passed we fall back to
            # unconditional re-entry (a defensible baseline — no leak, but no signal guard).
            cooldown_end = norm.index[min(trigger_i + 20, len(norm) - 1)] if trigger_i + 20 < len(norm) else None
            if cooldown_end is not None:
                remaining_after_cool = norm.loc[cooldown_end:]
                if len(remaining_after_cool) >= 2:
                    signal_still_active = False
                    if active_check_fn is not None:
                        # Truncated history: prices from asof through cooldown_end ONLY.
                        history_up_to_cool = path.loc[:cooldown_end]
                        pre_at_cool = closes[sym].dropna().loc[:asof]
                        pre_at_cool = pre_at_cool.iloc[:-1].tail(pre_history_days) if len(pre_at_cool) > 1 else pre_at_cool.iloc[:0]
                        signal_still_active = bool(active_check_fn(sym, entry_px, history_up_to_cool, pre_at_cool))
                    if not signal_still_active:
                        # Signal cleared (or no active_check_fn provided) → re-enter at cooldown_end price
                        re_norm = remaining_after_cool / float(remaining_after_cool.iloc[0])
                        reentry = exit_realized * re_norm * (1.0 - cost_bps / 10000.0)
                        turnover_cost_total += cost_bps / 10000.0
                        cash_leg = pd.Series(exit_realized, index=norm.loc[exit_day:cooldown_end].index)
                        after = pd.concat([cash_leg[:-1], reentry])

        # combine: hold from asof to exit_day, then `after`
        held_leg = norm.loc[:exit_day]
        full = pd.concat([held_leg[:-1], after])
        full = full.reindex(norm.index, method="ffill")
        per_symbol_paths[sym] = (w, full, exit_day, exit_val, True)

    if not per_symbol_paths:
        return pd.Series(dtype=float), {}

    # portfolio value = sum(w_i * curve_i), rebased to 1.0 at asof
    combined = pd.DataFrame({sym: c for sym, (_, c, _, _, _) in per_symbol_paths.items()})
    ws = pd.Series({sym: w for sym, (w, _, _, _, _) in per_symbol_paths.items()})
    ws = ws / ws.sum()
    port = (combined * ws).sum(axis=1)

    meta = {
        "asof": asof, "mature": mature, "n_picks": len(picks),
        "n_exits": n_exits, "exited": bool(n_exits > 0),
        "n_false_exits": n_false_exits,     # per-exit count of >=5% post-exit recoveries this cycle
        "opportunity_pct": float(np.mean(opp_pcts)) if opp_pcts else 0.0,
        "turnover_cost": float(turnover_cost_total),
        "cycle_return_pct": float(100 * (port.iloc[-1] - 1)),
        "cycle_return_baseline_pct": float(100 * ((combined.iloc[-1] * ws).sum() - 1)),
    }
    return port, meta


# ------------------------------- BACKTEST DRIVER -----------------------------------

def run_backtest(rule_fn, rule_name, reentry_policy, reg_df, closes,
                 initial_capital=100000, cost_bps=15, active_check_fn=None,
                 cycle_filter=None):
    """Iterate historical cycles chronologically and compound the portfolio.

    active_check_fn: OPTIONAL point-in-time signal-active check, used by P3 re-entry.
                     See simulate_cycle for the required signature. If None, P3 defaults to
                     unconditional re-entry after cooldown (safe but no signal-clearing guard).
    cycle_filter:   OPTIONAL callable(cycle_asof) -> bool. If provided, ONLY cycles whose asof
                     passes the filter apply the rule; other cycles run baseline (no rule).
                     Used by Rule C1's regime gate: apply the rule only in Weak-regime cycles.
    """
    cycles = reg_df[(reg_df["source"] == "historical") & (reg_df["scored"] == 1)].sort_values("asof")
    if cycles.empty:
        raise RuntimeError("No historical cycles in registry — run recommendation_registry --backfill first.")

    equity = pd.Series(dtype=float)
    metas = []
    current_val = float(initial_capital)
    for rec_id, grp in cycles.groupby("rec_id", sort=False):
        cycle_asof = pd.Timestamp(grp["asof"].iloc[0])
        # Apply the rule only if this cycle passes the (optional) filter; otherwise run baseline
        active_rule = rule_fn if (cycle_filter is None or cycle_filter(cycle_asof)) else \
                     (lambda sym, e, p, pre: (False, None, "filter: rule inactive this cycle"))
        active_check = active_check_fn if active_rule is rule_fn else None
        curve, meta = simulate_cycle(grp, closes, active_rule, reentry_policy,
                                     cost_bps=cost_bps, active_check_fn=active_check)
        if curve.empty:
            continue
        scaled = curve * current_val
        # concat, dropping the first sample if it overlaps the previous cycle's last date
        if not equity.empty:
            scaled = scaled[scaled.index > equity.index[-1]]
        equity = pd.concat([equity, scaled])
        if not scaled.empty:
            current_val = float(scaled.iloc[-1])
        meta["rec_id"] = rec_id
        meta["policy"] = reentry_policy
        meta["rule"] = rule_name
        metas.append(meta)

    return equity.sort_index(), metas


def run_baseline(reg_df, closes, initial_capital=100000, cost_bps=15):
    """Baseline = hold every pick asof -> mature with no intra-cycle intervention."""
    def never_trigger(sym, entry_px, path, pre_history):
        return (False, None, "baseline: never exits")
    return run_backtest(never_trigger, "baseline", "P1", reg_df, closes,
                        initial_capital=initial_capital, cost_bps=cost_bps)


# --------------------------- ROBUSTNESS HELPERS ---------------------------

def read_trial_manifest_count(manifest_path=None):
    """Parse the Lab-wide manifest and return `cumulative_strategy_search`. Raises LookupError
    if the file is missing OR the label can't be parsed — NEVER falls back to a default.

    Silent fallback was a 2026-07-13 audit finding: the old default of 30 masked a label mismatch
    and reported n_trials=30 when actual was 28. Failing loud is correct here.

    Search order:
    1. Lab-wide central manifest: india/ai_lab/trial_manifest.md
    2. Legacy LAB006-local manifest (if central is missing)
    """
    import re
    # Default to the central Lab-wide manifest
    if manifest_path is None:
        manifest_path = Path(__file__).resolve().parents[1] / "trial_manifest.md"
    p = Path(manifest_path)
    if not p.exists():
        # Legacy fallback: LAB006-local manifest (kept for provenance of pre-2026-07-13 runs)
        legacy = Path(__file__).parent / "trial_manifest.md"
        if legacy.exists():
            p = legacy
        else:
            raise LookupError(f"Trial manifest not found at {manifest_path} or legacy {legacy}. "
                              f"Refusing to guess n_trials — update the manifest first.")
    text = p.read_text(encoding="utf-8")
    # PRIMARY: the standardized central-manifest label
    m = re.search(r"cumulative_strategy_search:\s*(\d+)", text)
    if m:
        return int(m.group(1))
    # LEGACY: LAB006 local manifest labels
    for pattern in (r"strategy_search_count \(as-of.*?\)[^0-9]*(\d+)",
                    r"strategy_search_count \(all-time\)[^0-9]*(\d+)",
                    r"strategy_search_count \(including .+?\)[^0-9]*(\d+)"):
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    raise LookupError(f"Could not parse n_trials from {p}. Add a "
                      f"'cumulative_strategy_search: N' line at the top of the manifest.")


def pbo_across_configs(config_returns_df, S=8):
    """PBO across a REAL multi-strategy candidate matrix.
    config_returns_df: T rows (dates or cycles) x N cols (distinct strategy configs, N >= 4).
    Raises if N < 4 — the metric is degenerate below that.
    Cost variants of the same strategy MUST NOT be columns here — they are the same strategy."""
    from india.validation import pbo as _pbo
    R = config_returns_df.dropna(how="any")
    if R.shape[1] < 4:
        raise ValueError(f"pbo_across_configs requires >=4 distinct strategy configs, got {R.shape[1]}. "
                         f"Cost-sensitivity variants of the same strategy do NOT count.")
    if len(R) < S:
        raise ValueError(f"pbo_across_configs: T={len(R)} < S={S} blocks — need more time observations.")
    return float(_pbo(R, S=S))


# ------------------------------- REPORT -----------------------------------

def _fmt(x, kind="num"):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    if kind == "pct":
        return f"{x*100:+.1f}%"
    if kind == "pctabs":
        return f"{x*100:.1f}%"
    if kind == "int":
        return f"{int(x)}"
    return f"{x:+.2f}"


def write_report(rule_name, baseline_metrics, rule_variants, out_path):
    """rule_variants: dict {policy_name: (metrics, dsr_dict, pbo, cycles_meta)}."""
    lines = [f"# LAB006 · Rule {rule_name} — Backtest Report",
             f"_Generated {datetime.now().isoformat(timespec='seconds')}_", "",
             "## Verdict",
             "**Read this table like a portfolio audit, not a horse race.** Return alone does not decide.",
             "Look for material improvement on MaxDD, CVaR, Ulcer, recovery time. Confirm PBO<0.10, DSR>0.90.",
             "The operator makes the promotion call.", "",
             "## Metric comparison", ""]

    # header
    hdr = ["Metric", "Baseline"] + [f"Rule {rule_name} · {p}" for p in rule_variants]
    lines.append("| " + " | ".join(hdr) + " |")
    lines.append("|" + "|".join(["---"] * len(hdr)) + "|")

    def row(label, key, kind="num"):
        vals = [baseline_metrics.get(key)] + [rule_variants[p][0].get(key) for p in rule_variants]
        lines.append("| " + " | ".join([label] + [_fmt(v, kind) for v in vals]) + " |")

    row("CAGR", "cagr", "pct")
    row("Total return", "total_ret", "pct")
    row("Sharpe", "sharpe")
    row("Sortino", "sortino")
    row("Max DD", "max_dd", "pct")
    row("CVaR (5%)", "cvar5", "pct")
    row("Ulcer Index", "ulcer", "pctabs")
    row("Recovery days", "recovery_days", "int")
    row("Turnover (frac cycles exited)", "turnover", "pctabs")
    row("False-exit rate", "false_exit_rate", "pctabs")
    row("Opportunity cost (avg %)", "opportunity_cost")

    lines.append("")
    lines.append("## Robustness (DSR / PBO)")
    lines.append("| Variant | DSR | PBO | Note |")
    lines.append("|---|---|---|---|")
    for p, (m, dsr_d, pbo_val, _) in rule_variants.items():
        note = "OK" if (dsr_d.get("dsr", 0) > 0.90 and pbo_val < 0.10) else "❌ fails gate"
        lines.append(f"| {p} | {dsr_d.get('dsr', float('nan')):.3f} | {pbo_val:.3f} | {note} |")

    lines.append("")
    lines.append("## Interpretation")
    lines.append("* P1 (cash-until-rebalance) — did the exit save capital vs holding?")
    lines.append("* P2 (rotate-to-next) — was capital better deployed elsewhere?")
    lines.append("* P3 (cooldown-then-reenter) — false-exit resilience.")
    lines.append("")
    lines.append("### Promotion decision")
    lines.append("Fill in after operator review:")
    lines.append("- [ ] Promote to Telegram-as-signal")
    lines.append("- [ ] Reject — evidence insufficient")
    lines.append("- [ ] Retest with tweaked parameter")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  report written -> {out_path}")
