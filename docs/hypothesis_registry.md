# ARJUNA — Hypothesis Registry

> The scientific contract. Nothing is promoted on intuition. Every claim is GREEN (validated,
> frozen), YELLOW (promising, needs testing), or RED (tested, rejected). Flow:
> **Hypothesis → Experiment → Evidence → Promotion.** Updated 2026-06-22.

## 🟢 GREEN — validated, frozen (real backtests + diagnostics)

| Claim | Evidence | Notes |
|---|---|---|
| HRP/EW + regime, quarterly, 15 stk, sector≤2 = the champion | full backtest; DSR 0.995, PBO 0.01 | Core v2.2 |
| **The regime overlay is the real edge** (not selection/weighting) | decomposition: w/o regime Sharpe ~1.3, with it ~2.0; helped 3/4 recent quarters (+7.5 vs +4.7) | `ARJUNA_STRATEGY_DECISION.md` |
| Quarterly > monthly | Sharpe 1.86 vs 1.70, wins at all cost levels | — |
| Sector≤2 | tuning grid + stress robust | — |
| BROAD (EW-all + regime) is a valid higher-return style | DSR 0.992, higher CAGR every sub-period, holds on Nifty-100 | survivorship-flattered; Sharpe parity is the honest read |
| Monte-Carlo / recovery / underwater / time-div / tail / DSR / PBO | all real simulations on historical distribution | survivorship-inflated levels; *shapes* are the signal |
| Horizon dominates odds at the short end | conditional matrix: 1W ~51–59% across all regimes | `evidence/probability_matrix.py` |

## 🟡 YELLOW — promising, NOT yet validated (do not over-sell)

| Claim | Status | Evidence we have | What's missing |
|---|---|---|---|
| **Probability Surface** (P(+) by horizon) | PARTIALLY VALIDATED | unconditional curve from champion (55→96%) is real | conditional-by-regime is surprising (below); forward data |
| **Confidence = min(regime, horizon)** | ASSUMPTION, mildly REFUTED | conditional matrix shows Weak-regime entries had *higher*, not lower, odds | kept as a *conservative* heuristic only; real mapping needs forward data (rare cells are bull-flattered) |
| **Probability Surface × Regime** (conditional) | TESTED, INCONCLUSIVE | matrix populated (`probability_matrix.py`); pattern: Weak ≥ Strong on odds | windows overlap; Weak 6M/1Y = 100% is a small-sample/bull artifact — not trustworthy yet |
| **Horizon Modes** (Tactical/Opportunity/Core) | FRAMEWORK | short-end coin-flip confirmed; labels are honest | mode *boundaries* not optimised; forward data |
| **Capital Ladder** (3→25 stk by capital) | PARTIALLY TESTED | each rung backtested (15 = concentrated sweet spot) | survivorship; not forward; whole-share frictions |
| **Horizon-aware selection** (momentum@1M, quality@6M, regime@1Y) | PURE HYPOTHESIS | none | a real A/B vs the current selector, gated |
| **Position count by horizon** | PURE HYPOTHESIS | none | backtest count×horizon |

## 🔴 RED — tested, rejected (do not revisit without new data)

| Claim | Why rejected |
|---|---|
| ML return prediction (XGBoost/LightGBM/RF) | AUC ~0.50 on public data |
| Deep learning (LSTM/Transformer) | no better than random on returns |
| Reinforcement learning (PPO) | lost to buy-and-hold; overfit |
| GNN | no edge |
| Per-stock direction timing | turned SBI +276% into +34% (`per_stock_timing.py`) |
| Recovery / anti-fragility / persistence ranking | re-derives low-vol (AUC 0.66 vs vol 0.68; `resilience_ranking.py`) |
| Multibagger identification | ~random (2/10) |
| Dynamic-N, exposure tiers | lower Sharpe than fixed |
| HMM regime, GARCH, vol-targeting, crash classifier | lost to the simple rule |
| Sector-momentum tilt, ranking IC, triple-barrier | no/zero edge |

## The standing rule

From here: **no promotion on intuition.** A YELLOW item moves to GREEN only via a pre-registered
experiment (hypothesis + target + success criteria: DSR>0.95 · PBO<0.05 · rolling Sharpe>Core ·
acceptable turnover · **forward paper > 4 quarters net of cost**). The single most valuable missing
evidence is **forward paper (Q3'26→Q2'27)** — nothing else moves the needle as much. Less
philosophy, more experiments.

## Open tests (priority order)

1. ✅ Probability Surface × Regime — DONE (`evidence/probability_matrix.py`); inconclusive, see YELLOW.
2. Capital Ladder — partially done; needs forward + frictions.
3. Confidence Matrix from historical frequencies — the conditional matrix IS this; thin cells.
4. Horizon-aware selector — A/B test, unbuilt.
5. Position count by horizon — unbuilt.
6. **Forward paper (Q3'26→Q2'27)** — the big one. Time, not code.
