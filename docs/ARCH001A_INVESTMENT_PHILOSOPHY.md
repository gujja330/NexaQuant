# ARCH001A — AEGIS Investment Philosophy & Decision Theory

## THE CONSTITUTION OF AEGIS

**Document type:** Constitutional foundation — supersedes every other design document
**Status:** DRAFT · design only · NO code · NO parameter tuning · NO production changes
**Governance:** Once operator-approved, this document becomes CONSTITUTIONAL. Every existing and future ARCH / RISK / LAB / OPS / MON document must comply with it. Where a downstream document conflicts with this one, this document wins and the downstream document is amended.
**Owner role:** Chief Investment Officer · Chief Risk Officer · Head of Research · Chief Compliance Officer · Chief Technology Officer (all seats represented by the operator in the current organisation)
**Author:** AEGIS engineering
**Date opened:** 2026-07-17
**Predecessors:** none (this is the apex of the constitutional hierarchy)
**Successors (bound by this document):** `ARCH002_EXIT_FRAMEWORK.md` · `RESEARCH_ROADMAP_2026-2027.md` · every ARCH00* and ARCH01* to come
**Related evidence:** `research/RISK001-A_RESULTS.md` · `Executive Summary.pdf` · `docs/RISK001-A_EXIT_ANALYTICS.md` · `docs/RISK001-B_RISK_CONTROLLER_ARCHITECTURE.md`

---

## 0.  Preamble & non-negotiables

1. This document is **constitutional design**, not implementation. It contains no code, no parameter values that would change production behaviour, and touches no sealed file.
2. Every article, every clause, every rule below is subject to the amendment discipline in Article X of the Constitution (§1.10). Nothing here is casually revised.
3. Where any downstream document (ARCH002 through ARCH016, RISK*, LAB*, OPS*, MON*) says something incompatible with this document, **this document wins**. The downstream document is amended, not this one.
4. The operator (currently one person; may be a committee in the future) holds all constitutional-approval authority. No AI, no automated process, no code path can amend the Constitution.
5. On approval, the Constitution is versioned (`ARCH001A v1.0`) and its content is byte-hashed. Future amendments produce new versions (`v1.1`, `v2.0`) — never in-place edits. Old versions remain readable in git history.
6. Cumulative_strategy_search: **38** (unchanged). MON001 fingerprint: `e4c070673568c52d…` (invariant). Sealed files touched: **0**.

---

## 1.  THE AEGIS CONSTITUTION

Ten Articles. Each Article contains numbered clauses. Every clause has a **rationale** (why it exists) and, where relevant, a **precedent** (which philosopher or literature it draws from). Clauses marked **[INVARIANT]** cannot be amended; the only path to change them is to retire this Constitution entirely and adopt a successor.

---

### Article I — Mission

**1.1** AEGIS exists to grow the operator's capital, over time, while never risking the capital's permanent loss.
> **[INVARIANT]** *Rationale:* This is the ultimate goal. Any other objective (return, Sharpe, prestige) is subordinate to this one. *Precedent:* Buffett Rule #1 ("Don't lose money") and Rule #2 ("Don't forget Rule #1").

**1.2** AEGIS is designed to be operated indefinitely — decades, not years.
> *Rationale:* The compounding advantage of survival is exponential. A system that loses 50% needs 100% to recover; a system that avoids the 50% loss compounds continuously. *Precedent:* Munger — "The first rule of compounding: never interrupt it unnecessarily."

**1.3** AEGIS serves the operator, not the model.
> **[INVARIANT]** *Rationale:* The operator's judgment always outranks the model. The model advises; the operator decides. *Precedent:* All institutional practice; specifically Kahneman's insight that models beat humans on average but humans catch the tail cases models miss.

**1.4** AEGIS never optimises for return above survival.
> **[INVARIANT]** *Rationale:* Optimising for return above survival is how firms blow up. This is the *first* difference between AEGIS and a return-maximising system. *Precedent:* Long-Term Capital Management (LTCM 1998); Taleb — the "turkey problem."

---

### Article II — Investment Constitution

**2.1  Definition of investing.** Investing is the deliberate deployment of capital with the expectation that it will grow, over time, through the productive use of the assets acquired.
> Contrast with **speculation** (symmetric bets where skill and luck are indistinguishable over the sample) and **gambling** (negative-sum, house edge).

**2.2  Definition of risk.** Risk is the probability and magnitude of *permanent capital loss*.
> **[INVARIANT]** *Rationale:* Volatility is not risk. Volatility is the variance of the return distribution; risk is the downside tail of the wealth distribution. A position that swings ±20% but always returns is volatile; a position that permanently loses 20% is risky. *Precedent:* Howard Marks — "Risk means more things can happen than will happen; and the things that happen can hurt you badly." Buffett — "Risk comes from not knowing what you're doing." Taleb — the difference between measured risk (variance) and actual risk (ruin).

**2.3  Definition of uncertainty.** Uncertainty is the domain where probability distributions themselves are unknown or unknowable.
> *Rationale:* Frank Knight (1921) distinguished **risk** (known distribution) from **uncertainty** (unknown distribution). AEGIS operates in uncertainty most of the time; it *acts as if* it operates in risk (fitted distributions) and pays for that pretence with kill-switches, robustness margins, and Rule 8. *Precedent:* Taleb — "The problem with fitting distributions to markets is that the distribution changes when you fit it."

**2.4  Definition of edge.** Edge is a *repeatable, robust, empirically-validated* advantage over the market average.
> Three claims must be simultaneously true for something to qualify as edge:
> - **Repeatable** — persists across time, not a single-sample fluke
> - **Robust** — persists across market regimes, not only in the calibration window
> - **Empirically validated** — measured on out-of-sample data with proper statistical hygiene (Article IV)

**2.5  Definition of luck.** Luck is the variance component of outcome not attributable to skill or edge. Zero-mean over a long enough sample; non-zero over any finite sample.
> *Rationale:* Every quant strategy needs an honest luck accounting. If a strategy has Sharpe 1.0 over 5 years, the 95% confidence interval on true Sharpe is roughly [0.1, 1.9]. Most of what looks like edge is luck.

**2.6  Definition of skill.** Skill is the *persistent* component of outcome — reproducible across time, market conditions, and — crucially — different implementations of the same idea.
> *Rationale:* Skill is what survives adversarial replication. If two independent implementations of the same idea both produce edge, that's skill. If only one does, that's overfitting.

---

### Article III — Decision Constitution

