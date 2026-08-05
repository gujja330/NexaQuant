# AEGIS · Context Intelligence Layer · Architecture Spec

**Ticket ID:** `RL-CIL`
**Signed into force:** 2026-08-05
**Status:** SPEC LOCKED · scaffold shipped · full build in Phase 2 (starts 2026-09-09)
**Author:** CEO (AI · fully delegated authority per operator directive 2026-08-05)
**Governance:** Article IX + Article X · binding on all future engine work

---

## 1 · The problem this solves

Every recommendation runner today (R1 · R2 · future R3) answers *"what's
the highest-scoring stock from my model?"* · none answer *"is that
recommendation still appropriate given what changed in the world since
my features were computed?"*

Example (operator-flagged 2026-08-05):
- TCS scores rank #1 in R2 based on historical features
- Overnight: NASDAQ futures weak · IT sector selling globally · AI names red
- **Institutional PM would immediately reduce TCS conviction**
- **Current AEGIS still says "TCS · rank #1 · BUY"**

The gap is not a missing data feed — most context data already exists in
`macro_regime.json` · `sector_rotation.json` · `currency_intelligence.json`
· `bond_intelligence.json` · `volatility_intelligence.json` ·
`commodity_intelligence.json` · `fii_dii_flow.json` · `ai_news_narrative.json`.

The gap is a **consumer layer** that reads all of them and modulates
recommendation confidence, position sizing, and state.

---

## 2 · The one design principle (Article IX inheritance)

**The Context Intelligence Layer does NOT generate recommendations.**

It answers exactly one question · per recommendation · every day:

> *"Given everything that changed since this stock's features were computed,
> should I increase confidence · reduce confidence · shrink position size ·
> delay entry · trigger review · or exit?"*

Stock selection stays with runners. Context adjustment stays with the layer.
Never mixed. Ever.

---

