# AEGIS Changelog

All notable changes to the AEGIS platform.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

---

## [v2.1.0-RC1] — 2026-07-18

**Phase 2 Release Candidate 1.**

The platform is complete as a research operator's workbench. Every
engine on the [PHASE2_MASTER_ROADMAP.md](docs/PHASE2_MASTER_ROADMAP.md)
critical path (P0-P8) is shipped. Institutional multi-tenant deployment
still requires the 6 blockers documented in
[docs/PHASE2_PRODUCTION_AUDIT.md](docs/PHASE2_PRODUCTION_AUDIT.md) §6.

### Added

**Decision Center v1.0** (`6355a0f`)
- Overnight diff engine: NEW · UPGRADED · DOWNGRADED · TARGET_HIT ·
  STOP_HIT · INTELLIGENCE_UP/DOWN · CONFIDENCE_UP/DOWN · NEW_HELD ·
  EXITED · SIZING_WARNING
- Human-readable overnight paragraph (deterministic, no LLM)
- Exit center — held positions ranked by severity with stacked reasons
- Watchlist — near-buy candidates with trend indicator
- Priority-tiered notifications (CRITICAL · HIGH · MEDIUM · LOW)
- Dashboard integration as first section

**Dashboard v2.0** (`8e20b2b`)
- Rewrote 11-page engineering console into 2-page investor-first surface
- Canonical recommendation table with CMP · Buy Below · Target · Stop ·
  Upside · Risk:Reward · Hold days · Intelligence · Confidence · Action
- Stock Detail drill-down with 10-dimension Why-Buy chip grid
- Sizing counterfactuals ("why not 4%? why not 12%?")
- Global search · realtime 60s auto-refresh · pipeline status indicator
- Zero DEV-module references in user-facing UI

**Daily Orchestrator v1.0** (`f635f5b`)
- `scripts/aegis_daily_v2.py` — runs every Phase 2 v2 engine in
  dependency order in ~30-40s
- Per-step verdict + artifact-refresh check
- Append-only history at `reports/aegis_daily_v2_history.jsonl`
- Wired into GitHub Actions after the base pipeline

**Adaptive Rec Engine v2.1 Intelligence Fusion** (`f29b1b8`)
- 10 dimension scorers with configurable weights + graceful degradation
- Deterministic decision mapping (85+ Strong-Buy · 70+ Buy · etc.)
- 9-rule conflict detector (CRITICAL · MEDIUM · MINOR)
- Per-recommendation explainability panel (Why this? · Why not stronger?)
- Weights editable via `reports/fusion_weights.json`

**Adaptive Rec Engine v2.0 Confidence Rebuild** (`1d9fdf8`)
- Feature-importance model replacing raw confidence heuristic
- HGB Precision@10 = 0.80 vs baseline 0.60 (+20pp)
- Permutation importance from live data: volatility · score · drawdown · momentum

**Validation Engine v2.0 Paper Harness** (`a04a5da`)
- Content-addressed paper-trading ledger
- Expected-vs-actual reconciliation
- Metric drift + rolling edge detection
- Opportunity cost tracking

**Risk & Capital Engine v2.0** (`80e590f`)
- Position sizing with 4 bounded factors + counterfactuals
- VaR / CVaR / variance decomposition
- Per-position + per-sector budget attribution

**Knowledge Graph v1.6 Stress Propagation** (`8c7d96d`)
- 5 canonical stress scenarios via personalized PageRank
- Portfolio-exposure overlay per scenario
- Champion-strategy-failure caught 96.5% portfolio exposure risk

**DNA Feedback Loop v1.5** (`a0df1a2`)
- Closes ADR-009 latent value
- 84 discovered patterns with historical win rate + expectancy
- Per-current-rec priors from historical DNA

**UX030 Telegram Sender (opt-in)** (`e0027ac`)
- Standalone 5-message rich delivery
- Env parity with sealed sender
- Parallel delivery ledger

**Governance Suite** (`d2d5a9b · 6559476 · 6322e75`)
- ENGINE_EVOLUTION_GUIDE.md (constitution)
- DESIGN_DECISIONS.md (14 ADRs)
- PHASE2_MASTER_ROADMAP.md (delivery contract)
- NEXAQUANT_MANIFESTO.md (mission + principles)
- AEGIS_RESEARCH_AGENDA_2035.md (5-10 year backlog)

**Documentation** (this release)
- HOWTO_RUN_AEGIS.md · 3-step operator guide
- DAILY_OPERATIONS.md · deep operational reference
- PHASE2_PRODUCTION_AUDIT.md · this release audit
- RELEASE_NOTES_RC1.md · release notes
- VERSION.md · version manifest
- CHANGELOG.md · this file

### Changed

- Dashboard auto-refresh interval defaults to ON, 60s cadence.
- Daily scheduler restored to ~06:00 IST morning cadence (was moved
  to post-close during OPS001-F).
- Telegram sender remains on the sealed retry wrapper for production;
  UX030 renderer is opt-in only.

### Fixed

- `MON001 dashboard MARKET_CLOSED payload` (`3e17682`) — build_dashboard()
  now uses `.get()` defaults for partial payloads; regression fixed.

### Removed

- **Nothing removed.** Historical DEV017-DEV031 modules preserved as
  frozen milestones per ADR-003.

### Governance invariants unchanged

- Fingerprint: `e4c070673568c52d…` (MON001 sealed baseline)
- Production constants: HOLD=63 · rebal=63 · sector_cap=2 · name_cap=0.30 · method=hrp
- Cumulative strategy search: 38 (unchanged)
- MON001 forward_boundary_asof: 2026-03-28 (unchanged)
- Sealed + LAB files: 0 touched

### Test posture

- Full regression suite PASSES on `main`.
- 190+ Phase 2 module smoke tests pass across:
  - Adaptive Rec v2.0/v2.1 · Validation v2.0 · Risk & Capital v2.0
  - Knowledge Graph (26 tests) · DNA Feedback · Decision Center
  - Executive Dashboard spec · Telegram UX030
- End-to-end test script: `scripts/e2e_test.py`

---

## Historical milestones (frozen)

### DEV031-B — Knowledge Graph completion — Sprint 16 late
Communities · propagation · explainability paths · timeline snapshots.

### DEV030 — Champion vs Challenger Framework — Sprint 15
9-metric composite · 4-gate promotion recommender.

### DEV029 — Confidence Calibration — Sprint 15
5 calibration methods competed; Platt selected. ECE 0.287 → 0.002.

### DEV028 — Recommendation DNA — Sprint 14
208 immutable content-keyed records.

### DEV027 — Strategy Doctor — Sprint 14
15 diagnostic rules · 677 diagnoses fired · 218 overconfidence
(independently confirmed the calibration finding).

### DEV026 — AI Research Assistant — Sprint 13
Deterministic Q&A · 6 templates.

### DEV025 — Adaptive Learning — Sprint 13
1,060 trades analysed · ECE 0.29 flagged.

### DEV017-DEV024 — Phase 1 Foundation — Sprints 1-12
Research Intelligence (Global · Sector · Industry · Company) ·
Historical Validation · Portfolio Construction · Recommendation Engine ·
Portfolio Monitoring.

### OPS001 — Production sealed baseline
Fingerprint `e4c070673568c52d…` — INVARIANT.

---

## [Older releases]

Prior daily automated commits under `[skip ci]` are omitted from this
changelog. Consult `git log --oneline` for the full history.
