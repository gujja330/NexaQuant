# AEGIS Documentation Registry
**Stage 0.5 deliverable · Every doc surveyed, summarized, and cross-referenced**

Summaries below are 2-3 sentence distillations by the runtime-audit agent from actually reading each doc's first ~50 lines. Full contents of each doc are the source of truth.

---

## A. Architecture — CURRENT reality documented

| Path | Summary | Reconciliation status |
|---|---|---|
| `docs/AEGIS_ARCHITECTURE.md` | Overall architecture (not fully read) | Presumed authoritative |
| `docs/AEGIS_ARCHITECTURE_REVIEW.pdf` | PDF review doc | Not machine-readable |
| `docs/AEGIS_WHITEPAPER.md` | Marketing/positioning whitepaper | Aspirational |

## B. Architecture — DEV017-020 tier docs (out of sync with code)

⚠️ **All three docs self-declare "DRAFT · design only · NO code · NO production changes" at line ~6, yet the corresponding engines EXIST and RAN once (2026-07-17).**

| Path | Summary | Reconciliation status |
|---|---|---|
| `docs/ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md` | Frames "missing top three tiers" (Global/Macro/Country) above AEGIS's existing Company→Portfolio stack. Dated 2026-07-17. | **OUT OF SYNC** — `research/global_intelligence/` was built and ran the same day |
| `docs/ARCH017A_MARKET_DATA_CANONICAL_MODEL.md` | Schema constitution: 7 design principles (tenant-generic, immutable raw, explicit confidence, traceability, UTC, idempotent, fail-loud). Positions itself as MON001-equivalent for the Market Intelligence Layer. | **OUT OF SYNC** — engines already implemented |
| `docs/ARCH018_SECTOR_INTELLIGENCE_ENGINE.md` | Global→Sector→Industry→Company hierarchy design. Says parameters shown are "v1 draft — not adopted." | **OUT OF SYNC** — sector engine already implemented and ran |

**PRD implication:** treat these three as aspirational spec, not description of current state.

## C. Lifecycle + engineering

| Path | Summary |
|---|---|
| `docs/ARCH001A_INVESTMENT_PHILOSOPHY.md` | 10 Articles, 10 INVARIANT non-negotiables. Objective = fractional-Kelly log-utility with survival + DD constraints. |
| `docs/ARCH001_RECOMMENDATION_LIFECYCLE.md` | Recommendation lifecycle spec |
| `docs/ARCH002_EXIT_FRAMEWORK.md` | Exit-policy framework |
| `docs/DESIGN_DECISIONS.md` | 14 ADRs (Architecture Decision Records) I authored earlier this session |
| `docs/ENGINE_EVOLUTION_GUIDE.md` | How engines evolve v1 → v2 without new DEV numbers |
| `docs/CHANGE_CONTROL_CHECKLIST.md` | Change discipline |
| `docs/ENGINEERING_CHECKLIST.md` | Engineering discipline |

## D. Governance / ops

| Path | Summary |
|---|---|
| `AEGIS_CONSTITUTION.md` (root, I wrote earlier) | India v2.0 Constitution — 13 locked orchestrator steps, allowed/forbidden change categories, 5-question test, amendment protocol |
| `usa/AEGIS_USA_CONSTITUTION.md` (I wrote earlier) | USA v1.0 Constitution — same shape, USD invariant |
| `docs/DEPLOYMENT.md`, `docs/DEPLOYMENT_GUIDE.md` | Deploy docs |
| `docs/DAILY_OPERATIONS.md` | Daily ops runbook |
| `docs/HOW_TO_RUN_PIPELINE.md` (I wrote earlier) | One-command runbook + Telegram wiring |
| `usa/docs/HOW_TO_RUN_USA.md` (I wrote earlier) | USA runbook |

## E. ENG reports (build sprint records)

| Path | Summary |
|---|---|
| `docs/ENG001_REPORT.md` | Governance sprint |
| `docs/ENG002_REPORT.md` | Follow-up governance |
| `docs/ENG003_REPORT.md` | Continuation |
| `docs/ENG004_CI_ROOTCAUSE.md` | CI root-cause analysis |

## F. Research + strategy — THE AUTHORITATIVE EVIDENCE LEDGER

⚠️ **These are the docs that describe what the strategy actually is + why.**

