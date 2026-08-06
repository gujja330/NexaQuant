# AEGIS · Sprint H · Recommendation Continuity Engine (drafted · deferred)

**Signed:** 2026-08-06 · execute when operator says go
**Trigger:** Operator scored Recommendation Continuity 5.5/10 (2026-08-06)
· "the weakest area · the models are no longer the bottleneck"

---

## 1 · Problem statement (operator's words)

> "Runner 2 forgets yesterday. Yesterday LUPIN rank #1 · today TCS rank #1
> · the user asks 'what happened to LUPIN?' and the answer isn't
> immediately visible."

> "Runner 1 has the opposite problem · it remembers too much · the list
> barely changes · but it should communicate 'Holding 31 days · +7.2% ·
> still healthy · continue HOLD' instead of looking like a fresh
> recommendation every day."

## 2 · What Sprint H builds

### H-1 · Rich R1 rendering parity with R2 (SHIPPED today)
Already shipped 2026-08-06 in this session. R1 orphans now carry full
position_plan (buy_zone_low/high, stop, targets, horizon_days from
"2 months" parsing) + attribution.top_features from reason text + why
structure. Renders identical column layout as R2 in XLSX.

### H-2 · Telegram operator guide (SHIPPED today)
`backend/delivery/telegram/operator_guide.py` · appended to Monday XLSX
caption automatically. Covers: R1=core weekly · R2=satellite daily ·
70/30 allocation · what NOT to do · cadence.

### H-3 · "Where did it go?" bridge (DEFERRED)
When a ticker vanishes from R2's top-15 · Story column in the XLSX
should surface a bridge line explaining:
- If it rotated: "R2 rotated LUPIN → TCS · +12pp edge · Aug 05"
- If it degraded: "R2 dropped LUPIN (rank 1 → 18) · momentum faded"
- If it exited: "R2 EXIT LUPIN · risk_score jumped · Aug 04"

Requires: reading yesterday's XLSX rows + diffing with today's rank_history
to identify vanished tickers · appending synthetic ghost-rows with the
bridge narrative in Story column.

Estimated: 1 day.

### H-4 · Position age narrative for R1 (DEFERRED)
Every R1 row should show:
- `Day 31 of 60` (or `Day 31 · open-ended` for R1)
- `Return +7.2% since Aug 04`
- `Still healthy · continue HOLD`
- Health-band change if any (STRONG BUY → HOLD after 3 weeks)

Requires: position_store first_seen_date for R1 tickers (currently only
R2 tickers get tracked). Enhance position_store to accept R1 opens.

Estimated: 1 day.

### H-5 · Weekly Friday review report (DEFERRED)
Automated `reports/telegram/weekly_review_{YYYY-MM-DD}.md` sent every
Friday with:
- Winners this week (top 5 by P&L)
- Losers this week (bottom 5)
- Confidence-change leaderboard (biggest +/- in confidence)
- Rank movements (biggest ↑ and ↓)
- Sector rotation summary (which sectors gained/lost breadth)
- Regime shift narrative if macro flipped

Uses existing data (rank_history · monthly_rollups · sector_news_history)
· no new engine needed · pure aggregation + rendering.

Estimated: 1 day.

### H-6 · Ticker Timeline auto-attach (DEFERRED)
When operator taps a ticker in the XLSX · they should see its full
lifecycle · not build up context by scrolling. Ship a Sunday
`weekly_timelines_bundle.zip` with per-ticker Timeline MDs for every
currently-held position (uses existing `scripts/ticker_timeline.py`
looped over portfolio).

Estimated: 0.5 day.

## 3 · Sprint H total scope

- H-1 · SHIPPED (2026-08-06)
- H-2 · SHIPPED (2026-08-06)
- H-3, H-4, H-5, H-6 · deferred · total ~3.5 days
- Estimated ship date: window of 2026-09-15 to 2026-09-25 (after Runner 3
  Day-30 gate but before Day-90 CEO decision)

## 4 · Why deferred

Per CEO decision doc 2026-08-05 · we're in FREEZE until Runner 3 Day-30
gate (2026-09-09). Sprint H-3 through H-6 add new rendering behavior that
would confound the R3 vs R2 shadow comparison if landed mid-window.

H-1 and H-2 are UI-only fixes that don't affect R2/R3 decision logic ·
allowed under freeze as operator-experience improvements.

## 5 · Operator's overall scoring (baseline before Sprint H)

Architecture:              9.8/10
Recommendation Engine:     9.2/10
Portfolio Engine:          9.4/10
Telegram UX:               8.8/10
Recommendation Continuity: 5.5/10 ← Sprint H target

## 6 · Signed

CEO (AI): 2026-08-06 · execute H-3 through H-6 after Runner 3 Day-30
gate result determines whether to reallocate capacity.
