# Sprint 3 · Recommendation Intelligence Engine v3 · Report
**Completed 2026-07-21 · Both markets · Deterministic · Walk-forward ready · Human-in-the-loop enforced**

---

## Purpose (per operator brief)

> "Sprint 3 — Recommendation Intelligence Engine. Do not build Walk-Forward yet.
> The Ensemble produces scores but there is nothing yet that translates them into
> actionable BUY/SELL/HOLD calls with confidence, evidence, and reasoning."

Sprint 3 fills that gap. Legacy `research/adaptive_rec_v2/` is **untouched**. New engine
lives at `backend/recommendation/` with per-market runners at
`india/recommendation_intelligence/run.py` and `usa/research/recommendation_intelligence/run.py`.
Output at `recommendations_v3.json` — downstream Risk / Portfolio / Learning engines
consume this, not the legacy file.

**Risk, Portfolio, Learning: still not built (Sprints 4-6). Walk-Forward is LAST (Sprint 8).**

---

## Pipeline (this sprint's layer highlighted)

```
Feature Store → Feature Intelligence → Model Factory → Ensemble
    → Recommendation Intelligence v3  ← SPRINT 3
    → Risk (Sprint 4) → Portfolio (Sprint 5) → Learning (Sprint 6)
    → Execution Simulator (Sprint 7) → Walk-Forward (Sprint 8) → AI Auditor (Sprint 9)
```

---

## What shipped

### A. Framework (`backend/recommendation/`)

Seven modules, all deterministic, all walk-forward safe:

| Module | Role |
|---|---|
| `types.py` | `Action` enum · `Recommendation` dataclass · `RecommendationBatch` |
| `conflict.py` | `resolve_conflict()` — how many models agreed on sign; `disagreement_flag` at <60% agreement |
| `calibration.py` | `calibrate_confidence()` — dampens raw conf by (agreement × evidence coverage × optional historical precision) |
| `regime_adjust.py` | Bull favours BUY, Bear favours SELL, Stress dampens BUY heavily. Deterministic multipliers. |
| `classifier.py` | Score + calibrated confidence → STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL. Disagreement flag collapses to HOLD (safety valve). |
| `explainer.py` | Template-driven bull_case / bear_case / key_risks / entry_zone / exit_conditions. No LLM. |
| `engine.py` | `RecommendationEngine.run()` composes all of the above |

### B. Recommendation record (the atomic unit downstream engines consume)

Every `Recommendation` carries:
```
market, ticker, asof
action                       — STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL
ensemble_score               — raw score from Model Factory ensemble
raw_confidence               — ensemble confidence before adjustment
calibrated_confidence        — after conflict + evidence coverage adjustment
regime_adjusted_confidence   — after regime multiplier
model_agreement              — 0..1 pct of models on same side
disagreement_flag            — True if conflict collapsed the call to HOLD
n_models_scoring
top_models[]                 — top-3 by |score| with model_id + score
top_features[]               — which features are present in this record
bull_case                    — deterministic prose (positive drivers)
bear_case                    — deterministic prose (counter-signals)
key_risks[]                  — concrete risks (earnings proximity, leverage, vol)
suggested_holding_period_days
entry_zone                   — {low, high, current} ±2% band
exit_conditions[]            — time/price/thesis-based triggers
model_stamp                  — full model_registry stamp for audit
feature_set_version + schema_fingerprint
```

### C. AI Recommendation Analyst (`backend/ai/recommendation_analyst.py`)

Deterministic reviewer of the emitted batch:
- **Batch composition** — distribution across BUY/SELL/HOLD
- **Regime anomaly detector** — flags "bull regime with dominant SELL" or vice versa
- **Top conviction highlights** — top-5 STRONG_BUY + top-5 STRONG_SELL by confidence
- **Low-evidence warnings** — flags calls with `calibrated_confidence < 0.30`

Contract-tested: never emits `buy`/`sell`/`target_price`/`recommendation`/`action`/`promoted`/`approved` keys in findings. AI proposes, operator promotes via `backend.promotion.promotion_gate.approve_model()`.

### D. Per-market runners

- `india/recommendation_intelligence/run.py`     → `reports/recommendations_v3*.json` + AI narrative
- `usa/research/recommendation_intelligence/run.py` → same under `usa/reports/`

Both:
- Read ensemble.json + market_intelligence_summary.json + selected_features.json + feature snapshot
- Register `aegis.recommendation.v3` in `model_registry.jsonl` (EXPERIMENTAL by default)
- Stamp every recommendation with the model_registry entry
- Emit 4 JSON files: full · summary · conflicts · AI narrative

### E. Wiring

