# Rule C1 — Pre-registration

**Originally sealed 2026-07-13** · **Amended 2026-07-13 (same day, PRE-RUN)** with methodology
corrections logged below. Any post-run change would invalidate the pre-registration.

## Pre-run methodology correction log

| Date | Change | Reason |
|---|---|---|
| 2026-07-13 (amend v2, pre-run) | **PBO removed as C1 promotion gate.** Cost variants (15/30/50 bps) are the SAME strategy under different friction assumptions, not competing strategies. CSCV/PBO requires a genuine multi-strategy candidate matrix (Bailey-López de Prado). For a single frozen pre-registered strategy PBO is not identifiable. | Operator flagged that N=3-cost-variants is the same conceptual mistake as the earlier N=2 (rule vs baseline) PBO. |
| 2026-07-13 (amend v2, pre-run) | **Terminology fix**: replace "training" / "held-out" / "nested validation" with **discovery / confirmation / full-period**. | C1 has no fitted model — no learned parameters, no threshold selection, no fitting step. Calling anything "training" is misleading. 2022 inspired the hypothesis (discovery); everything else is confirmation. |
| 2026-07-13 (amend v2, pre-run) | **n_trials** for DSR reads from `trial_manifest.md`, not hardcoded. | Cumulative Lab-wide trial burden must reflect all strategy-search variants (Rule B configs + Rule C configs + C1). Cost sensitivity variants are labelled separately and NOT counted in strategy-search trials. |

Both amendments occurred BEFORE any C1 code was executed. They correct methodology, not results.

## Hypothesis (unchanged)

Trailing-stop protection at 5% is only useful when the market regime is Weak/Bear. Applying it
during Strong/Neutral regimes destroys CAGR without corresponding drawdown benefit. Regime-gated
activation preserves the DD/Ulcer improvement observed in Rule C 5% P3 while avoiding the CAGR
loss during risk-on periods.

**Origin**: 2022 bear-market period drove the DD improvement in provisional Rule C runs. That is
a hypothesis-generation observation, not proof. C1 tests whether the mechanism generalises.

## Locked parameters (unchanged)

| Parameter | Value | Rationale |
|---|---|---|
| Rule type | Trailing stop, close-to-close execution | Same as Rule C convention |
| Stop level | **5%** — SINGLE VALUE, no grid | Threshold-mining prevention |
| Re-entry policy | **P3 only** (cooldown 20d, PIT-safe active-check) | P1 loses too much CAGR; P2 has concentration bug |
| Regime gate | Rule ACTIVE only when `current_regime()` == "Weak" | Uses frozen `india/confidence_engine.py` — PIT-safe |
| Rebalance cycle | 63 days | Matches registry |
| Cost stress test | 15 / 30 / 50 bps as SEPARATE robustness check (NOT PBO configs) | Robustness to India trading friction; reported separately |

## Regime signal — PIT safety

`india/confidence_engine.current_regime()` reads only PRE-asof data (per the frozen strategy's
own PIT discipline). The regime label at cycle asof is what would have been known that day. No
future info leakage. **Verified**: `evidence/probability_matrix.regime_state_series()` returns a
series indexed by trading dates; we query at each cycle's asof (a rebalance date), never later.

## Metrics reported

CAGR · Sharpe · Sortino · MaxDD · CVaR(5%) · Ulcer · Recovery days · Turnover · **False-exit rate
(per-exit, corrected denominator)** · Missed-recovery avg · Regime-attribution (bull/bear/sideways
contribution to metrics).

## Three-period evaluation

- **Discovery period**: 2022 cycles (the period that inspired the hypothesis)
- **Confirmation sample**: 2021 + 2023-2026 cycles (all other historical cycles)
- **Full period**: 2021-2026 (descriptive; not the primary promotion evidence)

**Promotion evidence must come primarily from the confirmation sample.** The 2022 period is
reported for transparency but cannot substitute for out-of-discovery evidence.

## Robustness checks (frozen BEFORE running)

- **DSR** with `n_trials` read from `trial_manifest.md` (strategy-search trials only; cost variants excluded)
- **Fold stability**: Rule C1 performance across purged walk-forward folds (via `india.validation.purged_walkforward`)
- **Cost stress**: results reported at 15/30/50 bps SEPARATELY — same strategy, different friction. NOT a PBO input.
- **Regime attribution**: portfolio return decomposed into contributions from Strong/Neutral/Weak-regime cycles
- **PBO**: N/A for this single-strategy pre-registration. May be reported later if C1 is included in a legitimate broader candidate matrix (e.g., alongside future rules D/E/F).

## Promotion gate (frozen, amended)

Rule C1 promotes to Telegram-as-signal ONLY if ALL are true:
1. **DSR > 0.90** with n_trials from trial_manifest
2. **MaxDD improvement ≥ 5pp** vs baseline in the **confirmation sample** (not discovery, not full-period)
3. **MaxDD improvement ≥ 3pp** in full-period (sanity check that discovery didn't dominate)
4. **False-exit rate (per-exit) < 40%** in confirmation sample
5. **Cost robust**: MaxDD improvement in confirmation sample still holds at 50 bps
6. **Regime attribution sane**: Weak-regime cycles account for the DD improvement, not other regimes
7. Operator approves

Failing ANY of (1)–(6) → REJECT. Advisory promotion is not an option.

## What C1 will NOT do

- Not test other stop levels (that's C2, if ever)
- Not test other re-entry policies (P3 only)
- Not tune the regime signal
- Not adjust to look better after seeing partial results
- Not touch Core or Telegram
- Not compute standalone PBO for a single-strategy pre-registration

## Reproducibility

- Sealed: 2026-07-13 (amended same day, pre-run — see log above)
- Code file: `india/ai_lab/LAB006_Exit_Strategy/rule_C1_regime_gated.py` (to be written AFTER
  scaffold bugs are fixed)
- Reports: `reports/rule_C1_regime_gated_<date>.md`
- Diagnostics: `reports/rule_C1_diagnostics_<date>.csv`
- Trial manifest: `trial_manifest.md` (drives DSR n_trials)
