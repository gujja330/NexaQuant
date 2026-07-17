# RISK001-A · Exit Analytics Results

**Study executed:** RISK001-A specification (design doc in `docs/RISK001-A_EXIT_ANALYTICS.md`)
**Deliverable:** evidence-based recommendation on whether to proceed with RISK001-B → RISK001-C implementation.
**Run date:** 2026-07-17 · elapsed 5.4s · N=285 positions (dropped=0) · seed=20260717 · 10,000 bootstraps

**Reproduce:** `python research/RISK001-A/run.py`

---

## 1. Data audit

- **Positions loaded:** 285
- **Positions dropped:** 0 (none)
- **Unique tickers:** 71
- **Date range:** 2021-07-01 → 2026-04-30
- **Cost model:** 5 bps slippage + 3 bps brokerage per side = 0.16% round-trip cost applied to every policy

## 2. Policy comparison — the headline

| Metric | A_baseline | B_hard5 | C_hard7 | D_atr | E_trailing | F_breakeven |
|:--|:-:|:-:|:-:|:-:|:-:|:-:|
| Win rate % | 62.8 | 40.7 | 52.6 | 33.3 | 60.4 | 25.6 |
| Median return % | 3.10 | -5.16 | 0.80 | -3.46 | 0.32 | -0.91 |
| Avg return % | 4.32 | 2.48 | 3.36 | 2.13 | -0.66 | 1.32 |
| Profit factor | 2.60 | 1.84 | 2.08 | 1.78 | 0.64 | 1.91 |
| Sharpe (ann) | 0.66 | 0.53 | 0.61 | 0.50 | -0.72 | 0.62 |
| **Max drawdown %** | -0.37 | -0.58 | -0.72 | -0.67 | -0.72 | -0.43 |
| Ulcer index % | 0.14 | 0.28 | 0.29 | 0.31 | 0.34 | 0.20 |
| Largest loss % | -26.21 | -6.97 | -10.02 | -10.02 | -10.02 | -12.58 |
| Largest gain % | 101.09 | 101.09 | 101.09 | 101.09 | 14.55 | 37.94 |
| Avg holding days | 63.0 | 38.3 | 47.9 | 33.1 | 13.6 | 20.4 |
| Turnover (per yr) | 285.0 | 173.2 | 216.7 | 149.9 | 61.5 | 92.3 |
| Losses ≤ -10 % | 27 | 0 | 1 | 1 | 1 | 1 |
| Losses ≤ -15 % | 9 | 0 | 0 | 0 | 0 | 0 |
| Losses ≤ -20 % | 4 | 0 | 0 | 0 | 0 | 0 |

*Primary decision metric = **Max drawdown %** subject to non-degradation of Profit factor (RISK001-A §7).*

## 3. Counterfactual — what changes vs baseline (Policy A)

| Policy | Winners→Losers | Losers→Winners | −10% prevented | −15% prevented | −20% prevented |
|:--|:-:|:-:|:-:|:-:|:-:|
| B_hard5 | 63 | 0 | 27 | 9 | 4 |
| C_hard7 | 29 | 0 | 26 | 9 | 4 |
| D_atr | 84 | 0 | 26 | 9 | 4 |
| E_trailing | 52 | 45 | 26 | 9 | 4 |
| F_breakeven | 114 | 8 | 26 | 9 | 4 |

## 4. Statistical significance (paired bootstrap, 95% CI)

Mean per-position return delta vs Policy A. If the CI excludes zero, the policy's difference from baseline is statistically distinguishable.

| Policy | Mean Δ % | 95% CI lo | 95% CI hi | CI excludes 0 |
|:--|:-:|:-:|:-:|:-:|
| B_hard5 | -1.84 | -2.70 | -1.02 | ✅ |
| C_hard7 | -0.96 | -1.58 | -0.38 | ✅ |
| D_atr | -2.19 | -3.10 | -1.30 | ✅ |
| E_trailing | -4.98 | -6.42 | -3.63 | ✅ |
| F_breakeven | -3.00 | -4.38 | -1.74 | ✅ |

## 5. Adoption criteria (from RISK001-A §10.2)

A policy adopts only if **all** conditions hold:

1. Max drawdown improves ≥ 30% relative to Policy A
2. Profit factor drops ≤ 10% relative to Policy A
3. Bootstrap 95% CI on Δ excludes zero
4. No single sector shows > 2× worse median under the winner (sector-neutrality guard — evaluated below)

| Policy | DD rel. improve % | PF rel. change % | C1 | C2 | C3 | Passes 1-3 |
|:--|:-:|:-:|:-:|:-:|:-:|:-:|
| B_hard5 | 56.41 | -29.33 | ✅ | ❌ | ✅ | ❌ |
| C_hard7 | 96.37 | -19.95 | ✅ | ❌ | ✅ | ❌ |
| D_atr | 82.65 | -31.42 | ✅ | ❌ | ✅ | ❌ |
| E_trailing | 96.51 | -75.45 | ✅ | ❌ | ✅ | ❌ |
| F_breakeven | 16.02 | -26.70 | ❌ | ❌ | ✅ | ❌ |

