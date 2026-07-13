# NexaQuant · Post-LAB010 Research Audit

**Date:** 2026-07-13 · **Auditor role:** Principal Quant Research Architect (adversarial).
**Scope:** LAB001–LAB010 evidence synthesis + gap audit + roadmap justification.
**Status:** Read-only audit. No production, Core, Telegram, or trial-manifest modification.

---

## 0. Executive summary

- **Total sealed research trials over 4.5 years:** 38 (`india/ai_lab/trial_manifest.md:19`).
- **Candidates promoted to production from LAB001–LAB010:** **0**.
- **Alpha dimensions actually tested:** 1 (price-based rebalance timing / exit / exposure).
- **Alpha dimensions planned but NEVER tested:** 4 (earnings, PIT fundamentals, corporate events, institutional flows) — all remain LAB001–004 stubs.
- **Production HOLD=63 / rebal=63 status:** pre-dates all research; supported as "not-rejected" (LAB008/LAB009 methodology-limited), never affirmatively validated.
- **Backtest window (2021-10-01 → 2026-03-27):** used in 5 consecutive labs (LAB006–LAB010). Data-burn is severe.
- **Recommended verdict:** **HOLD on further alpha search on the same data.** Establish forward-paper validation and orthogonal-data acquisition first.

## 1. Evidence map — LAB001 through LAB010

| Lab | Domain | Status | Trials added | Verdict | Production impact | Key limitation |
|---|---|---|---:|---|---|---|
| LAB001 Earnings | Non-price alpha (surprise, guidance, revisions) | STUB — planned | 0 | N/A | none | `data/layers/earnings.parquet` does not exist |
| LAB002 Fundamentals | PIT fundamentals + acceleration | STUB — planned | 0 | N/A | none | `data/layers/fundamentals.parquet` does not exist |
| LAB003 Events | Corporate events (M&A, wins, approvals) | STUB — planned | 0 | N/A | none | `data/layers/events.parquet` does not exist |
| LAB004 Flows | FII/DII, MF holdings changes | STUB — planned | 0 | N/A | none | `data/layers/flows.parquet` does not exist |
| LAB005 Ranking | LtR ranker on rich features | STUB on-main; harness claimed on `ai-lab` branch | 0 | Price-only rejected (RQS 0.504 vs 0.510) per README; result not verifiable on-main | none | Blocked on LABs 001–004 delivering kept features |
| LAB006 Exit Strategy | Early-exit rules B/C/C1 | EXECUTED — ALL REJECTED | 28 | Rule B rejected on economics; Rule C: PBO 0.229, all 12 configs REJECT; Rule C1: 2/6 gates pass, DSR 0.817 < 0.90, Weak-regime CAGR halved | none — `exit_reasons.py` in prod is admitted cosmetic (`README.md:88-90`) | Rules A/D deferred (no PIT score history / not backtestable); documented DSR-count bug (n_trials=30 vs true 28) |
| LAB007 Dynamic Exposure | 4 exposure policies (A/B/C/D) vs N0 | EXECUTED — ALL REJECT | 4 | A/B/C/D all fail Ulcer + DSR gates; PBO 0.700 (cash=0%) / 0.871 (cash=6%); N0 top-2 in 0% of folds | none — N0 stays production | Only 4 Weak cycles in confirmation window; PBO very high; era effect not fixable via exposure |
| LAB008 Horizon Calibration | H21/H42/H84 vs N0=63 | EXECUTED — ALL REJECT under sealed methodology; post-execution audit → Decision B (methodology-limited) | 3 | Every alternative fails G1 (CAGR gap) | none — SUPERSEDED by LAB009 | Calendar-phase confound (H84 misses 2021-07 through 2021-09); 100% turnover cost overstated (actual H21 turnover 32.5%) |
| LAB009 Horizon Phase Recalibration | H21/H42/H84 with realistic turnover + 4 phase offsets each | EXECUTED — 3 evidence states A/B/C due to two mid-lab methodology audits | 3 | State A: H42 PROMOTE / H84 REJECT. State B (maturity-corrected): H42 REJECT / H84 PROMOTE. **State C (period-corrected, `413a735`, final trustworthy): H21/H42 REJECT, H84 PROMOTE-ELIGIBLE (Lab level)** | none — HOLD=63 unchanged | PBO 0.87/0.84; 12–13 cycles per H84 phase; Gate 3 margin +0.021; Gate 5 exactly at 0.500 |
| LAB010 H84 Robustness Validation | LOBO + cost stress on H84 vs N0 (no search) | EXECUTED — **NOT_VALIDATED** | 0 (validation of existing hypothesis) | V4 stress cost passes fully; V6 full-window LAB009 replay passes fully; V1 LOBO_dropB2/dropB3 FAIL Gate 3; V2 LOBO_dropB1 FAIL Gate 1 (cash=0% only); V3 LOBO_dropB3 phase-win-rate 0.25 < 0.50; V5 block-majority 1/3 (H84 wins only B2). **H84's LAB009 verdict depends almost entirely on block B2 (2023-07 → 2024-12)** | none — HOLD=63 unchanged | Same data as LAB009 (not truly OOS); PBO 0.90/0.94 (higher than LAB009's 0.87); H84 loses cycles to block boundaries proportionally more than N0 (harder for H84 — a stress feature, not a bug) |