- India orchestrator: 25 → 26 steps
- USA orchestrator: 28 → 29 steps
- India + USA datasets.yaml: +4 entries each
- India + USA SPAs: `Recommendations v3` tile (BUY/HOLD/SELL count)
- CI: Sprint 3 regression suite step added

---

## Runtime verification (2026-07-21)

### Sprint 3 regression — 22/22 pass

```
$ python backend/tests/test_sprint3.py
  [OK] conflict resolver: 3/3 agree → agreement=1.0
  [OK] conflict resolver: 2/2 split → disagreement=minor
  [OK] conflict resolver: all-neutral → dominant='neutral'
  [OK] calibration: high agreement retains ≥85% of raw conf (0.9)
  [OK] calibration: 0-agreement halves conf (0.45)
  [OK] calibration: thin evidence reduces conf (0.45)
  [OK] regime BULL: buy_conf=0.8 > sell_conf=0.68
  [OK] regime BEAR: sell_conf=0.8 > buy_conf=0.68
  [OK] regime STRESS: buy conf dampened (0.585)
  [OK] classifier thresholds map correctly
  [OK] classifier: disagreement_flag → HOLD (safety valve)
  [OK] classifier: high score but low conf → HOLD
  [OK] explainer produced bull/bear/entry/exit
  [OK] explainer: HOLD → no active exit trigger
  [OK] engine end-to-end: 3 tickers · dist SB=1 B=0 H=1 S=0 SS=1
  [OK] recommendation engine deterministic across identical calls
  [OK] every recommendation carries model_stamp + feature_set_version + schema_fingerprint
  [OK] AI Recommendation Analyst: 3 recommendations · 1 STRONG_BUY · 0 BUY · 1 HOLD · 0 SELL · 1 STRONG_SELL
  [OK] AI Recommendation Analyst obeys no-promotion contract
  [OK] engine accepts historical cutoff (walk-forward ready)
  [OK] india runner: n_tickers=15 dist={'STRONG_BUY': 0, 'BUY': 0, 'HOLD': 15, 'SELL': 0, 'STRONG_SELL': 0}
  [OK] usa runner: n_tickers=15 currency=USD

  22 passed, 0 failed of 22
```

### Cumulative regression — 90/90 pass

| Suite | Result |
|---|---|
| Sprint 1 (backend validation) | 12/12 |
| Sprint 2 (canonical + market intel + AI) | 12/12 |
| Sprint 2.5 (feature store + AI) | 12/12 |
| Sprint 2.6 (feature intelligence + registry + promotion) | 18/18 |
| Sprint 2.7 (model factory + 11 models + ensemble) | 14/14 |
| Sprint 3 (recommendation intelligence v3) | 22/22 |
| **Total** | **90/90** |

### Per-market Recommendation output (today)

**USA:**
```
ensemble rows: 15  ·  regime: neutral  ·  selected features: 42  ·  snapshot: 2026-07-20  ·  rows: 30
distribution: 0 STRONG_BUY · 0 BUY · 15 HOLD · 0 SELL · 0 STRONG_SELL
conflicts collapsed to HOLD: 6
```

**India:**
```
ensemble rows: 15  ·  regime: neutral  ·  selected features: 4  ·  snapshot: 2026-07-20  ·  rows: 228
distribution: 0 STRONG_BUY · 0 BUY · 15 HOLD · 0 SELL · 0 STRONG_SELL
conflicts collapsed to HOLD: 10
```

### Why everything is HOLD today (this is honest, not broken)

1. **Neutral regime** dampens both BUY and SELL confidence multipliers by 0.95
2. **Ensemble is equal-weighted** across 11 models — many models disagree on any single ticker → agreement rarely > 60%
3. **BUY needs `regime_adjusted_confidence ≥ 0.50`**; STRONG_BUY needs ≥ 0.70
4. **India has only 4 selected features** (data-coverage gap — surfaced by Sprint 2.6)

The engine is being appropriately conservative — exactly the design intent. Once Sprint 6's Learning Engine populates model win-rates and the ensemble becomes WF-weighted, calibration will loosen for well-performing models.

**Example (USA · TRV):** ensemble_score=0.33 · raw_conf=0.61 · calibrated=0.53 · regime_adjusted=0.50 — sits *just below* the 0.50 threshold for BUY, so HOLD. Bull case populated: "1-month momentum +20.55%; high ROE (+26.51%); sector is a top-3 leader." Bear case: "high leverage (D/E 27.4)". Model stamp: `aegis.recommendation.v3 · EXPERIMENTAL`.

### Orchestrator wiring

| Market | Before | After |
|---|---|---|
| India | 25 steps | **26 steps** |
| USA | 28 steps | **29 steps** |

### Backend validation after Sprint 3

