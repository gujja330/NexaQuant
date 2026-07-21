# Sprint 4 · Risk Engine · Report
**Completed 2026-07-21 · Both markets · Deterministic · Walk-forward ready · Human-in-the-loop enforced**

---

## Purpose

Convert Sprint 3's Recommendation Intelligence v3 (BUY/SELL/HOLD calls) into **sized positions with explicit risk budgets**. First engine downstream of the recommendation layer that produces a portfolio-shaped output.

Per the locked Phase 2 architecture (`docs/AEGIS_PHASE2_ARCHITECTURE.md` §"Sprint 4 · Risk Engine"). Legacy `research/risk_capital_v2/` UNTOUCHED — this is the new engine at `backend/risk/`.

**Portfolio Engine, Learning Engine, Execution Simulator, Walk-Forward, AI Auditor, Research Factory: still not built (Sprints 5-10).**

---

## What shipped

### A. Framework (`backend/risk/`)

Seven deterministic modules composed by the engine:

| Module | Role |
|---|---|
| `types.py` | `SizedPosition`, `RiskBudget`, `RiskReport`, `CapReason` enum |
| `sizing.py` | Kelly-fractional formula + confidence-tier multiplier |
| `vol_adjustment.py` | Inverse-vol size scaling + VIX regime dampener |
| `exposure_caps.py` | Per-ticker cap + per-sector cap + cap-reason chooser |
| `concentration.py` | HHI + top-K concentration |
| `var_cvar.py` | Parametric 95% VaR + CVaR (zero-corr approximation) |
| `engine.py` | `RiskEngine.run()` composes all of the above |

### B. Sizing pipeline (per active recommendation)

```
edge = confidence × |ensemble_score| × direction × VIX_multiplier
kelly = clamp(edge / vol², [-max_kelly, +max_kelly])
size_by_conf = kelly × confidence_tier_multiplier[action]
size_by_vol = size_by_conf × min(4.0, max(0.25, target_vol / ticker_vol))
target_weight = min(size_by_vol, per_ticker_cap, sector_headroom)
```

Every position records which constraint bounded it (`cap_reason`): KELLY / PER_TICKER_CAP / SECTOR_CAP / VOL_CAP / CONFIDENCE_GATE / DISAGREEMENT / SHORT_DISABLED / NOT_CAPPED.

### C. `SizedPosition` — the atomic output

```
market · ticker · action · ensemble_score · confidence
target_weight (signed) · target_notional
risk_budget_bps
stop_loss_pct · take_profit_pct
vol_20d_annualised · kelly_fraction
cap_reason
entry_reference (price)
model_stamp (from model_registry)
schema_fingerprint · feature_set_version
```

### D. `RiskReport` — portfolio-level aggregation

```
n_positions · n_long · n_short
gross_exposure_pct · net_exposure_pct · cash_pct
hhi_concentration · top_5_concentration_pct
per_sector_exposure_pct (map)
portfolio_var_95_1d_pct · portfolio_cvar_95_1d_pct
portfolio_vol_annualised
verdict (PASS / WARNING / FAIL)
breaches (list of {kind, ticker/sector, value, cap})
```

### E. `configs/risk_budget.yaml` — operator-owned

Locked parameters per market. India: 25% max Kelly / 6% per-ticker / 25% per-sector / long-only / 15% target vol. USA: 30% max Kelly / 8% per-ticker / 30% per-sector / shorts enabled / 14% target vol. Confidence-tier multipliers, stop-loss defaults, and the confidence gate (0.30) all in the YAML.

**Every change to `risk_budget.yaml` must be reviewed** — the config's SHA256 will be stamped into the Experiment Registry (Sprint 8's substrate) so historical replays can reconstruct the budget that was in effect.

### F. AI Risk Analyst (`backend/ai/risk_analyst.py`)

Descriptive audit — never promotes. Emits:
- Portfolio composition (gross · cash · HHI · VaR · CVaR · vol)
- Cap-reason breakdown (why did positions end up where they did?)
- Regime consistency check (bull regime with net short = flag)
- Downgrade candidates (positions marginally above confidence gate)
- Breach highlights

Contract-tested against `{buy, sell, target_price, recommendation, action, promoted, approved}` keys.

### G. Per-market runners

- `india/risk_engine/run.py` (INR, long-only, 15% target vol)
- `usa/research/risk_engine/run.py` (USD, shorts enabled, 14% target vol)

