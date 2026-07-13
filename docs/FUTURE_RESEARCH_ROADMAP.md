# NexaQuant · Future Research Roadmap (Post-LAB010)

**Written:** 2026-07-13 · **Basis:** Post-LAB010 adversarial audit
(see `docs/POST_LAB010_RESEARCH_AUDIT.md`).
**Audience:** future researcher or AI agent with zero chat context.
**Nature:** provisional — every phase may be re-scoped or cancelled after each preceding
phase's evidence.

---

## 1. NexaQuant research state after LAB010

- **Cumulative sealed strategy trials (LAB001–LAB010):** 38 (`india/ai_lab/trial_manifest.md:19`).
- **Candidates promoted to production from any lab:** 0.
- **Production configuration (unchanged since pre-lab era):**
  - `india/recommendation_registry.py:31` — `HOLD = 63` (trading days)
  - `india/recommendation_generator.py:44` — `CONFIG = dict(method="hrp", regime="global", sector_cap=2, rebal=63, name_cap=0.30, ...)`
  - `india/confidence_engine.py:32-51` — `current_regime()` (LAB007 N0; VIX 120d q80 → 0.6/1.0, Nifty 200-DMA → 0.6/1.0, `global_exposure` multiplicative)
  - `india/exit_reasons.py` — cosmetic exit labels, admitted post-hoc (not evidence-backed)
- **Backtest window used repeatedly:** 2021-07-01 → 2026-01-27 across LAB006–LAB010.
- **PBO trajectory across executed labs:** 0.229 (LAB006 Rule C) → 0.700–0.871 (LAB007) → 0.30–0.31 (LAB008) → 0.87–0.84 (LAB009) → **0.90–0.94 (LAB010)**. Rising — signal of exhausted search on this window.

## 2. Executive summary of LAB001–LAB010

- **LAB001 Earnings, LAB002 Fundamentals, LAB003 Events, LAB004 Flows:** STUB. Never executed — datasets never assembled.
- **LAB005 Ranking (learning-to-rank):** STUB on `main` branch; harness claimed on `ai-lab` branch. Price-only test recorded as REJECT (RQS 0.504 vs 0.510 baseline). Blocked pending kept features from LAB001–004.
- **LAB006 Exit Strategy:** EXECUTED. Rules B / C (12 configs) / C1 all REJECTED. Rules A/D not backtestable. +28 trials. `exit_reasons.py` in production is COSMETIC not lab-derived.
- **LAB007 Dynamic Exposure:** EXECUTED. Alternatives A / B / C / D vs production N0 all REJECT. PBO 0.70–0.87 (high). N0 not top-2 in any fold. +4 trials.
- **LAB008 Horizon Calibration:** EXECUTED. H21 / H42 / H84 all REJECT. Post-execution audit → Decision B (methodology-limited: calendar-phase confound + 100% turnover cost overstatement). +3 trials. SUPERSEDED by LAB009.
- **LAB009 Horizon Phase Recalibration:** EXECUTED, three evidence states A → B → C due to maturity-boundary + period-boundary corrections. Final trustworthy state (commit `413a735`): H21 / H42 REJECT, H84 PROMOTE-ELIGIBLE at Lab level only. PBO 0.87 / 0.84. Gate 3 margin +0.021 (tight). Gate 5 at 0.500 boundary. +3 trials.
- **LAB010 H84 Robustness Validation:** EXECUTED. **NOT_VALIDATED.** V4 stress cost + V6 full-window LAB009 replay PASS; V1 / V2 (partial) / V3 (partial) / V5 block-majority FAIL. H84's LAB009 promote-eligibility depends almost entirely on block B2 (2023-07 → 2024-12). +0 trials (validation of counted hypothesis).

## 3. Complete research evidence map

See `docs/POST_LAB010_RESEARCH_AUDIT.md` §1 (single-table view).

## 4. Validated production capabilities

