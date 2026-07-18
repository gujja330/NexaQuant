# AEGIS Phase 2 Master Roadmap

**The delivery document. Not what to build — how you'll know it's finished.**

Horizon: 6–12 months from lock date · 2026-07-17.
Governed by [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) and
[DESIGN_DECISIONS.md](DESIGN_DECISIONS.md). Any conflict — those two win.

---

## 1. Phase 2 Objective

> **Mission:** Transform AEGIS from a research platform into a
> continuously validated wealth intelligence platform.

Phase 1 answered *can we build coherent institutional research?* Yes,
including a rigorous self-diagnosis (the raw confidence signal has no
predictive power). Phase 2 answers a different question:

> **Does the platform actually compound capital, and can we prove it live?**

**Success criteria (all five must hold at Phase 2 completion):**

- **Better allocation** — capital sits in positions the Risk & Capital
  Engine can defend against three counter-questions per position.
- **Better calibration** — the rebuilt confidence signal shows
  meaningful win-rate discrimination across confidence tiers.
- **Better risk** — max drawdown constrained inside a documented budget;
  breaches auto-fire alerts and Champion review.
- **Better expectancy** — realised profit factor within a documented
  tolerance of expected profit factor across at least two quarters.
- **Better validation** — daily paper-trading harness running · rolling
  out-of-sample tracking live · expected-vs-actual reconciled monthly.

If any one of these is missing, Phase 2 is **not** complete regardless
of how many features shipped.

---

## 2. Current State

Progress against Phase 2 completion, per engine. Percentages are
outcomes-based (how much of the target capability is delivered), not
lines-of-code.

**Research Foundation Layer**
```
Complete    ████████████████████ 90%
Remaining              ░░
```
DEV017–DEV020 + DEV031-B shipped. 10% remaining: 10/44 industries and
2/14 sectors silently ungated · regime detection uses fallback classifier
for historical windows (no persisted per-date labels).

**Adaptive Recommendation Engine**
```
Complete    █████████████░░░░░░░ 65%
Remaining                  ░░░░░░░
```
v1.0–v1.4 shipped. **Blocker: v2.0 confidence rebuild.** The current
composite decision score is downstream-poisoned by the noisy raw
confidence input (DEV029 finding, ADR-008).

**Risk & Capital Engine**
```
Complete    ███████████░░░░░░░░░ 55%
Remaining              ░░░░░░░░░
```
v1.0–v1.2 shipped. Missing: v2.0 position sizing · v2.1 dynamic risk
budget · v2.2 correlation-aware allocation · v2.3 regime-conditional
allocation. Champion selection works but promotion recommender has never
actually promoted (only initial adoption).

**Validation Engine**
```
Complete    █████████░░░░░░░░░░░ 45%
Remaining              ░░░░░░░░░░░
```
v1.0 shipped (walk-forward PIT backtest, 2022+ window). Missing:
rolling out-of-sample tracking · paper trading harness · expected-vs-actual
reconciliation · edge-decay monitoring. Historical view only; no live
continuous validation loop.

**Multi-Asset Intelligence Engine**
```
Complete    ░░░░░░░░░░░░░░░░░░░░ 0%
Remaining              ░░░░░░░░░░░░░░░░░░░░
```
Not started. Deferred until Phase 2 P0–P3 are cleared and multi-asset
data feeds are procured (governance decision, not engineering).

**Delivery Layer**
```
Complete    ████████░░░░░░░░░░░░ 40%
Remaining              ░░░░░░░░░░░░
```
UX030 renderer + UX031 spec shipped as artifacts. Missing: Telegram
delivery pipeline wiring (UX030-B), Dashboard frontend implementation
(UX031-B), any authenticated write path.

**Overall Phase 2**
```
Complete    ████████████░░░░░░░░ ~59%
```
Weighted by engine importance. Foundation is strongest; Validation and
Multi-Asset are the material gaps.

---

## 3. Master Priority Table

Priorities are **outcome-importance**, ordered by how much each item
would improve decision quality if delivered. Execution order is
different (see §4 dependency graph) because some P-later items unblock
P-earlier items.

