# AEGIS Engine Evolution Guide

**The engineering constitution. Read this before touching code.**

Version 1.0 · 2026-07-17 · Locked under [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) ADR-005

---

## 1. Vision

AEGIS evolves in three phases. Each phase reframes the problem, not the code:

```
Phase 1 — Research Intelligence            [COMPLETE · DEV017 – DEV031-B]
    Fifteen research modules. Deterministic pipelines. Advisory outputs.
    Answered: "Can we build a coherent, auditable investment research platform?"

    Verdict: yes, but the confidence signal has no predictive power.

              |
              v

Phase 2 — Wealth Intelligence              [CURRENT]
    Existing engines evolve in place. No new DEV modules by default.
    Every change must serve decision quality against six priorities.
    Answered: "Can we compound capital responsibly with what we already built?"

              |
              v

Phase 3 — Institutional Experience         [FUTURE]
    Multi-tenant, real-time, execution-integrated, compliance-audited.
    Answered: "Can AEGIS operate as an institutional product, not a
    research artifact?"
```

Phase 2 is where all current work happens. Phase 3 is deliberately deferred
until Phase 2 produces evidence that the engines compound capital.

---

## 2. Locked Architecture

AEGIS is **four operational engines** built on a **research foundation** and
communicated through a **delivery layer**. No new engines are added by
default — the operational surface is closed until the operator explicitly
reopens it.

### 2.1 Foundation Layer — Research Intelligence

Reads market data, produces the shared context every engine consumes.

| Module | Scope | Current Outputs |
|---|---|---|
| DEV017 Global Intelligence     | 23 macro variables · regime classification         | `global_context.json` |
| DEV018 Sector Intelligence     | 14 sectors scored on rotation + momentum           | `sector_intelligence.json` + `.parquet` |
| DEV019 Industry Intelligence   | 44 industries scored under sector rollup           | `industry_intelligence.json` + `.parquet` |
| DEV020 Company Intelligence    | 208 companies with hierarchical context            | `company_intelligence.json` + `.parquet` |
| DEV031 Knowledge Graph         | 581 nodes · 2,629 edges · communities · propagation | `knowledge_graph.json` (+ 10 companions) |

**Responsibility:** produce validated inputs. Never make decisions.
**Contract:** every downstream engine reads the foundation's artifacts; no
direct module calls.

### 2.2 Engine 1 — Adaptive Recommendation Engine

Turns research foundation into ranked, calibrated, auditable recommendations.

**Composition (current):**
- DEV023 Recommendation logic (8 types · entry / target / stop)
- DEV025 Adaptive learning (trade-outcome loop)
- DEV026 Research assistant (deterministic Q&A)
- DEV027 Strategy doctor (15 diagnostic rules)
- DEV028 Recommendation DNA (immutable audit trail)
- DEV029 Confidence calibration (5-method competition, Platt selected)

**Responsibility:** produce today's recommendations + their evidence chain.
**Never:** auto-execute · mutate state · rewrite past recommendations.

### 2.3 Engine 2 — Risk & Capital Engine

Turns ranked recommendations into position-sized, risk-budgeted portfolios.

**Composition (current):**
- DEV022 Portfolio construction (11 allocators × 9 types = 99 constructions)
- DEV024 Portfolio monitoring (11 alert types · 4 rebalance actions)
- DEV030 Champion vs Challenger (9-metric composite · 4-gate promotion)

**Responsibility:** allocation, capital preservation, drawdown control.
**Never:** override advisory-only posture · promote a strategy without
gate clearance.

### 2.4 Engine 3 — Validation Engine

Verifies that the other engines' outputs would have worked historically and
tracks whether they are working now.

**Composition (current):**
- DEV021 Historical validation & backtesting (walk-forward · PIT-safe)

**Responsibility:** provide the evidence base for every claim the other
engines make. Any strategy without a Validation Engine track record is
unbacked and cannot be promoted.

### 2.5 Engine 4 — Multi-Asset Intelligence Engine

