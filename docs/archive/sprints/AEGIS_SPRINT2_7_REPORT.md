# Sprint 2.7 · Model Factory + Ensemble Intelligence · Report
**Completed 2026-07-20 · Both markets · 11 models · Walk-forward-ready · Human-in-the-loop enforced**

---

## Purpose (per operator brief)

> "Sprint 2.7 — Model Factory & Ensemble Intelligence. Stop before implementing
> Investment Intelligence. Build a complete Model Factory so AEGIS can manage,
> evaluate, compare, version, and evolve multiple prediction models."

The revised pipeline the operator locked in memory:
```
Feature Store → Feature Intelligence → Model Factory → Research Factory → Investment Intelligence
```

Sprint 2.7 delivers the Model Factory layer. Investment Intelligence still not started.

**Recommendation Engine, Risk, Portfolio, Learning: untouched.**

---

## Architecture

**Before:** one recommendation engine consumed features directly.

**After:** many prediction models each score every ticker; the ensemble combines them; downstream engines consume the ensemble.

```
Feature Store snapshot
    ↓
Feature Intelligence (selected_features.json)
    ↓
Model Factory  ← 11 models: Momentum, Trend, Value, Growth, Quality,
                    ↓         Mean Reversion, News, Macro, Sector Rotation,
                    ↓         Event Driven, AI Hybrid
Model Intelligence (metrics per model)
    ↓
Ensemble (equal-weight v0; WF-weighted in Sprint 9)
    ↓
[Sprint 3+ Investment Intelligence consumes this]
```

---

## What shipped

### A. Framework (`backend/model_factory/`)

| Module | Purpose |
|---|---|
| `model_base.py` | `BaseModel` ABC + `ModelMetadata` + `ModelPrediction` + `ModelType` enum. Every model implements `train(features, target, cutoff)` + `predict(features, cutoff)` + `describe()`. Walk-forward safe. |
| `factory.py` | `ModelFactory.train_all()` / `predict_all()` — orchestrates all 11 models. AI Hybrid gets other models' predictions injected before running (meta-model). |
| `model_intelligence.py` | `evaluate_model()` computes metrics: n_scored, avg_score, top_10_confidence, and (when learning corpus present) win_rate, profit_factor, precision, sharpe. Status field is honest — `insufficient_history` until Sprint 9. |
| `ensemble.py` | `EnsembleWeights` + `ensemble_predict()`. v0 equal-weight; v1+ WF-weighted (Sprint 9). Weight config lives in operator-owned YAML. |

### B. 11 Model implementations (`backend/model_factory/models/`)

Each carries **business_rationale + economic_intuition + feature_dependencies + business_rationale** in `ModelMetadata`.

| Model | Signal | Rationale |
|---|---|---|
| **Momentum** | returns × MA alignment × RSI | Winners keep winning 3-12mo (documented factor) |
| **Trend** | ADX × 52W distance × SMA alignment | Persistent uptrends are safest bulls |
| **Value** | 1/PE + 1/PB | Margin of safety + reversion to mean |
| **Growth** | earnings_growth × ROE | Compounding earnings drives multi-year returns |
| **Quality** | ROE + margins + (low D/E) + quality_score | High-quality compounds; low-quality erodes |
| **Mean Reversion** | oversold conditions × quality filter | Panic detaches price from fundamentals |
| **News** | sentiment × polarity × volume | Sentiment drives short-term flows |
| **Macro** | market composite + VIX dampener | Macro conditions the *level* of returns |
| **Sector Rotation** | sector_return × leadership | Capital rotates over 3-12mo cycles |
| **Event Driven** | earnings surprise × PEAD × insider flow | Discrete events → predictable drift |
| **AI Hybrid** | meta-ensemble of the other 10 | No single style wins in every regime |

All 11 return `ModelPrediction` with per-ticker `{score ∈ [-1, +1], confidence ∈ [0, 1], evidence}`. **Deterministic** — verified by `test_predictions_deterministic`.

### C. AI Model Analyst (`backend/ai/model_analyst.py`)

Reads model descriptions + metrics. Emits:
- Per-model narrative (name, purpose, current confidence)
- Ensemble participation proposal (`include` / `include_experimental_only` / `exclude_no_data`)
- Deprecation candidates (low top-10-confidence models)