Both register `aegis.risk.v1` in `model_registry.jsonl` as EXPERIMENTAL and stamp every sized position for audit + walk-forward.

### H. Wiring

- India orchestrator: 26 → 27 steps (`risk_engine` after `recommendation_intelligence`)
- USA orchestrator: 29 → 30 steps
- India + USA datasets.yaml: +3 entries each
- India + USA SPAs: **Risk Engine** tile (n_sized · verdict · gross · cash · HHI)
- CI: Sprint 4 regression suite step added

---

## Runtime verification (2026-07-21)

### Sprint 4 regression — 23/23 pass

```
$ python backend/tests/test_sprint4.py

  ── Sizing math ──
  [OK] Kelly bounded by max_kelly_fraction across sweep
  [OK] Kelly returns 0 on invalid vol
  [OK] confidence tier multipliers signed correctly

  ── Exposure caps ──
  [OK] per-ticker cap clips both sides + preserves under-cap
  [OK] per-sector cap reduces available headroom
  [OK] per-sector cap saturated → 0

  ── Vol adjustment ──
  [OK] vol-adjusted size scales inversely with ticker vol
  [OK] VIX dampener respects regime + level

  ── Concentration ──
  [OK] HHI(single_position)=1.0, HHI(empty)=0.0
  [OK] HHI(uniform 10 positions)=0.1
  [OK] top-5 concentration matches expected ratio

  ── VaR / CVaR ──
  [OK] VaR/CVaR = 0 on empty portfolio
  [OK] CVaR ≥ VaR ≥ 0 on non-trivial portfolio (VaR=0.0019 CVaR=0.0024)

  ── End-to-end engine ──
  [OK] engine end-to-end · n_sized=4 active=3 verdict=PASS
  [OK] engine deterministic across identical calls
  [OK] engine accepts historical cutoff (walk-forward ready)
  [OK] SHORTs disabled → short positions have cap_reason=SHORT_DISABLED, weight=0
  [OK] no sized position exceeds per_ticker_cap
  [OK] no sector exceeds per_sector_cap

  ── AI Risk Analyst ──
  [OK] AI Risk Analyst produced narrative
  [OK] AI Risk Analyst obeys no-promotion contract

  ── Integration ──
  [OK] india runner: n_positions=0
  [OK] usa runner:   n_positions=0 currency=USD

  23 passed, 0 failed of 23
```

### Cumulative regression — 113/113 pass

| Suite | Result |
|---|---|
| Sprint 1 (backend validation) | 12/12 |
| Sprint 2 (canonical + market intel + AI) | 12/12 |
| Sprint 2.5 (feature store + AI) | 12/12 |
| Sprint 2.6 (feature intelligence + registry + promotion) | 18/18 |
| Sprint 2.7 (model factory + 11 models + ensemble) | 14/14 |
| Sprint 3 (recommendation intelligence v3) | 22/22 |
| **Sprint 4 (risk engine)** | **23/23** |
| **Total** | **113/113** |

### Backend validation

| Market | Before | After |
|---|---|---|
| India | 42 datasets · WARNING | **45 datasets · WARNING** (legacy `recommendations.json` + `sector_context.json` stale — pre-existing) |
| USA | 53 datasets · PASS | **56 datasets · PASS · 0.914** |

### Per-market Risk Engine output (today)

Both markets: 15 recommendations input · **0 active sized positions** · 100% cash · verdict PASS.

**Why:** Sprint 3's classifier emitted all HOLDs today (neutral regime × conservative calibration thresholds). Risk Engine correctly skips HOLDs entirely. Once Sprint 3 starts emitting BUY/SELL calls (which will happen naturally as Sprint 6 Learning Engine populates model win-rates and the ensemble goes WF-weighted), the Risk Engine will size them via the Kelly + cap pipeline.

The **synthetic-input regression test** confirms sizing works: given a strong-BUY (score 0.7, conf 0.85) + BUY + STRONG_SELL, the engine emits 3 active sized positions with gross exposure 24%, cash 76%, HHI 0.333, and portfolio vol 4.7% annualised — all deterministic, all inside caps.

### Orchestrator wiring

| Market | Before | After |
|---|---|---|
| India | 26 steps | **27 steps** |
| USA | 29 steps | **30 steps** |

---