## 2. What is actually running in production

- `india/recommendation_registry.py:31` — `HOLD = 63` (holding period in trading days)
- `india/recommendation_generator.py:44` — `CONFIG = dict(method="hrp", regime="global", sector_cap=2, rebal=63, name_cap=0.30, ...)`
- `india/confidence_engine.py:32-51` — `current_regime()` — the LAB007 N0 (VIX 120d q80 → 0.6/1.0, Nifty 200-DMA → 0.6/1.0, `global_exposure` multiplicative)
- `india/exit_reasons.py` — cosmetic exit labels, admitted post-hoc (`LAB006/README.md:88-90`) — NOT evidence-backed
- Portfolio construction: HRP with `sector_cap=2`, `name_cap=0.30` — **never challenged in any lab**
- Universe: Nifty-200 India equities — **never expanded or ablated in any lab**

## 3. Contradictions and reversals across labs

| Contradiction | Details |
|---|---|
| H42 promote → reject | LAB008: H42 REJECT (under 100% turnover). LAB009 State A: H42 PROMOTE-ELIGIBLE. LAB009 State B (maturity boundary): H42 REJECT (Gate 3 margin flipped from +0.027 → -0.024). LAB009 State C (period boundary): confirmed REJECT. Verdict FLIPPED four times in three labs on identical data. |
| H84 promote → not-validated | LAB008: H84 REJECT. LAB009 State B/C: H84 PROMOTE-ELIGIBLE. LAB010: NOT_VALIDATED under LOBO chronological stress. Verdict trajectory: reject → promote → not-validated. |
| "63d validates" language | LAB008 base report said "validates 63d". LAB008 evidence audit (`LAB008_EVIDENCE_AUDIT.md:143-150`) explicitly downgraded this to "not-rejected". Weaker language survives; stronger language was retracted. |
| PBO gate | LAB006 Rule B was originally rejected partly on PBO 0.850 that was later RETRACTED as degenerate N=2 CSCV (`reports/rule_B_findings_2026-07-13.md` audit banner). PBO is now diagnostic-only for all subsequent labs (`LAB_STANDARDS.md:135-140`). |

**None of the reversals reached production** — HOLD=63 has never changed. But the reversal frequency signals that the same underlying data admits multiple mutually incompatible verdicts depending on methodology micro-choices.

## 4. Adversarial concerns (evidence-cited)

### 4.1 Data burn / same-window reuse

Labs LAB006–LAB010 all evaluate against the same core registry (`data/aegis_registry.csv`) or its H×P re-derivations, over the same asof window 2021-07-01 → 2026-01-27 (confirmation ends 2026-01-27 in all sealed period-mature-bounded splits). Five consecutive labs on the same 4.5-year window. Whatever alpha exists in this data has been searched for from multiple angles. Additional search of similar hypotheses on this window creates severe multiple-testing burden that DSR at n_trials=38 does not fully capture (DSR corrects for search over Sharpe candidates, not for cascaded conditional experiments).

### 4.2 PBO trend

- LAB006 Rule C: 0.229 (12 configs)
- LAB007 A/B/C/D: 0.700 (cash=0%), 0.871 (cash=6%) (5 configs, N low)
- LAB008 H21/H42/H84: 0.300 / 0.314 (4 configs, N < min interpretation threshold)
- LAB009 (16 phase configs): 0.871 / 0.843
- LAB010 (8 phase configs): 0.900 / 0.943

Recent trials PBO is climbing (0.90-0.94). This is diagnostic of exhausted-search overfitting: even after methodology corrections, the top-K configs on the same data no longer generalize to leave-one-fold-out subsets.

### 4.3 Small-sample power

