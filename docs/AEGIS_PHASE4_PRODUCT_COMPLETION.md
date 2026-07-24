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
