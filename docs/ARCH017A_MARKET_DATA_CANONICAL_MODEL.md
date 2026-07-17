# ARCH017A — Market Data Canonical Model

## The Database Constitution for the Market Intelligence Layer

**Document type:** Design specification · canonical data model
**Status:** DRAFT · design only · NO code · NO parameter tuning · NO production changes
**Owner role:** Chief Data Officer · Data Architect · Head of Research
**Author:** AEGIS engineering
**Date opened:** 2026-07-17
**Parent constitution:** [`ARCH001A_INVESTMENT_PHILOSOPHY.md`](ARCH001A_INVESTMENT_PHILOSOPHY.md) — compliant with Articles IV (Research), V (Learning), VII (Operational), VIII (Ethics)
**Consumers (all bound to this schema):** ARCH017 · ARCH018 · ARCH019 · ARCH020 · ARCH021 · ARCH022 · ARCH023 · ARCH024 · ARCH025 · ARCH026 · ARCH027 · ARCH028 · ARCH029 · ARCH030
**Related evidence:** none yet (this is a schema doc; validation happens as consumers land)
**Sealed files touched:** 0. Production code touched: 0. Parameters tuned: 0.

---

## 0.  Preamble & non-negotiables

1. This document is **design specification**, not implementation. No table is created, no ingest job is authored, no code is changed by this document.
2. It defines the canonical *shape* every downstream Market Intelligence document (ARCH017-030) inherits. Every field name, every timestamp convention, every confidence definition, every missing-data behaviour comes from this document.
3. Where any downstream doc introduces a data field or entity, that field must be added *here* first, via the amendment discipline in §14.
4. Sealed baseline (MON001) is not affected — this document lives in the Market Intelligence Layer, entirely downstream of the sealed core.
5. **Rule of thumb.** If two ARCH017-030 documents refer to the same concept ("regime state," "confidence," "USD strength") by different field names, one of them is wrong. This document is the arbiter.

---

## 1.  Purpose

Without a canonical data model, ARCH017-025 will evolve inconsistent assumptions about fields, timestamps, confidence, and dependencies. The Market Intelligence Layer is a *federated* set of subsystems (global, sector, regime, graph, memory, attribution, holding, exit); they all read and write shared state. A shared vocabulary is the price of coherence.

Analogue: what MON001's sealed baseline is to the recommendation engine, ARCH017A is to the Market Intelligence Layer — the *frozen* interface every consumer relies on.

---

## 2.  Design principles

The seven principles below govern every schema choice below.

1. **Tenant-generic.** No hardcoded sector lists, no hardcoded ticker universes, no hardcoded macro thresholds. Every domain-specific input comes from a `ClientProfile`-equivalent runtime config. (ARCH001A Article VII clause 7.6.)
2. **Immutability of raw.** Every raw observation is stored append-only. Corrections are new rows superseding older ones — never in-place edits. (Article VII clause 7.4.)
3. **Explicit confidence.** Every derived / normalised / classified field carries a confidence value. Missing confidence is a schema violation — it forces the consumer to guess. Consumers must reduce risk when they see low confidence (Rule 8).
4. **Traceability.** Every stored value can be traced back to its raw source (URL / API endpoint / file path), timestamp of retrieval, and code SHA of the transformation that produced it.
5. **UTC everywhere.** All timestamps are UTC ISO-8601. IST equivalents are computed on read, never stored, never trusted from third-party feeds.
6. **Idempotent ingest.** Re-ingesting the same raw data produces byte-identical stored rows. Re-runs are free.
7. **Fail loud.** When a required feed is missing or a validator fails, the schema forces the consumer to receive an explicit "unavailable" signal. Silently substituting stale data is forbidden.

---

## 3.  Entity taxonomy

The Market Intelligence Layer has exactly eight entity classes. Every field in any ARCH017-030 doc belongs to exactly one of these.

