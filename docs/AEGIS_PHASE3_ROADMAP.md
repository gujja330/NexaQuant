# AEGIS · Phase 3 · Institutional Intelligence Layer
### LOCKED 2026-07-21

**Status:** Roadmap locked. Phase 2 remains (Sprints 8/9/10). Phase 3 begins AFTER Sprint 10.
**Operator directive:** After Sprint 10 · Research Factory, STOP adding core execution engines. From that point onward the highest return on effort is enriching the intelligence layer — using the historical data, macro context, and factor library already built to generate better insights.

---

## Guiding Principle

> Don't ask "what new engine?" — ask "how do existing engines become smarter?"

Adding more isolated modules to a pipeline that already has 14 dilutes signal. Phase 3 modules are **layered on top of** the existing engines. They enrich what the six existing AI Analysts see. They don't replace anything and they don't produce new production actions.

---

## Locked Roadmap

```
Phase 1  ✅ SHIPPED — Sprints 1 → 7.5
──────────────────────────────────────────────────────────────
  Feature Store · Feature Intelligence · Model Factory ·
  Recommendation v3 · Risk · Portfolio · Learning · Macro Intel ·
  Execution Simulator · Persistence + Factor Library

Phase 2  ⚪ REMAINING
──────────────────────────────────────────────────────────────
  Sprint 8   Institutional Walk-Forward Validation
  Sprint 9   Institutional AI Auditor  (EXPANDED — see §Sprint 9)
  Sprint 10  Research Factory

Phase 3  ⚪ INSTITUTIONAL INTELLIGENCE LAYER
──────────────────────────────────────────────────────────────
  1. Market Memory Engine
  2. Event Intelligence
  3. Relationship Graph
  4. Institutional Explainability
  5. Scenario Engine
  6. Strategy Lab
  7. Portfolio Optimizer
  8. Institutional Dashboard

  ⛔ No further core engines after Phase 3.
```

---

## Sprint 9 · Institutional AI Auditor (EXPANDED)

Previously scoped as "AI Validation Auditor" — accuracy metrics. **Expanded scope:** for every failed (and every winning) trade, produce a **multi-dimensional root-cause report**.

Questions the Auditor MUST answer:

| Dimension | Example finding |
|---|---|
| Macro | "Regime flipped RISK_OFF the day after entry" |
| Commodity | "Oil +9% between entry and exit — position was in an airline" |
| Sector | "Sector was laggard in the rotation regime at entry" |
| Currency | "USD strengthened 3%; the stock was an IT exporter beneficiary — actually a tailwind we underweighted" |
| Yield | "10Y +30 bps in the horizon; the stock was a rate-sensitive REIT" |
| Model | "Model X and Y disagreed; ensemble split resolved to HOLD but confidence was 0.51 (just above threshold)" |
| Feature | "Momentum score decayed by 40% between entry and exit; not caught" |
| Execution | "Fill slippage 80 bps vs modelled 25 bps" |
| Risk sizing | "Volatility scaling used 20-day; realized 60-day was 1.6× that" |
| Portfolio allocation | "Position was 4.8% while the ex-post-Kelly optimal was 1.2%" |
| Timing | "Entered at day+3 relative to a 5-day mean-reversion cycle bottom" |

**Deliverable:** `reports/ai_auditor_per_rec.json` — one record per closed recommendation, with dimension scores that add up to explain the outcome.

**Not deliverable:** a scalar accuracy number. That belongs in Sprint 8 Walk-Forward metrics.

---

## Phase 3 · Module Specifications

### 1. Market Memory Engine ⭐

**One-liner:** Deterministic recall — "have we seen this before?"

Reads the Sprint 7.5 history parquets (macro_history · factor_library_history · recommendation_history · execution_history) and answers similarity queries against past state.

```
Query:  Oil +9%,  VIX = 28,  USD strong
Answer: Seen 6 times in the last 5Y.
        Average Auto return = -8%
        Average Energy return = +11%
        3 of 6 preceded a >5% correction in the next 20 sessions.
```

**Not AI.** Just SQL/DuckDB on the history parquets. No new agent — the existing Macro Analyst and Recommendation Analyst *consume* Memory Engine output.

**Storage:** DuckDB on top of the Sprint 7.5 parquets (read-only view).

---

### 2. Event Intelligence ⭐

Detects and normalizes:

`Fed · RBI · War · Election · Tariff · Hurricane · Earthquake · Lockdown · Budget · Earnings · Merger · Guidance`

For each event, produces a link to affected `companies / industries / sectors / macro factors`.

