# AEGIS · Wave 5 · Phase 10 · Portfolio Attribution
### 🔒 SHIPPED 2026-07-27 · code + 9 tests + validator + docs

**Purpose:** every position's realized return decomposed into 13 factor contributions.

## What Shipped

**Package:** `backend.portfolio.monitoring.attribution`
**Types:** `PositionAttribution` · `PortfolioAttribution` · `AttributionSource` (enum)
**Constants:** `ATTRIBUTION_FACTORS` = 13 factors:
```
momentum · value · quality · growth · sector · macro · risk ·
fundamentals · news · corp_actions · execution · learning · residual
```
**Class:** `PortfolioAttributionEngine(market)` — deterministic
**API:** `compute_attribution(market, positions, asof, run_utc)`
**Schema fingerprint:** `aegis.portfolio_attribution.v1.20260727`

## Algorithm

Given per-position `realized_return_pct` + `factor_weights` (from ensemble model contributions):

```
For each position:
    tot_abs = sum(|weight| for known factors excluding residual)
    if tot_abs ≈ 0:
        contribs = {residual: realized}
    else:
        for each factor:
            contribs[factor] = (weight / tot_abs) * realized
        contribs[residual] = realized - sum(attributed)
    ASSERT sum(contribs) == realized (up to float precision)
```

Aggregate portfolio-level contribution = sum across all positions.

## Tests

**File:** `backend/tests/test_wave5_portfolio_attribution.py`

**9/9 tests green:**
- Schema fingerprint present
- Deterministic (identical inputs → identical outputs)
- Contributions sum to realized return per position (reconciliation invariant)
- No-signal case → 100% residual
- Negative weights reduce contribution correctly
- All 13 factors present in aggregate
- Market required (empty string raises)
- Scales to 50 positions
- Dual-market (India + USA · same fingerprint)

## Validator

`validation/portfolio_validation/attribution_validator.py` — reconciliation invariant enforced (sum of contributions per position must equal realized_return within 1e-3).

## Constitution Compliance

| Article | Status |
|:---:|:---:|
| 15 · 20-field Cap Map entry | ✅ populated |
| 21 · schema_fingerprint | ✅ |
| 25 · Every capability has validator | ✅ |
| 30 · One canonical implementation | ✅ |
| 40 · Tests per capability | ✅ |
| 62 · Dual-market parameterized | ✅ |
| 68 · Type hints | ✅ |
| 91 · Deterministic | ✅ tested |

## Integration Path

- **Wave 5 Phase 15 (Platform):** wire into daily orchestrator after `portfolio_engine` step
- **Wave 5 Phase 14 (Delivery):** attribution tile in Executive Dashboard · weekly digest in Telegram
- **Consumers:** Explainability layer (D4) · Champion/Challenger analysis (D6)

## Definition of Done · Phase 10

- [x] Portfolio Attribution Engine · deterministic · fingerprinted · walk-forward safe
- [x] 9/9 tests green
- [x] Validator with reconciliation invariant
- [x] Sealed contracts UNTOUCHED
- [x] Documented in Cap Map + this doc

**End of Phase 10 · SHIPPED 2026-07-27.**
