# AEGIS Phase 4 · Product Completion Program (Institutional Edition)
### 🔒 LOCKED 2026-07-24 · Sits on top of Phase 3 (FROZEN)

**Directive:** Architecture is FROZEN. The objective is no longer building isolated engines. The objective is to transform AEGIS into a complete institutional-grade investment product for both India and USA through parallel development.

Phase 3 built the engines. Phase 4 wraps them into 20 complete product modules — each with India + USA implementations, a global-comparison artifact, and the full quality gate (tests · replay · walk-forward · docs · API · dashboard · reports).

---

## Hard Rules (locked · non-negotiable)

- **Dual-market parallel** — every sprint develops India + USA together (see [Phase 3 rule](AEGIS_PHASE3_MASTER_ROADMAP.md#hard-rule--dual-market-parallel-development-added-2026-07-24))
- **Global comparison artifact** — every sprint produces `reports/global/<module>_comparison.json`
- **No sprint complete until both markets pass**
- **No duplicate logic** — shared backend, country adapters only
- **Repository evidence only** — no assumptions
- **Historical replay compatible** · **walk-forward compatible** · **research governance mandatory**
- **No placeholder implementations** · **no paid APIs** · **no new AI agents**
- **No new architectural proposals from me** — implementation mode only. Any new engine requires explicit operator "essential" flag.

---

## Module → Existing-Substrate Map (repository evidence)

Before quoting cost/scope for each module, this table shows what already exists in the repo vs what would be net-new work.

| # | Module | Existing engines | Phase 3 sprints | Net-new work |
|---|---|---|---|---|
| 1 | Market Intelligence Center | Sprint 2 · Market Intelligence (india+usa) · Sprint 6.5 · Macro Intel · Sector Rotation | — | Dashboard + heatmap views · daily-summary compositor · global comparison |
| 2 | Research Center | `research/*` engines (adaptive_rec_v2 · risk_capital_v2 · knowledge_graph · sector_intelligence · industry_intelligence · company_intelligence · macro_intelligence · fusion) | — | Research explorer UI · timeline/history views · unified query API |
| 3 | Screening Center | none | — | **Engine work** — dynamic filter engine, saved-screens persistence, historical screen replay |
| 4 | Watchlist Center | none | — | **Engine work** — watchlist CRUD, alerts, history persistence |
| 5 | Recommendation Center | Sprint 3 Rec v3 + Runner 1 (legacy) + Sprint 7.7 replay + Sprint 7.8 benchmark | (Trade State C1 · Lifecycle C2 · Drift C4 · Failure C5) | Dashboard aggregator · analytics view |
| 6 | Trade Lifecycle Center | — | **C1 · C2 · C3 · C4 · C5** (all Trade + Failure + Drift sprints roll up here) | Center-view compositor |
| 7 | Portfolio Center | Sprint 5 Portfolio Engine · Sprint 5 state history · Sprint 7 Execution | **F1 · F2** (Decision + Timeline) | Global-portfolio view (combined India+USA) · rebalancing surface |
| 8 | Risk Center | Sprint 4 Risk Engine · Sprint 6.5 VIX + Regime | — | Stress/scenario surfaces · tail-risk composer · currency + liquidity risk views (some engine work) |
| 9 | Execution Center | Sprint 7 Execution Simulator + statistics + ledger | — | Paper-trading interactive layer · fill simulation UI |
| 10 | Replay Laboratory | Sprint 7.6 backfill · Sprint 7.7 replay + walk-forward + lookahead guard | (B0 · B1 · B2) | Interactive replay dashboard · scenario replay controller |
| 11 | Backtesting Laboratory | none (walk-forward exists but strategy-builder does not) | — | **Engine work** — strategy builder, parameter optimization, factor testing harness |
| 12 | Strategy Laboratory | 11 model factory models (momentum/trend/value/growth/quality/MR/news/macro/sector/event/AI-hybrid) + Sprint 2.7 ensemble | — | **Engine work (light)** — declarative strategy compositor on top of existing models |
| 13 | Learning Center | Sprint 6 Learning Engine · calibration · feature/model attribution · failure clusters | (C4 Drift · C5 Failure) | Promotion history view · model-evolution timeline |
| 14 | Research Factory | `research/adaptive_rec_v2` + `research/risk_capital_v2` (existing) | (G1 Research → Promotion loop) | Ticket system · governance surface |
| 15 | Operator Center | `india/telegram_notify.py` (SEALED) + `scripts/telegram_send_ux030.py` + existing dashboard | (E1 Telegram · E2 Dashboard · E3 Daily Report · D1 Lifecycle Manager · D2 Operator Intel) | Alert engine (light) |
| 16 | Analytics Center | many `reports/*.json` producers, no aggregation layer | — | Cross-market analytics compositor · performance analytics view |
| 17 | Reporting Center | ad-hoc `docs/AEGIS_*_REPORT.md` producers | — | **Engine work** — periodic report generator (daily/weekly/monthly/quarterly/annual) · PDF + Excel + HTML + MD renderers |
| 18 | API Center | none | — | **Engine work** — REST API layer over all report outputs · OpenAPI/Swagger |
| 19 | Administration Center | ad-hoc `configs/*.yaml` + no user/role model | — | **Engine work** — config surface · audit log surface · health monitor (some already exists via ops_check) · users/roles/permissions (new if genuinely needed) |
| 20 | Cross-Market Intelligence | none as a module (individual reports exist per market) | — | **Aggregator only** — composes existing per-market outputs into `reports/global/*` (falls out of dual-market rule) |

**Summary:**
- 8 modules are pure "wrap existing" (1, 5, 7, 8, 9, 10, 13, 20)
- 5 modules are Phase 3 sprint outputs rolled up (6, 15) or lightly wrapped
- 7 modules need SOME engine work (2, 3, 4, 11, 12, 17, 18, 19)

That mapping determines cost. Cheapest = wrap-only. Most expensive = full engine work.

---

## Directory Layout (locked)

### Per-market outputs (preserve existing dual-market layout)

```
reports/india/<module>/<file>.<ext>       ← India per-module outputs (new subdir structure)
usa/reports/<module>/<file>.<ext>         ← USA per-module outputs (new subdir structure)
reports/global/<module>_comparison.json   ← cross-market comparison (Phase 3 rule)
```

**Compat note:** the existing `reports/<file>.<ext>` and `usa/reports/<file>.<ext>` flat layout is preserved for backwards compat with the daily pipeline. Phase 4 introduces the `<module>/` subdirectories as ADDITIVE structure. Nothing existing moves.

---

## 20 Modules · Locked Scope

### Module 1 · Market Intelligence Center
**Substrate:** Sprint 2 · Market Intelligence · Sprint 6.5 · Macro Intel · Sector Rotation
**Features:** Market Dashboard · Breadth · Liquidity · Regime · Volatility · Advance/Decline · Sector Rotation · Heatmaps · Daily Summary
**Deliverables:** `reports/india/market/` + `usa/reports/market/` + `reports/global/market_comparison.json`

### Module 2 · Research Center
**Substrate:** `research/*` engines (adaptive_rec_v2 · risk_capital_v2 · knowledge_graph · sector/industry/company/macro intelligence · fusion)
**Features:** Research Explorer · Historical Research · Company · Sector · Industry · Macro
**Outputs:** Research Database · Research Timeline · Research History · Research Reports

### Module 3 · Screening Center ⚙ engine work
**Institutional Stock Screener · India + USA**
**Features:** Dynamic filters (Sector · Industry · PE · PB · ROE · ROCE · Growth · Momentum · Quality · Volatility · Liquidity · Market Cap · Dividend · Custom) · Save Screens · Historical Screen Replay
**Outputs:** `screen_results.parquet` · `saved_screens.json`

### Module 4 · Watchlist Center ⚙ engine work
**Features:** Manual · AI · Sector · Event · Macro · Operator · Historical Watchlists · Alerts
**Outputs:** `watchlists.json` · `watchlist_history.parquet`

### Module 5 · Recommendation Center
**Substrate:** Sprint 3 Rec v3 + Runner 1 legacy + Sprint 7.7 replay + Sprint 7.8 benchmark
**Features:** Runner 1 · Runner 2 · Comparison · Trade State · Trade Lifecycle · History · Timeline · Analytics
**Outputs:** `recommendation_dashboard.json`

### Module 6 · Trade Lifecycle Center
**Substrate:** Phase 3 sprints C1 · C2 · C3 · C4 · C5
**Features:** Entry · Holding · Targets · Exit · Post-Exit · Reversal · Re-entry · Failure · Learning
**Outputs:** `trade_lifecycle/`

### Module 7 · Portfolio Center
**Substrate:** Sprint 5 Portfolio + Sprint 5 state history + Sprint 7 Execution · Phase 3 F1 · F2
**Features:** India Portfolio · USA Portfolio · Global Portfolio · Cash · Allocation · Sector Exposure · Country Exposure · Risk · Returns · Timeline · Performance · Rebalancing
**Outputs:** `portfolio/`

### Module 8 · Risk Center
**Substrate:** Sprint 4 Risk Engine · Sprint 6.5 VIX + Regime
**Features:** Market · Sector · Portfolio · Position · Currency · Liquidity · Tail Risk · Stress Tests · Scenario Analysis
**Outputs:** `risk/`

### Module 9 · Execution Center
**Substrate:** Sprint 7 Execution Simulator + statistics + ledger
**Features:** Paper Trading · Execution Simulator · Transaction History · Slippage · Fees · Fill Simulation · Position Ledger
**Outputs:** `execution/`

### Module 10 · Replay Laboratory
**Substrate:** Sprint 7.6 backfill + Sprint 7.7 replay + walk-forward + lookahead guard · Phase 3 B0 · B1 · B2
**Features:** Historical Replay · Walk Forward · Benchmark · Scenario Replay · Replay Dashboard · Replay Reports
**Outputs:** `replay/`

### Module 11 · Backtesting Laboratory ⚙ engine work
**Features:** Strategy Builder · Historical Testing · Benchmark Testing · Factor Testing · Parameter Optimization
**Outputs:** `backtests/`

### Module 12 · Strategy Laboratory ⚙ light engine work
**Substrate:** 11 Model Factory models + Sprint 2.7 ensemble
**Features:** Momentum · Growth · Value · Quality · Low Vol · Dividend · Mean Reversion · Custom Strategy · Factor Combination
**Outputs:** `strategies/`

### Module 13 · Learning Center
**Substrate:** Sprint 6 Learning + Phase 3 C4 Drift + C5 Failure
**Features:** Failure Analysis · Recommendation Drift · Calibration · Outcome Learning · Promotion History · Model Evolution
**Outputs:** `learning/`

### Module 14 · Research Factory
**Substrate:** `research/adaptive_rec_v2` + `research/risk_capital_v2` + Phase 3 G1
**Features:** Research Tickets · Experiments · Promotion · Approval · Governance · Research Ledger
**Outputs:** `research_factory/`

### Module 15 · Operator Center
**Substrate:** `india/telegram_notify.py` (SEALED — extend via consumer, never touch contract) + Phase 3 D1 · D2 · E1 · E2 · E3
**Features:** Telegram · Dashboard · Alerts · Daily Report · Portfolio Summary · Market Summary · Trade Summary · Research Summary
**Outputs:** `operator/`

### Module 16 · Analytics Center
**Substrate:** all `reports/*.json` producers
**Features:** India Analytics · USA Analytics · Cross Market · Portfolio · Recommendation · Trade · Risk · Performance
**Outputs:** `analytics/`

### Module 17 · Reporting Center ⚙ engine work
**Features:** Daily · Weekly · Monthly · Quarterly · Annual reports in PDF · Excel · HTML · Markdown
**Outputs:** `reports/` (root · flat renders)

### Module 18 · API Center ⚙ engine work
**Features:** REST API · Research API · Recommendation API · Portfolio API · Replay API · Learning API · Risk API · Analytics API · Swagger · OpenAPI
**Outputs:** `api/`

### Module 19 · Administration Center ⚙ engine work
**Substrate:** ad-hoc `configs/*.yaml` + `ops_check.py` (partial)
**Features:** Configuration · Markets · Users · Roles · Permissions · Audit · Logs · Health · Monitoring
**Outputs:** `admin/`

### Module 20 · Cross-Market Intelligence
**Substrate:** the dual-market Phase 3 rule (falls out automatically as `reports/global/*` accumulates)
**Features:** India vs USA · Sector · Factor · Performance · Recommendation · Portfolio · Risk · Trade comparisons
**Outputs:** `reports/global/`

---

## Product Quality Gates (every module must include)

- [ ] India support
- [ ] USA support
- [ ] Global comparison
- [ ] Historical replay compatibility
- [ ] Walk-forward validation
- [ ] Unit tests
- [ ] Integration tests
- [ ] Regression tests
- [ ] Documentation
- [ ] API endpoint
- [ ] Dashboard tile / view
- [ ] Reports

Missing any = module NOT COMPLETE. No exceptions.

---

## Sprint-to-Module Mapping (dependencies · execution order)

Phase 3 sprints must execute in order (A1 → A2 → B0 → B1 → B2 → B3 → C1 → C2 → C3 → C4 → C5 → D1 → D2 → D3 → E1 → E2 → E3 → F1 → F2 → G1). Phase 4 modules complete as their substrate sprints ship:

| After sprint... | Modules that become buildable |
|---|---|
| A2 (Repository Audit + Engine Discovery done) | none · unblocks EVERYTHING |
| B2 (Walk-Forward institutional) | 10 (Replay Lab) |
| B3 (Runner Benchmark) | 5 (Recommendation Center) partial |
| C5 (Failure Analysis) | 6 (Trade Lifecycle Center) · 13 (Learning Center) |
| D3 (Explanation Engine) | 15 (Operator Center) · 5 (Rec Center) full |
| F2 (Portfolio Timeline) | 7 (Portfolio Center) · 8 (Risk Center) |
| G1 (Research promotion loop) | 14 (Research Factory) |

**Engine-work modules (3, 4, 11, 12, 17, 18, 19)** are independent of Phase 3 sprints — they can be prioritized separately. Each is its own "Sprint P4-Mx" (P4 = Phase 4, Mx = module number).

---

## What Comes Next (operator decides ordering)

Options for the FIRST Phase 4 work to start:

1. **Start Phase 3 A1** (Repository Audit) — read-only, unblocks the entire chain, produces the substrate map every downstream module needs
2. **Start Phase 3 A2** (Research Engine Discovery, after A1) — same discipline, produces the engine inventory
3. **Pick a low-dependency Phase 4 module first** — Module 20 (Cross-Market Intelligence — aggregates existing outputs · pure wrap) OR Module 3 / 4 (Screening / Watchlist Centers — engine work but Phase 3 independent)

**My recommendation** (informational only — decision is yours): **A1 first, then A2, then B0, then start Module 20 (Cross-Market Intelligence) in parallel with B1** since it's the cheapest module and aggregates whatever data exists. Everything else stays queued behind Phase 3 sprints.

---

## Governance for This Document

- **LOCKED 2026-07-24** by operator directive.
- Sits on top of `docs/AEGIS_PHASE3_MASTER_ROADMAP.md` (FROZEN).
- No sprint starts without explicit operator "start".
- Every module report must reference this doc + `docs/AEGIS_PHASE3_MASTER_ROADMAP.md`.
- **Implementation mode:** no new architectural proposals from me. Any request to add a NEW engine (not just wrap existing) requires explicit operator "essential" flag.

---

**End of Phase 4 · Product Completion Program · LOCKED 2026-07-24**

# MANDATORY PRIORITY OVERRIDE — INDIA FIRST, USA SECOND

Revise the Phase 4 execution plan immediately.

The user requires sequential production certification rather than parallel stabilization of India and USA.

## 1. Strict execution priority

Follow this order:

1. Complete India pipeline execution.
2. Complete India dataset validation.
3. Complete India lifecycle and historical reconciliation.
4. Complete India XLSX information and formatting corrections.
5. Complete India research and final processing.
6. Certify India repeat-run reliability.
7. Declare India 100% certified only with complete execution evidence.
8. Only then begin USA stabilization.
9. Complete USA using the same certification standards.
10. Certify the combined daily local execution.

Do not alternate between unresolved India and USA issues.

Do not begin USA-specific remediation while India remains uncertified.

Shared infrastructure fixes required for India are permitted, but preserve USA state and verify that shared changes do not introduce regressions.

## 2. India — mandatory 100% completion

India is the immediate and exclusive production priority.

The user recalls approximately 81 core pipeline stages followed by eight final processing steps.

Discover the authoritative stage counts from the current repository, including all nested subprocesses, workflow definitions, local runners and stage registries.

Do not assume the remembered counts are correct.

Verify every applicable stage individually.

For each stage, establish:

- Stage identifier and name.
- Actual command.
- Required inputs.
- Input freshness.
- Expected outputs.
- Actual outputs.
- Output schema correctness.
- Output semantic correctness.
- Execution duration.
- Exit code.
- Final validation status.

Every applicable required stage must PASS.

Every applicable optional stage must also be executed and evaluated. Resolve unexpected optional-stage failures rather than ignoring them.

Legitimately conditional or inapplicable stages must have documented reasons and evidence.

Do not classify a failed stage as optional merely to achieve certification.

Do not count unit tests as production stage executions.

Do not declare success based only on the parent process exit code.

## 3. Resolve all outstanding India blockers

Complete the following:

- Resolve all five stale backend datasets identified in Phase 3.
- Trace each dataset to its authoritative producer.
- Correct missing producer execution and dependency ordering.
- Complete the full India V2 rerun.
- Verify the same-day recommendation reuse correction in full execution.
- Verify R1 and R2 integration.
- Verify all applicable scoring engines.
- Verify market and sector intelligence.
- Verify feature-store freshness.
- Verify recommendation generation.
- Verify admission decisions.
- Verify stop-loss and target calculations.
- Verify lifecycle transitions.
- Verify authorized exit propagation.
- Verify historical lineage.
- Verify SSOT.
- Verify final reconciliation.
- Verify Research P0 and P1.
- Verify workbook generation.
- Verify all final processing steps.
- Verify publication protection.
- Verify delivery preflight without sending Telegram messages.

Investigate and fix any additional defects discovered during execution.

Do not stop after fixing only the currently known issues.

Continue until the entire India execution contract is satisfied.

## 4. India XLSX — mandatory product quality correction

India cannot be certified until its generated XLSX is accurate, complete, professionally formatted and suitable for daily investment analysis.

Implement all XLSX requirements specified in the previous Phase 4 extension.

Retain the existing two-sheet architecture:

- CURRENT
- EXIT HISTORY

Correct the workbook generation source code rather than manually editing generated files.

### 4.1 Column correctness

Audit every existing column and its authoritative source.

Correct misleading names, incorrect calculations, stale information, missing values, invalid defaults and inconsistent data types.

Ensure the workbook provides accurate information for:

- Stock identity.
- Sector.
- Market capitalization and its as-of date.
- Engine.
- Action.
- Admission status.
- Actionability.
- NEW or RE-ENTRY classification.
- Entry date.
- Days held.
- Entry price.
- Latest price.
- Market data as-of date.
- P&L percentage.
- Confidence.
- Original stop, where available.
- Current stop.
- Stop state.
- Stop distance.
- Return at stop.
- Potential profit giveback.
- Target price.
- Target status.
- Remaining upside.
- Reward-to-risk ratio, where applicable.
- Decision reason.
- Decision freshness.
- Position identity.

Reuse existing columns wherever possible.

Add or rename columns only when necessary to correct information or provide decision-critical clarity.

Update affected downstream readers and validators.

Do not fabricate unavailable information.

### 4.2 Correct target presentation

Phase 3 identified 27 blank India R2 targets caused by suppression of targets already at or below the latest price.

Correct this behavior.

Preserve the authoritative target price.

Clearly distinguish:

- TARGET NOT REACHED.
- TARGET REACHED.
- TARGET EXCEEDED.
- TARGET NOT AVAILABLE.
- TARGET NOT APPLICABLE.

Explain whether the target is advisory or an actual exit trigger.

Do not silently remove achieved targets.

Do not invent replacement targets.

### 4.3 Explain profitable HOLD positions

For every profitable position that remains open, verify the actual production decision.

Where supported by existing evidence, communicate:

- Why the position remains active.
- Whether the target has been achieved.
- Whether the investment thesis remains intact.
- Whether the trend remains intact.
- Whether trailing-stop management is active.
- How much return is protected at the current stop.
- How much accumulated profit could be surrendered before reaching the stop.
- Whether an authorized exit signal exists.

Investigate the actual role of the 60-day and 90-day horizons.

Distinguish mandatory holding periods, maximum holding horizons, prediction horizons and research evaluation windows.

Fix confirmed decision propagation defects.

Do not change the investment strategy without separate approval.

### 4.4 Improve NEW recommendation visibility

Make fresh recommendations easy to identify and evaluate.

Display verified entry price, target, stop, potential upside, downside, reward-to-risk ratio, confidence, recommendation reason and actionability.

Distinguish genuinely new opportunities from re-entry opportunities.

Preserve the existing no-measured-edge and NOT ACTIONABLE warnings where applicable.

Do not generate additional recommendations by weakening admission thresholds.

### 4.5 Restore profit and loss colour coding

The user specifically identified missing P&L colour formatting.

Restore consistent formatting across CURRENT and EXIT HISTORY.

Required formatting:

- Positive P&L: green.
- Negative P&L: red.
- Zero P&L: neutral.
- Positive return at stop: green.
- Negative return at stop: red.
- NEW recommendations: blue.
- ACTIVE+: green.
- HOLD: neutral or existing active styling.
- TARGET REACHED or EXCEEDED: green.
- REVIEW: amber.
- STOP BREACH: red.
- EXIT: red.
- STALE DATA: amber.
- ADVISORY or NOT ACTIONABLE: clearly distinguishable warning styling.

Apply formatting dynamically using actual numeric values and canonical statuses.

Do not hardcode individual stock names.

Ensure formatting survives every workbook regeneration.

### 4.6 Professional workbook usability

Verify and correct:

- Header formatting.
- Column widths.
- Row heights.
- Frozen headers.
- Frozen identity columns where appropriate.
- Auto-filters.
- Numeric cell types.
- Percentage formats.
- INR currency formats.
- Date formats.
- Text wrapping.
- Reason column readability.
- Section hierarchy.
- Alignment.
- Missing-value presentation.
- Conditional formatting.
- Formatting consistency between sheets.

Ensure there are no clipped headers, incorrect percentage scaling, misleading blank cells or unnecessary duplicate columns.

Maintain compatibility with Microsoft Excel on Windows.

## 5. India historical integrity

Reconcile the complete India registry against CURRENT, EXIT HISTORY and durable lineage.

Verify:

- No unexplained disappearing stocks.
- No missing active episodes.
- No duplicate positions.
- No duplicate exits.
- No unauthorized historical price changes.
- No incorrect episode associations.
- No stale GitHub artifacts overwriting newer local state.
- No administrative closures incorrectly counted as trading outcomes.
- No stop-breach marks incorrectly counted as realized exits.

Preserve legitimate retired and advisory records.

Verify the historical performance statistics against their documented populations and formulas.

## 6. India XLSX automated certification

Generate the corrected India workbook in staging.

Reopen the actual generated XLSX and verify every column, row, calculation, record classification and formatting rule.

Test representative cases for:

- Positive P&L.
- Negative P&L.
- Zero P&L.
- NEW recommendation.
- RE-ENTRY recommendation.
- Target reached.
- Target exceeded.
- Missing target.
- Profitable HOLD.
- Stop breach.
- Realized exit.
- Administrative closure.
- Advisory position.
- Stale market data.

Verify that the workbook accurately reflects authoritative production state.

Perform visual inspection where supported.

Produce the corrected staged India XLSX for user review.

## 7. India fresh execution and repeat-run certification

After implementing all corrections:

1. Run all relevant regression tests.
2. Execute the complete India pipeline using fresh market data.
3. Verify every applicable core stage.
4. Verify every final processing step.
5. Verify every required output artifact.
6. Verify all dataset freshness and integrity checks.
7. Verify the generated India workbook.
8. Verify research outputs.
9. Verify delivery preflight.
10. Repeat the complete execution against the same effective market-data dates.
11. Verify repeat-run idempotency.
12. Verify automatic recovery and last-known-good state protection.

A staged execution using old saved inputs is not sufficient for final certification.

An isolated successful test is not sufficient.

A successful workbook generation alone is not sufficient.

Do not promote live production workbooks or send Telegram messages without approval.

## 8. Mandatory India certification report

Before beginning USA remediation, produce a consolidated India certification report containing:

- Exact total core stage count.
- Exact final processing step count.
- Required stage count.
- Optional stage count.
- Successfully executed stage count.
- Validated reuse count.
- Failed stage count.
- Blocked stage count.
- Unexpected skipped stage count.
- Legitimately inapplicable stage count.
- Output artifacts validated.
- Dataset freshness results.
- Price integrity results.
- Lifecycle results.
- Historical lineage results.
- Research results.
- XLSX column correctness results.
- XLSX formatting results.
- Repeat-run results.
- State protection results.
- Delivery preflight results.

Provide a machine-readable stage verification matrix with evidence for every PASS.

Explicitly report:

INDIA CORE PIPELINE: PASS / FAIL / BLOCKED

INDIA FINAL PROCESSING: PASS / FAIL / BLOCKED

INDIA DATA INTEGRITY: PASS / FAIL / BLOCKED

INDIA HISTORICAL INTEGRITY: PASS / FAIL / BLOCKED

INDIA INVESTMENT DECISION CORRECTNESS: PASS / FAIL / BLOCKED

INDIA XLSX DATA CORRECTNESS: PASS / FAIL / BLOCKED

INDIA XLSX FORMATTING: PASS / FAIL / BLOCKED

INDIA RESEARCH: PASS / FAIL / BLOCKED

INDIA REPEAT-RUN SAFETY: PASS / FAIL / BLOCKED

INDIA PRODUCTION READINESS: PASS / FAIL / BLOCKED

INDIA 100% CERTIFIED: YES / NO

India may be declared 100% certified only when all applicable requirements have passed, no unresolved production blockers remain, and all exclusions are explicitly justified.

Do not use approximate completion percentages as a substitute for certification.

## 9. USA — begin only after India certification

Once India is 100% certified, proceed to USA.

Apply the proven India execution, validation, state protection and XLSX quality standards wherever applicable.

Resolve the outstanding USA issues, including:

- Backend dataset validation failures.
- Seven missing scoring symbols.
- Price freshness.
- CNP price-basis integrity.
- USA universe correctness.
- Current research coverage.
- Historical episode preservation.
- All applicable pipeline stages.
- All final processing steps.
- XLSX column accuracy.
- XLSX formatting.
- Repeat-run reliability.

Do not perform destructive universe resets.

Do not weaken validation gates.

Do not introduce regressions into the certified India pipeline.

After USA-specific fixes, rerun relevant India regression and integration checks.

## 10. Final combined certification

Only after India and USA are independently certified, execute the canonical combined local command.

Verify complete execution for both markets, market isolation, historical preservation, workbook correctness, research completeness and publication protection.

Provide the final Windows PowerShell daily execution command.

The final product must support reliable manual daily operation without depending on GitHub Actions.

## 11. Execution directive

Continue actual implementation and testing.

Do not stop at another audit, recommendation, theoretical report or partial fix.

Do not move to USA while India remains incomplete.

If an external dependency genuinely prevents India certification, identify the exact blocker, evidence, attempted remedies and required user action. Do not falsely declare success or silently move to USA.

The immediate objective is:

INDIA FIRST — EVERY STAGE — EVERY OUTPUT — COMPLETE XLSX — 100% CERTIFICATION.

USA SECOND — APPLY THE SAME STANDARD.

COMBINED DAILY EXECUTION LAST.

This priority override supersedes all previous instructions to work on India and USA concurrently.

## **Revised execution roadmap**

## **Phase 4A — India**

Immediate priority

Resolve five stale datasets

Complete full V2 execution

Verify every core stage (\~81, subject to confirmation)

Verify every final step (\~8, subject to confirmation)

Correct XLSX columns and calculations

Restore profit/loss colour formatting

Verify historical integrity

Complete fresh execution and repeat-run tests

Achieve 100% India certification

**Mandatory gate: India 100% certified**

No unresolved production blockers

## **Phase 4B — USA**

Begin only after India passes

Resolve USA-specific issues and apply the same complete certification standards.

## **Phase 4C — Combined certification**

Verify both markets through one reliable daily local command.

## **Expected final India certification**

| Certification area                 | Required result               |
| ---------------------------------- | ----------------------------- |
| Core pipeline stages               | 100% applicable stages passed |
| Final processing steps             | 100% applicable steps passed  |
| Backend datasets                   | All required datasets valid   |
| Unexpected failures                | 0                             |
| Unexplained missing positions      | 0                             |
| Duplicate episodes                 | 0                             |
| Unresolved price integrity defects | 0                             |
| XLSX column correctness            | PASS                          |
| XLSX profit/loss formatting        | PASS                          |
| Investment decision consistency    | PASS                          |
| Research completeness              | PASS                          |
| Fresh execution                    | PASS                          |
| Repeat-run safety                  | PASS                          |
| Publication protection             | PASS                          |

**Do not accept another summary saying India is nearly complete.** We need the actual stage-by-stage execution evidence, corrected India Excel workbook and a definitive certification result.

The remembered 81 stages and eight final steps still need confirmation from the repository. I have deliberately retained that verification requirement rather than assuming those counts are accurate.
