# AEGIS · Wave 5 · Phase 9 · Capital Intelligence (Capital Rotation + Opportunity Cost)
### 🔒 SHIPPED 2026-07-27 · code + tests + validators + docs · Constitution-compliant

**Purpose:** deliver two NEW first-class engines that operator flagged as ⭐⭐⭐⭐⭐ priority in v2.2 audit:
- **Capital Rotation Engine** — rotate on remaining-expected-upside vs alternatives (not time-based)
- **Opportunity Cost Engine** — every HOLD justifies "why not rotate"

## What Shipped

### Capital Rotation Engine

- **Package:** `backend.recommendation.capital_rotation`
- **Types:** `Position` · `Candidate` · `RotationAction` (KEEP/ADD/TRIM/EXIT/ROTATE) · `RotationDecision` · `RotationPlan`
- **Core functions:** `keep_score(p)` · `candidate_score(c, sector_strength, macro_gate)` · `macro_gate_multiplier(regime)` · `decide_action(keep, best_cand)` · `compute_rotation_plan(...)`
- **Class:** `CapitalRotationEngine(market)` — deterministic, walk-forward safe
- **Schema fingerprint:** `aegis.capital_rotation.v1.20260727` (Article 21 compliant)

**Score formulas (Wave 5 authoritative):**
```
keep_score(p)      = 0.35·upside + 0.20·conf_delta + 0.15·rank_delta + 0.15·sector + 0.15·pnl
candidate_score(c) = (0.40·upside + 0.25·conf + 0.20·rank + 0.15·sector) × macro_gate
macro_gate         = {risk_on:1.0, neutral:0.9, risk_off:0.5, stress:0.3, recession_warning:0.5, unknown:0.85}

thresholds:
  EXIT   if keep_score  < -0.20
  TRIM   if keep_score  < +0.10  (trim_fraction = 0.5)
  ROTATE if best_candidate_score − keep_score > +0.25
  else KEEP
```

### Opportunity Cost Engine

- **Package:** `backend.recommendation.opportunity_cost`
- **Types:** `OpportunityCostEnrichment` (hold_ticker · oc_next_best_ticker · oc_next_best_score · oc_expected_alpha_delta · oc_reason_not_to_rotate)
- **Class:** `OpportunityCostEngine(rotate_edge_threshold=0.25)`
- **API:** `enrich_holds(holds, candidates, rotate_edge_threshold=0.25)`
- **Schema fingerprint:** `aegis.opportunity_cost.v1.20260727`
- **Sector-preference logic:** picks same-sector candidate if available, else best overall
- **Three reason classes:** `opportunity_cost_high` (edge > threshold) · `hold justified` (marginal edge) · `hold optimal` (no better candidate)

### Tests

**File:** `backend/tests/test_wave5_capital_rotation.py`

**15/15 tests green:**
- Determinism (identical inputs → identical outputs)
- Schema fingerprint present
- 4 threshold decision tests
- Macro gate coverage all 6 regimes
- Score bounds (keep + candidate)
- End-to-end producing all action types
- Opportunity cost: schema · high-edge flag · hold-when-no-edge · sector preference · determinism

### Validators

- `validation/recommendation_validation/capital_rotation_validator.py` — validates serialized RotationPlan (all fields present · valid actions · bounded scores · ROTATE has candidate_ticker · schema_fingerprint match)
- `validation/recommendation_validation/opportunity_cost_validator.py` — validates OC enrichment (all 5 fields present · schema fingerprint · non-empty reason)

## Constitution Compliance

| Article | Status |
|:---:|:---:|
| 14 · Capability = discrete institutional function | ✅ two capabilities |
| 15 · 20-field Cap Map entry | ✅ populated in Phase 4 Cap Map |
| 21 · schema_fingerprint | ✅ both engines carry it |
| 25 · Every capability has validator | ✅ both validators shipped |
| 26 · Validator location `validation/<domain>_validation/` | ✅ |
| 30 · One canonical implementation | ✅ single engine per capability |
| 40 · Tests per capability | ✅ `test_wave5_capital_rotation.py` (dual-capability coverage acceptable per shipping cadence) |
| 41 · Regression preserved | ✅ 15 new tests · pre-existing 280+ unaffected |
| 62 · Dual-market | Engine is market-parameterized · `CapitalRotationEngine(market)` |
| 68 · Type hints on public signatures | ✅ |
| 91 · Deterministic (byte-equality contract) | ✅ tested `test_capital_rotation_deterministic` + `test_opportunity_cost_deterministic` |

## Integration Path (post-Phase-9)

**Wave 5 Phase 14 (Delivery Platform):**
- Add rotation plan tile to Executive Dashboard
- Add rotation alerts to Telegram morning brief
- Route `reports/rotation_plan.json` into daily orchestrator (`scripts/aegis_daily_v2.py` new step post-`decision_center`)

**Wave 5 Phase 15 (Platform Services):**
- Wire into `aegis_daily_v2.py` + `usa_daily.py` after portfolio step
- Enable `--frozen-clock` for byte-equal replay
- Enable append-only history at `reports/history/rotation_plan.parquet`

## Definition of Done · Phase 9

- [x] Capital Rotation Engine · Constitution-compliant · deterministic · fingerprinted
- [x] Opportunity Cost Engine · Constitution-compliant · deterministic · fingerprinted
- [x] 15/15 tests green
- [x] 2 validators created in validation/recommendation_validation/
- [x] Sealed contracts UNTOUCHED
- [x] MON001 fingerprint preserved
- [x] Documented in Cap Map + this Phase 9 doc

**End of Phase 9 · SHIPPED 2026-07-27.**
