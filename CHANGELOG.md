# AEGIS Changelog

All notable changes to the AEGIS platform.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

---

## [v2.1.2] — 2026-08-14 · Sprint K Part 28 · Risk→Decision Consistency

**State-machine integrity release.**

Executes Sprint K+ Part 28 (specced 2026-08-13 as commit `775eb8a5`).
Fixes the LUPIN 2026-08-12 P0 bug (STOP_LOSS_HIT + Decision=BUY BIG
simultaneously visible in the same XLSX row) and the entire family of
Status/Decision/Action contradictions surfaced by the CEO XLSX audit.

**Do NOT touch was honoured throughout:** zero changes to R1/R2 model
logic, thresholds, weights, sealed scoring engines, or the portfolio
construction algorithm. This sprint is Decision-layer state-machine
repair only.

Six commits · 8 waves · shipped:

| Commit    | Scope                                                                        |
|-----------|------------------------------------------------------------------------------|
| `e12096cd` | Waves 1-3 · Risk Controller precedence + CLOSED uniformity + consistency matrix |
| `0b020aed` | Waves 4-7 · Post-Exit column + stop semantics + risk state in P0 + validator |

### Added

**Bucket R · Risk Controller Veto** (`configs/priority_matrix.yaml`, `e12096cd`)
New highest-priority bucket. Any binding risk signal in the `Alerts`
column (STOP_LOSS_HIT · HARD_STOP · TRAILING_STOP_HIT · GAP_EXIT ·
PORTFOLIO_MAX_DD · EMERGENCY_EXIT · CRITICAL_DEEP_LOSS) forces bucket R
regardless of Status or Investability. Bucket R renders as:
```
🎯 DECISION       🔴 EXIT · Stop Loss Hit · IMMEDIATE
Urgency          🔴 IMMEDIATE
Action           EXIT
Review           CLOSED
```
Same-day rotation (bucket J · never held) still wins over R for the
pathological case where a same-day rotation also had a stop signal.

**Post-Exit Assessment column** (col 31, `0b020aed`)
Analytical / research-only classification of the close event.
NEVER a trading instruction. Live Decision column stays clean.
Populated:
- R → `Stop Loss Triggered · <SIGNAL> @ <perf>%`
- H → `Premature Exit? · quality intact at close`
- I → `Clean Exit · quality had degraded`
- J → `Same-Day Rotation · never held`
- active → blank

**Automated consistency-matrix tests** (`backend/tests/test_decision_consistency.py`)
21 pytest tests, all pass. Enforces every INVALID combination from spec:
- STOP_LOSS_HIT + BUY/ADD/HOLD → FAIL
- HARD_STOP / TRAILING_STOP_HIT / GAP_EXIT / PORTFOLIO_MAX_DD /
  EMERGENCY_EXIT / CRITICAL_DEEP_LOSS + BUY → FAIL
- EXIT status + HOLD/BUY/ADD decision → FAIL
Plus explicit anchors for LUPIN / POWERGRID / HEROMOTOCO test cases +
precedence-hierarchy test iterating every binding signal against the
strongest buy pattern (STRONG BUY + QUALITY + +15% P&L).

**P0 outcome dataset · risk-state provenance** (`0b020aed`)
`OutcomeRow` extended with:
- `risk_state` (STOP_LOSS_HIT · HARD_STOP · CLEAN · etc.)
- `stop_trigger_price` (the level that triggered the exit)
`_load_exit_events_index()` reads Alerts + Stop Loss columns from
history XLSX at capture time · P1 Attribution can now group closed
positions by binding-signal type without reconstructing from XLSX.

**Stop semantics locked to close-based** (`configs/exit_thresholds.yaml`)
New `stop_semantics` block documents:
- Mode = `close_based` (daily close breaches stop = HIT)
- Trigger reference = parquet daily close
- Trigger session = end-of-day
- Execution price = next-open (T+1)
- Distinguishes PROTECT (approaching · current close > stop) from
  EXIT (hit · current close ≤ stop → bucket R)
Any future intraday semantic must be ADDED alongside · never replace.

