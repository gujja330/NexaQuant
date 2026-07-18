# Adaptive Recommendation Engine · v2.0

**Confidence signal rebuild — P0 in [PHASE2_MASTER_ROADMAP.md](../../docs/PHASE2_MASTER_ROADMAP.md).**

Supersedes the v1.4 raw-confidence pass-through (DEV023 + DEV029). Every
output is advisory. Determinism enforced (fixed random_state, sorted
categorical columns, fixed iteration counts).

Governed by [ENGINE_EVOLUTION_GUIDE.md](../../docs/ENGINE_EVOLUTION_GUIDE.md)
and [DESIGN_DECISIONS.md](../../docs/DESIGN_DECISIONS.md). Reads
DEV017–DEV031 outputs; produces its own artifacts.

---

## What it does

1. Loads DEV025 `learning.parquet` (1,060+ completed trades).
2. Builds a feature matrix of numeric dimensions + one-hot sector/industry.
3. Time-based split (70% train · 30% test) — no look-ahead.
4. Fits three candidate signal models with fixed determinism:
   - `v1.4_baseline_raw_confidence` — pass-through of DEV023's raw `confidence`.
   - `hgb_v2.0` — HistGradientBoosting (random_state=42, max_iter=200).
   - `logreg_v2.0` — regularised LogReg (C=0.3, random_state=42).
5. Evaluates on the held-out test set with the full ADR-013 metric panel.
6. Selects the best model by a **top-K identification** rule (weighted
   Precision@10 + Precision@5) — not by global calibration. Rationale:
   the operator holds the top-K by decision score; ranking accuracy in
   that tail is worth more than global probability calibration.
7. Runs the PHASE2 §6 exit criterion — Strong-Buy WR > Buy WR > Hold WR
   > Sell WR — and reports pass/fail with spread.

## Selection rule

```
score(model) = Precision@10(model) + 0.5 · Precision@5(model)
```

Argmax across candidates. Ties broken by insertion order.

## Outputs

Written to `reports/`:

- `adaptive_rec_v2_signal.json` — headline + governance + delta-vs-baseline
- `adaptive_rec_v2_scoreboard.json` — full model comparison
- `adaptive_rec_v2_feature_importance.json` — top-K features from best model
- `adaptive_rec_v2_reliability.json` — baseline + best reliability curves
- `adaptive_rec_v2_signal.parquet` — per-trade `(raw_confidence, v2_signal, is_winner, return_pct)`
- `adaptive_rec_v2_migration.md` — v1.4 → v2.0 migration guide (human-readable)

## Governance

- Advisory only. v2.0 output is a top-K identifier, not a calibrated
  probability. Do NOT expose the raw v2.0 output outside a ranked context.
- To surface as an operator-facing confidence percentage, chain through
  DEV029's Platt scaling on the v2.0 signal.
- The v1.4 recommendation logic remains in place until the operator
  explicitly promotes v2.0. This module produces the evidence to make
  that promotion decision defensible.

## Run

```
python research/adaptive_rec_v2/run.py
python research/adaptive_rec_v2/tests/test_smoke.py
```

## Layout

```
research/adaptive_rec_v2/
  lib/
    features.py       — feature matrix + imputation + time split
    model.py          — 3 signal models (baseline / HGB / LogReg)
    metrics.py        — full 13-metric panel + Precision@K
    reliability.py    — reliability curves + tier discrimination
  compute/
    engine.py         — orchestration
  publish/
    bundle.py         — 6 outputs
  tests/
    test_smoke.py
  run.py
```