**Contract-tested:** no finding may contain `buy`, `sell`, `target_price`, `recommendation`, `action`, `promoted`, or `approved` keys. AI proposes, operator promotes.

### D. Per-market runners

- `india/model_factory/run.py`     → `reports/model_factory.json` + `model_metrics.json` + `ensemble.json` + `ai_model_narrative.json`
- `usa/research/model_factory/run.py` → same shape under `usa/reports/`

Both:
- Read latest `features/{market}/YYYY-MM-DD.parquet`
- Restrict to `selected_features.json` from Sprint 2.6
- Run all 11 models via `ModelFactory`
- Emit per-model metrics + ensemble scoreboard + AI narrative
- **Stamp every model in `model_registry.jsonl`** as EXPERIMENTAL (Sprint 2.6 registry pattern)

### E. Wiring

- India orchestrator: 24 → 25 steps (`model_factory` after `feature_intelligence`)
- USA orchestrator: 27 → 28 steps
- India + USA `datasets.yaml`: +4 entries each
- India + USA SPAs: Model Ensemble tile added
- CI: Sprint 2.7 regression suite step added

---

## Runtime verification (2026-07-20)

### Sprint 2.7 regression — 14/14 pass

```
$ python backend/tests/test_sprint27.py
  [OK] all 11 model types registered (11 types)
  [OK] all 11 models carry business_rationale + economic_intuition
  [OK] every model declares feature_dependencies
  [OK] factory ran 11 models × 20 tickers, all scores in [-1, +1]
  [OK] all model predictions deterministic across identical calls
  [OK] ensemble combines 11 models → 20 tickers
  [OK] ensemble weights normalize correctly
  [OK] empty ensemble handled cleanly
  [OK] evaluate_model: n_scored=20 status=insufficient_history
  [OK] AI Model Analyst produced narrative for 11 models
  [OK] AI Model Analyst obeys no-promotion contract
  [OK] all 11 models accept cutoff dates (walk-forward ready)
  [OK] india model factory: 11 models emitted
  [OK] usa model factory: 11 models · ensemble top_10 populated

  14 passed, 0 failed of 14
```

### Cumulative regression — 68/68 pass

| Suite | Result |
|---|---|
| Sprint 1 (backend validation) | 12/12 |
| Sprint 2 (canonical + market intel + AI) | 12/12 |
| Sprint 2.5 (feature store + AI) | 12/12 |
| Sprint 2.6 (feature intelligence + registry + promotion) | 18/18 |
| Sprint 2.7 (model factory + 11 models + ensemble) | 14/14 |
| **Total** | **68/68** |

### Backend validation after Sprint 2.7

| Market | Before | After |
|---|---|---|
| India | 34 datasets · PASS · 0.916 | **38 datasets · PASS · 0.912** |
| USA | 45 datasets · PASS · 0.918 | **49 datasets · PASS · 0.916** |

### Per-market Model Factory (today)

**USA (Dow 30 · 30 tickers · 47 selected features):**
```
ran 11 models
ensemble: 11 models × 30 tickers scored
AI Analyst: 11 models registered · 11 ready for ensemble · 2 flagged for review
```

**India (228 tickers · 4 selected features — India feature coverage still limited):**
```
ran 11 models
ensemble: 11 models × 228 tickers scored
AI Analyst: 11 models registered · 11 ready for ensemble · 10 flagged for review
             (many flagged because India lacks bar/fundamentals coverage for
              most universe tickers — data gap, not model defect)
```

### Orchestrator wiring

| Market | Before | After |
|---|---|---|
| India | 24 steps | **25 steps** |
| USA | 27 steps | **28 steps** |

---

## Walk-forward compatibility (verified)

- Every model's `predict(features, cutoff)` accepts a cutoff date (`test_models_accept_cutoff_parameter`)
- Every prediction is deterministic on identical input (`test_predictions_deterministic`)
- Every model stamps into `model_registry.jsonl` with `schema_fingerprint` — future walk-forward can reconstruct which model version was in effect at any freeze date
- Feature dependencies flow from `selected_features.json` (Sprint 2.6) — replaying at a past date requires only re-selecting features at that cutoff