## 3 · Where it sits in the pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  DATA INGEST (existing)                                       │
│  · price bars · fundamentals · news · earnings                │
│  · FII/DII · options · macro · commodities                    │
└──────────────────────────┬───────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  RUNNERS (stock selection · UNTOUCHED)                        │
│  · Runner 1 (SEALED · adaptive_rec_v2)                        │
│  · Runner 2 (v3 canonical)                                    │
│  · Runner 3 (SHADOW · RL-Runner3)                             │
└──────────────────────────┬───────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  CONTEXT INTELLIGENCE LAYER (NEW)                             │
│                                                                │
│   ┌────────────────────────────────────────────────┐         │
│   │ 15 CONTEXT ENGINES (feed into layer)             │         │
│   │                                                    │         │
│   │  · Global Economic Calendar    (NEW · Phase 2A)  │         │
│   │  · Earnings Calendar           (partial · lift)  │         │
│   │  · Macro Engine                (exists)          │         │
│   │  · Sector Engine               (exists)          │         │
│   │  · News Engine                 (exists)          │         │
│   │  · Market Breadth              (NEW · Phase 2B)  │         │
│   │  · Sector Breadth              (partial · lift)  │         │
│   │  · Correlation Engine          (exists)          │         │
│   │  · Institutional Flow          (exists)          │         │
│   │  · Options Positioning         (partial)         │         │
│   │  · Currency Engine             (exists)          │         │
│   │  · Bond Yield Engine           (exists)          │         │
│   │  · Volatility Engine           (exists)          │         │
│   │  · Commodity Engine            (exists)          │         │
│   │  · Global Risk Engine          (NEW · Phase 2C)  │         │
│   └──────────────────────┬─────────────────────────┘         │
│                            ▼                                    │
│   ┌────────────────────────────────────────────────┐         │
│   │  CIL CONSUMER (per recommendation)               │         │
│   │  Reads all context engine outputs                │         │
│   │  Applies contribution weights                    │         │
│   │  Emits: Final Confidence · State Change · Alert  │         │
│   └────────────────────────────────────────────────┘         │
└──────────────────────────┬───────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  PORTFOLIO / DELIVERY (existing)                              │
│  · portfolio_manager.py · Telegram XLSX                       │
└─────────────────────────────────────────────────────────────┘
```

**All runners consume the same context layer.** Zero duplication across
R1 · R2 · R3.

---

## 4 · The 15 context engines · what exists · what's new

| # | Engine | Data source | Status | Consumed today? |
|---|---|---|---|---|
| 1 | Global Economic Calendar | RBI/Fed/ECB/etc + earnings dates | **NEW · Phase 2A** | — |
| 2 | Earnings Calendar (per ticker) | free exchange bulletins | partial (usa/earnings.parquet) | R3 features_free only |
| 3 | Macro Engine | reports/macro_regime.json | ✅ exists | ⚠️ R006 buffer only |
| 4 | Sector Engine | reports/sector_rotation.json | ✅ exists | ⚠️ Health Score sector factor |
| 5 | News Engine | reports/ai_news_narrative.json | ✅ exists | ❌ ignored |
| 6 | Market Breadth | advancers/decliners per index | **NEW · Phase 2B** | — |
| 7 | Sector Breadth | sector-level A/D | partial (sector_rotation) | ❌ ignored |
| 8 | Correlation Engine | reports/correlation_matrix.json | ✅ exists | ❌ ignored |
| 9 | Institutional Flow | reports/fii_dii_flow.json | ✅ exists | ⚠️ R3 features_free only |
| 10 | Options Positioning | NSE F&O feed | partial | ⚠️ R3 features_free only |
| 11 | Currency Engine | reports/currency_intelligence.json | ✅ exists | ❌ ignored |
| 12 | Bond Yield Engine | reports/bond_intelligence.json | ✅ exists | ❌ ignored |
| 13 | Volatility Engine | reports/volatility_intelligence.json | ✅ exists | ❌ ignored |
| 14 | Commodity Engine | reports/commodity_intelligence.json | ✅ exists | ❌ ignored |
| 15 | Global Risk Engine | wars · tariffs · elections | **NEW · Phase 2C** | — |

**Score:** 10 of 15 engines already produce data. 5 need building. All 15
are unused by confidence today. **This is a wiring problem, not a data
problem.**

---

## 5 · The CIL consumer · contribution model

Per-recommendation adjustment formula (transparent · reproducible):

```
Adjusted Confidence = Base Confidence
    + Macro Contribution        (weight 0.15 · range ±15)
    + Sector Contribution       (weight 0.15 · range ±15)
    + Breadth Contribution      (weight 0.10 · range ±10)
    + News Contribution         (weight 0.10 · range ±10)
    + Earnings Contribution     (weight 0.10 · range ±10)
    + Vol / Risk Contribution   (weight 0.10 · range ±10)
    + Currency Contribution     (weight 0.05 · range ±5)
    + Bond Contribution         (weight 0.05 · range ±5)
    + Institutional Flow        (weight 0.10 · range ±10)
    + Portfolio Concentration   (weight 0.10 · range ±10)

Clamped to [0, 100].
```

**Total adjustment cap: ±20 points** on any single recommendation per day
(prevents whipsaw). Weights overridable via `configs/context_weights.json`
· default weights above are the starting spec.

Each context engine returns a **contribution object** the CIL consumer
composes:

```python
@dataclass
class ContextContribution:
    engine_name: str
    contribution_pts: float       # positive = boost · negative = drag
    reason: str                   # human-readable · goes into Story col
    severity: str                 # info · warning · critical
    data_available: bool          # False = ignored in composition
```

---

## 6 · Recommendation State Machine (per CIL output)

The CIL doesn't just adjust confidence — it triggers state transitions:

```
BUY  ─┬─▶  BUY (no change)
      ├─▶  WATCH        (context drag −5 to −10)
      ├─▶  REVIEW       (context drag −10 to −15)
      ├─▶  REDUCE       (context drag > −15 · reduce position 50%)
      └─▶  EXIT_URGENT  (multiple critical severity signals)

HOLD ─┬─▶  HOLD
      ├─▶  WATCH        (health degradation)
      └─▶  REDUCE       (aggregate drag > −15)
