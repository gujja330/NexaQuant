# AEGIS Phase 3 · Master Roadmap · ARCHITECTURE FROZEN
### Trade Lifecycle Intelligence + Operator Intelligence Platform
### 🔒 FROZEN 2026-07-24 · Supersedes docs/AEGIS_PHASE3_ROADMAP.md

> **Architecture freeze:** No more engines beyond what's listed below. Remaining work is **implementation quality, validation, integration** — not architecture expansion. Any request to add a Phase 3 engine after this date requires explicit operator override in writing.

**Operator directive:** The core investment architecture is considered LOCKED. Focus of future development is NOT adding more prediction engines or AI agents, but transforming existing intelligence into a continuously improving operator experience driven by historical evidence. All future improvements must be evidence-backed through Historical Replay, Walk-Forward Validation, Research Governance, and Learning.

---

## The One Insight (why this supersedes the prior 8-module roadmap)

> Everything after Recommendation is answering ONE question: **What should the operator do today?**
>
> Holding updates · target progress · exit decisions · reversal detection · re-entry · notifications · dashboard · historical tracking — all facets of the same workflow. They must never live in separate engines with their own recommendation streams.

The prior Phase 3 spec (2026-07-21 · 8 discrete modules: Memory · Events · Graph · Explainability · Scenarios · Strategy Lab · Optimizer · Dashboard) would have fragmented lifecycle logic across multiple engines. This revision consolidates them into two integrated layers:

```
Recommendation Engine
     ↓
Trade Lifecycle Intelligence Engine      ← ONE engine, all lifecycle facets
     ↓
Operator Intelligence Layer              ← ONE surface, all consumer-facing views
     ↓
Telegram · Dashboard · Learning          ← single voice
```

---

## Locked Pipeline (authoritative — do not reorder)

```
Canonical Data Layer
     ↓
Market Intelligence
     ↓
Macro & Intermarket Intelligence
     ↓
Feature Store
     ↓
Feature Intelligence
     ↓
Model Factory
     ↓
Recommendation Engine  (Runner 1 legacy + Runner 2 Rec v3 — kept as sources)
     ↓
Risk Engine
     ↓
Portfolio Engine
     ↓
Execution Simulator
     ↓
──────── Phase 3 begins here ────────
Trade State Engine  ⭐                (TWO state machines: RECOMMENDATION_STATE + POSITION_STATE
                                       — dumb data only, no calculations)
     ↓
Trade Lifecycle Intelligence Engine   (analytics only: probabilities, expected exits, re-entry,
                                       lifecycle scores — never touches state, never renders)
     ↓
Recommendation Drift Intelligence     (monthly · was BUY, would model say BUY today? why diverge?)
     ↓
Recommendation Lifecycle Manager      (THIN RENDERER: composes State + Lifecycle + Risk +
                                       Portfolio + Macro → JSON. Never calculates.)
     ↓
Operator Intelligence Layer           (ONE authoritative surface + PRIORITIZATION buckets:
                                       Immediate Action / Review Today / Healthy / Watchlist)
     ↓
Portfolio Decision Intelligence       (Highest Conviction · Highest Risk · Most Overvalued ·
                                       Best Re-entry · Most Urgent Exit · Sector Concentration ·
                                       Cash Allocation · Portfolio Health)
     ↓
Telegram + Dashboard + Operator Daily Report + Learning
     ↓
Research Factory → Walk-Forward → Promotion → Production  (continuous self-improvement)
```

**Strict layer responsibilities (learned from 2026-07-24 review):**

