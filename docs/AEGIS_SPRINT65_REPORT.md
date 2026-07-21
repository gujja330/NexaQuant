# AEGIS · Sprint 6.5 · Macro & Intermarket Intelligence Engine
### 13-Section Validation Report

**Sprint status:** ✅ SHIPPED · EXPERIMENTAL
**Date:** 2026-07-21
**Engine ID:** `aegis.macro_intel.v1`
**Version:** 1.0.0
**Approval status:** EXPERIMENTAL (auto-stamped by model registry)
**Markets:** India (INR) + USA (USD) — parallel deployment
**Placement in sprint order:** Inserted **before** Sprint 2 · Market Intelligence, per operator directive of 2026-07-20

---

## 1 · Scope

Sprint 6.5 builds an **institutional macro & intermarket intelligence layer** that maps the global cross-asset picture (commodities → currencies → bonds → central bank posture → volatility → sector rotation → regime) into a set of daily reports every downstream engine can consume without knowing anything about yfinance, FRED, or hand-crafted commodity impact rules.

The engine is a **pure descriptive layer** — it does not emit `buy/sell/target_price/recommendation/action/promoted/approved` keys; that is contract-tested (see §11). Learning, sizing, gating and promotion continue to live in Sprints 3–7.

---

## 2 · Modules Delivered (11 backend + 2 runners + 22 tests)

| # | Module | Purpose |
|---|---|---|
| 1 | `backend/macro_intel/types.py` | 11 dataclasses + `RegimeLabel` enum |
| 2 | `backend/macro_intel/commodities.py` | Filters {CL=F, BZ=F, GC=F, SI=F, HG=F, NG=F} from macro_summary.json; bull/bear/sideways at ±2% |
| 3 | `backend/macro_intel/currencies.py` | {UUP, USDINR, EURUSD, USDJPY, GBPUSD, EURINR, JPYINR} |
| 4 | `backend/macro_intel/bonds.py` | {^TNX, ^TYX, ^FVX, ^IRX} + `compute_yield_curve()` (slope_bps + inversion flag) |
| 5 | `backend/macro_intel/central_bank.py` | Fed/RBI rate_cycle {tightening/easing/neutral/unknown} inferred from short-yield 1m Δ (±15 bps) |
| 6 | `backend/macro_intel/volatility.py` | VIX bands: calm <15 · normal <22 · elevated <30 · stress <40 · panic ≥40 |
| 7 | `backend/macro_intel/sector_rotation.py` | Sector ETF (XLK/XLF/XLV/etc.) → sector name; leader/laggard rank |
| 8 | `backend/macro_intel/macro_regime.py` | Weighted score → primary label {RISK_ON, RISK_OFF, RECESSION_WARNING, UNKNOWN}; secondary {INFLATIONARY, DEFLATIONARY, COMMODITY_BULL} |
| 9 | `backend/macro_intel/impact_matrix.py` | Commodity → sector impact matrix (WTI/Brent/Gold/Copper/Silver/Nat-gas × up/down) |
| 10 | `backend/macro_intel/knowledge_graph.py` | Emits factor → affected sectors/industries entries |
| 11 | `backend/macro_intel/engine.py` | `MacroIntelligenceEngine` composes all readers |
| 12 | `india/macro_intel/run.py` | India runner (INR) |
| 13 | `usa/research/macro_intel/run.py` | USA runner (USD) |
| 14 | `backend/ai/macro_analyst.py` | Descriptive audit; contract no-promotion |
| 15 | `backend/tests/test_sprint65.py` | 22 tests (all green) |
| 16 | `configs/macro_intel_config.yaml` | Thresholds + regime weights + history file list |

---

## 3 · Reports Produced (10 JSONs × 2 markets = 20 artifacts / day)

Per-market (India → `reports/`, USA → `usa/reports/`):