**STATUS: PLANNED · not implemented.** Reserved as the fourth operational
engine. Extends the platform beyond equities to debt, gold, commodities,
FX. Adds new **input feeds** to the Research Foundation and new
**allocation targets** to the Risk & Capital Engine. Does not require new
recommendation logic — the Adaptive Recommendation Engine composes over
whatever the Foundation produces.

### 2.6 Delivery Layer

Communicates engine outputs to humans. Never mutates state.

| Layer | Current status |
|---|---|
| UX030 Telegram Intelligence     | Spec + renderer shipped · not wired to production delivery pipeline |
| UX031 Executive Dashboard       | JSON contracts shipped · no frontend implementation |

---

## 3. Engine Evolution Policy

Each engine advances through **versions**, not through new DEV numbers.
Version numbers carry meaning:

- `vN.0` — new capability (behavior change)
- `vN.M` — refinement of existing capability (no interface break)
- `vN.M.P` — bug fix / non-functional improvement

### 3.1 Adaptive Recommendation Engine

```
v1.0   Rule-based recommendations                     [DEV023]
v1.1   + Adaptive learning loop                       [DEV025]
v1.2   + Failure post-mortem diagnostics              [DEV027]
v1.3   + Immutable DNA audit trail                    [DEV028]
v1.4   + Confidence calibration (post-hoc)            [DEV029]
   |
   v
v2.0   Confidence signal rebuild                      [Phase 2 · P0]
       (raw confidence carries no signal today — must be replaced with
        features that have measurable win-rate discrimination)
v2.1   Segment-level win-rate integration
v2.2   Precision@K optimisation (Top1/Top3/Top5/Top10/Top20)
v2.3   Recommendation diversity + ranking stability
v3.0   Abstention intelligence — do not recommend when uncertain
```

### 3.2 Risk & Capital Engine

```
v1.0   99 constructions × 11 allocators               [DEV022]
v1.1   + Live monitoring + alerts                     [DEV024]
v1.2   + Champion vs Challenger governance            [DEV030]
   |
   v
v2.0   Position sizing optimisation
       (current: equal / score / kelly-quarter; add regime-aware sizing)
v2.1   Dynamic risk budgeting
v2.2   Correlation-aware allocation (beyond HRP)
v2.3   Regime-conditional capital allocation
```

### 3.3 Validation Engine

```
v1.0   Walk-forward PIT backtest · 6 strategies       [DEV021]
   |
   v
v2.0   Rolling out-of-sample tracking
v2.1   Expected vs actual reconciliation
v2.2   Paper trading harness (before any real execution)
v2.3   Strategy health monitoring (edge decay detection)
```

### 3.4 Multi-Asset Intelligence Engine

```
v1.0   [PLANNED · scope not yet approved]
       Only builds when the operator explicitly unblocks and multi-asset
       data feeds are procured. Do not scaffold ahead of that decision.
```

### 3.5 Foundation Layer (Research Intelligence)

Historical DEV17–DEV20 + DEV31 are frozen at v1.x. Future work modifies
the engines that consume them, not the foundation itself, unless a
consuming engine surfaces a specific input gap. Additions to the
foundation must be justified by demonstrating **at least one engine**
needs the new input.

---

## 4. Architecture Rules

Two governance questions. Non-negotiable. Every change is checked
against them.

### Rule 1 — Determinism

> Given identical inputs, does this change produce identical outputs?

If no, reject. AEGIS is auditable because it is deterministic. Random
seeds, wall-clock-derived values, and non-stable iteration orders are
forbidden. If randomness is unavoidable (e.g., certain optimisation
algorithms), it must be seeded explicitly and the seed committed as part
of the run metadata.

### Rule 2 — Advisory-Only

> Does this change auto-execute, mutate broker state, or bypass human
> review?

If yes, reject. AEGIS is advisory-only per ARCH001A Article V clause 5.1.
The only exception is a dedicated Execution Integration engine, which
must be advisory-mode-only until certified. Certification is a separate
governance decision, not an engineering one.

---

## 5. Data Flow