| Layer | Does | Does NOT |
|---|---|---|
| Trade State Engine | current state · prices · holding day · highest / lowest · transitions | intelligence · probabilities · confidence · recommendations |
| Trade Lifecycle Intelligence | probabilities · expected exit · re-entry probability · lifecycle scores | render UI · compose messages · touch state |
| Recommendation Drift Intelligence | monthly rec vs current-model vs outcome comparisons | daily updates · state changes · UI |
| Recommendation Lifecycle Manager | THIN RENDERER — compose upstream outputs into unified JSON | calculate anything · invent new metrics |
| Operator Intelligence Layer | prioritize into buckets · single-voice notification | recompute lifecycle · duplicate rec logic |
| Portfolio Decision Intelligence | portfolio-level buy/increase/reduce/exit/hedge/wait/average/rebalance decisions | per-position lifecycle (that's above) |

Existing supporting engines (Replay Framework · Walk Forward · Persistence · Factor Library · Research Factory · Institutional Governance) remain, feeding into every Phase 3 layer where relevant.

---

## HARD RULE · Dual-Market Parallel Development (added 2026-07-24)

> **Every Phase 3 sprint must be implemented, tested, replayed, and benchmarked for BOTH India and USA in parallel. A sprint is only complete when both markets are supported and a global comparison artifact is produced.**

This is now a permanent architectural rule, not a preference. Reasons:
1. Cross-market learning is a first-class deliverable — do certain strategies / factors / lifecycle behaviors work better in one market vs the other?
2. Parallel dev prevents India-first-USA-later drift (features exist for one market, not the other, confusing operator and downstream engines).
3. A sprint that "works on India but not USA" is a half-shipped sprint — it doesn't count.

### Sprint Structure Template (every Phase 3 sprint follows this)

```
Shared Engine (backend/<engine>/)
        │
        ├── India Adapter (india/<engine>/run.py)     → reports/<engine>.json + parquets
        │
        └── USA Adapter (usa/research/<engine>/run.py) → usa/reports/<engine>.json + parquets
                                                                    │
                                                                    ↓
                                              Cross-Market Comparison
                                              (reports/global/<engine>_comparison.json)
```

### Directory Layout for Outputs

Existing (already dual-market · preserve):
```
reports/<engine>.<ext>            ← India per-engine outputs
usa/reports/<engine>.<ext>        ← USA per-engine outputs
```

New (added for Phase 3):
```
reports/global/<engine>_comparison.json    ← cross-market side-by-side + delta metrics
```

Do NOT move existing `reports/` / `usa/reports/` — that would break every daily-pipeline commit + dozens of consumers. Additive only.

### Acceptance Criteria (every sprint MUST hit ALL of these)

- [ ] Shared engine complete (`backend/<engine>/`)
- [ ] India adapter complete (`india/<engine>/run.py`)
- [ ] USA adapter complete (`usa/research/<engine>/run.py`)
- [ ] India tests pass
- [ ] USA tests pass
- [ ] Replay works on India (where applicable)
- [ ] Replay works on USA (where applicable)
- [ ] Walk-Forward works on India (where applicable)
- [ ] Walk-Forward works on USA (where applicable)
- [ ] `reports/global/<engine>_comparison.json` generated
- [ ] Sprint report explicitly enumerates: India results · USA results · Global comparison

**Missing any of these → sprint NOT COMPLETE. No exceptions. Docs count both markets.**

### Global Comparison Artifact (mandatory per sprint)

Every sprint that produces per-market outputs MUST also produce:
```
reports/global/<sprint_name>_comparison.json
```

Contents (per sprint's domain):
- India value · USA value · delta (absolute + %)
- Sample sizes for each market
- Statistical significance flag (using `backend.benchmark.statistical_significance` sample-size verdict)
- Per-dimension deltas (win rate · Sharpe · holding period · target achievement · exit efficiency · re-entry success · factor performance · sector performance · recommendation quality · portfolio performance)

This artifact becomes the substrate for future cross-market learning (identifying which strategies / factors / lifecycle behaviors work better in one market than the other).

---

## Hard Discipline (INVARIANT · learned from real incidents)

1. **Do NOT remove, bypass, or duplicate existing engines.** Extend and integrate. If two components appear to compete, the fix belongs INSIDE the aggregation layer, not outside via disabling one.
2. **Do NOT touch operator-visible features without explicit "yes" from the operator.** Telegram messages, dashboard tiles, workflow steps, notifications, output files. Options presented, decision theirs.
3. **Do NOT touch `india/telegram_notify.py` message contract** (OPS001-I sealed regression). Also sealed: `research/adaptive_rec_v2/`, `research/risk_capital_v2/`, MON001 files, fingerprint `e4c070673568c52d…`.
4. **Do NOT push without running the FULL local test suite first:**
   ```bash
   python nexaquant/tests/test_regression.py         # ENG001 + OPS001-I + invariance guards
   python backend/tests/test_sprint75.py              # persistence + factor library
   python backend/tests/test_sprint76.py              # historical backfill + replay
   python backend/tests/test_sprint77.py              # full replay + walk-forward + lookahead guard
   python backend/tests/test_sprint77_runner1.py      # Runner 1 legacy audit-trail
   python backend/tests/test_sprint78.py              # recommendation benchmark
   python backend/tests/test_telegram_notify_fallback.py
   ```
5. **No new AI agents.** Six exist (Rec/Risk/Portfolio/Learning/Macro/Execution Analysts). That is the full set.
6. **No new recommendation engines.** Runner 1 + Runner 2 + Trade Lifecycle Intel + Operator Intel is the FULL set.
7. **Every enhancement must pass Historical Replay + Walk-Forward + Research Governance** BEFORE production.
8. **Free/open-source stack only.** No paid APIs.
9. **Sealed OPS001/MON001 files untouched · fingerprint preserved · legacy engines untouched.**

---

## Execution Roadmap (revised 2026-07-24)

Seven phases · **Trade State Engine (Phase C1) is the anchor** · every phase gated on operator "start" before code touched.

### Phase A · Repository Intelligence (read-only, zero code change)

| Sprint | Deliverable | Output |
|---|---|---|
| **A1** | Repository Audit — Runner 1/2 architecture · all rec entry points · duplicates · dead code · connected vs disconnected engines | `docs/AEGIS_REPO_AUDIT.md` |
| **A2** | Research Engine Discovery — per-engine status matrix (Exists · Active · Connected · Partially · Planned · Missing) across the full inventory | `reports/research_engine_inventory.json` |

### Phase B · Historical Intelligence

| Sprint | Deliverable | Output |
|---|---|---|
| **B0 ⭐** | **History Quality Validation** — BEFORE replay, validate history is actually complete. Per data-family checks: recommendation history (missing/duplicate/partial/corrupted days) · price history (trading day gaps, missing candles, corporate-action-adjacent anomalies, delistings) · macro (GDP, inflation, repo, Fed observation coverage) · commodities (Gold/Oil/Copper/Nat-Gas coverage) · news (coverage, duplicates, missing days) · learning corpus (continuous or broken). Also **flags tickers where corporate-action-adjusted vs raw prices diverge** (input to future data-layer enhancement). | `reports/history_quality_report.json` with per-family PASS/WARN/FAIL + verdict READY_FOR_REPLAY or NEEDS_REPAIR |
| **B1** | Historical Replay `2025-01-01 → today` — every engine on `--asof`, no `latest` refs. **Cannot start until B0 reports READY_FOR_REPLAY** (otherwise replay silently trains on incomplete data). | expanded rec/risk/portfolio/execution/learning history parquets |
| **B2** | Institutional Walk-Forward — Sharpe · Sortino · CAGR · Alpha · Beta · DD · PF · Win / sector / regime / model | all `walkforward_*.json` populated on real backfilled ledgers |
| **B3** | Runner Benchmark — Runner 1 vs Runner 2 on RECONSTRUCTED history (never today's snapshot) | `reports/benchmark_compare.json` with verdict READY_FOR_COMPARISON |

**Data-layer enhancement (parallel track, not a Phase 3 sprint):** Corporate Actions Engine. Trade State (C1) currently consumes raw prices. Institutionally it should consume corporate-action-adjusted prices (splits · bonuses · dividends · mergers · delistings). B0 IDENTIFIES the issue; the fix lives in `data/` / `backend/canonical/` — existing engines extended, no new Phase 3 module. Prerequisite for institutional-grade Trade State on long histories.

### Phase C · Trade Intelligence

**⛔ HARD BLOCKER:** C1 CANNOT start until A1 (Repository Audit) AND A2 (Research Engine Discovery) are **literally complete** with `docs/AEGIS_REPO_AUDIT.md` + `reports/research_engine_inventory.json` on disk and reviewed. Otherwise C1 may later discover another history source or recommendation ledger and require redesign.

| Sprint | Deliverable | Output |
|---|---|---|
| **C1 ⭐** | **Trade State Engine** — TWO state machines: (a) `RecommendationState`: GENERATED → APPROVED → ACTIVE → SUPERSEDED → EXPIRED; (b) `PositionState`: NEW → OPEN → TARGET(+X%) → EXIT → POST_EXIT → REVERSAL → REENTRY → CLOSED. **Dumb data only** (current state · prices · holding day · highest / lowest · transitions). Dynamic target thresholds from config, not hardcoded slots. | `reports/trade_state.parquet` + `reports/recommendation_state.parquet` (append-only, one row per entity-day) |
| **C2** | Trade Lifecycle Intelligence Engine — analytics on top of state: probabilities, expected exit, re-entry probability, lifecycle scores. **Consumes state, never mutates it.** | `trade_lifecycle_analysis.json` + `trade_lifecycle_score.parquet` |
| **C3** | Target Horizon · Exit Intelligence · Re-entry Intelligence — three sub-modules of the lifecycle engine sharing the same state substrate | `profit_target_matrix.parquet` · `exit_efficiency_analysis.json` · `reentry_probability_matrix.parquet` |
| **C4** | Recommendation Drift Intelligence — monthly cadence: for each historical recommendation, compare (a) original rec → (b) current position state → (c) actual realized outcome → (d) what the current model would recommend TODAY → (e) why did they diverge? | `reports/recommendation_drift.parquet` + `reports/recommendation_drift_summary.json` |
| **C5 ⭐** | **Failure Analysis Engine** — for every LOSING closed position (learning corpus rows with `is_winner=False`), deterministic root-cause attribution: was the loss driven by wrong macro / wrong sector / wrong entry timing / wrong factor signal / wrong news reaction / wrong risk sizing? Each dimension scored 0-1 based on state at entry vs at exit. Uses existing macro_history · factor_library_history · sector_rotation history — no new data source. | `reports/failure_analysis.parquet` (per-position attribution) + `reports/failure_clusters.json` (recurring failure patterns) |

### Phase D · Recommendation Lifecycle

| Sprint | Deliverable | Output |
|---|---|---|
| **D1 ⭐** | **Recommendation Lifecycle Manager** — **THIN RENDERER · never calculates.** Composes Trade State + Trade Lifecycle + Risk + Portfolio + Macro upstream outputs into a unified JSON. Every field is a PASSTHROUGH from an upstream engine — this layer invents no metrics. | `reports/dynamic_trade_recommendations.json` |
| **D2** | Operator Intelligence Layer — ONE authoritative surface WITH PRIORITIZATION. Buckets: `Immediate Action` / `Review Today` / `Healthy Holdings` / `Watchlist`. Operator reads the bucket, not all 35 positions. | `reports/operator_daily_summary.json` (grouped by bucket) |
| **D3 ⭐** | **Explanation Engine** — DETERMINISTIC (not AI). For every recommendation, produces a per-dimension attribution: `why was this recommended?` → Macro %  + Sector %  + Fundamentals %  + Technical %  + Risk %  + Portfolio %  + Learning %. Attribution itself becomes historical (append-only) so drift + failure analyses can inspect it. | `reports/recommendation_explanations.parquet` (append-only) + `reports/recommendation_explanation_<date>.json` |

### Phase E · Operator Experience

| Sprint | Deliverable | Output |
|---|---|---|
| **E1** | Unified Telegram — extends `india/telegram_notify.py` (sealed contract preserved) to render from D2 output. UX030 sender REDIRECTS to same D2 output (no more competing streams — internal merge, not external disable) | new Telegram body shape, same OPS001-I invariants |
| **E2** | Unified Dashboard — every recommendation displays Holding Day · Current Return · Highest Return · Target Progress · Exit Status · Reversal Status · Re-entry Status · Lifecycle Score | dashboard tiles reading from D2 |
| **E3 ⭐** | **Operator Daily Report** — NEW SIGNALS / ACTIVE POSITIONS / Target Hit Today / Exit Recommended / Re-entry Opportunity / High Risk / Trade Lifecycle Changes / Macro Change / Portfolio | `reports/operator_daily_report.md` + Telegram morning brief |

### Phase F · Portfolio Intelligence

| Sprint | Deliverable | Output |
|---|---|---|
| **F1** | Portfolio Decision Engine — per-position (buy · increase · reduce · exit · hedge · wait · average · rebalance) PLUS portfolio-level answers: **Highest Conviction · Highest Risk · Most Overvalued · Best Re-entry · Most Urgent Exit · Sector Concentration · Cash Allocation · Portfolio Health.** | `reports/portfolio_decisions.json` (per-position) + `reports/portfolio_health.json` (portfolio-level) |
| **F2 ⭐** | **Portfolio Timeline Engine** — historical portfolio snapshots. Answers: "what did my portfolio look like 3 months ago / 6 months ago / last year?" Per-date: Cash · Exposure · Sector Allocation · PnL · Drawdown · Decisions · Macro Regime. Powered by portfolio_history + macro_history + walkforward outputs — no new data source. Replay becomes visual. | `reports/portfolio_timeline.parquet` (append-only, one row per portfolio-day) + `reports/portfolio_timeline_<range>.json` (queryable window) |

### Phase G · Continuous Self-Improvement

| Sprint | Deliverable | Output |
|---|---|---|
| **G1** | Research Factory ↔ Trade Lifecycle loop — trade lifecycle output feeds research tickets → walk-forward → promotion → production | `reports/research_promotion_ledger.parquet` |

**Sequencing rule:** phases execute in order (A → B → C → D → E → F → G). Within each phase, sprints execute in order. **No sprint starts without explicit operator "start" — options presented, decision theirs.**

**Full sprint sequence (FROZEN):**
```
A1 → A2 →
B0(⭐) → B1 → B2 → B3 →
C1(⭐) → C2 → C3 → C4 → C5(⭐) →
D1(⭐) → D2 → D3(⭐) →
E1 → E2 → E3(⭐) →
F1 → F2(⭐) →
G1
```

**No sprints beyond this list.** Once G1 lands, AEGIS has every major institutional capability. Future work is depth (making each engine deeper) not breadth (adding new engines). Data-layer enhancement (Corporate Actions in `backend/canonical/`) runs as a parallel track and is not a Phase 3 sprint.

---

## Why Trade State Engine (C1) Is The Anchor

Every downstream problem has ONE root cause: **positions are treated as stateless `BUY`/`SELL`/`HOLD` labels instead of evolving state machines.**

Once C1 exists, these problems SOLVE THEMSELVES:

| Problem | Fixed by Trade State Engine because... |
|---|---|
| Stale APOLLO recommendation (same message day after day) | APOLLO transitions `NEW → OPEN → holding day 1 → 2 → 3...` — content changes with state, not repeated as static |
| IPCALAB repeats identically | Same as above — state evolves; the notification renderer just prints current state |
| Day-tracking missing | Trade state carries `days_in_state`, `entry_asof`, `current_asof` |
| %-move missing | State transitions computed from current price vs entry — arithmetic falls out |
| Exit not tracked | `EXIT` and `POST_EXIT` are first-class states with their own timers |
| Reversal / re-entry disconnected | `REVERSAL` and `REENTRY` are state transitions, not separate engines |
| Dual-notification confusion | ONE state per position → ONE notification per position — competition dissolves |

Once C1 ships, C2 / D1 / D2 / E1-E3 become "consume the state and render", not "invent lifecycle from scratch."

---

## Mandatory Prerequisites (order — cannot start Phase 3 build until all green)

### 1 · Repository Audit
Repository evidence only. No assumptions. Determine:
- Runner 1 architecture (entry points, dependencies, output files)
- Runner 2 architecture
- ALL recommendation entry points across the repo
- Connected research engines · Disconnected research engines
- Duplicate logic · Legacy logic · Unused intelligence modules

### 2 · Research Engine Discovery
For every engine below, determine status: **Exists · Active · Connected · Partially Connected · Planned · Missing**.

- **Market:** Breadth · Liquidity · Market Regime
- **Macro:** GDP · Inflation · Repo · RBI · Fed · ECB · Fiscal Policy · Credit Growth
- **Commodities:** Brent · WTI · Crude · Gold · Silver · Copper · Aluminum · Steel · Coal · Uranium · Lithium · Agriculture · Natural Gas
- **Currency:** USD · INR · DXY
- **Bonds:** Yield Curve · Credit Spread
- **Volatility:** VIX · India VIX
- **Sector Intelligence:** Rotation · Ranking · Momentum
- **Fundamentals:** Revenue · Earnings · Cash Flow · ROE · ROCE · PE · PB · Debt
- **News:** Headlines · Sentiment · Corporate Events
- **Alternative Data:** ETF Flows · Insider Activity · Search Trends · Options · Futures
- **Knowledge Graph:** Entity Relationships · Supply Chain · Commodity Impact · Cross Sector Impact
- **Factor Library:** Momentum · Growth · Value · Quality · Volatility · Custom
- **Learning · Model Intelligence · Risk · Portfolio · Execution · Replay · Walk Forward**

For each, determine whether it currently contributes to recommendations.

### 3 · Historical Replay 2025-01-01 → Today
Every engine executing with `--asof`. No `latest` references.

### 4 · Walk-Forward Metrics
Sharpe · Sortino · CAGR · Alpha · Beta · Drawdown · Profit Factor · Win Rate · Sector Performance · Regime Performance · Model Performance.

### 5 · Recommendation Benchmark Runner 1 vs Runner 2
Using RECONSTRUCTED history, NOT today's snapshot. Win Rate · Sharpe · Drawdown · Profit Factor · BUY Precision · SELL Precision · HOLD Accuracy · Regime Performance · Sector Performance.

### 6 · Research Governance
No production change without: research ticket · minimum sample size · regime awareness · walk-forward validation · historical evidence · promotion review.

---

## Trade Lifecycle Intelligence Engine

Manages the complete lifecycle of every recommendation:

```
Entry → Holding → Target Achievement → Exit Optimization → Post-Exit Monitoring →
Reversal Detection → Re-entry Opportunity → Second Exit → Learning
```

### Answers Per Recommendation

**Entry**
- When should I enter?

**Holding**
- Probability distribution across 1 / 3 / 5 / 10 / 20 / 60 days

**Profit Targets** — for each of +1% / +2% / +3% / +5% / +7% / +10% / +15% / +20%:
- Probability of reaching
- Earliest day · Median day · Average day

**Exit**
- Optimal exit
- Historical exit probability
- Drawdown before exit
- Expected upside remaining
- Exit confidence

**Post-Exit Monitoring** (day 1 → day 60 after exit)
- Additional upside · Downside after exit
- Was exit premature? · Did exit capture the move?

**Reversal Detection**
- Reversal day · Reversal strength · False-reversal flag · Breakout · Trend reversal

**Re-entry**
- Optimal re-entry · Expected return · Expected holding · Expected exit
- Probability of second move

**Trade Lifecycle Score** — every completed recommendation receives:
- Entry Quality · Holding Quality · Exit Quality · Re-entry Quality · Overall Score

---

## Operator Intelligence Layer

**The operator NEVER receives raw recommendations.** Instead, a continuously evolving living object per position with the full lifecycle context.

### Daily Recommendation Evolution

```
BUY  ·  <TICKER>
  Recommendation Date       2026-XX-XX
  Holding Day               <n>
  Current Return            <pct>
  Highest Return            <pct>
  Lowest Drawdown           <pct>
  Current Drawdown          <pct>
  Target Progress           <pct of target>
  Historical Probability    <pct>
  Expected Holding          <days>
  Suggested Exit            <recommendation>
  Exit Confidence           <pct>
  Historical Additional Upside  <pct>
  Reversal Probability      <pct>
  Expected Re-entry Window  <days>
  Re-entry Probability      <pct>
  Trade Lifecycle Score     <0-100>
```

Every trading day: holding_day increments · current-return updates · highest-gain updates · drawdown updates · target-progress updates · exit recommendation updates · re-entry updates. **NO recommendation is static.**

### Unified Operator Notification

AEGIS produces **ONE** authoritative notification. Never multiple competing.

Internally combines: Runner 1 · Runner 2 · Macro · Commodities · Learning · Historical Replay · Walk Forward · Risk · Portfolio · Trade Lifecycle Intel → ONE institutional recommendation to the operator.

### Dashboard Evolves At Same Pace

Every recommendation on the dashboard displays: Holding Day · Current Return · Highest Return · Target Progress · Exit Status · Reversal Status · Re-entry Status · Lifecycle Score. Same shape as Telegram, same living object.

---

## New Outputs (Locked)

All append-only, walk-forward-safe, deterministic per asof:

```
trade_lifecycle_analysis.json          entry_quality_analysis.json
holding_period_statistics.json         profit_target_matrix.parquet
exit_efficiency_analysis.json          post_exit_analysis.json
reversal_statistics.json               reentry_horizon_analysis.json
reentry_probability_matrix.parquet     second_move_statistics.json
trade_lifecycle_score.parquet          dynamic_trade_recommendations.json
operator_daily_summary.json            operator_notification_history.parquet
```

---

## Long-Term Vision

AEGIS evolves from a Recommendation Engine into:

```
Institutional Investment Intelligence Platform
     ↓
Market Research → Sector Research → Industry Research → Company Research
     ↓
Recommendation → Trade Lifecycle Intelligence → Operator Intelligence
     ↓
Execution Intelligence → Learning → Evidence-Driven Self-Improvement
```

---

## Success Definition

A new operator can look at any trade and, within 30 seconds:
- Why did the system recommend it?
- What macro/event/factor conditions were in place at entry?
- Where is it right now in its lifecycle?
- What's the current recommendation (hold longer, exit, re-enter)?
- What actually happened after exit — did we capture the move?

No new *actions*, richer *understanding* of every action produced.

---

## What Comes After This Roadmap (freeze rationale)

Once these 18 sprints ship (A1 · A2 · B0 · B1 · B2 · B3 · C1 · C2 · C3 · C4 · C5 · D1 · D2 · D3 · E1 · E2 · E3 · F1 · F2 · G1), AEGIS has every major institutional capability:

- Research · Replay · Walk-Forward · Benchmarking
- Recommendation · Risk · Portfolio · Execution
- Trade State · Trade Lifecycle · Exit · Re-entry
- Recommendation Drift · Failure Analysis
- Operator Intelligence · Portfolio Intelligence · Portfolio Timeline
- Explanation Engine · Continuous Learning

**The bottleneck stops being architecture and becomes execution quality.** Every ounce of remaining effort goes into:
1. **Implementation quality** — each engine built to institutional standards, comprehensive tests, walk-forward validated
2. **Integration** — engines feeding each other cleanly, no orphan data, no dead outputs
3. **Depth** — making each existing engine smarter (better calibration, more historical evidence, tighter thresholds) rather than adding new ones
4. **Operator experience** — every intelligence surfaced through the unified Operator Intelligence Layer as living, day-by-day-evolving trade lifecycles

Any future request to add a Phase 3 engine after this date requires an explicit operator override, in writing, with a clear justification for why it cannot live inside the existing layer boundaries.

---

## Governance for This Document

- **FROZEN 2026-07-24** by operator directive.
- Supersedes `docs/AEGIS_PHASE3_ROADMAP.md` (kept for history reference).
- Any deviation from this pipeline requires an explicit operator override, in writing.
- Every sprint proposal that touches Phase 3 must reference this document in its report.
- Architecture is FROZEN — implementation is where value comes from now.

---

**End of Phase 3 Master Roadmap · LOCKED 2026-07-24**
