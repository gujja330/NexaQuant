# validation/ — per-capability validators

**Constitution reference:** Articles 25 · 26 · 27 · 28 · 29.

Every AEGIS capability MUST have a validator here. Validators run in CI. Any validator failure blocks the merge.

## Structure

```
validation/
  data_validation/           OHLC integrity · duplicates · NaN · delistings
  feature_validation/        mathematical correctness per feature
  factor_validation/         factor library null-rate · dispersion · monotonicity
  indicator_validation/      shared indicators: RSI/ATR/ADX/MACD/EMA/SMA/VOL/BETA
  fundamentals_validation/   latest-vs-as-of · look-ahead detection
  technical_validation/      feature-store technical output · scale sanity
  macro_validation/          regime coherence · symbol-map completeness
  sector_validation/         taxonomy · schema · rotation math
  model_validation/          determinism · rank/scale · confidence semantics
  recommendation_validation/ action classifier · calibration · disagreement handling
  portfolio_validation/      size limits · cash policy · turnover · concentration
  replay_validation/         byte-equality · frozen-clock · resume determinism
  benchmark_validation/      Wilson CI · sample-size gates · verdicts
  report_validation/         schema fingerprint · required fields · staleness
  telegram_validation/       dedup key · concurrency · retry semantics
  dashboard_validation/      data-source pinning · cache-bust · schema alignment
  workflow_validation/       cron collision · concurrency block · publish-marker order
  contract_validation/       sealed contracts UNTOUCHED · fingerprint preserved
  schema_validation/         producer-owner registry · consumer compatibility
  performance_validation/    per-step budget · memory · zero-caching audit
  integration_validation/    E2E chain integrity · 32-step India · 35-step USA
  dependency_validation/     import direction · forbidden-import matrix
  capability_validation/     20-field template completeness
```

## Convention

`validation/<domain>_validation/<engine>_validator.py`

Each validator implements:

```python
from validation.base import BaseValidator, ValidationResult

class ExampleValidator(BaseValidator):
    def validate(self, ctx) -> ValidationResult:
        ...
```

Wave 4 · D8 wires every validator into CI. Wave 5 · Phase 3 creates skeleton.
