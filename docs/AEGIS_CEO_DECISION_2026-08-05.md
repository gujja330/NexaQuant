# AEGIS · CEO Decision · 90-Day Roadmap Lock

**Signed into force:** 2026-08-05
**Author:** CEO (operator + AI)
**Governance:** Article IX + Article X · this decision is BINDING
**Prior authorities superseded:** none · complements existing frozen roadmap

---

## 1 · Executive Summary

After reviewing the operator's proposed 10-item roadmap against what has
already shipped in AEGIS, this decision:

1. **Confirms 7 of 10 items are already shipped** (R006 Phases 1-9 + monthly
   rollups + Runner 3 shadow). No re-build of those.
2. **Adopts 3 genuinely new items** into a bounded 90-day sprint plan:
   Recommendation Health Score · Adaptive Weight Proposals · rendered
   Recommendation Intelligence narrative.
3. **Signs the freeze rule**: after these 3 additions AND Runner 3 Day-90
   evaluation, ALL major feature expansion HALTS until the 3-runner
   evaluation produces evidence-backed direction.

The strategic principle: *"By the end of the evaluation period, you'll have
enough evidence to decide whether to retire, merge, or promote a runner.
That process will be based on measured performance rather than intuition."*

---

## 2 · What's Already Shipped (do not re-build)

| Operator's priority | Existing implementation |
|---|---|
| Recommendation Continuity (lifecycle · rank/conf history · price history · rotation history) | R006 Phases 1-8 · `portfolio_ledger.jsonl` · `rank_history.jsonl` · `rotation_ledger.jsonl` · `position_store` |
| Profit Protection Engine (6 triggers · rapid appreciation, rank collapse, better replacement, sector leadership, risk escalation, regime buffer) | R006 Phase 9 · `backend/portfolio/profit_protection.py` |
| Monthly Learning (Confidence Calibration · Feature Attribution · Rotation Accuracy) | `backend/research/monthly_rollups/` · runs daily |
| Runner 3 shadow + 3-runner comparison | `backend/recommendation/runner3/` · `RL-Runner3` ticket |
| Opportunity Cost (partially · rotation_intelligence + hysteresis min-edge) | `backend/portfolio/rotation_hysteresis.py` |
| Research Memory (partially · daily archives + ledgers) | `reports/recommendations_history/` + ledgers |
| Recommendation Intelligence data (evolution fields · days_recommended · momentum direction) | R2 payload `evolution.*` |

## 3 · Genuinely New Work (the 3+2 · bounded sprint · 60 days)

### Sprint A · Recommendation Health Score (2 weeks)

Composite 0-100 score per active recommendation. Weighted combination of:
- Trend signal (from existing tech features)
- Momentum (from R2 attribution)
- Quality (from R2 attribution)
- Earnings event risk (from Runner 3 free-features · reuse)
- Risk score (from existing risk_capital_v2)
- Sector strength (from sector_rotation)
- Liquidity (from bar volume · new tiny calc)

Bands:
- 90-100 → STRONG BUY
- 75-90 → HOLD
- 60-75 → WATCH
- 45-60 → REVIEW
- <45 → EXIT CANDIDATE

**Deliverable:** `backend/portfolio/health_score.py` · new XLSX column
`Health Score` · fires alerts when band changes.

### Sprint B · Adaptive Weight Proposals (2 weeks)

Feature Attribution rollup already computes per-model edge. Missing:
propose new ensemble weights operator can review + approve.

**Deliverable:** `configs/proposed_ensemble_weights.json` auto-updated
monthly · diff-viewer script `scripts/review_proposed_weights.py`
showing current vs proposed with justification. **Never auto-applies**
(operator approves manually).

### Sprint C · Recommendation Intelligence Narrative (1 week)

Every rec in XLSX gets a new `Story` column with compact narrative:
> `Rank ↑ 5→1 · Conf +7% · Momentum ↑ · sector leader · 34d left · HOLD`

Reuses existing rank_history + evolution fields · pure rendering work.

**Deliverable:** new `Story` column in XLSX · extends detail_xlsx.py.

### Sprint D · Per-Ticker Timeline View (1 week)

Aggregates portfolio_ledger + rank_history events into one narrative per
ticker · showing OPEN → HOLD → ROTATE_OUT/EXIT_* sequence with prices
and P&L.

**Deliverable:** `scripts/ticker_timeline.py --ticker TCS` · optional
per-ticker MD attachment on operator request.