```

Fires the existing Alert column in XLSX · surfaces in Story column.

---

## 7 · Recommendation Review Triggers (event-driven)

Beyond daily runs · re-evaluate immediately when:

| Trigger | Threshold | Action |
|---|---|---|
| Sector drops | > −2% intraday | mark all sector positions REVIEW |
| VIX spikes | +18% | reduce all sizes by 30% · tighten stops |
| Fed / RBI announcement | scheduled | pre-emptively reduce affected sector positions |
| Major earnings miss | affected sector | REVIEW all sector positions |
| Stock gaps | > 3% overnight | REVIEW that specific ticker |
| Portfolio concentration | > sector cap | reject new adds · propose trim |
| FII/DII flow reversal | > 2σ vs 20d mean | reduce confidence globally |
| Geopolitical event | manual flag | operator sets · CIL reads |

Event listener is Phase 2D · not required for Phase 2A launch.

---

## 8 · Phased delivery · 3 sub-phases

### Phase 2A · Foundation (Days 1-14 · 2026-09-09 to 2026-09-23)
- Economic Calendar data ingest (RBI + Fed + earnings)
- CIL scaffold with 4 initial engine adapters (Macro · Sector · Vol · News)
- Basic contribution model wired into Health Score
- One end-to-end example: TCS row shows base confidence 39% · context drag −8 · adjusted 31%

### Phase 2B · Full coverage (Days 15-30 · 2026-09-24 to 2026-10-08)
- 10 more engine adapters (all existing context engines wired)
- Market Breadth Engine (NEW)
- State machine transitions live
- XLSX gets 3 new columns: `Adj Conf` · `Ctx Drag` · `Ctx Reason`

### Phase 2C · Event triggers (Days 31-45 · 2026-10-09 to 2026-10-23)
- Global Risk Engine (NEW)
- Event listener + review triggers
- Sector drop > 2% intraday auto-flag
- VIX spike auto-size-reduce

### Phase 2D · Consolidation (Days 46-60 · 2026-10-24 to 2026-11-03)
- Backfill CIL adjustments on 30-day historical window
- Compare "adjusted vs raw" outcomes via feature_attribution rollup
- Ship CIL performance report as monthly rollup
- **Aligned with Runner 3 Day-90 CEO decision** (2026-11-03)

---

## 9 · Isolation constraints (Article X · same discipline as R3)

- CIL never modifies runner-owned files (recommendations.json etc.)
- CIL writes ONLY to `reports/context/*`
- CIL is optional in the daily orchestrator
- CIL failure never blocks Telegram delivery
- All runners keep their raw confidence unchanged · CIL emits ADJUSTED
  confidence as a separate field · never overwrites base

Testable via `backend/tests/test_cil_isolation.py` (added in Phase 2A).

---

## 10 · Success criteria (pre-registered · Article X)

Phase 2D completion gates:
- Historical replay shows CIL-adjusted confidence has better Brier score
  than raw confidence over the same window
- Sector-drop event triggers correctly on 3+ historical high-vol days
- Portfolio concentration adjustment kicks in on positions that would
  breach sector cap
- Adjusted-vs-raw XLSX comparison shows operator can trust it before
  removing raw

If Phase 2D success criteria fail: CIL stays in shadow mode · adjusted
confidence displayed but not used for portfolio sizing.

---

## 11 · What ships TODAY (before Phase 2 starts)

Three preparation items · zero freeze violation:

1. **This document** (spec locked)
2. **Economic Calendar data-only ingest** (data gates itself · needs 30
   days of collection before Phase 2 can use it)
3. **CIL scaffold** — empty package structure with pluggable adapter
   interface · so Phase 2A opens the day of Runner 3 Day-30 gate and
   immediately fills in adapters vs building infrastructure

---

## 12 · Signed

**CEO (AI):** 2026-08-05 · full authority per operator delegation
**Governance:** Article X (Evidence-First Promotion)
**Amends:** `docs/AEGIS_CEO_DECISION_2026-08-05.md` Phase 2 slot
**Blocks:** any new engine that duplicates CIL responsibilities