## Walk-forward compatibility (verified)

- `test_engine_accepts_cutoff` — engine runs at arbitrary historical cutoff
- `test_engine_deterministic` — same inputs → identical output
- Every position stamps `model_stamp` + `schema_fingerprint` + `feature_set_version`
- No LLM calls · no random state · no clock reads inside engine logic

---

## Human-in-the-loop enforcement

- Every position carries `model_stamp` with `approval_status="experimental"` by default
- `aegis.risk.v1` registered as EXPERIMENTAL in `model_registry.jsonl`
- Promotion via `backend.promotion.promotion_gate.approve_model()` with WF evidence (Sprint 8+)
- AI Risk Analyst contract-tested: never emits `promoted`/`approved`/`buy`/`sell` keys

---

## Files created

**Framework:**
- `backend/risk/__init__.py`
- `backend/risk/types.py`
- `backend/risk/sizing.py`
- `backend/risk/vol_adjustment.py`
- `backend/risk/exposure_caps.py`
- `backend/risk/concentration.py`
- `backend/risk/var_cvar.py`
- `backend/risk/engine.py`

**AI + config:**
- `backend/ai/risk_analyst.py`
- `configs/risk_budget.yaml`

**Per-market runners:**
- `india/risk_engine/__init__.py`
- `india/risk_engine/run.py`
- `usa/research/risk_engine/__init__.py`
- `usa/research/risk_engine/run.py`

**Tests + report:**
- `backend/tests/test_sprint4.py`
- `docs/AEGIS_SPRINT4_REPORT.md`

## Files modified

- `docs/AEGIS_PHASE2_ARCHITECTURE.md` — added Experiment Registry cross-cutting note
- `scripts/aegis_daily_v2.py` — +1 step
- `usa/scripts/usa_daily.py` — +1 step
- `india/backend_validation/datasets.yaml` — +3 entries
- `usa/backend_validation/datasets.yaml` — +3 entries
- `ux/dashboard/frontend/index.html` — Risk Engine tile
- `usa/dashboard/frontend/index.html` — Risk Engine tile
- `.github/workflows/aegis-ci.yml` — Sprint 4 regression step

---

## What Sprint 4 does NOT do

- Does not touch legacy `research/risk_capital_v2/`
- Does not build Portfolio Engine (Sprint 5)
- Does not implement joint optimisation across sectors — Sprint 4 uses greedy per-rec allocation. Sprint 5 Portfolio Engine's job to do joint construction.
- Does not compute `target_notional` in currency — that needs an AUM input, which comes from Portfolio Engine
- Does not run walk-forward (Sprint 8)

---

## Dependencies unblocked

| Downstream sprint | Now consumes |
|---|---|
| Sprint 5 · Portfolio Engine | `sized_positions.json` → construct N-name portfolio with weights |
| Sprint 6 · Learning Engine | Records prediction + outcome per sized position |
| Sprint 7 · Execution Simulator | Simulates fills via slippage + commissions on `sized_positions.json` |
| Sprint 8 · Walk-Forward | Replays Risk Engine at each freeze date + measures per-position outcomes |

---

## Confidence checklist

- [x] Both markets simultaneously (India + USA)
- [x] Legacy `research/risk_capital_v2/` NOT modified
- [x] Kelly-fractional sizing with configurable max fraction
- [x] Per-ticker + per-sector exposure caps (contract-tested)
- [x] Inverse-vol scaling with VIX regime dampener
- [x] Parametric VaR + CVaR (95%, 1-day)
- [x] HHI + top-K concentration
- [x] Every SizedPosition carries model_stamp + schema_fingerprint + feature_set_version
- [x] Cap-reason recorded per position (audit trail)
- [x] AI Risk Analyst — descriptive only, contract-tested no-promotion
- [x] Deterministic (contract-tested)
- [x] Walk-forward ready — accepts cutoff (contract-tested)
- [x] Configs loaded from `risk_budget.yaml` (operator-owned)
- [x] Dashboards updated (Risk Engine tile both markets)
- [x] CI updated
- [x] Sprint 4 regression: 23/23 · cumulative 113/113
- [x] No TODOs, no placeholders

Sprint 4 report complete. Ready for operator sign-off before **Sprint 5 · Portfolio Engine** (N-name construction, weight normalization, cash policy, rebalance diff against prior state, AI Portfolio Analyst).