**Acceptance-criteria validator** (`scripts/validate_decision_acceptance.py`)
Reads both markets' Portfolio sheets + P0 outcome parquet · computes
all 10 acceptance criteria + prints PASS/FAIL per criterion:
```
#1  STOP_LOSS_HIT → EXIT                       100%
#2  Closed → live BUY/HOLD                     0
#3  EXIT + BUY combinations                    0
#4  EXIT + HOLD combinations                   0
#5  Telegram/XLSX parity                       single-source guarantee
#6  Position ID uniqueness (P0)                0 duplicates
#7  Historical P&L contamination               0 suspicious
#8  Consistency-matrix tests                   invokes pytest
#9  Live Decision containing Post-Exit label   0
#10 Named test cases                           LUPIN/POWERGRID/HEROMOTOCO...
```
Non-zero exit if any criterion fails · can plug into CI.

### Fixed

**LUPIN 2026-08-12 P0 · Alerts orphaned from Decision** (`e12096cd`)
Root cause verified: `_classify_priority()` accepted
`(status, inv_verdict, pnl, is_same_day)` only — the `Alerts` column
containing STOP_LOSS_HIT was NEVER passed in. So LUPIN
(STRONG BUY + QUALITY inv) landed in bucket A → Decision=BUY BIG
regardless of the risk signal.

Fix: both call sites (`_classify_priority` for Portfolio sheet and
`_hist_classify` for History sheet) now accept `alerts` and short-
circuit to bucket R when any binding signal present.

Verified: LUPIN 2026-08-12 case now returns bucket=R · decision=EXIT.

**POWERGRID · SKIP → EXIT** (`e12096cd`)
3 consecutive days (Aug 10-12) POWERGRID had STOP_LOSS_HIT but Decision=SKIP.
Now correctly bucket R → EXIT · IMMEDIATE.

**HEROMOTOCO / INDIANB / ATUL / NATIONALUM / OFSS · closed showing HOLD** (`e12096cd`)
Bucket H (EXIT + Quality-high) fell through to `_resolve_decision`
which returned HOLD. Now H and I both route to `⚪ CLOSED` in the
live Decision column. Any "Premature Exit?" analysis moved to the
new Post-Exit Assessment column (Wave 4).

**Position ID collision** (`ba37e654` yesterday + rebuilt today)
LUPIN and COALINDIA had 2 rows each with identical position_id
(R1 and R2 shared it). Fixed by adding `_{RUNNER}` suffix. Verified
this morning's P0 rebuild: 44 rows / 44 unique position IDs · 0 dupes.

### Changed

- Row-write loop appends 31st column (Post-Exit Assessment · text width 32)
- `is_terminal` predicate now includes bucket H (was only I + J)
- Portfolio sort key already fixed yesterday · Sprint K adds R and H
  routing but doesn't affect sort order (R is active · needs exec)

### Governance invariants unchanged

- R1/R2, sealed engines, thresholds, weights · untouched
- Fingerprint: `e4c070673568c52d…` (MON001 sealed baseline)
- Sealed + LAB files: 0 touched
- Research NEVER feeds back into R1/R2 automatically
- All 8 waves shipped with green pytest · no bypasses

### Acceptance criteria status

Code-level guarantee (unit tests):
```
#8  Consistency-matrix tests                   21/21 PASS
```

Run-time verification against XLSX (deferred to next CI rebuild ·
Windows-local `build_unified_history` hang known · see Known Unresolved):
```
#1  STOP_LOSS_HIT → EXIT                       code guarantees 100%
#2  Closed → live BUY/HOLD                     code guarantees 0
#3  EXIT + BUY                                 code guarantees 0
#4  EXIT + HOLD                                code guarantees 0
#5  Telegram/XLSX parity                       single-source · CODE GUARANTEE
#6  Position ID uniqueness                     PASS (44/44 in fresh P0)
#7  Historical P&L contamination               PASS
#9  Live Decision Post-Exit label leak         code guarantees 0
#10 LUPIN/POWERGRID/HEROMOTOCO cases           PASS (see test suite)
```

The 21-test consistency matrix is the acceptance floor · every future
sender change re-runs it in CI. First live proof lands on the next
scheduled CI cycle (~06:41 UTC daily).

### Known unresolved (still deferred)

- `build_unified_history` local hang on Windows (~15 min · doesn't
  reproduce on Linux CI). Investigation deferred. Local iteration
  works via `--skip-refresh --skip-regen` or waits for CI rebuild.