| Path | Summary | Key finding |
|---|---|---|
| `docs/ARJUNA_ALPHA_MASTER.md` | Canonical evidence ledger. Portfolio-probability optimization (not stock-picking) as objective. Full validation gate: walk-forward, purged CV, embargo, Deflated Sharpe, PBO, SPA, White RC. | **"Confirmed":** risk predictability (vol AUC 0.76, drawdown 0.62), HRP+regime+Global-Risk (Sharpe 2.04). **"Rejected":** HMM regime (Sharpe 1.06 vs 1.64), 7-feature ML on 300 holdings (AUC 0.47). |
| `docs/ARJUNA_V2_ARCHITECTURE.md` | AEGIS v2 is NOT AI stock-selection — it's risk-allocation/regime-management. Validated champion: HRP + regime + Global Risk (Sharpe 2.04, maxDD 12.8%, DSR 0.996). | Live config `method=hrp, regime=global` — matches `india/recommendation_generator.py:44`. |
| `docs/ARJUNA_V4_ROADMAP.md` | AI: Temporarily Closed, Reopens on Data. Not rejected outright but starved of features. Sets `MODELS_FROZEN_UNTIL_DATA_ARRIVES = True` in `india/config.py`. | Unfreeze requires: point-in-time fundamentals, news archive, analyst revisions, alt data. `india/ai_reopen.py` is the trigger check. |
| `docs/AI_ML_REFINEMENT_PLAN.md` | Self-correction of earlier "AI doesn't help" claim. The actual finding: 7 price-only features on 300 holdings has no skill (AUC 0.47), not that AI fails inherently. | Refinement roadmap: rich features → broad data → cross-sectional-rank framing → GBT+NN ensemble → rigorous validation. Sequenced behind data-arrival milestones. |
| `docs/FEATURE_REGISTRY.md` | Feature/signal inventory with PIT / quality / live / tested / promoted status. | **Only PROMOTED (India):** vol/risk rank, HRP, regime exposure, dynamic universe. Momentum/RSI/RS = "tested (no lift)." SEC fundamentals, earnings, insider, ETF flows, 13F, FRED, news = **"Planned"** for USA. |
| `docs/AEGIS_RESEARCH_AGENDA_2035.md` | Long-range research roadmap |
| `docs/AEGIS_RESEARCH_HANDBOOK.md` | Research methodology |
| `docs/AI_MODELS_VALIDATION.md` | ML validation methodology |
| `docs/FUTURE_RESEARCH_ROADMAP.md` | Sequenced research plan |
| `docs/DATASET_SHORTLIST.md` | Prioritized data sources |
| `docs/ARJUNA_AI_STRATEGY.md`, `ARJUNA_ALPHA_DATA_RESEARCH.md`, `ARJUNA_BUILD_STAGES.md`, `ARJUNA_DEEP_RESEARCH_ML.md`, `ARJUNA_OPERATING.md`, `ARJUNA_PRODUCT_ROADMAP.md`, `ARJUNA_RESULTS.md`, `ARJUNA_STRATEGY_DECISION.md`, `ARJUNA_v2_Architecture.pdf` | Full ARJUNA strategy family — the intellectual core of what AEGIS actually is | Reading order: STRATEGY_DECISION → V2 → ALPHA_MASTER → V4_ROADMAP → AI_STRATEGY → RESULTS |

## G. Session logs (audit trail)

| Path | Purpose |
|---|---|
| `docs/chat_transcript_2026-07-13.md` | Earlier session |
| `docs/chat_transcript_2026-07-18.md` | Session that culminated in AEGIS v2.0 FREEZE (I wrote this) |

## H. Executive materials

| Path | Purpose |
|---|---|
| `docs/AEGIS_EXECUTIVE_REPORT.html` | Executive-facing summary |
| `Executive Summary.pdf` (root) | Institutional exit/risk-control PDF, 11 pages |
| `Executive Summary_1.pdf` (root) | Untracked variant |

---

## Docs I have NOT read

Every doc above was surfaced by grep or the audit agent's summary — but the FULL contents of most are not yet consumed. Before Stage 1 PRD work, at minimum I should read:

1. `docs/ARJUNA_ALPHA_MASTER.md` (full) — the evidence ledger
2. `docs/ARJUNA_V2_ARCHITECTURE.md` (full) — what AEGIS actually is
3. `docs/ARJUNA_V4_ROADMAP.md` (full) — the ML re-activation gate
4. `docs/ARCH001A_INVESTMENT_PHILOSOPHY.md` (full) — the 10 non-negotiables
5. `docs/FEATURE_REGISTRY.md` (full) — the ground-truth feature inventory
6. `docs/ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md`, `ARCH017A_MARKET_DATA_CANONICAL_MODEL.md`, `ARCH018_SECTOR_INTELLIGENCE_ENGINE.md` (full) — even though out-of-sync, they contain the design intent for the intelligence tiers
7. `docs/DESIGN_DECISIONS.md` (full) — 14 ADRs
8. `docs/AI_ML_REFINEMENT_PLAN.md` (full)

Reading these should be a prerequisite for Stage 1 PRD authoring.

## I. Doc dead code / stale

| Doc | Why stale |
|---|---|
| ARCH017 / ARCH017A / ARCH018 self-declared "no code" but code exists | Reconcile |
| Many ENG*_REPORT.md are point-in-time sprint records | Retain as history |
| `docs/AEGIS_ARCHITECTURE_REVIEW.pdf` | I generated this via reportlab in earlier session |
| Any doc claiming AEGIS is "AI Investment Intelligence Platform" | Currently accurate as intent; runtime is technicals + HRP + regime |
