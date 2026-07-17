# AEGIS Design Decisions

**Architecture Decision Records (ADRs).**

Every non-trivial architectural choice that shaped AEGIS lives here.
When you ask "why is it built this way?", the answer is in this file
rather than in someone's head or lost in a commit message.

Format per ADR:

- **ID** — stable identifier, never renumbered
- **Title** — one line
- **Status** — Accepted · Superseded · Deprecated · Reversed
- **Context** — the problem or forcing question
- **Decision** — what was chosen
- **Consequences** — what it enables · what it costs
- **Alternatives considered** — what else was on the table

New decisions append. Old decisions are not deleted; if reversed, mark
the status and add a Superseded-by link.

---

## ADR-001 · Artifact-driven architecture

- **Status:** Accepted (2026 · Phase 1)
- **Context:** Fifteen research modules each producing intermediate results
  that later modules consume. If modules called each other directly, the
  full lifecycle would not be replayable, individual modules would not be
  independently testable, and a change to any module would ripple
  through the entire system unpredictably.
- **Decision:** No module calls another module's code. Every module reads
  validated artifacts from `reports/` (JSON / Parquet / CSV) and writes
  its own artifacts. The producer never knows who its consumers are.
- **Consequences (positive):**
  - Determinism is enforceable — same artifacts in, same artifacts out.
  - Every module has a single `run.py` and can be exercised in isolation.
  - The full lifecycle is replayable from any snapshot of `reports/`.
  - Onboarding is easier — each module is a self-contained unit.
- **Consequences (negative):**
  - Disk I/O overhead on every step (acceptable at daily-batch scale).
  - Contract drift is possible if producers change output shape without
    consumers being updated — mitigated by contract documentation in
    [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) §6.
- **Alternatives considered:**
  - In-memory pipeline (Airflow / Dagster / plain function calls) —
    faster, but destroys replayability.
  - Message-queue architecture (Kafka) — appropriate for real-time but
    overkill for daily batch and would require redesigning module
    boundaries.

---

## ADR-002 · Advisory-only

- **Status:** Accepted (2026 · Phase 1 · ARCH001A Article V clause 5.1)
- **Context:** AEGIS produces investment recommendations. The default
  assumption in a recommendation platform is that recommendations may
  eventually flow into an execution layer. That assumption creates
  compliance, fiduciary, and reputational exposure disproportionate to
  the platform's current maturity.
- **Decision:** No engine may auto-execute, mutate broker state, or
  bypass human review. Every output is advisory. This is a
  constitutional constraint, not an engineering convenience.
- **Consequences (positive):**
  - No possibility of unintended trading — the platform cannot lose
    money it does not control.
  - Compliance surface is dramatically smaller.
  - Users cannot blame the platform for execution decisions they made.
- **Consequences (negative):**
  - AEGIS never captures the "full loop" of automated trading value.
  - Any future Execution Integration engine is a governance decision,
    not an engineering roadmap item.
- **Alternatives considered:**
  - Optional auto-execution (opt-in per user) — rejected because it
    creates a two-tier system where the default posture is unclear.
  - Advisory-by-default with certified execution mode — deferred until
    Phase 3 and only under a separate governance ADR.

---

## ADR-003 · Engine evolution over module proliferation

- **Status:** Accepted (2026-07-17)
- **Context:** By DEV031-B the platform had accumulated fifteen numbered
  research modules. The natural extrapolation was DEV032, DEV033, DEV034
  — a linear list of new modules. This would eventually produce a
  platform whose surface area was defined by its accretion history
  rather than its architecture.
- **Decision:** From Phase 2 onward, work is scoped as **engine
  versions**, not new DEV modules. The four operational engines
  (Adaptive Recommendation · Risk & Capital · Validation · Multi-Asset)
  and one foundation layer (Research Intelligence) are the fixed
  architectural surface. New capabilities advance existing engines
  (e.g., `Adaptive Rec Engine v2.0`), not new engines.
- **Consequences (positive):**
  - Architectural surface stays comprehensible.
  - Release history becomes readable (v1.0 → v1.1 → v2.0) instead of
    a sequence of unrelated module numbers.
  - Naming aligns with what the engines actually do rather than the
    accident of when they were built.
- **Consequences (negative):**
  - DEV017–DEV031-B numbering becomes historical rather than active
    — reduces visibility into legacy module ownership until the
    version mapping in [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) §7 is internalised.
  - Some future work will not fit neatly into an existing engine and
    will require a governance-level "is this a new engine?" decision.