**3.1  Framework.** AEGIS makes decisions under uncertainty using **Bayesian posterior beliefs** combined with a **utility function that penalises tail loss**.
> *Rationale:* Pure Bayesian expected-utility maximisation with a linear utility is Kelly betting — mathematically optimal in a world of known distributions. Reality is not that world. AEGIS uses a *concave* utility (log-wealth) *penalised* by a tail-loss term (Expected Shortfall). *Precedent:* Kelly (1956); Thorp (1962, Beat the Dealer); Markowitz (1952); von Neumann & Morgenstern (1944).

**3.2  Objective function.** The AEGIS objective is:

```
maximise    E[ log(W_T) ]                              (long-run wealth growth, ergodic)

subject to  P(ruin over 10 years)  ≤ 1%                (survival constraint)
            Max Drawdown           ≤ 20%               (drawdown constraint)
            Every position's max loss is bounded        (position-level hard stop, Article VI)
            Portfolio has a kill switch                 (Article VII / ARCH002 L8)
```

> *Rationale:* This is **drawdown-constrained log-utility optimisation** — closest continuous mathematical statement of Rules 1-6 of the operator's mission. Log-utility naturally recovers Kelly sizing; the constraints suppress full-Kelly to *fractional* Kelly, empirically shown by Thorp and others to be superior in the presence of parameter estimation error. **[INVARIANT for the constraints; the growth term may be replaced.]**

**3.3  Fractional Kelly discipline.** AEGIS operates at *at most* one-quarter Kelly on any single position and one-eighth Kelly on portfolio-aggregate exposure.
> *Rationale:* Full Kelly maximises long-run growth *only* when the edge is known exactly. In reality, edge estimates have variance; full Kelly on an estimated edge is regularly ruinous. Thorp himself operated at half-Kelly. AEGIS chooses quarter-Kelly per position and one-eighth aggregate as the discipline. *Precedent:* Thorp, "The Kelly Capital Growth Investment Criterion" (2006 Wiley volume).

**3.4  Decision under Knightian uncertainty.** When the model's *own confidence* in its distribution estimate is low, AEGIS *reduces exposure*, never increases it.
> *Rationale:* This is Rule 8 ("when uncertain, reduce") mechanised. See Article VI clause 6.9.

**3.5  Regime-adaptive λ.** The tail-penalty coefficient (implicit in the drawdown constraint of §3.2) scales with the current market regime:
- **Strong** regime, low volatility → smaller λ (accept more tail for more growth)
- **Neutral** regime → default λ
- **Weak / Crisis** regime → larger λ (protect harder)
- **Unknown** regime → largest λ (minimum exposure until regime resolves)
> *Rationale:* Kaminski-Lo (2007) — stop-loss efficacy depends on the autocorrelation of returns and hence on the regime. Same principle applies to the whole optimisation.

---

### Article IV — Research Constitution

**4.1  Every claim requires evidence.** No hypothesis becomes a production parameter without evidence produced under the discipline of this Article.

**4.2  Pre-registration.** Every research study must pre-register:
- The hypothesis being tested
- The statistical test to be applied
- The primary and secondary metrics
- The decision rule (adopt / reject / inconclusive)
- The sample and time window
> All *before* running the analysis. Precedent: pharmaceutical clinical trials.

**4.3  No re-tuning on same data.** Once a study has been run on a dataset, the parameters tested may not be adjusted based on the results and re-run on the same dataset.
> **[INVARIANT]** *Rationale:* This is p-hacking. A "5% didn't work, let me try 4%" iteration on the same 285 positions is not new evidence; it is compounding luck. New evidence requires a genuinely new dataset (more time; different universe; different regime).

**4.4  Statistical hygiene.** Every study must:
- Use minimum sample sizes (N ≥ 30 per bucket for any specific claim)
- Apply multiple-testing corrections (Bonferroni or Benjamini-Hochberg) when comparing many candidates
- Compute confidence intervals (bootstrap or analytical) alongside point estimates
- Report *all* comparisons made, including failed ones
- Freeze random seeds and record them
> *Precedent:* Bailey & López de Prado — deflated Sharpe ratio; the multiple-comparisons crisis in strategy backtesting.

**4.5  Publication.** Every study publishes:
- Successful conclusions
- **Failed** hypotheses
- Data-quality caveats
- Bugs found during execution
> *Rationale:* Failed hypotheses have information value. Suppressing them creates a publication-bias problem in the operator's own research corpus. *Precedent:* research reproducibility crisis; Ioannidis 2005.

**4.6  Discipline over ambition.** A research finding that is *marginal* and *contested* stays unadopted, even if the operator "feels" it works. Feelings do not defeat evidence in this Constitution.

---

### Article V — Learning Constitution

**5.1  Learning is bounded.** No parameter, no model, no threshold changes in production without operator approval.
> **[INVARIANT]** *Rationale:* Unsupervised online learning in production is how quant systems drift, overfit recent regimes, and quietly break. AEGIS learns *observationally* — accumulating attribution and calibration data — but does not act on that data in real time.

**5.2  Learning is observational.** The self-learning engine (ARCH002 §9, ARCH008 planned) *records outcomes*. It does not *automatically retune* the parameters that produced those outcomes.

**5.3  Champion-challenger discipline.** When a new model or parameter is proposed, it enters a challenger role:
- Shadow: runs alongside champion; emits telemetry but has no production effect
- Paper-trade: alters a shadow book; measured against champion
- Promotion: only if beats champion on the objective function of §3.2 with statistically-significant margin
- Rollback: challenger can always be reverted; champion cannot be retired without a challenger that beats it

**5.4  Every learned quantity needs statistical significance.** No bucket-level claim with N < 30. No cross-cutting claim without multiple-testing correction.

**5.5  Regime-conditioned learning.** Learning is stratified by regime. A pattern seen in a Strong regime does not generalise to Weak without independent evidence.

---

### Article VI — Risk Constitution

Extends the six-rule mission of the operator with three additional rules distilled from RISK001-B and this document's deliberations. **All ten rules are [INVARIANT].**

