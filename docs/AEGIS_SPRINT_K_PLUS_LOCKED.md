# AEGIS · Sprint K+ · Locked Production Spec

**v1.8 amended 2026-08-18 (CEO final architectural fix · Position
Lifecycle + Opportunity Registry + Output Integrity)**: added **Part 30
· Opportunity Registry + Daily NEW Discovery Engine** (executed same
day · 5 waves shipped). Origin: Aug 18 India workbook audit surfaced
Zydus (NEW every day since Aug 11), ONGC/HINDUNILVR (Recommended date
restamped daily), INDIGO (NEW+CLOSED same day appearing in active
Portfolio), NTPC/BATAINDIA/LICI/TATAPOWER (EXIT + ACTIVE coexistence),
and 60-column Portfolio being unusable as a decision cockpit. Operator
verbatim: "AEGIS must stop treating today's recommendation as a new
opportunity. It needs a persistent Opportunity Registry."

Part 30 answers this with an event-sourced Registry that gives every
investment idea one immutable `opportunity_id` + `created_date` across
its entire lifecycle. Every downstream NEW/EXISTING/CLOSED/REJECTED
determination now reads the Registry · not today's XLSX. Also adds a
zero-tolerance validation gate (11 checks from operator Section 26),
Portfolio 3-section banner layout (NEW / EXISTING / ACTION REQUIRED /
CLOSED), 14-column hide-in-Excel for slim client view, INDIGO REJECTED
filter, and a daily discovery diagnostic file. All shipped same day as
5 commits (0380fe4e · 3fb264e2 · dd915ad5 · aa422853). Sprint K now
30 parts · execution window unchanged.

**v1.2 amended 2026-08-08**: added Part 25 (Dual-Snapshot Attribution) +
Part 26 (Institutional Investability Engine · 9 sub-engines · replaces
blocklist thinking) + Part 27 (Emerging Compounder research module ·
smallcap discovery). Sprint K now 27 parts · execution window extends
to 2026-11-28.