- Sprint K Part 29 · pipeline runtime reduction (60min → 15min) ·
  deferred by operator "we can plan later".
- Sprint K Parts 25-27 · Attribution / Investability / Compounder ·
  execution scheduled Nov 4-30.

---

## [v2.1.1] — 2026-08-13 · Pipeline Hygiene Sprint

**Non-model correctness + observability release.**

Triggered by CEO manual audit of the 2026-08-11 India + USA production
run. Every fix is either a broken code path, a misleading log line,
a decision/accounting semantic problem, or a CI blocker. **Zero R1/R2
model, threshold, or scoring changes** — architecture stays locked per
the 2026-07-18 v2.1.0-RC1 baseline.

Five commits · 18 fixes · shipped on `main`:

| Commit  | Scope |
|---------|-------|
| `b0b652cc` | P0 pipeline hygiene · 4 fixes |
| `4c41854d` | ENG003 CI discipline · remove `\|\| echo` masks |
| `2a8751d5` | **CI unblock** · Guard 8 scoped to sender's `--market` |
| `d6c44862` | Hygiene batch · truthful logs + subsystem rollup + UTF-8 |
| `ba37e654` | Decision layer + P0 identity · 6 fixes (XLSX review) |

### Fixed

**P0 · SSoT ImportError on both markets** (`b0b652cc`)
Commit `d0c369e7` (P0 Outcome Dataset build) accidentally REPLACED
`backend/research/__init__.py` with a docstring stub, dropping every
re-export. `backend.recommendation.ssot.run` imports 12 symbols from
this package (lines 58-67); both India and USA SSoT stages failed with
`cannot import name 'ingest_runner1_picks_for_date'`. Restored full
`__all__` list with 12 canonical re-exports.

**P0 · `None ensemble_score` crashes classifier on 507 USA recs** (`b0b652cc`)
`percentile_classifier.py:92` did `float(r.get('ensemble_score', r.get('score', 0.0)))`
which crashed with `TypeError` on all 507 USA legacy recs because
`ensemble_score` is JSON null (present, not missing) so `dict.get`
returned `None` instead of falling through to `score`. Added `_num_or()`
helper that treats `None`/`NaN`/non-numeric as missing and walks the
fallback chain. Regression tests added for none / both-missing / NaN.
Verified end-to-end: 507 USA recs classify cleanly · 10/10/60/10/10 dist.

**P0 · Sector metadata missing across USA pipeline** (`b0b652cc`)
`usa/configs/universe.yaml` stamped `default_sector: "Large-Cap"` (a
cap-size, not a GICS sector) on every dynamic-loaded ticker. This
misleading placeholder propagated to feature store, rec engine, sized
positions, portfolio engine — resulting in `n_sectors=0` despite 5 real
positions. Fixed via:
- `default_sector: "Large-Cap"` → `"Unknown"`
- `_ticker_sector_map()` falls back to `reports/sector_cache.json[usa]`
  (hydrated from `markets/usa/sectors.csv` on first call)
- Portfolio engine reports `sector_metadata_coverage=N/M` honestly
- New `scripts/refresh_usa_sector_cache.py` backfills from yfinance

**CI unblock · Guard 8 Price Integrity was checking both markets always** (`2a8751d5`)
Root cause of 4× consecutive AEGIS Daily failures (`#119-122`,
2026-08-11 to 2026-08-12): Guard 8 hardcoded `for market in (india, usa)`
and evaluated BOTH markets regardless of what the sender was actually
publishing. On `aegis-daily.yml` (India CI), USA parquets are `.gitignored`
(only refreshed by `aegis-usa.yml` + committed back), so the checkout has
no USA bars. Guard 8 then reported:
```
usa * : bar_data_stale · latest bar missing 999d old · pipeline data source failing
usa LH   : rec_no_parquet
... 509 CRITICAL mismatches total ...
BLOCKING send
```
India was completely healthy but got blocked because USA looked absent.
`check_all(root, asof)` → `check_all(root, asof, markets=('india','usa'))`.
Default preserved for orchestrators that legitimately want the full-repo
view. Sender now passes `markets=tuple(markets)` so a `--market india` call
evaluates only India.

