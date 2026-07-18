# NexaQuant · AEGIS Manifesto

> Why AEGIS exists — and why it is built the way it is.

This document is deliberately not technical. Every other document in
this repository tells you *how* AEGIS is built. This one tells you *why*.
When a future contributor cannot understand why a rule exists — start here.

---

## Mission

Build an institutional-grade wealth intelligence platform focused on
responsible long-term capital allocation.

Not a screener. Not a signal service. Not an execution bot. A platform
that treats every recommendation as an evidence chain, learns from
outcomes systematically, and admits its own weaknesses in daylight.

The mission is durable. Every specific milestone in
[PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md) is temporary. If
the roadmap and the mission ever conflict, the mission wins.

---

## Core Principles

The six principles below apply to every decision — architectural,
research, product, and organisational.

### Determinism

Given identical inputs, AEGIS produces identical outputs. Always. The
reason a review board can trust a claim is because the review board can
reproduce it. The reason a bug can be fixed is because it recurs
deterministically. The reason yesterday's recommendation can be
justified today is because yesterday's evidence chain still runs. If a
technique cannot be made deterministic, it does not enter the platform.

### Evidence over intuition

No claim is asserted without artifacts to back it. No strategy is
promoted without a Validation Engine track record. No confidence
percentage is surfaced without calibration data behind it. Intuition
is welcome as a hypothesis; it is never accepted as a conclusion.

### Explainability

Every recommendation traces to inputs the operator can inspect. Every
metric ties to a specific artifact under `reports/`. Every algorithmic
choice has an ADR in [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md). If
someone asks "why did AEGIS say buy this?" — the platform can answer
in evidence, not in prose.

### Advisory-first

AEGIS never auto-executes. Never mutates broker state. Never bypasses
human review. This is a constitutional constraint (ADR-002), not a
technical limitation. The platform's job is to make the human decision
better — not to remove the human from it. The day AEGIS could auto-trade
and chose not to is the day the constitutional discipline was worth
building.

### Continuous validation

Backtests are the beginning of a claim, not the end. Every strategy
that reaches the delivery layer is being watched, live, by the
Validation Engine. Edge decay is expected; the platform's job is to
detect it before it destroys capital, not after.

### Capital preservation

The first priority of the six-priority research order is **better
allocation**. The second is **better capital preservation**. Growth
follows. This ordering is not accidental. Any research that improves
average return at the cost of tail-risk fails the priority order and
is not admitted.

---

## Engineering Philosophy

### Artifact-driven architecture

No module calls another module's code. Every module reads validated
artifacts from `reports/` and writes its own. This is why the full
lifecycle is replayable, why every module is independently testable,
and why the platform is fifteen composable engines rather than one
monolith of implicit dependencies (ADR-001).

### Engine evolution over module proliferation

Fifteen research modules were enough. The platform now advances through
**engine versions**, not new module numbers (ADR-003). This constrains
architectural surface, keeps the engines comprehensible, and forces
new work to improve capability rather than accrete features.

### Governance before expansion

Every new capability passes six research-priority questions before it
is written. Every architectural decision opens an ADR before it lands.
Every version bump reports the full metric panel before it is
declared shipped. Governance is not a slowdown — it is what makes
speed sustainable.

### Determinism as an engineering discipline

Determinism is enforced in code (fixed iteration counts, sorted
iteration orders, lex tie-breaks, no random seeds unless explicitly
committed), not just aspired to in prose. When randomness cannot be
avoided, it is seeded and the seed is part of the run metadata.

### Tenant-generic by default

No ticker, sector, industry, or company is hardcoded (ADR-010). AEGIS
serves NexaQuant today but the code carries no assumption about who it
serves. This makes multi-tenant expansion an operational change, not a
code rewrite.

---

## Research Philosophy

### Optimise decision quality, not feature count

The measure of a research effort is not "did we ship a new engine" —
it is "did we improve one of the six priorities" (allocation ·
preservation · calibration · validation · expectancy · explainability).
Impressive-sounding work that does not improve decisions is deferred,
not scheduled.

### Measure expectancy alongside win rate

Any experiment that optimises win rate in isolation regresses
expectancy. Any experiment that optimises expectancy in isolation
regresses drawdown. Every experiment reports the full thirteen-metric
panel (ADR-013). Cross-experiment comparisons happen against the fixed
shape, not the researcher's chosen headline.

### Learn systematically from both successes and failures

DEV025 (Adaptive Learning) captures winners *and* losers. DEV027
(Strategy Doctor) diagnoses failures. DEV028 (Recommendation DNA)
preserves the reasoning behind every past recommendation. The
combination is the platform's memory. Any research that improves
this memory ranks higher than research that adds new inference.

### Admit weakness in daylight

The most credible thing AEGIS has produced to date is the discovery
that its own raw confidence signal has no predictive power (ADR-008).
Three independent modules found it. The finding was published, not
suppressed. Phase 2's P0 milestone is the rebuild. This is how a
research platform is supposed to work: it surfaces its own weaknesses
faster than an external reviewer would.

---

## Long-Term Vision

AEGIS is not aiming to generate the maximum number of recommendations.

It is aiming to become a **deterministic, explainable, continuously
validated, institutional-grade wealth intelligence platform that
compounds capital responsibly over the long term**.

The success measure is not modules shipped. It is not features
released. It is not commit count. The success measure is:

> Over a full market cycle, did AEGIS make its users' capital compound
> at a defensible rate, with a documented risk budget, and produce an
> evidence trail an institutional review would accept?

Everything else — the four engines, the JSON contracts, the ADRs, the
constitution, the roadmap, this manifesto — exists in service of that
single question.

---

## For future contributors

If you are opening this repository for the first time, read in this
order:

1. This document (`NEXAQUANT_MANIFESTO.md`) — the why
2. [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) — the reasons behind the how
3. [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) — the how
4. [PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md) — the what-next
5. [AEGIS_ARCHITECTURE_REVIEW.pdf](AEGIS_ARCHITECTURE_REVIEW.pdf) —
   an honest assessment of where the platform stands today

Then look at the code. In that order, the code will make sense. In
any other order, you will re-derive decisions the platform has already
made.

---

*NexaQuant · Institutional Research · Advisory Only · Confidential*
