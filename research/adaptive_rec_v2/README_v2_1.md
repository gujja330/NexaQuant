# Adaptive Rec Engine · v2.1 · Intelligence Fusion

**Enhancement to Adaptive Rec Engine v2.0.** Fuses signals from every
upstream engine into a single Investment Intelligence Score with
per-dimension breakdown, conflict detection, and explainability.

No new engine. No new DEV module. Engine-version bump per ADR-005.

## Rationale

Every AEGIS engine produces a valuable signal independently. Before
v2.1 nothing combined them into a final decision — the operator had
to reconcile Research + Historical + Validation + Risk + DNA + KG +
Calibration + Learning + Explainability by hand.

v2.1 does this fusion deterministically, transparently, and with
every disagreement surfaced as a named conflict.

## The 10 dimensions

| # | Dimension | Source | Default Weight |
|---|-----------|--------|---:|
| 1 | Research         | `recommendations.json` (rollup DEV017-DEV020) | 15% |
| 2 | Historical       | `learning.parquet` (DEV025) | 15% |
| 3 | Validation       | `validation_v2_latest.json` (v2.0) | 10% |
| 4 | Risk             | `risk_capital_v2_latest.json` (v2.0) | 15% |
| 5 | Portfolio Fit    | `recommendations.json` (DEV022 rollup) | 10% |
| 6 | Knowledge Graph  | `entity_network.json` (DEV031-B) | 5% |
| 7 | DNA              | `recommendation_dna_feedback.json` (v1.5) | 10% |
| 8 | Calibration      | `confidence_calibration.json` (DEV029) | 5% |
| 9 | Learning         | `learning.parquet` (DEV025) | 5% |
| 10 | Explainability  | `recommendation_paths.json` (DEV031-B) | 5% |

Each dimension is scored 0-100. Missing sources produce `None`
(never fabricated). Weights normalise across available dimensions.

## Fusion → Decision

```
intelligence_score = Σ (normalised_weight_i × dimension_score_i)
```

Deterministic decision thresholds:

- 85+ → **Strong-Buy**
- 70-85 → **Buy**
- 55-70 → **Hold**
- 40-55 → **Reduce**
- <40 → **Avoid**

## Conflict Detection

7 rules across 3 severity tiers:

| Severity | Rule | Fires when |
|---|---|---|
| CRITICAL | `research_high_risk_low` | research >=75 AND risk <=40 |
| CRITICAL | `dna_high_validation_low` | dna >=75 AND validation <=40 |
| CRITICAL | `raw_buy_fusion_sell` | DEV023 says Buy but fusion says Reduce/Avoid |
| CRITICAL | `raw_sell_fusion_buy` | DEV023 says Sell but fusion says Buy/Strong-Buy |
| MEDIUM | `research_strong_validation_weak` | research >=75 AND 40 < validation <=60 |
| MEDIUM | `buy_but_historical_loser` | historical <=35 AND raw rec is buy-side |
| MEDIUM | `strong_buy_thin_portfolio_fit` | Strong-Buy AND portfolio_fit <=30 |
| MINOR | `wide_dimension_spread` | max - min across dimensions > 40 |
| MINOR | `many_missing_dimensions` | >=4 dimensions missing |

Every conflict names the rule so the operator can trace which check fired.

## Explainability

Every recommendation ships with:

- **Why this recommendation?** — top-3 dimensions with highest score + their explanations
- **Why not stronger?** — bottom-3 dimensions holding it back + their explanations
- **Contribution table** — per-dimension weight, normalised weight, and dollar contribution to the final score
- **Conflict register** — every rule that fired, with severity + rationale

## Configurable weights

Drop a `reports/fusion_weights.json` file with a subset (or all) of
the 10 dimension names → weight overrides. Values not present retain
the default. Weights need not sum to 1.0 — fusion renormalises across
available dimensions automatically.

Example:
```json
{
  "research": 0.20,
  "risk": 0.20,
  "validation": 0.15,
  "historical": 0.15,
  "dna": 0.10,
  "portfolio_fit": 0.10,
  "knowledge_graph": 0.05,
  "calibration": 0.05
}
```

## Live results (2026-07-18 run · 208 recs)

- Decision distribution: **Reduce 188 · Hold 19 · Avoid 1** · zero Strong-Buy/Buy
- Conflicts: **32 CRITICAL · 1 MEDIUM · 208 MINOR** · 32 tickers with CRITICAL
- Top firing rules: `wide_dimension_spread` (208) · `raw_buy_fusion_sell` (32)

Interpretation: **v2.1 systematically downgrades DEV023's confidence when
the full evidence panel does not agree**. This is not a bug — it is
the fusion producing exactly what it was designed to produce. When
research says Buy, historical says thin evidence, validation is
insufficient, and DNA has no matching pattern, the fused score lands
in the 50-65 band. That maps to Reduce / Hold under the current
thresholds.

The operator can:
- Adjust `reports/fusion_weights.json` to weight the strongest signals higher.
- Adjust decision thresholds (edit `lib/fusion.py::DECISION_THRESHOLDS`).
- Interpret the CRITICAL raw_buy_fusion_sell conflicts as "review before acting" markers.

## Outputs (5)

- `reports/investment_intelligence.json` — full per-ticker report
- `reports/investment_intelligence.parquet` — flat table for downstream analysis
- `reports/intelligence_explanation.json` — top-20 + bottom-10 with why-panels
- `reports/intelligence_conflicts.json` — full conflict register + summary
- `reports/intelligence_summary.json` — one-page portfolio snapshot

## Governance

- Advisory only. Every dimension carries an explanation. Every
  conflict is named. Weights are configurable and transparent.
- Deterministic — same artifacts + same weights → same output.
- Does NOT modify DEV023 recommendations. The fusion score is
  parallel decision-support evidence, not an override.
- Fusion decision disagreements with DEV023 fire CRITICAL conflicts
  by design — the operator must reconcile before acting.

## Run

```
python research/adaptive_rec_v2/run_fusion.py
python research/adaptive_rec_v2/tests/test_fusion.py
```

## Dashboard

The Executive Dashboard now includes a `/intelligence` route with:
- Intelligence score + decision distribution
- Conflict severity counts
- Top-10 recommendations by fused score
- Top-5 CRITICAL conflicts
- Why-panel for the current top rec
- Fusion weights bar chart
- Stress-scenario table (from KG v1.6)

## Layout

```
research/adaptive_rec_v2/
  lib/
    features.py       — v2.0 (unchanged)
    model.py          — v2.0 (unchanged)
    metrics.py        — v2.0 (unchanged)
    reliability.py    — v2.0 (unchanged)
    dimensions.py     — v2.1 (10 dimension scorers)
    fusion.py         — v2.1 (weighted fusion + decision mapping)
    conflicts.py      — v2.1 (rule-based conflict detector)
  compute/
    engine.py         — v2.0 (unchanged)
    fusion_engine.py  — v2.1 (fusion orchestrator)
  publish/
    bundle.py         — v2.0 (unchanged)
    fusion_bundle.py  — v2.1 (5 fusion outputs)
  tests/
    test_smoke.py     — v2.0 (15 tests)
    test_fusion.py    — v2.1 (37 tests)
  run.py              — v2.0 CLI
  run_fusion.py       — v2.1 CLI
```