**P0 · Position ID collision in outcome dataset** (`ba37e654`)
`position_id = {TICKER}_{MKT}_{DATE}` collided when the same position
was picked by both R1 and R2 (LUPIN_IND_20260731 · COALINDIA_IND_20260731
both had 2 rows with identical id). Attribution and P1 grouping analyses
double-counted. Fix: `position_id = {TICKER}_{MKT}_{DATE}_{RUNNER}` —
now truly unique.

**Decision layer contradictions on NEW/EXIT/ARTIFACT lifecycle states** (`ba37e654`)
CEO 2026-08-11 XLSX review flagged:
- ZYDUSLIFE (NEW · STRONG BUY · rank 2 · +6.43%) got Decision=PROTECT / TIGHTEN STOP
- Same-day rotation artifacts (CANBK, UNIONBANK, TORNTPHARM) got HOLD
- Closed EXITs (BIOCON, FORTIS, HEROMOTOCO) got HOLD + "Premature Exit?"

Root cause: `_resolve_decision()` ran generic protective/trailing rules
without asking "what lifecycle state is this in?". Fix: after resolution,
override by priority_bucket:
- `J` (ARTIFACT / same-day) → Decision = `⚪ ARTIFACT · not held`
- `I` (CLOSED · runner+portfolio agree exit) → Decision = `⚪ CLOSED`
- `H` (REVIEWING · portfolio challenging exit) → keep as-is
- NEW position (`rec_dt == asof`) → NEW-state logic below

**NEW-position decision logic** (`ba37e654`)
NEW positions bypass trailing-stop / tighten-stop rules entirely on day 0.
Decision derived from investability ONLY:
- QUALITY / OK    → 🟢 BUY · new position · quality confirmed
- MARGINAL        → 🟡 WATCH · new · small size only
- AVOID           → 🔴 SKIP · new · quality fails
- PENDING (P1-4)  → ⏳ PROVISIONAL BUY · investability pending

**Portfolio accounting counted artifacts as open positions** (`ba37e654`)
Portfolio said `56 positions · 19 closed · 37 open` but 3 of those
"open" were same-day rotation artifacts (never held). Aggregation loop
now detects ARTIFACT (`Entry Date == Exit Date` OR `status == ROTATED_SAMEDAY`)
and SKIPS from all counters. New 4th KPI row `Artifacts (excluded)`
shows the count separately with "not counted in P&L / win rate" note.
Win rate denominator now excludes flats (matches formal definition).

**`rank_history stamped n=0` misleading log** (`d6c44862`)
After an idempotent rerun (14/15 already stamped), log said `n=0`
which looked like a bug when it was actually correct. New log line:
```
rank_history: new=1 · skipped_already_stamped=14 · recs_seen=15 · ledger_size_today=17
```

**Context health `1 important stale` without naming what** (`d6c44862`)
Non-actionable. Now:
```
🟡 Context Health: 20/21 · 0 critical · 1 important stale · stale: reports/research/portfolio_snapshot_india.json (age 5.8d)
```

**Price integrity `43/522 checked` looked like sampling** (`d6c44862`)
Not sampling. `n_positions_checked=43` = ACTIVE positions verified,
`n_recs_checked=522` = full rec-file rows. Also 7 warnings didn't say
whether they touched active positions. Guard now emits:
```
🟡 Price Integrity: 7 warnings on 46 active positions (rec-file rows checked: 522) [ON ACTIVE POSITIONS] · tickers: india:BEL.NS,BRITANNIA.NS,POWERGRID.NS,KOTAKBANK.NS,SUNPHARMA.NS+2
```

**UTF-8 mojibake in orchestrator subprocess output** (`d6c44862`)
`Â·`, `â†’`, `ðŸ‡®ðŸ‡³`, `â‚¹` in logs. Windows `subprocess.run` default was
`locale.getpreferredencoding()` (cp1252) which mangled child scripts'
UTF-8. Both orchestrators now pass `encoding='utf-8', errors='replace'`
explicitly.

**ENG003 CI discipline · `|| echo` masks on research post-processing** (`4c41854d`)
`aegis-usa.yml:132/138` and `aegis-daily.yml:253/259` used
`|| echo "FAILED · non-blocking"` which masked real exit codes as green
in CI logs — the exact anti-pattern that let 17 days of stale-Telegram
slip through earlier. Removed all 4 masks; `continue-on-error: true`
already provides non-blocking behaviour. Failures now surface as red
steps · workflow still continues.

