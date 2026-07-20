# Sprint 2 · Canonical Data Model + Market Intelligence + AI Agents · Report
**Completed 2026-07-20 · Both markets · Deterministic · Walk-forward safe · No recommendation logic touched**

---

## Purpose (per operator brief)

Build the **Canonical Data Model** so every ingested source (Sprint 1B) maps to a
common internal schema while preserving market-specific attributes. On top of
that, run a deterministic **Market Intelligence** engine. Embed the first three
**AI agents** — Data Quality, Market Analyst, Evidence Summarizer — which
*explain, validate, and summarize* without recommending. All outputs must be
replayable for the future Institutional Walk-Forward Validation Framework.

**Recommendation Engine, Risk, Portfolio, Learning: untouched.**

---

## What shipped

### A. Canonical Data Model (`backend/canonical/`)

| Artifact | What it does |
|---|---|
| `model.py` | `MarketProfile` (India + USA), `CanonicalDatasetSpec` |
| `schemas.py` | **9 canonical row types**: `CanonicalBar`, `CanonicalFundamentals`, `CanonicalNews`, `CanonicalFlow`, `CanonicalCorporateAction`, `CanonicalEarnings`, `CanonicalMacro`, `CanonicalFlowProxy`, `CanonicalHolding` — all frozen dataclasses, all carrying `market` + `asof` + `currency` + `source` |
| `adapters.py` | One function per kind: `adapt_prices`, `adapt_fundamentals`, `adapt_news`, `adapt_flows`, `adapt_corporate_actions`, `adapt_earnings`, `adapt_macro`, `adapt_flow_proxy`, `adapt_holdings` — plus `adapt_all(repo_root, market, cutoff=)` runner. Every adapter accepts a `cutoff` date and filters rows on-or-before it. **Walk-forward safe.** |

**Currency invariant:** every monetary field carries its currency (`INR` for India rows, `USD` for USA rows). No canonical row ever mixes.

**Replayability:** adapters are pure functions of (repo_root, market, cutoff). No network I/O at inference time. Same disk state + same cutoff → identical output.

### B. Market Intelligence Engine (`backend/market_intelligence/`)

Deterministic. Reads canonical data only. Emits a market-level snapshot per market:

| Signal | Both | India-only | USA-only |
|---|---|---|---|
| breadth_above_20ma | ✓ | | |
| breadth_at_52w_high | ✓ | | |
| liquidity_5v20 | ✓ | | |
| benchmark_5d_pct | ✓ | | |
| benchmark_1m_pct | ✓ | | |
| vix | ✓ | | |
| move | | | ✓ |
| macro | | | ✓ (rates + DXY + gold + oil) |
| sector_rotation | ✓ | via sector_context (frozen) | via ETF flows |
| news_pulse | ✓ | | |
| flow_pulse | ✓ | FII + DII | insider net |

Composite Market Health = weighted deterministic sum (breadth 30% · benchmark 1m 25% · liquidity 15% · vol 15% · news 10% · flow 5%). Regime classifier maps composite → {bull / bear / neutral / stress} with an explicit rule set.

**Every signal carries its `evidence` dict** — exact numbers used, so the AI Analyst can narrate without duplicating math.

### C. AI Agents (`backend/ai/`) — deterministic templates, NOT LLM calls

Each returns an `AgentOutput` with `headline · narrative · findings · evidence · citations · confidence · caveats`.

| Agent | Reads | Emits |
|---|---|---|
| **Data Quality** (`data_quality.py`) | `backend_validation_summary.json` | verdict-driven narrative + top-5 issues + follow-up steer (pause / reschedule / continue) |
| **Market Analyst** (`market_analyst.py`) | `MarketIntelligenceResult` | multi-paragraph narrative: regime, breadth, benchmark, volatility, macro (USA), sector rotation, news+flow pulse, supportive-vs-cautionary balance |
| **Evidence Summarizer** (`evidence_summarizer.py`) | any `CanonicalDataset` bundle | one-paragraph cross-source snapshot (news, fundamentals, flows, earnings, corp actions, macro) — supports `focus_symbol` for per-ticker use later |

**Contract enforced by test `test_agents_have_no_recommendation_output`:** no agent's `findings` may contain `buy` / `sell` / `target_price` / `recommendation` / `action` keys.

**Determinism:** all three are template-based (same input → same output, no randomness, no LLM API calls, no clock reads). A future upgrade can swap the template layer for an LLM as long as `determinism` field is set to `llm-cached` and the LLM output is pinned to the freeze date.