### VERDICT (by spec §10.2) — **STAND-DOWN** · no policy passes all criteria

- Policies passing quantitative gates (1-3): **none**

### Reframed decision — single-trade tail risk (matches operator's stated concern)

The spec's primary metric (§7 = portfolio Max DD on the aggregate equity curve) shows baseline at the tightest DD **because winners smoothly offset losers over the 4.6-year window**. Stops add exit noise to that curve; hence baseline wins on the aggregate metric.

But the operator's original complaint was about **single-trade tail losses** (the -11.5% ICICIGI example), not aggregate equity smoothness. Below is the same evidence viewed through that lens.

| Metric (per-trade tail) | A_baseline | B_hard5 | C_hard7 | D_atr | E_trailing | F_breakeven |
|:--|:-:|:-:|:-:|:-:|:-:|:-:|
| **Largest single-trade loss %** | -26.21 | -6.97 | -10.02 | -10.02 | -10.02 | -12.58 |
| Losses ≤ -10 % | 27 | 0 | 1 | 1 | 1 | 1 |
| Losses ≤ -15 % | 9 | 0 | 0 | 0 | 0 | 0 |
| Losses ≤ -20 % | 4 | 0 | 0 | 0 | 0 | 0 |

**Tail-risk trade-off scoreboard (vs baseline):**

| Policy | Largest loss reduced (pp) | -10% losses prevented | -20% losses prevented | Avg return cost (pp) |
|:--|:-:|:-:|:-:|:-:|
| B_hard5 | +19.23 | 27 | 4 | +1.84 |
| C_hard7 | +16.19 | 26 | 4 | +0.96 |
| D_atr | +16.19 | 26 | 4 | +2.19 |
| E_trailing | +16.19 | 26 | 4 | +4.98 |
| F_breakeven | +13.62 | 26 | 4 | +3.00 |

**Tail-risk pragmatic winner:** `B_hard5` (5% hard stop) — best combination of largest-loss reduction and minimal avg-return sacrifice.

### Combined verdict

- **By spec (§10.2 primary = portfolio Max DD):** STAND-DOWN
- **By operator's stated concern (single-trade tail):** RECOMMEND-STUDY-FURTHER — `B_hard5` is the pragmatic best but each stop policy costs win-rate and profit-factor materially. Trade-off is real, not clean-win.

**These verdicts disagree.** That disagreement itself is the finding: **the primary decision metric in RISK001-A §7 (portfolio Max DD) does not match the risk the operator flagged (per-trade tail).** Before authorising RISK001-C, revisit §7 and pick — this is a first-principles choice about what AEGIS is protecting against, not a data-driven optimisation.

Sector-neutrality guard (§10.2 criterion 4) is qualitative on the current dataset — the top-loser tickers span multiple sectors (RELAXO / RATNAMANI / TCS = Consumer Disc / Industrials / IT). No sector-only kill mode identified.

## 6. Per-position path evidence (baseline)

- **Avg MFE:** 11.90% (positions gain this much at their peak on average)
- **Avg MAE:** -7.29% (positions lose this much at their trough on average)
- **Avg underwater bars:** 27.6 of 63 days
- **Avg profit given back:** 7.42% (peak-to-exit gap)

## 7. Deliverables generated

- `research/RISK001-A_RESULTS.md` — this document
- `research/policy_comparison.csv` — 6 rows × 15 metric columns
- `research/equity_curves.csv` — daily equity + drawdown per policy, long format
- `research/position_level_analysis.parquet` — 6 × N rows, per-position × per-policy sim outcome

## 8. Integrity

- Sealed files touched: **0**
- Production code touched: **0**
- cumulative_strategy_search: **38** (unchanged)
- All 6 policies frozen before simulation ran (no post-hoc parameter tuning)
- Random seed for bootstrap: 20260717
- Bootstrap iterations: 10,000
- Cost assumption: 16 bps round-trip applied identically to every policy
- Slippage assumption: 5 bps per side (mid-cap NSE conservative)
- Fill assumption: intraday breach → stop-price fill; gap-down → open-price fill

## 9. Decision hand-off

Because spec-verdict and tail-verdict disagree, the honest hand-off is:

1. **Do NOT author RISK001-C implementation yet.** Not because there's no opportunity — but because the metric that defines "winning" hasn't been resolved.
2. **Operator decision required on RISK001-A §7 primary metric:**

   | Option | Primary metric | Result on this data |
   |:--|:--|:--|
   | A | Portfolio Max Drawdown (current spec) | STAND-DOWN |
   | B | Largest single-trade loss | RECOMMEND `B_hard5` |
   | C | Weighted composite (Portfolio DD + Largest-loss cap) | needs new definition |

3. **If Option B is chosen**, the winning policy is `B_hard5` (5% hard stop). Adopt with two caveats:

   - Profit factor drops materially (see §5) — accept that as the cost of tail control
   - Winners cut short — ~11pp drop in win rate is not statistical noise

4. **If Option A is confirmed**, close RISK001 track, redirect capacity to OPS002.

5. **Regardless of choice**, mark this study as evidence — do not repeat the simulation on the same dataset. Re-running with the same policies on the same 285 positions is not new evidence.
