# AEGIS Phase 5 · Institutional Development Standards
### MASTER IMPLEMENTATION SPECIFICATION · 🔒 LOCKED 2026-07-24

**Purpose:** This document defines HOW every future sprint is implemented.

This is NOT architecture (see [Phase 3 · FROZEN](AEGIS_PHASE3_MASTER_ROADMAP.md)).
This is NOT product planning (see [Phase 4 · LOCKED](AEGIS_PHASE4_PRODUCT_COMPLETION.md)).
This is the **implementation contract** for the entire repository.

No sprint may violate this document. Developers no longer decide architecture — they only implement.

---

## Objective

Transform AEGIS into an institutional-grade software product where every future implementation follows the same standards. Eliminate architectural decision-making during development. Maximise implementation speed while maintaining institutional quality.

---

## Global Repository Structure (LOCKED)

```
backend/         · shared engine code · framework
india/           · India-market adapters + runners
usa/             · USA-market adapters + runners (currently under usa/research/*)
reports/         · runtime outputs (per-market + global/)
configs/         · operator-owned config
research/        · legacy research engines (adaptive_rec_v2, risk_capital_v2 — SEALED)
tests/           · cross-cutting integration tests (per-engine tests live in engine dir)
docs/            · specs, roadmaps, sprint reports
scripts/         · orchestrators, one-shot utilities
api/             · REST API layer (planned · Phase 4 Module 18)
frontend/        · dashboard code (existing under ux/dashboard/frontend + usa/dashboard/frontend)
```

Every future feature must fit into this structure. No random folders. No duplicated code.

**Compat note:** `usa/research/<engine>/` is the current convention (not `usa/<engine>/`) because USA sits under `usa/research/` historically. Phase 5 spec says "USA Implementation → `usa/research/<engine>/`" — treat as literal.

---

## Engine Implementation Standard

Every NEW engine must contain:

```
backend/<engine>/
    __init__.py         public API + version constants
    engine.py           the main engine class
    models.py           dataclasses / enums / value objects
    repository.py       read/write against parquet/json/config
    service.py          orchestration between engine + repository
    validators.py       input + output validators
    persistence.py      append-only history writer
    comparison.py       cross-market comparison helper
    metrics.py          performance + institutional metrics computation
    exceptions.py       engine-specific exceptions
    config.py           config loader + typed config object
    utils.py            pure helpers
    tests/              unit + integration tests colocated with engine
```

**Engine must never exceed its responsibility.** Cross-cutting concerns (logging, metrics collection, comparison) live in dedicated modules within the engine folder.

**Grandfathering rule (existing engines):** engines that already exist in the repo (Sprint 1 → Sprint 7.8 · about 15+ engines) are NOT retroactively refactored to match this layout wholesale. When an existing engine gets touched by a future sprint, that sprint brings it into partial compliance (adds missing files as needed). Full retrofit is scheduled as a dedicated hygiene sprint AFTER Phase 3 + Phase 4 ship. Rationale: preserves the daily pipeline (sealed OPS001/MON001, fingerprint `e4c070673568c52d…`).

---

## India Implementation Standard

```
india/<engine>/
    run.py              CLI entry point + daily-orchestrator hook
    config.py           India-specific config binding
    market_adapter.py   India profile · price file paths · currency INR
    report_writer.py    India output writers → reports/india/<engine>/
    tests/              India-adapter tests
```

**Compat note:** existing India runners live at `india/<engine>/run.py` but many do NOT yet have separate `config.py` / `market_adapter.py` / `report_writer.py`. Same grandfathering rule as above.

---

## USA Implementation Standard

```
usa/research/<engine>/
    run.py              CLI entry point + USA-orchestrator hook
    config.py           USA-specific config binding
    market_adapter.py   USA profile · price file paths · currency USD
    report_writer.py    USA output writers → usa/reports/<engine>/
    tests/              USA-adapter tests
```

---

## Global Implementation Standard

```
reports/global/
    <engine>_comparison.json
    <engine>_comparison.parquet
    <engine>_comparison.md
```