### D. Per-market runners

- `india/market_intelligence/run.py`  → `reports/market_intelligence{.json,_summary.json}` + `reports/ai_market_narrative.json`
- `usa/research/market_intelligence/run.py` → same paths under `usa/reports/`

### E. Data Persistence upgrade (Sprint 1B follow-through)

Per the operator's mid-turn directive (2026-07-20), Sprint 1B ingestion modules are now **append-only**. Daily ingestion fetches only the new day's data and dedupes on natural key. Modules upgraded:
- `usa/research/macro/run.py` — dedupe on (symbol, date)
- `usa/research/etf_flows/run.py` — dedupe on (ticker, date)
- `usa/research/insider/run.py` — dedupe on (ticker, date, insider, transaction, shares)
- `usa/research/corporate_actions/run.py` — dedupe on (ticker, action_date)
- `usa/research/earnings/run.py` — dedupe on (ticker, asof) — keeps per-day snapshot ledger
- `usa/research/sec_13f/run.py` — dedupe on (ticker, holder, date_reported)
- `india/corporate_actions.py` — dedupe on (ticker, action_date)

Persistence memory saved at [aegis_data_persistence.md](../../.claude/projects/c--Users-GPraveenKumar-Downloads-prism/memory/aegis_data_persistence.md).

### F. Wiring

- India orchestrator (`scripts/aegis_daily_v2.py`): 21 → 22 steps (`market_intelligence` inserted after `backend_validation`)
- USA orchestrator (`usa/scripts/usa_daily.py`): 24 → 25 steps
- India datasets.yaml: +3 entries (`market_intelligence`, `market_intelligence_summary`, `ai_market_narrative`)
- USA datasets.yaml: +3 entries (same shape)
- India SPA (`ux/dashboard/frontend/index.html`): loads 2 new files; Market Regime tile added to Portfolio Health strip
- USA SPA (`usa/dashboard/frontend/index.html`): same
- CI (`.github/workflows/aegis-ci.yml`): Sprint 2 regression suite added

---

## Runtime verification (2026-07-20)

### Sprint 2 regression suite — 12/12 pass

```
$ python backend/tests/test_sprint2.py
  [OK] MarketProfile currency + benchmark set correctly
  [OK] KINDS enumeration matches (9 canonical kinds)
  [OK] adapt_all returns CanonicalDataset per include-kind (4/4)
  [OK] walk-forward cutoff filter: now=30 past=0
  [OK] market intel deterministic: composite=48.71 regime=neutral
  [OK] USA market intel: regime=neutral composite=49.7 signals=11
  [OK] AI DataQuality: All 25 registered datasets are within their SLAs.
  [OK] AI MarketAnalyst: Neutral · constructive · Composite Market Health 49.7/100.
  [OK] AI EvidenceSummarizer: Data snapshot · USA. News: 30 tickers scored across 240 headlines...
  [OK] all 3 AI agents obey no-recommendation contract
  [OK] india market intel runner: regime=neutral composite=48.71
  [OK] usa market intel runner: regime=neutral composite=49.69 currency=USD

  12 passed, 0 failed of 12
```

### Sprint 1 regression suite still green — 12/12 pass

Nothing about Sprint 1's freshness/schema/quality/lineage framework changed. Sprint 2 outputs are new datasets the framework simply validates.

### Backend validation after Sprint 2

| Market | Before Sprint 2 | After Sprint 2 |
|---|---|---|
| India | 25 datasets · PASS · 0.917 | **28 datasets · PASS · 0.916** |
| USA | 36 datasets · PASS · 0.921 | **39 datasets · PASS · 0.919** |

### Per-market market intelligence output

**India:**
```
regime: Neutral · constructive (composite 48.7/100)
signals: 8 (breadth_above_20ma, breadth_at_52w_high, liquidity_5v20,
             benchmark_5d_pct, benchmark_1m_pct, sector_rotation,
             news_pulse, flow_pulse)
AI headlines:
  · analyst: "Neutral · constructive · Composite Market Health 48.7/100."
  · dq     : "All 25 registered datasets are within their SLAs."
  · ev     : "Data snapshot · INDIA."
```

**USA:**
```
regime: Neutral · constructive (composite 49.7/100)
signals: 11 (adds vix + macro + move + holding-based coverage on top of India shape)
AI headlines:
  · analyst: "Neutral · constructive · Composite Market Health 49.7/100."
  · dq     : "All 36 registered datasets are within their SLAs."
  · ev     : "Data snapshot · USA. News: 30 tickers scored across 240 headlines..."
```