- **Alternatives considered:**
  - Continue linear DEV numbering — rejected as it encourages module
    proliferation over capability improvement.
  - Group modules under thematic labels but keep the numbering —
    rejected as cosmetic; doesn't change the underlying incentive.

---

## ADR-004 · Validation starts immediately

- **Status:** Accepted (2026 · Phase 1 · DEV021 built first among engines)
- **Context:** Investment platforms are frequently built recommendation-first,
  with validation added late — often after real money has been risked
  based on unvalidated logic. This ordering treats validation as an
  afterthought when it is actually the source of every credible claim.
- **Decision:** The Validation Engine (DEV021) was built before the
  Recommendation Engine (DEV023) and before the Portfolio Engine
  (DEV022). Every strategy that reaches the Champion tier must have
  a Validation Engine track record. No unbacked claim reaches the
  delivery layer.
- **Consequences (positive):**
  - Every recommendation traces to a walk-forward, PIT-safe backtest.
  - The Champion vs Challenger framework can enforce sample-size gates
    (DEV030 requires 30+ trades before promotion).
  - Trust is earned by evidence, not asserted by copy.
- **Consequences (negative):**
  - Slower to first recommendation than a validation-later approach.
  - Backtest window is fixed at 2022+ (three-year corpus) — narrower
    than a full-history platform would provide.
  - Strategies without backtest coverage are excluded even if they
    would otherwise be reasonable.
- **Alternatives considered:**
  - Validation as a follow-on module — rejected because it produces
    the exact ordering this ADR is meant to prevent.
  - Skip backtesting and rely on live paper-trading — rejected because
    live paper-trading would take years to produce equivalent evidence.

---

## ADR-005 · No new DEV modules after DEV031-B

- **Status:** Accepted (2026-07-17)
- **Context:** After DEV031-B the operator locked the architecture. The
  future roadmap moved from "which new module do we build?" to "how do
  we make the existing engines produce better decisions?"
- **Decision:** No new DEV-numbered modules are added by default. Phase 2
  work advances existing engines through version bumps. Any proposal
  for a genuinely new engine escalates to a governance decision (a new
  ADR) rather than being scheduled as engineering work.
- **Consequences (positive):**
  - Focus shifts from feature count to decision quality.
  - Architecture stays locked (see ADR-003) rather than drifting under
    add-a-module pressure.
  - The six-priority research order (allocation → preservation →
    calibration → validation → expectancy → explainability) actually
    guides work instead of being an aspiration.
- **Consequences (negative):**
  - Some Phase-1-era roadmap items (DEV032 Scenario Simulator, DEV033
    Factor Attribution, DEV034 Multi-Asset, DEV035 Governance,
    DEV036 APIs, DEV037 Realtime, DEV038 Execution) are now
    "reopened by governance" rather than "scheduled by engineering."
- **Alternatives considered:**
  - Continue the DEV roadmap unchanged — rejected because it produced
    ADR-003's stated problem.
  - Freeze the codebase entirely — rejected as it eliminates the
    engine-evolution path this ADR is designed to protect.

---

## ADR-006 · Determinism is mandatory

- **Status:** Accepted (2026 · Phase 1)
- **Context:** Institutional review requires that any published claim
  be reproducible. Random seeds, wall-clock-derived values, and
  order-dependent iteration all destroy reproducibility.
- **Decision:** Every algorithm in AEGIS is deterministic. Where an
  algorithm has a natural randomised form (label propagation, PageRank
  initial vector), the deterministic variant is chosen: sorted-node
  iteration, lex tie-breaks, fixed iteration counts. Explicitly seeded
  randomness is permitted only when strictly required and the seed is
  stamped into the run metadata.
- **Consequences (positive):**
  - Every claim is reproducible from the code + inputs.
  - Test assertions can check exact values, not "close to" bounds.
  - Debugging is possible — a bug reproduces every time.
- **Consequences (negative):**
  - Some algorithms (stochastic gradient descent) are structurally
    forbidden and must be replaced with deterministic alternatives.
  - Performance is sometimes worse than a randomised counterpart.
- **Alternatives considered:**
  - Seed-based determinism ("random but seeded") — allowed as a
    fallback but not the default; the deterministic-by-construction
    variant is preferred when it exists.

---

## ADR-007 · Point-in-time safety enforced by test

