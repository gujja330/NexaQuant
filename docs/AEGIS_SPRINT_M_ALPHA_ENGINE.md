# AEGIS · Sprint M · Alpha Engine (Winner/Loss Control + Opportunity Refresh)

**Draft locked 2026-08-25 · execution TBD after CEO Phase-2 approval**
**Depends on: Sprint K+ (30 parts · complete) · Sprint L (locked · not yet exec)**
**Origin: CEO directive 2026-08-25 · "AEGIS — WINNER/LOSS CONTROL + OPPORTUNITY REFRESH"**

Sprint M is the "AEGIS becomes selective" sprint. The strategic re-focus
away from producing more recommendations toward capturing more RISK-
ADJUSTED EXPECTANCY per unit of operator attention.

CEO objective verbatim:
> "The ultimate KPI is not how many recommendations AEGIS produced.
> The ultimate KPI is: how much risk-adjusted positive expectancy did
> AEGIS create, and how much avoidable loss did it prevent?"

Prior sprint context:
- **Sprint K+** shipped the Registry + Investability + attribution
  substrate that Sprint M builds on
- **Sprint L** shipped/locks the Distillation + Capital Preservation
  engines that Sprint M's findings feed into (via Research Ticket path,
  never automatic)
- **Constitutional invariant preserved**: research NEVER mutates R1/R2
  without walk-forward validation + explicit CEO approval

Sprint M sits on top of both · consumes their outputs · produces the
CEO-facing selective-alpha engine.

---

## Sprint M Scope Summary (22 Parts)

| Part | Title | Phase | Effort | Depends on |
|---|---|---|---|---|
| M1 | Winner Genome | 3 | 6h | Registry · Investability · Feature Store |
| M2 | Loss Genome (14-cat) | 3 | 6h | Registry · loss_attribution_v2 |
| M3 | Winner-vs-Loser Comparison Matrix | 2 | 4h | M1 · M2 |
| M4 | Multi-Dim Cap Analysis | 4 | 5h | M1 · M2 · sector_cache |
| M5 | Small-Cap Emerging Leader Engine | 3 | 8h | Fundamentals data · governance data |
| M6 | Real NEW vs Recycled Engine | 3 | 4h | Registry state machine |
| M7 | Daily Opportunity Refresh | 3 | 3h | M6 |
| M8 | Ranking Effectiveness Study | 2 | 4h | Walk-forward · rank_history |
| M9 | R1 vs R2 Dimensional Deep-Dive | 4 | 3h | M3 · rank_history |
| M10 | Entry Timing Engine (Quality + Timing) | 2 | 6h | Investability · technicals |
| M11 | Multi-Signal Loss Prevention Veto | 5 | 8h | M2 · context adapters · CEO approval |
| M12 | Adaptive Stop-Loss (regime + sector) | 5 | 10h | Sprint L data · CEO approval |
| M13 | Exit Quality Tracker | 2 | 4h | Registry · parquet |
| M14 | Profit Preservation State Machine | 5 | 8h | M13 · CEO approval |
| M15 | Active vs Exit P&L discipline audit | 6 | 2h | Sender code audit |
| M16 | Immutable Position ID (audit + enforce) | 6 | 3h | Registry (already has) |
| M17 | Data Quality Gates (pre-portfolio) | 6 | 4h | price_integrity_guard extend |
| M18 | Portfolio Presentation focus | 6 | 2h | Existing hide-column config |
| M19 | Daily CEO Summary (5-section) | 2 | 3h | All Phase 2 outputs |
| M20 | Research Ticket System | 4 | 4h | Docs + workflow spec |
| M21 | Statistical Discipline (N-thresholds) | 2 | 2h | Governance layer |
| M22 | Consolidated Final Report (25 metrics) | 2 | 3h | Aggregator of all engines |

**Total effort estimate**: ~102 hours (12-15 focused engineering sessions).
**Recommended execution: 4-6 weeks calendar** at 2-3 sessions/week.

---

## Phase Plan

### Phase 2 · Foundation (Sessions 1-6 · ships in first 2 weeks)

**Goal**: give the operator immediate CEO-grade visibility from what
already exists · minimize risk · no decision-path changes.

Parts:
- **M22 · Consolidated Final Report** ← FIRST · leverages every engine already running
- **M3 · Winner-vs-Loser Comparison Matrix** · one JSON, one markdown
- **M13 · Exit Quality Tracker** · answers "are we destroying alpha?"
- **M10 · Entry Timing Engine** · CEO explicit "most important improvement"
- **M21 · Statistical Discipline** · governance-level safety net
- **M19 · Daily CEO Summary** · 5-section daily digest → Telegram caption

