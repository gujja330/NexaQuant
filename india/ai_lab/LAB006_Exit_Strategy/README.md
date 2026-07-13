# LAB006 — Exit Strategy

**Status:** Active · **Owner:** Operator + Assistant · **Opened:** 2026-07-13

## Purpose

Evidence-test whether an EARLY-EXIT overlay (running between the frozen 63-day rebalance cycles)
produces better portfolio utility than the baseline "hold to next rebalance". Outputs are pure
research — Core (arjuna_v2 + confidence_engine + selection rule) remains frozen per
`docs/ARJUNA_OPERATING.md`. A rule graduates from Lab → Telegram-as-signal only if it clears the
promotion gate below AND the operator approves.

## Hypotheses

Four independent rules, each testing a distinct failure mode. Test independently — a null result
on one does NOT stop the others.

| Rule | Signal | Failure mode tested | Backtestable now? |
|---|---|---|---|
| **A** Score-drop | Held stock's daily score crosses below 45 | Model conviction deterioration | ❌ No PIT score history — start forward collection today |
| **B** Vol-spike | 20d realized vol ≥ 1.6× the trailing 60d baseline | Volatility regime break for a name | ✅ Backtest 2021-2026 |
| **C** Trailing stop | Post-entry drawdown ≥ X% (grid: 5/8/10/12) | Price-path risk control | ✅ Backtest 2021-2026 |
| **D** Sentiment | news_sentiment score below threshold for 3+ consecutive days | Information / event deterioration | ⚠️ Depends on news archive; audit before build |

## Baseline

- Hold each pick from `asof` to `mature_date` (63 calendar days ~ 42 trading days).
- Weights = whatever the frozen engine assigned at `asof`.
- No intra-cycle intervention.
- Registry source: `data/aegis_registry.csv`, `source == "historical"`, `scored == 1`.

## Full portfolio lifecycle (what every experiment must model)

Exit rules cannot be tested in isolation — capital state after an exit determines the real result.
Every experiment MUST simulate all three re-entry policies and report each separately:

| Policy | After exit, capital... |
|---|---|
| **P1 Cash-until-rebalance** | Sits in cash (0 return) until the cycle's next rebalance date. Baseline for "did the exit save capital?" |
| **P2 Rotate-to-next-ranked** | Immediately enters the next-ranked candidate from the same cycle. Tests "was the exited capital better deployed elsewhere?" |
| **P3 Cooldown-then-reenter** | Cash for 20 trading days; if the exit signal has cleared, re-enter the same name at the current price. Tests false-exit resilience. |

## Multi-metric evaluation — NO single hardcoded gate

Per the operator: an exit overlay is a RISK CONTROL. A rule that trades 1% CAGR for -11pp MaxDD
may absolutely be worth promoting. Report ALL of these; the operator makes the promotion call:

| Metric | Direction |
|---|---|
| CAGR | higher better |
| Sharpe | higher better |
| Sortino | higher better |
| MaxDD | less-negative better |
| CVaR (5%) | less-negative better |
| Ulcer Index | lower better |
| Recovery time (days) | lower better |
| Turnover | lower better |
| Cost drag (bps assumed) | lower better |
| False-exit rate | lower better (exited stock that then recovered ≥5% within cycle) |
| Opportunity cost | lower better (foregone return from cash if P1) |
| PBO | < 0.10 required |
| DSR | > 0.90 required |

## Promotion gate (soft — evidence + judgment)

Baseline threshold: rule must clear **PBO < 0.10 and DSR > 0.90** on the full backtest AND at
least one non-return metric (MaxDD, CVaR, Ulcer, recovery) shows material improvement across
purged walk-forward folds. Operator approves per-rule. Do NOT auto-promote.

## Files

- `exit_lab.py` — common utilities: metric suite, re-entry simulators, portfolio walker
- `rule_B_vol_spike.py` — Rule B implementation + backtest driver
- `score_path_collector.py` — forward collector for Rule A (writes daily to
  `data/aegis_score_paths.csv` — starts today, review in 6 months)
- `reports/` — dated markdown + CSV output per experiment

## Log

- **2026-07-13** — Lab opened. Audit complete: Rule A deferred (no PIT history). Rule B (vol-spike) REJECTED on economic evidence (MaxDD unchanged, CAGR loss at every k). PBO evidence retracted after audit found N=2 CSCV setup was degenerate. See `reports/rule_B_findings_2026-07-13.md`.
- **2026-07-13** — Rule C (trailing stop) provisional run flagged 5 scaffold bugs: per-exit false-exit denominator, PIT-safe P3, full-matrix PBO, DSR n_trials from manifest, P2 concentration excluded from promotion. See `reports/rule_C_trailing_stop_2026-07-13.md` (marked PROVISIONAL).
- **2026-07-13** — Scaffold fixed. Rule C **audit-closure rerun**: **P3 PIT fix deflated 5% P3 materially** (Sharpe 1.83 → 1.22, MaxDD -9.7% → -12.7%). Full-matrix PBO across 12 configs = 0.229 (fails <0.10). No Rule C config passes DSR > 0.90. See `reports/rule_C_audit_closure_2026-07-13.md`.
- **2026-07-13** — Rule C1 (regime-gated 5% P3 Weak-only) pre-registered + amended (PBO=N/A for single-strategy; discovery/confirmation/full-period terminology). Executed once. **REJECTED — 2 of 6 gates pass**. Mechanism DOES work in Weak cycles (MaxDD -11.8% → -5.6%, +6.2pp) BUT CAGR halves in Weak cycles too (+19.8% → +9.7%), 2022 "discovery" period showed CAGR HALVED with no MaxDD gain — meaning the original 2022 observation was largely a P3-leak artifact. See `reports/rule_C1_regime_gated_2026-07-13.md`.
- **2026-07-13** — Rule D scoping: NOT historically backtestable. `news_sentiment.py` docstring
  explicitly labels it a "LIVE/forward experiment: cannot be backtested." Archive has 3 weeks of
  data. Forward-collect only. Same category as Rule A.
- **2026-07-13** — **LAB006 status: no exit rule promoted.** Rule B rejected on economics.
  Rules C/C1 rejected on gates. Rules A/D require forward-collection. Cosmetic exit labels in
  `india/exit_reasons.py` remain the operator-facing exit signal — clearly labelled as post-hoc
  explanations, NOT evidence-backed advice. The frozen strategy's own regime-based exposure
  adjustment appears to already handle exit-management sufficiently for the low-vol universe it
  selects. Revisit A/D in Q1 2027 with 6+ months of forward data.