| Priority | Work                     | Engine       | Version | Six-priority mapping           |
|----------|--------------------------|--------------|---------|--------------------------------|
| P0       | Confidence rebuild       | Adaptive     | v2.0    | Calibration → Expectancy       |
| P1       | Live validation harness  | Validation   | v2.0    | Validation                     |
| P2       | Segment-level win rates  | Adaptive     | v2.1    | Allocation → Expectancy        |
| P3       | Position sizing          | Risk         | v2.0    | Allocation → Preservation      |
| P4       | Precision@K optimisation | Adaptive     | v2.2    | Calibration → Expectancy       |
| P5       | Dynamic risk budgeting   | Risk         | v2.1    | Preservation → Allocation      |
| P6       | Opportunity cost tracking| Validation   | v2.1    | Expectancy → Validation        |
| P7       | Ranking stability        | Adaptive     | v2.3    | Calibration                    |
| P8       | Edge decay monitoring    | Validation   | v2.3    | Validation                     |
| P9       | Abstention intelligence  | Adaptive     | v3.0    | Preservation → Explainability  |

**Deliberately absent from Phase 2** — because they do not clear the
research acceptance gate under [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) §9:

- Scenario simulator (nice-to-have; does not compound capital directly).
- Factor attribution as a new engine (may sit inside Adaptive Rec v2.x
  as an explanation tool, not as new capability).
- Multi-asset expansion (requires data-vendor decision, not engineering).
- Execution integration (constitutional decision under ADR-002).

---

## 4. Dependency Graph

Priority order is not execution order. To ship P0 (confidence rebuild)
you must first know whether the rebuild worked — which requires P1
(live validation) to be running. Execution proceeds in dependency order:

```
                         P1 · Validation v2.0
                    (live paper-trading harness)
                                |
                                v
                    P0 · Adaptive v2.0
                    (confidence rebuild)
                     verified against P1
                                |
                +---------------+---------------+
                |                               |
                v                               v
       P2 · Adaptive v2.1               P3 · Risk v2.0
       (segment win rates)              (position sizing)
                |                               |
                v                               v
       P4 · Adaptive v2.2               P5 · Risk v2.1
       (Precision@K)                    (dynamic risk budget)
                |                               |
                v                               v
       P7 · Adaptive v2.3               (Risk v2.2 · corr-aware)
       (ranking stability)                      |
                |                               v
                |                       (Risk v2.3 · regime-cond)
                |                               |
                +---------------+---------------+
                                |
                                v
                       P6 · Validation v2.1
                       (opportunity cost)
                                |
                                v
                       P8 · Validation v2.3
                       (edge decay)
                                |
                                v
                       P9 · Adaptive v3.0
                       (abstention)
```

**Rules:**
- No engine version ships without upstream dependencies shipping first.
- Every version bump is verified against the live Validation harness.
  No unverified capability reaches the delivery layer.
- Multi-Asset is not on this graph. It is deferred to Phase 3.

---

## 5. Success Metrics

Every milestone reports the full panel. No milestone is declared
complete on a single-metric win (ADR-013). No metric is optimised in
isolation.

| Metric              | Direction | Notes                                    |
|---------------------|-----------|------------------------------------------|
| Win Rate            | higher    | Anchor around 55–65% band; not maximised |
| Expectancy          | higher    | Per-trade R multiple                     |
| Profit Factor       | higher    | > 1.5 target                             |
| Avg Win             | higher    |                                          |
| Avg Loss            | lower (mag) |                                        |
| Max Drawdown        | lower (mag) | Constrained by risk budget             |
| Sharpe              | higher    | > 1.0 institutional band                 |
| Sortino             | higher    | > 1.5 target                             |
| Calmar              | higher    | CAGR / max DD                            |
| Stability Score     | higher    | 1st-half vs 2nd-half consistency         |
| Calibration Error   | lower     | ECE < 0.05 target (currently 0.002)      |
| Precision@K         | higher    | Track K in {1, 3, 5, 10, 20}             |
| Opportunity Cost    | lower     | Missed-edge tracking                     |