---

## Human-in-the-loop enforcement (extends Sprint 2.6)

- Every model registered as EXPERIMENTAL by default — the ensemble includes them (v0), but the `approval_status` field is honest
- Promotion to APPROVED requires operator invocation of `approve_model()` in `backend/promotion/promotion_gate.py` with WF metrics evidence
- AI Model Analyst NEVER emits `buy`/`sell`/`promote` — only descriptive narrative + ensemble participation proposals
- Ensemble weight strategy is data-driven only (equal-weight now, WF-weighted later); operator retains YAML override

---

## Files created

**Framework (backend/model_factory/):**
- `__init__.py`
- `model_base.py`
- `model_intelligence.py`
- `ensemble.py`
- `factory.py`
- `models/__init__.py` + 11 model files

**AI agent:**
- `backend/ai/model_analyst.py`

**Per-market runners:**
- `india/model_factory/__init__.py`
- `india/model_factory/run.py`
- `usa/research/model_factory/__init__.py`
- `usa/research/model_factory/run.py`

**Tests + docs:**
- `backend/tests/test_sprint27.py`
- `docs/AEGIS_SPRINT2_7_REPORT.md`

## Files modified

- `scripts/aegis_daily_v2.py` — +1 step
- `usa/scripts/usa_daily.py` — +1 step
- `india/backend_validation/datasets.yaml` — +4 entries
- `usa/backend_validation/datasets.yaml` — +4 entries
- `ux/dashboard/frontend/index.html` — Model Ensemble tile
- `usa/dashboard/frontend/index.html` — Model Ensemble tile
- `.github/workflows/aegis-ci.yml` — Sprint 2.7 regression step

---

## What Sprint 2.7 does NOT do

- Does not modify the (old) Recommendation Engine
- Does not train ML models — models are rule-based scoring today. Sprint 9 (Learning Engine) can swap internals without changing the interface.
- Does not compute win_rate / precision / recall — those need the learning corpus (Stage 0.5 Finding 1: corpus is frozen). Metrics return `insufficient_history` honestly.
- Does not implement Research Factory or Investment Intelligence — those are Sprints 2.8 and 3.
- Does not enable WF-weighted ensemble — that's Sprint 9 once WF runner exists

---

## Dependencies unblocked

| Downstream sprint | Now consumes |
|---|---|
| Sprint 2.8 · Research Factory (proposed next) | `model_metrics.json` — knows which models to hypothesize improvements for |
| Sprint 3 · Investment Intelligence | `ensemble.json` — the top-10 ticker score, not raw features |
| Sprint 7 · Recommendation Engine | Ensemble output stamped with `model_registry` for audit |
| Sprint 9 · Learning Engine | Populates SHAP + regime metrics per model · promotes weight configurations |
| Walk-Forward | Every model replayable at any cutoff — deterministic verified |

---

## Confidence checklist

- [x] Both markets simultaneously
- [x] Recommendation Engine NOT modified
- [x] 11 model types: Momentum, Trend, Value, Growth, Quality, Mean Reversion, News, Macro, Sector Rotation, Event Driven, AI Hybrid
- [x] Every model has business_rationale + economic_intuition (contract-tested)
- [x] Every model has feature_dependencies declared
- [x] Every model deterministic (contract-tested)
- [x] Every model accepts a cutoff (walk-forward ready)
- [x] Ensemble combines all models (verified 11 × 30 tickers)
- [x] Ensemble weights configurable + normalized
- [x] Model Intelligence metrics harness with graceful degradation
- [x] AI Model Analyst never promotes (contract-tested)
- [x] Model Registry stamps every model as EXPERIMENTAL
- [x] Dashboards updated (Model Ensemble tile both markets)
- [x] CI updated
- [x] Sprint 2.7 regression: 14/14 · cumulative 68/68 across S1+S2+S2.5+S2.6+S2.7
- [x] No TODOs, no placeholders

Sprint 2.7 report complete. Ready for operator sign-off before next sprint (Research Factory per your revised pipeline, or direct-to-Investment-Intelligence — your call).