| # | Entity | Description | Typical cadence |
|:-:|:--|:--|:-:|
| 1 | `RawObservation` | A single raw datapoint pulled from a source, unnormalised | source-dependent (real-time to quarterly) |
| 2 | `DerivedMetric` | A computed transformation of one or more RawObservations | daily |
| 3 | `NormalizedIndicator` | A DerivedMetric mapped onto a standardised scale (0-100 or z-score) | daily |
| 4 | `Classification` | A discrete label (e.g. `Risk-On`) produced from Normalized inputs | daily |
| 5 | `CompositeScore` | A weighted combination of Classifications and NormalizedIndicators | daily |
| 6 | `RegimeState` | A named regime (e.g. `Late Cycle`) with duration + transition history | daily / on-change |
| 7 | `Dependency` | A directed edge in the market knowledge graph (ARCH020) | monthly / on-recalibration |
| 8 | `MemorySnapshot` | A full daily snapshot of all above, keyed by trading date (ARCH022) | daily |

Each entity has a fixed schema (§4-11 below). Adding a new field to an existing entity is an amendment (§14).

---

## 4.  `RawObservation` — the immutable ground layer

Every atomic input to the Market Intelligence Layer starts here. Once stored, a RawObservation is byte-frozen.

### 4.1  Schema

| Field | Type | Cardinality | Description |
|:--|:--|:-:|:--|
| `observation_id` | UUID v7 | required | Time-ordered UUID; primary key |
| `variable_key` | str | required | Canonical name from the variable catalogue (§4.4). E.g. `equity_index.us.spx.close` |
| `asof_utc` | ISO 8601 datetime UTC | required | The time the observation is *about*, not the time it was retrieved |
| `ingested_at_utc` | ISO 8601 datetime UTC | required | The time the observation was written to the store |
| `value` | Union[float, int, str, bool] | required | The raw value, in the raw unit of the source |
| `unit` | str | required | Canonical unit from the units catalogue (§4.5). E.g. `USD`, `INR`, `bps`, `%`, `index_pts` |
| `source_id` | str | required | Canonical source identifier from the sources catalogue (§4.6). E.g. `yfinance.v0`, `nseindia.public.v1` |
| `source_row` | JSON | required | The exact raw row from the source, verbatim, for auditability |
| `retrieval_url` | str | optional | For web / API sources: the exact URL hit |
| `code_sha` | str | required | Git SHA of the ingest code that produced this row |
| `checksum` | str | required | SHA-256 of `variable_key + asof_utc + value + unit + source_id`; deduplication key |
| `superseded_by` | UUID v7 | optional | If a correction supersedes this row, the newer observation's id |
| `superseded_at_utc` | ISO 8601 datetime UTC | optional | Time the supersession was recorded |

### 4.2  Invariants

1. **Immutability.** `observation_id` is never reused. Deletion is not authorised except in an operator-approved data-quality remediation.
2. **Canonical variable_key.** No free-form variable names. Every key must appear in the variable catalogue (§4.4) at the time of ingest, else ingest fails.
3. **Idempotent by checksum.** Attempting to ingest a row with an existing `checksum` is a no-op.
4. **Superseded rows are visible.** Corrections do not delete originals; consumers can (and should) verify the audit trail.

### 4.3  Retrieval semantics

- Reads default to *latest non-superseded* row for `(variable_key, asof_utc)`.
- Time-travel reads (as-of-what-was-known-on-date-X) are supported by filtering `ingested_at_utc ≤ X`.
- Corrections that arrive late (e.g. a value revised T+3) create new rows with `superseded_by` pointing forward from the original; original stays visible.

### 4.4  Variable catalogue

Every variable used in the Market Intelligence Layer is registered here. New variables require an amendment (§14). Registration format:

```
variable_key           : namespace.category.subcategory.name
                          example: equity_index.us.spx.close
                          example: macro.us.fomc.policy_rate
                          example: fx.usd_inr.spot
                          example: commodity.brent.close
                          example: flow.india.fii.cash_net
canonical_unit         : e.g. index_pts, %, bps, USD_per_INR
frequency              : real-time / intraday / daily / weekly / monthly / quarterly
first_available_utc    : the earliest date the source provides data
canonical_source_id    : the *authoritative* source; other sources are fallbacks
fallback_source_ids    : ordered list of fallbacks (§10)
retrieval_module       : which ingest code produces this variable
```

The initial catalogue for ARCH017's Global Intelligence Engine is defined in [`docs/ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md`](ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md) §3. Additions from ARCH018-030 land in subsequent amendments.

### 4.5  Units catalogue