Every arrow below is a validated artifact under `reports/`. No engine
calls another engine directly. Removing this constraint would remove
determinism (Rule 1).

```
                Market Data (yfinance, daily)
                          |
                          v
    +---------------------+---------------------+
    |         Research Foundation Layer         |
    |  DEV017 Global -> DEV018 Sector ->        |
    |  DEV019 Industry -> DEV020 Company        |
    |  DEV031 Knowledge Graph                   |
    +---------------------+---------------------+
                          |
        +-----------------+-----------------+
        |                 |                 |
        v                 v                 v
+----------------+ +----------------+ +----------------+
|   Adaptive     | |   Risk &       | |   Validation   |
| Recommendation | |   Capital      | |   Engine       |
|   Engine       | |   Engine       | |                |
+-------+--------+ +-------+--------+ +-------+--------+
        |                  |                  |
        |     +------------+                  |
        |     |                               |
        v     v                               |
    Recommendations ---> Portfolio -> Monitoring ---> Learning
                                                      loop back to
                                                      Adaptive Rec
                                                      Engine's learning
        \                 |                    /
         \                v                   /
          \-----> Validation Evidence <------/
                          |
                          v
                    Delivery Layer
                (UX030 Telegram · UX031 Dashboard)
```

**Flows:**
- **Downstream:** Foundation → Recommendations → Portfolio → Monitoring.
- **Feedback:** Trade outcomes → Learning (DEV025) → back into
  Adaptive Recommendation for next-cycle calibration.
- **Validation:** Every engine's output is checkable against the
  Validation Engine's backtest evidence before it is trusted.

---

## 6. JSON Contracts

Each engine declares its **input contract** (files it reads) and its
**output contract** (files it emits). Consumers depend on the contract,
not on the producer's code.

### 6.1 Adaptive Recommendation Engine

**Inputs:**
```
reports/global_context.json                (Foundation · DEV017)
reports/sector_intelligence.json           (Foundation · DEV018)
reports/industry_intelligence.json         (Foundation · DEV019)
reports/company_intelligence.json          (Foundation · DEV020)
reports/knowledge_graph.json               (Foundation · DEV031)
reports/learning.parquet                   (Self · feedback loop)
```

**Outputs:**
```
reports/recommendations.json / .parquet    (DEV023)
reports/learning.parquet                   (DEV025 · appended)
reports/learning_summary.json              (DEV025)
reports/strategy_doctor.json / .parquet    (DEV027)
reports/recommendation_dna.json / .parquet (DEV028)
reports/confidence_calibration.json        (DEV029)
reports/confidence_calibration.parquet     (DEV029)
reports/calibration_metrics.json           (DEV029)
reports/reliability_diagram.json           (DEV029)
reports/confidence_bias.json               (DEV029)
reports/calibration_history.json           (DEV029)
```

### 6.2 Risk & Capital Engine

**Inputs:**
```
reports/recommendations.json               (Adaptive Rec Engine)
reports/confidence_calibration.parquet     (Adaptive Rec Engine · advisory)
reports/global_context.json                (Foundation · DEV017)
reports/backtest_summary.parquet           (Validation Engine · DEV021)
reports/backtest_equity_curves.csv         (Validation Engine · DEV021)
```

**Outputs:**
```
reports/portfolio.json / .parquet          (DEV022)
reports/portfolio_monitoring.json          (DEV024)
reports/rebalance_plan.json                (DEV024)
reports/champion_strategy.json             (DEV030)
reports/challenger_scoreboard.json         (DEV030)
reports/head_to_head_matrix.json           (DEV030)
reports/regime_comparison.json             (DEV030)
reports/drift_report.json                  (DEV030)
reports/promotion_recommendation.json      (DEV030)
reports/strategy_leaderboard.parquet       (DEV030)
```

### 6.3 Validation Engine

**Inputs:**
```
reports/company_intelligence.parquet       (Foundation · DEV020)
reports/global_context.json                (Foundation · DEV017)
data/raw/india/*.parquet                   (Market data)
```