- **Rule 1.** Never lose capital unnecessarily. ("Unnecessarily" = when a deterministic pre-defined rule would have prevented the loss.)
- **Rule 2.** Preserve capital before pursuing return.
- **Rule 3.** Large losses are unacceptable. ("Large" = beyond the per-position hard-stop budget computed at admission.)
- **Rule 4.** Small losses are business expenses.
- **Rule 5.** Profits may be unlimited.
- **Rule 6.** Risk must always be bounded. (Every position: known max-loss in ₹ and % of portfolio at entry. Every portfolio: known max-DD budget.)
- **Rule 7.** The Risk Controller has veto power. (No score, weight, override, or configuration can prevent an exit that the Controller flags.)
- **Rule 8.** When uncertain, reduce risk. (Missing data, unknown regime, null confidence → REDUCE. Never HOLD_LARGER because "we're not sure.")
- **Rule 9.** Time horizon is real. Do not liquidate a long-term position for a short-term movement unless a hard rule fires. (Prevents whipsaw exits on transient adverse moves.)
- **Rule 10.** The system must fail safe. (Any component that cannot verify its inputs freezes new commitments. Silence is not success — a system that stops producing signals is not implicitly "holding"; it is *stopped*, and every open position is re-evaluated by hard rules.)

---

### Article VII — Operational Constitution

**7.1  Sealed baseline discipline.** The MON001 sealed baseline (currently fingerprint `e4c070673568c52d…`) is byte-invariant. No component of AEGIS modifies any sealed file. Amendment to the sealed baseline requires the MON001 amendment ceremony (documented in `docs/MON001_CERTIFICATION.md`).

**7.2  Amendment lifecycle.** For any operational change (new stop, new sizing rule, new metric):
- Design (ARCH doc)
- Evidence (RISK / LAB study; pre-registered per Article IV)
- Approval (operator)
- Shadow (parallel run, no effect)
- Paper-trade (shadow book, no real trades)
- Live (subject to rollback)
> No exceptions. No steps skipped.

**7.3  Rollback authority.** The operator can revert any change at any time, with or without justification. Rollback is a *right*, not a request.

**7.4  Audit trail.** Every decision, every override, every state transition, every parameter change is appended to an immutable log. Nothing is deleted; corrections are new appends that supersede.

**7.5  Kill switch authority.** The operator has manual kill-switch authority (ARCH002 L8.d). The system has automated kill-switches (ARCH002 L8.a-e). Neither can be disabled.

**7.6  Tenant-generic.** Every prompt, copy string, threshold, sector list, and default parameter must be read from a runtime configuration (ClientProfile-equivalent). No hardcoded sectors, tickers, or thresholds specific to any single operator or deployment.
> *Precedent:* longstanding operator principle (recorded in `feedback_tenant_generic.md` memory).

**7.7  No hardcoded parameters.** Every tunable value in production code must come from a versioned configuration file — never a literal in code. Configuration changes go through §7.2.

**7.8  Reproducibility.** Every study, every backtest, every live decision is reproducible from the frozen inputs (data + config + code SHA + random seed). Non-reproducible results are treated as no results.

---

### Article VIII — Ethics

**8.1  Transparency.** Every recommendation is auditable — the operator can, at any time, reconstruct why the system said what it said.

**8.2  Explainability.** Recommendations include *why*, not only *what*. A "buy X" is not a valid output; a "buy X because … / risks are … / would exit if …" is.

**8.3  Operator override.** The operator can always: manually exit a position, refuse a proposed entry, reduce a proposed weight, halt all trading. **[INVARIANT]** *No configuration can disable operator override.*

**8.4  AI autonomy floor.** No parameter, model, or policy changes in production without explicit operator approval. AI produces analyses, drafts, proposals — never unilateral production changes.
> **[INVARIANT]**

**8.5  No misleading confidence.** Confidence numbers exposed to the operator (Telegram: "Confidence: 87%") are *calibrated*. If historical 87% buckets actually win 62%, the system says 62% or an interval `[55%, 68%]`, not 87%.

**8.6  Advisory-only in v1.** AEGIS produces recommendations; it does not automatically place orders. Broker integration (ARCH011) is deferred to v2.

**8.7  Failure honesty.** When the system does not know, it says "unknown" — never a fabricated point estimate. When a rule cannot evaluate, the audit records the failure explicitly.

**8.8  No forced trades.** Even after a signal, the operator must act. The system never simulates the operator's action, and never claims a trade was executed unless the operator confirms.

**8.9  Data privacy.** Operator data (positions, capital, personal identifiers) never leaves the operator's environment except with explicit approval per instance.

---

### Article IX — Governance

**9.1  Constitutional priority order.** When multiple documents apply to a situation, the priority is:

```
1. ARCH001A  (this document — Constitution)
2. ARCH002   (Exit & Capital Preservation Framework)
3. RISK001-B (Risk Controller architecture — component of ARCH002)
4. ARCH003 through ARCH016 (in dependency order per RESEARCH_ROADMAP)
5. RISK / LAB / OPS / MON evidence studies
6. Implementation code
```
Higher-priority documents *always* win over lower-priority when they conflict.

**9.2  Conflict resolution.** When a conflict is discovered:
- If the lower-priority document is wrong: amend it.
- If the higher-priority document is wrong: amend it via the amendment discipline (Article X). Do not silently override.

**9.3  Operator approval required.** Every constitutional change, every new ARCH doc entering CONSTITUTIONAL status, every threshold reaching production requires the operator's explicit approval documented in `docs/APPROVALS_LOG.md` (to be created when first approval lands).

**9.4  Documentation-first.** No implementation may precede its design document. If a spec is missing, the implementation is halted until the spec is written.

**9.5  Standing veto.** The operator holds a standing veto on every AI-produced proposal, without cause. Vetoed proposals are archived but not deleted; they may be revisited later with new evidence.

**9.6  Committee-of-one is fine.** In the current AEGIS organisation, one operator holds all seats (CIO, CRO, CTO, HoR, CCO). This is documented, not obscured. Future organisational scaling will formalise separate roles.

---

### Article X — Amendments & Meta-Rules

**10.1  How this document may be amended.** An amendment to ARCH001A requires:
1. A written proposal citing the specific clause(s) being amended and the justification
2. Publication of the proposal for a review period (minimum 7 calendar days; in a single-operator organisation, this is a self-imposed cooling period)
3. Operator explicit approval
4. Version increment (`v1.0` → `v1.1` for clause revisions; `v2.0` for Article structural changes)
5. All existing CONSTITUTIONAL documents (ARCH002+) reviewed for continuing compliance; any that no longer comply are amended in the same commit
6. Audit-trail entry in `docs/CONSTITUTIONAL_AMENDMENTS_LOG.md`

