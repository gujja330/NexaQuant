# AEGIS · Sprint A · Three-Runner Parallel Development

**Sprint start:** 2026-09-03
**Sprint duration:** 8 weeks build + 8 weeks live shadow = 16 weeks to promotion decision
**Baseline commit:** `be33513d` on `origin/main`
**Authoritative spec:** `docs/AEGIS/AEGIS_R1_R2_R3_Implementation_And_Strategy.pdf` (committed `16a8c31d`)
**Prior session log:** `docs/AEGIS/SESSION_LOG_2026-09-02.md`

---

## 1 · Executive Summary

Sprint A executes the three-runner architecture: **R1 as defensive specialist · R2 as broad all-weather core · R3 as aggressive research edge**. All three run in parallel under a formal isolation contract. The composite layer reads all three but writes to none.

The sprint has two equally important objectives:
1. **Ship the runners + composite** per the strategy document, evidence-gated, on the 8-week build cadence
2. **Institutionalize the coding + delivery standards** that prevent the class of recurring failures we observed in 2026-09-02's session (file locks, untracked file loss, admin-filter drift across consumers, positional column reads, cached validator staleness)

Everything in this document is a codified sprint plan. Deviation from any standard requires named CEO authorization.

---

## 2 · Sprint Objectives

### Primary deliverables (must-ship by Week 8)

- **R2 zero-entry diagnosis** with documented root-cause classification (bug vs discipline)
- **Daily Signal Ledger** foundation (60-day rolling · R1 + R2 forward returns 5/10/20/60d)
- **Fundamentals Feature Store** (13 signals · zero new external sources)
- **P0 dynamic exit bridge retrospective replay** (539 R2 closes · with OHLC intraday sequencing correction)
- **P1 confidence calibration** wired to delivered output (both runners) with joint-calibration fix
- **P2 sector/regime-adjusted ranking** live in R2 top-N
- **R1 advisory sheet** `05_R1_Advisory` in both markets' workbooks
- **Composite meta-ensemble layer** with sample-size floor
- **`06_Composite_Signals` sheet** in both markets (shadow-only)
- **R3 Tier 1 build** (GBM + Fundamentals Feature Store · fully isolated)
- **Signal Silence trigger** (8th Research Trigger) + Minimum Viable Signal governance
- **Standards enforcement** (all sections in §4)

### Non-goals (explicitly out of scope)

