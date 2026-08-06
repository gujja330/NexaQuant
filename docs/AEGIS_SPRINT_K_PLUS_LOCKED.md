# AEGIS · Sprint K+ · Locked Production Spec

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

---

## Execution timeline (55 days)

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
| 2026-11-06 to 2026-11-10 | Parts 21-22 · Telemetry + Self-Learning feedback | daily telemetry log · calibration feedback |
| 2026-11-11 to 2026-11-15 | Part 23 · Full regression suite | all tests green |
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