**10.2  [INVARIANT] clauses cannot be amended.** Clauses marked **[INVARIANT]** in this document are byte-frozen. The only path to change them is to retire this Constitution and adopt a successor (a new document, e.g. `ARCH001B` or a fork `ARCH001A-DERIVATIVE`).

**10.3  Grandfather clauses.** An amendment does not retroactively invalidate designs approved under the prior version. When ARCH001A `v1.0` is amended to `v1.1`, existing ARCH002 (approved under `v1.0`) remains in effect. Newly-approved documents comply with the new version.

**10.4  Constitutional-review cadence.** The Constitution is reviewed every 12 months from adoption. Review findings are documented; amendments (if any) follow §10.1.

**10.5  Retirement.** If the operator determines that AEGIS's mission has fundamentally changed, this Constitution may be retired and a new one adopted. Retirement is not lightly done and requires explicit written record.

---

## 2.  Philosophical foundations

The Constitution above is not invented. It is a synthesis of what practitioners and academics have concluded, over the century of formal investing, is *the way* to survive in markets. This section grounds each philosophical strand.

### 2.1  The value-investing lineage

**Warren Buffett** (b. 1930). Chairman of Berkshire Hathaway. Public output: annual letters (1965 to present) and *The Essays of Warren Buffett* (Cunningham, ed.). Key contributions to AEGIS:
- **"Never lose money"** as an operating principle, not a slogan (Article I, clause 1.1).
- **Circle of competence** — only invest in what you understand. AEGIS restricts its universe to NIFTY-200-ish tradable Indian equities; it does not opine on commodities, foreign markets, or private equity.
- **Margin of safety** (from Graham) — buy well below intrinsic value; the difference is the safety buffer. Analogue in AEGIS: `hard_stop_pct` sets the operational margin of safety per position.
- **Long-term compounding** — return is not the point; *compounded* return is. Losses that require dis-proportionate recoveries are catastrophic to compounding.

**Charlie Munger** (1924-2023). Vice Chairman of Berkshire Hathaway. Public output: *Poor Charlie's Almanack*, USC/Harvard speeches. Key contributions:
- **Inversion**: instead of asking "how do I win?", ask "how do I not lose?" Rules 1-4 of Article VI are inversion in operational form.
- **Latticework of mental models** — no single discipline explains the market. AEGIS blends statistics (Article III), behavioural economics (§2.4 below), risk management (Article VI), and system-safety engineering (Article VII).
- **"Invert, always invert"** — every proposal must survive the question "what would make this catastrophic?"
- **Avoiding stupidity beats seeking brilliance** — Article IV's "discipline over ambition" clause.

### 2.2  The cycles-and-second-order lineage

**Howard Marks** (b. 1946). Co-founder Oaktree Capital. Public output: memos to clients (1990 to present); *The Most Important Thing*.
- **Risk = probability of loss**, not volatility (Article II, clause 2.2). This is Marks's central pedagogical point.
- **Second-level thinking** — the market prices first-level thoughts. Edge comes from thinking one level deeper than the crowd. AEGIS's factor models attempt this; we humble ourselves about how often we succeed.
- **Cycles** — nothing goes up forever; nothing goes down forever. Regime intelligence (ARCH006) formalises this.
- **"You can't predict; you can prepare"** — codified in the drawdown constraint of §3.2 and the kill-switch discipline of Article VII.

### 2.3  The principles-and-diversification lineage

**Ray Dalio** (b. 1949). Founder Bridgewater. Public output: *Principles*; *Principles for Dealing with the Changing World Order*; All Weather and risk-parity papers.
- **Radical transparency** — every decision is inspectable. Article VIII, clause 8.1.
- **Risk parity** — equal risk contribution across uncorrelated assets, rather than equal capital weighting. ARCH005 (Portfolio Construction) formalises this.
- **All Weather** framing — build a portfolio that survives every macroeconomic environment. AEGIS is not full All Weather (it is currently long-only Indian equities), but the regime-adaptive λ of §3.5 borrows the idea.
- **"Diversifying well is the Holy Grail of investing"** — through correlation, not just count. ARCH005 §L5.a caps pairwise correlation at 0.85.

### 2.4  The behavioural lineage

**Daniel Kahneman** (1934-2024) & **Amos Tversky** (1937-1996). Public output: Prospect Theory papers (1979, 1992); *Thinking, Fast and Slow*.
- **Prospect theory** — losses hurt roughly 2× as much as equivalent gains feel good. AEGIS's asymmetric objective function (§3.2) reflects this: the drawdown constraint is *disproportionately* penalised versus the growth term.
- **System 1 vs System 2** — fast, intuitive judgment vs slow, deliberate reasoning. AEGIS is System 2 (rule-based); operator override is where System 1 gets to intervene, but only *against* the model (never for higher risk).
- **Anchoring, availability, framing, hindsight bias** — cognitive traps every quantitative system must guard against.

**Richard Thaler** (b. 1945). Nobel 2017. Public output: *Nudge*; *Misbehaving*.
- **Mental accounting** — investors treat different pools of capital differently, contrary to rational theory. AEGIS's single portfolio-DD budget (Rule 6) enforces one budget, no accounting fictions.
- **Endowment effect** — people hold losers because "they own them." Hard stops (Rule 1) mechanically defeat the endowment effect.

The behavioural literature is fundamentally about *why humans make bad investment decisions*. AEGIS's rules are constructed to prevent those failures at the process level, not by asking humans to be better.

### 2.5  The quantitative lineage

**Harry Markowitz** (1927-2023). Nobel 1990. Modern Portfolio Theory (1952).
- **Diversification** as risk reduction — foundational.
- **Efficient frontier** — for any target return, there is a minimum-variance portfolio; for any variance, a maximum-return portfolio.
- **Caveat:** MPT uses variance-as-risk (which contradicts §2.2). AEGIS uses MPT geometrically (portfolio construction) but not axiomatically (variance is not our risk measure).

**Jim Simons** (1938-2024). Founder Renaissance Technologies. Publicly opaque on methods; publicly clear on *approach*:
- **Pure quant discipline** — signals matter, stories don't
- **Short holding periods** — Medallion's approach is intraday to weekly; AEGIS is longer-horizon (63 days) but the discipline of "rules, not narratives" is Simons-inherited
- **Continuous re-evaluation** — Medallion retrains constantly. AEGIS does *not* retrain continuously; it defers to Article V's supervised-learning discipline.
- **Statistical arbitrage** — many small, uncorrelated edges compound. AEGIS's multi-factor scoring is a lower-bandwidth version of the idea.