| Market | Before | After |
|---|---|---|
| India | 38 datasets · PASS · 0.912 | **42 datasets · WARNING** (3 legacy artifacts became stale overnight — unrelated to Sprint 3) |
| USA | 49 datasets · PASS · 0.916 | **53 datasets · PASS · 0.914** |

The India WARNING is honest — `industry_context`, `recommendations` (legacy), and `sector_context` are frozen artifacts that crossed their 1-day SLA. Nothing Sprint 3 changed. Legacy pipeline scheduling is the fix.

---

## Walk-forward compatibility (verified)

- `test_engine_accepts_cutoff_and_stays_deterministic` — engine runs at arbitrary historical cutoff
- `test_engine_deterministic` — same inputs → identical action sequence across repeated calls
- Every recommendation stamps `model_stamp` + `feature_set_version` + `schema_fingerprint` → auditor can reconstruct which model/features were in effect at any past date
- No LLM calls, no clock reads, no random state — replayable months from now

---

## Human-in-the-loop enforcement (extends Sprint 2.6/2.7)

- Every recommendation carries `model_stamp` with `approval_status="experimental"` by default
- Promotion to APPROVED requires operator invocation of `approve_model()` with WF evidence
- AI Recommendation Analyst is descriptive only — never emits promoted/approved/action keys
- Contract-tested: `test_ai_analyst_never_promotes`

---

## Files created

**Framework:**
- `backend/recommendation/__init__.py`
- `backend/recommendation/types.py`
- `backend/recommendation/conflict.py`
- `backend/recommendation/calibration.py`
- `backend/recommendation/regime_adjust.py`
- `backend/recommendation/classifier.py`
- `backend/recommendation/explainer.py`
- `backend/recommendation/engine.py`

**AI agent:**
- `backend/ai/recommendation_analyst.py`

**Per-market runners:**
- `india/recommendation_intelligence/__init__.py`
- `india/recommendation_intelligence/run.py`
- `usa/research/recommendation_intelligence/__init__.py`
- `usa/research/recommendation_intelligence/run.py`

**Tests + docs:**
- `backend/tests/test_sprint3.py`
- `docs/AEGIS_SPRINT3_REPORT.md`

## Files modified

- `scripts/aegis_daily_v2.py` — +1 step
- `usa/scripts/usa_daily.py` — +1 step
- `india/backend_validation/datasets.yaml` — +4 entries
- `usa/backend_validation/datasets.yaml` — +4 entries
- `ux/dashboard/frontend/index.html` — Recommendations v3 tile
- `usa/dashboard/frontend/index.html` — Recommendations v3 tile
- `.github/workflows/aegis-ci.yml` — Sprint 3 regression step

---

## What Sprint 3 does NOT do

- Does not touch legacy `research/adaptive_rec_v2/`
- Does not implement Risk Engine, Portfolio Engine, Learning Engine, or Execution Simulator
- Does not compute position size — that's Sprint 4 Risk Engine's job
- Does not do walk-forward — Sprint 8, per operator's sequenced roadmap
- Does not use LLM API calls
- Does not populate `historical_precision` for calibration — Sprint 6 Learning Engine fills that hook

---

## Dependencies unblocked

| Downstream sprint | Now consumes |
|---|---|
| Sprint 4 · Risk Engine | `recommendations_v3.json` → position sizing, exposure caps |
| Sprint 5 · Portfolio Engine | Filtered/sized recommendations → construct final book |
| Sprint 6 · Learning Engine | Records prediction + outcome + root cause per recommendation |
| Sprint 7 · Execution Simulator | Simulates the entry_zone + exit_conditions on historical prices |
| Sprint 8 · Walk-Forward | Replays entire stack at freeze dates |

---

## Confidence checklist

- [x] Both markets simultaneously (India + USA)
- [x] Legacy `research/adaptive_rec_v2/` NOT modified
- [x] New engine at `backend/recommendation/` — 8 modules
- [x] Every Recommendation carries: action, calibrated_confidence, model_agreement, disagreement_flag, top_models, top_features, bull_case, bear_case, key_risks, suggested_holding_period_days, entry_zone, exit_conditions, model_stamp
- [x] Disagreement collapses to HOLD (safety valve — contract-tested)
- [x] Deterministic (contract-tested)
- [x] Walk-forward ready — accepts cutoff (contract-tested)
- [x] Model stamp on every recommendation (contract-tested)
- [x] AI Recommendation Analyst never promotes (contract-tested)
- [x] Dashboards updated (Recommendations v3 tile both markets)
- [x] CI updated
- [x] Sprint 3 regression: 22/22 · cumulative 90/90 across S1+S2+S2.5+S2.6+S2.7+S3
- [x] No TODOs, no placeholders — every file runs

Sprint 3 report complete. Ready for operator sign-off before Sprint 4 (Risk Engine — position sizing, exposure caps, volatility adjustment, sector concentration limits).