Every engine · every sprint · no exceptions. This is the substrate for cross-market learning (see [Phase 3 dual-market rule](AEGIS_PHASE3_MASTER_ROADMAP.md#hard-rule--dual-market-parallel-development-added-2026-07-24)).

---

## Implementation Pipeline (locked · every sprint)

```
Shared Engine   →   India Adapter   →   USA Adapter   →   Replay   →   Walk Forward
     ↓                                                                         ↓
Benchmark   →   Comparison   →   Dashboard   →   Reports   →   API   →   Tests   →   Production
```

Missing any link = sprint NOT COMPLETE.

---

## Engine Contract (LOCKED · no custom naming)

Every engine class exposes these public methods:

```python
class Engine:
    def load(self)          -> None:   ...    # load inputs from repository
    def validate(self)      -> None:   ...    # validate inputs before run
    def run(self, *, asof)  -> Result: ...    # deterministic per-asof execution
    def benchmark(self)     -> dict:   ...    # institutional metrics
    def replay(self, *, date_from, date_to) -> None: ...   # historical replay
    def walk_forward(self)  -> dict:   ...    # walk-forward validation
    def compare(self, other_market: "Engine") -> dict: ...  # cross-market
    def export(self, format: str) -> bytes: ...  # json/parquet/md/pdf/excel
    def report(self, cadence: str) -> str: ...   # daily/weekly/monthly/quarterly/annual
```

**Compat note:** existing engines already expose `run(asof=...)` (verified in Sprint 7.7 · every engine class already accepts an `asof` parameter). Other methods (`benchmark`, `replay`, `walk_forward`, `compare`, `export`, `report`) currently live at the runner level or in separate modules (`backend/replay/`, `backend/benchmark/`, `backend/statistics/`). Phase 5 mandates surfacing these on the engine class itself for NEW engines. Existing engines conform when touched.

---

## Configuration Contract (LOCKED)

```
configs/
    india.yaml          India-wide config (currency, timezone, benchmark, thresholds)
    usa.yaml            USA-wide config (currency, timezone, benchmark, thresholds)
    global.yaml         cross-market config (dual-market rules, comparison thresholds)
    <engine>_config.yaml   engine-specific config (already established convention)
```

**Every threshold configurable. No hardcoding.** Enforcement pattern: engines load their config via `config.py` at instantiation; no bare literal thresholds in engine code.

**Compat note:** existing `configs/` has `base_config.yaml` + per-engine yamls (`macro_intel_config.yaml`, `execution_config.yaml`, `learning_config.yaml`, `portfolio_config.yaml`, `risk_budget.yaml`, `factor_library_config.yaml`, `trade_state_config.yaml` planned). Phase 5 adds explicit `india.yaml` + `usa.yaml` + `global.yaml` as market-wide config surfaces (currently market-config is embedded in each engine yaml under `market_defaults:`). These new files land when a sprint needs them; not a bulk-migration.

---

## Output Contract (LOCKED · every engine produces ALL of these)

```
JSON                today's snapshot
Parquet             today's snapshot as columnar
Markdown Summary    human-readable summary
Comparison JSON     cross-market comparison (reports/global/)
Metrics JSON        institutional metrics
Logs                execution log
History             append-only history parquet
```

**No engine produces only one file.**

**Compat note:** existing engines mostly produce JSON only. Markdown/parquet snapshots + explicit Metrics JSON are added when engines are next touched.

---

## Database Contract (LOCKED)

Every engine stores:

```
History             append-only over time
Current Snapshot    latest state
Metrics             per-run institutional metrics
Statistics          rolling stats
Comparison          cross-market artefacts
Timeline            historical view
```

**Append only. Replay safe.** This is already enforced by Sprint 7.5's `backend/persistence/history_writer.py` — every new engine uses that utility.

---

## API Contract (LOCKED · Phase 4 Module 18 delivers)

Every engine automatically exposes:

```
GET  /current
GET  /history
GET  /metrics
GET  /replay
GET  /compare
GET  /export
```

**No custom APIs.** Standard shape across all engines.

**Compat note:** API layer does not yet exist (Phase 4 Module 18 · ⚙ engine work). Once the API framework lands (probably FastAPI), every engine's routes are generated from its `Engine` class methods above — one class = one route bundle, zero per-engine glue.

---

## Dashboard Contract (LOCKED)

Every module automatically appears on dashboard, showing:

```
India       ·  USA       ·  Global
History     ·  Metrics   ·  Comparison   ·  Timeline
```

**Compat note:** dashboards currently live at `ux/dashboard/frontend/` (India) and `usa/dashboard/frontend/` (USA) as static SPAs consuming JSON. Phase 4 Module 15 (Operator Center) + Module 20 (Cross-Market Intelligence) evolve these into the unified surface Phase 5 mandates.

---

## Report Contract (LOCKED · Phase 4 Module 17 delivers)

Every module generates:

```
Cadence:  Daily · Weekly · Monthly · Quarterly · Annual
Format:   PDF · Excel · Markdown · JSON
```

**Compat note:** Reporting Center (Module 17) is engine work · not yet started. Until then, engines produce daily JSON + markdown summaries; Reporting Center will roll them into PDF/Excel at the cadences above.

---

## Test Contract (LOCKED · every sprint · no exceptions)

```
Unit Tests
Integration Tests
Regression Tests
Replay Tests
Walk Forward Tests
Performance Tests
Comparison Tests
India Tests
USA Tests
```

**No sprint complete until all pass.**

**Pre-push discipline (learned from 2026-07-24 incident):**

Before ANY push touching CI-tracked code, developer MUST run locally and confirm 100% green:

```bash
python nexaquant/tests/test_regression.py            # ENG001 + OPS001-I + invariance guards
python backend/tests/test_sprint75.py                # persistence + factor library
python backend/tests/test_sprint76.py                # historical backfill + replay
python backend/tests/test_sprint77.py                # full replay + walk-forward + lookahead guard
python backend/tests/test_sprint77_runner1.py        # Runner 1 legacy audit-trail
python backend/tests/test_sprint78.py                # recommendation benchmark
python backend/tests/test_telegram_notify_fallback.py
# + any newly-added test suite from the current sprint
```

If ANY suite fails locally, the push does not happen. This rule is enforced by developer discipline; there is no server-side hook to short-circuit CI.

---

## Logging Contract (LOCKED)

Every engine logs:

```
Start           timestamp + inputs summary
Finish          timestamp + outputs summary
Execution Time  wall-clock seconds
Inputs          input file paths + row counts
Outputs         output file paths + row counts
Warnings        anything non-fatal but noteworthy
Errors          anything fatal (with traceback)
Statistics      any engine-specific stats
```

Standard log format across all engines. Stdout-friendly for CI consumption.

---

## Performance Contract (LOCKED)

Every engine emits (in metrics JSON):

```
Execution Time
Memory (peak)
CPU (peak)
Cache (hit/miss rate if applicable)
Report Size (bytes)
History Size (rows + bytes)
Comparison Size (bytes)
```

Everything measurable. Feeds Analytics Center (Phase 4 Module 16).

---

## Quality Contract (LOCKED · zero-tolerance)

- **No TODO** — resolve before merge or file a follow-up ticket
- **No FIXME** — same
- **No placeholder implementations** — either fully implemented or explicitly deferred with an operator-visible flag
- **No mock implementation** — real code paths only in production
- **No dead code** — remove or archive to `docs/history/`
- **No duplicated logic** — extract to shared helper
- **No commented production code** — delete it; git history preserves what was there

**Enforcement:** grep-based CI check on future sprints (planned lightweight step in `aegis-ci.yml`).

---

## Documentation Contract (LOCKED · every module)

Every module must include:

```
README             (module overview + quick start)
Architecture       (how it fits, dependencies)
API                (public methods + REST endpoints)
Outputs            (files produced + shapes)
Configuration     (config file shape + operator-adjustable knobs)
Replay Guide      (how to run historically)
Walk Forward Guide (how to validate)
Developer Guide   (extending the engine)
User Guide        (operator-facing)
```

Location convention: `docs/<module>/*.md` or `backend/<engine>/README.md` for engine-specific docs.

---

## Cross-Market Contract (LOCKED)

Every engine automatically produces:

```
India value
USA value
Global comparison
Statistical Difference
Best Market
Worst Market
Learning Candidate
```

"Learning Candidate" = strategy/factor/lifecycle behaviour that appears to work better in one market than the other. Feeds Cross-Market Intelligence (Phase 4 Module 20) and Research Factory (Phase 3 G1 + Phase 4 Module 14).

---

## Versioning (LOCKED)

Every engine tracks:

```
Version              engine semver
Schema Version       output schema fingerprint (already Sprint 2.6 pattern)
Output Version       report format version
API Version          REST API version (once API Center lands)
Replay Version       replay-framework compatibility marker
```

Version bumps follow SemVer strictly. Breaking output schema change → major version bump → downstream consumers pin the old version until migration.

---

## Acceptance Checklist (every sprint · no exceptions)

- [ ] Shared Engine complete (per Engine Implementation Standard)
- [ ] India adapter complete
- [ ] USA adapter complete
- [ ] Replay working (both markets)
- [ ] Walk-Forward working (both markets · where applicable)
- [ ] Benchmark working
- [ ] Cross-market Comparison artifact generated
- [ ] Dashboard tile / view added
- [ ] Reports (daily minimum · other cadences per Reporting Center)
- [ ] API endpoint (once API Center lands)
- [ ] Tests (all 9 types listed in Test Contract)
- [ ] Documentation (all 9 types listed in Documentation Contract)
- [ ] Performance metrics emitted
- [ ] Versioning bumped
- [ ] Quality contract passes (no TODO/FIXME/placeholder/mock/dead code)
- [ ] Production ready (deployed to daily-pipeline hook, or explicitly deferred with reason)

**Missing any → Sprint = NOT COMPLETE. No exceptions.**

---

## Sealed Contract Preservation (HARD RULE · learned incidents)

Nothing in Phase 5 overrides these sealed files. If a Phase 5 standard conflicts with a sealed file's existing structure, the SEALED file wins:

- `india/telegram_notify.py` — OPS001-I sealed message contract · never touch
- `research/adaptive_rec_v2/` — legacy engine · never touch
- `research/risk_capital_v2/` — legacy engine · never touch
- MON001 files — sealed
- Fingerprint `e4c070673568c52d…` — invariant

When extending a sealed engine's capability (e.g. a new Telegram output), do it via a NEW consumer that reads sealed engine output — never by modifying the sealed engine's contract.

---

## Grandfathering Rule (existing engines)

Phase 5 standards apply IN FULL to NEW engines built after 2026-07-24.

For engines that already exist (Sprint 1 → Sprint 7.8 · roughly 15 engines):
- **When touched by a future sprint**, that sprint brings the engine into partial Phase 5 compliance (adds missing files/methods/tests as needed for the current change)
- **Full retrofit** is scheduled as a dedicated hygiene sprint AFTER Phase 3 + Phase 4 ship — never as a shotgun refactor of the daily pipeline
- **Reason:** the daily pipeline's stability is the platform's promise to the operator; refactoring stable working code purely for cosmetic conformance to a new standard is not worth the risk

---

## Final Rule

From this point onward, developers should never ask "How should I build this?" — the answer must already exist in this specification. Every sprint becomes an implementation exercise rather than a design exercise.

If a case arises where the specification is silent or ambiguous, the developer MUST propose an amendment to this document (as a docs-only PR) and get explicit operator approval BEFORE building. Silent invention of a new convention is a violation.

---

## Governance for This Document

- **LOCKED 2026-07-24** by operator directive.
- Sits alongside `docs/AEGIS_PHASE3_MASTER_ROADMAP.md` (engine roadmap · FROZEN) and `docs/AEGIS_PHASE4_PRODUCT_COMPLETION.md` (product modules · LOCKED).
- Any deviation requires an explicit operator override, in writing, in a docs-only amendment PR merged BEFORE the implementation PR.
- Every sprint report must reference this document + confirm compliance per the Acceptance Checklist.

---

**End of Phase 5 · Institutional Development Standards · LOCKED 2026-07-24**