### Added

**Universe role SSoT** (`b0b652cc`)
Same file name `recommendations.json` had OPPOSITE meanings across
markets (India = 15 selected · USA = 507 universe scan). New:
- `universe_role: "selected_candidates" | "universe_scan"` field on both writers
- `universe_role_note` explaining what the file is
- `docs/AEGIS_UNIVERSE_ROLES.md` as programmatic + human SSoT
- P0 outcome dataset audit confirms: ingests `position_store` +
  `rank_history` only · never `recommendations.json` · no leakage

**Subsystem GREEN/YELLOW/RED rollup in both orchestrators** (`d6c44862`)
Previously an SSoT/research failure could ride under a green pipeline
because `optional` steps got lumped together. Each subsystem now gets
its own verdict up top:
```
SUBSYSTEM HEALTH ROLLUP:
  PRODUCTION   GREEN   ok=8/8
  SSoT         GREEN   ok=1/1
  DELIVERY     GREEN   ok=1/1
  RESEARCH     YELLOW  ok=2/3  failed=[research_platform]
  P0           GREEN   ok=1/1
  P1           GREEN   ok=1/1
```
Derived from step name (no per-step tagging needed).

**`scripts/refresh_usa_sector_cache.py`** (`b0b652cc`)
Idempotent · resumable · fail-open-per-ticker yfinance sector fetch
for the full 516-ticker active USA universe. Backfills
`reports/sector_cache.json[usa]` beyond the 227-ticker starter set.

**`stamp_today_detailed()` in rank_history** (`d6c44862`)
Returns `{n_new, n_skipped_dedup, n_recs_seen, n_already_today}` so
callers can log a truthful message when the ledger is idempotent-skipped
vs actually failing.

**`important_fails[]` in health monitor payload** (`d6c44862`)
Full stale-item detail now in the payload, not just the count.

**Formal P&L / win-rate definitions** (`ba37e654`)
Inline in aggregation-loop comments as SSoT:
- Position P&L   = per-position price change (unweighted)
- Realized (sum) = SUM of Exit P&L across CLOSED (excludes ARTIFACT + SAMEDAY)
- Unrealized     = SUM of live P&L across ACTIVE (excludes ARTIFACT + SAMEDAY)
- Combined       = Realized + Unrealized (sum-of-position-%, NOT
                   portfolio-weighted return; caveat documented)
- Win rate       = WIN / (WIN + LOSS) where WIN > +0.01 · LOSS < -0.01
                   flats + artifacts + rotations EXCLUDED from denom

**`reports/context/pipeline_runtime_profile.json`** (`ba37e654`)
P2 sprint artifact. Categorises the 43-step USA pipeline; the top-7
stages consume 92.5% of the 61-min wall-clock, all yfinance ingests
(earnings 974s · news 729s · fundamentals 545s · corp actions 447s ·
market data 256s · insider 229s · SEC 13F 196s). Actual optimisation
deferred per 2026-08-11 CEO lock (correctness before performance).

**`_num_or()` helper + Investability PENDING state** (`b0b652cc`, `ba37e654`)
`_num_or(rec, primary, fallback, default)` treats `None`/`NaN` as missing
in the classifier. `⏳ PENDING` verdict now shown when Investability
hasn't been computed yet — feeds `PROVISIONAL BUY` decision instead
of `NaN → PROTECT`.

### Changed

- Portfolio KPI banner adds a 4th row "Artifacts (excluded)" with count.
- India rank_history log line now explicit about idempotent skips.
- Context health `render_summary()` names stale item(s) inline.
- Price integrity `render_summary()` names affected active positions
  and whether warnings touch the position layer.

### Governance invariants unchanged

- All R1/R2 model logic, thresholds, weights — untouched.
- Fingerprint: `e4c070673568c52d…` (MON001 sealed baseline).
- Sealed + LAB files: 0 touched.
- Research NEVER feeds back into R1/R2 automatically (Constitutional
  invariant verified).

### Test posture