Every `unit` field value must appear here. Adding a unit requires amendment.

Standard units:

- Currencies: `USD`, `INR`, `EUR`, `JPY`, `CNY` (ISO 4217 codes)
- Price ratios: `USD_per_INR`, `INR_per_USD` (direction matters; documented explicitly)
- Percentages: `%` (0-100 scale; `pct` and `percent` are forbidden aliases)
- Basis points: `bps` (1 bps = 0.01%)
- Index points: `index_pts` (dimensionless; refers to the specific index in the variable_key)
- Counts: `count`, `count_per_day`
- Volumes: `shares`, `contracts`, `INR_lakhs`, `INR_crores`, `USD_millions`, `USD_billions`
- Time: `days`, `sessions`, `bars`

**Prohibited.** Free-form units like "points" (ambiguous), "dollars" (which dollar?), "percent" (spelling variant).

### 4.6  Sources catalogue

Every `source_id` must appear here. Each source has:

- `source_id` — canonical identifier
- `source_kind` — free / paid / operator-manual
- `latency` — real-time / EOD / T+1 / T+X
- `reliability_class` — Tier 1 (authoritative) / Tier 2 (secondary) / Tier 3 (best-effort)
- `retrieval_method` — API / web scrape / file drop / manual entry
- `licensing` — public / creative commons / licensed / operator-only
- `owner_contact` — for licensed feeds, the point of contact if the feed breaks
- `governance_notes` — any regulatory constraints (rate limits, redistribution rules)

The initial sources catalogue is defined in ARCH017 §5 and expanded by subsequent ARCH docs.

---

## 5.  `DerivedMetric` — computed transformations

DerivedMetrics are deterministic functions of one or more RawObservations. They are recomputed daily; they do not accumulate — a fresh compute replaces the prior day's value.

### 5.1  Schema

| Field | Type | Description |
|:--|:--|:--|
| `metric_id` | UUID v7 | Primary key |
| `metric_key` | str | Canonical name. E.g. `derived.us_2s10s.slope_bps`, `derived.india.vix_ma_20d` |
| `asof_utc` | ISO 8601 UTC | The date the metric refers to |
| `computed_at_utc` | ISO 8601 UTC | When the compute ran |
| `value` | float | The metric value |
| `unit` | str | From the units catalogue |
| `input_observation_ids` | JSON array of UUID v7 | Every RawObservation that fed the compute |
| `formula_key` | str | Canonical formula name. E.g. `slope_2y_10y`, `moving_average_20d` |
| `formula_version` | str | Semver: `v1.0`, `v1.1`, etc. Versioning enables side-by-side v1 vs v2 comparisons. |
| `code_sha` | str | SHA of the compute code |
| `confidence` | float ∈ [0, 1] | See §9 |
| `confidence_components` | JSON | Breakdown of what drives the confidence (missing inputs, staleness, source tier) |

### 5.2  Invariants

1. **Deterministic.** Recomputing with the same `input_observation_ids` and `formula_version` produces byte-identical `value`.
2. **Reproducible from raw.** A consumer can, given only the `input_observation_ids` and `formula_version`, re-derive the value.
3. **No implicit conversions.** If a formula needs INR-converted USD prices, the conversion is *explicit* — either a separate DerivedMetric or a documented step within the formula.

---

## 6.  `NormalizedIndicator` — standardised-scale scores

NormalizedIndicators map DerivedMetrics onto a *common* scale so composites (§8) can combine them apples-to-apples.

### 6.1  Schema

| Field | Type | Description |
|:--|:--|:--|
| `indicator_id` | UUID v7 | Primary key |
| `indicator_key` | str | E.g. `norm.usd_strength`, `norm.us_equity_momentum` |
| `asof_utc` | ISO 8601 UTC | |
| `computed_at_utc` | ISO 8601 UTC | |
| `raw_metric_id` | UUID v7 | The DerivedMetric being normalised (or null if from multiple) |
| `raw_metric_ids` | JSON array | If multiple DerivedMetrics feed the indicator |
| `value_0_100` | float ∈ [0, 100] | The normalised score |
| `zscore` | float | Optionally exposed z-score version (∼N(0,1) if the underlying is normal) |
| `normalization_method` | str | E.g. `zscore_rolling_252d`, `percentile_rolling_252d`, `min_max_static` |
| `normalization_version` | str | Semver |
| `code_sha` | str | |
| `confidence` | float ∈ [0, 1] | Propagated from the input DerivedMetric with adjustment |