- LAB007 confirmation: 4 Weak cycles (`preregistration.md:127-130`).
- LAB009 H84 per phase: 12-13 cycles (`LAB009 THREE_STATE_FORENSIC_COMPARISON.md`).
- LAB010 LOBO fold H84 per phase: 5-11 cycles.

At this sample size, a single volatile cycle can flip a gate. The verdict flips observed in §3 are consistent with this power regime.

### 4.4 Universe-selection

Nifty-200 is chosen a priori. There is no evidence in any of LAB001–LAB010 that the current universe (a) is stable through time, (b) has survivorship-free construction, (c) generalizes to Nifty-500 / mid-cap / off-index securities. AEGIS's stated preference for low-volatility names (LAB006 Rule B explanation, README:52-54) is a universe artifact, not a robustness property.

### 4.5 Execution assumptions

Every simulator uses `cost_bps` × turnover as the entire execution cost model. There is no modeling of:
- Slippage on illiquid names
- Market impact of position sizes at nominal capital scale
- Timing (open vs close vs VWAP)
- Failed fills, partial fills, cancellations
- Bid-ask spread outside the point-in-time close

Whether the promoted (frozen) system actually achieves its backtested characteristics under real fills is untested. `india/broker_angelone.py` exists but no lab has connected it to a live-fill dataset for realism calibration.

### 4.6 Cosmetic exit labels in production

`india/exit_reasons.py` is called from `india/telegram_notify.py` — real users see these labels. LAB006/README.md:88-90 explicitly labels them as "clearly labelled as post-hoc explanations, NOT evidence-backed advice." A cosmetic label that users read as diagnostic is a governance risk that no lab has audited.

### 4.7 Missing walk-forward on live paper data

No lab has tested any production behaviour on data POSTDATING its own preregistration seal. Every "validation" has been in-sample or LOBO-within-sample.

## 5. Structural gaps — what has never been tested

**Alpha families never touched by any executed lab:**
1. Earnings surprise / guidance / revisions (LAB001 STUB)
2. PIT fundamentals + acceleration (LAB002 STUB)
3. Corporate events (LAB003 STUB)
4. Institutional flows (LAB004 STUB)
5. Learning-to-Rank over enriched features (LAB005 blocked)
6. Momentum overlays (never proposed as a lab)
7. Cross-sectional value factor (never proposed)
8. Sector-conditional strategies (`sector_cap=2` is a portfolio rule, not a strategy)
9. Multi-horizon overlays (blending 63d with 21d or 84d — never proposed)
10. Options / derivatives strategies (universe is equities-only)

**Risk dimensions never tested:**
1. Regime-conditional position sizing (beyond current_regime())
2. Tail-risk hedging
3. Cross-asset diversification
4. Volatility targeting
5. Correlation-based deleveraging

**Portfolio construction alternatives NEVER tested vs HRP:**
1. Equal-weight
2. Inverse-volatility
3. Minimum-variance
4. Rank-weighted by score
5. Turnover-penalized construction

**Execution / operations never audited:**
1. Slippage model calibration against Angel broker fills
2. Fill quality over daily open vs adjacent close
3. Capacity analysis (what fraction of ADV do positions represent?)
4. Rebalance-day queueing / execution latency

**Monitoring capability never built:**
1. Live-vs-backtest drift detector
2. Regime-shift alerts
3. Trial-count discipline dashboard
4. Automatic model-halt on out-of-envelope live behaviour

## 6. What the current state permits / forbids

- **Permits:** continued production operation with HOLD=63 / rebal=63 / current_regime() exposure / HRP construction. All three have been "not-rejected" by properly sealed labs.
- **Forbids (evidence-based):** any promotion of H84, H42, H21, exit rules A/B/C/C1, exposure alternatives A/B/C/D. All were tested and rejected.
- **Uncharted:** all non-price alpha families, portfolio-construction alternatives, execution modeling, forward paper validation, universe robustness. No lab has ever ruled these in or out.

## 7. The critical question

**Should NexaQuant do another alpha lab on the same data, or should it stop and do orthogonal work?**

Signals pointing to STOP-and-diversify:
- 5 consecutive labs (LAB006–LAB010) on the same window ⇒ severe data-burn
- Rising PBO trend (0.23 → 0.94) ⇒ evidence of exhausted-search fragility
- Four H42/H84 verdict flips on identical data ⇒ methodology-sensitivity at this signal-to-noise ratio
- Zero production impact from 38 trials ⇒ negative marginal value of same-data search
- Four planned non-price alpha families never touched ⇒ orthogonality gaps are enormous
- Zero forward-paper validation ⇒ true out-of-sample evidence is nil