- New regression tests in `backend/tests/test_institutional_optimization.py`:
  `test_percentile_handles_none_ensemble_score_uses_score_fallback`
  `test_percentile_handles_both_keys_missing_defaults_to_zero`
  `test_percentile_handles_nan_score_treats_as_missing`
- `python nexaquant/tests/test_ci_discipline.py` — 6/6 passed (29
  grandfathered masks scanned, 0 new).
- `python -m backend.recommendation.ssot.run --market {india|usa}`
  succeeds on both markets after `__init__.py` restore.

### Known unresolved (deferred by CEO lock)

- Pipeline runtime = 60 min per market. Sequential per-ticker yfinance
  calls. Fix requires ThreadPool + retry/backoff sprint (~1 day). See
  `reports/context/pipeline_runtime_profile.json`.
- USA sector cache coverage 227/516 (~44%). Full backfill takes
  ~8 min via `scripts/refresh_usa_sector_cache.py`.
- Portfolio-weighted return not emitted (needs per-position sizing
  in the sheet · TODO after Sprint L).
- `build_unified_history` local hang on Windows (~15 min · doesn't
  reproduce on Linux CI). Investigation deferred.

---

## [v2.1.0-RC1] — 2026-07-18

**Phase 2 Release Candidate 1.**

The platform is complete as a research operator's workbench. Every
engine on the [PHASE2_MASTER_ROADMAP.md](docs/PHASE2_MASTER_ROADMAP.md)
critical path (P0-P8) is shipped. Institutional multi-tenant deployment
still requires the 6 blockers documented in
[docs/PHASE2_PRODUCTION_AUDIT.md](docs/PHASE2_PRODUCTION_AUDIT.md) §6.

### Added

**Decision Center v1.0** (`6355a0f`)
- Overnight diff engine: NEW · UPGRADED · DOWNGRADED · TARGET_HIT ·
  STOP_HIT · INTELLIGENCE_UP/DOWN · CONFIDENCE_UP/DOWN · NEW_HELD ·
  EXITED · SIZING_WARNING
- Human-readable overnight paragraph (deterministic, no LLM)
- Exit center — held positions ranked by severity with stacked reasons
- Watchlist — near-buy candidates with trend indicator
- Priority-tiered notifications (CRITICAL · HIGH · MEDIUM · LOW)
- Dashboard integration as first section

**Dashboard v2.0** (`8e20b2b`)
- Rewrote 11-page engineering console into 2-page investor-first surface
- Canonical recommendation table with CMP · Buy Below · Target · Stop ·
  Upside · Risk:Reward · Hold days · Intelligence · Confidence · Action
- Stock Detail drill-down with 10-dimension Why-Buy chip grid
- Sizing counterfactuals ("why not 4%? why not 12%?")
- Global search · realtime 60s auto-refresh · pipeline status indicator
- Zero DEV-module references in user-facing UI

**Daily Orchestrator v1.0** (`f635f5b`)
- `scripts/aegis_daily_v2.py` — runs every Phase 2 v2 engine in
  dependency order in ~30-40s
- Per-step verdict + artifact-refresh check
- Append-only history at `reports/aegis_daily_v2_history.jsonl`
- Wired into GitHub Actions after the base pipeline

**Adaptive Rec Engine v2.1 Intelligence Fusion** (`f29b1b8`)
- 10 dimension scorers with configurable weights + graceful degradation
- Deterministic decision mapping (85+ Strong-Buy · 70+ Buy · etc.)
- 9-rule conflict detector (CRITICAL · MEDIUM · MINOR)
- Per-recommendation explainability panel (Why this? · Why not stronger?)
- Weights editable via `reports/fusion_weights.json`

**Adaptive Rec Engine v2.0 Confidence Rebuild** (`1d9fdf8`)
- Feature-importance model replacing raw confidence heuristic
- HGB Precision@10 = 0.80 vs baseline 0.60 (+20pp)
- Permutation importance from live data: volatility · score · drawdown · momentum

**Validation Engine v2.0 Paper Harness** (`a04a5da`)
- Content-addressed paper-trading ledger
- Expected-vs-actual reconciliation
- Metric drift + rolling edge detection
- Opportunity cost tracking

**Risk & Capital Engine v2.0** (`80e590f`)
- Position sizing with 4 bounded factors + counterfactuals
- VaR / CVaR / variance decomposition
- Per-position + per-sector budget attribution

