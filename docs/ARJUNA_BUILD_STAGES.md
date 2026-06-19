# ARJUNA — Staged Build Plan (v1)

Build order with a **test gate** at the end of every stage. We do NOT move to the next
stage until the current one passes its test. Spec it implements: [ARJUNA_AI_STRATEGY.md](ARJUNA_AI_STRATEGY.md).

Goals this serves: **pick the best stocks, AVOID bad ones before ordering, decent win rate,
beat the Nifty net of cost (the real 10/10 bar).**

---

## STAGE A — Data & Features (the fuel)  → `[ ]`
| # | Module | Does |
|---|---|---|
| A1 | `india/data_nse.py` (+ broker pull) | Expand universe to **Nifty 100**; pull clean history (Angel, incremental). |
| A2 | `india/feature_engine.py` | ~30 signals/stock/week: technical + ALL fundamentals + macro/sector. |
| A3 | `india/labels.py` | Two targets: `forward_return_rank` (picker) and `win` (avoidance filter). |

**TEST A:** ~100 stocks with full history saved; feature matrix builds with no NaN leakage;
label distribution sane (≈balanced win/loss). Print shape + sample rows.

## STAGE B — The AI Brain (pick best + avoid bad)  → `[ ]`
| # | Module | Does |
|---|---|---|
| B1 | `india/ai_ranker.py` | **GBT** learns feature→forward-return-rank. **PICKS THE BEST.** |
| B2 | `india/ai_avoid.py` | P(win) meta-label. Low-confidence picks **VETOED before ordering.** |
| B3 | `india/reject_rules.py` | Deterministic pre-trade vetoes (illiquid, broken chart, debt+weak FCF, crowding). |

**TEST B:** ranker beats a random/momentum baseline on out-of-sample rank correlation (IC > 0);
avoidance filter raises win rate vs no-filter on a holdout; reject rules remove known-bad names.

## STAGE C — Portfolio & Cost  → `[ ]`
| # | Module | Does |
|---|---|---|
| C1 | `india/portfolio.py` | Top 15–20 survivors, equal-weight, VIX de-risk, **monthly AND weekly**. |
| C2 | `india/costs.py` | Indian costs ~21bps (brokerage+STT+GST+SEBI+stamp+slippage) on every trade. |

**TEST C:** portfolio turns scores→weights correctly; cost model matches a hand-checked trade;
both horizons produce a position series.

## STAGE D — Honest Validation (the 10/10 gate)  → `[ ]`
| # | Module | Does |
|---|---|---|
| D1 | `india/backtest_ai.py` | Walk-forward replay, both horizons, honest-floor vs optimistic-fundamentals. |
| D2 | `india/validate_gate.py` | Purged+embargoed CV, Deflated Sharpe, **beat-Nifty** check, win-rate/expectancy. |
| D3 | `india/report_ai.py` | ₹ YoY, win rate, per-stock blotter, current picks WITH reasons + why others avoided. |

**TEST D (the real one):** does any variant beat Nifty buy-and-hold on **return AND Sharpe AND
drawdown**, net of cost, out-of-sample? Report the honest verdict either way.

## STAGE E — Go Live (only if D passes)  → `[ ]`
| # | Module | Does |
|---|---|---|
| E1 | `india/run_arjuna.py` | Paper-trade on Angel during market hours; then fund. |

**TEST E:** paper run places the same picks the backtest would, logs ₹ P&L live.

---

## Honest notes (carried from the spec)
- **Win rate:** target ~75% via SELECTIVITY (avoidance filter + hard rejects = trade fewer, better),
  but we report the REAL number + expectancy. High win rate alone ≠ profit; beating the Nifty is the bar.
- **Fundamentals look-ahead:** snapshot fundamentals are flagged "optimistic/not-tradeable"; a
  technical+macro-only "honest floor" runs in parallel. Only that (or point-in-time) justifies real money.
- **Kill criterion:** if nothing beats the Nifty net of cost OOS, we say so and recommend indexing.

## Progress log
- 2026-06-19: plan saved. Starting Stage A.