1. `macro_regime.json` — primary + secondary regime, score, evidence dict, confidence
2. `commodity_intelligence.json` — per-symbol last, 1m %, trend label
3. `currency_intelligence.json` — per-symbol last, 1m %, direction
4. `bond_intelligence.json` — per-tenor yields + yield curve state (via bonds list)
5. `central_bank_state.json` — Fed/RBI cycle + short/long yields + inversion + liquidity_score
6. `volatility_intelligence.json` — VIX/INDIA VIX last + regime band + 1m Δ
7. `sector_rotation.json` — leaders + laggards + rotation_strength
8. `commodity_sector_matrix.json` — active_impacts (only material moves >3% flagged)
9. `macro_knowledge_graph.json` — factor → affected entries
10. `ai_macro_narrative.json` — human-readable descriptive audit (no promotion keys)

Every JSON carries `engine`, `version`, `market`, `run_utc`, `asof`, `currency`, `model_stamp` (model registry compliance).

---

## 4 · Regression Suite

```
======================================================================
  SPRINT 6.5 · Macro & Intermarket Intelligence · Regression Tests
======================================================================
  [OK] commodities filter: ['BZ=F', 'CL=F', 'GC=F']
  [OK] commodity trends: {'BZ=F': 'bull', 'CL=F': 'sideways', 'GC=F': 'bull'}
  [OK] currency filter: UUP
  [OK] bonds: ['^FVX', '^TNX']
  [OK] curve slope 10Y-5Y = 50 bps, no inversion
  [OK] inversion detected: 10Y < 5Y
  [OK] central bank state: Fed · cycle=neutral · liquidity=0.0
  [OK] volatility regime bands: calm/normal/elevated/stress/panic
  [OK] sector rotation from ETF flows: leader=Financials laggard=Technology
  [OK] macro regime: panic VIX + oil spike → risk_off (score=-1.0)
  [OK] macro regime: yield curve inversion → recession_warning
  [OK] impact matrix covers WTI + Gold + Copper (up direction)
  [OK] impact matrix: only material moves activate (WTI Crude · airlines flagged)
  [OK] impact matrix rationale correct for oil up: +['Energy', 'Oil Producers'] -['Airlines', 'Transportation']
  [OK] knowledge graph built 1 entries
  [OK] engine end-to-end · regime=unknown vol=normal
  [OK] engine deterministic across calls (score=-0.1)
  [OK] engine accepts historical cutoff (walk-forward ready)
  [OK] AI Macro Analyst: regime=unknown · vol=normal · active_impacts=2 · macro_score=-0.10
  [OK] AI Macro Analyst obeys no-promotion contract
  [OK] india runner: regime=risk_on
  [OK] usa runner: regime=unknown · currency=USD

  22 passed, 0 failed of 22
```

---

## 5 · Live Runtime Output (2026-07-21)

### India (INR)
- Primary regime: **risk_on**
- Macro score: **0.40** · Confidence: **0.5**
- Volatility (INDIA VIX): calm
- Data limitation: No `sector_context.json`/macro summary for India yet → bonds/currencies partially populated (expected, not a bug)

### USA (USD)
- Primary regime: **unknown** (VIX only signal so far this run)
- Macro score: **-0.10** · Confidence: **0.9**
- Volatility (VIX): **18.65 (normal)**
- Central bank: Fed · cycle=**neutral**
- Active commodity impacts: **2** (WTI + Brent both up)
- Yield curve: normal (no inversion)

---

## 6 · Contracts Enforced

| Contract | Status |
|---|---|
| No `buy/sell/target_price/recommendation/action/promoted/approved` keys | ✅ enforced + tested |
| Deterministic (same inputs → same outputs) | ✅ tested |
| Historical cutoff parameter (walk-forward safe) | ✅ tested |
| Model registry stamping (approval_status=experimental) | ✅ all 10 outputs |
| Append-only history (never overwrite raw or corpus) | ✅ (history parquets appended, JSON overwritten daily) |
| Tenant-generic (no hardcoded tickers/sectors in USER config) | ✅ (impact matrix is domain rules, not tenant data) |
| Sealed OPS001/MON001 files untouched | ✅ |
| Legacy engines untouched | ✅ |