**Reporting cadence:** every experiment produces this panel. Milestone
gate reviews consume it. Cross-experiment comparisons happen against
this fixed shape.

---

## 6. Exit Criteria

Every milestone has a concrete DONE condition. Absent the condition,
the milestone remains open regardless of code shipped.

### Adaptive v2.0 — Confidence rebuild

DONE only if the reliability curve shows meaningful discrimination
across confidence tiers. Concretely:

- Strong-Buy realised win rate > Buy realised win rate
- Buy realised win rate > Hold realised win rate
- Hold realised win rate > Sell realised win rate (or Sell fires as
  intended — realised loss rate exceeds base rate)
- ECE remains below 0.05 after the rebuild
- Full metric panel does not regress vs v1.4 on any dimension by more
  than 5%

Otherwise the rebuild is incomplete and Adaptive stays on v1.4.

### Validation v2.0 — Live validation harness

DONE only if:

- Daily paper-trading run publishes to `reports/`
- Weekly, monthly, quarterly reports generated automatically
- Expected vs actual reconciliation report emits alerts on divergence
- At least 30 days of continuous operation without silent failure
- Harness verified against Adaptive v1.4 baseline before Adaptive v2.0
  is admitted for testing

### Risk & Capital v2.0 — Position sizing

DONE only if the portfolio can answer three counter-questions per
position:

- Why 6% allocation to this ticker?
- Why not 4%?
- Why not 12%?

Each answer must trace to inputs the operator can verify (score,
confidence, sector exposure, correlation, volatility, regime).

### Validation v2.1 — Opportunity cost

DONE only if a monthly opportunity-cost report exists that:

- Names the trades AEGIS did not recommend which subsequently won
- Categorises misses by reason (below score threshold · sector avoided ·
  regime-off · confidence too low · other)
- Is small enough to be reviewed by a human in under 30 minutes

### Adaptive v2.1 — Segment win rates

DONE only if a `segment_win_rates.parquet` artifact exists with rows
per (sector × industry × market-cap × regime) cell, and the Adaptive
Recommendation Engine downweights recommendations in cells where
realised win rate is below the base rate at statistical significance.

### Every other milestone

Exit criteria defined at proposal time. No milestone opens without
its exit criteria written down.

---

## 7. Technical Debt Register

Maintained in-place. Every entry has a planned closure milestone.

| Debt                                       | Severity | Planned closure       |
|--------------------------------------------|----------|-----------------------|
| Raw confidence heuristic (no signal)       | Critical | Adaptive v2.0         |
| 10/44 industries + 2/14 sectors ungated    | High     | Foundation v1.6       |
| Small learning sample (1,060 trades)       | High     | Validation v2.0 (rolling) |
| 99 DEV022 portfolios unbacked              | High     | Validation v2.2       |
| DEV028 DNA never consumed downstream       | High     | Adaptive v1.5         |
| UX030 renderer not wired to delivery       | High     | Delivery Layer v1.2   |
| UX031 has no frontend                      | High     | Delivery Layer v1.3   |
| India-only universe                        | Medium   | Multi-Asset (Phase 3) |
| Batch-only ingestion (daily yfinance)      | Medium   | Phase 3               |
| No per-date historical regime labels       | Medium   | Foundation v1.6       |
| Single-tenant                              | Medium   | Phase 3 governance    |
| Windows cp1252 encoding recurring          | Low      | Ongoing hygiene       |
| Print-to-stdout logging                    | Low      | Delivery Layer v1.4   |
| No incremental compute                     | Low      | Phase 3               |
| Company → Supplier / Customer edges absent | Low      | Foundation v2.0 (data-blocked) |

New entries append; closed entries move to a struck-through / archive
section rather than being deleted.

---

## 8. Research Debt Register

Separate from technical debt. These are gaps in *knowledge* the platform
has not yet built, not bugs in code that already exists.

