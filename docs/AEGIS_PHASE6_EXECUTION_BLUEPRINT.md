# AEGIS Phase 6 · Repository Execution Blueprint
### PARALLEL DEVELOPMENT EXECUTION PLAN · 🔒 LOCKED 2026-07-24

**The Four-Pillar Roadmap:**
- [Phase 3 · FROZEN](AEGIS_PHASE3_MASTER_ROADMAP.md) — WHAT to build (18 engine sprints)
- [Phase 4 · LOCKED](AEGIS_PHASE4_PRODUCT_COMPLETION.md) — WHICH modules ship (20 product modules)
- [Phase 5 · LOCKED](AEGIS_PHASE5_DEVELOPMENT_STANDARDS.md) — HOW to build (10 contracts)
- **Phase 6 · THIS DOC — WHO owns what + WHEN it runs (parallel execution)**

Architecture is frozen. Product scope is frozen. Development standards are frozen. **This document defines HOW the repository is executed until AEGIS reaches production.**

- No future sprint should decide where code belongs.
- No future sprint should decide ownership.
- Everything is already allocated.

---

## Objective

Convert the roadmap into executable work packages. Every folder · every module · every dependency · every output · every test · every API · every dashboard — allocated, tracked, parallel-schedulable.

---

## Terminology Note (real repo context)

The spec below uses the word "**team**" as a work-stream label. In this single-operator context that means "**parallel work stream Claude can execute independently**" — not literal human teams. The ownership map is the same regardless: each stream owns defined deliverables · no overlap · streams can run in parallel.

---

## Repository Execution Map (ownership)

```
backend/     · shared engine framework  (Backend stream)
india/       · India-market runtime      (India stream)
usa/         · USA-market runtime        (USA stream)
research/    · legacy research engines   (SEALED — do not touch except via consumers)
configs/     · operator-owned config     (Backend stream owns loaders · operator owns values)
reports/     · runtime outputs           (owned by producing engine's stream + Reports stream for cadence rollups)
tests/       · cross-cutting integration (Test stream)
docs/        · specs · sprint reports    (Documentation stream)
frontend/    · dashboard code            (Frontend stream)
api/         · REST layer                (API stream · Phase 4 Module 18 delivers)
scripts/     · orchestrators             (Backend + market streams jointly)
```

**Each folder owns defined deliverables. Nothing overlaps.**

---

## Ownership by Stream

### Backend Stream (`backend/`)

Canonical · Market · Macro · Features · Models · Recommendation · Risk · Portfolio · Execution · Replay · Walk Forward · Benchmark · Trade State · Trade Lifecycle · Operator · Learning · Research Factory · Analytics · Comparison · Persistence · Logging · Metrics · Utilities

### India Stream (`india/`)

Market Adapter · Execution · Reports · Replay · Dashboard · Daily Jobs · Telegram · APIs · Tests · Outputs

### USA Stream (`usa/`)

Market Adapter · Execution · Reports · Replay · Dashboard · Daily Jobs · APIs · Tests · Outputs

### Frontend Stream (`frontend/` · currently `ux/dashboard/frontend/` + `usa/dashboard/frontend/`)

Dashboard · Operator · Research · Portfolio · Risk · Replay · Trade Lifecycle · Analytics · Reports · Administration · Settings

### API Stream (`api/` · Phase 4 Module 18 delivers)

Authentication · Market API · Research API · Portfolio API · Replay API · Recommendation API · Trade API · Analytics API · Reporting API · Administration API · Health API · Swagger · OpenAPI

### Data Stream (spans `data/`, `backend/canonical/`, `backend/persistence/`)

Canonical Data · History · Market Data · Macro Data · Corporate Actions · Replay Data · Learning Data · Metadata · Schemas · Validation

### Reporting Stream (`reports/` cadence rollups · Phase 4 Module 17)

Daily · Weekly · Monthly · Quarterly · Annual · PDF · Excel · Markdown · JSON

### Analytics Stream (`backend/analytics/` + `reports/analytics/` · Phase 4 Module 16)

Performance · Portfolio · Trade · Recommendation · Risk · Market · Research · Learning · Cross Market

### Documentation Stream (`docs/`)

Architecture · Development · Deployment · Configuration · Operator · API · Developer · Replay · Walk Forward · Research · User · Administration

### Test Stream (`tests/` + `backend/tests/` + `nexaquant/tests/` + per-engine tests)

Unit · Integration · Regression · Replay · Walk Forward · Performance · Load · Stress · API · Dashboard · India · USA · Cross Market

### CI/CD Stream (`.github/workflows/`)

Formatting · Lint · Tests · Replay Validation · Walk Forward Validation · Documentation Validation · API Validation · Packaging · Deployment · Versioning · Release Notes

---

## Execution Waves (dependency-ordered)

Waves execute in order; sprints WITHIN a wave can run in parallel where the Phase 3 sequencing allows.

| Wave | Sprints | Dependency |
|:---:|---|---|
| **1** | Repository Intelligence | A1 · A2 |
| **2** | Historical Intelligence | B0 · B1 · B2 · B3 |
| **3** | Trade Intelligence | C1 · C2 · C3 · C4 · C5 |
| **4** | Operator Intelligence | D1 · D2 · D3 |
| **5** | Operator Experience | E1 · E2 · E3 |
| **6** | Portfolio Intelligence | F1 · F2 |
| **7** | Research Intelligence | G1 |
| **8** | Phase 4 Product Modules | Modules 1 → 20 |

**Cross-wave rule:** engine-work Phase 4 modules (3 Screening · 4 Watchlist · 11 Backtesting · 12 Strategy · 17 Reporting · 18 API · 19 Admin) are Phase-3-independent — they can execute in parallel to Waves 3-7 in dedicated stream slots.