**Exit criteria for Phase 2**:
- All 6 modules produce JSON + markdown outputs
- Each has ≥ 4 pytest tests
- Consolidated report renders < 30 seconds on real data
- Operator reviews · approves Phase 3 kickoff

### Phase 3 · Advanced Data Engines (Sessions 7-12 · weeks 3-4)

Depends on Phase 2 · requires richer data sources for some parts.

Parts:
- **M1 · Winner Genome** · 30+ field structured profile per winner
- **M2 · Loss Genome** · 14-category primary + secondary attribution
- **M5 · Small-Cap Emerging Leader** · 6 quality dimensions
- **M6 · Real NEW vs Recycled** · Registry state machine enforcement
- **M7 · Daily Opportunity Refresh** · state-aware daily digest
- **M8 · Ranking Effectiveness Study** · per-rank walk-forward return

**Exit criteria for Phase 3**:
- Winner Genome captures at least 25 fields per winner
- Loss Genome primary-cause attribution ≥ 80% coverage (not "UNKNOWN")
- Small-cap engine surfaces ≥ 3 EMERGING LEADER candidates per week with
  ≥ 4 of 6 quality dimensions positive
- Real-NEW definition eliminates recycled recommendations (measurable
  drop in same-ticker "NEW" reappearances)

### Phase 4 · Governance + Multi-Dim Analysis (Sessions 13-15 · week 5)

Parts:
- **M20 · Research Ticket System** · formal ticket file structure
- **M4 · Multi-Dim Cap Analysis** · cap × sector × runner × regime
- **M9 · R1 vs R2 Dimensional Deep-Dive** · segment-level attribution

**Exit criteria for Phase 4**:
- First 10 Research Tickets filed (with N-thresholds enforced)
- Cap × Sector × Runner × Regime matrix populated with real data
- R1 vs R2 dominance patterns identified per segment

### Phase 5 · Decision-Path Changes (Sessions 16-20 · week 6 · CEO approval gated)

**Constitutional gate**: Each of these MUST have a Research Ticket
(from Phase 4) + walk-forward validation + explicit CEO approval BEFORE
touching production.

Parts:
- **M11 · Multi-Signal Loss Prevention Veto** · multi-signal entry veto
- **M12 · Adaptive Stop-Loss** · sector + regime + volatility conditional
- **M14 · Profit Preservation State Machine** · HOLD/PROTECT/TRAIL/TP/EXIT

**Exit criteria for Phase 5**:
- Every change lands via Research Ticket → walk-forward → CEO sign-off
- Guardrails: production-side change gated behind config flag defaulting
  to OFF · flipped ON after paper period

### Phase 6 · Audit + Polish (Sessions 21-23 · week 6-7)

Parts:
- **M15 · Active vs Exit P&L audit**
- **M16 · Position ID enforcement audit**
- **M17 · Data Quality Gates** (extend price_integrity_guard)
- **M18 · Portfolio Presentation focus** (verify column set)

**Exit criteria for Phase 6**:
- Zero mixed Active/Exit P&L rows
- Zero re-used Position IDs across re-entries
- ≤ 17 visible columns in Portfolio (per Part 18)

---

## Part Specifications

### M1 · Winner Genome
- Per closed winner, capture:
  Runner · Rank · Rank pct · Model score · Confidence · Sector ·
  Industry · Market · Cap · Investability · Market regime · Sector
  regime · Sector breadth · Rel sector strength · Market breadth ·
  Global ctx · News sentiment · News severity · Macro risk ·
  Technical trend · Momentum · RSI · Distance from MA20/50/200 ·
  Volatility · Liquidity · Valuation · Expected alpha · Context
  drag · Risk score · Entry-zone quality · Stop distance · Target
  distance · Portfolio exposure · Correlation exposure
- Return trajectory: 1D · 3D · 5D · 10D · 20D · 30D · Max gain ·
  Max drawdown · Exit P&L · Days held · Exit reason
- Store as append-only Parquet ledger
  `reports/research/winner_genome_{market}.parquet`
- Emit summary JSON with per-segment metrics