| Research gap                       | Impact                                                              | Planned closure                |
|------------------------------------|---------------------------------------------------------------------|--------------------------------|
| No feature importance analysis     | Cannot rebuild confidence signal empirically                        | Precursor to Adaptive v2.0     |
| No causal analysis                 | Correlations treated as causal; regime shifts poorly understood     | Adaptive v3.x (long-horizon)   |
| No macro attribution               | Cannot decompose returns into macro-driven vs alpha-driven          | Validation v2.2                |
| No factor attribution              | Cannot report exposure to Value / Growth / Momentum / Quality / etc.| Adaptive v2.x (explanation tool)|
| No Bayesian uncertainty            | Point-estimate confidence only; no credible intervals               | Adaptive v2.x or v3.0          |
| No Monte Carlo forward projections | Cannot quantify range of Phase 2 outcomes                           | Validation v2.4 (deferred)     |
| No cross-market comparison         | Cannot benchmark India-only performance against international peers | Multi-Asset (Phase 3)          |

Research debt is closed by *investigation*, not by shipping code. A
research debt item may close without any new module — the closure is
"we now understand this and can defend the current design".

---

## 9. Production Readiness

Track per release. Updated by the implementation checklist under
[ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) §10.

| Dimension       | Current | Phase 2 target | Notes                                  |
|-----------------|---------|----------------|----------------------------------------|
| Logging         | 4/10    | 7/10           | Move from print-to-stdout to structured|
| Recovery        | 4/10    | 7/10           | No snapshot/restore beyond git         |
| Monitoring      | 4/10    | 8/10           | Telegram health checks exist; need metrics DB |
| Deployment      | 3/10    | 6/10           | AWS EC2 target; no CI/CD deploy pipeline |
| CI/CD           | 5/10    | 8/10           | GitHub Actions running; add build gates|
| Caching         | 3/10    | 5/10           | Nothing memoised; every run recomputes |
| Scaling         | 4/10    | 6/10           | Single-machine batch; sequential       |
| Security        | 3/10    | 7/10           | No auth on outputs; secrets in .env    |
| Observability   | 4/10    | 8/10           | No metrics DB, no dashboards           |

Phase 2 targets are the release bar. Every milestone that ships must
either not regress these or explicitly justify the regression.

---

## 10. Phase Completion Gate

Phase 2 is COMPLETE when — and only when — all of the following are
demonstrably true:

- **Validation** — live paper-trading harness has run for ≥ 90 days
  without silent failure. Weekly + monthly + quarterly reports exist.
- **Risk** — every position in the current portfolio answers the three
  counter-questions (§6 Risk & Capital v2.0 exit criteria).
- **Calibration** — rebuilt confidence signal shows tier discrimination
  (§6 Adaptive v2.0 exit criteria). ECE below 0.05.
- **Allocation** — position sizing traceable to inputs; sector /
  industry / regime concentration bounded by explicit budget.
- **Learning** — feedback loop from DEV025 into Adaptive v2.x closed;
  DNA feedback loop (v1.5) active.
- **Expectancy** — realised profit factor within documented tolerance
  of expected profit factor for ≥ 2 consecutive quarters.
- **Precision** — Precision@5 reported monthly and above chance level
  (>= 0.60 target aligned with `top_5_ew` win rate).
- **Stability** — ranking-stability metric reported; ranking churn per
  monthly rebalance below documented threshold.
- **Production readiness** — all §9 dimensions at or above the Phase 2
  target column.

If any single criterion is missing, Phase 2 is NOT complete regardless
of what else has shipped. This is the whole point of a gate.

---

## Closing

This roadmap is the delivery contract. The constitution
([ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md)) says how work
must be done; the ADRs ([DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)) say
why the constitution has the rules it does; this roadmap says what must
be true for Phase 2 to be finished.

When the roadmap conflicts with the constitution, the constitution
wins. When the constitution conflicts with an ADR, the ADR wins. When
new evidence contradicts an ADR, a new ADR opens and supersedes the
old one.

Read this before starting Phase 2 work. Update this when Phase 2 work
lands. Close Phase 2 only when this document says so.