### 6.2  Normalisation methods (registered)

- **`zscore_rolling_252d`** — running mean/stdev over the last 252 sessions; z-score → `50 + 10 × z` clamped to [0, 100].
- **`percentile_rolling_252d`** — the raw metric's percentile rank within the last 252 sessions.
- **`min_max_static`** — hard-coded min and max; percentile within that range.
- **`hmm_state_probability`** — the probability the underlying is in State X per a fitted HMM (used by ARCH019).

Adding a new method is an amendment.

### 6.3  Invariants

- The `value_0_100` range is exactly [0, 100]. Values outside are schema violations.
- Higher values mean *more risk-on* or *more supportive*, depending on the indicator. Direction is documented per indicator in ARCH017 §5.

---

## 7.  `Classification` — discrete labels

Every Classification maps continuous NormalizedIndicators onto a fixed enum. The enums are declared once, here, and referenced by consumers.

### 7.1  Global market posture

`Classification.global_posture` ∈ `{Risk-On, Risk-Off, Rotating, Neutral, Unknown}`.

| Label | Definition |
|:--|:--|
| `Risk-On` | Global CompositeScore > 65 with confidence ≥ 0.7 |
| `Risk-Off` | Global CompositeScore < 35 with confidence ≥ 0.7 |
| `Rotating` | Sub-scores diverge (equity risk-on, credit risk-off) — signals from ARCH018/019 conflict |
| `Neutral` | 35 ≤ CompositeScore ≤ 65 with confidence ≥ 0.7 |
| `Unknown` | Confidence < 0.7 or a required feed is stale |

### 7.2  Liquidity posture

`Classification.liquidity` ∈ `{Improving, Stable, Deteriorating, Unknown}`.

Definitions in ARCH017 §5.

### 7.3  Dollar posture

`Classification.usd` ∈ `{Bullish, Neutral, Weak, Unknown}`.

### 7.4  Volatility regime

`Classification.vol_regime` ∈ `{Calm, Elevated, Spiking, Unknown}`.

### 7.5  Rates regime

`Classification.rates` ∈ `{Hiking, Cutting, On-Hold, Unknown}`.

### 7.6  Regime state

`Classification.regime` ∈ `{Expansion, Recovery, Late-Cycle, Recession, Panic, Liquidity-Crisis, High-Inflation, Disinflation, AI-Bubble, Commodity-Boom, Election, War, Unknown}`.

Defined operationally in ARCH019.

### 7.7  Common properties

Every Classification carries:

- `asof_utc`
- `label` (from the enum)
- `confidence ∈ [0, 1]`
- `contributing_indicator_ids` (which NormalizedIndicators drove the label)
- `duration_days` (for state-machine classifications: how long has this label held?)
- `previous_label` (the last different label; supports transition analysis)

---

## 8.  `CompositeScore` — weighted combinations

CompositeScores are the *output* the operator sees on dashboards and that downstream consumers use.

### 8.1  Schema

| Field | Type | Description |
|:--|:--|:--|
| `composite_id` | UUID v7 | |
| `composite_key` | str | E.g. `composite.global_risk`, `composite.sector_strength.it` |
| `asof_utc` | ISO 8601 UTC | |
| `value_0_100` | float ∈ [0, 100] | |
| `classification` | str | The Classification label at this value (e.g. `Risk-On`) |
| `confidence` | float ∈ [0, 1] | |
| `component_indicators` | JSON array | Each element: `{indicator_id, weight, value_0_100, contribution_to_composite}` |
| `weighting_scheme` | str | E.g. `equal_weighted`, `information_ratio_weighted`, `expert_curated_v2` |
| `weighting_version` | str | Semver |

### 8.2  Invariant: contribution equals composite

`sum(component_indicators[i].contribution_to_composite) == value_0_100` (within numerical tolerance).

### 8.3  Contribution breakdown

Every CompositeScore *must* expose which indicators drove it, in percentage-contribution form. This is Article VIII clause 8.2 (explainability) operationalised. When ARCH023 asks "why is Global Risk 81 today?", it reads this field.