- **Status:** Accepted (2026 · Phase 1 · DEV021)
- **Context:** The single most common bug in backtesting is look-ahead
  bias — the strategy sees data at time T+1 that would not have been
  available at time T. Look-ahead bias inflates backtest results and
  produces strategies that fail live.
- **Decision:** Every backtest module includes a
  `test_pit_scorer_no_lookahead` assertion. Any code path that could
  peek at future data must fail this test before it can be merged.
- **Consequences (positive):**
  - PIT safety is verified, not asserted.
  - Any future backtest module inherits the requirement automatically.
- **Consequences (negative):**
  - Test coverage overhead on every backtest change.
  - Some legitimate lookback techniques must be rewritten to be
    PIT-safe (e.g., cannot use rolling stats that include the current
    bar for a decision made on the current bar).

---

## ADR-008 · The raw confidence signal has no predictive power

- **Status:** Accepted (2026-07-17 · surfaced by DEV029)
- **Context:** Three independent modules (DEV025 · DEV027 · DEV029)
  detected that AEGIS's raw confidence field has no discriminative
  signal against trade outcomes. Every trade wins ~58% regardless of
  stated confidence. Platt scaling correctly collapses the label to the
  base rate.
- **Decision:** The current raw confidence signal is treated as a
  rank-ordering label, not a probability. DEV029's calibrated
  confidence is what the delivery layer surfaces. A rebuild of the
  raw signal (Adaptive Rec Engine v2.0) is scheduled as P0 in Phase 2.
- **Consequences (positive):**
  - The platform admits its own foundational weakness — earning
    credibility rather than hiding it.
  - The rebuild becomes a well-scoped Phase 2 project with a clear
    success criterion (Precision@K discrimination between confidence
    tiers).
- **Consequences (negative):**
  - Every recommendation currently in the corpus inherits the noisy
    signal — the composite decision score is downstream-poisoned.
  - Until v2.0, users must treat the confidence percentage as a rank
    label, not a probability. This is documented but not enforced.
- **Alternatives considered:**
  - Patch the calibration without rebuilding the raw signal — this is
    what DEV029 does, and the finding proves it is insufficient.
  - Discard confidence entirely — rejected because rank information
    is still useful for surfacing top-K.

---

## ADR-009 · Content-addressed audit trail

- **Status:** Accepted (2026 · Phase 1 · DEV028)
- **Context:** Institutional review requires that any recommendation be
  traceable to its exact inputs and reasoning at the moment it was
  issued. Overwrite-on-next-run destroys this. Timestamp-based storage
  is vulnerable to clock drift and reordering.
- **Decision:** Every recommendation is content-hashed and stored in an
  append-only DNA table (DEV028). Records cannot be mutated or deleted
  once written; duplicates are detected by content-hash and ignored.
- **Consequences (positive):**
  - Full audit trail exists.
  - Any recommendation can be reconstructed from its DNA record.
  - Regulatory / compliance questions have an evidence base.
- **Consequences (negative):**
  - Storage grows monotonically (currently negligible; requires attention
    at ~10^7 recommendations).
  - No engine currently consumes the DNA store — its value is latent.
    Realising this value is a Phase 2 backlog item (Adaptive Rec
    Engine v1.5).

---

## ADR-010 · Tenant-generic — no hardcoded tickers, sectors, or companies

- **Status:** Accepted (2026 · Phase 1)
- **Context:** AEGIS is built for NexaQuant but must be capable of
  serving different tenants with different universes without a code
  fork per tenant. Hardcoded ticker lists, sector taxonomies, and
  company-specific logic would prevent this.
- **Decision:** No code path hardcodes a ticker, sector name, or
  company. Every such reference reads from a configuration or data
  file at runtime.
- **Consequences (positive):**
  - Any code change immediately benefits all future tenants.
  - Multi-tenancy (a future Enterprise Governance capability) does not
    require a rewrite.
- **Consequences (negative):**
  - Some code is less concise than a hardcoded shortcut would allow.
  - Configuration surface is larger.
- **Alternatives considered:**
  - Fork-per-tenant — rejected as it multiplies maintenance surface.
  - Hardcode current universe, plan to genericise later — rejected
    because "later" rarely arrives once the shortcut is written.

---

## ADR-011 · Delivery layer never mutates state

- **Status:** Accepted (2026 · Phase 1 · UX030 · UX031)
- **Context:** Delivery layers historically become the platform's
  weakest security surface — every message renderer or dashboard
  endpoint that mutates state is another authentication boundary and
  another audit-trail gap.
