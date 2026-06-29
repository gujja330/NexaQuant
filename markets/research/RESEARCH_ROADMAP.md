# AEGIS Research Programs

Research is organized into **Programs**, not isolated cycles. A Program owns one dataset/theme and contains
several pre-registered experiments (RCs). Every experiment ends in exactly one verdict — **PROMOTE /
INVESTIGATE / REJECT** — and appends a row to `LEADERBOARD.csv`. Nothing is ever "implemented"; things are
promoted on evidence or rejected. Executive rollup: `RESEARCH_DASHBOARD.md` (auto-generated).

Standards for every experiment live in `docs/AEGIS_RESEARCH_HANDBOOK.md` (PIT, leakage embargo, promote
bar, significance). The framework engine (`core/usa_research.py`) is **LOCKED** — experiments parameterize
it, they don't rewrite it.

---

## Program A — Fundamentals (SEC EDGAR)   ·   STATUS: open, RC001 closed
The first program. Free, official, point-in-time via `filed` dates.
- **RC001 — composite & decomposition** ✅ CLOSED → `RC001_sec_fundamentals.md`
  - Verdict: composite NOT PROMOTED (failed by cancellation). Leads: revenue growth (+, 🟡), ROE (inverse,
    🔴 as a positive factor). Robust to sector/size/regime. Open risk: ROE-inverse may be a 2024–26 artifact.
- **RC00x (future, same dataset):** valuation factors (P/E, P/B, FCF yield), quality-as-short, the
  growth-tilt/ROE-inverse blend tested directly — each as a new RC row.

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