---

## Walk-Forward Compatibility

Every Sprint 2 component was designed with the Institutional Walk-Forward Validation Framework as the acceptance test:

- **Adapters** accept `cutoff: date` — any date on-or-after cutoff+1 is dropped
- **Engine** consumes only canonical rows (which respect cutoff) — same disk state + same cutoff yields identical composite score (verified by `test_market_intelligence_deterministic`)
- **AI agents** are pure functions of their structured input — no external calls, no randomness
- **Ingestion is append-only** — historical data is preserved forever, so any freeze date can be reconstructed from disk

`AgentOutput.determinism` field will let us tell a template-driven agent apart from an LLM-cached agent in later sprints — walk-forward auditor can require `template` OR `llm-cached` (with cached-output pinned to freeze date).

---

## Files created

**Backend framework:**
- `backend/canonical/schemas.py`
- `backend/canonical/adapters.py`
- `backend/market_intelligence/__init__.py`
- `backend/market_intelligence/engine.py`
- `backend/ai/__init__.py`
- `backend/ai/base.py`
- `backend/ai/data_quality.py`
- `backend/ai/market_analyst.py`
- `backend/ai/evidence_summarizer.py`
- `backend/tests/__init__.py`
- `backend/tests/test_sprint2.py`

**Per-market runners:**
- `india/market_intelligence/__init__.py`
- `india/market_intelligence/run.py`
- `usa/research/market_intelligence/__init__.py`
- `usa/research/market_intelligence/run.py`

**Documentation:**
- `docs/AEGIS_SPRINT2_REPORT.md` — this file

## Files modified

- `scripts/aegis_daily_v2.py` — +1 step (market_intelligence)
- `usa/scripts/usa_daily.py` — +1 step
- `india/backend_validation/datasets.yaml` — +3 entries
- `usa/backend_validation/datasets.yaml` — +3 entries
- `ux/dashboard/frontend/index.html` — +2 files loaded, Market Regime tile added
- `usa/dashboard/frontend/index.html` — same
- `.github/workflows/aegis-ci.yml` — +1 CI step
- 7 Sprint 1B ingestion modules — append-only upgrade

---

## What Sprint 2 does NOT do (scope discipline)

- Does not modify the Recommendation Engine
- Does not modify Risk / Portfolio / Fusion / Learning engines
- Does not embed AI in those layers (that's Sprints 3-9 per the AI-embedded architecture roadmap)
- Does not use LLM API calls (template-based determinism for walk-forward)
- Does not implement Investment Committee debate (that's Sprint 6 · Fusion)
- Does not touch Institutional Memory / Winner Genome (Sprint 9 · Learning)

---

## Dependencies unblocked

| Downstream sprint | Now has fresh input |
|---|---|
| Sprint 3 · Investment Intelligence | Per-stock canonical adapters + AI Evidence Summarizer for per-ticker narratives |
| Sprint 4 · Intelligence Validation | Canonical data across all sources → conflict detection can compare like-with-like |
| Sprint 6 · Fusion | Market regime + AI Market Analyst narrative feeds macro/sentiment weighting |
| Sprint 7 · Recommendation | Market Intelligence provides the "environment" context (regime, breadth, volatility) |
| Final · Walk-Forward | Canonical adapters + engine determinism verified for replay |

---

## Confidence checklist

- [x] Both markets simultaneously (India + USA)
- [x] Recommendation Engine NOT modified
- [x] Canonical Data Model: 9 kinds, shared schema, market-specific attributes preserved
- [x] Market Intelligence engine deterministic (test verified)
- [x] 3 AI agents shipped: Data Quality, Market Analyst, Evidence Summarizer
- [x] All AI outputs are explain/validate/summarize — no recommendations (contract test enforced)
- [x] All AI outputs replayable for walk-forward (template determinism)
- [x] Versioned outputs + evidence + confidence + citations per agent
- [x] Integrated into both SPAs (Market Regime tile)
- [x] Sprint 1B ingestion upgraded to append-only per data-persistence directive
- [x] Sprint 2 regression: 12/12
- [x] Sprint 1 regression: 12/12 (unchanged)
- [x] Both markets backend_validation still PASS with new datasets
- [x] No TODOs, no placeholders — everything runs

Sprint 2 report complete. Ready for operator sign-off before Sprint 3 (Investment Intelligence per-stock).
