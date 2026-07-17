# DEV029 — Confidence Calibration & Probability Engine

**Sprint 15 (single).** Fixes overconfidence detected in DEV025 (ECE 0.29) and
confirmed by DEV027 (218 overconfidence diagnoses across 677 total).

> Constitutional: Advisory-only, evidence-driven, no manual tuning.
> All 5 methods are competed on held-out data; the best is chosen automatically.

---

## What it does

A confidence of 80% should historically win about 80% of the time. Today
prism's raw confidence is off — 80%-labelled trades win ~55% of the time.
DEV029 learns the mapping `raw_confidence -> true_probability` from history.

Five calibration methods are fitted on a time-based train split; the method
with lowest Brier score on the held-out test is selected.

| Method | Best when |
|---|---|
| Platt scaling | Roughly linear miscalibration; small samples |
| Isotonic regression | Monotone but non-linear miscalibration; large samples |
| Histogram binning | Discrete confidence buckets; interpretable |
| Beta calibration | S-shaped miscalibration; heavy tails |
| Temperature scaling | Single-parameter softmax sharpness fix |

---

## Inputs

- `reports/learning.parquet` (from DEV025) — 1060 completed trades with
  columns `entry_date`, `confidence` in [0.5, 1.0], `is_winner` in {0, 1}.

## Outputs (6)

Written to `reports/`:

- `confidence_calibration.json` — headline (raw vs calibrated metrics,
  best method, reliability curves, governance note).
- `calibration_metrics.json` — scoreboard across all 5 methods on test set.
- `reliability_diagram.json` — raw + calibrated reliability curves for plotting.
- `confidence_bias.json` — per-bin bias analysis + warnings (over/underconfident,
  sparse regions, insufficient evidence).
- `calibration_history.json` — append-only history of every calibration run.
- `confidence_calibration.parquet` — per-trade `(raw, calibrated, is_winner)`.

Also appended to:
- `data/market_intelligence/derived/calibration_history.parquet`

## Metrics

| Metric | Interpretation | Direction |
|---|---|---|
| Brier score | MSE of prediction vs outcome | lower better |
| Log loss | Cross-entropy | lower better |
| ECE | Weighted mean bin gap | lower better |
| MCE | Worst-bin gap | lower better |
| Reliability | Sum of squared per-bin gap | lower better |
| Sharpness | Variance of predictions | higher = bolder |
| Confidence bias | Mean pred - mean actual | 0 ideal; +ve = overconfident |

## Governance

**Retrain only when new data is available; drift-based.** Confidence
calibration is a one-shot correction from history, not a live-tuned parameter.
No auto-application to the recommendation engine — outputs are advisory
under ARCH001A Article V clause 5.1.

## Run

```
python research/confidence_calibration/run.py
python research/confidence_calibration/tests/test_smoke.py
```

## Layout

```
research/confidence_calibration/
  lib/
    methods.py   — 5 calibrators (Platt, isotonic, histogram, beta, temperature)
    metrics.py   — Brier / log loss / ECE / MCE / reliability / sharpness / bias
  compute/
    engine.py    — orchestration: split, fit, select best, warn, history
  publish/
    bundle.py    — 6 output files
  tests/
    test_smoke.py
  run.py         — CLI
```

## Why now

DEV027 diagnosed **overconfidence** as the top failure mode (218 of 677
diagnoses fired). DEV025 reported ECE = 0.29 — meaning bins are on
average 29 percentage points miscalibrated. DEV029 is the direct fix.