**Cliff Asness** (b. 1966). Co-founder AQR. Extensive academic publication.
- **Factor investing** — value, momentum, quality, low-vol persist across markets and eras. AEGIS uses momentum and quality factors (registry data confirms).
- **Documented humility** — Asness openly discusses factor drawdowns and model failure modes. AEGIS's own scorecard (post-mortem framework) is in this spirit.
- **"I've been wrong about this before"** — a phrase every quant researcher should be able to say.

**Ed Thorp** (b. 1932). *Beat the Dealer* (1962), *Beat the Market* (1967), *A Man for All Markets* (2017).
- **Kelly criterion** as *the* mathematically optimal bet-sizing rule when edge is known. Applied to blackjack, cards, then to markets.
- **Fractional Kelly** as *the* practical adaptation when edge is estimated. Thorp himself operated at half-Kelly for decades. AEGIS operates at quarter-Kelly per position (§3.3).
- **Convertible bonds** — Thorp's first hedge-fund arbitrage strategy. Not directly applicable to AEGIS but the discipline (find a mathematical inefficiency, size properly, exit on convergence) is.

**John L. Kelly** (1923-1965). *A New Interpretation of Information Rate* (1956).
- **The Kelly criterion** — for a positive-edge bet with known probabilities, the optimal fraction of capital to bet is `f* = (bp − q) / b` where `b` is the odds, `p` the win probability, `q = 1 − p`. Under repeated betting with reinvestment, this maximises long-run log-wealth.
- **Ergodicity implications** — Kelly is optimal in the "time average" sense (long-run individual), not in the "ensemble average" (expected wealth across parallel realities). Peters (2019) has extensively argued that this distinction matters.

### 2.6  The uncertainty / robustness lineage

**Nassim Taleb** (b. 1960). *Fooled by Randomness*, *The Black Swan*, *Antifragile*, *Skin in the Game*, *Statistical Consequences of Fat Tails*.
- **Antifragility** — gains from disorder, beyond mere robustness. Article II clause 2.7 ("What is antifragility?").
- **Black Swan** — high-impact, low-probability, retrospectively-rationalised events. Cannot be predicted; must be prepared for via convex payoffs and kill switches.
- **Iatrogenics** — intervention that causes more harm than the disease. AEGIS's aversion to "adaptive learning in production" (Article V, clause 5.1) is Taleb-inherited.
- **Barbell strategy** — extreme safety (cash / treasuries) + extreme risk-taking (small options positions), avoiding the middle. Not directly implemented in AEGIS but philosophically resonant with the "fractional Kelly + kill switch" structure.
- **Convexity** — payoffs that gain more from good outcomes than they lose from bad ones. Trailing stops (ARCH002 L3) are locally convex.

**Frank Knight** (1885-1972). *Risk, Uncertainty, and Profit* (1921). Defined the risk-vs-uncertainty distinction on which Article II clause 2.3 rests.

### 2.7  The decision-theoretic lineage

**John von Neumann & Oskar Morgenstern** (1944). *Theory of Games and Economic Behavior*.
- **Expected utility theory** — under axioms of rationality, decision-makers maximise expected utility of outcomes.
- AEGIS uses a *concave* utility (log-wealth) as the objective (§3.2). This encodes risk-aversion: an extra ₹1 million of wealth is worth less to someone with ₹100 million than to someone with ₹100 thousand.
- **Caveats:** the axioms (completeness, transitivity, continuity, independence) are violated in observed human behaviour — this is what prospect theory documents.

**Bruno de Finetti** (1906-1985) and **Leonard "Jimmie" Savage** (1917-1971). Foundations of subjective/Bayesian probability. AEGIS's Bayesian framing (§3.1) rests on their axioms.

**Robust decision-making** (Wald 1950; Hansen & Sargent 2001; Lempert & Collins 2007). Decision-makers should choose actions that perform *acceptably* across the *set* of plausible probability distributions, rather than optimising for a single "point estimate" distribution. AEGIS uses this to select fractional-Kelly parameters — the fraction is chosen to be robust to estimation error in edge.

**Adaptive decision systems** (recent literature; MDP frameworks). Systems that update their action policy as new information arrives, subject to appropriate discount rates. AEGIS's learning is *observational* (Article V) — we accumulate evidence but do not automate parameter updates.

### 2.8  Meta-observation

Every practitioner listed above independently converged on a small set of principles:

1. **Losses cost more than gains earn** (Kahneman, Marks, Buffett)
2. **Never bet the farm** (Kelly, Thorp, Taleb, Munger)
3. **Diversify by correlation, not by count** (Dalio, Markowitz, Simons)
4. **The edge is smaller than you think** (Asness, Thorp, Simons)
5. **The environment changes; be ready** (Marks, Taleb, Dalio)
6. **Discipline beats brilliance** (Buffett, Munger, Asness)
7. **Systems beat forecasts** (Simons, Thorp, Asness)

These seven convergent principles are the philosophical backbone of the ten-article Constitution.

---

## 3.  Answers to the ten fundamental questions

The Constitution above operationalises answers to these questions. This section states the answers plainly, without the formal Article structure.

### 3.1  What is investing?

Investing is the deliberate deployment of capital, with a defined time horizon, expecting *risk-adjusted* growth via ownership of productive assets. It is distinguished from:

- **Speculation**: symmetric bets where the operator cannot demonstrate an edge; over time, outcomes cluster around zero (minus costs).
- **Gambling**: negative-expected-value activities; the house edge guarantees loss over sufficient repetitions.
- **Saving**: capital preservation without growth ambition (e.g. bank deposits at inflation-lagging rates).

AEGIS is an investing system — never a speculating or gambling one.

### 3.2  What is risk?

Risk is the probability, and expected magnitude, of **permanent capital loss**. It is measured against the operator's *actual usable capital* — not against a paper benchmark. Volatility is one *symptom* of risk but not risk itself: a position that swings ±30% weekly but always returns to entry is not risky (subject to psychological tolerance); a position that permanently gaps down 15% is.

### 3.3  What is uncertainty?

Uncertainty is the domain where AEGIS operates when it cannot honestly claim to know the underlying probability distribution — because it has never seen the current regime, because data are missing, because indicators disagree. AEGIS *acts as if* it operates in risk (with fitted distributions) but pays for the pretence with margins, kill switches, and Rule 8.

### 3.4  What is edge?

