# ARCH018 — Institutional Sector Intelligence Engine

## The Sector Tier Between Global Context and Stock Selection

**Document type:** Constitutional design · Market Intelligence Layer (Phase 2)
**Status:** DRAFT · design only · NO code · NO parameter tuning · NO production changes
**Owner role:** Chief Investment Officer · Head of Research · Head of Sector Coverage
**Author:** AEGIS engineering
**Date opened:** 2026-07-17
**Parent constitution:** [`ARCH001A_INVESTMENT_PHILOSOPHY.md`](ARCH001A_INVESTMENT_PHILOSOPHY.md) — compliant with Articles I, II, III, IV, VII, VIII
**Parent data model:** [`ARCH017A_MARKET_DATA_CANONICAL_MODEL.md`](ARCH017A_MARKET_DATA_CANONICAL_MODEL.md) — every field name, timestamp, confidence value inherited
**Upstream inputs:** [`ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md`](ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md) — global composites + classifications feed sector modulation
**Downstream consumers:** ARCH018A (Company) · ARCH019 (Regime) · ARCH020 (Graph) · ARCH021 (Dependency) · ARCH022 (Memory) · ARCH023 (Attribution) · ARCH024 (Adaptive Holding) · ARCH025 (Adaptive Exit)
**Sealed files touched:** 0. Production code touched: 0. Parameters tuned: 0.

---

## 0.  Preamble & non-negotiables

1. This document is **constitutional design**. Nothing is implemented; no ingest job authored; no production pipeline changed.
2. ARCH018 sits between ARCH017 (Global) and ARCH018A (Company). It answers the question *"which sectors are worth exposure today, and in what proportion?"*
3. Every field name, every confidence value, every classification enum used below is inherited from ARCH017A. If a downstream consumer wants a new field, it is added to ARCH017A first, then referenced here.
4. **ARCH018 never emits BUY / SELL / EXIT.** It publishes sector scores, sector confidence, sector allocations, and sector-conditional advisory hints. The recommendation engine and RISK001-C consume these as inputs; they do not replace them.
5. Parameters shown (weight tables, thresholds, rotation triggers) are v1 draft — **not adopted**. Adoption requires evidence per §21 validation and operator approval per §23 rollout.

---

## 1.  Mission

AEGIS today evaluates *companies*. Institutional investors evaluate:

```
Global Markets   ← ARCH017 (delivered as design)
       │
       ▼
Macroeconomy     ← ARCH017 (delivered as design)
       │
       ▼
Country          ← ARCH017 (delivered as design)
       │
       ▼
Sector           ← ARCH018 (this document)
       │
       ▼
Industry         ← ARCH018 (this document, at sub-sector level)
       │
       ▼
Company          ← ARCH018A (planned; the next design after this one)
       │
       ▼
Portfolio        ← AEGIS existing recommendation + RISK001-C
```

ARCH018 fills the sector tier. Without it, ARCH018A cannot ask *"is this company good given its sector context?"* and the recommendation engine cannot ask *"is this sector worth exposure right now?"*.

The mission has five sub-goals:

1. **Score every sector daily** with an explainable 0–100 composite.
2. **Rank sectors** relative to each other and to the global regime.
3. **Detect sector rotation** — when leadership changes, and when a sector's trend is exhausted.
4. **Allocate capital** across sectors, subject to portfolio-level constraints from ARCH001A Article III + ARCH002.
5. **Feed downstream consumers** (ARCH018A / ARCH019 / ARCH020 / ARCH023 / ARCH024 / ARCH025) with the sector context they each need.

---

## 2.  Scope

### 2.1  In scope

- Sector taxonomy for the Indian equity universe + optional global mapping (§5)
- Macro-to-sector transmission (§6) and global-to-sector transmission (§7)
- Sector Strength Model: 13-dimension composite (§8)
- Sector confidence, per-horizon (§9)
- Sector rotation engine (§10)
- Sector allocation engine with portfolio-level constraints (§11)
- Sector correlation, diversification, crowding, concentration (§12)
- Sector lifecycle model (§13)
- Sector dependency graph (feeds ARCH020) (§14)
- Sector news intelligence integration (feeds from ARCH026) (§15)
- Output contract (§17), consumer table (§18), validation methodology (§21)

### 2.2  Out of scope

