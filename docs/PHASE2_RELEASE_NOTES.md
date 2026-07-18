# Phase 2 · Release Notes

**Release window:** 2026-07-17 → 2026-07-18
**Base commit:** `1bf4b59` · **Head commit:** on `origin/main` after this note lands.
**Governance:** [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) ·
[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) ·
[PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md).

Six engine-version bumps and one delivery-layer opt-in shipped over
this window. Every change is advisory-only, deterministic, and does not
touch the sealed core (fingerprint `e4c070673568c52d…` verified
unchanged).

## Full metric panel · this release

Regression: **all upstream suites PASS**. Invariance guards **HOLD**.

Phase 2 module smoke tests:

| Module | Tests |
|---|---|
| Adaptive Rec Engine v2.0 | 15 / 15 |
| Validation Engine v2.0 | 13 / 13 |
| Risk & Capital Engine v2.0 | 15 / 15 |
| DNA Feedback (v1.5) | 10 / 10 |
| Knowledge Graph v1.6 | 28 / 28 |
| UX Dashboard spec (UX031) | 69 / 69 |
| UX Telegram (UX030) | 40 / 40 |
| **Total** | **190 / 190** |

## Engine version bumps

### Adaptive Recommendation Engine · v1.4 → v2.0 · `1d9fdf8`

**P0 in Phase 2 · confidence signal rebuild.** ADR-008 identified that
raw confidence has no predictive power. v2.0 replaces the raw signal
with a HistGradientBoosting model over 8 numeric dimensions + one-hot
sector/industry. Selection rule = Precision@10 + 0.5 · Precision@5
(top-K identification, not global calibration).

Live-data findings (1,060 trades, 70/30 time-based split, random_state=42):
- HGB Precision@10 = **0.800** vs baseline **0.600** → **+20pp**
- HGB Precision@5 = **0.600** vs baseline **0.400** → **+20pp**
- Tier discrimination: monotone (Strong-Buy WR 60.0% > Buy 59.6% > Hold
  59.0% > Sell 58.4%). Spread 1.6pp — **MARGINAL** vs the 10pp exit
  criterion. v2.0 is a top-K identifier, not a global probability fix.
- Feature importance (permutation, neg_brier_score):
  volatility 0.222 · score_at_entry 0.222 · drawdown 0.191 ·
  momentum 0.177 · position_52w 0.132.
- Confidence itself does NOT appear in top-8 — confirms ADR-008.

New outputs (6):
`adaptive_rec_v2_signal.json` · `.parquet` · `_scoreboard.json` ·
`_feature_importance.json` · `_reliability.json` · `_migration.md`.

Governance: v2.0 output is a top-K identifier, NOT a calibrated
probability outside the ranked context.

### Adaptive Recommendation Engine · v1.4 → v1.5 · `a0df1a2`

**DNA feedback loop · closes ADR-009 latent value.** DEV028's DNA
store had 208 immutable records that no engine consumed. v1.5
joins DEV025 learning outcomes into DNA, extracts feature-patterns
(sector · classification · score_band), and computes per-current-rec
priors + a pattern leaderboard.

Live-data findings:
- 84 distinct patterns discovered.
- Top pattern: `Auto::Strong-Bullish::top_decile` WR 1.00 (n=1, thin)
- Strong: `Financial Services::Bullish::top_quartile` WR 0.84 (n=2)
- Bottom: `IT::Neutral::median_minus` WR 0.00 · `Metal::Bearish::bottom_half` WR 0.13

Advisory only. Does not mutate the immutable DNA parquet.

New output: `reports/recommendation_dna_feedback.json`.

### Validation Engine · v1.0 → v2.0 · `a04a5da`

**P1 in Phase 2 · live paper-trading harness.** Turns DEV021's
historical backtest into a continuous validation loop.

Modules (4):
- `paper_portfolio.py` — content-addressed ledger (positions +
  trades + MTM under `data/market_intelligence/derived/validation_v2/`)
- `expected_actual.py` — reconciliation vs DEV023 target / stop /
  hold-period
- `drift.py` — 1st-half vs 2nd-half Sharpe/win-rate/expectancy
- `opportunity_cost.py` — missed-edge tracking

First live run (as_of 2026-07-18):
- Opened 20 paper positions (top-K by decision score, MAX_PAPER_POSITIONS=20).
- Marked to market against latest `data/raw/india/{ticker}_D1.parquet`.
- Drift: `insufficient_evidence` (no closed trades yet — expected day 1).
- Opportunity cost: 6 missed edges detected.

Content-addressed ledger with SHA256 trade_id → dedup verified.

New outputs: `validation_v2_latest.json` · `validation_v2_daily_<date>.{json,md}` ·
`validation_v2_open_positions_<date>.csv` · `validation_v2_closed_trades.csv`.

Phase 2 exit criterion (§6): ≥ 30 days continuous operation. Accrues
from recurring runs, not more code.

### Risk & Capital Engine · v1.2 → v2.0 · `80e590f`

**P3 in Phase 2 · position sizing that answers three counter-questions.**

Sizing model:
```
target_weight = base × f_confidence × f_regime × f_volatility × f_sector_concentration
```
Each factor bounded (documented ranges); final weight clamped to
`[1%, 15%]`. Sector cap → factor 0 (BLOCK).

Portfolio risk: parametric VaR/CVaR/variance decomposition with
conservative `ρ = 0.30` default correlation. Per-position + per-sector
attribution.

Live-run: portfolio ann vol **19.3%** (below 20% budget) · VaR 95%
**31.7%** · CVaR 95% **39.7%** · verdict **WARNING** (per-position
budget breaches on 5 large-vol holdings).