1. HOLD=63 trading day rebalance cadence — "not-rejected" by LAB008/LAB009 (methodology-limited; LAB009 State B/C actually finds H84 marginally preferable, but LAB010 says that finding is fragile).
2. HRP portfolio construction with sector_cap=2, name_cap=0.30 — pre-dates all labs; never challenged.
3. Regime exposure via `current_regime()` (LAB007 N0) — not-rejected by LAB007 vs alternatives A/B/C/D.
4. LAB006-derived methodology fixes (PBO diagnostic-only, DSR from central manifest, mature-bounded common window, period-bounded discovery/confirmation).
5. Sealed preregistration + AST-safe gate evaluator + YAML config + trial manifest.
6. Forensic three-state comparison workflow (LAB009).
7. Pre-seal adversarial audit workflow (LAB010).

## 5. Research-only findings (LAB-level, never promoted)

- LAB009 H84 promote-eligibility (Lab-only; LAB010 says NOT_VALIDATED under LOBO).
- LAB006 Weak-regime exit-rule mechanism (halved CAGR was the price; rejected).
- LAB007 candidate D (fixed 0.85 exposure): marginally-favorable G1 at cash=0% but fails DSR + G6 (regime asymmetry test).

## 6. Unresolved structural weaknesses (evidence-cited from audit §4)

| # | Weakness | Evidence |
|---|---|---|
| W1 | Same 4.5-year backtest window reused across 5 consecutive labs | LAB006 through LAB010 all use 2021-07-01 → 2026-01-27 (or subset). |
| W2 | PBO rising in recent labs | LAB010 PBO 0.90 / 0.94 vs LAB006 Rule C 0.23. |
| W3 | Small-sample power on the promoted-eligible signal | LAB009 H84 has 12–13 cycles per phase; LAB010 LOBO folds 5–11 cycles. Verdict FLIPPED four times on identical data (H42 promote → reject cascade). |
| W4 | Zero forward-paper evidence | No lab has tested production behaviour on post-2026-03-27 data. |
| W5 | HRP portfolio construction untested | Never challenged in any lab against equal-weight, min-var, inverse-vol, etc. |
| W6 | Nominal execution model | Every simulator uses `cost_bps × turnover`; no slippage / market impact / bid-ask / fill quality modeling. |
| W7 | Cosmetic user-facing exit labels | `india/exit_reasons.py` labelled "NOT evidence-backed" but shown to users via `telegram_notify.py`. |
| W8 | Universe never ablated | Nifty-200 chosen a priori; no evidence on Nifty-500 / mid-cap / off-index robustness. |
| W9 | No monitoring / drift detection | No live-vs-backtest divergence alerts. No trial-count discipline dashboard. |
| W10 | Non-price alpha families never touched | LAB001–004 all STUB; no earnings, fundamentals, events, or flows evidence exists. |

## 7. Alpha dimensions already explored

- Rebalance horizon (LAB008 / LAB009 / LAB010)
- Exit rules — vol spike, trailing stop, regime-gated trailing stop (LAB006)
- Dynamic exposure calibration (LAB007)
- Learning-to-Rank on price-only features (LAB005, price-only reject)

## 8. Alpha dimensions NOT explored

- Earnings surprise / guidance / estimate revisions (LAB001 STUB)
- PIT fundamentals + acceleration of ratios (LAB002 STUB)
- Corporate events — approvals, M&A, buybacks, mgmt change (LAB003 STUB)
- Institutional flows — FII / DII / MF holdings changes (LAB004 STUB)
- Learning-to-Rank on enriched features (LAB005 blocked)
- Momentum overlays or momentum-conditional selection
- Cross-sectional value factor
- Sector-conditional strategy dispatch (`sector_cap` is portfolio cap only)
- Multi-horizon overlays (blending 63d with 21d / 84d holds)
- Options / derivatives (universe is equity-only)
- Cross-asset diversification (India equities only)

## 9. Multiple-testing and research-overfitting status