- **Decision:** The delivery layer (Telegram · Dashboard · any future
  copilot or workspace) reads from `reports/` and produces
  human-facing surfaces only. It never writes to `reports/`, never
  calls engine code, never modifies broker or portfolio state.
- **Consequences (positive):**
  - Delivery-layer bugs cannot corrupt engine outputs.
  - The delivery layer can be rebuilt or replaced without touching
    any engine.
  - Different delivery surfaces (Telegram · web · mobile · voice) all
    see the same underlying evidence.
- **Consequences (negative):**
  - Any user interaction that would naturally mutate state (e.g.,
    "mark this recommendation as reviewed") must go through a
    separate authenticated engine, not the delivery layer.
- **Alternatives considered:**
  - Allow limited annotation from delivery layer — deferred to Phase 3
    under a separate ADR; requires an authenticated write path.

---

## ADR-012 · Six-priority research order

- **Status:** Accepted (2026-07-17)
- **Context:** Without a stated priority order, research proposals get
  evaluated on novelty and impressiveness rather than decision-quality
  impact. This produces a platform with many features that do not
  compound investment returns.
- **Decision:** All research proposals are evaluated against six
  priorities in this order:
  1. Better allocation
  2. Better capital preservation
  3. Better calibration
  4. Better validation
  5. Better expectancy
  6. Better explainability
- **Consequences (positive):**
  - Proposals compete on the right axis.
  - Research resources concentrate on what actually improves decisions.
  - Explainability is deliberately last — important, but subordinated
    to whether the underlying decisions are correct.
- **Consequences (negative):**
  - Some intellectually interesting research (e.g., novel graph
    algorithms) is deferred because it does not clearly serve the
    priorities.
- **Alternatives considered:**
  - Weight-based ranking — rejected as opaque; a strict lexicographic
    order is easier to apply.
  - No priority order — rejected as it produced the problem this ADR
    solves.

---

## ADR-013 · Full metric panel on every experiment

- **Status:** Accepted (2026-07-17)
- **Context:** Optimising a single metric in isolation (e.g., maximise
  Sharpe) reliably regresses others (e.g., drawdown balloons). A
  strategy that looks great on one number and terrible on the rest is
  a well-known institutional failure mode.
- **Decision:** Every experiment reports the full panel:
  - Win Rate · Expectancy · Profit Factor · Avg Win · Avg Loss ·
  - Max Drawdown · Sharpe · Sortino · Calmar ·
  - Stability Score · Calibration Error · Precision@K · Opportunity Cost.
- **Consequences (positive):**
  - Trade-offs are visible.
  - No experiment can hide a regression behind a headline metric.
  - Cross-experiment comparisons are apples-to-apples.
- **Consequences (negative):**
  - Report length grows.
  - Some experiments are marked "improved on X but regressed on Y" —
    the operator must judge the trade-off rather than the code doing
    it silently.

---

## ADR-014 · Never publish to claude.ai Artifacts

- **Status:** Accepted (2026-07-17 · operator instruction)
- **Context:** The Claude Code environment offers an Artifact publish
  tool that surfaces documents on claude.ai. The operator's claude.ai
  account is not their personal account; artifacts published from this
  session appear on a shared / organizational surface that is unwanted.
- **Decision:** No document produced for AEGIS is published to
  claude.ai Artifacts. Deliverables are produced as local files in
  the repository (HTML · PDF · Markdown). PDF is produced directly
  via `reportlab` when required.
- **Consequences (positive):**
  - Documents stay under the operator's control.
  - No leakage into a shared claude.ai surface.
- **Consequences (negative):**
  - No shareable web link produced from a claude.ai artifact URL —
    sharing requires exporting the file explicitly.
- **Alternatives considered:**
  - Publish then delete — rejected because artifacts may be cached,
    indexed, or otherwise persisted before deletion.
  - Publish default-private — rejected because it still leaves the
    artifact on the shared surface.

---

## Reversal & supersession policy

- ADRs are not deleted when reversed. Instead, the status changes to
  `Reversed` and a link to the superseding ADR is added.
- The ID never renumbers. If ADR-003 is reversed, the ID stays at
  ADR-003 and a note points forward.
- New ADRs cite their supersession relationships explicitly.

## When to open a new ADR

- Any change that violates an existing ADR — that violation must open
  a new ADR that supersedes the old.
- Any decision that limits or expands the platform's constitutional
  surface (e.g., "when is execution integration allowed?").
- Any decision the next reader will want to know the reasoning for
  and would otherwise reconstruct from git archaeology.
