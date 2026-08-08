# AEGIS · Sprint K+ · Locked Production Spec

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
