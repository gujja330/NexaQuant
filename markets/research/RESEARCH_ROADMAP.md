# AEGIS Research Programs

Research is organized into **Programs**, not isolated cycles. A Program owns one dataset/theme and contains
several pre-registered experiments (RCs). Every experiment ends in exactly one verdict — **PROMOTE /
INVESTIGATE / REJECT** — and appends a row to `LEADERBOARD.csv`. Nothing is ever "implemented"; things are
promoted on evidence or rejected. Executive rollup: `RESEARCH_DASHBOARD.md` (auto-generated).

Standards for every experiment live in `docs/AEGIS_RESEARCH_HANDBOOK.md` (PIT, leakage embargo, promote
bar, significance). The framework engine (`core/usa_research.py`) is **LOCKED** — experiments parameterize
it, they don't rewrite it.

**Tracking artifacts:** `registry/DATASET_REGISTRY.csv` (what data exists + status), `registry/
FEATURE_CATALOG.csv` (every feature + status + IC), `registry/EXPERIMENT_REGISTRY.csv` (planned work, vs
the Leaderboard which holds results), `datasets/SEC_SCORECARD.md` (score a dataset before using it),
`RESEARCH_TIMELINE.md` (quarterly view), `RESEARCH_DASHBOARD.md` (auto rollup).

---

## Where we are (2026-06-29)
- **Program 0 — Infrastructure Expansion** ✅ COMPLETE → `experiments/PROGRAM0_comparison.md`. Deeper history
  (2y→up to 64y) + SEC coverage (74→208) showed **every static-fundamental & naive-earnings lead was a
  2024–26 small-sample artifact** (all flat under power). The gate held; nothing false was promoted.
- **Strategic pivot:** stop recombining ROE/margin/EPS/debt/revenue — proven flat on this universe. Move to
  **genuinely different information domains** (alternative data), one at a time, same discipline.
- **Now executing:** Program 1.1 — SEC Form 4 insider (RC005).
- **AI (Program 4) is last** — only after ~100+ validated features exist (today: ~0 USA-validated).

Higher-level program arc (split by information domain): **0 Infrastructure ✓ → 1 Insider (active) →
2 Analyst → 3 ETF/Holdings → 4 Options/Volatility → 5 Macro → 6 ML Ranking (last)**. Each is a distinct
data domain, run one at a time, same gate. The lettered sections below are the detailed cycle inventory.

## MACRO ROADMAP — complete BOTH R&D tracks before any market decision (no early optimization)
The USA-research / India-production split is **DEFERRED** (see `MARKET_DECISION.md`) — it was premature.
Only the market-agnostic core is locked. The strategic sequence:
1. **Complete India R&D** — every domain through the identical gate (tracker: `DOMAIN_COVERAGE.md`).
2. **Complete USA R&D** — same pipeline, same methodology.
3. **Cross-market validation** — universal vs market-specific factors.
4. **Portfolio simulation** — India-only / USA-only / 50-50 / 70-30 / dynamic, identical assumptions.
5. **Capital-allocation & product decision** — where our money goes + what AEGIS recommends, from evidence.
Immediate order: finish **RC005** → close the ⬜ domains in `DOMAIN_COVERAGE.md` for both markets → freeze
both libraries → portfolio sims → final decision. Goal: no major research area left unexplored in EITHER
market before deciding anything.

## Program A — Fundamentals (SEC EDGAR)   ·   STATUS: ✅ CLOSED — **REJECTED**
- **RC001 — composite & decomposition** ✅ CLOSED → `RC001_sec_fundamentals.md`. 2y leads (growth +, ROE
  inverse) were **shown FLAT on 14y by Program 0** → all static ratios NOT PROMOTED (confident rejection).
- Do NOT spend more cycles recombining these ratios on this universe; the cross-sectional edge is ~0.

## Program 1 — Alternative Data (ACTIVE, priority order)
1. **RC005 — Insider (SEC Form 4)** ▶ PILOT running. Open-market net buy (P−S), 90d, PIT filed date.
2. **RC006 — Analyst revisions** (estimate/target/recommendation changes). Needs a source.
3. **RC007 — Institutional flows (13F)** quarterly holdings / manager changes.
4. **RC008 — ETF holdings/flows** (sector + thematic).
5. **RC009 — Macro & market structure** (curve, credit, DXY, VIX) — as a regime conditioner.

## Program B — Earnings Intelligence   ·   STATUS: designed, not started
- **RC002 — Surprise:** SUE / surprise vs naive expectation; post-earnings drift 1–60d. PIT = 8-K/10-Q
  `filed`. Hypothesis: positive surprise drifts up; stronger in smaller names. Pitfall: announcement-date
  accuracy; short event windows → embargo care.
- **RC003 — Guidance:** management guidance direction/revisions vs prior. Pitfall: unstructured text, sparse.
- **RC004 — Revisions:** trend in reported fundamentals (revisions momentum). Pitfall: free estimates scarce.

## Program C — Insider Activity (SEC Form 4)   ·   STATUS: designed, not started
- **RC005 — Net buy:** net open-market purchase value (code P), 90d. PIT = `filed` (≤2 business days).
- **RC006 — CEO/officer buy:** weight by insider role (CEO/CFO > director). 
- **RC007 — Cluster buy:** multiple insiders buying in a window (strongest signal in literature).
- Pitfalls: 10b5-1 planned-sale noise; size-normalise; sparse events → pooled IC.

## Program D — ETF Intelligence   ·   STATUS: designed, not started
- **RC008 — Flows:** sector/thematic ETF creation-redemption flow → member stocks.
- **RC009 — Holdings:** holdings changes / weight drift.
- **RC010 — Sector rotation:** flow-implied rotation vs `core/sector_intelligence.py` scores.
- Pitfalls: single-stock flow attribution is indirect; short-interest is lagged/low-frequency.

## Program E — Macro (FRED)   ·   STATUS: designed, not started
- **RC011 — Rates** · **RC012 — Yield curve** · **RC013 — Credit spreads** · **RC014 — Dollar (DXY).**
- Hypothesis: macro is a **conditioner** (when to tilt growth vs defensive), not a stock-level alpha — likely
  best as a regime overlay (cf. India: the whole edge was the regime overlay).
- Pitfall: few independent macro regimes in short history → severe power/overlap problem; don't fit
  regime boundaries to returns.

## Program F — News / Sentiment   ·   STATUS: designed, not started
- **RC015 — Sentiment** · **RC016 — Topics** · **RC017 — Event detection.**
- Hypothesis: short-lived (days), decays fast, likely dies after costs. Pitfall: publish-timestamp
  look-ahead; spurious correlation.

## Program G — AI Models   ·   STATUS: designed, not started (enters AFTER factor programs have signal)
- **RC018 — Learning-to-Rank:** rank stocks from all validated features. **RC019 — Meta-rank:** blend
  program signals. **RC020 — Dynamic weights:** regime-conditioned weighting. **RC021 — Regime clustering.**
- Hard rule: AI consumes only features that already passed their program's gate; learned weights are
  walk-forward + embargoed (the RC001.2 0.287 leakage lesson is mandatory here).

---

## Sequencing principle
Don't open a new program just because one closed. Finish extracting a program's signal (decompose +
explain, as RC001 did) and log every result first. Cross-market lift (works in BOTH India and USA) is the
strongest evidence and the basis for promoting a feature into the shared library → India Lab → production.
