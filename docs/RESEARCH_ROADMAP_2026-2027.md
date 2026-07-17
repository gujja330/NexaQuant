# AEGIS Research Roadmap 2026–2027

**Document type:** Master index of the `00_FUNDAMENTAL_RESEARCH` track
**Status:** LIVE INDEX — updated when tracks land or their status changes
**Author:** AEGIS engineering
**Date opened:** 2026-07-17
**Governance:** ARCH002-approved amendment discipline applies to every doc referenced below

---

## 0.  Frame — why this track exists

AEGIS v1 is feature-complete. Continued value now comes from **institutional capabilities**, not more indicators. The user's directive (verbatim excerpts preserved throughout this document as the reference of record):

> "You should build **institutional capabilities**. If I were the CTO of AEGIS, I'd organize the remaining work into **Research Tracks**. Every track produces a design document first, then implementation later. That way, your project folder becomes a long-term blueprint rather than a collection of ad hoc prompts."

**Updated strategic guidance (2026-07-17, second directive):**

> "Based on everything we've built — ARCH001A Constitution, ARCH002-ARCH016 roadmap, RISK001, and the new deep research — I would **not write any more code yet**. You're at the point where **architecture is becoming more important than features**."
>
> "Today AEGIS already has multi-factor ranking, HRP portfolio, risk controller architecture, exit architecture, Telegram, monitoring, CI/CD, governance, research process, constitutional design, capital preservation philosophy. The next leap is no longer 'another indicator.' Instead: add **context-aware intelligence** — sector dynamics, macro context, AI-driven learning, and regime awareness — to improve stock selection and risk management."
>
> "The biggest missing piece: right now AEGIS mostly answers *'Is this stock good?'* Professional funds instead answer *'Is this stock good — given today's market?'* Those are completely different questions."

**Example the operator gave** (Infosys score = 92): before recommending BUY, a professional investor asks — is IT sector strong? Nasdaq falling? USD strengthening? US recession fears? FII selling IT? Earnings season? INR weakening? Tech spending increasing? Same stock, different answer, depending on context. **AEGIS today lacks that context layer.**

> "Therefore I would NOT jump to AI yet. AI without context becomes an overfitting machine. Need: **Context, then AI**."

Three organising principles for this track:

1. **Design first, implement second.** Every ARCH doc is a design deliverable. Implementation is a *separate* work item, gated on: (a) design approval, (b) evidence from a companion RISK/LAB study if quantitative, (c) shadow-mode + paper-trade phases.
2. **Capital-preservation-first ordering.** ARCH002 (Exit) → ARCH003 (Risk Budgeting) → ARCH004 (Position Sizing). Return-optimising tracks come later. This reflects Rule 2 of the AEGIS Constitution: preserve capital before pursuing return.
3. **Context before intelligence.** ARCH017–ARCH025 (Market Intelligence Layer) precede ARCH026–ARCH030 (AI Learning Layer). Sector, macro, regime, dependencies, market memory all built *before* AI is asked to reason about them. This is the second directive above, mechanised.

---

## 1.  Track status board

| ID | Title | Status | Depends on | Design ETA | Impl gate |
|:--|:--|:-:|:--|:-:|:--|
| **ARCH001A** | Investment Philosophy & Decision Theory (**CONSTITUTIONAL**) | 🟢 DRAFT (2026-07-17) | — | done | operator approval |
| **ARCH001** | Recommendation Lifecycle | ✅ DONE | ARCH001A | — | shipped as design |
| **ARCH002** | Exit & Capital-Preservation Framework | 🟢 DRAFT (2026-07-17) | ARCH001A + RISK001-A1 evidence | done | operator approval + RISK001-C |
| **ARCH003** | Enterprise Risk Budgeting | 🟡 SCOPED | ARCH001A + ARCH002 | 2026-Q3 | new evidence study |
| **ARCH004** | Position Sizing | 🟡 SCOPED | ARCH003 | 2026-Q3 | new evidence study |
| **ARCH005** | Portfolio Construction (beyond HRP) | 🟡 SCOPED | ARCH004 | 2026-Q4 | new evidence study |
| **ARCH006** | Regime Intelligence | 🟡 SCOPED | ARCH002 | 2026-Q4 | classifier build |
| **ARCH007** | Uncertainty Quantification | 🟡 SCOPED | ARCH006 | 2027-Q1 | calibration study |
| **ARCH008** | Self-Learning Framework | 🟡 SCOPED | ARCH007, LAB011 | 2027-Q1 | LAB011 shipped |
| **ARCH009** | Model Governance | 🟡 SCOPED | all above | 2027-Q2 | — |
| **ARCH010** | Anti-Fragility | 🟡 SCOPED | ARCH002, ARCH007 | 2027-Q1 | stress-test framework |
| **ARCH011** | Execution Architecture | 🟡 SCOPED | ARCH002, ARCH003 | 2027-Q2 | broker integration decision |
| **ARCH012** | Explainable AI for Investment Decisions | ⚪ BONUS | ARCH008 | TBD | — |
| **ARCH013** | Alternative Data Framework | ⚪ BONUS | ARCH002, ARCH009 | TBD | — |
| **ARCH014** | Scenario & Stress Testing | ⚪ BONUS | ARCH010 | TBD | — |
| **ARCH015** | Evaluation & Benchmarking | ⚪ BONUS | ARCH008, ARCH009 | TBD | — |
| **ARCH016** | Human-in-the-Loop Decision Support | ⚪ BONUS | ARCH009 | TBD | — |
| **ARCH017A** | Market Data Canonical Model (database constitution for Phase 2) | 🟢 DRAFT (2026-07-17) | ARCH001A | done | operator approval |
| **ARCH017** | Global Intelligence Engine | 🟢 DRAFT (2026-07-17) | ARCH001A + ARCH017A + ARCH002 | done | operator approval + ingest scaffolding |
| **ARCH018** | Sector Intelligence Engine | 🟢 DRAFT (2026-07-17) | ARCH017 + ARCH017A | done | operator approval + LAB015-B evidence |
| **ARCH018A** | Company Intelligence Engine | 🟡 SCOPED (2026-07-17) | ARCH018 | 2026-Q3 | new design cycle |
| **ARCH031** | Investment Research Pipeline (academic papers, sell-side, transcripts, regulatory) | 🟡 SCOPED (2026-07-17, operator suggestion) | ARCH026 | 2027-Q2 | separate design cycle |
| **ARCH019** | Regime Detection Engine | 🟡 SCOPED (2026-07-17) | ARCH017, ARCH018 · **subsumes ARCH006** | 2026-Q4 | classifier build |
| **ARCH020** | Market Knowledge Graph | 🟡 SCOPED (2026-07-17) | ARCH017, ARCH018 | 2026-Q4 | graph schema |
| **ARCH021** | Cross-Market Dependency Engine | 🟡 SCOPED (2026-07-17) | ARCH020 | 2027-Q1 | dependency graph validation |
| **ARCH022** | Market Memory Database | 🟡 SCOPED (2026-07-17) | ARCH017 | 2026-Q4 | schema + retention |
| **ARCH023** | Decision Attribution Engine | 🟡 SCOPED (2026-07-17) | ARCH017 + ARCH018 | 2027-Q1 | attribution methodology |
| **ARCH024** | Adaptive Holding Engine | 🟡 SCOPED (2026-07-17) | ARCH019, ARCH022 | 2027-Q1 | RISK004-A evidence |
| **ARCH025** | Adaptive Exit Engine | 🟡 SCOPED (2026-07-17) | ARCH024 · **extends ARCH002** | 2027-Q1 | RISK004-B evidence |
| **ARCH026** | AI Research Assistant (LLM) | 🟡 SCOPED (2026-07-17) | ARCH020, ARCH022 | 2027-Q2 | LLM safety review |
| **ARCH027** | Strategy Doctor (failure analysis) | 🟡 SCOPED (2026-07-17) | ARCH022, ARCH023 · **overlaps ARCH008** | 2027-Q2 | ≥500 closed positions |
| **ARCH028** | Recommendation DNA / Pattern Clustering | 🟡 SCOPED (2026-07-17) | ARCH022, ARCH023 | 2027-Q2 | ≥500 closed positions |
| **ARCH029** | Confidence Calibration | 🟡 SCOPED (2026-07-17) | ARCH023 · **overlaps ARCH007** | 2027-Q2 | calibration study |
| **ARCH030** | Champion vs Challenger Platform | 🟡 SCOPED (2026-07-17) | ARCH023, ARCH029 · **overlaps ARCH008** | 2027-Q2 | shadow-mode discipline |