Edge is a **statistical advantage over the market average that is repeatable, robust, and empirically validated** (Article II, clause 2.4). AEGIS presumes small edge — a few basis points per position on average — and sizes accordingly. The system does not claim large edges. If a strategy appears to have Sharpe > 2 on a single sample, AEGIS treats this as *evidence of overfitting*, not of skill.

### 3.5  What is luck?

Luck is the residual variance in outcomes after accounting for skill and edge. Over N=285 positions, the observed Sharpe has a confidence interval roughly ± 0.6 around the true value. Most short-run performance is luck. AEGIS treats a strong recent quarter as *possibly lucky* and a weak recent quarter as *possibly unlucky*; response to both is *insufficient evidence to change parameters*.

### 3.6  What is skill?

Skill is what remains after luck is subtracted. Persistent across time, universe, and — critically — across independent implementations of the same idea. Skill withstands adversarial replication.

### 3.7  What is capital preservation?

Capital preservation is the maintenance of the operator's real (inflation-adjusted) purchasing power through time, subject to reasonable access and liquidity constraints. It is the *primary* objective of AEGIS (Article I). It is *not* the same as return maximisation; the two can conflict, and when they do, preservation wins.

### 3.8  What is antifragility?

Antifragility (Taleb) is the property of a system that *gains* from disorder — its performance improves under stress, rather than merely surviving. AEGIS is not fully antifragile; it aims for **robust with antifragile-adjacent features**:

- The self-learning engine (Article V) records failure modes, converting operational stress into long-term wisdom
- Kill switches (Article VII) cap downside but do not create upside from disorder
- Post-mortem discipline (§3.15) turns losses into learning

True antifragility would require *convex payoffs* from disorder (option-like positions that gain from volatility). AEGIS does not currently trade options; ARCH010 (Anti-Fragility) may propose partial antifragile mechanisms in v2+.

### 3.9  What is robustness?

Robustness is *insensitivity to specific input assumptions*. A robust decision performs well across many plausible scenarios, not just the base-case one. AEGIS's fractional-Kelly discipline (§3.3), regime-adaptive λ (§3.5), and hard-loss caps (Article VI) are all robustness mechanisms — each protects against a specific class of assumption failure.

### 3.10  What is resilience?

Resilience is the *ability to recover from stress events*. AEGIS's resilience mechanisms:

- Kill-switch → freeze → operator re-arms (Article VII)
- Post-mortem → learning → parameter proposal → shadow → paper → live (Article V + Article VII)
- Sealed baseline that cannot be corrupted by learning (Article VII, clause 7.1)

Resilience is measured by *time-to-recovery* after adverse events. AEGIS's target: recover to fully-operational status within one trading session of any single-day-loss event that does not breach the kill switch.

---

## 4.  The objective function — chosen, with reasoning

The user's ARCH001A prompt asks: *"Should AEGIS optimise for Maximum CAGR, Max Sharpe, Max Survival, Max Utility, Min Drawdown, Max Calmar, Max Sortino, Max Probability of Survival? Should objectives change with market regimes?"*

This section answers those questions definitively for CONSTITUTIONAL adoption.

### 4.1  Survey of candidate objective functions

| Candidate | Formula | Pros | Cons |
|:--|:--|:--|:--|
| **Max CAGR** | `arg max CAGR` | Simple; growth-oriented; matches investor intuition | Fragile to sequence risk; ignores drawdown; often achieved by leverage-to-ruin |
| **Max Sharpe** | `arg max (return / vol)` | Reward-per-risk framing; well-known | Treats vol as risk (violates §2.2); can be gamed with high-frequency low-vol strategies |
| **Max Sortino** | `arg max (return / downside_vol)` | Only penalises downside vol; closer to §2.2 | Still uses vol; ignores drawdown depth × duration |
| **Max Calmar** | `arg max (CAGR / |Max DD|)` | Explicitly penalises drawdown; matches operator intuition | Sensitive to single worst-drawdown event; noisy on short samples |
| **Min DD** | `arg min |Max DD|` | Extreme drawdown protection | Trivially achieved by 100% cash — no return |
| **Max Utility (Kelly log-wealth)** | `arg max E[log(W_T)]` | Mathematically optimal for long-run growth (ergodic); recovers Kelly sizing | Sensitive to edge estimation error; full Kelly is ruinous on estimated edges |
| **Max Probability of Survival** | `arg max P(W_T > W_0 - ε)` | Explicit survival | Trivially achieved by cash; ignores growth |
| **Fractional-Kelly log-utility + DD constraint** | `arg max E[log(W_T)]` s.t. `P(ruin) ≤ 1%` and `Max DD ≤ 20%` | Balances survival and growth; matches operator philosophy; robust to estimation error | Slightly more complex to implement; requires DD budget calibration |

### 4.2  AEGIS's chosen objective

The AEGIS objective function is **fractional-Kelly log-utility maximisation, subject to survival and drawdown constraints**:

```
maximise    E[ log(W_T) ]
subject to
    P( ruin over 10 years ) ≤ 1%           (survival)
    Max Drawdown over any 12-month window ≤ 20%    (drawdown)
    Every position has a computed max-loss ≤ 5% of portfolio    (Article VI Rule 6)
    Portfolio has an automated kill switch at −15% drawdown from peak    (ARCH002 L8.a)
    Kelly fraction applied ≤ 0.25 per position, ≤ 0.125 aggregate    (fractional Kelly, §3.3)
    All Article VI Rules 1–10 hold at all times.
```

**Why this and not the others.**

- Rejects **Max CAGR alone** because it violates Rule 4 (capital preservation overrides return maximisation).
- Rejects **Max Sharpe** because Sharpe treats volatility as risk (violates Article II clause 2.2).
- Accepts the *spirit* of **Max Calmar** in the drawdown constraint — Calmar's numerator is CAGR (log-utility approximation) and denominator is max DD (our DD constraint).
- Uses **log-utility** as the growth term because it is *ergodic* (per Kelly, Thorp, Peters) — the wealth path an individual actually experiences.
- **Fractional Kelly** rather than full Kelly because edge is estimated, not known (per Article II clause 2.4). Full Kelly on estimated edge is empirically ruinous.
- **Survival constraint** is the ultimate guardrail: even if every other rule is loosened, `P(ruin) ≤ 1%` remains.

### 4.3  Regime dependence of the objective

The *constraints* in §4.2 do not change with regime (they are invariant). The *aggressiveness* of the fractional-Kelly parameter does:

| Regime | Kelly fraction (per-position) | Aggregate fraction | Justification |
|:--|:-:|:-:|:--|
| Strong (trend, low vol) | 0.25 (baseline) | 0.125 | Kaminski-Lo: edge is more reliable in trends; Kelly closer to optimal |
| Neutral | 0.20 | 0.10 | Standard prudence |
| Weak (rangebound, elevated vol) | 0.15 | 0.075 | Kaminski-Lo: stops less effective; reduce sizing |
| Crisis (drawdown regime detected) | 0.10 | 0.05 | Prioritise survival; small positions only |
| Unknown | 0.05 | 0.025 | Rule 8: uncertainty → reduce |

Note: these fractions are illustrative. Final values will be established via ARCH003 (Risk Budgeting) evidence. **They are not adopted parameters yet.**

### 4.4  What AEGIS *never* optimises for (in isolation)

- **Return alone** (without a survival constraint) — violates Rule 1.
- **Volatility alone** (without an expected-return term) — trivially achieved by cash.
- **Sharpe alone** — uses the wrong risk definition (Article II clause 2.2).
- **Recent-period performance** — sample-size discipline (Article IV clause 4.4).
- **Aesthetic metrics** ("beautiful equity curve") — not decision-quality-relevant.

### 4.5  What AEGIS *always* optimises for (in the objective's spirit)

- **Long-run compounded log-wealth**
- **Survival over any decade-long horizon**
- **Robustness to edge-estimation error**
- **Calibrated confidence** (Article VIII clause 8.5)
- **Explainability** (Article VIII clause 8.2)
- **Auditability** (Article VII clause 7.4)

---

## 5.  The AEGIS Decision Hierarchy

Every decision, at every level (single position, portfolio, model, policy), traverses this hierarchy. Higher tiers *always* preempt lower tiers.

```
Tier 1  —  Protect Capital
                (Rules 1, 3, 7; ARCH002 L1, L8)
                    │
                    ▼
Tier 2  —  Preserve Optionality
                (keep cash, avoid over-commitment;
                 ARCH002 L0 admission gate; Rule 6)
                    │
                    ▼
Tier 3  —  Reduce Tail Risk
                (cap worst 1-5%; ARCH002 L2, L7; Rule 6, Rule 8)
                    │
                    ▼
Tier 4  —  Maintain Liquidity
                (never forced sale; ARCH002 L0 ADV gate;
                 no over-concentration; Article VII)
                    │
                    ▼
Tier 5  —  Exploit Edge
                (deploy only when the empirical
                 evidence supports advantage; Article IV)
                    │
                    ▼
Tier 6  —  Increase Returns
                (compound within all above constraints;
                 fractional Kelly, §3.3)
```

Reading the hierarchy: a decision that improves Tier 6 (return) but degrades Tier 1 (capital protection) is **rejected**. A decision that leaves Tier 1 unchanged but improves Tier 4 (liquidity) is *considered* (not automatically accepted). The higher the tier, the higher the burden of proof for a change.

---

## 6.  Trade-offs — explicit tension resolution

Every quant system has internal tensions. The Constitution resolves them explicitly to prevent future documents from re-litigating.

| Tension | Resolution | Where enforced |
|:--|:--|:--|
| Return vs Drawdown | Drawdown wins. Rule 2 / §4.2 constraint. | ARCH002 L1, L7 |
| CAGR vs Sharpe | CAGR-with-DD-constraint wins; Sharpe as diagnostic only | §4.2 objective |
| Sample size vs Statistical power | Sample size wins; no small-N claims | Article IV clause 4.4 |
| Adaptation vs Overfitting | Overfitting risk wins; supervised learning only | Article V clause 5.1 |
| Speed vs Robustness | Robustness wins; slow decisions preferred | Article VII clause 7.2 |
| Complexity vs Explainability | Explainability wins; if operator can't reconstruct why, don't ship | Article VIII clause 8.2 |
| Autonomy vs Auditability | Auditability wins; operator override always available | Article VIII clause 8.3-4 |
| AI capability vs Human authority | Human authority wins | Article VIII clause 8.3 |
| Backtest performance vs Live discipline | Live discipline wins; backtest is prior evidence, not blessing | Article IV + Article VII clause 7.2 |
| New data vs Sealed baseline | Sealed baseline wins for its scope; new data feeds new studies, not old sealed models | Article VII clause 7.1 |
| Recent regime vs Long history | Depends: long history dominant for parameter estimation; recent regime dominant for regime-classifier features | ARCH006 (to be written) |

Where a new document identifies a *new* tension not listed above, it must be added here via amendment (Article X).

---

## 7.  Ethics — expanded

Article VIII states the ethics clauses. This section elaborates each with practical examples of *what compliance looks like*.

### 7.1  Transparency (clause 8.1)

**Compliance means:**
- Every published recommendation has, in the audit trail: the code SHA that produced it, the data snapshot used, the score, the confidence, the exit plan (stop, target, expiry).
- Every override (operator or system) is recorded with timestamp, actor, and reason.
- The operator can, at any time, reconstruct the state at any prior date and re-derive what would have been recommended.

**Non-compliance means:**
- "Because the model said so" as the only explanation.
- Ephemeral parameters that are not versioned.
- Lost audit rows.

### 7.2  Explainability (clause 8.2)

**Compliance means:**
- Every Telegram/report has a *"Why"* section — the top reasons contributing to the recommendation.
- Confidence intervals accompany point estimates.
- Contributions of individual factors (momentum, quality, low-vol) are broken out where the model supports it.

**Non-compliance means:**
- Opaque neural-network scores with no attribution.
- Confidence numbers that cannot be tied to historical calibration.

### 7.3  Operator override (clause 8.3)

**Compliance means:**
- Every code path that *could* be blocked by an operator override *is* blocked.
- Override actions are logged, but never require justification to be effective.
- Override that *increases* risk is refused (Article VI Rule 7).

### 7.4  AI autonomy floor (clause 8.4)

**Compliance means:**
- No AI-produced code lands in production without the operator's explicit approval (currently: manual git review + commit).
- No AI-produced parameter change enters production without ARCH-doc + evidence + approval + shadow/paper/live phases.
- AI outputs are proposals, not executions.

**Non-compliance means:**
- Auto-tuning parameters in production based on recent performance.
- Automatic model retraining without operator sign-off.
- "AI approved by AI" as a governance shortcut.

### 7.5  Calibrated confidence (clause 8.5)

**Compliance means:**
- The confidence displayed on any recommendation has been empirically calibrated against historical outcomes.
- If historical 80-90% confidence bucket actually wins 60%, the system reports 60% (or a range), not 80-90%.
- Confidence calibration is a first-class LAB013 deliverable.