Every position ships with counterfactuals ("why not 4%?" and "why not 12%?")
that trace to specific factor deltas.

New outputs: `risk_capital_v2_latest.json` · `<date>.json` ·
`_explanation_<date>.md` · `_sizing.parquet`.

### Knowledge Graph · v1.5 → v1.6 · `8c7d96d`

**Stress propagation + scenario cascade.** Extends DEV031 with a
canonical scenario library that leverages the existing graph +
portfolio overlay via personalized PageRank.

5 canonical scenarios (data-driven; skip if source absent):
1. `regime_shift_risk_off`
2. `loser_signal_amplification`
3. `sector_shock_<top>` — biggest sector by connectivity
4. `company_collapse_<top>` — top-influence company
5. `champion_strategy_failure` — current champion degradation

Live-run findings (4 scenarios today):
- `company_collapse_ipcalab`: **93.2%** portfolio exposure, 17
  positions hit.
- `champion_strategy_failure`: **96.5%** portfolio exposure, 18
  positions hit. Real concentration risk finding.
- `sector_shock_infrastructure`: 5.0% exposure, high sector contagion
  (0.22 reach).

New output: `reports/stress_scenarios.json`.

Supplier / Customer / Ownership graph edges remain deferred (no data
source).

## New capabilities

### Executive Dashboard (UX031) frontend · `384e58b`

Self-contained single-page vanilla JS + HTML. No build step. No React.
No CDN. Reads `reports/*.json` client-side.

7 routes · 20+ widgets. Every widget declares its source file. Dark-first
institutional theme (matches `ux/dashboard/lib/theme.py`). Light-mode
overrides + persisted toggle. 12-col responsive grid.

Quick start:
```
python ux/dashboard/frontend/serve.py
open http://127.0.0.1:8765/ux/dashboard/frontend/index.html
```

### UX030 Telegram sender (opt-in) · `e0027ac`

Standalone `scripts/telegram_send_ux030.py`. Uses the UX030 renderer
to build 5 messages (morning brief · new buys · champion · portfolio
health · executive summary) from live `reports/*.json`.

- Compatible with the existing retry wrapper's SUCCESS/FAILURE markers.
- Env parity with `india/telegram_notify.py` (TOKEN aliases, .env loading).
- Delivery ledger at `reports/telegram_delivery_ux030_<date>.jsonl`.

Deliberate opt-in: does NOT modify the sealed `scripts/telegram_send_with_retry.py`
or `india/telegram_notify.py`. Operator flips production over after a
parallel-run stability window.

## Bug fixes

### MON001 dashboard renders on MARKET_CLOSED payload · `3e17682`

CI regression fix. OPS001.5 commissioning SUB-12 failed on a Saturday
with `KeyError: 'forward_days_accumulated'` because
`_write_market_closed_report()` writes a minimal 5-field payload and
`build_dashboard()`'s `if latest else` guard didn't handle partial
payloads. 16-line surgical fix using `.get()` with defaults + a
MARKET_CLOSED banner. Regression PASS after fix.

## Governance documents (retroactive index)

Written earlier in the same session; recorded here for the release-note
completeness:

- [NEXAQUANT_MANIFESTO.md](NEXAQUANT_MANIFESTO.md) — mission + principles
- [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) — 14 ADRs
- [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) — constitution
- [PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md) — delivery contract
- [AEGIS_RESEARCH_AGENDA_2035.md](AEGIS_RESEARCH_AGENDA_2035.md) — 25-domain research backlog
- [AEGIS_ARCHITECTURE_REVIEW.pdf](AEGIS_ARCHITECTURE_REVIEW.pdf) — brutally-honest 16-page review
- [AEGIS_EXECUTIVE_REPORT.html](AEGIS_EXECUTIVE_REPORT.html) — institutional showcase

## What was NOT done (deliberate)

- **Supplier / Customer / Ownership graph edges** — no data source
  available. Deferred until an alt-data vendor decision is made
  (Phase 3, per research agenda Tier B).
- **UX030 production delivery cutover** — sender ships as opt-in. The
  sealed `india/telegram_notify.py` remains the default until a
  parallel-run stability window has been observed.
- **Full UX031 route coverage** — 7 of 10 spec routes implemented in
  the frontend; `/historical`, `/health`, `/market` deferred but
  their JSON contracts remain intact in `dashboard_routes.json`.
- **Champion promotion trigger** — DEV030 has never actually promoted;
  the promotion recommender remains in `initial_champion` state.
- **Phase 2 completion** — this release ships the foundational
  capabilities. The Phase 2 completion gate (§10 of the roadmap)
  requires 90 days of continuous validation harness operation + a
  live confidence-rebuild verification cycle. That accrues from
  recurring runs, not from more code.

## Invariance verification

- Fingerprint: `e4c070673568c52d…` OK == sealed
- Production constants: HOLD=63, rebal=63, sector_cap=2, name_cap=0.30, method=hrp — OK
- `cumulative_strategy_search = 38` — OK (not incremented)
- MON001 `forward_boundary_asof = 2026-03-28` — OK
- Sealed + LAB files unchanged. Changed files this release: 242,
  sealed_touched=0, lab_touched=0.

## Onboarding order for new contributors

Unchanged from `NEXAQUANT_MANIFESTO.md`:

1. `NEXAQUANT_MANIFESTO.md` — the why
2. `DESIGN_DECISIONS.md` — the reasons behind the how
3. `ENGINE_EVOLUTION_GUIDE.md` — the how
4. `PHASE2_MASTER_ROADMAP.md` — the what-next
5. `AEGIS_ARCHITECTURE_REVIEW.pdf` — honest state today
6. **This document** — what shipped this window

Then read the code.