---

## Parallel Streams (simultaneous execution)

```
Stream A · Backend        (shared framework)
Stream B · India          (India-market runtime)
Stream C · USA            (USA-market runtime)
Stream D · Frontend       (dashboard code)
Stream E · API            (REST layer)
Stream F · Documentation  (docs/*)
Stream G · Reports        (cadence rollups)
Stream H · Testing        (all test types)
Stream I · Analytics      (cross-cutting metrics)
```

**All streams operate simultaneously.** A sprint may spawn work across multiple streams — the sprint plan itemises which streams contribute what, and each stream's contribution is a mergeable unit.

---

## Sprint Execution Template (every sprint follows this)

```
Planning
     ↓
Implementation
     ↓
India adapter                    ┐
     ↓                            │  parallel where possible
USA adapter                       ┘
     ↓
Replay          (both markets)
     ↓
Walk Forward    (both markets · where applicable)
     ↓
Benchmark
     ↓
Analytics
     ↓
Reports
     ↓
API endpoint added
     ↓
Dashboard tile added
     ↓
Testing         (9 types from Phase 5 Test Contract)
     ↓
Documentation   (9 types from Phase 5 Doc Contract)
     ↓
Merge           (only if merge rules pass)
     ↓
Production      (deployed to daily-pipeline hook)
```

---

## Merge Rules (LOCKED · block PR merge)

**No merge if ANY of these fail:**

- Replay fails (India OR USA)
- Walk Forward fails (India OR USA · where applicable)
- Regression fails (`nexaquant/tests/test_regression.py` OR any `backend/tests/test_sprint*.py`)
- India tests fail
- USA tests fail
- Documentation missing
- API endpoint missing (once API Center lands · Wave 8 Module 18)
- Dashboard tile missing
- Reports missing
- Global comparison artifact (`reports/global/<engine>_comparison.json`) missing

Enforced by CI on push and by developer discipline (Phase 5 pre-push sweep) on local.

---

## Definition of Done (single source of truth)

A sprint is DONE when ALL of these are true:

- [ ] Code (per Phase 5 Engine Standard)
- [ ] Tests (all 9 types per Phase 5 Test Contract)
- [ ] Replay (both markets)
- [ ] Walk Forward (both markets · where applicable)
- [ ] Documentation (all 9 types per Phase 5 Doc Contract)
- [ ] Dashboard tile / view
- [ ] API endpoint (once API Center lands)
- [ ] Reports (daily minimum · other cadences per Reporting Center)
- [ ] Analytics metrics emitted
- [ ] Global comparison artifact
- [ ] Performance metrics emitted
- [ ] Version bumped
- [ ] Release notes entry
- [ ] Production ready (or explicitly deferred with reason)

**Missing any = NOT DONE. No exceptions. No partial credit.**

---

## Reality-Reconciliation Notes (what exists · what's aspirational)

Phase 6 defines the target execution model. Some streams don't yet exist as separate concerns:

| Stream | Current state | Grandfathering per Phase 5 |
|---|---|---|
| Backend | Exists · organised by engine subdir | Existing engines partial-compliant; new engines full-compliant |
| India | Exists · runners at `india/<engine>/run.py` | Existing runners lack `config.py/market_adapter.py/report_writer.py` separation — added when touched |
| USA | Exists · at `usa/research/<engine>/` | Same as India |
| Frontend | Exists · `ux/dashboard/frontend/` (India) + `usa/dashboard/frontend/` (USA) as static SPAs | Wave 8 Modules 15/20 evolve into unified surface |
| API | Does NOT exist | Wave 8 Module 18 delivers |
| Data | Exists · `data/`, `backend/canonical/`, `backend/persistence/` | Corporate Actions engine is the parallel data-layer track per Phase 3 B0 |
| Reporting | Ad-hoc `docs/AEGIS_*_REPORT.md` sprint reports · no cadence rollups | Wave 8 Module 17 delivers |
| Analytics | Individual reports produce their own metrics · no aggregation | Wave 8 Module 16 delivers |
| Documentation | Present · `docs/*.md` per sprint | Standard 9-doc structure applied per new module |
| Test | Present · `backend/tests/test_sprint*.py` + `nexaquant/tests/` | Grows per new sprint |
| CI/CD | `.github/workflows/aegis-ci.yml` + `aegis-daily.yml` + `aegis-usa.yml` etc. | Extended per new sprint |

**Nothing existing gets refactored purely for cosmetic conformance — that's a dedicated hygiene sprint after Phase 3 + Phase 4 ship (per Phase 5 grandfathering rule).**

---

## Final Objective

At completion AEGIS becomes:

- ✔ Institutional Investment Platform
- ✔ India + USA (dual-market parallel per sprint)
- ✔ Historical Replay
- ✔ Walk Forward
- ✔ Institutional Research
- ✔ Portfolio Intelligence
- ✔ Trade Lifecycle
- ✔ Operator Intelligence
- ✔ Analytics
- ✔ Reporting
- ✔ APIs
- ✔ Administration
- ✔ Production Ready

**No further architectural work should be required after this execution blueprint.** From this point on: implementation only. Any new architectural proposal requires explicit operator override in writing.

---

## Governance for This Document

- **LOCKED 2026-07-24** by operator directive.
- Fourth pillar of the roadmap authority (alongside Phase 3 · Phase 4 · Phase 5).
- Any deviation requires a docs-only amendment PR + operator approval BEFORE implementation.
- Every sprint report must reference this document + confirm the sprint's stream + wave + DoD status.

---

**End of Phase 6 · Repository Execution Blueprint · LOCKED 2026-07-24**