- **Trial count 38** applied to DSR — captures search burden on Sharpe candidates within the sealed hypotheses set.
- **NOT captured by DSR:** the cascade of methodology audits within LAB009 (each corrected bug flipped verdicts) and the reuse of the same window across 5 labs. In practice, the effective search space is larger than 38.
- **Rising PBO** across executed labs (0.23 → 0.94) is the empirical signal that best-config on the training window increasingly fails to survive folded validation.
- **Verdict flips** for H42 across LAB008 / LAB009-A / LAB009-B / LAB009-C are consistent with a signal-to-noise ratio too low to sustain a firm verdict at 12–13 cycles per phase.
- **Recommendation:** any further alpha search on this window should be regarded as manufacturing noise unless the hypothesis is genuinely orthogonal to price-only rebalance/exit/exposure logic.

## 10. Ranked top-5 next research directions

Full scoring table in `docs/POST_LAB010_RESEARCH_AUDIT.md` §8.

1. **MON001** — Forward paper-trading + monitoring of the frozen production system. **Highest priority. Critical.**
2. **ENG001** — Portfolio-construction ablation (HRP vs equal-weight / inverse-vol / min-var). High.
3. **LAB011** (provisional) — Earnings PIT layer test (requires prior data acquisition ENG002). High.
4. **ENG003** — Execution / slippage calibration against broker fills (depends on MON001). Medium.
5. **LAB012** (provisional) — Fundamentals PIT layer test (requires prior data acquisition ENG004). Medium.

## 11. Recommended immediate next phase

**MON001 — Forward paper-trading + monitoring.** Not another lab.

**Rationale:**
- Zero cost — uses existing recommendation output.
- Zero search burden — no new hypotheses; deployment of the already-frozen system.
- Zero data-burn — evidence accrues on FRESH post-2026-03-27 data.
- Highest orthogonality — first true out-of-sample evidence in the project's history.
- Load-bearing for #3 (ENG001), #4 (ENG003), and future labs — everything downstream benefits from a live monitoring substrate.

## 12. Provisional future phase roadmap

**Note:** IDs prefixed `LAB` = alpha search; `ENG` = engineering; `RISK` = risk engineering; `VAL` = validation; `EXEC` = execution research; `MON` = monitoring / operations. Ordering is a working best-estimate — subject to revision after each phase's evidence.

### MON001 · Forward paper-trading + monitoring · Monitoring · CRITICAL

- **Core question:** does the frozen production system (HOLD=63, current_regime(), HRP) achieve backtested Sharpe / MaxDD / turnover / cost characteristics on truly out-of-sample data?
- **Why now:** zero forward-paper evidence exists. All 38 trials were in-sample. Weakness W4.
- **Evidence gap from LAB001-010:** the entire real-world validation dimension.
- **Dependencies:** none.
- **Required data:** live recommendation output + broker fill records (once integrated).
- **Expected output:** rolling live-vs-backtest divergence metrics; drift alerts; capacity/liquidity observations.
- **Production decision it could influence:** decision to halt or continue the frozen system when live drift exceeds envelope.
- **Main failure risk:** insufficient broker-fill integration → live evidence remains a paper simulation.
- **Classification:** monitoring (not strategy search).
- **Trial-count increment:** NONE.
- **Priority:** Critical.
- **Recommended sequence:** first.

### ENG001 · Portfolio-construction ablation · Portfolio · HIGH

- **Core question:** does the production HRP allocation dominate simpler alternatives (equal-weight, inverse-volatility, minimum-variance, rank-weighted) on the same registry?
- **Why now:** HRP is a load-bearing assumption never challenged in any lab. Weakness W5.
- **Evidence gap from LAB001-010:** portfolio-construction dimension entirely untested.
- **Dependencies:** ideally after MON001 has ≥3 months of forward evidence so ablation can be validated on fresh window too.
- **Required data:** existing `data/aegis_registry.csv`.
- **Expected output:** ablation table with all 5 constructions on same picks; DSR + PBO diagnostics; recommended promotion-eligible construction if any.
- **Production decision it could influence:** allocation-rule change (rare; likely not-rejected outcome).
- **Main failure risk:** re-uses same window as LAB006-010 → aggravates W1/W2 unless done AFTER MON001 forward data available.
- **Classification:** alpha search (each construction rule = 1 hypothesis).
- **Trial-count increment:** yes — number of alternative constructions tested.
- **Priority:** High.
- **Recommended sequence:** after MON001 has begun accruing forward evidence.