### M2 · Loss Genome (14-category)
- Every loss gets ONE primary + optional secondary from:
  A · BAD STOCK
  B · BAD TIMING
  C · SECTOR DRAG
  D · MARKET/MACRO SHOCK
  E · NEWS SHOCK
  F · EXCESSIVE VOLATILITY
  G · STOP TOO TIGHT
  H · STOP TOO LOOSE
  I · TIME STOP FAILURE
  J · THESIS FAILURE
  K · QUALITY FALSE POSITIVE
  L · RANKING FAILURE
  M · EXIT FAILURE
  N · ROTATION FAILURE
- Classifier is deterministic ladder (14 signal checks)
- Extends `loss_attribution_v2` (6-cat) · v3 becomes 14-cat
- Same-day A/B secondary allowed
  (e.g., LUPIN · Primary: BAD TIMING · Secondary: HEALTHCARE WEAKNESS)

### M3 · Winner-vs-Loser Comparison Matrix
- 15 dimensions: R1/R2 · rank bucket · confidence bucket · model score
  bucket · sector · cap · investability · market regime · sector regime
  · sector breadth · technical trend · momentum · volatility · liquidity
  · news · macro · context drag · expected alpha · entry-zone
- Per cell: N · win% · avg return · median return · profit factor ·
  expectancy · avg drawdown · statistical confidence
- **Enforcement**: optimize for expectancy, not win rate alone
- Report: `reports/research/win_loss_matrix_{market}.json` + `.md`

### M4 · Multi-Dim Cap Analysis
- LARGE / MID / SMALL
- Cap × Sector
- Cap × Runner
- Cap × Runner × Sector
- Cap × Investability
- Cap × Market Regime
- Report: `reports/research/cap_analysis_{market}.json`
- Success = identifies segments with best risk-adjusted expectancy

### M5 · Small-Cap Emerging Leader Engine
- 6 quality dimensions · each with 6-9 sub-checks:
  1. FUNDAMENTAL QUALITY · revenue growth · earnings growth · ROE ·
     ROCE · FCF · debt · interest coverage · margin trend · consistency
  2. TECHNICAL QUALITY · above 50/200 DMA · improving trend · RS ·
     volume confirm · accumulation · momentum persistence · breakout
  3. GOVERNANCE QUALITY · promoter holding · pledging · auditor
     stability · regulatory · related-party · restatements
  4. MARKET/SECTOR QUALITY · sector strength · breadth · rotation ·
     regime · institutional flow
  5. LIQUIDITY QUALITY · turnover · traded value · spread · abnormal-vol
  6. RISK QUALITY · volatility · drawdown · beta · gap risk
- EMERGING LEADER only if ≥ 4/6 dimensions positive
- Emit `reports/research/emerging_leader_{market}.json`

### M6 · Real NEW vs Recycled Engine
- A stock is NEW only if:
  - not already active OR
  - previous thesis ended + new thesis formed OR
  - previously WATCH/IGNORED and crossed opportunity threshold
- Registry state machine: NEW → ACTIVE → HOLD → PROTECT → REVIEW → EXIT → CLOSED
- Re-entry gets new Position ID (per M16)
- Rank change alone doesn't trigger NEW

### M7 · Daily Opportunity Refresh
- Portfolio produces two internal buckets:
  - TOP NEW OPPORTUNITIES
  - TOP EXISTING POSITIONS
- SKIP stocks NEVER appear in investor-facing portfolio
- Opportunity States: NEW · ACTIVE · HOLD · PROTECT · REVIEW · EXIT · CLOSED
- One sheet UI (per current locked design) · internal state machine

### M8 · Ranking Effectiveness Study
- For each Rank 1-10, measure forward returns at 1D/3D/5D/10D/20D/30D
- Per rank: win rate · expectancy · profit factor · max DD ·
  avg gain · avg loss
- Ship: `reports/research/ranking_effectiveness_{market}.json`
- If Rank 1 < Rank 5 · file Research Ticket to investigate

### M9 · R1 vs R2 Dimensional Deep-Dive
- R1 expectancy · R2 expectancy · overall
- R1 × sector · R2 × sector
- R1 × cap · R2 × cap
- R1 × regime · R2 × regime
- R1 × investability · R2 × investability
- Identify which feature combinations drive R1/R2 divergence
- Ship: `reports/research/r1_vs_r2_{market}.json`

### M10 · Entry Timing Engine (CEO priority)
- Separate Investability Score from Timing Score
- Timing Score inputs:
  - Distance from MA20 (in ATR units)
  - RSI (14) · 3-day trend
  - Volume vs 20d average (confirmation)
  - Sector momentum in same window
  - Market regime (bull-favor bull entries)
  - Breakout quality (base > 20d, breakout > 1σ)