**Knowledge Graph v1.6 Stress Propagation** (`8c7d96d`)
- 5 canonical stress scenarios via personalized PageRank
- Portfolio-exposure overlay per scenario
- Champion-strategy-failure caught 96.5% portfolio exposure risk

**DNA Feedback Loop v1.5** (`a0df1a2`)
- Closes ADR-009 latent value
- 84 discovered patterns with historical win rate + expectancy
- Per-current-rec priors from historical DNA

**UX030 Telegram Sender (opt-in)** (`e0027ac`)
- Standalone 5-message rich delivery
- Env parity with sealed sender
- Parallel delivery ledger

**Governance Suite** (`d2d5a9b · 6559476 · 6322e75`)
- ENGINE_EVOLUTION_GUIDE.md (constitution)
- DESIGN_DECISIONS.md (14 ADRs)
- PHASE2_MASTER_ROADMAP.md (delivery contract)
- NEXAQUANT_MANIFESTO.md (mission + principles)
- AEGIS_RESEARCH_AGENDA_2035.md (5-10 year backlog)

**Documentation** (this release)
- HOWTO_RUN_AEGIS.md · 3-step operator guide
- DAILY_OPERATIONS.md · deep operational reference
- PHASE2_PRODUCTION_AUDIT.md · this release audit
- RELEASE_NOTES_RC1.md · release notes
- VERSION.md · version manifest
- CHANGELOG.md · this file

### Changed

- Dashboard auto-refresh interval defaults to ON, 60s cadence.
- Daily scheduler restored to ~06:00 IST morning cadence (was moved
  to post-close during OPS001-F).
- Telegram sender remains on the sealed retry wrapper for production;
  UX030 renderer is opt-in only.

### Fixed

- `MON001 dashboard MARKET_CLOSED payload` (`3e17682`) — build_dashboard()
  now uses `.get()` defaults for partial payloads; regression fixed.

### Removed

- **Nothing removed.** Historical DEV017-DEV031 modules preserved as
  frozen milestones per ADR-003.

### Governance invariants unchanged

- Fingerprint: `e4c070673568c52d…` (MON001 sealed baseline)
- Production constants: HOLD=63 · rebal=63 · sector_cap=2 · name_cap=0.30 · method=hrp
- Cumulative strategy search: 38 (unchanged)
- MON001 forward_boundary_asof: 2026-03-28 (unchanged)
- Sealed + LAB files: 0 touched

### Test posture

- Full regression suite PASSES on `main`.
- 190+ Phase 2 module smoke tests pass across:
  - Adaptive Rec v2.0/v2.1 · Validation v2.0 · Risk & Capital v2.0
  - Knowledge Graph (26 tests) · DNA Feedback · Decision Center
  - Executive Dashboard spec · Telegram UX030
- End-to-end test script: `scripts/e2e_test.py`

---

## Historical milestones (frozen)

### DEV031-B — Knowledge Graph completion — Sprint 16 late
Communities · propagation · explainability paths · timeline snapshots.

### DEV030 — Champion vs Challenger Framework — Sprint 15
9-metric composite · 4-gate promotion recommender.

### DEV029 — Confidence Calibration — Sprint 15
5 calibration methods competed; Platt selected. ECE 0.287 → 0.002.

### DEV028 — Recommendation DNA — Sprint 14
208 immutable content-keyed records.

### DEV027 — Strategy Doctor — Sprint 14
15 diagnostic rules · 677 diagnoses fired · 218 overconfidence
(independently confirmed the calibration finding).

### DEV026 — AI Research Assistant — Sprint 13
Deterministic Q&A · 6 templates.

### DEV025 — Adaptive Learning — Sprint 13
1,060 trades analysed · ECE 0.29 flagged.

### DEV017-DEV024 — Phase 1 Foundation — Sprints 1-12
Research Intelligence (Global · Sector · Industry · Company) ·
Historical Validation · Portfolio Construction · Recommendation Engine ·
Portfolio Monitoring.

### OPS001 — Production sealed baseline
Fingerprint `e4c070673568c52d…` — INVARIANT.

---

## [Older releases]

Prior daily automated commits under `[skip ci]` are omitted from this
changelog. Consult `git log --oneline` for the full history.