---

## 9.  Confidence — the universal scalar

Every derived / normalised / classified / composite entity carries a `confidence ∈ [0, 1]`. This is Article II clause 2.3 (uncertainty) and Article VIII clause 8.5 (calibrated confidence) operationalised as a first-class data field.

### 9.1  Confidence components

`confidence` is computed from four factors, combined multiplicatively:

```
confidence = C_source × C_freshness × C_completeness × C_agreement
```

- **`C_source`** — reliability of the underlying RawObservation source (Tier 1 = 1.0, Tier 2 = 0.85, Tier 3 = 0.7). Sources catalogue (§4.6).
- **`C_freshness`** — how recent the underlying data is versus its expected cadence. Fresh = 1.0; expected-latest = 0.9; stale by 1 period = 0.5; stale by 2+ periods = 0.
- **`C_completeness`** — fraction of expected input observations that are available. If a formula needs 5 inputs and 4 are present, `C_completeness = 0.8`.
- **`C_agreement`** — for indicators from multiple methods (e.g. HMM regime detection + rule-based regime detection), the fraction agreeing on the classification.

### 9.2  What consumers do at low confidence

Per Article II Rule 8 (uncertainty → reduce):

| Confidence | Interpretation | Downstream action |
|:-:|:--|:--|
| ≥ 0.9 | High | Full trust; use value directly |
| 0.7 – 0.9 | Medium | Use value; monitor closely |
| 0.5 – 0.7 | Low | Reduce exposure per Rule 8; flag on dashboard |
| < 0.5 | Very low | Treat classification as `Unknown`; freeze new admissions |
| = 0 | Failed | Data outage; kill switch consideration (ARCH002 L8.c) |

### 9.3  Confidence is *always* published

There is no notion of a "confidence-free" score in this schema. Every score, indicator, classification, composite carries confidence. Consumers cannot access a value without also accessing its confidence.

---

## 10.  Missing-data behaviour

### 10.1  Rule (from Article II clause 2.7 and Article VIII clause 8.7)

**Missing data never silently becomes a substitute value.** Every consumer receives an explicit signal of what is missing and either:

- Reduces exposure per Rule 8, or
- Refuses to compute the downstream value and returns `Unknown`, or
- Uses an explicitly-documented fallback source (§10.3)

### 10.2  How missingness is represented

- `RawObservation.value` is never null. If a source returns null, the row is simply not written; downstream reads see the absence.
- `DerivedMetric.value` is never null. If inputs are missing, the DerivedMetric is not computed (or is computed with `confidence = 0` and a special flag).
- Consumers query `latest(variable_key)` and receive either a row or `NotFound`. `NotFound` is not the same as `value = null`.

### 10.3  Fallback ordering

Every variable has a canonical source and (optionally) an ordered list of fallbacks (§4.4). Fallback resolution:

- Query `canonical_source` first.
- On timeout / error / null / staleness beyond acceptable threshold, query `fallback_source_ids[0]`.
- Repeat down the list.
- If all fail, emit an explicit `feed_outage(variable_key)` event to the OPS pipeline (ARCH002 L8.c candidate).

Fallback usage is logged: every row records which source actually served the value.

### 10.4  Stale-data threshold per cadence

| Expected cadence | "Stale" begins at | "Failed" begins at |
|:--|:-:|:-:|
| real-time | 15 minutes | 4 hours |
| intraday | 2 hours | 1 session |
| daily | 1 session | 2 sessions |
| weekly | 8 days | 15 days |
| monthly | 40 days | 60 days |
| quarterly | 100 days | 180 days |

Consumers see the actual staleness in the `C_freshness` component of confidence.

---

## 11.  Versioning discipline

Every schema element and every transformation has a version.

### 11.1  Schema versioning