- Decision matrix:
  Quality HIGH + Timing HIGH → BUY
  Quality HIGH + Timing LOW  → WATCH (wait for setup)
  Quality LOW  + Timing HIGH → SKIP (chasing garbage)
  Quality LOW  + Timing LOW  → IGNORE
- Ship: `backend/decision/entry_timing.py` + tests

### M11 · Multi-Signal Loss Prevention Veto
- Before BUY, check 13 signals:
  Investability · Timing · Sector regime · Market regime · News risk
  · Macro event · Volatility · Liquidity · Drawdown risk · Correlation
  · Entry zone · Stop distance · Expected R/R
- If ≥ N (default 4) signals negative → REDUCE / WAIT / REJECT
- Config-driven veto threshold
- NEVER auto-applied · Research Ticket → walk-forward → CEO sign-off

### M12 · Adaptive Stop-Loss
- Study empirically per segment:
  Sector · Cap · Volatility · Runner · Hold period · Market regime
- Classify each stop-hit: TIGHT STOP vs THESIS FAILURE (via forward
  recovery test)
- Emit sector-specific stop recommendation
- Same governance: Research Ticket → walk-forward → CEO sign-off

### M13 · Exit Quality Tracker
- For every EXIT, capture 5D/10D/20D post-exit return
- Classify:
  GOOD EXIT       · post-exit return within ±2% of exit price
  PREMATURE EXIT  · post-exit return > +5% (we left money on table)
  LATE EXIT       · post-exit return < -5% (we should have exited earlier)
  CORRECT STOP    · post-exit downside continued
  CORRECT TP      · post-exit reversed
- Emit `reports/research/exit_quality_{market}.json`
- Aggregate: what % of our exits are PREMATURE?
  (answer to "are we destroying alpha by exiting winners too early?")

### M14 · Profit Preservation State Machine
- Per active profitable position:
  Current P&L · Max Gain · Current DD from Max · Distance to stop ·
  Distance to target · Trend health · Sector health · Market health
- States: HOLD · PROTECT · TRAIL · TAKE PROFIT · EXIT
- Never exit merely because up · protect when evidence degrades
- Let winners run when evidence remains strong

### M15 · Active vs Exit P&L discipline audit
- Sender code audit:
  Active P&L = (Current / Entry - 1) × 100 (ONLY for OPEN positions)
  Exit P&L   = (Exit / Entry - 1) × 100     (ONLY for CLOSED positions)
- Never compute Active P&L for closed positions with today's market price
- Never show Exit P&L for open positions

### M16 · Immutable Position ID (audit)
- Registry already assigns opportunity_id (per Sprint K+ Part 30)
- Audit: verify no re-used IDs across re-entries
- Enforce: re-entry emits new Position ID
  (e.g., IND-R2-20260825-000143 → IND-R2-20260830-000178)
- Immutable through NEW → ACTIVE → HOLD → PROTECT → REVIEW → EXIT → CLOSED

### M17 · Data Quality Gates (pre-portfolio)
- Extend `price_integrity_guard` with:
  CLOSED + current P&L only → INVALID
  ACTIVE + exit P&L → INVALID
  NEW + old recommendation date → INVESTIGATE
  NEW + existing active Position ID → INVALID
  Today Move without valid prior close → UNAVAILABLE (not fabricated)
- Add to delivery_gate BLOCKING codes when severity FAIL

### M18 · Portfolio Presentation focus
- Investor-facing columns (17 max):
  Date · Runner · Ticker · Company · Position State · Decision · Rank
  · Confidence · Entry Price · Current Price · Active P&L% · Exit P&L%
  · Stop · Target · Sector · Cap · Opportunity State · Why
- Verify current hide-column config matches this list
- Everything else moves to research/diagnostic files

### M19 · Daily CEO Summary (5-section)
- NEW OPPORTUNITIES · top 3-5
- EXISTING POSITIONS · top changes only (not full list)
- RISK ALERTS · top 3
- LOSSES · what went wrong (last day)
- WINNERS · what worked
- ROTATIONS · what should replace what
- LEARNING · one-liner from Distillation Engine (Sprint L)
- Format: markdown + Telegram caption
- Ship: `backend/delivery/ceo_daily_summary.py`