**Outputs:**
```
reports/backtest_summary.json / .parquet   (DEV021)
reports/backtest_equity_curves.csv         (DEV021)
reports/strategy_comparison.json           (DEV021)
reports/failure_analysis.json              (DEV021)
reports/signal_attribution.json            (DEV021)
```

### 6.4 Multi-Asset Intelligence Engine (Planned)

Not yet defined. Contracts declared at v1.0 approval time.

### 6.5 Delivery Layer

**Inputs (Telegram):** All engine outputs. Renderer is read-only.
**Inputs (Dashboard):** All engine outputs plus knowledge graph subgraphs.
**Outputs (Telegram):** Message strings sent to Telegram Bot API. No
files written to `reports/`.
**Outputs (Dashboard):** `reports/dashboard_*.json` configuration only.

---

## 7. Version History

The DEV017-DEV031-B numbering is preserved as **historical milestones**
in git and in the architecture review. From Phase 2 onward, changes are
documented as engine versions:

| Historical (Phase 1) | Engine (Phase 2 onward) | v |
|---|---|---|
| DEV017 · Global Intelligence         | Research Foundation         | 1.0 |
| DEV018 · Sector Intelligence         | Research Foundation         | 1.1 |
| DEV019 · Industry Intelligence       | Research Foundation         | 1.2 |
| DEV020 · Company Intelligence        | Research Foundation         | 1.3 |
| DEV021 · Backtesting                 | Validation Engine           | 1.0 |
| DEV022 · Portfolio Construction      | Risk & Capital Engine       | 1.0 |
| DEV023 · Recommendation Engine       | Adaptive Rec Engine         | 1.0 |
| DEV024 · Portfolio Monitoring        | Risk & Capital Engine       | 1.1 |
| DEV025 · Adaptive Learning           | Adaptive Rec Engine         | 1.1 |
| DEV026 · Research Assistant          | Adaptive Rec Engine         | 1.1a |
| DEV027 · Strategy Doctor             | Adaptive Rec Engine         | 1.2 |
| DEV028 · Recommendation DNA          | Adaptive Rec Engine         | 1.3 |
| DEV029 · Confidence Calibration      | Adaptive Rec Engine         | 1.4 |
| DEV030 · Champion vs Challenger      | Risk & Capital Engine       | 1.2 |
| DEV031 · Knowledge Graph             | Research Foundation         | 1.4 |
| DEV031-B · Graph completion          | Research Foundation         | 1.5 |
| UX030 · Telegram Intelligence        | Delivery Layer              | 1.0 |
| UX031 · Executive Dashboard          | Delivery Layer              | 1.1 |

**Rule:** any new work opens with a stated target engine + version.
Example commit prefix: `Adaptive Rec Engine v2.0 : confidence rebuild`.

---

## 8. Future Research (Phase 2 Backlog)

All future research proposals must map to one or more of the six research
themes and one or more of the six priorities. The full active backlog:

### 8.1 Expectancy & profit-factor

Instrument every recommendation with per-trade expectancy targets, and
track realised profit factor against expected. Detect drift when realised
undershoots expected by more than a documented threshold.

**Priority:** Better expectancy · **Engine:** Adaptive Rec Engine v2.x

### 8.2 Precision curves

Compute Precision@K for K in {1, 3, 5, 10, 20} across the recommendation
history. Report as a ranked table alongside the calibration metrics. Use
Precision@5 as the primary quality metric (aligns with `top_5_ew`
champion).

**Priority:** Better calibration + better expectancy · **Engine:**
Adaptive Rec Engine v2.2

### 8.3 Recommendation DNA feedback

DEV028 emits immutable DNA records; no engine reads them today. Wire the
Adaptive Recommendation Engine to consume its own historical DNA to
detect repeat failures and adjust future recommendations.

**Priority:** Better calibration + better explainability · **Engine:**
Adaptive Rec Engine v1.5

### 8.4 Feature importance analysis

Analyse which features actually discriminate winners from losers. This is
the empirical foundation for the v2.0 confidence rebuild. Without this,
the rebuild is guesswork.