### 7.6  Advisory-only in v1 (clause 8.6)

**Compliance means:**
- The system produces recommendations; the operator executes.
- No API-based auto-execution against a broker.
- Broker integration is deferred to ARCH011 v2 with additional safeguards.

### 7.7  Failure honesty (clause 8.7)

**Compliance means:**
- When a rule cannot evaluate its inputs, it emits `RULE_UNEVALUABLE` in the audit — not a made-up "pass" verdict.
- When a data feed is stale, the pipeline halts, not silently proceeds with old data.
- When confidence returns null, the position is reduced (Rule 8), not held at full weight.

---

## 8.  How this Constitution applies to existing documents

At the time of drafting (2026-07-17), the following documents exist and must be evaluated for compliance with this Constitution:

| Document | Compliance status | Notes / actions |
|:--|:-:|:--|
| `docs/MON001_CERTIFICATION.md` | ✅ COMPLIANT | Sealed baseline discipline is Article VII clause 7.1 |
| `docs/OPS001-*.md` (all) | ✅ COMPLIANT | Pipeline discipline aligns with Article VII |
| `docs/ARCH001_RECOMMENDATION_LIFECYCLE.md` | ✅ COMPLIANT | Three-dates discipline aligns with Article VIII clause 8.7 |
| `docs/RISK001-A_EXIT_ANALYTICS.md` | ✅ COMPLIANT | Pre-registration and statistical hygiene match Article IV |
| `docs/RISK001-B_RISK_CONTROLLER_ARCHITECTURE.md` | ✅ COMPLIANT | The 6-rule Investment Constitution in RISK001-B §1 is subsumed by this Constitution's Article VI (Rules 1-10) |
| `docs/ARCH002_EXIT_FRAMEWORK.md` | ✅ COMPLIANT | Explicit reference at ARCH002 §15 to be updated post-approval |
| `docs/RESEARCH_ROADMAP_2026-2027.md` | 🟡 REVISION NEEDED | Add ARCH001A at position 1 of the priority order (updated in the same commit as this file) |
| `research/RISK001-A_RESULTS.md` | ✅ COMPLIANT | Statistical discipline; two verdicts presented honestly |

**On approval of this Constitution:**
- Update `docs/RESEARCH_ROADMAP_2026-2027.md` §1 status board to reflect ARCH001A at position 1
- Update `docs/ARCH002_EXIT_FRAMEWORK.md` §15 integration matrix to reference this Constitution as the parent
- Every future ARCH doc includes a "Compliance with ARCH001A" section in its integrity block

---

## 9.  Future evolution — what changes and what does not

**Never changes (INVARIANT clauses):**
- Article I clauses 1.1, 1.3, 1.4
- Article II clause 2.2 (definition of risk)
- Article III clause 3.2 constraints (survival + drawdown)
- Article V clause 5.1 (learning is bounded)
- Article VI Rules 1-10
- Article VIII clauses 8.3, 8.4 (operator override, AI autonomy floor)
- Article X clause 10.2 (invariance is invariant)

**Evolves through Article X amendment discipline:**
- The specific Kelly fractions in §4.3 (regime-dependent) — expected to be set via ARCH003 evidence
- The specific drawdown budget (20%) — reviewable via ARCH003
- The regime taxonomy (§4.3) — will be formalised by ARCH006
- The philosophical foundations (§2) — additions welcomed; removals require Article X amendment
- Integration with future ARCH003-ARCH016

**May be added:**
- New philosophical references
- New tensions and their resolutions (§6)
- New ethics clauses (Article VIII) — additive only, never subtractive without Article X

---

## 10.  Constitutional review discipline

**Cadence.** Reviewed annually (12 calendar months from adoption).

**Trigger events for extraordinary review:**
- A "black swan" market event that violates the survival constraint
- A regulatory environment change materially affecting the mission
- A major shift in AEGIS's operational structure (e.g. adding external investors)
- An operator-declared review

**Review process:**
- Read this document end-to-end
- Cross-reference against the current live behaviour of AEGIS
- Identify gaps: places where AEGIS *behaves* differently from what the Constitution *requires*
- File amendments (Article X) to reconcile

**Review output.** A `docs/CONSTITUTIONAL_REVIEWS/YYYY-MM-DD_review.md` document recording findings and any amendments filed.

---

## 11.  Absolute non-negotiables (summary)

If any single statement in this document is elevated above every other clause, these are they. Amendment requires retiring the whole Constitution.

1. **Never lose capital unnecessarily.**
2. **Preserve capital before pursuing return.**
3. **The operator has final authority. Always.**
4. **No AI change in production without explicit operator approval.**
5. **Risk means permanent capital loss. Not volatility.**
6. **Uncertainty defaults to reducing exposure. Never increasing it.**
7. **Every claim requires evidence collected under Article IV discipline.**
8. **The sealed baseline is byte-invariant. Only the MON001 ceremony can amend it.**
9. **Audit trails are append-only. Nothing is deleted.**
10. **Operator override always works. No configuration disables it.**

---

## 12.  Signatures — approvals required for CONSTITUTIONAL status

This document is in **DRAFT** status until:

1. Operator's explicit written approval (recorded in `docs/APPROVALS_LOG.md`, to be created)
2. Cross-check that every existing ARCH / RISK / OPS / MON doc is compliant (this pass done in §8 above; must be re-affirmed at approval time)
3. Version stamp: `ARCH001A v1.0` on approval; content hash recorded
4. Constitutional Amendments Log created

**Once approved:** every future document, every implementation, every parameter change flows through this document.

---

## 13.  Integrity + sign-off

- Sealed files touched: **0**
- Production code touched: **0**
- Parameters tuned: **0**
- MON001 fingerprint: `e4c070673568c52d…` (unchanged, verified at time of drafting)
- `cumulative_strategy_search`: **38** (unchanged)
- Approvals required: operator sign-off + `docs/APPROVALS_LOG.md` entry + version stamp
- **Effective date:** upon operator approval (currently pending)
- **Version:** DRAFT / v0.9 (proposed v1.0 on approval)

---

## 14.  Change log

| Date | Change | Author | Version |
|:--|:--|:--|:--|
| 2026-07-17 | Initial draft: 10 Articles, philosophical foundations, objective function chosen, decision hierarchy, ethics framework | AEGIS engineering | DRAFT / v0.9 |
