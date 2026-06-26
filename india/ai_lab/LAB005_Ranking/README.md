# LAB-005 — Learning-to-Rank

**Hypothesis:** an ML ranker over a *rich* feature set (technicals + sector + the KEPT LAB datasets —
earnings, fundamentals, events, flows) predicts **relative ranking** better than the hand-weighted
suitability score. Predicts ranking, **never price**.

**Why it runs LAST:** on price features alone it does not beat the baseline (already shown — see below).
It only has a chance once LAB-001..004 have contributed *kept* non-price features.

**Harness (built):** `india/ai_lab/rank_model.py` (on the `ai-lab` branch) — LightGBM ranker, walk-forward,
purged, scored by the same RQS metric as the baseline. To run it on enriched features, add the kept LAB
columns to its feature list and re-run.

**Result so far (price-only):** RQS 0.504 vs baseline 0.510 → **does not clear the gate** (expected).
This is recorded honestly in `experiments.yaml` (LAB-005, walk_forward: FAIL).

**Promotion:** beat frozen baseline OOS + hold across folds + DSR + forward paper. Only then to production.

**Status:** harness-built; waiting on KEPT non-price features from LAB-001..004.