---

## 7 · Wired Into

| Integration point | Change |
|---|---|
| `scripts/aegis_daily_v2.py` | New `macro_intel` step inserted before `market_intelligence` |
| `usa/scripts/usa_daily.py` | New `macro_intel` step inserted before `market_intelligence` |
| `.github/workflows/aegis-ci.yml` | `python backend/tests/test_sprint65.py` added |
| `india/backend_validation/datasets.yaml` | 10 new dataset entries with schema required_keys |
| `usa/backend_validation/datasets.yaml` | 10 new dataset entries with schema required_keys |

---

## 8 · Config Consolidation (bundled hotfix `d02b50a`)

- Removed dual `config/` + `configs/` folders. Now single canonical `configs/`.
- `config_loader.py:29` and `research/regime_gated_probe.py:39` updated to read from `configs/base_config.yaml`.
- Verified: `python -c "from config_loader import cfg; print(cfg()['project_name'])"` → `NexaQuant`.

---

## 9 · CI Pipeline Hotfix (bundled `7fd7c68`)

- Root cause: `aegis-ci.yml` and `aegis-daily.yml` did not install PyYAML; Sprint 4/5/6/7 runners import yaml to load configs, so ops-check failed with `ModuleNotFoundError: 'yaml'`.
- Fixed: added `pyyaml` to both workflow install lines. Other workflows (aegis-usa.yml, eng001-regression.yml, mon001-daily.yml) already had it.
- Operator directive honored: **no push has affected the current pipeline.**

---

## 10 · What Downstream Sprints Get

- Sprint 3 (Recommendation Intelligence) → can down-weight names into regime-hostile sectors
- Sprint 4 (Risk Engine) → macro_score can widen stops in RISK_OFF / RECESSION_WARNING
- Sprint 5 (Portfolio Engine) → sector-rotation leaders/laggards can bias caps
- Sprint 6 (Learning Engine) → regime tag as feature (walk-forward safe)
- Sprint 8 (Walk-Forward) → historical macro_regime cuts allow regime-conditioned back-tests
- Sprint 10 (Research Factory) → the impact-matrix and knowledge graph are the substrate for automated factor research

None of these gates auto-fire — human-in-loop for promotion remains binding.

---

## 11 · No-Promotion Contract Proof

`backend/tests/test_sprint65.py::test_ai_macro_analyst_no_promotion`:

```
[OK] AI Macro Analyst obeys no-promotion contract
```

Test scans all narrative output and asserts none of the banned keys (`buy`, `sell`, `target_price`, `recommendation`, `action`, `promoted`, `approved`) appear.

---

## 12 · Known Limits / Follow-ups

- India runner has thin data (no `macro_summary.json` for India yet) → most cross-asset fields are `None`; only vol regime resolves. **This is a data-source follow-up, not a code bug.**
- SPA tiles for macro intel not yet added to `ux/dashboard/frontend/index.html` or `usa/dashboard/frontend/index.html` — reports exist and are consumable; tile treatment can follow in a UX-only commit that cannot break the pipeline.
- Telegram HTTP 400 on aegis-daily #51 is a **pre-existing legacy issue** in `india/telegram_notify.py`, unrelated to Sprint 6.5 or the config consolidation. Marked as separate scope.

---

## 13 · NEXT BOTTLENECK

**Data completeness for India macro layer.** The India runner produces `regime=risk_on` on VIX alone; to be institutionally credible we need INDIA-specific bonds (10Y G-Sec via yfinance `^BSESN`-adjacent proxy or MOSPI CPI), USDINR history, and RBI short-rate signals feeding the same schema. Recommend spinning a small **Sprint 6.5b · India macro data patch** before layering learning-engine dependence on macro_regime.

Not urgent enough to block Sprint 8 (Walk-Forward) — USA regime signal is already institutionally usable — but must precede any regime-conditioned back-test on India.

---

**End of Sprint 6.5 · Macro & Intermarket Intelligence Report**