- Every entity class has a schema version (this document's revision number). Amendments (§14) increment the schema version.
- Rows carry the schema version they were written under. Reads apply migrations if needed.

### 11.2  Formula versioning

- Every `formula_key` has a version. E.g. `slope_2y_10y v1.0` vs `slope_2y_10y v1.1`.
- Changing a formula (even a bugfix) requires a new version. Old rows keep their v1.0 lineage; new rows use v1.1.
- Consumers query for a specific version when reproducibility matters (e.g. reproducing a historical decision).

### 11.3  Weighting versioning

- Every CompositeScore has a `weighting_version`. Changing weights requires a new version.
- Old CompositeScore rows retain their weighting_version for audit; new rows use the new version.

### 11.4  Ingest-code SHA

- Every row carries the git SHA of the code that produced it. Consumers can, in principle, rerun any computation from the SHA + input rows.

---

## 12.  Storage discipline

### 12.1  Where data lives

- **Hot store.** `data/market_intelligence/raw/YYYY-MM/*.parquet` (RawObservations, monthly partitioned)
- **Warm store.** `data/market_intelligence/derived/YYYY-MM/*.parquet` (DerivedMetrics, NormalizedIndicators, Classifications, CompositeScores)
- **Snapshot store.** `data/market_intelligence/snapshots/YYYY/YYYY-MM-DD.parquet` (one full MemorySnapshot per trading day; ARCH022 consumes)

### 12.2  Retention

- RawObservations: indefinite (Article VII clause 7.4)
- DerivedMetrics / NormalizedIndicators / Classifications / CompositeScores: indefinite (they're reproducible from raw, but keeping them saves compute on time-travel queries)
- MemorySnapshots: indefinite (this is the market memory asset)

### 12.3  Compaction

- Monthly compaction rewrites the previous month's partition into optimised parquet.
- Compaction never modifies values; it only re-arranges storage.
- Compaction is idempotent.

### 12.4  Backups

Beyond the operator's git repository:
- Local: same partition file layout replicated to a secondary path.
- Cloud (future): S3 or equivalent, with lifecycle policies matching retention.

Backup strategy is deferred to `ARCH_OPS_BACKUP.md` (not yet written).

---

## 13.  Governance of this model

### 13.1  Ownership

The operator owns this document. Every amendment requires operator approval (Article IX clause 9.3).

### 13.2  Amendment discipline

Following the same pattern as ARCH001A Article X:

1. Written proposal citing the specific field / entity / catalogue entry being amended
2. Justification
3. Impact analysis: which existing consumers (ARCH017-030) are affected
4. Migration plan for any historical rows if the change is not additive
5. Operator approval
6. Version stamp increment (schema-version bump if entity structure changes)
7. Audit trail entry in `docs/CANONICAL_MODEL_AMENDMENTS_LOG.md` (to be created on first amendment)

### 13.3  Additive vs breaking changes

- **Additive** (add a field with a default; add an enum value): minor version increment, no migration.
- **Breaking** (change a field's type; remove a field; rename): major version increment; explicit migration for historical rows; consumers must be updated in the same commit.

### 13.4  Prohibited changes

- Removing an entity class
- Making a currently-required field optional
- Changing the semantic meaning of a field name (renaming and repurposing)

Prohibited changes require this document to be retired and a successor adopted, mirroring ARCH001A Article X clause 10.2.

---

## 14.  Non-goals

- This document does **not** specify which specific data sources ARCH017 uses (that's ARCH017 §5).
- This document does **not** define composite formulas (that's ARCH017-025, per-consumer).
- This document does **not** implement ingest, storage, or serving code.
- This document does **not** specify UI for browsing the data (dashboards live in OPS002).
- This document does **not** address non-market data (news, transcripts, alt-data — those go through ARCH013).
- This document does **not** address confidence for the *AEGIS recommendation engine* (that's ARCH029; different domain).

---

## 15.  Integration with the wider AEGIS architecture

| Consumer | Reads from ARCH017A | Writes to ARCH017A |
|:--|:--|:--|
| **ARCH017** Global Intelligence Engine | Reads RawObservations, writes DerivedMetrics / NormalizedIndicators / Classifications / CompositeScores | Yes |
| **ARCH018** Sector Intelligence | Reads ARCH017 outputs + sector-specific RawObservations; writes DerivedMetrics for sectors | Yes |
| **ARCH019** Regime Detection | Reads Classifications from ARCH017 + ARCH018; writes `Classification.regime` | Yes |
| **ARCH020** Knowledge Graph | Reads Dependencies from this doc's §16 (below); writes edge weights | Yes |
| **ARCH021** Dependency Engine | Reads the Knowledge Graph (Dependencies) | No writes |
| **ARCH022** Market Memory | Reads *everything* daily and writes MemorySnapshots | Yes (MemorySnapshots only) |
| **ARCH023** Decision Attribution | Reads all CompositeScores + their `component_indicators`; produces Shapley attributions | No writes |
| **ARCH024** Adaptive Holding | Reads Classifications for regime + sector; recommends holding changes | No writes |
| **ARCH025** Adaptive Exit | Same as ARCH024 + reads Confidence to inform L6 modulator (per ARCH002) | No writes |
| **ARCH026** AI Research Assistant | Reads MemorySnapshots for context; writes DerivedMetrics with `formula_key = 'llm_extract.<name>'` | Yes (LLM-derived metrics only, with source citations in `input_observation_ids`) |
| **ARCH027** Strategy Doctor | Reads MemorySnapshots at position entry/exit; produces attribution reports | No writes |
| **ARCH028** Recommendation DNA | Reads MemorySnapshots at position entry; computes DNA fingerprints | Yes (as DerivedMetrics) |
| **ARCH029** Confidence Calibration | Reads confidence values across the layer; produces calibration curves | No writes |
| **ARCH030** Champion-Challenger | Reads everything; writes side-by-side CompositeScores under `weighting_version` = challenger | Yes (challenger-tagged rows only) |

---

## 16.  Dependency (Knowledge Graph edges) schema

`Dependency` is the eighth entity class. Reserved here for the graph layer (ARCH020 will populate it).

| Field | Type | Description |
|:--|:--|:--|
| `dependency_id` | UUID v7 | Primary key |
| `source_key` | str | The variable_key or entity_key on the *cause* side |
| `target_key` | str | The variable_key or entity_key on the *effect* side |
| `relationship_type` | enum | `correlated`, `causal_positive`, `causal_negative`, `regime_conditional`, `sector_pass_through` |
| `strength` | float ∈ [-1, 1] | Signed edge weight |
| `confidence` | float ∈ [0, 1] | Same semantics as §9 |
| `evidence_type` | enum | `empirical_correlation`, `expert_curated`, `llm_proposed`, `hybrid` |
| `evidence_window_start_utc` | ISO 8601 UTC | For empirical edges: the window used |
| `evidence_window_end_utc` | ISO 8601 UTC | |
| `regime_conditioning` | JSON | If regime-conditional: which regime states apply |
| `last_recalibrated_at_utc` | ISO 8601 UTC | Edges decay over time; recalibration cadence per edge |
| `superseded_by` | UUID v7 | If a new edge replaces this one |

Detailed graph semantics live in ARCH020. This schema is the reserved seat.

---

## 17.  Sample rows (illustrative)

Not adopted values. Just to show what the schema looks like *populated*.

### 17.1  A RawObservation

```
observation_id       01HFXZ3K2Q1F0J7VBQTPS6A2H4
variable_key         equity_index.us.spx.close
asof_utc             2026-07-17T20:00:00Z
ingested_at_utc      2026-07-17T20:03:41Z
value                6234.55
unit                 index_pts
source_id            yfinance.v0
source_row           {"Open":..., "High":..., "Low":..., "Close":6234.55, ...}
retrieval_url        (n/a — yfinance library)
code_sha             0a3f570…
checksum             sha256:e9b1...
```

### 17.2  A DerivedMetric

```
metric_id            01HFXZ4B9M2N0T1F7YQFA9WPR0
metric_key           derived.us.2s10s.slope_bps
asof_utc             2026-07-17T20:00:00Z
computed_at_utc      2026-07-17T20:05:12Z
value                −42.5
unit                 bps
input_observation_ids [01HFXZ3K…, 01HFXZ3L…]
formula_key          slope_2y_10y
formula_version      v1.0
code_sha             0a3f570…
confidence           0.98
confidence_components {C_source:1.0, C_freshness:0.98, C_completeness:1.0, C_agreement:1.0}
```

### 17.3  A NormalizedIndicator

```
indicator_id         01HFXZ5D4C3P0R2H8ZQ...
indicator_key        norm.us_yield_curve_inversion
asof_utc             2026-07-17T20:00:00Z
value_0_100          92.3    (higher = more inverted = more risk-off)
zscore               2.7
normalization_method zscore_rolling_252d
confidence           0.98
```

### 17.4  A Classification

```
label                Risk-Off
confidence           0.86
contributing_indicator_ids [norm.us_equity_momentum, norm.usd_strength, norm.us_yield_curve_inversion, norm.vix]
duration_days        14
previous_label       Neutral
```

### 17.5  A CompositeScore

```
composite_key        composite.global_risk
value_0_100          22.4
classification       Risk-Off
confidence           0.86
component_indicators [
  {indicator_key: "norm.us_equity_momentum",   weight: 0.25, value_0_100: 18, contribution_to_composite: 4.5},
  {indicator_key: "norm.usd_strength",         weight: 0.15, value_0_100: 78, contribution_to_composite: 11.7},
  {indicator_key: "norm.vix",                  weight: 0.20, value_0_100: 15, contribution_to_composite: 3.0},
  ... (others summing to remaining 3.2 points)
]
weighting_scheme     equal_weighted
weighting_version    v1.0
```

---

## 18.  Success criteria

This document has done its job when:

- Every ARCH017-030 doc references field names from this schema without inventing new ones.
- Every downstream consumer specifies its reads and writes in terms of the eight entity classes.
- Adding a new data source is a mechanical exercise of registering variable / unit / source and adding an ingest module — no schema surprises.
- Two engineers reading two different ARCH docs converge on the same understanding of "confidence" or "risk-on" without ambiguity.
- Failed data feeds produce explicit `feed_outage` events, never silent stale-substitutions.

---

## 19.  Constitutional compliance (ARCH001A)

| ARCH001A clause | How ARCH017A complies |
|:--|:--|
| Article I clause 1.1 (Never lose capital) | Missing-data → reduce exposure (§10.1) |
| Article II clause 2.3 (Uncertainty) | Confidence is a first-class field on every entity (§9) |
| Article II clause 2.7 (Failure honesty) | `Unknown` classification and `NotFound` reads (§10) |
| Article IV clause 4.1 (Evidence) | Every stored value is traceable to source + code SHA (§2.4) |
| Article IV clause 4.4 (Statistical hygiene) | Formula and weighting versions frozen; §11 |
| Article V clause 5.1 (Learning bounded) | No auto-learning; challenger writes tagged, never overwrites champion (§15) |
| Article V clause 5.2 (Learning observational) | All derived values are compute-only; no self-modification |
| Article VII clause 7.1 (Sealed baseline) | This layer sits downstream of MON001; sealed core untouched |
| Article VII clause 7.4 (Audit) | Rows are append-only; supersession is a new row (§4.2) |
| Article VII clause 7.6 (Tenant-generic) | Variable catalogue is data, not code; no hardcoded thresholds (§2.1) |
| Article VII clause 7.7 (No hardcoded params) | Weights, thresholds, formulas versioned externally (§11) |
| Article VII clause 7.8 (Reproducibility) | Every row carries `code_sha` and `formula_version` (§11.4) |
| Article VIII clause 8.1 (Transparency) | Every value traceable to its inputs (§5.2, §8.3) |
| Article VIII clause 8.2 (Explainability) | Contribution breakdown mandatory on CompositeScores (§8.3) |
| Article VIII clause 8.5 (Calibrated confidence) | `confidence` on every derived entity; ARCH029 calibrates it separately |
| Article VIII clause 8.7 (Failure honesty) | Missing data never silently substituted (§10) |

---

## 20.  Integrity + sign-off

- Sealed files touched: **0**
- Production code touched: **0**
- Parameters tuned: **0**
- MON001 fingerprint: `e4c070673568c52d…` (invariant)
- `cumulative_strategy_search`: **38** (unchanged)
- Approvals required: operator sign-off + `docs/APPROVALS_LOG.md` entry
- **Effective date:** upon operator approval (currently pending)
- **Version:** DRAFT / v0.9 (proposed v1.0 on approval)

---

## 21.  Change log

| Date | Change | Author | Version |
|:--|:--|:--|:--|
| 2026-07-17 | Initial canonical model — 8 entity classes, confidence discipline, missing-data behaviour, versioning, integration with ARCH017-030 | AEGIS engineering | DRAFT / v0.9 |
