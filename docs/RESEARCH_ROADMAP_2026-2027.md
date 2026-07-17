# AEGIS Research Roadmap 2026–2027

**Document type:** Master index of the `00_FUNDAMENTAL_RESEARCH` track
**Status:** LIVE INDEX — updated when tracks land or their status changes
**Author:** AEGIS engineering
**Date opened:** 2026-07-17
**Governance:** ARCH002-approved amendment discipline applies to every doc referenced below

---

## 0.  Frame — why this track exists

AEGIS v1 is feature-complete. Continued value now comes from **institutional capabilities**, not more indicators. The user's directive:

> "You should build **institutional capabilities**. If I were the CTO of AEGIS, I'd organize the remaining work into **Research Tracks**. Every track produces a design document first, then implementation later. That way, your project folder becomes a long-term blueprint rather than a collection of ad hoc prompts."

Two organising principles for this track:

1. **Design first, implement second.** Every ARCH doc is a design deliverable. Implementation is a *separate* work item, gated on: (a) design approval, (b) evidence from a companion RISK/LAB study if quantitative, (c) shadow-mode + paper-trade phases.
2. **Capital-preservation-first ordering.** ARCH002 (Exit) → ARCH003 (Risk Budgeting) → ARCH004 (Position Sizing) come first. Return-optimising tracks (ARCH005 Portfolio Construction) come later. This reflects Rule 2 of the AEGIS Constitution: preserve capital before pursuing return.

---

## 1.  Track status board

| ID | Title | Status | Depends on | Design ETA | Impl gate |
|:--|:--|:-:|:--|:-:|:--|
| **ARCH001** | Recommendation Lifecycle | ✅ DONE | — | — | shipped as design |
| **ARCH002** | Exit & Capital-Preservation Framework | 🟢 DRAFT (2026-07-17) | RISK001-A1 evidence | done | operator approval + RISK001-C |
| **ARCH003** | Enterprise Risk Budgeting | 🟡 SCOPED | ARCH002 | 2026-Q3 | new evidence study |
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

**Status legend.** ✅ DONE · 🟢 DRAFT delivered · 🟡 SCOPED (this doc has the objectives) · ⚪ BONUS (post-v2) · 🔴 BLOCKED

---

## 2.  Execution order (operator-preferred sequence)

Per the operator's directive in the ARCH002-context message:

```
1.  ARCH002  Exit Framework                  ← delivered 2026-07-17
2.  ARCH003  Risk Budgeting
3.  ARCH004  Position Sizing
4.  ARCH006  Regime Intelligence
5.  ARCH007  Uncertainty Quantification
6.  ARCH008  Self-Learning
7.  ARCH005  Portfolio Construction
8.  ARCH010  Anti-Fragility
9.  ARCH011  Execution
10. ARCH009  Governance
11. ARCH012–ARCH016  (advanced capabilities)
```

This sequence builds capital-preservation capability first (2–4), then adaptive intelligence (6–8), then return-optimising sophistication (5), then robustness and productionisation (10–11), then organisational-scale controls (9), then advanced differentiators (12–16).

---

## 3.  Per-track scoping

Each subsection below is the seed for the eventual full design document. It captures: objective · key research topics · deliverable structure · dependencies · non-goals. A future working session can pick any one of these and produce the full ARCH-doc following the ARCH002 template shape.

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

## 6.  What comes next (immediate)

1. **Await operator's RISK001-A1 primary-metric decision** (blocks RISK001-C implementation from ARCH002).
2. **On approval of ARCH002**: begin `RISK001-C` implementation of §13.1 subset (L1.a hard stop + L1.b gap stop + L4.a time exit + L7.a portfolio DD + L8.a kill switch + L0 position validation).
3. **In parallel, no ARCH-doc work needed**: OPS002 (Operational Excellence) can begin as it's largely independent of the exit-track evidence.
4. **After RISK001-C ships**: kick off ARCH003 (Risk Budgeting) — the next capital-preservation track.

Everything else in §1's status board is queued behind the above.

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