**Priority:** Better calibration · **Engine:** Adaptive Rec Engine v1.5
(precursor to v2.0)

### 8.5 Abstention intelligence

When the confidence signal is genuinely uncertain, the engine should
abstain rather than recommend Hold. Introduce an "Abstain" recommendation
type that surfaces its uncertainty.

**Priority:** Better calibration + better capital preservation ·
**Engine:** Adaptive Rec Engine v3.0

### 8.6 Opportunity cost

Track the trades AEGIS did not recommend but that would have won. Report
as a monthly opportunity-cost figure. Distinguishes disciplined abstention
from missed edges.

**Priority:** Better expectancy · **Engine:** Validation Engine v2.1

### 8.7 Edge decay monitoring

For each strategy, detect when its recent-window Sharpe / expectancy
degrades meaningfully vs its historical baseline. Fire a drift alert;
route to the Champion promotion recommender.

**Priority:** Better validation · **Engine:** Validation Engine v2.3

### 8.8 Ranking stability

How often do the same tickers appear in top-K across consecutive runs?
Volatile rankings imply weak signal; stable rankings imply strong signal.
Track and surface.

**Priority:** Better calibration + better expectancy · **Engine:**
Adaptive Rec Engine v2.3

### 8.9 Segment-level win rates

Compute win-rate stratified by sector · industry · market-cap · regime.
Surface segments where AEGIS wins consistently vs segments where it does
not. Guides where to concentrate + where to abstain.

**Priority:** Better allocation + better expectancy · **Engine:**
Adaptive Rec Engine v2.1

### 8.10 Continuous learning

The learning loop currently only updates on trade-closure. Add continuous
learning over the open-position window: MFE / MAE tracking, stop-loss
efficacy, entry-timing accuracy.

**Priority:** Better calibration · **Engine:** Adaptive Rec Engine v3.x

**Note on prioritisation:** the operator will select the actual sequence.
This document lists the backlog; it does not schedule the work.

---

## 9. Research Acceptance Criteria

Every research proposal must open with answers to these six questions.
If four or more answers are "No", reject or defer.

1. Does it improve **allocation**?
2. Does it improve **capital preservation**?
3. Does it improve **calibration**?
4. Does it improve **validation**?
5. Does it improve **expectancy**?
6. Does it improve **explainability**?

Additionally:

- **Can it be implemented within an existing engine?** If it requires a
  brand-new engine, that is a governance-level decision, not an
  engineering one. Escalate.
- **Does it optimise a single metric in isolation?** If yes, reject.
  Every experiment must report the full metric panel (Win Rate ·
  Expectancy · Profit Factor · Avg Win · Avg Loss · Max DD · Sharpe ·
  Sortino · Calmar · Stability Score · Calibration Error · Precision@K ·
  Opportunity Cost).

---

## 10. Implementation Checklist

Every merge into `main` must include:

- [ ] **Architecture impact statement** — which engine · which version bump
- [ ] **Data flow diff** — new inputs consumed · new outputs produced ·
      contracts unchanged unless a version bump justifies it
- [ ] **Tests** — smoke tests updated · determinism reasserted · PIT
      safety reasserted if the change touches backtest paths
- [ ] **Documentation** — this file (`ENGINE_EVOLUTION_GUIDE.md`) updated
      if any contract or version changes
- [ ] **ADR** — new [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) entry
      if a governance choice was made
- [ ] **Migration** — how existing consumers cope with the new outputs;
      any breaking-change migration path stated explicitly
- [ ] **Benchmarks** — for any change to a scoring / ranking algorithm,
      before/after full-metric-panel report on the same corpus
- [ ] **Production readiness** — logging · error handling · CLI ·
      recovery pathway all considered even if not fully addressed

---

## Closing

This guide is the constitution. The rules here are more durable than any
single module. When the guide and any code disagree, the guide wins
until the guide itself is updated by an ADR.

Read this before touching code. Update it after touching code. Reject
proposals that ignore it.