Signals pointing to CONTINUE alpha search on the same data: **none supported by the evidence.**

**Verdict:** further alpha search on the current data is contra-indicated. NexaQuant needs:
1. Orthogonal data acquisition (earnings/fundamentals/events/flows)
2. Forward-paper validation of the frozen production system
3. Portfolio-construction ablation (HRP is a load-bearing assumption never tested)
4. Execution-model calibration against actual broker fills

## 8. Recommended top-5 next directions

Scored on: (E)xpected value / (O)rthogonality / (D)ata-availability / (L)eakage-risk / (F)-overfit-risk / (P)-production-usefulness / (C)-research-cost / (U)-urgency.

| # | Direction | E | O | D | L | F | P | C | U | Priority |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1 | Forward paper-trading validation of frozen system | Med | High | High (starts today) | Low | Low | Very high | Low | Highest | **CRITICAL** |
| 2 | Portfolio-construction ablation (HRP vs alternatives) | Med | High | High (uses existing registry) | Low | Med | High | Low | High | **HIGH** |
| 3 | LAB001 Earnings data acquisition + PIT layer test | High | Very high | Blocked — no data yet | Med (event dating) | Med | High | High | Med | **HIGH** |
| 4 | Execution / slippage calibration against broker fills | Med | High | Requires paper-trading first (dependency on #1) | Low | Low | Very high | Med | Med | **MEDIUM** |
| 5 | LAB002 Fundamentals PIT acquisition | High | High | Requires paid data source or careful scrape | High (PIT critical) | Med | High | Very high | Med | **MEDIUM** |

**Recommended immediate next phase:** **MON001 — Forward paper-trading + monitoring**, NOT another LAB.

**Reason:** No amount of additional in-sample search will address the core problem (data burn + rising PBO + zero real-world validation). Forward paper-trading is free, orthogonal, non-search, and produces evidence about the frozen system that cannot be produced any other way. It also creates the substrate for #4 (execution calibration). LAB001 is next-highest priority AFTER #1 begins accruing evidence and ideally after data acquisition unblocks it.

The other four must wait because:
- #2 shares the same data-burn concern as LAB006-010 — running it now during peak PBO risk would compound the multiple-testing burden. Running it after 3-6 months of forward paper evidence gives fresh windows for validation.
- #3 depends on acquiring an earnings dataset (`data/layers/earnings.parquet` — does not exist).
- #4 depends on #1 producing broker fills.
- #5 depends on sourcing PIT fundamentals data.

## 9. Trial-count and research-overfit accounting

- Current `cumulative_strategy_search: 38`.
- LAB010 correctly did NOT increment (validation of already-counted H84 hypothesis).
- Any future lab that revisits horizon/exit/exposure on the same window must increment for each new hypothesis and would drive DSR further down.
- Forward-paper monitoring is NOT a strategy search and does not increment.
- Portfolio-construction ablation would count as strategy search (each alternative construction rule = 1 hypothesis).
- Earnings/fundamentals/events/flows layer tests count as strategy search (new hypotheses).

## 10. Audit conclusion

**Research maturity score: 62 / 100.**

- Methodology (+): sealed preregistration, AST-safe gate evaluator, YAML-driven config, mature-boundary + period-boundary correction discipline, trial manifest, PBO discipline, DSR with central n_trials, adversarial pre-seal audit workflow.
- Evidence discipline (+): every reversal is documented; nothing has been silently promoted; production has been held stable through methodology iterations.
- Alpha breadth (−): heavy concentration on one family (price-based rebalance/exit/exposure). Four planned non-price families untouched.
- Data burn (−): 5 labs on the same 4.5-year window. PBO trending up.
- Real-world validation (−): zero forward-paper evidence; execution model is a nominal cost-bps.
- Portfolio construction (−): HRP is an untested load-bearing assumption.
- Monitoring / governance (−): production cosmetic labels (`exit_reasons.py`) are admitted evidence-free but user-facing.

**Strongest validated capability:** research process discipline (LAB009 forensic audit + LAB010 preregistration + AST-safe evaluator + sealed thresholds).

**Biggest unresolved weakness:** no forward-paper evidence + HRP untested + execution model is nominal.

**Highest research-overfitting risk:** running yet another rebalance/exit/exposure lab on the same 2021-10 → 2026-03 window.

**Recommended next phase:** MON001 (Forward paper-trading + monitoring).

**GO / HOLD / STOP verdict for further alpha research:** **HOLD until forward-paper evidence is accruing.**