- Company-level scoring (ARCH018A)
- Cross-sector regime labelling (ARCH019 — richer taxonomy than ARCH018's macro-cycle labels)
- Knowledge-graph traversal semantics (ARCH020)
- Portfolio construction across sectors (final HRP consumes sector inputs; ARCH005 will re-examine)
- LLM-based news processing (ARCH026 — this doc consumes ARCH026's output, does not replicate it)
- Trading decisions (RISK001-C + recommendation engine)
- Options / futures / cross-currency hedging
- Foreign-market single-name sector work

---

## 3.  Institutional practice survey

Public information only. Each firm's *approach* is documented; proprietary specifics are neither known nor claimed.

### 3.1  Asset managers and index providers

| Firm | What they publicly do with sectors | What ARCH018 borrows |
|:--|:--|:--|
| **BlackRock** | iShares sector ETFs; monthly sector outlook publications; *"BlackRock Sector Rotation Index"* is a public strategy that rotates among GICS sectors based on macro cycle position | Business-cycle-conditional sector weights (§6.4, §13); allocation matrix |
| **AQR Capital** | Extensive academic publication on cross-sectional and industry momentum (Asness, Moskowitz, Pedersen) | Industry momentum as a first-class score component (§8.1) |
| **Bridgewater** | *"All Weather"* framework partitions the world into growth-up / growth-down / inflation-up / inflation-down; sectors sorted by their sensitivity to each | 2×2 macro-regime × sector matrix (§6.5) |
| **Fidelity** | *"Sector Watch"* and *"Business Cycle Approach to Sector Investing"* white papers publicly detail early-cycle / mid-cycle / late-cycle / recession sector tilts | Sector-lifecycle framework (§13); sector-cycle mapping (§13.2) |
| **Goldman Sachs** | Global Investment Research publishes sector momentum, valuation, positioning composites; *"Sector-Neutral Alpha"* is a public product framing | Multi-dimensional sector composite (§8) |
| **JP Morgan** | *"Guide to the Markets"* quarterly publishes sector heatmaps; asset-management sector rotation strategies | Sector heatmap output format (§17.3) |
| **MSCI** | GICS (Global Industry Classification Standard) — the industry-standard sector taxonomy. 11 sectors, 25 industry groups, 74 industries, 163 sub-industries | Adopt GICS as the *canonical* sector taxonomy where compatible; NSE taxonomy as the *domestic* overlay (§5) |
| **Morningstar** | Publishes sector Style Box, sector-level valuation metrics (fair-value ratio), sector economic-moat aggregates | Sector valuation dimension (§8.6); sector-quality signal (§8.11 stability) |
| **State Street (SPDR)** | Sector-SPDR ETFs; monthly sector monitor with momentum, valuation, breadth | Multi-dimensional monitor structure (§8) |
| **Invesco / Vanguard** | Passive sector ETFs; publish sector-specific fund-level flow data | Flow signal (§8.13) |
| **S&P Dow Jones** | Sam Stovall's *"S&P Sector Investing"* — public framework tying sector performance to business-cycle phase | Sector-lifecycle mapping (§13.2), same as Fidelity |
| **NSE Indices** | Nifty sector indices — 8 headline: Auto / Bank / Financial Services / FMCG / IT / Media / Metal / Pharma; plus Realty, Energy, PSU Bank | Domestic sector universe (§5.2) |

### 3.2  Meta-observation

Every practitioner surveyed converges on the same five signals as the sector-selection core:

1. **Trend / momentum** (relative strength vs benchmark)
2. **Valuation** (aggregate P/E, P/B, forward earnings yield)
3. **Breadth** (fraction of sector constituents participating in the trend)
4. **Fundamentals** (earnings revisions, guidance surprises)
5. **Flow / positioning** (fund flows, institutional ownership changes)

Every firm adds proprietary layers on top — macro overlays, LLM-tagged news, positioning data from prime brokerage. But the core five are universal. ARCH018 §8 uses them as *dimensions*, expanded to thirteen for tighter signal separation.

---

## 4.  Academic literature

### 4.1  Sector rotation and business cycles

- **Sam Stovall (S&P)** — "Standard & Poor's Guide to Sector Investing" (public framework). Classifies sectors by cycle phase: early-cycle (Financials, Consumer Discretionary), mid-cycle (Industrials, IT), late-cycle (Energy, Materials, Consumer Staples), recession (Utilities, Healthcare, Consumer Staples).
- **Fidelity (Denis Mikula, Dirk Hofschire)** — "The Business Cycle Approach to Sector Investing." Extends Stovall with empirical evidence that sector leadership persists 6-12 months after cycle transitions.
- **Jacobsen & Zhang (2013)** — "Are Monthly Seasonals Real? A Three Century Perspective" — sector-level Halloween effect. Seasonality confirmed at sector granularity.
- **Chen, Roll & Ross (1986)** — "Economic Forces and the Stock Market" — foundational paper on macro factor → sector returns.

### 4.2  Industry momentum

- **Moskowitz & Grinblatt (1999)** — "Do Industries Explain Momentum?" JF. Industry momentum is a large fraction of stock momentum. Rotating into strong-industry, weak-industry loser stocks doesn't work; single-stock momentum is largely an industry effect.
- **Grinblatt & Han (2005)** — "Prospect Theory, Mental Accounting, and Momentum." Behavioural underpinning.
- **Hong, Torous & Valkanov (2007)** — "Do Industries Lead Stock Markets?" — some industries (petroleum, metals, retail) *lead* the aggregate market by 1-2 months.
- **Menzly & Ozbas (2010)** — "Market Segmentation and Cross-predictability of Returns." Cross-industry predictability via customer-supplier links → informs ARCH020 (Knowledge Graph).
- **Cohen & Frazzini (2008)** — "Economic Links and Predictable Returns." Customer-supplier link returns predict stock returns → informs dependency graph.

### 4.3  Relative strength and cross-sectional momentum

- **Asness, Moskowitz, Pedersen (2013)** — "Value and Momentum Everywhere." Sector momentum works cross-country.
- **Novy-Marx (2013)** — "The Quality Dimension of Value Investing." Extends factor framework to sector level.

### 4.4  Sector correlation and diversification

- **Longin & Solnik (2001)** — "Extreme Correlation of International Equity Markets." Correlations spike in crises; naive diversification fails when it's needed most.
- **Chua, Kritzman, Page (2009)** — "The Myth of Diversification." Same idea at sector granularity — sector correlations rise sharply in drawdowns.

### 4.5  Intermarket analysis

- **John Murphy (1991)** — "Intermarket Analysis." Sector propagation through commodities → equity sectors. Foundational for §7 (global variables to sectors).

### 4.6  Sector crowding

- **Khandani & Lo (2011)** — "What Happened to the Quants in August 2007?" Sector-neutral quant strategies crowded → sudden unwind → massive drawdown. Motivates §12 (crowding metric).

### 4.7  Diffusion and leadership

- **Menzly, Santos & Veronesi (2004)** — "Understanding Predictability." Industry-conditional predictability of returns.
- **Diebold & Yilmaz (2012)** — "Better to Give Than to Receive: Predictive Directional Measurement of Volatility Spillovers." Sector-level spillover indices — used in §14 (dependency graph edges).

### 4.8  Consequence for ARCH018

- **Sector momentum is real and robust** — supported across markets and decades (Moskowitz-Grinblatt; Asness et al).
- **Sector-cycle mapping is real** — the Stovall / Fidelity framework isn't overfit; it captures a genuine pattern (though the pattern's timing is noisy).
- **Correlations spike in crises** — sector diversification is a fair-weather claim. §12 caps sector concentration accordingly.
- **Lead-lag effects exist** — some sectors reliably lead the market (Hong-Torous-Valkanov). This is exploited in §10 (rotation) and §14 (dependency graph).
- **Overcrowding costs money** — sector positioning matters as much as sector merit. §12 tracks crowding.

Every ARCH018 design choice below traces to at least one paper or public practitioner source.

---

## 5.  Sector taxonomy

### 5.1  Two-level structure

- **Sector** — the top level. 11-13 sectors depending on classification.
- **Industry** (sub-sector) — the next level. ~25-30 industries in the Indian universe.

Individual companies are mapped to exactly one industry and inherit its sector.

### 5.2  Canonical taxonomies

Three sector systems are relevant:

| System | Coverage | Levels | Use in ARCH018 |
|:--|:--|:-:|:--|
| **GICS** (MSCI / S&P) | Global | Sector → Industry Group → Industry → Sub-Industry | *Reference* taxonomy for cross-country context |
| **ICB** (FTSE Russell) | Global | Industry → Supersector → Sector → Subsector | Reference only; not authoritative in ARCH018 |
| **NSE Sectoral Indices** | India | Sector level only | *Authoritative* domestic taxonomy for AEGIS's tradable universe |

The Indian universe is mapped as follows (v1 draft, tenant-generic — the actual mapping lives in a runtime `sector_map.yaml` per ARCH001A Article VII clause 7.6):

**Sectors:** Financials · IT · Consumer Discretionary · Consumer Staples · Energy · Materials · Industrials · Healthcare · Utilities · Communication Services · Real Estate · Autos (India-specific split) · Chemicals (India-specific)

**Industries within Financials:** Banks · NBFC · Insurance · Asset Management · Housing Finance · Brokers · Payments

**Industries within IT:** IT Services · Software Products · IT-enabled Services · Hardware

**Industries within Consumer Staples:** FMCG · Personal Care · Food · Beverages · Household Products

**Industries within Consumer Discretionary:** Auto · Auto Ancillaries · Retail · Apparel · Media · Hotels

... (full mapping in the runtime file; this doc shows the shape, not the values)

### 5.3  Mapping discipline

- Every AEGIS-universe ticker has exactly one industry mapping.
- The industry-to-sector mapping is many-to-one.
- Mapping is versioned via `sector_map_version` (semver). Reclassifications preserve historical rows under the old version — critical for reproducibility (ARCH001A Article VII clause 7.8).
- Mapping is tenant-generic — no ticker-specific special cases in code; all in the runtime file.

### 5.4  Where GICS and NSE disagree

Occasionally NSE's sectoral index and GICS assign a stock differently. ARCH018 resolves in favour of the *revenue-source* mapping (per S&P DJ methodology): where does the company get most of its revenue? This is documented per-ticker in the mapping file so ARCH018 doesn't re-litigate at query time.

---

## 6.  Macro variables → sectors

The transmission matrix. Each row = macro variable; each cell = expected direction of impact on the sector.

### 6.1  Interest rates (RBI repo / US Fed Funds / India 10Y yield)

| Sector | Rate ↑ impact | Rationale |
|:--|:-:|:--|
| Banks | Positive | NIM expansion, but only if loan growth persists |
| NBFC | Mixed | Cost-of-funds up; margin pressure unless pricing power exists |
| Real Estate | Negative | Mortgage rates up; demand slows |
| Auto | Negative | Financing costs up; demand-elasticity moderate |
| IT | Mixed | Discount-rate effect on valuation multiples; USD-INR partly offsets |
| Utilities | Negative | High-leverage sector; refinancing cost up |
| FMCG | Marginally negative | Discount-rate impact on valuation multiples |
| Oil & Gas | Neutral to positive | Commodity pricing dominant; less rate-sensitive |
| Gold-related | Positive | Investment demand for real assets |
| Healthcare | Mixed | Pharma resilient; hospitals rate-sensitive |
| Infra | Negative | Capital-intensive; higher hurdle rate |

### 6.2  Inflation

| Sector | High inflation impact |
|:--|:-:|
| FMCG | Negative (input costs + demand elasticity) |
| Auto | Negative (input steel/aluminium + rate transmission) |
| Metals | Positive (pricing power in inflation) |
| Energy | Positive (commodity thesis) |
| Cement | Positive to negative (mixed — pricing power vs energy costs) |
| Banks | Positive short-term (NIM), negative long-term (asset quality) |
| Real Estate | Positive real-asset thesis; but rate effect dominates |
| Consumer Staples | Negative (margin compression) |

### 6.3  GDP growth

| Sector | Rising GDP impact |
|:--|:-:|
| Consumer Discretionary | Positive (income elasticity) |
| Financials | Positive (credit demand) |
| Industrials | Positive (capex cycle) |
| Auto | Positive |
| Consumer Staples | Weakly positive (defensive) |
| Utilities | Weakly positive |
| Healthcare | Neutral |

### 6.4  Business-cycle mapping (Stovall / Fidelity framework)

Sector leadership by cycle phase — public framework used by BlackRock, Fidelity, S&P DJ, adopted here.

| Phase | Sectors expected to lead | Sectors expected to lag |
|:--|:--|:--|
| **Early cycle** (recovery) | Financials, Consumer Discretionary, Industrials, Real Estate | Utilities, Consumer Staples |
| **Mid cycle** (expansion) | IT, Communication Services, Industrials, Materials | Utilities, Healthcare |
| **Late cycle** | Energy, Materials, Consumer Staples, Healthcare | Consumer Discretionary, IT |
| **Recession** | Consumer Staples, Utilities, Healthcare | Financials, Consumer Discretionary, Industrials, Real Estate |

Note: this table is *empirical*, not causal. AEGIS uses it as a *prior*, not a directive. Actual sector scores in §8 dominate.

### 6.5  Bridgewater 2×2 (growth × inflation)

| | **Growth up** | **Growth down** |
|:--|:--|:--|
| **Inflation up** | Materials, Energy, Cyclicals | Gold-mining, Utilities, Staples |
| **Inflation down** | IT, Consumer Disc, Industrials | Consumer Staples, Utilities, Long-duration bonds |

Consumed as a *modulator* on §8 base score, not as a direct override.

---

## 7.  Global variables → sectors (intermarket)

Following Murphy (1991) and the operator's operator-provided example. Each row is a global variable; cells indicate which sectors move in what direction.

### 7.1  Oil (Brent / WTI)

| Direction | Sectors affected |
|:--|:--|
| Oil ↑ | Energy (upstream) ↑ · Paints ↓ (input cost) · Airlines ↓ · Tyres ↓ (natural rubber correlated) · Logistics ↓ · Refiners (downstream) mixed (marketing margin squeeze) |
| Oil ↓ | Energy ↓ · Consumer Discretionary ↑ (higher disposable income) · Airlines ↑ · Auto ↑ |

### 7.2  Copper

| Direction | Sectors affected |
|:--|:--|
| Copper ↑ | Metals ↑ · Electricals & Cables ↑ · EV components ↑ · Real Estate (indirect via construction demand) ↑ |
| Copper ↓ | Growth signal weakening; defensives rotate up |

### 7.3  US Dollar (DXY / USD-INR)

| Direction | Sectors affected |
|:--|:--|
| USD ↑ (INR ↓) | IT ↑ (export margins expand in INR terms) · Pharma ↑ (export earnings) · Textiles ↑ (export) · Consumer Staples ↓ (import cost of oil, edible oil) · Metals mixed |
| USD ↓ (INR ↑) | Reverse of above; capital-inflow narrative supports Financials |

### 7.4  US 10Y bond yield

| Direction | Sectors affected |
|:--|:--|
| US 10Y ↑ | Growth sectors (IT, high P/E consumer) ↓ (discount-rate effect); Value sectors (Financials, Energy) relatively better |
| US 10Y ↓ | Growth sectors ↑; long-duration assets bid |

### 7.5  Gold

Gold as a safe-haven signal; not directly consumed by AEGIS positions but consumed as a *regime* input feeding §9 sector confidence.

### 7.6  Volatility (VIX / India VIX)

High VIX correlates with defensive-sector outperformance (Utilities, Consumer Staples, Healthcare). Consumed by §10 rotation logic.

### 7.7  Global equity indices

Global sector correlations (e.g. Nasdaq → Indian IT) are captured in §14 (dependency graph). Not a direct override; enters through the dependency-weighted score adjustment in §8.14.

---

## 8.  Sector Strength Model — the 13-dimension composite

The heart of ARCH018. Each sector, every day, gets 13 sub-scores that combine into a single 0–100 composite. All 13 dimensions register against ARCH017A schemas.

### 8.1  Sector momentum

- **Sub-score:** `norm.sector.<name>.momentum`
- **Underlying:** Sector index price / total-return series
- **Metrics:** 20-day, 60-day, 120-day momentum (blended)
- **Normalisation:** `zscore_rolling_252d` (ARCH017A §6.2)
- **Direction:** Higher = trending up
- **Weight in composite:** 0.15 (v1 draft)
- **Empirical support:** Moskowitz-Grinblatt (1999); Asness-Moskowitz-Pedersen (2013)

### 8.2  Sector breadth

- **Sub-score:** `norm.sector.<name>.breadth`
- **Underlying:** Fraction of sector constituents above 50-DMA and 200-DMA; new-52w-high count vs new-52w-low
- **Direction:** Higher = broad participation
- **Weight:** 0.10
- **Empirical support:** Menzly-Santos-Veronesi (2004); classic technical analysis

### 8.3  Sector volume

- **Sub-score:** `norm.sector.<name>.volume`
- **Underlying:** Sector-aggregate turnover relative to 90-day median; unusual-volume day frequency
- **Direction:** Higher = accumulating; supported by fund flow
- **Weight:** 0.05
- **Failure mode:** volume can spike on distribution too — must be joint with momentum (§8.1) to be meaningful

### 8.4  Sector relative strength

- **Sub-score:** `norm.sector.<name>.rs_nifty`
- **Underlying:** Sector index / Nifty 50 ratio; 20d and 60d slope
- **Direction:** Higher = outperforming benchmark
- **Weight:** 0.15
- **Empirical support:** Hong-Torous-Valkanov (2007)

### 8.5  Sector earnings tone

- **Sub-score:** `norm.sector.<name>.earnings_tone`
- **Underlying:** Aggregate 4-quarter EPS growth; earnings-surprise rate (proportion of constituents beating consensus); guidance-revision direction
- **Direction:** Higher = beating and raising
- **Weight:** 0.15
- **Note:** Requires earnings dataset per ticker; source-tier depends on availability

### 8.6  Sector valuation

- **Sub-score:** `norm.sector.<name>.valuation`
- **Underlying:** Aggregate forward-P/E percentile within sector's own 10-year history; also EV/EBITDA where meaningful
- **Direction:** Higher = *cheaper* (undervalued) → higher sector score (contrarian bias)
- **Weight:** 0.08
- **Empirical support:** Novy-Marx (2013)
- **Caveat:** Valuation is *slow-moving* — a cheap sector can stay cheap. Combined with momentum for the "value + momentum" thesis.

### 8.7  Sector liquidity

- **Sub-score:** `norm.sector.<name>.liquidity`
- **Underlying:** Median ADV within the sector's tradable universe; bid-ask spread aggregate
- **Direction:** Higher = deep, tradable
- **Weight:** 0.03
- **Purpose:** Feeds ARCH018A admission gates (per ARCH002 L0). A sector with declining liquidity gets a lower score to reduce admissions.

### 8.8  Sector sentiment

- **Sub-score:** `norm.sector.<name>.sentiment`
- **Underlying:** Put-call ratio at sector level (if F&O data available); analyst-recommendation aggregate; social-media sentiment (deferred to ARCH026 for LLM ingest)
- **Direction:** Higher = supportive
- **Weight:** 0.04
- **Failure mode:** Sentiment is a lagging + contrarian indicator; interpret carefully

### 8.9  Sector news intelligence

- **Sub-score:** `norm.sector.<name>.news_signal`
- **Underlying:** LLM-tagged news signal from ARCH026 — earnings tone, regulatory tone, policy tone, geopolitical tone, ESG-event tone
- **Direction:** Higher = positive news flow
- **Weight:** 0.05
- **Note:** Deferred to ARCH026 delivery; until then, `confidence = 0` on this component; the score is redistributed.

### 8.10  Sector volatility

- **Sub-score:** `norm.sector.<name>.volatility`
- **Underlying:** Realised 20-day annualised volatility percentile within the sector's own 3-year history
- **Direction:** Higher = *calmer* → better risk-adjusted attraction
- **Weight:** 0.05
- **Purpose:** Feeds ARCH002 L2 ATR modulator; volatile sectors get wider stops at ARCH002 L1

### 8.11  Sector stability

- **Sub-score:** `norm.sector.<name>.stability`
- **Underlying:** Long-term drawdown history (max DD over 5 years, 10 years); return-consistency (Sortino)
- **Direction:** Higher = historically stable
- **Weight:** 0.03
- **Note:** Slow-moving; recalibrated quarterly

### 8.12  Sector leadership

- **Sub-score:** `norm.sector.<name>.leadership`
- **Underlying:** Was this sector the top-quintile performer in each of the last N rolling windows? Weighted by recency.
- **Direction:** Higher = persistent leader
- **Weight:** 0.05
- **Purpose:** Captures the "leaders continue leading" phenomenon documented in Hong-Torous-Valkanov (2007)

### 8.13  Institutional flow

- **Sub-score:** `norm.sector.<name>.institutional_flow`
- **Underlying:** FII/DII sector-level positioning where disclosed; mutual-fund sector exposure change; institutional-ownership delta
- **Direction:** Higher = institutions adding
- **Weight:** 0.05
- **Caveat:** Positioning data has publication lag; interpret quarterly at best

### 8.14  Cross-sector dependency adjustment (from §14)

- Not a separate score; a *multiplier* applied to the raw composite after summing the 13 dimensions.
- If sector X is heavily dependent on macro variable Y (per §14 graph), and Y is in an adverse state, the composite is adjusted downward by up to ±10 points.
- Ensures the composite reflects both intrinsic sector strength (§8.1-13) *and* extrinsic macro context (§14).

### 8.15  Weight table summary

```
 8.1  Sector momentum          0.15
 8.2  Sector breadth            0.10
 8.3  Sector volume             0.05
 8.4  Sector relative strength  0.15
 8.5  Sector earnings tone      0.15
 8.6  Sector valuation          0.08
 8.7  Sector liquidity          0.03
 8.8  Sector sentiment          0.04
 8.9  Sector news signal        0.05  (deferred until ARCH026)
 8.10 Sector volatility         0.05
 8.11 Sector stability          0.03
 8.12 Sector leadership         0.05
 8.13 Institutional flow        0.05
                               ─────
                               1.00

 8.14 Cross-sector dependency  ±10 points multiplier applied after weighted sum
```

These weights are **v1 draft**. Validation methodology (§21) determines whether they survive to v2. Weights are versioned via ARCH017A §8.1 `weighting_version` and never modified in-place.

### 8.16  Sector Score output

The final `Sector Score ∈ [0, 100]` is:

```
raw_score = Σ (weight_i × sub_score_i)
sector_score = clamp(raw_score + dependency_adjustment, 0, 100)
```

Confidence propagates per ARCH017A §9; if any sub-score's confidence is < 0.5, the sector's classification defaults to `Unknown` per §16.

---

## 9.  Sector Confidence — per-horizon

A sector score alone is insufficient. Institutional analysts distinguish *"strong today"* from *"strong over next 3 months"*. ARCH018 outputs sector confidence at four horizons.

### 9.1  Horizons

| Horizon | Notation | Meaning |
|:--|:-:|:--|
| 1-month | `conf.sector.<name>.1M` | Confidence sector will out-perform benchmark over next 21 trading days |
| 2-months | `conf.sector.<name>.2M` | Matches AEGIS's default HOLD=63 window |
| 3-months | `conf.sector.<name>.3M` | Consumed by ARCH024 (Adaptive Holding) for extension decisions |
| 6-months | `conf.sector.<name>.6M` | Consumed by ARCH019 (regime) for medium-term regime posture |

### 9.2  Method

Historical *forward-conditional* base rate: given today's `sector_score`, `regime`, `dependency_state`, what fraction of similar historical situations produced sector out-performance over the target horizon?

Analogue matching draws from ARCH022 (Market Memory) once that lands. Until then, a simpler model:

```
conf.<horizon> = w_score × sector_score_percentile
               + w_regime × conditional_prob_given_regime
               + w_momentum × forward_momentum_persistence
               + w_dependency × dependency_alignment_score
```

All four component signals are 0-1; weights sum to 1.0.

### 9.3  Confidence tiers

Per ARCH017A §9.2 the response ladder applies:

| Confidence | Downstream response |
|:-:|:--|
| ≥ 0.75 | Full trust; sector included at normal weight |
| 0.55–0.75 | Included at reduced weight |
| 0.4–0.55 | Included only if downstream company scores are top-decile |
| < 0.4 | Excluded from admission set (Rule 8) |

---

## 10.  Sector rotation

### 10.1  What "rotation" means

Rotation is the *shift in sector leadership* over time — Financials leading in Q1, IT leading in Q2, Energy leading in Q3. Institutional funds spend significant analyst-hours detecting rotation early because early positioning captures the whole move.

### 10.2  Rotation signals

ARCH018 monitors five signals:

- **Leadership persistence** — is the sector still in the top quintile of relative strength?
- **Volume divergence** — is momentum continuing on falling volume? (Distribution signal)
- **Breadth deterioration** — is the sector rally led by fewer names each week?
- **Macro-fit change** — has the regime moved such that the sector's Stovall-cycle affinity is receding?
- **Cross-sector correlation** — has the sector's correlation with the outperforming block reversed?

### 10.3  Rotation classification enum

`Classification.sector_rotation` ∈ `{Leading-Persistent, Leading-Exhausting, Lagging-Improving, Lagging-Persistent, Rotating-Out, Rotating-In, Unknown}`.

Rules:

```
Leading-Persistent   score_top_20% AND 4-week-slope > 0 AND breadth > 60%
Leading-Exhausting   score_top_20% AND breadth < 40% AND volume declining
Rotating-Out         previous top-quintile AND fell out AND flow negative
Rotating-In          previous bottom-quintile AND entered top-quintile
Lagging-Improving    score_bottom_40% AND 4-week-slope > 0
Lagging-Persistent   score_bottom_40% AND 4-week-slope < 0
Unknown              confidence < 0.6 on any critical component
```

Downstream consumers (ARCH024, ARCH025, recommendation engine hints) interpret these labels.

### 10.4  Exhaustion detection

A sector transitioning from `Leading-Persistent` → `Leading-Exhausting` is a critical signal. Historically, exhaustion precedes drawdown by 20-40 sessions. ARCH018 emits an explicit `exhaustion_warning(sector)` event when the transition occurs.

Empirical support: technical analysis literature; Chen-Roll-Ross factor decay.

---

## 11.  Sector Allocation Engine

### 11.1  Purpose

Convert sector scores into *portfolio-level sector weights* that a downstream consumer can honour.

### 11.2  Baseline allocation

Two modes:

- **Equal-sector-weight baseline** — each sector gets 1/N (where N is the number of admissible sectors, typically 10-13).
- **Score-tilted allocation** — each sector's weight is proportional to its score above a cutoff.

The Score-tilted formula:

```
raw_allocation[s] = max(0, sector_score[s] - allocation_cutoff)
                    × conf.sector[s].2M
                    × macro_regime_multiplier[s]

normalised_allocation[s] = raw_allocation[s] / Σ_over_sectors raw_allocation
```

Where:

- `allocation_cutoff` (v1 draft = 50) — a sector must score above 50 to receive positive weight
- `conf.sector[s].2M` — sector 2-month confidence (§9)
- `macro_regime_multiplier[s]` — modifier from §6.4 Stovall / §6.5 Bridgewater 2×2

### 11.3  Portfolio-level constraints

Allocation is *bounded* by portfolio constraints from ARCH001A + ARCH002 + tenant-generic config:

- **Sector cap.** No single sector > `sector_cap_pct` (production `sector_cap=2` in the production config; interpreted as 30% max weight per production convention; ARCH018 respects this).
- **Minimum diversification.** At least K sectors have positive allocation (K = 5 in v1 draft) — Rule 6 (bounded risk).
- **Correlation cap.** If two sectors have 63-day correlation > 0.85 (per ARCH002 L5.a analogue), their *combined* weight is capped at 40%.

### 11.4  Example allocation output

```
Sector             Score   Conf-2M   Raw     Normalised
IT                  88      0.85     32.3    22%
Financials          72      0.75     16.5    12%
Healthcare          95      0.82     36.9    26%
Consumer Staples    68      0.70     12.6    9%
Industrials         64      0.65     9.1     6%
Auto                58      0.55     4.4     3%
Energy              80      0.72     21.6    15%
Materials           62      0.60     7.2     5%
Others (excluded)   <50 or conf<0.4  0        0%
────────────────────────────────────────────  ────
                                              100% (with sector_cap check passed;
                                                     correlation check passed)
```

Illustrative — not adopted. Real values from live daily compute.

### 11.5  Advisory-only

ARCH018 publishes this allocation as an *advisory input* to the recommendation engine and RISK001-C. It does not force portfolio construction. The final portfolio is what HRP + RISK001-C produces; ARCH018's role is to inform, not overrule.

---

## 12.  Sector correlation, diversification, crowding

### 12.1  Correlation matrix

Daily-computed 63-day rolling sector-return correlation. Feeds:

- Allocation-engine correlation cap (§11.3)
- Diversification score (§12.2)
- Crowding detector (§12.4)

### 12.2  Diversification score

`composite.sector_diversification ∈ [0, 100]`. Higher = better diversified.

Method: 1 − (largest eigenvalue of correlation matrix / N) — larger eigenvalue = more concentrated risk factor.

### 12.3  Sector concentration (Herfindahl)

`composite.sector_concentration = Σ_s (weight_s)²` — the classic Herfindahl-Hirschman Index applied to sector weights. Higher = more concentrated (worse).

### 12.4  Sector crowding

Sector crowding is when a sector has become universally-favoured — every fund is long, every strategy is overweight, positioning is one-sided. Historically, crowded sectors experience violent unwinds (Khandani-Lo 2011).

Proxy metrics:

- **Institutional flow z-score** — how far positioning is from its 3-year mean
- **Volatility-of-volatility** — sudden vol clustering indicates positioning distress
- **Correlation with peer factors** — a crowded value or momentum position has high correlation with the factor itself

`Classification.sector_crowding[s] ∈ {Not-Crowded, Mild-Crowded, Heavily-Crowded, Unknown}`.

Heavy crowding is an *override signal* that reduces sector weight in §11 regardless of §8 score.

### 12.5  Sector heat

Colloquial term for "sector is running hot" — top-quintile RS, breadth > 70%, volume elevated, flow strong. Publishes `Classification.sector_heat[s] ∈ {Cold, Warm, Hot, Overheating, Unknown}`.

Overheating is a caution signal, not an exit signal. Positions in Overheating sectors get tighter stops per ARCH002 L6.

### 12.6  Sector drawdown & risk budget

Each sector has a *sector-level* max DD budget. If a sector's 63-day return breaches -X% (v1 draft: -12%), ARCH018 emits `sector_dd_breach(sector)` — a signal to ARCH002 L1.e (sector loss limit) and to §11.3 constraint tightening.

---

## 13.  Sector lifecycle

### 13.1  Five phases

Following the Stovall / Fidelity framework:

1. **Expansion** — early cycle. Cyclicals lead.
2. **Peak** — late cycle. Defensives + inflation-linked.
3. **Slowdown** — recession approaching. Staples, Utilities, Healthcare.
4. **Decline** — recession active. Consumer Staples, Utilities.
5. **Recovery** — early recovery. Financials, Consumer Discretionary, Industrials.

### 13.2  Sector-cycle mapping

Combines §6.4 (Stovall) with §6.5 (Bridgewater 2×2). Published as `Classification.sector_lifecycle[s] ∈ {Early-Cycle-Favourable, Mid-Cycle-Favourable, Late-Cycle-Favourable, Recession-Favourable, Universally-Favourable, Currently-Unfavourable, Unknown}`.

Feeds §11 allocation multiplier and §9 confidence.

### 13.3  Empirical evidence

Fidelity's public research shows sector-cycle patterns hold on 40+ years of US data. Application to India requires domestic recalibration — a companion evidence study (LAB015-A) will be scoped once ARCH018 is approved.

---

## 14.  Sector dependency graph

### 14.1  Purpose

Represent inter-sector and macro-sector edges as a directed graph. Feeds ARCH020 (Knowledge Graph) and enables ARCH021 (Dependency Engine) queries.

### 14.2  Node types

- **Macro variables** (Oil, USD, US10Y, VIX, Copper, Gold)
- **Sectors** (Financials, IT, Energy, …)
- **Industries** (Banks, NBFC, IT Services, Cement, …)

Companies are *not* nodes at ARCH018 level (they enter at ARCH020 / ARCH018A).

### 14.3  Edge types

- **Positive causal** — macro variable ↑ → sector ↑
- **Negative causal** — macro variable ↑ → sector ↓
- **Sector-to-sector** — supply-chain / demand-chain (Oil → Chemicals → Paints → Real Estate finish)
- **Regime-conditional** — edge weight depends on regime (e.g. rates ↑ helps Banks in Early-Cycle, hurts Banks in Late-Cycle)

Each edge carries: `source_key`, `target_key`, `strength ∈ [-1, 1]`, `confidence ∈ [0, 1]`, `evidence_type`, `regime_conditioning`, per ARCH017A §16.

### 14.4  Population strategy

Three populating sources:

1. **Empirical correlation** — 63-day rolling correlations, filtered for significance
2. **Expert curated** — analyst-provided edges (curated once, versioned)
3. **LLM proposed** — ARCH026 proposes edges from news / research reports, gated by governance

All edges are versioned. Recalibration cadence: monthly for empirical; quarterly for expert; per-ingest for LLM (subject to review).

### 14.5  Example dependency chain (from operator)

```
Oil ↑ → Energy ↑ → Chemicals ↓ (input costs) → Paints ↓ → Real Estate finish ↓
```

Or:

```
Copper ↑ → Metals ↑ → Electricals ↑ → EV components ↑
```

Or:

```
USD ↑ → IT ↑ (INR export margins) → Pharma ↑ (INR export margins) → Consumer Staples ↓ (import cost of edible oil)
```

These are captured as chains of directed edges in the graph.

### 14.6  Query patterns

- "Given Oil ↑, which sectors move and by how much?" — 2-hop traversal with edge-weight product.
- "Which sectors are 2-hops from a stressed macro variable?" — dependency risk assessment for §11 constraints.
- "Which sectors are structurally uncorrelated?" — diversification maximisation.

Query semantics live in ARCH021 (Dependency Engine); ARCH018 provides the graph substrate.

---

## 15.  Sector News Intelligence

Feeds from ARCH026 (LLM Research Assistant) when that lands. Until then, this section documents the *interface*, not the implementation.

### 15.1  News dimensions

Every sector accumulates daily news signals across dimensions:

- **Earnings** — beats/misses/guidance revisions, aggregated at sector level
- **Policy** — regulatory changes (SEBI, RBI, sectoral regulators like IRDAI, TRAI, etc.)
- **Government** — budget announcements, PLI schemes, subsidies, tax changes
- **RBI / MPC** — monetary policy statements interpreted for sector impact
- **Fed / global central banks** — global monetary policy sector implications
- **Geopolitics** — trade wars, sanctions, war effects
- **Commodity** — sector-relevant commodity moves
- **Imports / exports** — trade balance changes
- **ESG** — climate policy, ESG rating changes
- **AI disruption** — sectors under disruption threat
- **Manufacturing / PLI** — Production-Linked Incentive announcements
- **Taxation** — GST changes, direct-tax policy

### 15.2  Signal aggregation

Every news item is LLM-tagged (by ARCH026) with:

- `affected_sectors: [list]`
- `direction: {positive, negative, neutral}`
- `magnitude: {minor, moderate, major}`
- `time_horizon: {days, weeks, months, years}`
- `confidence: [0, 1]`

Aggregated to a daily `norm.sector.<name>.news_signal ∈ [0, 100]` per §8.9.

### 15.3  Interim behaviour

Until ARCH026 lands, `news_signal` confidence = 0 and its weight is redistributed proportionally to §8.1-8, §8.10-13.

---

## 16.  Sector Classifications (all enums)

All published to ARCH017A §7 Classifications:

| Classification | Values |
|:--|:--|
| `sector_score_bucket` | `Top-Quintile`, `Upper-Middle`, `Middle`, `Lower-Middle`, `Bottom-Quintile`, `Unknown` |
| `sector_trend` | `Bullish`, `Neutral`, `Bearish`, `Unknown` |
| `sector_rotation` | `Leading-Persistent`, `Leading-Exhausting`, `Rotating-Out`, `Rotating-In`, `Lagging-Improving`, `Lagging-Persistent`, `Unknown` |
| `sector_lifecycle` | `Early-Cycle-Favourable`, `Mid-Cycle-Favourable`, `Late-Cycle-Favourable`, `Recession-Favourable`, `Universally-Favourable`, `Currently-Unfavourable`, `Unknown` |
| `sector_crowding` | `Not-Crowded`, `Mild-Crowded`, `Heavily-Crowded`, `Unknown` |
| `sector_heat` | `Cold`, `Warm`, `Hot`, `Overheating`, `Unknown` |

Every Classification carries `confidence ∈ [0, 1]` and `contributing_indicator_ids`, per ARCH017A §7.7.

---

## 17.  Output contract

### 17.1  What ARCH018 publishes daily (08:45 IST, after ARCH017's 08:30 IST publish)

```
{
    asof_date_ist:                "2026-07-18",
    published_at_utc:             "2026-07-18T03:15:00Z",
    code_sha:                     "...",
    schema_version:               "ARCH017A v1.0",
    upstream_arch017_bundle:      { … reference to global bundle used as input … },

    sectors: [
        {
            sector_key:           "IT",
            sector_score:         88,
            sub_scores: {
                momentum: 90, breadth: 78, volume: 65, rs_nifty: 92,
                earnings_tone: 84, valuation: 55, liquidity: 82,
                sentiment: 60, news_signal: null, volatility: 82,
                stability: 70, leadership: 88, institutional_flow: 72
            },
            confidence: {"1M": 0.83, "2M": 0.85, "3M": 0.78, "6M": 0.68},
            classification: {
                sector_score_bucket: "Top-Quintile",
                sector_trend: "Bullish",
                sector_rotation: "Leading-Persistent",
                sector_lifecycle: "Mid-Cycle-Favourable",
                sector_crowding: "Mild-Crowded",
                sector_heat: "Warm"
            },
            allocation_recommendation_pct: 22,
            top_contributors: [
                {sub_score: "rs_nifty", contribution: +13.8},
                {sub_score: "momentum", contribution: +13.5},
                {sub_score: "earnings_tone", contribution: +12.6}
            ],
            top_detractors: [
                {sub_score: "valuation", contribution: +4.4}
            ],
            warnings: []
        },
        // ... 10-13 sectors total
    ],

    portfolio_level: {
        sector_diversification_score: 68,
        sector_concentration_hhi: 0.19,
        sector_correlation_top_pairs: [
            {"IT", "Communication Services", 0.72},
            {"Materials", "Energy", 0.68}
        ],
        exhaustion_warnings: [],
        crowding_warnings: ["Financials: Heavily-Crowded"],
        rotation_events_today: []
    },

    consumer_hints: {
        recommendation_engine:   "IT top pick; Financials avoid crowding",
        adaptive_holding:        "Hold IT positions; consider extending",
        adaptive_exit:           "Financials: tighter stop"
    }
}
```

### 17.2  What ARCH018 never emits

Per ARCH001A Article VIII clause 8.3-4 and this doc §0:

- ❌ BUY / SELL / EXIT recommendation
- ❌ Position weight change
- ❌ Ticker-level scoring (that's ARCH018A)
- ❌ Any decision that alters portfolio state

ARCH018 publishes *context*. Consumers translate.

### 17.3  Sector heatmap

For operator UI (OPS002 dashboard), a sector heatmap output is published:

```
Sector           Score  Trend      Rotation             Heat        Alloc
IT                 88   Bullish    Leading-Persistent   Warm         22%
Healthcare         95   Bullish    Leading-Persistent   Hot          26%
Energy             80   Bullish    Rotating-In          Warm         15%
Financials         72   Neutral    Lagging-Persistent   Heavy-Crowd   0%  (crowding override)
Consumer Staples   68   Neutral    Mid-Cycle-Fav        Cold          9%
Industrials        64   Neutral    Mid-Cycle-Fav        Warm          6%
Auto               58   Neutral    Mid-Cycle-Fav        Cold          3%
Materials          62   Neutral    Rotating-Out         Cold          5%
Consumer Disc      52   Bearish    Rotating-Out         Cold          0%
Utilities          45   Neutral    Late-Cycle-Fav       Cold          0%
Real Estate        38   Bearish    Lagging-Persistent   Cold          0%
```

Illustrative; not adopted.

---

## 18.  Consumers

| Consumer | Reads from ARCH018 |
|:--|:--|
| **ARCH018A** Company Intelligence | Sector score + sector rotation state per company's sector; industry sub-score if applicable |
| **ARCH019** Regime Detection | Sector rotation events, sector lifecycle labels, crowding warnings — as regime-transition signals |
| **ARCH020** Knowledge Graph | Sector taxonomy + dependency graph as node-set substrate |
| **ARCH021** Dependency Engine | Full sector dependency graph for shock-propagation queries |
| **ARCH022** Market Memory | Daily sector state at snapshot time |
| **ARCH023** Decision Attribution | Sector scores + sub-scores for attribution of company recommendations |
| **ARCH024** Adaptive Holding | Sector rotation + crowding + heat state for adaptive-hold decisions |
| **ARCH025** Adaptive Exit | Sector-dd-breach signals + crowding-override signals |
| **Recommendation engine (advisory-only hints)** | `sector_score` × `stock alpha` blend and sector-allocation caps |
| **RISK001-C** | Sector cap per ARCH002 L5.b (already exists); sector-dd-breach for L1.e |

---

## 19.  Governance & amendment

Per ARCH001A Article X + ARCH017A §13. Specifically for ARCH018:

- **New sub-score dimension** — requires an amendment to §8, new `formula_version`, evidence study demonstrating incremental information value.
- **Weight table change** — new `weighting_version`; historical rows keep old version; consumers can query either.
- **Sector taxonomy change** — requires new `sector_map_version`; documented mapping-migration for historical rows.
- **New classification enum value** — additive; requires downstream consumer readiness before adoption.
- **Threshold change (e.g. §11 `allocation_cutoff = 50`)** — new `formula_version`; pre-registered impact analysis on the 285-position historical universe + at least 3 years of sector-return history.

---

## 20.  Non-goals

- ARCH018 does not score companies (ARCH018A).
- ARCH018 does not produce trading decisions.
- ARCH018 does not replace HRP; it *informs* HRP inputs.
- ARCH018 does not process news text directly (ARCH026).
- ARCH018 does not manage cross-country sector exposures (out-of-scope for v1).
- ARCH018 does not model ETF sector flows outside India (out-of-scope for v1).
- ARCH018 does not touch sealed baseline files.

---

## 21.  Validation methodology

### 21.1  How we know if ARCH018 improves AEGIS

Two questions must be answered *before* production adoption:

- **Q1 — Discrimination.** Do high-sector-score-days precede sector out-performance? (Statistical, not causal.)
- **Q2 — Portfolio effect.** Does gating admissions on sector score improve realised risk-adjusted return of the 285-position AEGIS universe?

### 21.2  Companion evidence studies

- **LAB015-A** — Sector discrimination. Backtest: does `sector_score` at time T predict `sector_return` over [T, T+21d] with statistical significance?
  - Method: rank-correlation between score and forward return, per sector, over 5+ years
  - Adoption threshold: Spearman ρ > 0.10 with p < 0.05 after multiple-testing correction (11 sectors → Bonferroni α = 0.0045)
  - Deliverable: `research/ARCH018_LAB015A_SECTOR_DISCRIMINATION.md`

- **LAB015-B** — Sector-conditional stock scoring. Replay the 285-position AEGIS universe with `stock_score × sector_score` blend versus current stock-score-only. Does portfolio Max DD improve without profit-factor degradation > 10%?
  - Success criteria (mirroring RISK001-A §10.2 discipline):
    - Max DD improves ≥ 20% relative
    - Profit factor drops ≤ 10% relative
    - Sharpe non-decreasing
    - Bootstrap 95% CI on Δ excludes zero
    - No single sector shows > 2× worse performance under the new blend
  - Deliverable: `research/ARCH018_LAB015B_SECTOR_CONDITIONAL_SCORING.md`

- **LAB015-C** — Allocation-engine validation. Simulate §11 allocation over the historical window and compare portfolio outcomes vs equal-sector-weight baseline.

### 21.3  Deployment discipline

Per ARCH017A §12 and ARCH001A Article VII clause 7.2:

- Design → **Feature-flag** → **Shadow mode** (4 weeks; ARCH018 emits its bundle daily, no consumer reads it) → **Advisory mode** (4 weeks; consumers read but tag results as advisory) → **Live** (only if LAB015-B passes)
- At every stage, rollback is a right (Article VII clause 7.3)

---

## 22.  Failure modes

### 22.1  Sector-level

- **Sector reclassification.** A ticker moved from IT Services to Software Products mid-period — historical sector scores are re-derived under the new mapping but old rows retain their `sector_map_version` for reproducibility.
- **Data thinning.** A small sector (e.g. Media, only 8 listed names) has thin breadth data. Sector scores for such sectors carry lower confidence.
- **Corporate action.** A large-cap sector heavyweight has a demerger or acquisition — sector aggregates recompute the next day; a rebalancing artifact appears as a one-day spike; consumers should recognise and discount.

### 22.2  Cross-sector

- **Correlation spike (crisis).** Sector correlations spike toward 1.0 in a crisis (Longin-Solnik 2001). ARCH018 detects and emits `crisis_correlation_regime` warning; §11 allocation retreats to defensive baseline.
- **Crowding unwind.** Heavily-crowded sector suffers sudden reversal. ARCH018 issues `crowding_unwind_warning` events, and ARCH002 L1 fires per-position stops.

### 22.3  Model-level

- **Weight drift.** Weight table §8.15 becomes miscalibrated over time. Recalibrated via ARCH029 (Confidence Calibration) once that lands.
- **Late-arriving news signal.** ARCH026 late by more than 3 sessions → `news_signal.confidence = 0`; other 12 dimensions dominate; sector score confidence reduced.

---

## 23.  Rollout plan (design; not authorised)

| Phase | Duration | Guardrails |
|:--|:-:|:--|
| Design (this doc) | complete | 0 code |
| Ingest scaffolding | 1 week | `research/sector_intelligence/` (isolated from production) |
| Sub-score backfill | 2 weeks | 10-year history for each of the 13 dimensions |
| Composite backfill | 1 week | Historical daily composites per sector |
| Validation study | 3 weeks | LAB015-A + LAB015-B + LAB015-C |
| Shadow publish | 4 weeks | ARCH018 emits bundle; no consumer reads |
| Advisory consumer integration | 4 weeks | Consumers read, tag advisory |
| Live | pending | Only after LAB015-B passes AND RISK001-C is live |

Rollout does not touch sealed core.

---

## 24.  Investment Research Pipeline (forward reference)

The operator's suggested additional track (verbatim):

> "If your long-term ambition is to build something comparable in sophistication to institutional research platforms, I would eventually add a separate Investment Research Pipeline (before the AI layer) that continuously ingests academic papers, sell-side research, regulatory changes, earnings transcripts, and macro publications, converts them into structured hypotheses, and routes them through the same evidence and governance process you've already established."

Recorded here for reference. Full scoping in `docs/RESEARCH_ROADMAP_2026-2027.md` §3.-BONUS as `ARCH031 Investment Research Pipeline` (SCOPED).

---

## 25.  Constitutional compliance

| Clause | Compliance |
|:--|:--|
| ARCH001A Article I clause 1.1 (Never lose capital) | ARCH018 outputs advisory-only; RISK001-C L1 hard stop still fires; no bypass |
| ARCH001A Article II clause 2.2 (Risk = permanent loss) | Sector-DD budget (§12.6) is loss-focused, not vol-focused |
| ARCH001A Article II Rule 8 (Uncertainty → reduce) | Low confidence → sector excluded from admission set (§9.3) |
| ARCH001A Article III (Objective function) | Sector allocation is bounded by ARCH001A §4.2 constraints — sector_cap, correlation cap, min-diversification |
| ARCH001A Article IV clause 4.1 (Evidence) | Every weight and threshold requires LAB015 study before adoption (§21) |
| ARCH001A Article IV clause 4.3 (No re-tuning on same data) | Weights frozen before validation; challenger weights via ARCH030 |
| ARCH001A Article V clause 5.1 (Learning bounded) | No auto-learning; recalibration via ARCH029 with operator approval |
| ARCH001A Article VII clause 7.1 (Sealed) | ARCH018 sits downstream of sealed core; no touches |
| ARCH001A Article VII clause 7.6 (Tenant-generic) | Sector map + industry map + weight table all in versioned config, not code |
| ARCH001A Article VIII clause 8.2 (Explainability) | Sub-score contribution + top-contributors published in every bundle (§17) |
| ARCH001A Article VIII clause 8.3-4 (Operator override / AI autonomy floor) | Allocation is advisory; operator/RISK001-C can override |
| ARCH017A §2 (Design principles) | All 7 satisfied (tenant-generic, immutable, explicit confidence, traceable, UTC, idempotent, fail-loud) |

---

## 26.  Integrity + sign-off

- Sealed files touched: **0**
- Production code touched: **0**
- Parameters tuned: **0**
- MON001 fingerprint: `e4c070673568c52d…` (invariant)
- `cumulative_strategy_search`: **38** (unchanged)
- Approvals required: operator sign-off on ARCH017A + ARCH017 + ARCH018 together (ARCH018 depends on both parents)
- **Effective date:** upon operator approval + LAB015-B pass (pending)
- **Version:** DRAFT / v0.9 (proposed v1.0 on approval)

---

## 27.  Change log

| Date | Change | Author | Version |
|:--|:--|:--|:--|
| 2026-07-17 | Initial constitutional design — 13-dimension sector strength model, allocation engine, rotation classification, lifecycle mapping, dependency graph substrate, LAB015 validation methodology | AEGIS engineering | DRAFT / v0.9 |