**Feeds:** Recommendation Analyst (why a name is being downgraded), AI Auditor (was there an event around the failure window), Scenario Engine (replay this event's shock).

**Data sources (free):**
- Fed / RBI: official RSS + press-release scraping
- Elections / policy: Wikipedia + government RSS
- Earnings: yfinance calendar
- Hurricanes / earthquakes: NOAA / USGS APIs (free)
- Corporate actions: yfinance + NSE/BSE public disclosures

---

### 3. Relationship Graph ⭐

Today:
```
Oil → Airlines
```

Tomorrow:
```
Oil → Transportation → Airlines → IndiGo → Margins → Profit → EPS → Recommendation
```

**Implementation:** `networkx` DiGraph loaded from `configs/relationship_graph.yaml` (operator-owned taxonomy). The Sprint 6.5 impact matrix and knowledge graph feed the top edges; industry / company / feature / recommendation edges extend downward.

**Consumers:** Explainability (walk the graph to justify a call), Scenario Engine (propagate a shock), AI Auditor (attribute failure to a link on the chain), Research Factory (discover missing edges).

---

### 4. Institutional Explainability ⭐

Replaces `"BUY (confidence 0.72)"` with:

```
BUY  ·  RELIANCE
  Macro         82%   RISK_ON regime · oil bull · WTI +6% 1w
  Sector        76%   Energy leader in current rotation
  Commodity     91%   WTI +6% 1w · Brent +5% 1w (Impact Matrix: Energy +)
  Feature       84%   Momentum + Trend agree · low drawdown pos_52w = 0.87
  Model         73%   7 of 11 models agree (BUY/STRONG_BUY)
  Risk           APPROVED   sized at 3.2% (Kelly-fractional · below cap)
  Portfolio      APPROVED   would raise HHI to 0.14 (still <0.20 cap)
```

**Implementation:** aggregate scores already produced by Rec/Risk/Portfolio engines — no new computation, just a consolidated view. Uses the Relationship Graph to name the *reason* per dimension.

---

### 5. Scenario Engine ⭐

**Deterministic simulation, not prediction.** Replays a hypothetical macro shock through the current portfolio using the Relationship Graph and historical elasticities from Market Memory.

```
Q:  Fed cuts 100 bps — what happens?
A:  Sectors benefiting  : Banks (+3.2%), REITs (+4.1%), Growth (+2.7%)
    Sectors hurt        : Insurers (-1.8%), Money-market (-0.4%)
    Portfolio impact    : +₹142,000 (1.42% AUM) expected value
    Portfolio VaR change: -80 bps (risk falls)
    Comparable episodes : 3 (2020-03, 2019-07, 2008-12)
```

**Not AI. Not prediction.** Historical elasticities × current portfolio weights × Relationship Graph propagation.

---

### 6. Strategy Lab ⭐

Auto-generates strategies from the existing model factory:

`Momentum · Mean Reversion · Quality · Value · Macro · Sector Rotation · Dividend · Low Volatility`

Runs each through Sprint 8 Walk-Forward. Produces a side-by-side comparison. Operator promotes (or doesn't) via Sprint 2.6 human-in-loop gate.

**Not a new engine.** A configuration layer over the existing Model Factory + Walk-Forward.

---

### 7. Portfolio Optimizer ⭐

Adds one layer AFTER portfolio construction:

```
Today:      Risk → Portfolio
Tomorrow:   Rec → Macro → Risk → Portfolio → Optimizer → Efficient Frontier → Final
```

**Implementation:** cvxpy or scipy.optimize (both free, MIT/BSD). Constraints already encoded in Sprint 5 (HHI cap, per-sector cap, cash reserve). Optimizer chooses the point on the frontier that best satisfies the Constitution's fractional-Kelly + survival + drawdown objective.

Does NOT replace Sprint 5 — sits after it as an optional final polish. Falls back gracefully to Sprint 5's output if optimization fails.

---

### 8. Institutional Dashboard ⭐

Not another JSON. A **live web dashboard** consolidating:

`Market · Macro · Portfolio · Execution · Learning · Factors · Risk · AI · Research · Alerts`

**Stack (free):** Plotly Dash or Streamlit. Reads existing reports/*.json + reports/*.parquet + reports/*_history.parquet. Zero new data — just a good view over what already exists.

---

## Hard Constraints (INVARIANT)

1. **NO new AI agents.** Six exist (Rec · Risk · Portfolio · Learning · Macro · Execution Analyst). That is the full set. If a Phase 3 module wants AI narration, it uses one of the six.

2. **NO new core execution engines** after Sprint 10. The last "engine" module is Research Factory. Everything after is intelligence layer.

3. **Free / open-source stack ONLY.**
   - Market data: `yfinance` · Stooq · FRED · ECB · RBI · MOSPI · NSE/BSE public data
   - Storage: Parquet + **DuckDB** (add alongside for analytical queries)
   - Search: SQLite / DuckDB indexes
   - Graphs: `networkx`
   - Embeddings (optional): `sentence-transformers`
   - Vector search (optional): FAISS
   - Scheduling: cron / Windows Task Scheduler / GitHub Actions
   - Visualization: Plotly Dash or Streamlit
   - Optimization: `cvxpy` / `scipy.optimize`
   - No paid APIs. Ever.

4. **Human-in-loop for promotion** remains binding. All Phase 3 modules are descriptive/analytical. None auto-promote or auto-execute.

5. **Sealed OPS001 / MON001 files untouched.** Fingerprint `b65ceb49a83a` preserved.

6. **Contract:** Phase 3 modules follow the same rule as Sprint 6.5+ — no `buy/sell/target_price/recommendation/action/promoted/approved` keys in their outputs. They describe, they don't decide.

7. **Walk-forward safety:** Every Phase 3 module accepts a historical `asof` cutoff so it can be replayed by Sprint 8.

8. **Append-only history:** Every Phase 3 module that produces daily state gets a `<name>_history.parquet` via the Sprint 7.5 `backend/persistence` layer.

---

## What This Roadmap Deliberately Does NOT Do

- ❌ It does not add "Sprint 11" as a new engine. The next natural expansion is Phase 3, not Sprint 11.
- ❌ It does not add a 7th AI Analyst.
- ❌ It does not add another recommendation engine.
- ❌ It does not add more model types to the Model Factory (11 is enough).
- ❌ It does not introduce a paid data provider.

---

## Success Definition

Phase 3 is done when a new operator can look at any trade in the system and, within 30 seconds, answer:

- Why did the system recommend it?
- What macro/event/factor conditions were in place?
- What did the system expect to happen?
- What actually happened?
- Which dimension of the pipeline was responsible for the outcome?

No new *actions* — just a much richer understanding of every action already produced.

---

**End of Phase 3 Roadmap · Locked 2026-07-21**