- R3 GNN (Tier 3 · defer until 2000+ nodes)
- Peer-pair statistical arbitrage (requires short infrastructure we don't have)
- CUSUM change-point detection (Tier 3 supplement, not primary)
- R1 un-retirement to production P&L (advisory-only exposure is the whole point)
- Any change to R2's 11-model ensemble weights (locked baseline)
- New external data ingestion (fundamentals expansion uses existing sources only)

---

## 3 · Ground Rules Carried Forward

From every prior lock and the strategy document:

- R2 stays LOCKED · every upgrade is evidence-gated · not a direct edit
- R1 stays retired at production layer · engine-alive for advisory only
- R3 is SHADOW_ONLY · promotion requires named, dated, written CEO authorization
- No `override_allow` at any point during sprint
- No hardcoded stop-loss substitution
- No R2 signal-chain modification without walk-forward validation + statistical significance
- Every push must be preceded by full local pytest 100% pass + validator PASS both markets
- USA universe = S&P 500 only (n=516)
- 3-sheet contract still holds (4 with `04_Daily_Portfolio_History` added 2026-09-02)

---

## 4 · Coding, Git, and Delivery Standards

**These prevent the exact failures we observed 2026-09-02.** Every developer working the sprint follows them without exception. Any bypass requires explicit approval and is logged.

### 4.1 · Git operational standards

**S1 · Untracked user documents must be tracked before any git operation.**
Any file placed by the CEO or operator in `docs/`, `configs/`, or a project directory must be `git add`ed and committed within the same turn it's noticed. This prevents the class of failure that lost `AEGIS_R2_Upgrade_And_Runner3_Implementation_Spec.pdf` during rebase cycles.

**Enforcement:** at the start of every work session, run:
```
git status --short | grep "^??" | grep -E "\.(pdf|md|xlsx|json|yaml)$" | head
```
If any user-facing file is untracked, commit it immediately with a `chore: preserve` message.

**S2 · Kill Python processes before every git rebase/checkout that touches xlsx.**
Openpyxl and any tool that has loaded an `.xlsx` file holds a Windows file handle that blocks git's rename/unlink. This caused multiple "could not detach HEAD" failures on 2026-09-02.

**Enforcement:** before any `git pull --rebase`, `git checkout HEAD -- .`, or `git stash pop`:
```
powershell -Command "Get-Process -Name python -EA SilentlyContinue | Stop-Process -Force"
Start-Sleep 2
```

**S3 · Never run `git stash -u --include-untracked` when untracked user documents exist.**
Combine with S1: if `git status --short | grep "^??"` shows user documents, commit them first before any stash operation. Only run untracked-stash when the only untracked items are transient build artifacts we control.

**S4 · Rebase order for parallel-repo pushes.**
When origin has advanced (bot commits) and local has our work commit:
```
1. verify all user-facing files committed (S1)
2. kill python processes (S2)
3. git stash -u  (only transient artifacts)
4. git pull --rebase origin main
5. if conflict on binary xlsx: git checkout --theirs [file], git add, git rebase --continue
6. git push origin main
7. git stash pop (only if step 3 stashed anything real)
```

**S5 · Verify pushed SHA before claiming success.**
After `git push`, run `git log origin/main --oneline -3` and confirm the top SHA matches the local HEAD. Never say "pushed" based on the push command's exit code alone.

**S6 · CI conclusion is checked at step-level, not workflow-level.**
`AEGIS USA` workflow can report `conclusion: success` at the top level while an internal step (`send:`) failed. Always query:
```
GET /repos/{repo}/actions/runs/{run_id}/jobs
```
and inspect individual step conclusions. A step named `Telegram Command Center` or `send` with `conclusion: failure` inside a "successful" workflow is still a delivery failure.

### 4.2 · Code architecture standards

**S7 · Single source of truth for classification / filtering.**
Any predicate that classifies data (admin event, retired runner, orphan, etc.) is defined ONCE in a canonical location and imported everywhere it's used. Zero re-derivation, zero re-implementation.

Currently canonical:
- `_is_administrative_exit` — `scripts/build_aegis_3sheet_workbook.py`
- `retired_runners` — `backend/delivery/canonical/retirement.py`
- `PORTFOLIO_SHEET_ALIASES`, `EXIT_HISTORY_SHEET_ALIASES` — `backend/delivery/xlsx_contract.py`

**Enforcement:** any new consumer of these filters imports from the canonical source. A CI test verifies no local duplicate is defined (regex search for method name definitions across the tree, allowlist the canonical file only).

**S8 · No positional column reads on XLSX data.**
Every XLSX cell access is by header name via the `_row_val` / `_cell_val` / `_resolve_col` helpers already added to `backend/delivery/xlsx_validator.py`. Zero `row[7]` or `ws.cell(r, 23)` patterns. Add same helpers to any new XLSX consumer.

**Enforcement:** CI grep that fails the build if any new file in `backend/delivery/` or `backend/research/` contains `row\[[0-9]+\]` or `\.cell\([^,]+,\s*[0-9]+\)` outside a whitelisted resolver method.

**S9 · Validators + gates must be freshness-safe.**
Any consumer that reads a cached JSON report (like `delivery_gate` reading `wave_regression_{market}.json`) must either:
- Regenerate the JSON at consume-time (safest)
- OR verify the cached JSON's `run_utc` is within N minutes of the current time and fail loud if stale

We observed 2026-09-02 that `delivery_gate.decide` was reading a stale wave_regression JSON that pre-dated my A23 fix, causing false ALLOW/BLOCK verdicts.

**Enforcement:** add `_verify_freshness(cache_path, max_age_minutes)` to `backend/delivery/delivery_gate.py`; every cached report consumer calls it.

**S10 · Every commit that touches a validator must re-emit its cached report before pushing.**
Rule: if the commit modifies `backend/research/wave_regression.py` or `backend/delivery/xlsx_validator.py`, the same commit regenerates `reports/context/wave_regression_{market}.json` and `reports/context/xlsx_validation_{market}.json` for both markets. Otherwise CI runs on new code but production cron reads old cache.

**Enforcement:** pre-commit hook (or CI test) that fails if validator source was touched but corresponding JSON wasn't regenerated in the same commit.

**S11 · Sheet-name and row-offset dual-layout support is mandatory.**
Every XLSX consumer must handle both legacy (`Portfolio`, `Exit History (90d)`) and current (`01_Portfolio`, `03_Exit_History`) sheet names via the `PORTFOLIO_SHEET_ALIASES` / `EXIT_HISTORY_SHEET_ALIASES` tuples. Row offsets adjusted per sheet (`_row_offset` helper).

**S12 · Fabrication-free invariant · UNAVAILABLE always beats a made-up value.**
Any field derived from a canonical source uses `UNAVAILABLE` when the source returns None/empty/zero. Never substitute a default like 0 or a computed proxy that looks like data. This rule already holds; codify it in every new column added.

### 4.3 · Testing standards

**S13 · Delivery-tests suite is a CI gate, not advisory.**
`tests/delivery/` runs before every push and its passage is required. `pytest tests/delivery/ -q` must return `passed` with 0 failures. Currently 105 tests. Every new validator invariant adds a regression test in this suite.

**S14 · Full pytest must pass locally before push.**
`pytest tests/ -q` on the developer's machine before every push. Currently 560 tests. If it takes too long, split into `tests/` (cert-scoped, fast) and `tests/full/` (comprehensive, slower). Cert-scoped is the mandatory pre-push gate.

**S15 · Regression test for every reverted fix.**
When a fix gets reverted through git chaos (as A23 was reverted 2× on 2026-09-02), add an explicit CI test that fails if the fix is absent. Prevents silent regression via file drift.

Example:
```python
def test_a23_admin_filter_present():
    src = (_ROOT / "backend/research/wave_regression.py").read_text()
    assert "_a23_is_admin" in src, "A23 admin-filter fix has been reverted"
```

Already have this pattern for the delivery-layer sender fix (`test_workbook_3sheet_contract_after_legacy_sender.py`). Extend to every non-trivial fix that risks reversion.

### 4.4 · Sprint execution standards

**S16 · One commit per logical fix · no bundled unrelated changes.**
Prevents the class of failure where a rebase conflict on one file forces resolution decisions for unrelated files. Each commit is atomically about one thing.

**S17 · No push during known bot commit window.**
AEGIS USA runs at 12:00 / 12:30 / 13:00 UTC weekdays. AEGIS Daily runs on push + schedule. Avoid pushing during these windows unless it's a hot-fix; bot commits arriving during our push cycle cause rebase conflicts.

**S18 · Sprint-day file lockdown.**
During Sprint A, the following files require code review + rationale before any modification:
- `configs/aegis_retirement.yaml` (retirement policy)
- `configs/ensemble_weights_adaptive.yaml` (R2 model weights · adaptive but not human-tuned)
- `configs/delivery_gate.yaml` (never `override_allow: true`)
- `backend/recommendation/ssot/` (R2 SSoT)
- `backend/delivery/canonical/retirement.py` (retirement enforcement)

**S19 · Every deliverable has a Definition of Done checklist.**
No deliverable is considered complete until every item in its DoD is checked. See §11.

**S20 · CEO-facing surface changes require dry-run.**
Any change that will alter what the operator sees (new sheet, new column, new banner, new Telegram message) must be dry-run locally with `--build-only` and inspected by opening the actual XLSX before shipping. No exceptions.

---

## 5 · Parallel Development Tracks

Sprint A runs three tracks concurrently under the Part 0 isolation contract. Each track has its own owner, deliverables, gates. Tracks share the Daily Signal Ledger + Fundamentals Feature Store as common infrastructure but never write to each other's paths.

### Track 1 · R2 production upgrades (P0-P5)

Locked baseline. Every upgrade wraps around the ensemble, never modifies it. Additive or calibration-layer only.

**Owner:** primary R2 maintainer
**Isolation boundary:** writes only to `reports/production/*`, `configs/ensemble_weights_adaptive.yaml`, `backend/recommendation/*`
**Test gate:** every upgrade clears walk-forward validation with deflated-Sharpe correction on out-of-sample folds

### Track 2 · R1 advisory + composite layer

R1 stays retired at production layer, engine-alive for advisory. Composite meta-ensemble reads R1+R2 outputs, writes to `reports/research/composite/`.

**Owner:** delivery-layer maintainer + composite architect
**Isolation boundary:** composite writes only to `reports/research/composite/*` and `06_Composite_Signals` sheet; never writes to Registry, Exit History, or production P&L
**Test gate:** composite output on Day-1 must match R2-alone (Trust_Weight(R1)=0 due to sample-size floor)

### Track 3 · R3 Tier 1 build

Fully isolated per Part 0 contract. GBM + Fundamentals Feature Store as primary model. All output under `reports/research/r3/*` and `configs/r3_*.yaml`.

**Owner:** research engineer
**Isolation boundary:** CI test `test_r3_no_production_writes` fails the build if any R3 module imports or writes to any production path
**Test gate:** R3 must replicate R2 baseline (equivalent Sharpe on same universe with same feature subset) before any new-feature signal is added

---

## 6 · Week-by-Week Execution Plan

### Week 1 · Foundation

| Track | Deliverable | Owner | Gate |
|---|---|---|---|
| R2 | R2 zero-entry diagnosis · instrument signal chain per-stage · emit `reports/context/r2_signal_funnel_{market}.jsonl` for last 28 days | R2 | Preliminary classification: (a) gate too strict, (b) threshold too high, or (c) correctly restraining |
| Common | Build Daily Signal Ledger · `scripts/build_daily_signal_ledger.py` · 60-day forward returns 5/10/20/60d | Data | Both markets · ≥45 trading days populated |
| Common | Scaffold Fundamentals Feature Store · `scripts/build_fundamentals_feature_store.py` · 13-signal schema · empty derivations OK | Data | Schema locked; column names + provenance sources documented |
| R3 | Isolation CI test · `tests/isolation/test_r3_no_production_writes.py` · fails build if any R3 module writes to production path | R3 | Test present + committed · no R3 code yet |
| Standards | Enforce S1-S6 · commit any untracked user docs · pre-commit hook for validator freshness (S10) · CI grep for positional column reads (S8) | All | All 20 standards documented in this file + at least S1, S2, S7, S10, S13 automated |

### Week 2 · P0 replay + R1 advisory + Fundamentals derivation

| Track | Deliverable | Owner | Gate |
|---|---|---|---|
| R2 | P0 dynamic exit bridge retrospective replay · `scripts/replay_dynamic_exit_bridge.py` · OHLC intraday sequencing correction (Amendment 2 from prior evaluation) | R2 | n=539 · counterfactual expectancy statistically compared to actual (paired bootstrap) · per-regime breakdown · pessimistic ordering for ambiguous OHLC days |
| R1 | R1 advisory sheet `05_R1_Advisory` in both workbooks · explicit banner: "R1 Legacy Advisory · no dynamic-exit protection · not counted in production P&L" · reconciler C1 accepts 5-sheet | R1 | Gated on Week 1 preliminary R2 diagnosis; regression test that sheet exists + banner text |
| Common | Fundamentals derivation Layer 1 (Quality) · Piotroski F-score · Beneish M-score · Altman Z-score · Sloan Accruals · Interest Coverage | Data | All 5 computable from existing balance-sheet + income-statement + cash-flow data · per-ticker per-market · verified against 5 known cases |
| R3 | Isolation contract implementation · `backend/research/r3/` skeleton · `configs/r3_registry.yaml` (SHADOW_ONLY) · `configs/aegis_runner_registry.yaml` shipped | R3 | Skeleton importable · isolation CI test PASS · no functional code yet |

### Week 3 · Fundamentals Layer 2 + P1 calibration start

| Track | Deliverable | Owner | Gate |
|---|---|---|---|
| R2 | P1 Platt calibration · `backend/calibration/platt_calibration.py` · joint-calibration fix (Amendment 1 from prior evaluation: fit on `(raw_score, regime_encoded, win/loss)` jointly, not two-stage multiply) | R2 | ECE weekly refit job scheduled · sanity guard active (don't deploy if new ECE > old) |
| R1 | R1 output preserved to a historical archive · `data/r1_daily_archive/YYYY-MM-DD.csv` daily copy of `aegis_today.csv` for future ledger backfill | R1 | Daily copy running; archive covers ≥7 days by Week 3 end |
| Common | Fundamentals Layer 2 (Value) · FCF Yield · EV/EBITDA · Total Shareholder Yield · Sector-relative percentile ranking | Data | All 4 signals computable · sector-relative uses `sector_cache.json` for grouping |
| R3 | R3 Tier 1 model skeleton · LightGBM training loop · walk-forward folds per Part 4 protocol (train=252, test=63, step=21, embargo=5) | R3 | Loop runs on synthetic data · SHAP feature importance emits · no real training yet |

### Week 4 · Fundamentals Layer 3 + P1 wired

| Track | Deliverable | Owner | Gate |
|---|---|---|---|
| R2 | P1 calibrated confidence wired to delivered output (Telegram + XLSX) · replaces raw confidence in `02_Today_Momentum` after gate clears | R2 | ECE ≤ 0.05 sustained over 4 consecutive weekly refits |
| R1 | R1 calibrated confidence · same Platt pipeline applied to R1's historical daily-signal outcomes | R1 | R1 has ≥50 signals in ledger before calibration is trusted (per sample-size floor) |
| Common | Fundamentals Layer 3 (Momentum + Change) · Analyst Revision Momentum · Guidance Revision · Earnings Surprise History · Insider Form 4 Net Buying · 13F Institutional Change | Data | 5 signals wired · at least 3 computable from data currently ingested (analyst revision, surprise history, insider) · guidance + 13F may need small ingest extension |
| R3 | R3 Tier 1 model on Fundamentals Feature Store · trained on real data · walk-forward evaluated · emits shadow ledger | R3 | Model trained · IC computed per fold · deflated Sharpe reported |

### Week 5 · P2 R2 · Fundamentals per-signal ranking

| Track | Deliverable | Owner | Gate |
|---|---|---|---|
| R2 | P2 sector/regime-adjusted ranking · α, β walk-forward grid search on Daily Signal Ledger | R2 | Grid searched · IC per bucket · deflated for grid size |
| R1 | R1 rolling regime-adaptive sector filter (NOT hardcoded skip list) · sector composite score = 0.4·trailing_20d_realized_pnl + 0.3·trailing_10d_news_sentiment + 0.2·trailing_60d_relative_strength + 0.1·regime_multiplier | R1 | Filter computed daily · exposed as `reports/research/r1_sector_filter_{market}.json` · not yet applied to R1 advisory sheet |
| Common | Fundamentals per-signal IC ranking · permutation importance on Daily Signal Ledger · publish `reports/research/fundamentals_ic_report_{market}.json` | Data | All 13 signals ranked · which survive (IC > threshold at p<0.05 deflated) · which are noise |
| R3 | R3 shadow output live · daily emissions to `reports/research/r3/shadow_ledger.jsonl` | R3 | Ledger accumulating · zero writes to production paths (isolation CI verifies daily) |

### Week 6 · P2 R2 wired · KG communities PIT

| Track | Deliverable | Owner | Gate |
|---|---|---|---|
| R2 | P2 wired · regime-adjusted score used in R2's top-N selection | R2 | Statistically significant expectancy improvement on out-of-sample walk-forward · no NORMAL-regime degradation |
| R2 | P3 KG community-relative scoring · with mandatory point-in-time snapshot rule (Amendment: every historical backtest uses the KG snapshot that would have existed on that date) | R2 | Community turnover measured · PIT snapshot loader implemented · γ swept + deflated |
| R1 | R1 advisory sheet with regime-adaptive sector filter applied · picks flagged with sector composite score | R1 | Operator sees ranked R1 picks with sector context |
| Common | Fundamentals composite score · surviving signals combined via IC-weighted blend · single `fundamentals_score` column added to Feature Store | Data | Composite score usable as R2 P2 additive component and as R3 primary feature |

### Week 7 · Composite meta-ensemble

| Track | Deliverable | Owner | Gate |
|---|---|---|---|
| Composite | `backend/recommendation/composite/` engine shipped · reads R1 + R2 (+ R3 shadow if available) · writes ONLY to `reports/research/composite/` | Cross-runner | Trust_Weight(r) = 0 when trailing_closed_trades(r) < 50 · R1 disabled at launch until +25 trades accumulate |
| Composite | Runner Combination Matrix (§R1.6) computed daily · 9 dispositions per stock per day | Cross-runner | Matrix emits to `reports/research/composite/runner_matrix_{market}_{asof}.json` |
| Composite | Cross-runner conviction classifier · HIGH_CONVICTION / R1_ONLY / R2_ONLY / R3_ONLY / CONFLICT / SILENT dispositions | Cross-runner | Classifier tested on last 60 days of ledger data |
| R3 | R3 continues shadow · 60-day accumulation begins Week 7 · Day-30 kill gate at Week 11 | R3 | Shadow ledger growing daily · zero isolation violations |

### Week 8 · Governance + composite promoted to workbook

| Track | Deliverable | Owner | Gate |
|---|---|---|---|
| Governance | Signal Silence trigger (8th Research Trigger) · fires per §R1.7 rules with my amendment (cannot fire only when all-runners-silent AND universe-silent) | Cross-runner | Trigger tested on synthetic 15-day silence scenario · alert fires correctly · pre-registered |
| Governance | Minimum Viable Signal floor · pre-registered gate relaxation with hard cap 15 days per rolling 90 · never silent · always flagged | Cross-runner | Relaxation policy documented + walk-forward validated · CI test confirms hard cap enforced |
| Composite | New sheet `06_Composite_Signals` in both workbooks · shadow-only · reconciler C1 accepts 6-sheet | Composite | Sheet renders correctly · Runner Combination Matrix visible · zero P&L impact |
| Standards | Sprint retrospective · which of S1-S20 fired · which prevented issues · which need refinement | All | Retrospective document committed at Week 8 end |

### Week 9-16 · Live shadow (60 trading days)

- Composite runs daily alongside R2 (shadow-only)
- Realized performance tracked in parallel
- Day-30 kill gate: composite must not underperform R2 by more than 10% on realized expectancy
- Day-60 promotion decision: composite must beat R2 in realized expectancy at deflated-Sharpe significance
- **Decision:** promote composite as operator-facing recommendation OR revert to R2-alone
- **Governance:** promotion requires named, dated, written CEO authorization

---

## 7 · Cross-Runner Coordination

### 7.1 · Shared infrastructure (owned collectively)

- `reports/research/daily_signal_ledger_{market}.parquet` — updated daily by orchestrator step
- `reports/features/fundamentals_{market}.parquet` — updated daily
- `configs/aegis_runner_registry.yaml` — declares R1=RETIRED_ADVISORY, R2=PRODUCTION, R3=SHADOW_ONLY
- `backend/delivery/canonical/retirement.py` — single source of truth for runner status
- `_is_administrative_exit` — single source of truth for admin classification

### 7.2 · Coordination protocol

- **Daily standup (async):** each track posts a one-line status to `reports/sprint_a_status.jsonl`
- **Weekly sync (CEO-facing):** operator dashboard update in `docs/AEGIS/SPRINT_A_WEEK_{N}_STATUS.md` — auto-appended by orchestrator
- **Cross-track dependency changes:** any change to shared infrastructure requires all three tracks' acknowledgment before merge

### 7.3 · Isolation enforcement (Part 0 · mechanically)

- `tests/isolation/test_r3_no_production_writes.py` — greps R3 code + import graph · fails if any R3 module touches `reports/production/`, `configs/ensemble_weights_adaptive.yaml`, or `backend/recommendation/{engine,ssot}.py`
- `tests/isolation/test_composite_no_registry_writes.py` — same for composite layer · must never write to Registry JSONL
- `tests/isolation/test_r1_advisory_no_production_pnl.py` — R1 advisory sheet's picks never appear in Portfolio, Exit History, or production P&L aggregates

---

## 8 · Validation Methodology (referenced from doc Part 4)

All validation follows the strategy document's Part 4:

- **Walk-forward folds:** train=252d · test=63d · step=21d · embargo=5d
- **Paired bootstrap:** 10,000 resamples for strategy comparisons
- **Likelihood-ratio test:** for nested model comparisons (P4 Cap × Sector)
- **Deflated Sharpe Ratio:** applied to every experiment family with more than 1 trial

Sample-size tiers (locked):
- n<5 → observation only
- n=5-14 → hypothesis
- n=15-29 → research signal
- n=30-49 → stronger evidence
- n=50+ → validation candidate

**Per-experiment trial counts must be logged to `reports/research/experiment_ledger.jsonl`** so deflated-Sharpe corrections are auditable.

---

## 9 · Kill Gates (when to stop)

| Gate | Kill condition | Action |
|---|---|---|
| Week 1 R2 diagnosis | Root cause requires R2 engine change | Stop plan · request separate CEO authorization · R2 lock is inviolable |
| Week 2 P0 replay | Counterfactual expectancy ≤ actual, not significant | Bridge doesn't improve · document · don't invest more in exit-based optimization |
| Week 2 R1 advisory | Reconciler C1 fails 5-sheet acceptance | Revert to 4-sheet · re-diagnose C1 · do not ship advisory until it passes |
| Week 3-4 P1 calibration | ECE > 0.05 after 4 weekly refits | Try isotonic regression before abandoning · report if both fail |
| Week 5-6 P2 ranking | Best α, β doesn't beat baseline out-of-sample | Skip P2 · go straight to composite · don't ship regime adjustment |
| Week 5 Fundamentals IC | <3 of 13 signals show IC > 0.02 at p<0.05 deflated | Fundamentals expansion doesn't add value · park it · continue with Piotroski + Beneish only |
| Week 7 composite | R1 sample-size floor keeps R1 permanently at zero weight AND R3 shadow hasn't reached 50 trades | Composite is just "R2 renamed" · re-evaluate whether it's worth shipping |
| Week 9-16 shadow | Composite underperforms R2 by >10% at Day 30 | Kill composite · revert to R2-only · document why |
| Any time | `override_allow` gets flipped to true | Immediate stop-work · investigate who/why · revert · post-mortem |

---

## 10 · Deliverables Checklist (auditable)

### Infrastructure (Week 1)

- [ ] `scripts/build_daily_signal_ledger.py` shipped + committed
- [ ] `reports/research/daily_signal_ledger_india.parquet` populated ≥45 days
- [ ] `reports/research/daily_signal_ledger_usa.parquet` populated ≥45 days
- [ ] `scripts/build_fundamentals_feature_store.py` scaffolded
- [ ] `reports/features/fundamentals_{market}.parquet` schema locked
- [ ] `reports/context/r2_signal_funnel_{market}.jsonl` 28-day history
- [ ] R2 zero-entry diagnosis document at `docs/AEGIS/R2_ZERO_ENTRY_DIAGNOSIS.md`
- [ ] All 20 standards documented in this file (done)
- [ ] Standards automation: S1, S2, S7, S10, S13 automated (at least these)
- [ ] `tests/isolation/test_r3_no_production_writes.py` shipped

### R2 track

- [ ] Week 2 · `scripts/replay_dynamic_exit_bridge.py` with OHLC intraday correction
- [ ] Week 2 · `reports/research/exit_bridge_replay_report.json` with per-regime breakdown
- [ ] Week 3-4 · `backend/calibration/platt_calibration.py` with joint-calibration fix
- [ ] Week 4 · Calibrated confidence in Telegram/XLSX
- [ ] Week 5-6 · P2 α, β walk-forward tuned + deflated
- [ ] Week 6 · P2 wired to R2 top-N
- [ ] Week 6 · P3 KG community scoring with PIT snapshot rule

### R1 track

- [ ] Week 2 · `05_R1_Advisory` sheet with regression test
- [ ] Week 3 · R1 daily archive to `data/r1_daily_archive/`
- [ ] Week 4 · R1 calibration (once ≥50 signals in ledger)
- [ ] Week 5 · R1 rolling regime-adaptive sector filter
- [ ] Week 6 · R1 advisory sheet with sector composite scores

### R3 track

- [ ] Week 2 · Isolation skeleton at `backend/research/r3/`
- [ ] Week 3 · LightGBM training loop scaffold
- [ ] Week 4 · R3 trained on Fundamentals Feature Store · walk-forward evaluated
- [ ] Week 5 · R3 shadow ledger live at `reports/research/r3/shadow_ledger.jsonl`
- [ ] Week 5-onwards · Daily isolation CI passes

### Composite + governance

- [ ] Week 7 · `backend/recommendation/composite/` engine
- [ ] Week 7 · Trust_Weight sample-size floor enforced
- [ ] Week 7 · Runner Combination Matrix emitted daily
- [ ] Week 8 · Signal Silence trigger live
- [ ] Week 8 · Minimum Viable Signal floor + hard-cap enforcement
- [ ] Week 8 · `06_Composite_Signals` sheet shipped
- [ ] Week 8 · Sprint retrospective document

### Fundamentals

- [ ] Week 2 · Layer 1 (Quality) 5 signals derived
- [ ] Week 3 · Layer 2 (Value) 4 signals derived
- [ ] Week 4 · Layer 3 (Momentum + Change) 5 signals derived (or documented if data-source gap)
- [ ] Week 5 · Per-signal IC ranking · surviving signals identified
- [ ] Week 6 · Composite `fundamentals_score` column in Feature Store

### Standards

- [ ] All 20 standards enforced (some automated, some documented)
- [ ] Regression tests for A23/I20 admin-filter presence (S15)
- [ ] Pre-commit hook for validator freshness (S10)
- [ ] CI grep for positional column reads (S8)
- [ ] CI grep for canonical filter re-definitions (S7)
- [ ] Isolation CI tests for all three tracks (§7.3)

---

## 11 · Definition of Done (per deliverable)

Every deliverable is complete when ALL of:

1. **Code shipped** — committed to `origin/main` with descriptive commit message
2. **Tests added** — at least one test in `tests/` or `tests/delivery/` covers the new behavior
3. **Standards followed** — no positional column reads (S8) · uses canonical filters (S7) · no untracked user files (S1)
4. **CI green** — 3/3 workflows green on the commit that shipped the deliverable
5. **Documented** — either in this sprint doc's checklist OR in a purpose-specific `.md` in `docs/AEGIS/`
6. **Verified locally** — pytest tests/ 100% pass · delivery_gate ALLOW both markets · xlsx_validator PASS both markets
7. **Reversible** — if deliverable is a code change · rollback path documented (which commit to revert)
8. **Operator-visible changes dry-run** — if operator sees a new sheet/column/banner · verified via `--build-only` local build + XLSX inspection

---

## 12 · Emergency Procedures

### 12.1 · Push failure recovery

Prior sprint had multiple "could not detach HEAD" and rebase conflict cascades. Standard procedure:

```
1. git status --short           # what's uncommitted?
2. git ls-files -u              # any conflicted files?
3. Kill python processes (S2)
4. If conflicts: git checkout --theirs [xlsx files]; git add; git rebase --continue
5. If working tree dirty with only bot artifacts: git checkout HEAD -- .
6. If user documents untracked: git add + commit FIRST (S1)
7. git pull --rebase origin main
8. git push origin main
9. Verify pushed SHA matches local HEAD (S5)
```

### 12.2 · CI failure recovery

If AEGIS USA workflow shows top-level `success` but the operator receives BLOCKED alerts:

```
1. Query per-step conclusions via GitHub API (S6)
2. Identify which step failed (typically `Telegram Command Center`)
3. Reproduce locally: python scripts/telegram_command_center_send.py --market usa --build-only
4. Read the delivery_gate + xlsx_validator output
5. Fix root cause · single-source-of-truth (S7)
6. Push · monitor next scheduled cron slot for verification
```

### 12.3 · Operator receives spam BLOCKED alerts

If the operator's Telegram gets flooded with BLOCKED alerts:

```
1. IMMEDIATELY stop all local Telegram sends (kill any in-flight sender processes)
2. Do NOT enable override_allow · under any circumstance
3. Fix the underlying validation failure at the source
4. Verify local delivery_gate ALLOW before any push
5. Wait for the next scheduled cron slot to confirm fix
6. Post-mortem: which standard would have prevented the alert cascade?
```

### 12.4 · Untracked user document appears

If the CEO/operator places a new PDF, doc, or config in a project folder:

```
1. git add [path]
2. git commit -m "chore: preserve [description] ([date])"
3. git push (or defer if in known bot window)
4. Now safe to run any git operation
```

### 12.5 · A previously-fixed defect returns

If a defect we already fixed re-appears:

```
1. Check if the fix's source file has drifted (S15 regression test should have caught it)
2. Check git log for the file · when was the fix last present?
3. Check if a rebase or stash pop reverted the fix
4. Re-apply the fix · add a regression test if not already present · push
5. Post-mortem: was this a git-hygiene issue (S1-S6) or a code-hygiene issue (S7-S12)?
```

---

## 13 · Post-Sprint Transition

At Week 8 end (Build complete · Live shadow begins):

- **Sprint retrospective document** at `docs/AEGIS/SPRINT_A_RETROSPECTIVE.md`
- **Which of S1-S20 fired** · counts + prevented-issue evidence
- **Which standards need refinement** · concrete amendments
- **Sprint B preview** · what happens in Week 9-16 shadow window
- **Promotion criteria for composite** · quantitative thresholds documented

At Week 16 end (Promotion decision):

- **Sprint A closeout document** at `docs/AEGIS/SPRINT_A_CLOSEOUT.md`
- **Decision:** composite promoted to primary recommendation OR reverted
- **Evidence:** realized 60-day expectancy of composite vs R2-alone · deflated Sharpe · win rate · max DD
- **CEO sign-off:** named, dated, written authorization on promotion
- **Next sprint scope:** if composite promoted, Sprint B addresses tier-2 fundamentals + R3 tier-2 techniques

---

## 14 · Non-Negotiables (final)

- No `override_allow` at any point during sprint
- No R1 reintroduction to production without verbatim CEO authorization
- No R2 engine changes without walk-forward validation + statistical significance + CEO authorization
- No R3 promotion to R2 without deflated-Sharpe out-of-sample validation + CEO authorization
- No hardcoded sector skip lists off small samples
- No promotion of anything based on in-sample backtest results alone
- No Telegram sends outside the normal daily cron (except CEO-authorized dry-runs)
- Every user-facing PDF or doc is committed within the turn it's noticed
- Every push is preceded by full local pytest 100% pass + validator PASS both markets
- Every claim of "shipped" is verified by matching pushed SHA to local HEAD

---

## 15 · Success Criteria

Sprint A succeeds when at Week 16:

- Zero recurrence of the 2026-09-02 failure classes (untracked file loss, admin-filter drift, positional read breakage, cached validator staleness, delivery-gate mis-alignment)
- R2 delivery has been stable for 60 consecutive scheduled cron runs (India + USA)
- Daily Signal Ledger + Fundamentals Feature Store both operational
- R1 advisory sheet visible to operator with rolling sector filter
- R3 shadow ledger accumulating with zero isolation violations
- Composite layer either promoted (evidence-based) or reverted (evidence-based) — no ambiguous outcome
- All 20 standards enforced (some automated, some documented) with retrospective evidence of what they prevented

---

*Sprint A commences 2026-09-03 · baseline commit `be33513d` · reference spec `docs/AEGIS/AEGIS_R1_R2_R3_Implementation_And_Strategy.pdf`. Any deviation from this plan requires named CEO authorization.*