### ENG002 · Earnings dataset acquisition · Engineering · HIGH

- **Core question:** can we assemble a point-in-time earnings dataset (announcement dates + surprise + guidance + revisions) for the Nifty-200 universe over the 2019-01 → present window?
- **Why now:** LAB001 stub blocked on this data. First non-price alpha family. Weakness W10.
- **Evidence gap:** no non-price alpha dataset exists at all.
- **Dependencies:** none (data engineering, not research).
- **Required data:** sourced from Angel / third-party / press releases. PIT discipline is CRITICAL.
- **Expected output:** `data/layers/earnings.parquet` with strict PIT-safe schema.
- **Production decision:** unlocks LAB011 (earnings PIT gate).
- **Main failure risk:** data quality (missing announcements, misdated), survivorship bias in the constructed panel.
- **Classification:** engineering.
- **Trial-count increment:** NONE.
- **Priority:** High.
- **Recommended sequence:** in parallel with MON001.

### LAB011 · Earnings PIT layer gate · Alpha · HIGH

- **Core question:** does an earnings-surprise / guidance / revision signal produce IC / lift beyond the price-only baseline (RQS 0.510)?
- **Why now:** first true orthogonal-alpha lab. First test that isn't on the same 4.5-year price-only story.
- **Evidence gap:** entire non-price alpha family.
- **Dependencies:** ENG002 must complete first.
- **Required data:** `data/layers/earnings.parquet` (PIT-safe).
- **Expected output:** sealed report on IC / lift / walk-forward / DSR / regime-conditional lift.
- **Production decision it could influence:** if PASS, promotion candidate for feature layer inclusion (long chain to production).
- **Main failure risk:** subtle look-ahead leakage in event dating; survivorship in constructed panel.
- **Classification:** alpha search.
- **Trial-count increment:** yes — 1 per tested variant.
- **Priority:** High.
- **Recommended sequence:** after ENG002.

### ENG003 · Execution / slippage calibration · Execution · MEDIUM

- **Core question:** what is the actual slippage + market-impact profile of the production system on Angel-broker fills?
- **Why now:** every lab uses a nominal cost_bps model with no observed slippage. Weakness W6.
- **Evidence gap:** entire execution modeling dimension.
- **Dependencies:** MON001 must have accrued broker fill data.
- **Required data:** broker fills (Angel API) + backtested-vs-realized trade-level comparisons.
- **Expected output:** calibrated slippage curve; updated simulator cost model.
- **Production decision it could influence:** simulator cost model update (affects all future labs).
- **Main failure risk:** broker fills too few to calibrate; capacity issues obscure slippage signal.
- **Classification:** execution engineering.
- **Trial-count increment:** NONE (calibration, not search).
- **Priority:** Medium.
- **Recommended sequence:** after MON001 accumulates fills.

### ENG004 · Fundamentals PIT dataset acquisition · Engineering · MEDIUM

- **Core question:** can we assemble a PIT fundamentals dataset (as-reported ratios + acceleration deltas)?
- **Why now:** LAB002 blocked on this. Second non-price alpha family. Weakness W10.
- **Evidence gap:** no PIT fundamentals dataset exists.
- **Dependencies:** independent of MON001/ENG002/LAB011.
- **Required data:** paid source or careful scrape with as-reported (NOT restated) discipline.
- **Expected output:** `data/layers/fundamentals.parquet` (PIT-safe).
- **Production decision:** unlocks LAB012.
- **Main failure risk:** using restated numbers instead of as-reported → silent look-ahead. This is why LAB002 README says "using current values = look-ahead and the gate verdict becomes a lie."
- **Classification:** engineering.
- **Trial-count increment:** NONE.
- **Priority:** Medium.
- **Recommended sequence:** after LAB011 establishes non-price lab workflow.

### LAB012 · Fundamentals PIT layer gate · Alpha · MEDIUM

- **Core question:** does PIT fundamentals + acceleration produce IC / lift beyond the price + earnings baseline?
- **Dependencies:** ENG004 + LAB011.
- **Trial-count increment:** yes.
- **Priority:** Medium.