**Status legend.** ✅ DONE · 🟢 DRAFT delivered · 🟡 SCOPED (this doc has the objectives) · ⚪ BONUS (post-v2) · 🔴 BLOCKED

**Overlaps between ARCH017–030 and the original ARCH003–016 track:**

- **ARCH019 subsumes ARCH006.** ARCH019's taxonomy (Expansion / Recovery / Late Cycle / Recession / Panic / Liquidity Crisis / High Inflation / Disinflation / AI Bubble / Commodity Boom / Election / War / …) is a richer version of ARCH006's Strong/Neutral/Weak/Unknown. On approval, ARCH006 is either retired or renamed to a component of ARCH019.
- **ARCH029 overlaps ARCH007.** Confidence calibration is *one aspect* of uncertainty quantification. ARCH029 is the operational one (calibrated numbers on Telegram); ARCH007 is the full theoretical framing (aleatoric vs epistemic, prediction intervals, conformal prediction). ARCH029 can ship first; ARCH007 remains scoped as the broader framework.
- **ARCH027 + ARCH028 + ARCH030 overlap ARCH008.** Self-learning was originally scoped as ARCH008 (one umbrella doc). The new plan decomposes it into three components: ARCH027 (why did we fail?), ARCH028 (what patterns win vs lose?), ARCH030 (how do we promote a challenger?). ARCH008 is retired in favour of the three components.
- **ARCH025 extends ARCH002.** Not a replacement — the adaptive exit engine sits *on top of* the 9-layer exit framework. When ARCH025 is designed, it will amend ARCH002 §5.L4 (time-decay) and §5.L6 (regime modulator).

---

## 2.  Phase structure (adopted 2026-07-17)

The roadmap now operates as a five-phase maturity ladder. Every ARCH doc belongs to exactly one phase; phases must land in order for the work to compose sensibly.

```
┌───────────────────────────────────────────────────────────────┐
│  PHASE 0  ·  CONSTITUTIONAL                                    │
│  ARCH001A · ARCH001                                            │
│  → Define what "correct" means before optimising for it        │
├───────────────────────────────────────────────────────────────┤
│  PHASE 1  ·  CAPITAL PRESERVATION                              │
│  ARCH002 · ARCH003 · ARCH004                                   │
│  → Stop the losses; size the bets                              │
├───────────────────────────────────────────────────────────────┤
│  PHASE 2  ·  MARKET INTELLIGENCE (context layer)               │
│  ARCH017 · ARCH018 · ARCH019 · ARCH020 · ARCH021 ·             │
│  ARCH022 · ARCH023 · ARCH024 · ARCH025                         │
│  → Answer "is this stock good GIVEN today's market?"           │
├───────────────────────────────────────────────────────────────┤
│  PHASE 3  ·  AI LEARNING LAYER                                 │
│  ARCH026 · ARCH027 · ARCH028 · ARCH029 · ARCH030               │
│  → System learns from its own outcomes, gated by Phase 0-2     │
├───────────────────────────────────────────────────────────────┤
│  PHASE 4  ·  ORCHESTRATION + ADVANCED                          │
│  ARCH005 · ARCH009 · ARCH010 · ARCH011 · ARCH012-ARCH016       │
│  → Portfolio sophistication, governance formalisation,          │
│    anti-fragility, execution, XAI, alt-data, HITL              │
└───────────────────────────────────────────────────────────────┘

  DEFERRED (never enter production without further evidence)
  RL / autonomous AI / self-modifying models
  → require thousands of observations, not the current 285
```

