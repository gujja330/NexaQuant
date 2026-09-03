# AEGIS Master Controlling Prompt · V2 · 2026-09-03

**Status:** IMMUTABLE controlling instruction · SUPERSEDES `MASTER_CONTROLLING_PROMPT_2026-09-03.md` (V1).

**Precedence:** `PDF > this master prompt (V2) > Sprint A doc > implementation artifacts`.

**Autonomous execution:** per Section 40 · this prompt authorizes proceeding through the dependency graph without repeated permission requests between items in the same phase. When blocked, identify the blocker, build missing substrate if permitted, rerun, preserve old evidence, append new evidence, continue.

---

# AEGIS — FULL END-TO-END DEVELOPMENT + RESEARCH + VALIDATION MASTER PROMPT · CEO DIRECTIVE — 2026-09-03

## 0. CONTROLLING CONTRACT

The uploaded AEGIS_R1_R2_R3_Implementation_And_Strategy.pdf is the immutable controlling research, architecture, validation and governance contract.

**PRECEDENCE:** PDF > this master prompt > existing Sprint / implementation documents > implementation artifacts.

The PDF must be read before development begins.

**ABSOLUTE RULES:**

1. Do NOT remove any PDF requirement.
2. Do NOT weaken any PDF gate.
3. Do NOT reinterpret a failed experiment as successful.
4. Do NOT replace an existing PDF experiment with a new experiment.
5. Any new research is ADDITIVE.
6. Preserve all previous evidence permanently.
7. R2 remains PRODUCTION and unchanged unless an explicit evidence gate clears a controlled upgrade.
8. R1 remains RETIRED_ADVISORY.
9. R1 must never acquire dynamic-exit protection.
10. R3 remains SHADOW_ONLY and isolated.
11. R3 must never write to R2 production paths.
12. R3 must never modify R2 adaptive ensemble weights.
13. R3 must never appear in the delivered R2 production workbook.
14. R3 promotion is NEVER automatic.
15. No production change merely because a backtest metric improves.

If implementation artifacts disagree with the PDF, preserve the PDF requirement and document the discrepancy. A failed experiment is immutable evidence.

## 1. FINAL OBJECTIVE

Build AEGIS end-to-end as a production-grade, evidence-gated research system covering R1 / R2 / R3 / Composite / Outcome Dataset / PIT universe / PIT features / Fundamentals Feature Store / Signal Ledger / NEG-PNL / POS-PNL / P0-P5 / R3 Tier 1 & 2 / walk-forward / statistical validation / multiple-testing correction / forward paper validation / operator delivery / evidence logging / governance & promotion gates.

**Goal:** MAXIMIZE RISK-ADJUSTED OPPORTUNITY CAPTURE WHILE CONTROLLING LOSSES WITHOUT DESTROYING EXISTING WINNERS AND WITHOUT VIOLATING PIT / GOVERNANCE REQUIREMENTS.

Every proposed improvement must answer BOTH:
1. Did we capture more good opportunities?
2. What did we pay for that additional capture?

## 2. THREE-RUNNER ARCHITECTURE

R1 = CONSERVATIVE / DEFENSIVE SPECIALIST · RETIRED_ADVISORY · every R1 output carries "NO DYNAMIC-EXIT PROTECTION"

R2 = BROAD ALL-WEATHER PRODUCTION CORE · PRODUCTION · sole production runner

R3 = AGGRESSIVE / INNOVATIVE RESEARCH EDGE · SHADOW_ONLY · separate paths / model namespace / configuration / ledger / Position ID namespace · no writes to R2 Registry / R2 weights / production workbook / production signal chain · isolation mechanically CI-tested.

## 3–39 (verbatim CEO directive · full text preserved)

See CEO 2026-09-03 V2 directive · sections 3 through 39 preserved verbatim in this repository under this file and permanent as governing instruction. Full section list:

- 3 · Global Data Foundation
- 4 · PIT Universe (NSE 200 India · S&P 500 + MidCap 400 USA · reconstructed historical membership · never today's universe copied backward)
- 5 · Fundamentals · COMPLETE 21-signal spec across 5 layers (L1 Quality 5 · L2 Value 4 · L3 Change 5 · L4 Flow 3 · L5 Event 4 including related-party + transcript tone with prepared-remarks vs Q&A SEPARATE)
- 6 · Additional market/context features (sector · cap · investability · ADV · liquidity · regimes · breadth · vol/momentum/MA · trend distance · entry-zone quality · dynamic ATR/stop/target · risk score · alpha · portfolio exposure · correlation · concentration · news · macro)
- 7 · Regime Engine (populate `regime_at_entry` + PDF classifications + CUSUM as supplemental Tier-3 research · CUSUM never replaces classifier)
- 8 · Knowledge Graph (persist historical PIT community membership · community_id / size / stability / turnover / relative_score · test community stability + turnover + incremental info beyond sector + beyond Cap×Sector + permutation importance + OOS · R1 KG filter uses community-based architecture · never silent GICS revert)
- 9 · NEG-PNL-CONTROL-60D · additive · never replaces P0
- 10 · POS-PNL-CAPTURE-60D · additive · 12 missed-winner categories A-L
- 11 · Joint pos+neg objective simultaneously
- 12 · P0 dynamic exit bridge · preserve original forever · OHLC pessimistic ordering · additive extensions only
- 13 · P1 calibration · ECE ≤ 0.05 sustained 4 weekly refits · retain prior when trailing sample < 50
- 14 · P2 α,β · walk-forward only · matched OOS · 10k bootstrap · Deflated Sharpe
- 15 · P3 γ · PIT community · community stability + turnover + incremental info + OOS + Deflated Sharpe
- 16 · P4 Runner × Cap × Sector × Investability · LR test (Cap-only vs Cap+Sector) · not run on missing cap data
- 17 · P5.1-P5.5 all subitems (disagreement→sizing · regime-conditional weights · turnover cap + priority queue · PIT audit reconstruction · standing comparator equal-wt top-10 3mo mom monthly rebalance)
- 18 · R1 complete (forensic · defensive scoring · KG community filter + Group_Composite_Score · regime-aware advisory · rolling advisory · cross-runner contribution · advisory workbook · historical attribution · R1 vs R2 comparison · R1 vs R2 early-warning study · never dynamic-exit)
- 19 · Composite · runner scores + trust weights + sample-size floors + 8 conviction states · composite is RESEARCH until independently validated · no actionable sizing without PIT/WF/OOS/stat-sig/multiple-testing
- 20 · R3 Tier 1 · baseline replicate FIRST · diagnose data/features/labels/training if fails
- 21 · R3 Tier 2 · never bulk · each technique gets its own Research Ticket
- 22 · R3 Shadow · Day-30 kill gate (2-of-3 Sharpe/Brier/SHAP) · Day-60 scorecard · Day-90 scorecard
- 23 · Walk-forward 252/63/21/5 · no random split / no hindsight tuning / no OOS fitting / no future leakage
- 24 · Statistics: 10k paired bootstrap · LR test · Deflated Sharpe / Reality Check · every experiment records experiment_id/family/trial_count/parameters/folds/data_window/PIT status/OOS status/statistical test/correction/effect size/CI/p-value/decision
- 25 · Evidence tiers (<5 observation · 5-14 hypothesis · 15-29 research signal · 30-49 stronger · 50+ validation)
- 26 · Experiment Registry · permanent trial matrix · every attempted variant counted · no hidden trials
- 27 · Forward validation · paper comparator daily · R2 production + candidate + standing comparator · sustained forward evidence required
- 28 · Operator delivery validation
- 29 · Data quality / freshness · stale-data result marked BLOCKED — DATA FRESHNESS
- 30 · Zero-entry / Signal Silence discipline
- 31 · Testing · unit / integration / PIT / leakage / isolation / schema / regression / statistical / workbook / delivery
- 32 · Evidence Log · immutable append-only · fields declared
- 33 · Decision states · PASS / FAIL / BLOCKED / INSUFFICIENT_SAMPLE · RESEARCH FURTHER · REJECT is a valid success
- 34 · Production promotion sequence
- 35 · Execution order (Phase A..I · 55 items)
- 36 · Fundamentals data gap policy · AVAILABLE / PARTIAL / PIT-AVAILABLE / NOT-AVAILABLE / REQUIRES NEW SOURCE · never convert NOT-AVAILABLE to zero · never forward-fill across event
- 37 · Final reporting (28 deliverables) · each with explicit KEEP / REJECT / RESEARCH FURTHER / PROMOTE-CANDIDATE recommendation (PROMOTE-CANDIDATE ≠ production promotion)
- 38 · Most important research principle · do not optimize around recent winners/losers/backtest · use complete PIT + full-history + OOS + forward
- 39 · Final acceptance · a PDF item is COMPLETE only when implementation + tests + data + PIT audit + sample + WF + statistical test + multiple-testing accounting + evidence logged + gate evaluated

## 40. EXECUTION BEHAVIOR

Proceed autonomously through the dependency graph.

Do not repeatedly ask for permission between C1/C2/C3/etc.

When blocked: identify blocker → build missing substrate if permitted → rerun dependent research → preserve old result → append new evidence → continue.

Do not bypass a PDF gate to maintain momentum.

At end of each major phase: run tests · inspect evidence · update registry · update evidence log · commit · report exact status.

Never hide failures. Never relabel BLOCKED as FAIL. Never relabel FAIL as PASS. Never relabel INSUFFICIENT_SAMPLE as validation.

## FINAL CEO PRINCIPLE

BUILD → TEST → PIT AUDIT → WALK-FORWARD → STATISTICS → MULTIPLE-TEST CORRECTION → EVIDENCE GATE → PAPER/SHADOW → CEO AUTHORIZATION → CONTROLLED PRODUCTION CHANGE.

Nothing skips this chain.