### VAL001 · LAB009 methodology validity re-audit · Validation · MEDIUM

- **Core question:** after LAB010's NOT_VALIDATED verdict, is LAB009's promote-eligible H84 finding a false positive that survived methodology iteration due to search on the same data?
- **Why now:** four verdict flips on H42 across a single dataset suggests the methodology is signal-limited. A retrospective on which methodology corrections were driven by evidence vs. by the desire to flip a specific verdict is warranted.
- **Dependencies:** none — desk audit.
- **Required data:** existing lab evidence.
- **Expected output:** LAB009 audit re-classification (A / B / C) after LAB010 evidence integrated.
- **Production decision it could influence:** whether to formally close LAB008–LAB010 as "horizon question answered: production HOLD=63 remains, no promotion-eligible alternative exists".
- **Trial-count increment:** NONE.
- **Priority:** Medium.
- **Recommended sequence:** any time after MON001 begins.

### RISK001 · Portfolio risk envelope + tail hedging feasibility · Risk · LOW

- **Core question:** what is the tail-risk exposure of the current portfolio construction under stress regimes, and are hedges (index puts, sector shorts) economically feasible?
- **Dependencies:** ENG001 preferred.
- **Trial-count increment:** likely NONE (risk envelope study).
- **Priority:** Low.
- **Recommended sequence:** after ENG001.

### GOV001 · exit_reasons.py disposition · Governance · MEDIUM

- **Core question:** should `india/exit_reasons.py` continue to show COSMETIC (admitted non-evidence-backed) exit labels to users, or should it be replaced with either (a) evidence-backed labels once Rule A forward data accrues, or (b) generic non-diagnostic wording?
- **Why now:** governance risk — users read labels as diagnostic; LAB006 README explicitly says they're not.
- **Dependencies:** LAB006 Rule A forward-collection (score_path_collector.py) has enough data.
- **Trial-count increment:** NONE.
- **Priority:** Medium.
- **Recommended sequence:** any time.

## 13. Dependencies between future phases

```
MON001 (forward paper) ──► ENG003 (execution calibration)
                        └─► informs ENG001 (portfolio ablation) with fresh window
                        └─► informs VAL001 (LAB009 retrospective)

ENG002 (earnings data) ──► LAB011 (earnings PIT gate) ──► LAB005 (LtR ranker)
ENG004 (fundamentals data) ──► LAB012 (fundamentals PIT gate) ──► LAB005 (LtR ranker)
                                                      (LAB005 needs BOTH LAB011 and LAB012 kept features)

ENG001 (portfolio ablation) ──► RISK001 (risk envelope)

GOV001 (exit label disposition) ── independent, gated on LAB006 Rule A forward evidence maturity
```

## 14. Explicit research STOP conditions

Research MUST STOP (or pause) if any of the following occur:

1. Cumulative_strategy_search reaches 60 without a promotion — indicates active search on a data set that cannot support further trials.
2. PBO on any new lab exceeds 0.95 — indicates the top-configs no longer generalize even at LOBO scale.
3. LAB009-style methodology cascade recurs — if a single lab requires ≥ 2 mid-lab methodology corrections, the underlying signal is likely too weak to sustain the hypothesis; close the lab, do not iterate.
4. Live-vs-backtest divergence from MON001 exceeds pre-declared envelope for ≥ 4 consecutive weeks — halt live trading, do not attempt to "fix" via new alpha lab.
5. Trial manifest silent-fallback bug (or equivalent DSR n_trials integrity failure) is discovered again — halt all labs until root cause and framework hardening are complete.
6. A dataset (earnings / fundamentals / events / flows) is discovered to have look-ahead / survivorship contamination after LAB execution — retract lab results.

## 15. Rules for when `cumulative_strategy_search` must increment

Per `india/ai_lab/trial_manifest.md:11-14`:

- **Increment for:** every distinct hypothesis × parameter × policy combination TESTED FOR PORTFOLIO OUTCOMES.
- **DO NOT increment for:**
  - Cost variants of the same hypothesis (canonical + stress are counted as one)
  - Re-runs due to bug fixes (same hypothesis, no new search)
  - Framework refactors (LAB007 v2 was 0 trials)
  - Validation of an already-counted hypothesis (LAB010 correctly did not increment)
  - Post-lab methodology corrections that reprocess the same registry with new bounds (LAB009 State A → B → C was 0 additional trials; the corrections did not test new hypotheses)
  - Monitoring / paper-trading (not a search)
  - Portfolio construction rules if only one construction is used (but AB alternatives → increment)

## 16. Questions that must be answered before starting each future phase

For every phase before it opens:

1. What is the SINGLE hypothesis being tested? (No "test many and pick winner" framing.)
2. What data window will be used, and has any prior lab already searched over it? If so, why is another search justifiable?
3. What are the pre-registered gates and thresholds? Reused from prior lab, or genuinely new?
4. What is the confirmation-period cycle count, and is it ≥ 10 per phase?
5. Under what pre-declared conditions is the result NOT valid? (INCONCLUSIVE path.)
6. Does cumulative_strategy_search need to increment? By how many?
7. What is the leakage-risk profile (temporal, universe, event-dating, cost, PIT)?
8. What is the pre-declared adversarial audit checklist for this lab's methodology?
9. What is the production-promotion path if PASS, and what is the follow-up if FAIL?
10. What is the STOP condition for this specific lab (beyond global STOP conditions)?

Only after all 10 are answered may the lab proceed to preregistration seal.

---

## ROADMAP GOVERNANCE

This roadmap is provisional.

- Completing one phase does not automatically authorize the next.
- Every phase requires a fresh evidence review.
- Alpha hypotheses must be preregistered before execution.
- Validation work must not silently become parameter search.
- Failed hypotheses must remain documented — do not delete failed labs, do not rewrite history.
- Future roadmap items may be cancelled when evidence changes.
- Production promotion requires INDEPENDENT evidence appropriate to the change (out-of-sample where possible; forward-paper where feasible; multi-lab consilience where the change is architectural).
- Trial-count accounting must remain conservative: when in doubt, increment.
- No roadmap item is authorization to modify production. Production changes require a separate, explicit operator authorization tied to the specific change proposed and the evidence supporting it.
- A "promote-eligible" verdict at Lab level is NECESSARY but NOT SUFFICIENT for production promotion. Additional gates (forward-paper divergence, capacity, execution slippage, monitoring coverage) apply.
- If any phase's execution reveals a hidden bug in the lab framework (as LAB009 revealed the mature-boundary and period-boundary defects), pause the roadmap, harden the framework, re-verify prior sealed evidence still holds, and only then resume.
- If MON001 forward-paper evidence contradicts the frozen system's backtested characteristics, HALT the live system before doing additional research.

---

## History (do not edit above without appending here)

- 2026-07-13: Roadmap created after LAB010 NOT_VALIDATED verdict (results commit `a702b99`, seal `0e803eb`). Auditor: Principal Quant Research Architect (adversarial). Basis: `docs/POST_LAB010_RESEARCH_AUDIT.md`.
- 2026-07-13: **MON001 implemented and sealed.** Path: `india/monitoring/MON001_Forward_Validation/`. Sealed fingerprint: `064d8b04eb85b8194e02b07a07ead207770d598be72c46e4ec7698add912d52f`. Sealed envelope hash: `d017b352be54412655142d7bd00dd2d6fcbb1d2a50ce122d8e28e03de4197323` (LAB009 N0=63 State C canonical cost). Forward boundary: `2026-03-28`. Broker: `PAPER_ONLY`. Initial state at seal: `INSUFFICIENT_EVIDENCE` (13 forward trading days accumulated, need ≥ 30 for first metric). 45 forward-eligible recommendations ingested (2 batches from data/aegis_registry.csv). 25/25 adversarial framework tests pass. Production HOLD=63 / rebal=63 unchanged. `cumulative_strategy_search` remains 38. Roadmap ordering NOT modified — this is a factual status update only, per governance rule.