**Why this phase order (operator's rationale, verbatim):**

> "This sequence builds **from information to intelligence**:
> - First, gather **market context** (global, macro, sectors).
> - Then, convert that into **decision context** (regimes, dependencies, attribution).
> - Next, improve **portfolio decisions** (holding, exits).
> - Only after those foundations exist should AI become a learning and research layer."
>
> "That approach aligns with your constitutional principles: capital preservation first, evidence before automation, and operator-controlled evolution. It also minimizes overfitting while creating a platform that can realistically improve over years rather than chasing short-term optimization."

### 2.1  Execution order within phases

```
Phase 0 · CONSTITUTIONAL
  0.a  ARCH001A  Investment Philosophy & Decision Theory       ← delivered 2026-07-17
  0.b  ARCH001   Recommendation Lifecycle                      ← already shipped

Phase 1 · CAPITAL PRESERVATION
  1.a  ARCH002   Exit & Capital-Preservation Framework          ← delivered 2026-07-17
  1.b  ARCH003   Enterprise Risk Budgeting
  1.c  ARCH004   Position Sizing

Phase 2 · MARKET INTELLIGENCE  (the "context layer" — the biggest missing piece)
  2.a0 ARCH017A  Market Data Canonical Model        ← database constitution; must precede ARCH017
  2.a  ARCH017   Global Intelligence Engine         ← delivered 2026-07-17
  2.b  ARCH018   Sector Intelligence Engine         ← "probably the highest ROI research"
  2.c  ARCH019   Regime Detection Engine           (subsumes ARCH006)
  2.d  ARCH020   Market Knowledge Graph
  2.e  ARCH021   Cross-Market Dependency Engine
  2.f  ARCH022   Market Memory Database
  2.g  ARCH023   Decision Attribution Engine
  2.h  ARCH024   Adaptive Holding Engine
  2.i  ARCH025   Adaptive Exit Engine              (extends ARCH002)

Phase 3 · AI LEARNING LAYER
  3.a  ARCH026   AI Research Assistant (LLM for notes, NOT decisions)
  3.b  ARCH027   Strategy Doctor (failure analysis)      (component of retired ARCH008)
  3.c  ARCH028   Recommendation DNA (pattern clustering)  (component of retired ARCH008)
  3.d  ARCH029   Confidence Calibration                    (subset of ARCH007)
  3.e  ARCH030   Champion vs Challenger Platform            (component of retired ARCH008)

Phase 4 · ORCHESTRATION + ADVANCED
  4.a  ARCH005   Portfolio Construction (beyond HRP)
  4.b  ARCH009   Model Governance
  4.c  ARCH010   Anti-Fragility
  4.d  ARCH011   Execution Architecture
  4.e  ARCH012–ARCH016 (advanced differentiators; explainability, alt-data, stress
       testing, evaluation, HITL)

DEFERRED (do NOT enter production without further evidence)
  - Reinforcement Learning for stop placement
  - Autonomous AI (self-modifying models)
  - Fully-automated broker execution
```

**Priority rationale (from ARCH001A commissioning message).** *"Without ARCH001A, later research risks optimizing for conflicting goals."* The Constitution defines what "correct" means; without it, every downstream document must re-litigate first principles.

**Priority rationale (from 2026-07-17 second directive).** *"AI without context becomes an overfitting machine. Need: Context, then AI."* This is why Phase 2 (Market Intelligence) precedes Phase 3 (AI Learning). AEGIS has 285 closed positions today; automating learning against that few observations is guaranteed overfitting. Phase 2 gives the system enough *conditioning variables* that when Phase 3 arrives, the learning has structural scaffolding.

---

## 3.  Per-track scoping

Each subsection below is the seed for the eventual full design document. It captures: objective · key research topics · deliverable structure · dependencies · non-goals. A future working session can pick any one of these and produce the full ARCH-doc following the ARCH002 template shape.

### 3.0  ARCH001A — Investment Philosophy & Decision Theory  ✅ DRAFT DELIVERED 2026-07-17 · CONSTITUTIONAL APEX

Full document at [`docs/ARCH001A_INVESTMENT_PHILOSOPHY.md`](ARCH001A_INVESTMENT_PHILOSOPHY.md). Summary:

- **The Constitution of AEGIS** — 10 Articles: Mission · Investment · Decision · Research · Learning · Risk · Operational · Ethics · Governance · Amendments
- Philosophical foundations distilled from Buffett, Munger, Marks, Dalio, Taleb, Simons, Asness, Thorp, Kelly, Kahneman-Tversky, Thaler, Markowitz, Knight, von Neumann-Morgenstern, and the robust-decision literature
- Fundamental definitions: risk = *permanent capital loss*, not volatility (Article II)
- **Objective function chosen:** `maximise E[log W]` subject to `P(ruin ≤ 1%)` and `Max DD ≤ 20%` and Article VI Rules 1-10, at fractional Kelly ≤ 0.25 per position
- **6-tier decision hierarchy:** Protect Capital → Preserve Optionality → Reduce Tail Risk → Maintain Liquidity → Exploit Edge → Increase Returns
- **10 INVARIANT non-negotiables** that require Constitution retirement to amend
- Trade-off resolution matrix (§6) — 11 tensions with declared winners
- Ethics framework (Article VIII) — transparency, explainability, operator override, AI autonomy floor, calibrated confidence, failure honesty
- Amendment discipline (Article X)

**Status.** DRAFT pending operator approval. Once approved, this document becomes the constitutional apex — every other ARCH / RISK / LAB / OPS / MON doc inherits from it.

---

### 3.1  ARCH002 — Exit & Capital-Preservation Framework  ✅ DRAFT DELIVERED 2026-07-17

Full document at [`docs/ARCH002_EXIT_FRAMEWORK.md`](ARCH002_EXIT_FRAMEWORK.md). Summary:

- 9-layer priority-ordered architecture (L0 admission → L8 kill switch)
- Institutional survey (Renaissance, Two Sigma, AQR, Citadel, Man AHL, Bridgewater, WorldQuant, Jane Street, CTA consensus, academic literature)
- 5-action Risk Controller (EXIT / REDUCE / TRAIL / HEDGE / NO-OP)
- Capital Preservation Engine (12 observers)
- Self-learning engine (post-mortem schema + statistical hygiene)
- v1 → v1.1 → v2 → v3 rollout roadmap

**Status.** DRAFT pending operator approval + RISK001-A1 primary-metric decision.

---

### 3.2  ARCH003 — Enterprise Risk Budgeting

**Objective.** Design an institutional-grade risk budgeting framework that answers "how much capital can any position, sector, factor, or portfolio-level exposure lose in a day / week / month before automatic action is taken?"

**Key research topics.**
- Kelly Criterion (Kelly 1956) and Fractional Kelly (Thorp)
- Risk Parity (Bridgewater All Weather; Roncalli & Weisang)
- Equal Risk Contribution (Maillard, Roncalli, Teiletche)
- Conditional Value-at-Risk (Rockafellar & Uryasev 2000)
- Expected Shortfall vs VaR (Artzner et al. 1999 — coherent risk measures)
- Volatility targeting (AQR, Man AHL practice)
- Tail-risk allocation (Ang, Chen & Xing)
- Time-scaled budgets: daily loss budget / weekly / monthly / annual DD

**Deliverable — `docs/ARCH003_RISK_BUDGETING.md`.**
Sections: (0) preamble & non-negotiables · (1) mission — what "budget" means · (2) 5 nested budgets (position / sector / factor / portfolio / firm) · (3) time horizons and how they compose · (4) fractional-Kelly framing · (5) CVaR-95 as the working risk measure · (6) breach behaviour (soft warn → reduce → hard stop) · (7) integration with ARCH002 layers · (8) rollout · (9) non-goals · (10) integrity.

**Dependencies.** ARCH002 (Layer 7 references L7.b CVaR; ARCH003 defines it fully).

**Non-goals.** Kelly at full leverage (never in cash-equity). Firm-level risk (out of scope until firm structure exists).

**Companion evidence study.** RISK002-A — apply candidate budget structures to the 285-position AEGIS history, measure would-be breaches, decide adoption criteria.

---

### 3.3  ARCH004 — Position Sizing

**Objective.** Formalise how AEGIS decides "5% weight vs 10% vs 15%" for a given position. Currently weights are HRP-driven with `name_cap=0.30`. That's one input; ARCH004 defines the *full* sizing decision.

**Key research topics.**
- Fixed-fraction sizing (baseline)
- Kelly / fractional-Kelly on estimated edge
- ATR-based sizing (target risk per position = fixed ₹, size = risk_budget / (ATR × mult))
- Conviction-weighted sizing (weight ∝ score × confidence)
- Bayesian sizing (posterior over edge → posterior over weight)
- Volatility-scaled sizing (size ∝ 1/vol so per-position risk contribution is equal)
- Dynamic allocation as conviction shifts (mid-life resizing — or not; ARCH002 says not)

**Deliverable — `docs/ARCH004_POSITION_SIZING.md`.**
Sections: (0) preamble · (1) mission — what sizing solves that entry doesn't · (2) survey of 6 approaches with pros/cons · (3) proposed AEGIS default (fractional-Kelly clamped to `[2%, 12%]` per position, modulated by confidence) · (4) interaction with HRP · (5) mid-life resize policy (per ARCH002: no) · (6) rollout · (7) non-goals · (8) integrity.

**Dependencies.** ARCH003 (defines per-position budget in ₹).

**Companion evidence study.** RISK003-A — replay 285 positions with each sizing approach, measure portfolio-level Sharpe / Ulcer / max DD.

---

### 3.4  ARCH005 — Portfolio Construction (beyond HRP)

**Objective.** Compare Hierarchical Risk Parity (currently in AEGIS) against alternatives and decide whether/when to move beyond HRP.

**Key research topics.**
- HRP (Marcos López de Prado 2016)
- HERC (Hierarchical Equal Risk Contribution)
- Black-Litterman (subjective views + prior)
- Mean-variance (Markowitz 1952) with shrinkage (Ledoit-Wolf)
- CVaR-optimisation (minimise ES rather than variance)
- Equal-Risk-Contribution (Maillard-Roncalli-Teiletche)
- Risk Parity (Bridgewater)
- Maximum Diversification (Choueifaty-Coignard)
- Factor-neutral construction (Fama-French / Carhart)

**Deliverable — `docs/ARCH005_PORTFOLIO_CONSTRUCTION.md`.**
Sections: (0) preamble · (1) why HRP is the default · (2) alternatives and their failure modes · (3) comparison matrix (Sharpe stability, tail behaviour, turnover, transparency, data needs) · (4) proposed multi-method ensemble · (5) rollout · (6) non-goals.

**Dependencies.** ARCH003 + ARCH004.

**Companion evidence study.** LAB012-A — replay AEGIS universe under each method; compare 5-year Sharpe / Ulcer / max-DD.

---

### 3.5  ARCH006 — Regime Intelligence

**Objective.** Design the regime-detection subsystem that ARCH002-L6 consumes. Currently AEGIS has a simple Strong/Neutral/Weak label; this doc formalises how it should be produced and how downstream layers should react.

**Key research topics.**
- Hidden Markov Models for regime detection (Baum-Welch, Viterbi)
- Bayesian change-point detection (Adams-MacKay 2007)
- Macro regimes (Yield-curve inversion, credit spreads)
- Liquidity regimes (ADV, bid-ask, market impact)
- Volatility regimes (VIX / India VIX)
- Credit regimes (CDS spreads — India CDS or IGB spreads)
- Breadth (advance-decline, new-highs / new-lows)
- Market internals (sector rotation velocity, factor momentum)

**Deliverable — `docs/ARCH006_REGIME_INTELLIGENCE.md`.**
Sections: (0) preamble · (1) 7 regime archetypes (Bull / Bear / Sideways / Crisis / Recovery / Euphoria / Capitulation) with signature features · (2) proposed multi-model ensemble (HMM + change-point + rules) · (3) confidence output (not just label) · (4) how ARCH002 layers consume regime state · (5) failure modes (misclassification, latency, over-fitting) · (6) rollout · (7) non-goals.

**Dependencies.** ARCH002 L6 (this doc formalises what ARCH002 already assumes).

**Companion build.** `research/regime_classifier/` — new subsystem, isolated from production until validated.

---

### 3.6  ARCH007 — Uncertainty Quantification

**Objective.** Formalise how AEGIS represents and propagates uncertainty. Move from point-estimates (score=87) to distributions (posterior mean 87, 95% CI [72, 94]).

**Key research topics.**
- Bayesian models (posterior distributions on parameters)
- Monte-Carlo methods (bootstrap; MCMC where relevant)
- Conformal prediction (Vovk, Gammerman, Shafer)
- Prediction intervals (frequentist)
- Calibration (Platt scaling, isotonic regression)
- Brier score (Brier 1950)
- Expected Calibration Error
- Aleatoric vs Epistemic uncertainty (Der Kiureghian & Ditlevsen)
- Bayesian ensembling (deep ensembles as approximation)

**Deliverable — `docs/ARCH007_UNCERTAINTY.md`.**
Sections: (0) preamble · (1) two kinds of uncertainty · (2) what AEGIS currently exposes (point estimates) · (3) target state (calibrated intervals) · (4) when should the system say "I don't know" (Rule 8 mechanised) · (5) how uncertainty should reduce exposure (weight = base_weight × (1 − epistemic_uncertainty)) · (6) rollout · (7) non-goals.

**Dependencies.** ARCH006 (regime uncertainty feeds this).

**Companion evidence study.** LAB013-A — measure current confidence calibration on 285 positions; produce Brier score + reliability diagram.

---

### 3.7  ARCH008 — Self-Learning Framework

**Objective.** Design how AEGIS improves from its own outcomes without overfitting to short samples.

**Key research topics.**
- Online learning (SGD-style parameter updates)
- Concept drift detection (ADWIN, DDM, Page-Hinkley)
- Meta-learning (MAML, Reptile)
- Continual learning (elastic weight consolidation)
- Shadow / champion-challenger models
- Automatic evaluation loops
- A/B testing discipline for models
- Sample-size minima and multiple-testing corrections

**Deliverable — `docs/ARCH008_SELF_LEARNING.md`.**
Sections: (0) preamble · (1) what "learning" means and does NOT mean (not retraining on same data) · (2) two learning surfaces: calibration (fast) vs parameter (slow) · (3) shadow-model discipline · (4) champion-challenger promotion criteria · (5) drift detection and rollback · (6) rollout · (7) non-goals.

**Dependencies.** ARCH007 + LAB011 (Outcome Intelligence must exist for outcomes to feed back).

**Companion build.** New track `research/self_learning/`.

---

### 3.8  ARCH009 — Model Governance

**Objective.** Formalise the process by which any model / parameter / policy is proposed, evaluated, approved, promoted, monitored, and rolled back.

**Key research topics.**
- Model registry (MLflow, W&B, or in-repo YAML)
- Versioning strategies (semver for models; hash-based content addressing)
- Promotion criteria (metrics + statistical significance)
- Rollback criteria (drift, degradation)
- Evidence gates (which studies must be run before promotion)
- Approval workflows (who signs off — solo vs committee vs automated)
- Audit trail (immutable log of every change)
- Compliance considerations (SEBI, tax, KYC)
- Research governance (pre-registration, HARKing discipline)
- Production governance (canary rollout, kill switches)
- Experiment governance (multiple testing, sample size)

**Deliverable — `docs/ARCH009_MODEL_GOVERNANCE.md`.**
Sections: (0) preamble · (1) three governance surfaces (research / production / experiments) · (2) proposed model-registry structure · (3) promotion criteria per surface · (4) rollback triggers · (5) audit trail schema · (6) roles and approvals · (7) rollout · (8) non-goals.

**Dependencies.** ARCH002 amendment discipline is a subset of this; ARCH008 shadow-model discipline is a subset.

---

### 3.9  ARCH010 — Anti-Fragility

**Objective.** Design AEGIS to become *stronger* after stress events, not just to survive them. Taleb's framing.

**Key research topics.**
- Taleb — "Antifragile: Things That Gain from Disorder" (2012)
- Black Swan tail-risk protection
- Stress testing (Fed CCAR; European EBA; academic literature)
- Chaos engineering (Netflix Chaos Monkey; SRE practice)
- Fault injection at every layer
- Circuit breakers (already in ARCH002-L8)
- Kill switches (already in ARCH002)
- Graceful degradation (reduced-service modes)
- Post-incident learning (blameless post-mortems)

**Deliverable — `docs/ARCH010_ANTIFRAGILITY.md`.**
Sections: (0) preamble · (1) fragile vs robust vs antifragile · (2) 5 stress scenarios AEGIS must survive daily (crash, API outage, bad model, data corruption, false signal) · (3) chaos-engineering discipline (weekly randomised failure injection) · (4) reduced-service modes (data outage → hold; model outage → freeze; broker outage → alert) · (5) blameless post-mortem template · (6) how each incident makes the system stronger (specific mechanism) · (7) rollout · (8) non-goals.

**Dependencies.** ARCH002 (kill switch), ARCH007 (uncertainty in stress scenarios).

**Companion build.** `research/chaos/` — fault-injection test framework.

---

### 3.10  ARCH011 — Execution Architecture

**Objective.** Design the layer that converts recommendations into actual trades: broker integration, order types, execution algorithms, slippage estimation.

**Key research topics.**
- Transaction Cost Analysis (Kissell, Almgren-Chriss)
- Slippage models (linear, square-root, Almgren-Chriss)
- Liquidity (ADV, market impact estimation)
- Gap risk (already touched in ARCH002-L1.b)
- Order types (MKT, LMT, MOO, MOC, IOC, GTD)
- VWAP execution (twap, sniper algo)
- TWAP execution
- Execution quality metrics (implementation shortfall)
- Market impact (temporary vs permanent)
- Partial fills (repricing strategy)
- Broker selection (Zerodha, Upstox, Angel, IIFL — Indian brokers)

**Deliverable — `docs/ARCH011_EXECUTION.md`.**
Sections: (0) preamble · (1) v1 assumption (operator manually executes; no broker integration) · (2) what "paper-trade mode" means in ARCH002 · (3) execution simulator design · (4) real-broker integration roadmap · (5) order-type decision tree · (6) VWAP / TWAP for larger positions · (7) partial-fill policy · (8) rollout · (9) non-goals.

**Dependencies.** ARCH002, ARCH003.

**Companion build.** `research/execution_simulator/` — for paper-trade phase of ARCH002 rollout.

---

### 3.11  ARCH012 – ARCH016 (bonus tracks)

**ARCH012 — Explainable AI for Investment Decisions.** How to expose "why did you recommend X?" to the operator in a way that is honest, actionable, and not overwhelming. Research: SHAP, LIME, integrated gradients, counterfactuals, natural-language explanation. Deliverable: `docs/ARCH012_XAI.md`.

**ARCH013 — Alternative Data Framework.** Evaluate news sentiment, insider activity, options flow (OI, PCR), satellite imagery, ESG signals. Governance around use (leakage, licensing, cost, decay). Deliverable: `docs/ARCH013_ALTERNATIVE_DATA.md`.

**ARCH014 — Scenario & Stress Testing.** Formalise the 5 historical shock scenarios ARCH002-§8.1 mentions. Add hypothetical shocks (30% rupee devaluation, oil spike, geopolitical event). Deliverable: `docs/ARCH014_STRESS_TESTING.md`.

**ARCH015 — Evaluation & Benchmarking.** How AEGIS measures itself over years. Risk-adjusted metrics (Sharpe, Sortino, Calmar, MAR, Ulcer), calibration, benchmark comparisons (Nifty 50, Nifty 200), statistical significance. Deliverable: `docs/ARCH015_EVALUATION.md`.

**ARCH016 — Human-in-the-Loop Decision Support.** Where operator review adds value; where automation is appropriate; how overrides are logged and audited. Deliverable: `docs/ARCH016_HITL.md`.

---

### 3.11a  ARCH017A — Market Data Canonical Model  ✅ DRAFT DELIVERED 2026-07-17  (Phase 2 gate)

Full document at [`docs/ARCH017A_MARKET_DATA_CANONICAL_MODEL.md`](ARCH017A_MARKET_DATA_CANONICAL_MODEL.md). Summary:

- The **database constitution** for the Market Intelligence Layer. Every field name, timestamp convention, confidence value, and missing-data behaviour used by ARCH017-030 comes from this document.
- **8 entity classes**: RawObservation · DerivedMetric · NormalizedIndicator · Classification · CompositeScore · RegimeState · Dependency · MemorySnapshot
- **Confidence is a first-class field** on every derived entity, computed from 4 components (source × freshness × completeness × agreement)
- **Missing-data behaviour formalised** — never silently substituted; explicit `Unknown` / `NotFound` / `feed_outage`
- **Versioning discipline** — schema, formulas, weightings, code SHA all frozen per row
- **Fail-loud principle** — outages produce explicit events, not stale reads
- **Full compliance matrix** with ARCH001A Articles I, II, IV, V, VII, VIII

**Status.** DRAFT / v0.9 pending operator approval. Insertion at position 0 of Phase 2 (must precede ARCH017 approval).

**Amendment discipline.** Any downstream ARCH doc that needs a new variable, unit, source, or entity class amends this document first via §14.

---

### 3.12  ARCH017 — Global Intelligence Engine  ✅ DRAFT DELIVERED 2026-07-17  (Phase 2 · **operator's named next priority**)

Full document at [`docs/ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md`](ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md). Summary:

- **The missing top half of AEGIS.** Adds Global / Macroeconomy / Country tiers above AEGIS's existing Sector / Company / Portfolio tiers.
- **~60 variables inventoried** across 11 tiers: global equities, volatility, currencies, commodities, rates, macro, central-bank, flow (FII/DII), breadth, liquidity proxies, India domestic markers. All registered against ARCH017A §4.4 variable catalogue.
- **~35 DerivedMetrics** (2s10s slope, VIX MA, DXY MA, real yields, momentum blocks, breadth, FII flow rolling sums, etc.)
- **~25 NormalizedIndicators** on the [0, 100] scale — direction: higher = more risk-on
- **5 Classifications**: `global_posture` (Risk-On/Off/Rotating/Neutral/Unknown) · `liquidity` · `usd` · `vol_regime` · `rates`
- **4 CompositeScores**: `global_risk` · `macro` · `liquidity` · `usd`
- **Output contract**: daily bundle at 08:30 IST (pre-open) with `contributions.global_risk_top5` for explainability. **Never emits BUY/SELL/EXIT** — only context.
- **Consumer list**: ARCH018/019/020/021/022/023/024/025/026 + optional consumption by the recommendation engine (advisory-only hints; sealed core untouched)
- **Rollout plan**: design → ingest scaffolding → backfill → shadow publish (4 weeks) → advisory consumer integration → live only after RISK001-C ships.

**Objective.** Answer "*what is the state of the global environment today?*" as a daily input to every AEGIS decision.

**Why now.** AEGIS today makes buy/hold/sell decisions in isolation from global context. A recommendation to buy an Indian IT name is uninformed if it doesn't consider: Nasdaq direction, USD strength, US recession signals, FII flows in IT, US tech-spending trend, INR pressure. Same stock, same score — different correct answer.

**Daily-computed inputs to collect:**

- **Cross-border equity indices:** S&P 500, Nasdaq 100, Dow, FTSE, Nikkei, Hang Seng, SSE Composite, DAX, CAC
- **Volatility indices:** VIX (US), VNKY (Japan), India VIX (feeds MON001 already)
- **Currencies:** DXY (dollar index), INR/USD, EUR/USD, JPY/USD, CNY/USD
- **Commodities:** Brent, WTI, gold, silver, copper
- **Rates:** US 10Y, US 2Y, US-2s10s slope, India 10Y G-sec, RBI policy rate
- **Macro:** US PMI (mfg + services), US CPI, India CPI, India WPI, India IIP
- **Central bank action:** Fed dots, Fed statement sentiment (NLP), RBI MPC minutes
- **Flow:** FII/DII cash market data, FPI debt flows, MF equity inflows
- **Sentiment/liquidity:** SGX Nifty (pre-market), Asian markets overnight, US futures

**Output shape:**

```
Global Risk Regime  =  {Risk-On / Risk-Off / Rotating / Neutral}
Global Risk Score   =  0–100
Contributions       =  {equities: 22, rates: 15, DXY: 12, oil: −8, VIX: −5, ...}
Confidence          =  {high / medium / low}
```

**Deliverable — `docs/ARCH017_GLOBAL_INTELLIGENCE.md`.**
Sections: (0) preamble · (1) motivation (the Infosys-in-context example) · (2) data-source catalogue · (3) refresh cadence per input (some daily, some weekly, some quarterly) · (4) latency & failure handling (per Rule 8: uncertainty → reduce) · (5) output schema · (6) integration points (feeds ARCH018 sector, ARCH019 regime, ARCH020 knowledge graph) · (7) tenant-generic discipline (no hardcoded macro thresholds) · (8) rollout · (9) non-goals · (10) integrity.

**Dependencies.** ARCH001A (compliance), ARCH002 (feeds L6 regime modulator).

**Companion build.** `research/global_intelligence/` — data-collection scripts read-only wrt production.

---

### 3.13  ARCH018 — Sector Intelligence Engine  (Phase 2 · **"probably the highest ROI research"**)

**Objective.** For every sector in the AEGIS universe, compute a daily sector-strength score that combines relative strength, momentum, volume, breadth, capital flow, sector-specific earnings tone.

**Why highest ROI.** Once AEGIS knows a sector is weak, it can *stop recommending stocks in that sector*, or reduce their weights. Sector state affects far more decisions than any single-stock indicator. Institutional funds compute sector strength constantly.

**Metrics per sector (daily):**

- **Relative strength** vs Nifty (10d, 30d, 90d, 200d)
- **Momentum** (rate of change, sector index MACD)
- **Volume** (relative to 30d average)
- **Breadth** (% of sector names above 200-DMA)
- **Earnings tone** (last N quarters of sector aggregate EPS surprise)
- **Sector leadership rotation** (is this sector leading or lagging peer sectors?)
- **Capital flow** (FII/DII sector-cash positioning)
- **Sector volatility** (30-day realised)
- **Sector-specific macro drivers** (e.g. IT ↔ USD, Auto ↔ commodity prices, Financials ↔ credit spreads)
- **Sector confidence** (0-100 composite)

**Output shape:**

```
Sector       Score   Regime       Drivers
IT           88      Bullish      Nasdaq+, USD+, FII buying
Financials   42      Neutral      credit spreads flat, breadth ok
Pharma       95      Strong       earnings surprises, sector RS elevated
Auto         38      Weak         volume falling, sector breadth <30%
```

**Integration with stock scoring:**

```
Final score  =  Stock alpha score  ×  Sector score  (or additive blend, TBD)
```

**Deliverable — `docs/ARCH018_SECTOR_INTELLIGENCE.md`.**
Sections: (0) preamble · (1) motivation · (2) sector taxonomy (tenant-generic; sector map lives in ClientProfile equivalent) · (3) daily metrics per sector · (4) sector-score composite formula · (5) integration with existing stock scoring · (6) sector-conditional exit rules (feeds ARCH024/025) · (7) failure modes (single-name dominance in a sector; sector reclassification) · (8) rollout · (9) non-goals · (10) integrity.

**Dependencies.** ARCH017 (macro drivers), ARCH001A.

**Companion evidence study.** LAB014-A — backtest sector-conditional stock scoring on 285 positions. Does multiplying stock score by sector score improve realised P&L per unit of turnover?

---

### 3.14  ARCH019 — Regime Detection Engine  (Phase 2 · **subsumes ARCH006**)

**Objective.** Detect and label the current market regime along a richer taxonomy than Strong/Neutral/Weak. Regime affects entry, exit, holding period, sizing, sector allocation.

**Regime taxonomy (proposed):**

- Expansion
- Recovery
- Late Cycle
- Recession
- Panic
- Liquidity Crisis
- High Inflation
- Disinflation
- AI Bubble
- Commodity Boom
- Election Volatility
- War / Geopolitical Shock

**Methods to combine:**

- Hidden Markov Model (Baum-Welch on multi-input feature vector)
- Bayesian change-point detection (Adams-MacKay 2007)
- Rule-based overlays (specific macro thresholds → specific regime labels)
- Historical analogue matching (feeds ARCH022 Market Memory)

**Regime-conditional overrides per ARCH001A §4.3:**

- Kelly fraction (Strong=0.25 → Unknown=0.05)
- Hard stop tightness (Weak → tighter; Strong → wider)
- Holding horizon (Strong trending → extend; Panic → shorten)
- Sector allocation (Late Cycle → defensive rotation; Recovery → cyclical)

**Deliverable — `docs/ARCH019_REGIME_DETECTION.md`.**
Sections: (0) preamble · (1) motivation and taxonomy · (2) HMM design · (3) change-point overlay · (4) rule-based fallback (Rule 8 fail-safe) · (5) regime-conditional actions across ARCH002/018/024/025 · (6) failure modes (regime misclassification, latency, over-fitting to recent history) · (7) rollout · (8) non-goals · (9) integrity.

**Dependencies.** ARCH017 (macro inputs), ARCH018 (sector state), ARCH001A.

**Retires.** ARCH006 (Regime Intelligence) folds into ARCH019 as a subset.

---

### 3.15  ARCH020 — Market Knowledge Graph  (Phase 2)

**Objective.** Represent the causal / correlational relationships between macro inputs, sectors, industries, and stocks as a directed graph. Enable *graph reasoning* instead of *point reasoning*.

**Example graph edges (operator-provided):**

```
Oil ↑  →  Energy sector ↑  →  ONGC / IOC / BPCL ↑
Oil ↑  →  Paints ↓  (input cost pressure)
Oil ↑  →  Airlines ↓
Oil ↑  →  Tyres ↓  (natural rubber input)
Oil ↑  →  Asian Paints ↓
```

**Node types.**

- Macro variables (Oil, USD, US10Y, VIX, Nasdaq, FII flow)
- Sectors (IT, Financials, Auto, …)
- Industries (2W-Auto, 4W-Auto, Cement, Housing Finance, …)
- Stocks (SIEMENS, INFY, RELIANCE, …)

**Edge types.**

- Correlation (rolling; time-scoped)
- Causal (economic reasoning; hand-curated + LLM-proposed)
- Regime-conditional (edge weight depends on ARCH019 state)

**Deliverable — `docs/ARCH020_KNOWLEDGE_GRAPH.md`.**
Sections: (0) preamble · (1) motivation · (2) node + edge taxonomy · (3) graph schema (property graph vs RDF) · (4) how the graph is populated (correlation estimation + expert curation + LLM proposal + governance approval) · (5) query patterns (given macro shock X, which stocks are 2-hop affected?) · (6) integration with ARCH021 (dependency traversal) · (7) versioning + amendment · (8) rollout · (9) non-goals.

**Dependencies.** ARCH017, ARCH018, ARCH001A.

---

### 3.16  ARCH021 — Cross-Market Dependency Engine  (Phase 2)

**Objective.** Given a market event, traverse the knowledge graph to identify which AEGIS positions are affected, and by how much. Enables portfolio-level dependency-aware risk.

**Example.**

```
Event:   US Nasdaq −3% overnight
Traverse: Nasdaq → Indian IT sector → Infosys (portfolio position)
Impact:   High confidence dependency; Infosys typically −1.5% next session
Action:   Reduce Infosys weight or tighten stop pre-market
```

**Method.** Weighted graph traversal (BFS with edge-weight product), with a confidence threshold. Only high-confidence paths inform action; low-confidence paths are logged as diagnostic only.

**Deliverable — `docs/ARCH021_DEPENDENCY_ENGINE.md`.**
Sections: (0) preamble · (1) motivation · (2) traversal algorithm · (3) confidence scoring · (4) action mapping (High confidence + adverse → REDUCE; medium → tighten stop; low → log only) · (5) integration with ARCH002 layers · (6) failure modes (spurious correlations, non-stationarity of edges) · (7) rollout · (8) non-goals.

**Dependencies.** ARCH020, ARCH001A.

---

### 3.17  ARCH022 — Market Memory Database  (Phase 2 · long-term high-value asset)

**Objective.** Persist every trading day's complete market state so that future AEGIS can ask "*today looks 92% similar to October 2022 — what happened next?*" This is the compounding asset that pays off after 5+ years.

**Per-day snapshot schema.**

- All ARCH017 global inputs (macro, currencies, commodities, rates)
- All ARCH018 sector scores
- ARCH019 regime label + confidence
- Portfolio state (holdings, weights, unrealised P&L, exposure by sector)
- Recommendations issued (with attribution — ARCH023)
- News events flagged (ARCH026 output)
- Outcomes observed (for positions maturing today)

**Retention.** Indefinite. This is the historical memory; deletion is not authorised.

**Similarity search.** Given today's snapshot, find the top-N most similar historical snapshots (cosine / Mahalanobis / learned embedding). Return their forward outcomes as reference — *not as prediction*.

**Deliverable — `docs/ARCH022_MARKET_MEMORY.md`.**
Sections: (0) preamble · (1) motivation ("professional funds build this") · (2) snapshot schema · (3) storage (parquet by month; compressed) · (4) retention & governance · (5) similarity metrics · (6) reference-output UX ("today is closest to 2022-10-14"; NOT a forecast) · (7) integration with ARCH019 (regime-analogue enrichment) · (8) rollout · (9) non-goals (this is memory, not a predictor).

**Dependencies.** ARCH017, ARCH018, ARCH019.

---

### 3.18  ARCH023 — Decision Attribution Engine  (Phase 2)

**Objective.** For every recommendation, decompose the score into its contributing factors so the operator can see *why* — quantitatively.

**Attribution shape (operator-provided example).**

```
Recommendation: INFY  score 87
Attribution:
  Momentum       32%
  Sector         18%
  Macro          15%
  Quality        12%
  Valuation       8%
  Liquidity       6%
  News            5%
  Other           4%
```

**Method.** Shapley values on the composite score. For each factor, measure its marginal contribution by ablation (compute the score without that factor, take the delta). Aggregate across all orderings for a fair attribution.

**Deliverable — `docs/ARCH023_DECISION_ATTRIBUTION.md`.**
Sections: (0) preamble · (1) motivation (explainability is Article VIII clause 8.2) · (2) Shapley-value framework · (3) computational cost (2ⁿ orderings; sampling approximations) · (4) presentation (Telegram footer, dashboard, audit trail) · (5) integration with ARCH029 confidence calibration · (6) failure modes (correlated factors, orderings dependence) · (7) rollout · (8) non-goals.

**Dependencies.** ARCH017 + ARCH018 (factor inputs), ARCH001A Article VIII.

---

### 3.19  ARCH024 — Adaptive Holding Engine  (Phase 2)

**Objective.** Replace the static `HOLD=63` with a regime-and-context-adaptive holding decision.

**Rules (operator-provided sketch).**

- Market Strong + Sector strengthening + Stock leading → *extend hold*
- Market Weak → *shorten hold* (fewer days to expiry)
- Sector weakening → *reduce weight* (not necessarily exit)
- Macro deteriorating → *tighten trail* (Article II Rule 6)
- Stock still strongest in sector → *keep holding* even past nominal HOLD

**Constraint.** ARCH001A Article VI Rule 9 (Time horizon is real): do not liquidate a long-term position for a short-term movement unless a hard rule fires. Adaptive holding *extends* or *shortens* the intended horizon; it does not override L1 hard stops.

**Deliverable — `docs/ARCH024_ADAPTIVE_HOLDING.md`.**
Sections: (0) preamble · (1) motivation · (2) decision matrix (regime × sector × stock-strength → action) · (3) constraints (Rules 6, 9) · (4) evidence gate (RISK004-A on 285 positions) · (5) rollout · (6) non-goals.

**Dependencies.** ARCH019 (regime), ARCH018 (sector), ARCH022 (memory for analogues), ARCH001A.

**Companion evidence study.** RISK004-A — replay 285 positions with adaptive holding; compare vs fixed 63d.

---

### 3.20  ARCH025 — Adaptive Exit Engine  (Phase 2 · **extends ARCH002**)

**Objective.** Extend ARCH002's 9-layer framework with an adaptive-decision node that consults ARCH019 (regime), ARCH018 (sector), and ARCH022 (memory) at every bar.

**5-decision extension (operator-provided).**

```
For each open position:
  Capital-preservation check    →  ARCH002 L1/L2 (unchanged)
  Profit-protection check       →  ARCH002 L3 (unchanged)
  Thesis check                  →  is entry rationale still valid? (ARCH023 attribution recomputed)
  Opportunity check             →  is there a much better use of the capital? (ARCH017-020)
  Rotation check                →  ARCH002 L4/L5 (unchanged, but gated on capital state)
```

**Alignment with ARCH001A.** The 5-decision structure preserves the 6-tier Decision Hierarchy (§5): Capital → Optionality → Tail → Liquidity → Edge → Return. Rotation (Opportunity/Rotation checks) is subordinate to Capital and Profit protection.

**Deliverable — `docs/ARCH025_ADAPTIVE_EXIT.md`.**
Sections: (0) preamble · (1) motivation · (2) 5-decision framework · (3) amendments to ARCH002 §5 (L4 + L6) · (4) evidence gate (RISK004-B) · (5) rollout · (6) non-goals.

**Dependencies.** ARCH024, ARCH002, ARCH001A.

**Companion evidence study.** RISK004-B — same universe, adaptive vs current exit; measure DD, MFE preservation, turnover.

---

### 3.21  ARCH026 — AI Research Assistant  (Phase 3 · **notes only, not decisions**)

**Objective.** Use an LLM to *read and summarise* macro data, news, earnings transcripts, sector reports, and produce **research notes** — not trading decisions.

**Constraints (from ARCH001A Article VIII).**

- LLM output is *advisory* — never triggers a trade
- Every LLM claim is cited (source URL, timestamp, snippet)
- LLM confidence is calibrated separately from AEGIS confidence
- LLM output feeds ARCH017 macro sentiment and ARCH018 sector news, does not directly move any weight

**Use cases.**

- Daily macro-note synthesis (Fed watch, RBI watch, geopolitical)
- Sector-tone summaries after major sector news
- Earnings-transcript extraction for holdings (management guidance changes)
- Historical-analogue explanation ("today is analogous to X because...")

**Deliverable — `docs/ARCH026_AI_RESEARCH_ASSISTANT.md`.**
Sections: (0) preamble · (1) motivation · (2) LLM safety framework · (3) prompt discipline (never "should I trade" — always "summarise the sources") · (4) audit + citation requirements · (5) integration with ARCH017/018/022 · (6) failure modes (hallucination, staleness, source drift) · (7) rollout (behind feature flag) · (8) non-goals (LLM never makes decisions).

**Dependencies.** ARCH020 (grounding), ARCH022 (memory), ARCH001A.

---

### 3.22  ARCH027 — Strategy Doctor  (Phase 3 · component of retired ARCH008)

**Objective.** After every closed position (win or lose), analyse and record *why it happened*. Accumulate a corpus of causally-tagged outcomes so AEGIS learns from its history *observationally* (Article V clause 5.2).

**Attribution per closed position.**

```
Exit: −8% on TICKER
Root-cause decomposition:
  62%  Market regime shift (ARCH019: Strong → Weak on entry+15d)
  21%  Weak sector earnings (ARCH018: sector score 82 → 34 over hold)
  10%  Company-specific: guidance cut on earnings call (ARCH026 note)
   7%  Idiosyncratic / unexplained
```

**Method.** Regression / causal inference on the closed-position corpus with the ARCH017-023 context fields as regressors.

**Deliverable — `docs/ARCH027_STRATEGY_DOCTOR.md`.**
Sections: (0) preamble · (1) motivation · (2) post-mortem schema (extends ARCH002 §9.1) · (3) attribution methodology · (4) sample-size discipline (Article IV clause 4.4) · (5) presentation (dashboard + monthly report) · (6) integration with ARCH028 · (7) rollout · (8) non-goals (never automatically re-tunes parameters).

**Dependencies.** ARCH022 (memory), ARCH023 (attribution), ARCH001A Article V.

**Companion gate.** ≥500 closed positions before Strategy Doctor's conclusions are actionable (currently 285).

---

### 3.23  ARCH028 — Recommendation DNA / Pattern Clustering  (Phase 3 · component of retired ARCH008)

**Objective.** Give every recommendation a multi-dimensional "DNA fingerprint" — the combination of momentum, value, growth, quality, volatility, sector, macro, news, breadth, liquidity, regime state — and cluster historical outcomes by DNA type.

**Learned quantities (after ≥500 positions).**

```
DNA Type 27  (Momentum + Strong regime + Sector leader + Low vol)   → wins 91%
DNA Type 13  (Momentum + Late Cycle + Sector laggard + High vol)     → wins 34%
```

**Use.** New recommendations get a DNA type at admission; historically-losing types get lower weight or refusal.

**Deliverable — `docs/ARCH028_RECOMMENDATION_DNA.md`.**
Sections: (0) preamble · (1) motivation · (2) DNA taxonomy (features + binning) · (3) clustering methodology (K-means / hierarchical / GMM) · (4) sample-size discipline · (5) integration with ARCH023 attribution · (6) failure modes (over-clustering, drift) · (7) rollout · (8) non-goals.

**Dependencies.** ARCH022, ARCH023, ARCH001A Article V.

**Companion gate.** ≥500 closed positions.

---

### 3.24  ARCH029 — Confidence Calibration  (Phase 3 · **subset of ARCH007**)

**Objective.** Ensure that when Telegram shows "Confidence 87%," historical 87%-confidence positions actually win 87% of the time. Currently they don't (calibration is not enforced).

**Method.** Reliability diagram + isotonic regression / Platt scaling on the historical corpus. Recompute quarterly.

**Deliverable — `docs/ARCH029_CONFIDENCE_CALIBRATION.md`.**
Sections: (0) preamble · (1) motivation (Article VIII clause 8.5) · (2) reliability diagram framework · (3) Brier score + ECE (Expected Calibration Error) · (4) recalibration cadence · (5) presentation (show the range: "87% [80-90] historically") · (6) rollout · (7) non-goals.

**Dependencies.** ARCH022 (per-position outcomes), ARCH023, ARCH001A Article VIII.

**Note.** ARCH029 is the *operational* subset of ARCH007 (Uncertainty Quantification). ARCH007 remains scoped as the broader theoretical framework; ARCH029 is what ships first because it directly touches operator-visible UX.

---

### 3.25  ARCH030 — Champion vs Challenger Platform  (Phase 3 · component of retired ARCH008)

**Objective.** Formalise the champion-challenger discipline mentioned in ARCH001A Article V clause 5.3 — a running platform that can host multiple candidate strategies (models, parameter sets, exit policies) in shadow / paper-trade / live modes concurrently, with automated promotion gates.

**Discipline (from ARCH001A Article V).**

- Champion runs live
- Challenger runs shadow (no effect) → paper-trade (shadow book) → live (only if beats champion on the ARCH001A §4.2 objective with statistical significance)
- Rollback available at every stage
- Operator approval required for every promotion

**Deliverable — `docs/ARCH030_CHAMPION_CHALLENGER.md`.**
Sections: (0) preamble · (1) motivation · (2) 4-mode lifecycle (design → shadow → paper → live) · (3) promotion criteria (deflated Sharpe delta, drawdown non-degradation, sector-neutrality) · (4) rollback triggers · (5) audit trail schema · (6) infrastructure requirements (parallel pipeline execution) · (7) rollout · (8) non-goals (auto-promotion is forbidden).

**Dependencies.** ARCH023, ARCH029, ARCH001A Article V.

---

## 3-BONUS.  What AEGIS will NOT do (operator's explicit deferrals, 2026-07-17)

Verbatim from the strategic guidance:

> "Don't build RL yet. Don't build autonomous AI yet. Don't build self-modifying models yet. Reason: need thousands of observations. Not 285."

Formalised as deferrals:

| Deferred capability | Blocker | Earliest revisit |
|:--|:--|:-:|
| Reinforcement learning for stop placement | ≥ 2000 closed positions with quality attribution | 2028+ |
| Autonomous AI (self-directing agents) | ARCH001A Article V clause 5.1 [INVARIANT] | never in v1 |
| Self-modifying models (auto-retrain in prod) | ARCH001A Article V clause 5.1 [INVARIANT] | never in v1 |
| Fully-automated broker execution | ARCH011 approval + operator explicit opt-in | v3+ |
| Options / derivatives layer (HEDGE action) | ARCH011 + separate risk framework | v3+ |

Any future proposal to lift these deferrals must go through the ARCH001A Article X amendment discipline.

---

## 4.  Cross-cutting themes

Several themes recur across many docs. Formalising them once here avoids repetition.

### 4.1  Capital-preservation discipline

Every doc must include a "Rule 4: capital preservation overrides return maximisation" section that explains how this doc's proposals honour it. If a proposal in some ARCH doc would violate capital preservation, that proposal is rejected.

### 4.2  Statistical hygiene

Every companion evidence study (RISK00*, LAB0*) must:

- Pre-register hypotheses before running the analysis
- Freeze parameters before evaluation
- Report all comparisons made (multiple-testing correction)
- Use minimum sample sizes (typically N ≥ 30 per bucket for a claim)
- Publish raw output files alongside conclusions
- Never re-run on the same data after seeing results

### 4.3  Sealed-file invariance

Every ARCH doc must preserve the MON001 sealed baseline. `e4c070673568c52d…` is the current fingerprint. Any doc that would require modifying a sealed file must go through the MON001 amendment ceremony (see `docs/MON001_CERTIFICATION.md`).

### 4.4  Tenant-generic discipline

Every doc must be free of hardcoded sectors, tickers, thresholds specific to the current AEGIS deployment. Everything domain-specific must come from a ClientProfile-equivalent runtime config. This is a longstanding operator principle (recorded in memory as `feedback_tenant_generic.md`).

### 4.5  ARCH002 constitutional priority

Once ARCH002 is CONSTITUTIONAL (post operator approval), no downstream ARCH doc may contradict it. If a downstream doc identifies a conflict, the resolution path is: file an ARCH002 amendment (per ARCH002 §14), get operator approval for the amendment, then adjust the downstream doc.

---

## 5.  Governance of this roadmap

- **Owner.** AEGIS engineering (the assistant, on operator instruction).
- **Update cadence.** Whenever a new ARCH doc lands, this file's §1 status board is updated to reflect the new state, and the corresponding §3 subsection is either marked ✅ or replaced with a link to the delivered doc.
- **Amendments.** New tracks may be added (ARCH017+); the numbering is append-only. Existing track numbers are never reassigned.
- **Superseded content.** When a bonus track is promoted (e.g. ARCH013 becomes primary), its `⚪ BONUS` marker is removed and it takes its place in the priority list.

---

## 6.  What comes next (immediate, revised 2026-07-17)

Following the strategic guidance in §0 ("do not write more code; architecture is now more important than features"):

1. **No new code work.** Every immediate next step is a design doc.
2. **Await operator approvals on the constitutional docs already delivered:**
   - ARCH001A (Constitution) DRAFT → CONSTITUTIONAL
   - ARCH002 (Exit Framework) DRAFT → CONSTITUTIONAL
   - RISK001-A1 primary-metric decision (§9 of `research/RISK001-A_RESULTS.md`)
3. **On approvals landing**, begin **ARCH017** (Global Intelligence Engine) design — the operator-named next priority.
4. **After ARCH017 → ARCH018 → ARCH019** land as designs, the Market Intelligence Layer is ready to be gated on companion evidence studies (LAB014-A for sector-conditional scoring, RISK004-A/B for adaptive holding + exit).
5. **RISK001-C implementation** may begin in parallel *only after* ARCH001A + ARCH002 are CONSTITUTIONAL and the operator explicitly authorises it. That work is unblocked from the ARCH017-030 design cycle.

**What is NOT next.** Additional indicators, more scoring factors, RL, autonomous AI, self-modifying models, broker integration. All deferred per §3-BONUS.

---

## 7.  Integrity + sign-off

- Sealed files touched: **0**
- Production code touched: **0**
- MON001 fingerprint: unchanged
- `cumulative_strategy_search`: **38** (unchanged)
- Author-signed: AEGIS engineering (assistant)
- Operator-approved: pending
- CONSTITUTIONAL status: this doc is a **living index**, not constitutional. Constitutional status attaches to the individual ARCH docs once operator-approved.

---

## 8.  Change log

| Date | Change | Author |
|:--|:--|:--|
| 2026-07-17 | Initial roadmap; ARCH002 DRAFT; ARCH003-ARCH016 SCOPED / BONUS | AEGIS engineering |
| 2026-07-17 (revision 1) | ARCH001A added at constitutional apex; execution order revised | AEGIS engineering |
| 2026-07-17 (revision 2) | **Major.** Added ARCH017-ARCH030 (Market Intelligence Layer + AI Learning Layer). Phase structure formalised (Phase 0-4). ARCH019 subsumes ARCH006; ARCH027/028/030 replace ARCH008; ARCH029 is operational subset of ARCH007. Operator's strategic guidance (§0) preserved verbatim as reference of record. §3-BONUS added: deferred capabilities (RL, autonomous AI, self-modifying models, auto broker execution, options). §6 revised: no new code; design-only cycle. | AEGIS engineering |
| 2026-07-17 (revision 3) | ARCH017A (Market Data Canonical Model) DRAFT delivered as new Phase-2 gate — the "database constitution" every ARCH017-030 consumer inherits. ARCH017 (Global Intelligence Engine) DRAFT delivered — the missing top half of AEGIS (~60 variables, ~35 DerivedMetrics, ~25 NormalizedIndicators, 5 Classifications, 4 CompositeScores). Roadmap status board and §2.1 execution order updated. §3.11a added, §3.12 updated to reflect delivery. | AEGIS engineering |
