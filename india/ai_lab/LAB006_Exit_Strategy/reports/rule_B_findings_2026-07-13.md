# Rule B (vol-spike early exit) — Findings 2026-07-13

> **⚠ AMENDMENT 2026-07-13 (post-audit)** — The PBO numbers cited in this report (0.20–0.86)
> were computed using a degenerate 2-column CSCV setup (rule vs baseline only). Bailey-López de
> Prado CSCV requires a genuine multi-strategy candidate matrix (N ≥ ~10 configs). All PBO
> statements below are **RETRACTED as supporting evidence**.
>
> Rule B **REJECTION STANDS** on economic evidence alone:
> - MaxDD unchanged across all thresholds (best: -17.7% vs baseline -18.2%, a 0.5pp gain)
> - CAGR loss at every k (worst -7.3pp, best -0.9pp)
> - False-exit rate (per-exit, correctly computed): high across all thresholds
>
> These economic facts are sufficient. Do not cite the PBO column below.

## TL;DR — **REJECT.** Rule B does not clear the promotion gate at any tested threshold.

## Setup

- **Rule**: exit a held stock the first day its 20-day realized vol exceeds `k × baseline_vol`,
  where `baseline_vol` is the 60-day realized vol frozen at entry (no look-ahead).
- **Baseline**: hold each pick from `asof` → `mature_date` (63 days, matching registry).
- **Backtest window**: 19 quarterly cycles, 2021-07-01 → 2026-01-27, 285 scored historical picks.
- **Re-entry policies tested**: P1 (cash-until-rebalance), P2 (rotate-to-next), P3 (cooldown 20d).
- **Costs**: 15 bps per side on rule-triggered trips.
- **Parameter sweep**: k ∈ {1.6, 1.8, 2.0, 2.5, 3.0}, all 3 policies.

## Evidence table

| k    | Variant | CAGR    | Sharpe | MaxDD   | Ulcer | Turnover | DSR  | PBO  |
|:----:|:-------:|:-------:|:------:|:-------:|:-----:|:--------:|:----:|:----:|
| —    | Baseline| **+18.4%** | **1.40** | **-18.2%** | 6.0  | 0%       | —    | —    |
| 1.6  | P3      | +13.4%  | 1.23   | -18.2%  | **5.9** | 95%    | 0.95 | 0.40 |
| 1.8  | P3      | +15.7%  | 1.35   | -17.7%  | **5.4** | 79%    | 0.97 | 0.69 |
| 2.0  | P3      | +15.7%  | 1.33   | -18.2%  | 5.6   | 63%    | 0.97 | 0.57 |
| 2.5  | P3      | +17.3%  | 1.41   | -18.2%  | 5.8   | 53%    | 0.98 | 0.46 |
| 3.0  | P1      | +17.2%  | 1.39   | -18.2%  | 6.0   | 32%    | 0.97 | 0.23 |
| 3.0  | P2      | +17.5%  | 1.37   | -18.2%  | 6.2   | 32%    | 0.97 | 0.29 |

Bold = best value in column across all rows.

## What we learned — 3 findings

### 1. Rule B does NOT reduce MaxDD (the whole point of an exit overlay)
Baseline MaxDD -18.2% is essentially unchanged across every k and policy tested (best: -17.7%
at k=1.8 P3 — a 0.5pp improvement). This is the killer finding: vol-spike early exit does not
protect against the tail losses it was hypothesized to prevent.

**Why the hypothesis failed** — three plausible explanations (all defensible from the data):
- Vol spikes precede *recoveries* as often as they precede drawdowns (mean-reversion regime).
- The frozen 63-day rebalance already adjusts exposure when regime shifts, so intra-cycle
  vol-based exits are redundant with what Core already does.
- AEGIS deliberately picks LOW-VOL names — their vol spikes are, by construction, less predictive
  of downside than they would be for a high-vol universe.

### 2. Rule B costs meaningful CAGR at every k
Every variant underperforms baseline on CAGR. Best case: k=3.0 P2 loses 0.9pp (17.5% vs 18.4%).
Worst case: k=1.6 P1 loses 7.3pp (11.1% vs 18.4%). No trade improves total wealth.

### 3. PBO fails robustness at all tested thresholds
Even the best PBO (0.23 at k=3.0 P1) exceeds the 0.10 gate. The rule's Sharpe rank vs baseline
is unstable across folds — a strong signal of overfitting even before we broaden the search.
Grid-searching for a better k would only worsen this via multi-hypothesis inflation.

## Verdict against the promotion gate

- ❌ PBO < 0.10 — fails everywhere
- ❌ MaxDD improvement — negligible (0.5pp at best)
- ❌ CVaR / Ulcer material improvement — Ulcer improves 0.6pt at k=1.8 P3 but paired with -2.7pp CAGR loss (bad ratio)
- ❌ No k value produces a Pareto-improving portfolio

**Do NOT promote Rule B to Telegram-as-signal.** Cosmetic labelling in `india/exit_reasons.py`
stays as-is (post-hoc explanation of model-driven exits — clearly labelled).

## Recommendation — move to Rule C (trailing stop)

Rule C tests a different hypothesis: PATH-based drawdown control from post-entry high. That is
much closer to a proper risk overlay than vol-based signals, because it operates directly on the
metric we care about (drawdown), not a proxy (vol).

Rule C parameter grid to test: stop levels ∈ {5%, 8%, 10%, 12%} × 3 re-entry policies.
Est ~2 hours coding + backtest.

## Lab discipline note

This is exactly what evidence-based Lab work should produce — a clean rejection with a defensible
mechanism, before any of this ever reached Telegram or Core. The corrections you flagged
(re-entry testing, multi-metric evaluation, PBO gate) are what let us reject cleanly. If we'd
skipped straight to "trailing stop is common in trader lore, ship it" we'd have shipped noise.

## Data provenance
- Registry rows: 285 (source=historical, scored=1), 2021-07 → 2026-01, 19 cycles
- Price panel: `data/raw/india/*_D1.parquet` (yfinance-backed)
- Simulator: `india/ai_lab/LAB006_Exit_Strategy/exit_lab.py`
- Rule: `india/ai_lab/LAB006_Exit_Strategy/rule_B_vol_spike.py`
- Reproducible: `python india/ai_lab/LAB006_Exit_Strategy/rule_B_vol_spike.py --k <VALUE>`