### M20 · Research Ticket System
- File-based workflow: `reports/research/tickets/RT-{YYYY}-{NNN}.md`
- Required fields:
  Finding · Evidence (N, expectancy, PF) · Hypothesis · Required
  validation · Status (OPEN / VALIDATING / APPROVED / REJECTED)
- Never auto-apply · CEO approval workflow
- Top-10 open tickets shown in daily CEO summary (M19)

### M21 · Statistical Discipline
- N-threshold enforcement on every research output:
  N < 20  → observation only (no ticket)
  20-49   → directional evidence (ticket allowed)
  50-99   → research candidate
  100+    → production validation candidate
- Never allow production change on N < 100
- Enforce via research/statistical_guard.py

### M22 · Consolidated Final Report (25 metrics)
- Single artifact aggregating all engines' outputs:
  1. Top winning patterns          14. Exit-quality findings
  2. Top losing patterns           15. Timing failures
  3. Best sectors                  16. Ranking effectiveness
  4. Worst sectors                 17. New-opportunity refresh rate
  5. Best cap segments             18. Stale recommendation rate
  6. Worst cap segments            19. Re-entry rate
  7. Best R1 combinations          20. Profit factor
  8. Best R2 combinations          21. Expectancy
  9. Best sector × cap combos      22. Max drawdown
  10. Best regime combos           23. Win rate
  11. Small-cap emerging leaders   24. Average winner
  12. Worst recurring losses       25. Average loser
  13. Stop-loss findings
- Plus **TOP 10 RESEARCH TICKETS** ranked by expected impact
- Emitted as `reports/research/aegis_alpha_report_{market}.md` + `.json`
- Runs at end of every send · appended to Telegram caption if changes

---

## Success Metrics (Sprint M complete)

Sprint M is complete when the operator can answer these in ≤ 5 minutes
from the CEO Summary + Consolidated Report:

1. **"Where is our alpha coming from?"** → M3 comparison matrix +
   M22 report answer.
2. **"What are we systematically missing?"** → `win_discovery` capture
   rate + M4 cap-sector gap.
3. **"Are we exiting winners too early?"** → M13 exit-quality PREMATURE %.
4. **"Which small-caps are emerging leaders TODAY?"** → M5 output.
5. **"Should I trust Rank 1 over Rank 5?"** → M8 forward-return study.
6. **"How selective have we become?"** → M6 real-NEW count vs recycled.

## Non-Goals (out of scope)

- Any change to R1/R2 model architecture (that's Sprint L Distillation
  Engine · always via Research Ticket path)
- Any auto-executed change to production stops / positions (M11, M12,
  M14 all gated on CEO approval per Part 20)
- Any new AI/ML component beyond what already exists (per operator
  memory `feedback_no_more_ai_agents`)

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Scope creep (22 parts is big) | Phase gating · CEO reviews after each phase |
| Data insufficient for small-cap fundamentals (M5) | Start with what we have, mark PENDING for missing sources |
| Adaptive stops (M12) needs N ≥ 500 per sector | Statistical Discipline gate (M21) blocks it until N is enough |
| Multi-signal veto (M11) could reject good picks | Config-driven threshold · shadow mode before enforcing |
| M17 data quality gates could block delivery | Start as WARN · promote to BLOCK after observation period |

## Governance Summary

- Every Part that touches decision path (M11, M12, M14) MUST:
  1. File Research Ticket (M20)
  2. Pass N-threshold (M21 · usually 100+ closed positions per segment)
  3. Pass walk-forward validation
  4. Get explicit CEO written approval
  5. Ship behind config flag defaulted OFF
  6. Get flipped ON only after paper-tracking period
- Every Part that produces research output (M1-M9, M13, M22) is
  READ-ONLY · never mutates R1/R2 · always safe to iterate on

---

## Next Steps (post approval)

1. **CEO reviews this document** · confirms Phase 2 kickoff
2. **Phase 2 execution** starts with M22 (Consolidated Report) since it
   aggregates everything already running · immediate CEO value
3. Weekly Phase-2 status update in the daily CEO Summary (M19 will exist
   from Phase 2 · self-reporting)
4. Phase 3 gate: after Phase 2 exit criteria met · CEO signs off

---

## Amendment Log

- **v1.0 · 2026-08-25 · draft locked**: initial 22-part specification
  from CEO directive "AEGIS — WINNER/LOSS CONTROL + OPPORTUNITY REFRESH"
  · pending CEO review for Phase 2 kickoff.