**v1.3 amended 2026-08-08**: expanded Part 26 from 9 → 11 sub-engines
(added Valuation + Risk per operator directive · "amazing company at
PE=180 = wait" and "beta/correlation/tail/gap/drawdown risk"). Also
created **Sprint L** post-Sprint-K roadmap for Distillation Engine +
Capital Preservation Engine · both are learning/protection layers that
require Sprint K's attribution + walk-forward data to be useful. See
`docs/AEGIS_SPRINT_L_LEARNING_LAYER.md` for full Sprint L spec.

**v1.4 amended 2026-08-08 (evening)**: after CEO review of Portfolio v2:

- Priority column split into 4 orthogonal fields (Urgency · Reason ·
  Action · Review) · rationale: "current Priority mixes portfolio state
  + opportunity + diagnosis + execution · split for AI learning"
- Priority aging added to Part 25 scope (Day 1 Quality Dip → Day 8 Watch
  → Day 18 EXIT) · Priority should not stay frozen · decay based on
  outcome trajectory
- Priority Confidence deferred (needs classifier-boundary distance calc ·
  Sprint K Part 25 sub-item)
- Priority accuracy dashboard added to Part 25 (measure win rate per
  bucket after n≥50 · calibrate thresholds)
- "Reason narrative" (human-readable per-position explanation like
  "high-quality business · temporary technical weakness · expected
  holding period 30-90 days") added to Part 25 attribution
  snapshot deliverable

**v1.7 amended 2026-08-13 (CEO XLSX audit + runtime deferral)**: Two new
Parts added after CEO manual review of 2026-08-12 India workbook + runtime
discussion. Both deferred out of the 2026-08-11 hygiene sprint per operator
"we can plan later":

- **Part 28 · Risk→Decision Consistency Audit** (see below · full spec).
  Origin: LUPIN 2026-08-12 had `STOP_LOSS_HIT · -6.2%` in Alerts but
  Decision=`🟢 BUY` / Action=`BUY BIG`. Root cause: priority classifier
  reads (status, inv_verdict, pnl) only · Alerts column is orphaned ·
  Risk Controller signal never reaches the Decision layer. Also affects
  POWERGRID (3 consecutive days) + closed positions HEROMOTOCO · INDIANB ·
  ATUL · NATIONALUM · OFSS showing Decision=HOLD after actual closure.
  Sprint K Part 28 = strict Risk-Controller-precedence + consistency
  matrix + Post-Exit Assessment separation. ~1 full day of work.

- **Part 29 · Pipeline Runtime Reduction** (see below · full spec).
  Origin: manual `python scripts/aegis_run_all.py` takes ~60 min per
  market. Profile at `reports/context/pipeline_runtime_profile.json`
  shows 92.5% of runtime is 7 yfinance ingest steps, all sequential
  per-ticker. Target: 60 min → 12-15 min per market via ThreadPool +
  batch + staleness-aware skip. ~1 full day of work.

Sprint K now 29 parts · execution window extends to 2026-11-30.

**v1.6 amended 2026-08-08 (final)**: Constitutional rule from operator:
"all developments should be dynamic · no hardcoding at all."

This is now a governance invariant enforced across all future sprints:
- Every threshold · weight · limit · magic-number MUST live in YAML config
  under `configs/`
- Code MAY reference config values via loaders but NEVER hardcode
- New engines must ship WITH their config file · not code constants
- Sprint K Part 25 attribution data will drive config tuning · not code deploys
- Config changes are version-controlled but need no code review / redeploy

Enforcement in Sprint K:
- Every Part must audit its own module for hardcoded values before ship
- Externalize into `configs/{engine_name}.yaml` on first touch
- Add `configs/*.yaml` schema validation as Part 24 acceptance check

Externalized 2026-08-08 as proof-of-principle:
- `configs/investability.yaml` · all 11 weights + 4 thresholds + 6
  threshold-groups (fundamental · technical · liquidity · risk ·
  governance · bond_yields)

To externalize when next touched (per new rule):
- `configs/priority_matrix.yaml` · 10-bucket lookup table
- `configs/india_universe_tiers.yaml` · NIFTY 50 largecap seed + tiers
- `configs/status_fills.yaml` · row color mapping
- `configs/xlsx_schema.yaml` · Portfolio + History column definitions
- `configs/exit_thresholds.yaml` · stop-loss · deep-loss · rapid-gain

**v1.5 amended 2026-08-08 (night)**: after CEO review of Portfolio v3
(scored Readability 9.4 · Decision 9.6 · Institutional 9.3 · AI Learning 9.7):

**PRESENTATION LOCKED** for observation window 2026-08-11 to 2026-08-15.
No Portfolio format changes during this period. Focus is entirely on
collecting outcomes for classifier calibration.

Nine improvements queued for Sprint K Part 25 execution (Nov 4-10):

1. **Urgency numeric score** (0-100 internal) with display
   "🔴 HIGH (95)" · enables training on "urgency 95 → 91% correct exits"
2. **Review dynamic** · replace "5 DAYS" with actual date "Next Review:
   2026-08-13" OR trigger-based conditions (Price < Stop, sector improves,
   Fed meeting, news changes)
3. **Action + sizing** · replace "BUY" with "BUY 3% / Max 5%" · full
   position sizing per rec
4. **Reason narrative expansion** · multi-line explanation stored per
   position (currently one-word tag like "Quality Dip")
5. **Action Note → AI Narrative** · rename + expand to LLM-generated
   contextual explanation (Sprint L Part L1 Distillation output)
6. **Exit Reason in portfolio language** · "Rotation: HEROMOTOCO → GNFC ·
   Higher expected alpha +10.6%" instead of developer syntax
   "→ GNFC.NS +10.6pp alpha"
7. **Confidence Change tracking** · yesterday-vs-today delta with reason
   (e.g., "83 → 71 · sector weakness + Fed event")
8. **Decision ID** · unique identifier (D-20260808-IND-00431) linking
   every change · review · exit · re-entry · attribution
9. **Outcome loop** · YES/NO did-this-decision-succeed feeding Sprint L
   Distillation Engine

Execution deferred to Sprint K Part 25 (Nov 4-10) · attribution snapshot
module already scoped · these become sub-fields of the snapshot schema.

**Observation criteria · 4-stage validation (revised 2026-08-08 per CEO
review · "5 trading days is not enough · some recs have 60-90 day horizons"):**

### Stage 1 · Sanity check (Aug 11-15 · 5 trading days)

Not a decision milestone · noise-check only. Look for:
- Any Priority tag clearly WRONG for a specific ticker (log for review)
- Any bucket producing obviously bad decisions (systematic misclassification)
- Pipeline health: no missed days · guards green · sends successful

**No threshold changes this window** regardless of what data shows.

### Stage 2 · First statistical review (~Sep 8 · 30 trading days)

Minimum sample for meaningful statistics. Track EVERY recommendation ·
not just the 9-ticker A/B test.

Metrics computed for every Priority bucket:
- N recommendations issued
- N closed (Status became EXIT)
- Win rate (% with P&L > 0)
- Average return
- Median return
- Max drawdown per position
- Time to recovery (Priority C specifically)
- False-positive rate (Priority G that recovered · Priority A that failed)

### Stage 3 · Production decision (~Oct 6 · 60 trading days)

Sample size sufficient for institutional confidence (n≥50 closed).
Investability hard-gate promotion decision · multi-metric (not just bucket
success):

Promote to hard-gate ONLY IF ALL 5 conditions met:
1. Portfolio total return IMPROVED vs pre-Investability baseline
2. Portfolio max drawdown REDUCED vs baseline
3. Rotation quality maintained (Rotation Outcome Tracker win rate ≥ 55%)
4. Opportunity discovery not reduced excessively (fresh_buys count ≥ 80% of baseline)
5. Priority C recovery rate > 55% AND Priority G continued-weakness rate > 65%

**Any single failing condition = defer promotion · investigate.**

### Stage 4 · Constitutional lock (~Nov 4 · 90 trading days)

Full statistical validity. Sprint K Part 25 (Attribution) begins on this
date and consumes the accumulated data. Constitutional lock means:
- Investability Engine promoted to hard-gate (if all Stage 3 conditions met)
- Priority classifier thresholds calibrated from real outcomes (not intuition)
- Attribution snapshots retroactively populated for all Stage 2-3 recs

---

**Zero-feature discipline (Aug 11 → Nov 3):**

Per CEO directive: "I would not write another feature for the next week."
Extended to entire pre-Sprint-K window. Only allowed changes:
- Bug fixes (must be reproducible + regression-tested)
- Data pipeline maintenance (parquet · reports · daily runs)
- Documentation updates (Sprint K plan refinements)
- Observation logs · scorecards (not features · just tracking existing data)

NO CHANGES ALLOWED:
- No new columns in Portfolio or History sheets
- No new sub-engines in Investability
- No threshold changes (Investability · Priority · Runner)
- No universe expansion
- No caption reformatting
- No new alerts / guards / notifications

If operator identifies something worth adding · queue as v1.6 amendment ·
implement in Sprint K Part 25 window (Nov 4-10) with real data grounding.

---

**Daily observation scorecard (passive · uses existing data · not a feature):**

Nightly script `scripts/daily_scorecard.py` (to be added Aug 11 morning
as maintenance code · not new feature) reads:
- aegis_history_india.xlsx
- aegis_history_usa.xlsx
- investability_india.json
- investability_usa.json

Emits `reports/research/daily_scorecard_{date}.json`:
```json
{
  "asof": "2026-08-11",
  "priority_distribution": {"A": 2, "B": 5, "C": 4, ...},
  "day_over_day_p&l": +0.34,
  "misclassification_flags": [],   // populated at Sep 8 review
  "cumulative_since_lock": {
    "n_priority_C_issued": 4,
    "n_priority_C_recovered": null,   // determined at exit
    "n_priority_G_issued": 4,
    "n_priority_G_kept_falling": null
  }
}
```

Zero cost to build (reuses existing data readers). Feeds Sprint K Part 25
Attribution as training corpus.

**Signed into force:** 2026-08-06
**Author:** CEO (operator · locked · binding)
**Governance:** Constitutional · supersedes docs/AEGIS_SPRINT_K_PLAN.md
**Execution window:** 2026-09-10 → 2026-11-30 (~55 days · aligned with Runner 3 Day-90 gate)
**Post-Sprint stance:** 90-day paper-trading validation · no new features · no new engines

---

## Constitutional constraints (from operator directive)

- AEGIS v3.0 architecture is **constitutionally frozen**
- **Runner 1 is SEALED** · zero code touches
- **Runner 2 is under shadow evaluation** · minimal changes only
- Goal is NOT redesign · goal is **production-grade lifecycle completion**
- **Every change must be additive** · no schema breaking
- **No engine replacement · no feature duplication · no second Excel**
- **One canonical XLSX** · **one canonical Position Store**

---

## Part 1 · Regression audit (do FIRST · before any code)

Verify every prior sprint still works · regression test each:
- Recommendation IDs · Entry Price freezing · Position Store · Position Stage
- R1_NEW / R2_NEW · Trading Days · Current Performance · Previous Close
- Dynamic Today % · Recommendation Date · Position ID

**Never assume · verify by regression.**

## Part 2 · Position becomes permanent

Every recommendation is an object · never recreate · never overwrite · never
disappear. Lifecycle:
```
Discovery → NEW → BUY → ACTIVE → ADD → HOLD → REDUCE → ROTATE → EXIT → ARCHIVED
```
Every recommendation remains visible forever (even after EXIT → ARCHIVED).

## Part 3 · Immutable fields (freeze forever)

Recommendation ID · Position ID · Recommendation Date · Discovery Date ·
Engine · Country · Ticker · Company · Original Rank · Original Confidence ·
Original Alpha · Entry Price · Original Buy Zone · Original Stop ·
Original Target 1 · Original Target 2 · Original Portfolio Weight · Original Horizon

## Part 4 · Daily snapshot fields (update every trading day)

Snapshot Date · Current Price · Previous Close · Today % · Current Return % ·
Max Gain · Max Drawdown · Current Rank · Previous Rank · Weekly Rank ·
Monthly Rank · Current Confidence · Current Alpha · Current Health ·
Current Band · Sector Score · Market Score · Macro Score · News Score ·
Context Drag · Risk % · Dynamic Stop · Dynamic Buy Zone · Dynamic Targets ·
Portfolio Weight · Action · Status · Days Held · Days Left · Trading Days ·
Calendar Days · Last Updated

## Part 5 · Recommendation Continuity Engine

Store per-recommendation history: Rank · Confidence · Alpha · Price ·
Health · Context · News · Sector · Portfolio Weight · Reason.

Timeline shape (Jul 29 NEW → Jul 30 BUY → Jul 31 HOLD → Aug 5 REDUCE →
Aug 10 EXIT → ARCHIVED). **Never lose history.**

## Part 6 · Recommendation evolution

Daily compute Rank/Confidence/Score/Weight/Reason CHANGES · explain **WHY**
(not just "Rank changed" · give the driver breakdown).

## Part 7 · Position tracking

`Current Return = (Current Close − Frozen Entry) / Frozen Entry`

Entry NEVER changes. Current/Previous/Today% change daily.
Max Gain · Max DD · Dynamic Risk all update daily.

## Part 8 · Dynamic Risk Engine

Replace static risk. Daily compute: ATR · Volatility · Sector Risk · Macro
Risk · Market Regime · Liquidity · Gap Risk · Event Risk.

Risk % must evolve. Stop Loss must trail. Targets must trail. Buy Zone must
widen or narrow.

## Part 9 · Dynamic Confidence Engine

Confidence = Model Score × Sector Score × Market Regime × Macro × News ×
Breadth × Institutional Flow × Volatility × Correlation × Portfolio Context.

**Confidence must NEVER be model-only.**

## Part 10 · Context Engine (Runner 2's final gate)

Inputs: Market · Sector · News · Macro · Economic Calendar · Institutional
Flow · Portfolio · Correlation · Earnings Risk · Volatility.

These adjust Confidence / Position Size / Recommendation / Action.
**They DO NOT change raw model score.**

## Part 11 · Economic Calendar Engine

Integrate Fed · RBI · ECB · BOE · BOJ · CPI · PPI · GDP · PMI · Payrolls ·
Interest Rates · Major Elections · Budget · FOMC · RBI MPC · Holiday
Calendar · Expiry Calendar · Global Events.

Creates: Event Risk · Context Drag · Review Required.

## Part 12 · News Engine

Don't summarize · **classify**. Positive/Negative/Neutral · Affected
Sector/Stocks · Severity · Expected Duration · Confidence Impact ·
Portfolio Impact · Context Impact.

## Part 13 · Sector Engine (active · not informational)

Compute per sector: Breadth · Relative Strength · Momentum · Leadership ·
Institutional Rotation · Earnings Trend · News · Valuation · Liquidity ·
Volatility · Score. Runner inherits sector score.

## Part 14 · Recommendation Review Engine

Immediate review on: sector drops · market crashes · VIX spikes ·
Fed/RBI event · earnings miss · gap >3% · macro event · war · tariff ·
FII reversal · commodity shock.

Review → Reduce → Exit → Archive. **Don't wait for tomorrow.**

## Part 15 · Profit Protection Engine

If recommendation +12% AND target reached AND momentum weakens AND news
deteriorates AND sector weakens AND context weakens → automatically Reduce ·
Trail Stop · Partial Exit · Exit. **Protect gains · don't wait for horizon.**

## Part 16 · Rotation Engine

Never rotate 5 stocks → 1 stock without handling allocation. Combine · Cap ·
Split · Prioritize. **Portfolio cap always wins.**

## Part 17 · Runner comparison

Compare complete lifecycles (BUY → HOLD → EXIT) · not snapshots. Metrics:
Final Return · Holding Days · Max DD · Risk · Sharpe · Sortino · Hit Rate ·
Average Gain · Average Loss · Expectancy.

## Part 18 · Excel

**One workbook · never split.** Existing format remains. Only additive
columns. No breaking changes. Every historical workbook remains readable.

## Part 19 · New Opportunities

Same sheet. Run_Type R1_NEW / R2_NEW on first appearance · auto-decay to
R1 / R2 tomorrow. New discoveries appear BESIDE existing positions · never
replace existing rows. Discovery Rank / Portfolio Rank remain separate
internally.

## Part 20 · Data Quality

Verify daily: Recommendation Date · Snapshot Date · Current Price · Previous
Close · Today % · Entry Price · Buy Zone · Risk · Stop · Target · Portfolio
Weight · Days Held · Days Left all update correctly. **Never overwrite
frozen fields.**

## Part 21 · Telemetry

Daily log: Recommendations Created · Updated · Closed · Archived · Review
Triggered · Context Overrides · Risk Overrides · Runner Consensus · Market
Regime · Data Quality · Failures.

## Part 22 · Self Learning

Every closed recommendation feeds back into Position Store · Recommendation
Store · Feature Store · Backtest Store · Model/Confidence/Alpha/Risk
Calibration.

**No online learning · retraining only after evidence review.**

## Part 23 · Regression Tests

Before release verify: Recommendation continuity · Position continuity ·
Excel integrity · Telegram integrity · Ranking · Dynamic Risk · Dynamic
Confidence · Rotation · Runner comparison · Lifecycle · Context Engine ·
Economic Calendar · News Engine · Sector Engine · Profit Protection ·
Data freshness.

## Part 24 · Production Acceptance Criteria (all must pass)

✓ Recommendations never disappear
✓ Entry prices never change
✓ Current prices update daily
✓ Dynamic risk updates daily
✓ Confidence adapts daily
✓ Context influences decisions
✓ Sector influences decisions
✓ News influences confidence
✓ Economic calendar influences risk
✓ Portfolio concentration respected
✓ Profit protection active
✓ Recommendation continuity maintained
✓ Excel remains backward compatible
✓ Telegram remains concise
✓ Runner comparison evidence-based
✓ Every recommendation fully auditable
✓ Every recommendation has entry + loss-trigger attribution snapshot
✓ Every closed loser categorized into 1 of 6 loss types
✓ Weekly rollup identifies avoidable vs unavoidable losses

---

## Part 25 · Dual-Snapshot Attribution (Winners + Losers)

Added 2026-08-08 · operator directive after CEO-level "why" audit:
"same way, think of negative P&L stocks analysis too · and add this to
sprint K · plz add to sprint K docs all ur analysis on winning and
loosing what u wanna do."

### 25.1 · Rationale · why this is the highest-leverage add

**Winner analysis without loser analysis is confirmation bias.** Losers
reveal WHICH assumption broke · winners just say "everything worked."
One clear loss teaches more than three ambiguous wins.

**Loss asymmetry math.** 5 winners @ +3% = +15%. 3 losers @ -8% = -24%.
Losses swamp gains. Fix the losses first · that's where 10x improvement
lives.

**Current state gap.** We already compute:
- `reports/model_attribution.json` (per-model contribution)
- `reports/feature_attribution.json` (per-feature contribution)
- `reports/decision_attribution.json` (per-decision explainer)
- `reports/walkforward_per_sector.json` (sector-level rollup)

All exist as raw JSON · none surfaced per-position at operator level. Part
25 unifies these into ONE consumer-ready snapshot per (position_id).

### 25.2 · Winner attribution framework

**Snapshot at entry time.** Captured once when rec fires. Immutable.

Fields:
```json
{
  "position_id":       "HINDZINC_IND_20260804",
  "entry_snapshot": {
    "top_signals":     [{"name": "Momentum",  "score": 91},
                         {"name": "Sector",    "score": 82},
                         {"name": "Value",     "score": 78}],
    "confidence":      0.65,
    "regime_at_entry": "bull",
    "sector_breadth":  "strong",
    "vix_level":       14.2,
    "runner":          "R2",
    "conviction_band": "high"
  }
}
```

**Winner insights after n≥50:**
- Which top signal drives most winners? (Momentum? Value? Quality?)
- Which regime × runner combination has highest hit rate?
- Which sector concentration produces most wins?
- Does high confidence → higher win rate? (calibration check)
- Optimal holding period per signal type?

### 25.3 · Loser attribution framework

**Two-snapshot approach:** entry_snapshot (what we thought) + loss_snapshot
(what actually happened) + delta_analysis (what changed).

Fires when Perf < -3% (early loss detection) OR Status=EXIT with negative
P&L. First fire wins · subsequent updates append to history.

Fields:
```json
{
  "loss_snapshot": {
    "current_signals": [{"name": "Momentum",  "score": 45},
                         {"name": "Sector",    "score": 60},
                         {"name": "Value",     "score": 76}],
    "confidence_now":  0.34,
    "regime_at_loss":  "neutral",
    "days_from_entry": 6,
    "loss_pct":        -3.27
  },
  "delta_analysis": {
    "biggest_weakener":      "Momentum · dropped 91→45",
    "biggest_strengthener":  null,
    "regime_shifted":        true,
    "regime_shift_direction": "bull → neutral",
    "sector_relative_perf":  -4.2
  },
  "guard_verdict": {
    "stop_hit":        true,
    "stop_price":      524.78,
    "actual_exit":     527.10,
    "days_to_stop":    3,
    "guard_effective": true
  }
}
```

### 25.4 · Loss category classifier · 6 categories

Rule-based · deterministic · every loss gets exactly one category.

| # | Category | Detection rule | Actionable output |
|---|---|---|---|
| 1 | **guard_worked** | Status=EXIT · Exit Reason=STOP_LOSS_HIT · realized loss between -5% and -8% · exit within 5 days of trigger | Count frequency · system healthy · no action |
| 2 | **guard_failed** | Realized loss ≤ -8% AND days_to_exit > 5 · (stop-loss too slow) | **Tighten stop-loss OR add intraday guard** |
| 3 | **regime_shift** | Loss between -2% and -6% · slow bleed over 7+ days · regime_at_loss != regime_at_entry | **Invest in faster regime detection** |
| 4 | **selection_error** | Confidence at entry ≥ 0.60 · loss ≥ -5% · biggest_weakener not "SectorDrag" or "RegimeShift" · fundamentals broke | **Signal-quality issue · which feature lied?** |
| 5 | **rotation_loss** | Original position exited via Rotation → X · X's return over same holding period WORSE than original would have been | **Rotation Outcome Tracker's core verdict** |
| 6 | **unavoidable_market** | Loss between -1% and -4% · sector_relative_perf < -3% · rest of universe also down · macro drag | Not our fault · but flag position-sizing risk |

Learning tag: `avoidable | unavoidable | guard-failure`

### 25.5 · Portfolio "Why (top 3)" column · dual-mode

Column added to Portfolio sheet (v_1.1 lock schema). 40-char limit.

**Winners / HOLDs · positive framing:**
```
HINDZINC   · +8.17% · "Mom91 · SectorStrong · Value78"
BATAINDIA  · +3.10% · "Value85 · Mom76 · Quality72"
TCS        · +3.00% · "Momentum88 · Quality85 · IT-tailwind"
```

**Losers · deterioration framing:**
```
SUNPHARMA  · -3.27% · "MomDecay 88→45 · SectorWeak · RegimeShift"
POWERGRID  · -3.18% · "SectorDrag · RegimeNeutral · MomStable"
BIOCON     · -0.11% · "Rotation·not decay · engine picked LUPIN"
FORTIS     · -1.08% · "SelectionErr · Fundamental miss · Guard-fail"
```

**Notice the difference:** SUNPHARMA lost because momentum decayed
(avoidable · signal weakness). POWERGRID lost because whole sector was
weak (unavoidable · macro drag). Different diagnoses → different fixes.

### 25.6 · Weekly rollup · actionable output

Path: `reports/research/monthly/loss_category_review.json`

Emits:
```json
{
  "week_ending":  "2026-11-07",
  "n_closed":     47,
  "n_losers":     18,
  "categories": {
    "guard_worked":       {"n": 8,  "avg_loss": -5.2, "pct_of_losers": 44},
    "guard_failed":       {"n": 3,  "avg_loss": -9.8, "pct_of_losers": 17},
    "regime_shift":       {"n": 4,  "avg_loss": -3.4, "pct_of_losers": 22},
    "selection_error":    {"n": 2,  "avg_loss": -6.5, "pct_of_losers": 11},
    "rotation_loss":      {"n": 1,  "avg_loss": -4.1, "pct_of_losers": 6},
    "unavoidable_market": {"n": 0,  "avg_loss":  0.0, "pct_of_losers": 0}
  },
  "auto_flags": [
    {"severity": "HIGH", "type": "guard_failure_rate",
     "message": "17% guard failures · exceeds 15% threshold · propose stop-loss to -4% from -5%"},
    {"severity": "MED",  "type": "selection_error_sector_concentration",
     "message": "Both selection errors in Financials · propose masking below confidence 0.65"}
  ]
}
```

**Actionable queries after n≥50 losers:**

| Query | Threshold action |
|---|---|
| `% guard_failure > 15%` | Tighten stop-loss OR add intraday guard |
| `% regime_shift > 30%` | Faster regime detection · shorter lookback |
| `% selection_error > 20%` | Signal-quality regression · which feature is stale |
| Selection errors concentrated in sector X | Mask sector X below confidence threshold |
| Guard-failures cluster at gap-downs | Add pre-market gap detection |
| Regime-shift losers hold days > 7 | Faster regime-transition triggers |

### 25.7 · Feedback into Part 22 self-learning · closed loop

Part 22 (Self-Learning) currently feeds closed positions into calibration
adjustments. Part 25 enriches this with WHY:

**Before Part 25:** "Closed 47 positions this week · win rate 62% · avg
+2.1%"

**After Part 25:** "Closed 47 · win rate 62% · avg +2.1% · **17% guard
failures suggest stop-loss too loose · 22% regime shifts suggest we're
slow to detect bear turns · 2 of 3 selection errors were Financials
sector**"

The second version is actionable. The first is descriptive.

### 25.8 · Deliverables (7 concrete modules)

1. `backend/recommendation/attribution_snapshot.py`
   - `snapshot_entry(rec, market)` · called at rec creation
   - `snapshot_loss(position_id, market)` · called when Perf<-3% or EXIT
   - Persists to `reports/rec_attribution/{market}/{position_id}.json`

2. `backend/recommendation/loss_classifier.py`
   - `classify(position_snapshot, entry_snapshot) -> LossCategory`
   - 6-category rule engine · deterministic

3. `backend/delivery/telegram/detail_xlsx.py` update
   - Add "Why (top 3)" column to Portfolio sheet builder
   - 40-char truncation · dual-mode (winner/loser)

4. `backend/research/loss_rollup.py`
   - Weekly aggregator · emits `loss_category_review.json`
   - Auto-flags exceeding thresholds

5. `backend/recommendation/attribution_backfill.py`
   - One-shot: backfill entry_snapshot for existing positions
   - Uses historical parquet + recommendations.json archive

6. `backend/tests/test_attribution_snapshot.py`
   - Verify snapshot fires at correct pipeline stages
   - Verify 6 loss categories classify correctly on fixture data

7. `backend/tests/test_loss_classifier.py`
   - 6 fixture positions · one per category
   - Regression test: no category drift on schema change

### 25.9 · Acceptance criteria (Part 25 specific)

- [ ] Every position (past 90 days) has entry_snapshot backfilled
- [ ] Every loss (past 90 days) has loss_category assigned to 1 of 6 buckets
- [ ] Weekly rollup produces actionable auto-flags (not just descriptions)
- [ ] Portfolio "Why" column populated for all displayed positions
- [ ] Regression test verifies attribution captured at correct pipeline stage
- [ ] Loss classifier produces same category on same input (deterministic)
- [ ] Auto-flags integrate with Guard 7 (context health monitor) as WARNING signals
- [ ] Zero R1/R2 core code touches (Constitutional invariant preserved)

### 25.10 · Success metric · what Part 25 must prove by Nov 30

**Baseline (before Part 25):** operator asks "why did SUNPHARMA lose?" ·
we grep JSONs across 6 files · answer is speculation.

**Target (after Part 25):** operator opens Portfolio sheet · reads
"SUNPHARMA · -3.27% · MomDecay 88→45 · SectorWeak · RegimeShift" ·
knows in 3 seconds. Weekly rollup tells us WHICH of 6 causes dominates
losses that week · what specific fix to propose.

**Numerical target:** by end of Sprint K, ≥80% of closed positions have
non-null attribution snapshot · ≥90% of losers have category assigned ·
weekly rollup generates ≥1 actionable auto-flag per week.

### 25.11 · Rationale for winners + losers being ONE module (not two)

Considered splitting into Part 25a (winners) + Part 25b (losers). Rejected
because:
- Same data source (per-rec snapshot)
- Same storage (one file per position_id)
- Same consumer (Portfolio "Why" column · dual-mode display)
- Splitting doubles integration complexity for zero benefit

The framing "winners AND losers" makes the design symmetric · one snapshot
schema serves both.

---

## Part 26 · Institutional Investability Engine

Added 2026-08-08 · operator directive after IEX/JSWENERGY exclusion
discussion: "engine should read parameters · not hardcode blocklist ·
should be powerful enough to blocklist or pull best of best from
small caps."

### 26.1 · Core insight

**Every stock gets TWO independent scores.** Neither alone is sufficient.

- **Opportunity Score** (Runner 2 output) · "how attractive right now?"
- **Investability Score** (new · this part) · "should we own this at all?"

Final decision: `Opportunity × Investability` composite. A stock must
clear BOTH gates to be recommended.

**Why this beats blocklist:**
- No hardcoded ticker lists to maintain
- IEX becomes buyable IF regulatory clarity improves
- JSWENERGY becomes buyable IF debt improves
- Small-cap gems become buyable IF investability score is high
- **No human intervention needed** · engine self-corrects

**Why this beats simple weighted-exclusion:**
- Symmetric · works for both "avoid" and "discover"
- Universe-expandable (Nifty 200 → 500 → Midcap 150 → Smallcap 250)
- Institutional pattern (Bridgewater / Two Sigma structure their pipelines the same way)

### 26.2 · Eleven sub-engines with weights (v1.3 · expanded 2026-08-08)

Operator directive: current v1.2's 9 engines miss two critical dimensions:
1. **Valuation** — separates "quality company at bad price" from "poor
   quality". Current Wave 1 flagged HDFCBANK REJECT because tech was
   weak · but HDFCBANK is quality-at-bad-price (Valuation < 15 P/E · would
   flip to HOLD not REJECT with valuation lens).
2. **Risk** — beta/correlation/tail/gap/drawdown risk. Distinct from
   technical trend. A stock in uptrend can still have unacceptable gap
   risk (earnings vol · sector concentration).

| # | Sub-engine | Weight | Data source | Signals |
|---|---|---|---|---|
| 1 | **Fundamental** | 22% | yfinance + Screener API | ROE · ROCE · Revenue CAGR · EPS CAGR · Margin · FCF · Debt · Interest cov · WC · Capital allocation |
| 2 | **Technical** | 15% | Parquet + TA | RS · Trend · Volume profile · ATR · ADX · Breakout · Vol contraction · AVWAP · MTF trend · Momentum persistence |
| 3 | **Governance** | 13% | SEBI + BSE announcements + company reports | Auditor changes · Promoter pledge · Board quality · Independent directors · SEBI notices · Litigation · Insider buy/sell · ESG |
| 4 | **Ownership** | 9% | Shareholding pattern | FII trend · MF trend · PMS · Insurance · Promoter buying · Concentration |
| 5 | **Sector** | 9% | Existing sector_report + rotation | Sector momentum · Breadth · Rotation · Relative perf · Earnings revisions |
| 6 | **Macro** | 4% | Existing macro engine | RBI · Fed · Inflation · GDP · Bond yields · Crude · Dollar · Currency |
| 7 | **Liquidity** | 4% | NSE bhavcopy | Delivery % · Volume · Turnover · Spread · Impact cost |
| 8 | **News/Event** | 4% | News feed | Impact classification (Positive/Neutral/Negative/Very Negative) |
| 9 | **Earnings** | 5% | Earnings calendar + estimates | Earnings date · Surprise % · Guidance · Revision trend · Estimate revisions |
| **10** | **Valuation** | **8%** | Fundamental + peer-relative | P/E vs 5yr avg · P/E vs sector · P/B · EV/EBITDA · PEG · earnings yield vs bond yield · dividend yield trend |
| **11** | **Risk** | **7%** | Parquet + macro | Beta · sector correlation · tail-risk (95th percentile daily drawdown) · gap-risk (overnight moves) · max historical DD · vol regime |

Total: 100%. Valuation and Risk are NEW in v1.3 · address the HDFCBANK
false-REJECT case (Valuation lens flips it to HOLD) and add explicit
tail/gap risk measurement.

### 26.3 · Pipeline position (CRITICAL)

The Investability Engine sits **BEFORE** Runner 1 and Runner 2.

```
Universe (Nifty 200 · later 500 · later smallcap)
    ↓
Investability Engine
    ↓  (filter: Investability ≥ 60)
Runner 1  |  Runner 2
    ↓
Context Engine
    ↓
Portfolio Engine
    ↓
Recommendation Continuity
```

**Not** an after-filter. The engines only see stocks that pass institutional
investability. This is the reverse of blocklist thinking.

### 26.4 · Universe expansion strategy

Current: Nifty 200. Target progression:

```
Sprint K (this):           Nifty 200 + Nifty Next 50   =  250 stocks
Sprint K + 3 months:       + Nifty Midcap 150           =  400 stocks
Sprint K + 6 months:       + Nifty Smallcap 250         =  650 stocks
Sprint L (2027):           + BSE 500 · SME watch        = ~800 stocks
```

Investability filter is what makes universe expansion safe · without it,
adding smallcaps floods the ranker with noise. With it, we discover
tomorrow's midcaps.

### 26.5 · Decision matrix

| Investability | Opportunity | Decision |
|---|---|---|
| ≥ 80 | ≥ 70 | STRONG BUY |
| ≥ 70 | ≥ 60 | BUY |
| ≥ 60 | ≥ 50 | HOLD (existing positions) |
| < 60 | any | REJECT (never recommend) |
| any | < 40 | REJECT (Opportunity insufficient) |

Composite score: `Final = 0.6 × Opportunity + 0.4 × Investability`

Ranking: sorted by Final · top-15 becomes recommendations.

### 26.6 · Delivery

**Portfolio sheet gains 2 columns:**
- **Investability** (0-100 · number)
- **Why Investable** (top 3 sub-engine drivers · 40 chars)

Example:
```
HINDZINC · Opp 91 · Inv 84 · "Fund91 · Gov97 · Liq88"  → STRONG BUY
IEX      · Opp 92 · Inv 42 · "Fund74 · Gov39 · Reg23" → REJECT
Unknown SmallCap · Opp 88 · Inv 89 · "Fund94 · Gov92 · Own85" → BUY
```

### 26.7 · Deliverables (8 modules)

1. `backend/investability/__init__.py`
2. `backend/investability/fundamental.py` · ROE/D-E/growth signals
3. `backend/investability/technical.py` · RS/ADX/vol-contraction
4. `backend/investability/governance.py` · pledge/auditor/SEBI
5. `backend/investability/ownership.py` · FII/MF/promoter trends
6. `backend/investability/liquidity.py` · delivery/volume/turnover
7. `backend/investability/scorer.py` · weighted aggregator → 0-100
8. Ranking hook · pre-Runner-1/Runner-2 filter

### 26.8 · Data sources needed (net-new)

- Screener.in API (or manual CSV export) · deep fundamentals
- BSE/NSE shareholding-pattern quarterly parquet
- SEBI announcements RSS · governance flags
- Earnings estimate revisions · Refinitiv-lite alternative

### 26.9 · Execution window

**2026-11-11 to 2026-11-17** · after telemetry/attribution (Parts 21-22, 25)
so Investability can consume attribution data for feature validation ·
before Part 23 regression suite.

### 26.10 · Acceptance criteria

- Every ticker in universe has non-null Investability score
- IEX (real-world test case) scores < 60 · REJECT
- JSWENERGY scores < 60 · REJECT (unless leverage improves)
- Adding new small-cap to universe · engine auto-scores · no manual list
- Portfolio sheet shows Investability + Why-Investable columns
- Regression test: same input → same score (deterministic)
- Universe expansion Nifty 200 → 250 (add Next 50) verified working

---

## Part 27 · Emerging Compounder Engine (research module)

Added 2026-08-08 · operator directive: "we should also pull such stocks
and analyze to make profits [from small cap]."

### 27.1 · Different objective

**Not** a recommendation engine · a **research watchlist generator**.

Part 26 (Investability) says "is this stock good enough to recommend TODAY?"

Part 27 (Emerging Compounder) says "is this stock likely to be a 3-5x
compounder over 3 years?"

Different question · different data · different output.

### 27.2 · Compounder signals (weight-composed)

- Revenue CAGR ≥ 20% (3-yr and 5-yr)
- EPS CAGR ≥ 25% (3-yr)
- ROCE ≥ 20% consistent
- Debt-to-Equity < 0.5
- FCF positive 3 of 5 years
- Reinvestment rate high · low dividend payout
- Promoter holding ≥ 50% and stable/increasing
- Institutional ownership INCREASING (FII/MF quarter-over-quarter)
- Technical structure: base-building over 12+ months · not extended
- Sector: not sunset industry (regulatory/technology risk)

### 27.3 · Output

Weekly watchlist: `reports/research/emerging_compounders_{market}.json`

Top 20 candidates · each with:
- 3-year expected return band (rough estimate)
- Key risks
- Trigger conditions to promote to main universe
- Quarterly earnings watch dates

**Not** for immediate trading · for research + waitlist. Operator manually
reviews weekly · promotes candidates to main universe when triggers hit.

### 27.4 · Why kept separate from Part 26

- Different time horizon (3 years vs quarterly)
- Different data weight (growth vs current quality)
- Different consumer (research vs trading)
- Mixing would corrupt both scores

Kept as standalone research module · outputs a watchlist · never
auto-recommends. Human-in-loop by design.

### 27.5 · Execution window

**2026-11-18 to 2026-11-22** · after Investability Engine so we can use
its scoring as a filter on the compounder candidate pool.

### 27.6 · Deliverables

- `backend/research/emerging_compounder.py` · signal engine
- `reports/research/emerging_compounders_india.json` · weekly watchlist
- `reports/research/emerging_compounders_usa.json` · weekly watchlist
- Manual review process: operator flags approved candidates · gets added to
  universe expansion for next Sprint K review

**Deliverables.**

1. **Entry attribution snapshot** (`backend/recommendation/attribution_snapshot.py`)
   Fires at rec-creation time · captures top 3 positive signals, confidence,
   regime, sector breadth. Stored at
   `reports/rec_attribution/{market}/{position_id}.json` under `entry_snapshot`.

2. **Loss-trigger snapshot**
   Fires when Perf < -3% OR Status=EXIT. Captures deteriorating signals,
   biggest weakener, regime-at-loss, guard verdict. Same file under
   `current_snapshot` + `delta_analysis` + `guard_verdict`.

3. **Loss classifier** (`backend/recommendation/loss_classifier.py`)
   Rule-based · assigns each loss to 1 of 6 categories:
   · guard_worked (stop-loss fired on schedule)
   · guard_failed (deep loss · stop-loss too slow)
   · regime_shift (slow bleed · macro turned)
   · selection_error (fundamentally broken · signal lied)
   · rotation_loss (opportunity cost from rotation)
   · unavoidable_market (whole sector/market drag)
   Learning tag: avoidable | unavoidable | guard-failure

4. **Portfolio "Why (top 3)" column**
   Dual-mode display:
     Winners:  "Mom91 · SectorStrong · Value78"
     Losers:   "MomDecay 91→45 · SectorWeak · RegimeShift"
   40 chars max · truncated for glance.

5. **Weekly rollup** (`reports/research/monthly/loss_category_review.json`)
   For each of 6 categories: count · avg loss · % of total losses ·
   dominant sector/regime. Auto-flag if:
     - guard_failure > 15% (tighten stop-loss)
     - regime_shift > 30% (faster regime detection)
     - selection_error concentrated in one sector (mask below conf X)

6. **Feedback loop into Part 22 self-learning**
   Loss patterns feed calibration adjustments · closed-loop learning
   answers "which combinations reliably fail" not just "which win."

**Execution window.** 2026-11-04 to 2026-11-10 (7 days · runs parallel to
Parts 21-22 telemetry/self-learning · attribution IS the telemetry).

**Acceptance criteria.**
- Every position (past 90 days) has entry_snapshot backfilled
- Every loss (past 90 days) has loss_category assigned
- Weekly rollup produces actionable recommendations (tighten X, mask Y)
- Portfolio "Why" column populated for all displayed positions
- Regression test verifies attribution captured at correct pipeline stage

---

## Execution timeline (55 days · Part 25 slotted parallel with 21-22)

| Window | Focus | Deliverable |
|---|---|---|
| 2026-09-10 to 2026-09-13 | Part 1 · Regression audit | Green tests · issue log |
| 2026-09-14 to 2026-09-22 | Parts 2-4 · Position permanence + immutable/dynamic split | Position Store v2 · XLSX shape locked |
| 2026-09-23 to 2026-09-30 | Parts 5-7 · Continuity + Evolution + Tracking | rec history JSON per position · daily evolution diff |
| 2026-10-01 to 2026-10-08 | Part 8 · Dynamic Risk Engine (ATR-based) | dynamic stop/target/buy-zone/risk% |
| 2026-10-09 to 2026-10-14 | Parts 9-10 · Confidence + Context Engine (Runner 2 gate) | multiplicative confidence + context final-gate |
| 2026-10-15 to 2026-10-20 | Parts 11-13 · Calendar + News + Sector engines | 3 engines active · scored per rec |
| 2026-10-21 to 2026-10-25 | Parts 14-15 · Review + Profit Protection triggers | intraday review engine · profit-lock automation |
| 2026-10-26 to 2026-10-30 | Part 16-17 · Rotation + Runner Comparison | lifecycle-based comparison · not snapshot |
| 2026-10-31 to 2026-11-05 | Parts 18-20 · Excel/Data Quality validation | backward-compat regression |
| 2026-11-04 to 2026-11-10 | Parts 21-22 + **Part 25** · Telemetry + Self-Learning + **Attribution snapshots** | daily telemetry · calibration feedback · entry+loss attribution · loss classifier · weekly rollup |
| 2026-11-11 to 2026-11-17 | **Part 26** · Institutional Investability Engine | 9 sub-engines · Investability score · pre-Runner filter · universe expansion Nifty 200→250 |
| 2026-11-18 to 2026-11-22 | **Part 27** · Emerging Compounder Engine (research) | Weekly compounder watchlist · 3-year horizon · separate from recommendation flow |
| 2026-11-23 to 2026-11-28 | Part 23 · Full regression suite | all tests green |
| 2026-11-16 to 2026-11-30 | Part 24 · Production Acceptance sign-off | 16-checkbox sign-off |

**Post-2026-11-30**: FEATURE FREEZE. Move to 90-day paper-trading /
validation / calibration mode. No new engines. No new features.

---

## Governance rules for Sprint K+ execution

1. **Regression first · code second** (Part 1 mandates full audit before any change)
2. **Additive only** · never break the existing 54-column XLSX schema
3. **No R1 India code touches** (SEALED · Constitution Article X)
4. **R2 changes minimal** · limited to universe expansion + ensemble output shape
5. **One commit per Part** where possible · easier revert
6. **Each Part has its own regression test** before merge
7. **Guard 7 monitors every new engine output** as CRITICAL
8. **All Part 24 checkboxes must pass** before declaring Sprint K+ complete

---

## Part 28 · Risk→Decision Consistency Audit

**Added 2026-08-13** · CEO audit of 2026-08-12 India workbook found the
Risk Controller signal is orphaned from the Decision layer. The final
Decision can independently recompute BUY/HOLD after a binding stop-loss
has fired. This is a state-machine integrity bug, not a scoring issue.

### 28.1 · The bug

LUPIN 2026-08-12 · exact XLSX rows shown to operator:

```
Ticker         LUPIN
Alerts         STOP_LOSS_HIT · -6.2% ≤ -5.0% · exit
Current Perf%  -6.20%
Status         STRONG BUY
🎯 DECISION    🟢 BUY
Action         BUY BIG
Urgency        🔴 HIGH
Reason         Conviction Buy
Review         30 DAYS
```

Reading these fields left to right: risk fired stop-loss, decision layer
still says BUY BIG. That is not "one decision engine disagreeing with
another" — it means the risk controller's veto never reached the layer
that talks to the user.

Root cause (verified in code):
`scripts/telegram_command_center_send.py:_classify_priority()` accepts
`(status, inv_verdict, pnl, is_same_day)` — the `Alerts` column
containing STOP_LOSS_HIT / HARD_STOP / TRAILING_STOP_HIT etc. is never
passed in. Priority bucket resolves purely from runner status + investability,
so LUPIN (STRONG BUY + QUALITY inv) lands in bucket A and gets
`🟢 BUY · high conviction` regardless of what the risk layer said.

Also affects 4 STOP_LOSS_HIT rows in current workbook:

| Date   | Stock     | Perf   | Alert         | Current Decision | Correct |
|--------|-----------|-------:|---------------|------------------|---------|
| Aug 10 | POWERGRID | -5.53% | STOP_LOSS_HIT | ⚫ SKIP           | 🔴 EXIT |
| Aug 11 | POWERGRID | -6.28% | STOP_LOSS_HIT | ⚫ SKIP           | 🔴 EXIT |
| Aug 12 | POWERGRID | -6.75% | STOP_LOSS_HIT | ⚫ SKIP           | 🔴 EXIT |
| Aug 12 | **LUPIN** | -6.20% | STOP_LOSS_HIT | **🟢 BUY**       | 🔴 EXIT |

POWERGRID resolves to SKIP (not EXIT · still wrong) · LUPIN resolves to
BUY BIG (catastrophically wrong).

### 28.2 · Required precedence hierarchy

Risk-controller output is binding. In priority order:

```
1. EMERGENCY / HARD STOP             (unrecoverable · immediate exit)
2. PORTFOLIO MAX DD                  (portfolio-level circuit breaker)
3. GAP / VOLATILITY EXIT             (bar-level risk event)
4. TRAILING STOP HIT                 (profit-protection binding)
5. REDUCE                            (partial exit)
6. PROTECT                           (tighten stop · no exit)
7. HOLD                              (no action)
8. BUY / ADD                         (risk-increasing · lowest priority)
```

A BUY signal MUST NEVER override a higher-priority EXIT signal.

Alerts vocabulary that must trigger EXIT precedence:

```
STOP_LOSS_HIT
HARD_STOP
TRAILING_STOP_HIT
GAP_EXIT
PORTFOLIO_MAX_DD
EMERGENCY_EXIT
```

### 28.3 · State transitions

On any binding risk event:

```
Status         →  EXIT  (or EXIT_PENDING if execution unconfirmed)
🎯 DECISION    →  🔴 EXIT
Action         →  EXIT
Urgency        →  🔴 IMMEDIATE
Review         →  CLOSED
Reason         →  Hard Stop Hit  (or the specific alert reason)
Price Trigger  →  Hard Stop @ <price>
```

### 28.4 · Closed positions must never show live HOLD/BUY

Current workbook has 5 rows with `Status = EXIT · Decision = HOLD ·
Reason = Premature Exit?` (HEROMOTOCO · INDIANB · ATUL · NATIONALUM ·
OFSS). This is confusing — user sees exit + hold and cannot tell what
to do.

Fix: once genuinely closed →

```
Decision  →  ⚪ CLOSED
Action    →  CLOSED
Review    →  CLOSED
```

Any post-exit analysis ("Premature exit · would have kept +10.6%") moves
to a NEW separate column `Post-Exit Assessment` — never mixed with the
live Decision column.

### 28.5 · Stop-loss semantics (must be explicit)

Determine and document whether stops are:

1. **Close-based** (only trigger if close ≤ stop)
2. **Intraday-low-based** (trigger if low ≤ stop that day)
3. **Execution-confirmed** (only after actual fill)

Without this decision, `STOP_LOSS_HIT` is ambiguous — an intraday breach
that recovers by close would be labeled a hit under (2) but not (1).

Recorded fields per exit:
```
stop trigger price
trigger timestamp/session
reference price
execution price if known
exit price
realized P&L
```

### 28.6 · Live Decision vs Post-Exit Assessment

Two orthogonal concepts · never mixed:

**LIVE DECISION vocabulary** (what to do right now):
```
BUY · ADD · HOLD · PROTECT · REDUCE · EXIT · CLOSED · SKIP
```

**POST-EXIT ASSESSMENT vocabulary** (what happened after close):
```
Clean Exit · Premature Exit · Missed Upside · Good Rotation ·
Bad Rotation · Stop Loss · Target Achieved · Time Exit
```

### 28.7 · Consistency matrix (automated test)

Every rendered row must satisfy the validation table. Add
`backend/tests/test_decision_consistency.py`:

```
VALID
  STRONG BUY + BUY + BUY
  HOLD + PROTECT + TIGHTEN STOP
  HOLD + HOLD + HOLD
  EXIT + EXIT + EXIT
  EXIT + CLOSED + CLOSED
  STOP_LOSS_HIT + EXIT

INVALID (any occurrence = test failure)
  EXIT + HOLD + REVIEW
  EXIT + BUY + BUY BIG
  STOP_LOSS_HIT + BUY
  STOP_LOSS_HIT + ADD
  STOP_LOSS_HIT + HOLD
```

Wire the check into the existing regression suite.

### 28.8 · Telegram / XLSX parity

Both channels must consume the SAME `final_decision` object. XLSX must
never say `🔴 EXIT` while Telegram says `🟢 BUY` for the same ticker on
the same day. Single source. Add a parity assertion in the sender.

### 28.9 · P0 / P1 outcome dataset integration

P0 Outcome Dataset must record for each closed position:
```
Position ID · Risk State · Decision · Entry · Stop · Stop Trigger ·
Exit Date · Exit Price · Exit Reason · Exit P&L
```

P1 Attribution must use these canonical values (not reconstruct exits
independently from XLSX rows).

### 28.10 · Acceptance criteria (all must pass)

```
1. STOP_LOSS_HIT → EXIT                          100%
2. Closed → live BUY/HOLD                        0
3. EXIT + BUY combinations in workbook            0
4. EXIT + HOLD combinations in workbook           0
5. Telegram/XLSX decision mismatch                0
6. Position ID mismatch (P0/XLSX)                 0
7. Historical P&L contamination                   0
8. Consistency-matrix test failures               0
9. Live Decision containing Post-Exit label       0
10. LUPIN/POWERGRID/HEROMOTOCO test cases         PASS
```

### 28.11 · Do NOT touch

- R1/R2 model logic, weights, thresholds
- Sealed engines
- Portfolio construction algorithm
- Decision vocabulary rules that ARE correct today (BUY/HOLD/PROTECT/etc.)

This is state-machine repair · not model change.

### 28.12 · Estimated effort

~1 full day of focused work · 8 waves:

1. Alerts feed into priority classifier (LUPIN fix) · 2 hrs
2. Closed → CLOSED for all buckets not just I · 1 hr
3. Consistency matrix + test · 1.5 hrs
4. Post-Exit Assessment column split · 1 hr
5. Stop semantics doc + PROTECT vs EXIT · 1 hr
6. State continuity + immutability · 1 hr
7. Telegram/XLSX parity + P0/P1 reconciliation · 1 hr
8. Final smoke + 10 acceptance criteria · 0.5 hr

---

## Part 29 · Pipeline Runtime Reduction

**Added 2026-08-13** · manual `python scripts/aegis_run_all.py` currently
takes ~60 min per market. CI can absorb this (once per day) but local
iteration is painful. Profile artifact:
`reports/context/pipeline_runtime_profile.json`.

### 29.1 · Baseline

USA pipeline 2026-08-13 run · total 3676s (61 min) across 43 steps.
Top 7 stages consume 92.5%:

| Stage                    | Time  | % of total | Nature                    |
|--------------------------|------:|-----------:|---------------------------|
| ingest_earnings          | 974s  | 26.5%      | yfinance per-ticker       |
| ingest_news              | 729s  | 19.8%      | Google News RSS per-ticker|
| ingest_fundamentals      | 545s  | 14.8%      | yfinance per-ticker       |
| ingest_corporate_actions | 447s  | 12.2%      | yfinance per-ticker       |
| refresh_market_data      | 256s  | 7.0%       | yfinance OHLCV per-ticker |
| ingest_insider           | 229s  | 6.2%       | yfinance per-ticker       |
| ingest_sec_13f           | 196s  | 5.3%       | yfinance per-ticker       |

All 7 are sequential per-ticker loops over ~500 tickers · ~0.5-1s network
round-trip each · CPU idle. This is the entire bottleneck.

### 29.2 · Three levers (ordered by effort/impact)

**Lever A · Staleness-aware skip** (~2 hrs · low risk)
Only refetch tickers whose parquet/JSON is older than N hours. Skips
~40% of already-fresh tickers on a typical day.
Expected: 60 min → ~35 min per market.

**Lever B · ThreadPool parallelism** (~1 full day · medium risk)
`concurrent.futures.ThreadPoolExecutor(max_workers=6)` around each
per-ticker loop in the 7 ingest modules. Requires:
- Per-worker semaphore to avoid yfinance rate limits
- Exponential backoff on 429/503
- Retry with jitter
- Integration test on each of the 7 modules
Expected: 60 min → ~12-15 min per market.

**Lever C · Batch API where yfinance supports it** (~2-3 hrs · medium risk)
`yfinance.Tickers(list).info` batch-fetches fundamentals + earnings for
multiple tickers per call. Schema quirks in batch responses need handling.
Expected: additional 20-30% on those 2 stages.

### 29.3 · Recommended combo

**A + B combined** → ~12-15 min per market. C is optional polish.

### 29.4 · Non-goals

- Do NOT change what data is fetched (same 500 tickers · same fields)
- Do NOT change R1/R2 or downstream engine logic
- Do NOT parallelize downstream engines (they're already fast · 7% of runtime)
- Do NOT change CI cadence · this is purely local-iteration ergonomics

### 29.5 · Acceptance criteria

```
1. Full USA run wall-clock ≤ 20 min                YES
2. Full India run wall-clock ≤ 20 min              YES
3. Data output byte-for-byte identical to serial baseline (deterministic)  YES
4. Zero yfinance rate-limit failures across 10 consecutive runs           YES
5. All 43 USA steps still SUCCESS                  YES
6. All existing regression tests pass              YES
```

### 29.6 · Estimated effort

~1 full day · Lever A + B combined. Lever C optional.

### 29.7 · Ordering

**Do Part 28 (Decision consistency) FIRST.** Correctness before speed.
No point in optimizing a pipeline that outputs contradictory decisions.

---

## Part 30 · Opportunity Registry + Daily NEW Discovery Engine (SHIPPED 2026-08-18)

**Added AND executed 2026-08-18** · same-day ship · operator directive
"AEGIS must stop treating today's recommendation as a new opportunity ·
it needs a persistent Opportunity Registry." Fixes root-cause behind
Zydus/ONGC/Hindunilvr NEW-forever + INDIGO NEW+CLOSED + 60-column
Portfolio bloat + no daily discovery diagnostic. Cross-references:
supersedes aspirational Part 19 (New Opportunities), populates Part 22
(Self Learning) input, satisfies Part 23 (Regression Tests) for the
opportunity + decision layer.

### 30.1 · The bug (operator's Aug 18 India workbook audit)

Concrete failures in `aegis_history_india(20260818-120216).xlsx`:

| Ticker | First rec | Aug 18 Portfolio state | Correct behaviour |
|---|---|---|---|
| ZYDUSLIFE | Aug 11 | still 🆕 NEW | NEW day 0 only · ACTIVE from day 2 |
| ONGC | Aug 12 | Recommended = Aug 17 (restamped) | Recommended immutable = Aug 12 |
| HINDUNILVR | Aug 12 | NEW on Aug 12·13·17 | NEW exactly once |
| INDIGO | Aug 18 (new) | NEW + immediately CLOSED · in active NEW section | REJECTED · dropped from Portfolio |
| NTPC / BATAINDIA / LICI / TATAPOWER | varies | EXIT decision · Lifecycle ACTIVE | EXIT → Lifecycle CLOSED same day |
| Portfolio | 60 columns · SKIP + ARTIFACT mixed | overwhelming | ~15 essentials only |

### 30.2 · Root cause

Row builder computed `first_seen` from workbook history OR fell back
to `asof` (today). No persistent per-opportunity lifecycle store, so
`Recommended` got restamped daily → `opp_age` flagged NEW every day.
Section-17 client-facing simplification never happened. Same-day
rejections had no dedicated status.

### 30.3 · Architectural fix · persistent Opportunity Registry

New module `backend/research/opportunity_registry.py` · append-only
JSONL at `reports/research/opportunity_registry.jsonl` · event-sourced
with load-time collapse (latest event per `opportunity_id` wins).

Schema per opportunity (12 fields):
- `opportunity_id` — deterministic hash: `{MKT}-{R}-{TICKER}-{YYYYMMDD}-{sig6}`
- `market` · `runner` · `ticker` (bare · no .NS/.BO)
- `created_date` · YYYY-MM-DD · **IMMUTABLE**
- `initial_signal` · `initial_rank` · `initial_score`
- `status` · ACTIVE | CLOSED | REJECTED (one-way transitions)
- `closed_date` · `closed_reason` · `last_seen_date` · `ts_utc`

Public API:
- `make_opportunity_id()` · deterministic
- `get_or_create()` · returns existing ACTIVE if any · else creates
  new with today's asof as created_date (re-entry case)
- `close()` · ACTIVE → CLOSED (idempotent · never reverses)
- `reject()` · ACTIVE → REJECTED (INDIGO same-day case)
- `touch()` · update last_seen_date without mutating status
- `lifecycle_state(opp, asof)` · NEW / ACTIVE / CLOSED / REJECTED
- `opportunity_age_days()` · today - created_date

### 30.4 · Constitutional invariants (enforced by tests)

- `created_date` never changes for an existing `opportunity_id`
- Status transitions strictly one-way (CLOSED cannot revert to ACTIVE)
- Re-entry after CLOSE creates NEW `opportunity_id` (LUPIN case)
- REJECTED same-day never resurrects as ACTIVE (INDIGO case)
- `opportunity_id` is a deterministic hash · idempotent

### 30.5 · Wiring into row builder (Wave 2)

`backend/delivery/telegram/detail_xlsx.py:_rec_to_row`:
- `first_seen` fallback consults Registry FIRST (via `get_or_create`)
- Workbook-history lookup is now the second-tier fallback (bootstrap)
- Registry's `created_date` becomes the row's `Recommended` value
- Downstream `opp_age` reads from Registry too via `_opportunity_status`

Result: Zydus/ONGC/Hindunilvr `Recommended` stays fixed at first-day
value forever · NEW fires exactly once.

### 30.6 · Portfolio 3-section layout (Wave 3 · Section 17)

Portfolio sheet rows grouped into 4 banner-separated sections:
```
🆕 NEW OPPORTUNITIES TODAY       (light blue banner)
📊 EXISTING POSITIONS            (light green banner)
⚠️  ACTION REQUIRED · EXITS       (light red banner)
⚪ CLOSED · REFERENCE ONLY       (gray banner)
```
Banner rows are merged full-width · 20 px tall · bold · colored fill.
Sections with zero rows skipped (no empty banner shown).

### 30.7 · Slim column view (Wave 3 · Section 15)

14 internal-audit columns HIDDEN in Excel (preserved in the XLSX
file · not deleted · Excel `Unhide` reveals them):

| Hidden | Reason |
|---|---|
| Price Trigger · Execution Window | Redundant with Stop Loss + Target |
| R1/R2 Consensus · Exit Date · Exit Price · Exit Reason | Closed-row-only |
| Action · Review · Inv Quality · Investability · Action Note | Internal |
| Alerts | Internal (Risk Controller reads) |
| Post-Exit Assessment · Decision Basis | Analytical / research |

Result: 18 columns visible (15 essentials + Sector + Cap + Days) ·
matches operator Section 15 recommended client-facing layout.

### 30.8 · INDIGO REJECTED-drop filter (Wave 3)

Cross-references Registry · drops any row whose (market, runner,
ticker, row.Recommended) matches a REJECTED opportunity. Same-day
rotation artifacts never appear in the active Portfolio. Printed
`[xlsx:MKT] INDIGO filter · dropped N REJECTED same-day rows` for CI
visibility.

### 30.9 · Section 26 · 11 zero-tolerance validation checks (Wave 4)

`backend/research/opportunity_validator.py:validate_rows()`. Runs
after Decision Resolver dedup · logs to
`reports/context/opportunity_violations.json` with per-check counts:

1. Duplicate (Position ID, Date, Runner) with contradictory Status
2. CLOSED → ACTIVE transition (same PID re-appears as buy-family)
3. EXIT + HOLD coexistence
4. EXIT + BUY coexistence
5. Binding risk signal in Alerts but Status not EXIT
6. SKIP in unified rows list (must be filtered upstream)

Non-fatal at write time · pipeline still ships · findings surface for
CI and next-run audit.

### 30.10 · Section 23 · Daily discovery diagnostic (Wave 5)

`backend/research/opportunity_validator.py:emit_daily_diagnostic()` ·
writes `reports/context/daily_opportunity_discovery.json`:

```json
{
  "asof": "2026-08-18",
  "counts": {
    "active_opportunities":   42,
    "created_today":           3,
    "new_actionable_today":    2,
    "rejected_today":          1,
    "reentries_today":         0,
    "closed_today":            1,
    "total_ever_active":      42,
    "total_ever_closed":      15,
    "total_ever_rejected":     3
  },
  "verdict": "2 new opportunity(ies) discovered · 0 re-entry",
  "new_opportunities": [ {...}, {...} ],
  "closed_today_details": [ {...} ]
}
```

If `new_actionable_today == 0` verdict is explicitly:
`"NO QUALIFIED NEW OPPORTUNITY TODAY"` · never manufactured.

### 30.11 · Regression test coverage

`backend/tests/test_opportunity_registry.py` · **11 tests · all pass**:
- id deterministic · id diverges across runner + market
- ZYDUSLIFE · NEW only on created_date · ACTIVE for days 2-7
- ONGC · created_date immutable across 6 daily reruns
- LUPIN · re-entry after CLOSE gets NEW id · original stays CLOSED
- INDIGO · same-day REJECTED · never returns as ACTIVE
- lifecycle_state variants (NEW/ACTIVE/CLOSED/REJECTED)
- opportunity_age_days math
- CLOSED cannot revert (constitutional invariant)
- bulk helpers (count_by_status · opportunities_created_on · active_opportunities)

### 30.12 · Do NOT touch

- R1/R2 model logic · weights · thresholds
- Sealed engines
- Portfolio construction algorithm
- Decision Resolver priority order (already Sprint K Part 28)

Part 30 is state-machine + presentation + validation only. Zero model
changes.

### 30.13 · Execution status

**SHIPPED 2026-08-18** across 5 commits on `gujja330/NexaQuant@main`:

| Commit | Wave |
|---|---|
| `0380fe4e` | Wave 1 · Opportunity Registry (module + 11 tests) |
| `3fb264e2` | Wave 2 · Registry wired into row builder + opp_status |
| `aa422853` | Wave 3 · 3-section layout + slim columns + INDIGO filter |
| `dd915ad5` | Waves 4+5 · validation gate + daily diagnostic |

Cross-references: closes operator directives from Aug 15 (22-section
Position Continuity) + Aug 17 (Section 17 acceptance validator) +
Aug 18 (this final architectural fix). Combined with Sprint K Part 28
(Risk→Decision Consistency) the full lifecycle chain is now:

```
R1 · R2 signals
   ↓
Opportunity Registry (Part 30 · this) · immutable per-idea lifecycle
   ↓
Decision Resolver (Part 28) · single authoritative Decision per (PID,Date)
   ↓
Portfolio 3-section output (Part 30 · this) · client-facing 15 columns
   ↓
Zero-tolerance validation (Part 30 · this) · Section 26 gate
   ↓
Daily discovery diagnostic (Part 30 · this)
```

---

## Post-Sprint K+ · 90-day validation window

Per operator directive: "The limiting factor won't be architecture · it
will be the quality of the underlying signals and the evidence collected
from live operation."

- Dec 2026 - Feb 2027: paper-trading only
- Collect: hit rate · Sharpe · rotation accuracy · calibration drift
- Compare: R1 vs R2 vs R3 on complete lifecycle metrics (not snapshots)
- Decide: canonical runner (or keep all 3) based on evidence · not intuition
- Post-Feb 2027: potential Australia expansion IF · and only IF · evidence supports

---

## Signed 2026-08-06

Sprint K+ is CONSTITUTIONALLY LOCKED. Any deviation from these 24 parts
requires operator explicit amendment.
