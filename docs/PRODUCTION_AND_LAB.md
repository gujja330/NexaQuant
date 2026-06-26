# AEGIS — Production vs Research Lab (operating model)

> Adopted at the v1.3 freeze. AEGIS is a **portfolio-allocation engine** with strong explainability and
> evidence tracking — **not** an alpha-discovery engine (the score decomposition proves Risk/Vol is the
> dominant driver on every pick). Production is now frozen; all new work happens in the Lab and must
> *earn* its way into production.

## Two halves, deliberately separated

### 🛡️ AEGIS Production — `1.x Stable` (FROZEN)
Owns: dynamic tradable universe · portfolio construction (HRP) · regime exposure · dynamic
holding/sizing/review · risk profiles · explainability (suitability decomposition + attribution) ·
evidence loop (scorecard, calibration, MFE/MAE) · daily automation · change explanation.

Frozen tags: `v1.0-price-baseline`, `v1.1-production`, `v1.2-phaseA`, `v1.3-explainability`.
Production changes **only** when a Lab experiment demonstrably beats the frozen baseline.

### 🔬 AEGIS Research Lab — `LAB-NNN` experiments
Owns: new datasets (earnings, fundamentals, flows, announcements, revisions), feature engineering,
AI ranking (learning-to-rank), and any model changes. Lives in `india/ai_lab/` + the `ai-lab` branch +
the data-layer gate (`india/data_layer_gate.py`). **Nothing reaches production automatically.**

## The promotion pipeline (every dataset / model goes through this)

```
Raw Dataset → Validation → Feature Engineering → Information Coefficient (IC)
            → Incremental Lift (RQS) → Walk-Forward → Forward Paper → Production Gate
```

Gate to promote: beats the frozen baseline out-of-sample by a margin, holds across folds, survives a
trial-count penalty (DSR), then survives forward paper. Otherwise: documented as "tested, not adopted."

## Dataset acquisition order (one at a time — validate, then move on)
1. Quarterly earnings surprises
2. Point-in-time fundamentals
3. NSE corporate announcements
4. FII / DII flows
5. Bulk / block deals
6. Mutual-fund holdings
7. Analyst estimate revisions

## Where AI belongs
NOT a neural net on the risk score. The first AI is a **learning-to-rank** model over a *richer feature
set* (technicals + sector + earnings + fundamentals + events) predicting **relative ranking**, not price.
It only graduates if it beats the frozen baseline through the pipeline above.

## Effort allocation from here
~80–90% data acquisition + validation · ~10–20% explainability/maintenance · ~0% more price-side model.