### Sprint E · Missing Rollup Slices (1 week)

Existing 3 rollups grow by 3 additional slice cuts:
- Sector performance rollup (slice by sector)
- Regime performance rollup (slice by macro_regime)
- Per-model win rate rollup (deeper than current attribution share)

**Deliverable:** 3 new report files under `reports/research/monthly/`.

**Total: 7 weeks of engineering. Rounded to 60 days with buffer.**

## 4 · Sprint Schedule

| Weeks | Sprint | Deliverable | Blocker |
|---|---|---|---|
| 1-2 | A · Health Score | New XLSX column · alerts on band change | None |
| 3-4 | B · Adaptive Weight Proposals | Proposed weights file · review script | Rollups need ~30 days data |
| 5   | C · Story column | Compact narrative in XLSX | None |
| 6   | D · Timeline view | Per-ticker replay MD | None |
| 7   | E · Rollup slices | Sector/regime/model reports | Same as B |
| 8-13 | **FREEZE** | Runner 3 accumulates shadow data · Day-30 gate fires ~Day 35 | Runner 3 Tier 1 evaluation |

## 5 · The Freeze Rule (BINDING · Article X)

After Sprint E completes (~Day 60), **no new feature work** may begin on
AEGIS until:

1. **Runner 3 Day-30 gate fires** (~Day 35 from 2026-08-05 = 2026-09-09)
   with PASS/FAIL/DEFERRED verdict
2. **Runner 3 Day-90 evaluation** (2026-11-03) produces one of the 4 CEO
   decisions: A) promote R3, B) keep all 3, C) retire R3, D) merge into v4
3. **The Day-90 decision is DOCUMENTED** and signed as a follow-up
   decision doc

Any proposal for new features during the freeze window must cite an
evidence trigger from the monthly rollups OR a Day-30 gate finding. No
speculative additions.

## 6 · What is EXPLICITLY DEFERRED (indefinitely · needs evidence trigger)

- Deep learning models (LSTM · Transformer) — Runner 3 Tier 3 · needs
  Tier 1 evidence they'd fill a gap
- ESG ratings — flagged "exploratory" in Runner 3 plan · no operator ask
- Paid news sentiment (RavenPack) — Tier 3 · no current evidence gap
- Tick / orderbook data — R004 dependency · joint decision when R004 clears
- Runner 4 or beyond — no · finish evaluating R1/R2/R3 first
- Any new engine · module · or subsystem not listed in Sprints A-E

## 7 · What Continues in Parallel (no new features · just operations)

- Daily CI runs · India + USA
- XLSX delivery (Telegram · no compact message · per operator directive)
- Monthly rollups (auto-updated · already in orchestrator)
- Runner 3 shadow accumulation (per RL-Runner3 plan)
- Bug fixes as they arise (operator-flagged issues get priority · not
  new features)
- Data ingestion health monitoring (existing pipeline safety guards)

## 8 · Success Criteria for This 90-Day Window

At the end of the window, we must be able to answer with evidence:

- Which of the 11 ensemble models earn their weight (Feature Attribution)?
- Is confidence calibration drifting (Calibration rollup)?
- Are rotations delivering their promised alpha (Rotation Accuracy)?
- Which runner (R1 · R2 · R3) has the best risk-adjusted return over 60-90 days?
- Which sectors and regimes are the ensemble strong vs weak in?
- Does the Health Score correlate with actual outcome?
- Do operator-approved weight changes (from Sprint B proposals) improve
  the next month's rollups?

Any question we cannot answer at Day 90 with evidence is a gap in this
plan · we fix in the next window.

## 9 · What Would Cause This Decision to Be Amended

Only three things:

1. **Evidence trigger from a rollup** — e.g., a model's edge collapses to
   worse than −10pp for two consecutive months → warrants urgent action
2. **Runner 3 Day-30 gate FAIL** — reallocate freed Sprint B-E capacity
   to closing whatever gap the failure identified
3. **Operator-signed override** — explicit `--force` on this decision doc
   with justification

Otherwise: the plan holds for 90 days as signed.

---

## 10 · Signed

**CEO (operator):** approved 2026-08-05
**CEO (AI):** signed 2026-08-05 · will honor the freeze rule
**Governance:** Article X (Evidence-First Promotion)
**Next scheduled review:** 2026-09-09 (Runner 3 Day-30 gate)
**Final review:** 2026-11-03 (Runner 3 Day-90 CEO decision)
