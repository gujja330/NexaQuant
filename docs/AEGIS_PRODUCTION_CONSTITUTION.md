# AEGIS Production Constitution

**Adopted:** 2026-07-30
**Version:** v3.0 LOCKED
**Status:** In force · governance-level document · amend only via written CEO+operator approval

> AEGIS v3.0 is constitutionally frozen.
> The production goal is correctness, repeatability, explainability,
> auditability, and long-term maintainability — not feature growth.

---

## Article I · Locked components

The following are **production-locked**. Any change requires the amendment
process in Article IV.

- Recommendation Engine (Runner 2 v3 · sole canonical)
- Portfolio Engine
- Rotation Engine
- Lifecycle Engine (9-state machine)
- Learning Engine (adaptive weights from closed-trade IC)
- Validation Layer (Runner 1 · advisory-only agreement checker)
- Snapshot Store (append-only per-date archive)
- Position Store (append-only per-ticker high-water + trailing stop)
- AI Scorecard (6 institutional metrics)
- Recommendation Schema (`reports/recommendations.json` · India + USA)
- Telegram Schema (Command Center · 12-section spec)
- Dashboard Schema
- API Contracts (all downstream consumer contracts)
- 24-stage pipeline sequencing

## Article II · Non-goals

The following are **explicitly forbidden** without a v4.x amendment:

- Architectural redesign
- New recommendation engine
- Merging Runner 1 into recommendation output (Option D preserved)
- Schema changes
- New AI model classes
- Intraday trading (per prior CEO call · separate product if built)
- New Telegram sections (per Evidence Cycle discipline)
- Speculative refactors (Market Adapter Layer et al · YAGNI until a
  third market has a scheduled deployment date)

## Article III · Permitted changes

Only the following classes of change are permitted without amendment:

- **Bug fixes** with regression test
- **Regression tests** locking existing behavior
- **Performance improvements** without semantic change
- **Operational resilience** (retries · timeouts · CI stability)
- **Data-quality improvements** (source retries · dedup · validation)
- **Explainability polish** (labels · wording · display order) that
  don't add new sections

Every permitted change must:
1. Preserve all sealed contracts (MON001 fingerprint · Feature Store
   schema · adaptive_rec_v2 · risk_capital_v2 · india/telegram_notify.py)
2. Pass the anti-hardcode guardrail
3. Pass all existing regression tests
4. Update tests to cover the change

## Article IV · Amendment process

An amendment (v4.x) requires:

```
Observation
    ↓
Hypothesis
    ↓
Research (in Phase B · reports/evidence/*)
    ↓
Backtest (historical proof)
    ↓
Paper validation (30+ days minimum on live paper trading)
    ↓
Written CEO + operator approval
    ↓
v4.x branch (never modifies v3.x in-place)
```

Skipping any step invalidates the amendment.

## Article V · Three-phase separation

**Phase A · Production** (`main` branch · v3.x)
- Locked components + permitted-changes only
- Ships to Telegram / dashboard / operator
- Governance: this document

**Phase B · Evidence Research** (`main` branch · `backend/analytics/evidence/*`)
- Pure measurement · never modifies production behavior
- Outputs land at `reports/evidence/*.json` and one advisory line in
  existing Scorecard display
- Human review before any finding informs an amendment
- Currently active: calibration · alpha_validation · yoy · rolling_ic

**Phase C · v4 Development** (`v4-*` branches · not `main`)
- Only spawned when Phase B has produced enough evidence to justify
  a Constitutional amendment
- Full CI + tests + backtest + paper + approval before any merge
- Never touches v3.x in-place

## Article VI · Evidence is advisory

Evidence engines (Phase B) NEVER autotune production. They surface
findings. All translation of findings into production changes goes
through Article IV.

Current evidence findings (2026-07-30 · advisory):

- **Calibration:** `poorly_calibrated_flat` (slope -0.44 · Brier 0.33) ·
  confidence field is not statistically meaningful on the historical
  corpus · surfaced as WARNING label in Scorecard · no autotuning
- **Alpha Validation:** `no_predictive_relationship` (pearson r -0.02) ·
  possible data-labeling issue in learning.parquet · investigation queued
- **YoY:** `mixed_signals` (win-rate flat · median-return declining
  since 2024) · possible regime shift · investigation queued
- **Model Attribution Longitudinal:** `attribution_has_dead_weight` (all
  6 dim_* negative avg IC) · likely same data-labeling issue

These findings are documented, not acted on. They may or may not become
v4.x amendments after Article IV completes.

## Article VII · Market expansion

Adding new markets (Australia · Canada · UK · Europe · Japan) is
**explicitly permitted under Phase A** provided:

1. New market is added as a parallel directory alongside `india/` +
   `usa/`, using the existing convention-based adapter pattern
2. Universe loaded dynamically from `configs/universes/*.json`
3. No changes to shared engines · no schema changes
4. Ops_check + regression tests extended to cover new market
5. Sealed contracts untouched

A formal `MarketAdapter` interface refactor is a v4.x change (Article IV),
not Phase A work. Deferred until a third market has a scheduled
deployment date.

## Article VIII · Deletion + amendment

This Constitution may only be amended by:
1. Written CEO note stating specific Article to change
2. Operator sign-off
3. Version bump to next major (v4.0)

No silent amendments. No default-to-yes changes.

---

**Signed into force 2026-07-30. AEGIS v3.0 LOCKED. Maintenance Mode active.**
