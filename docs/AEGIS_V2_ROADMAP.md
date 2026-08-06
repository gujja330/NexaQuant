# AEGIS · v2 Roadmap (deferred features · post-lock)

**Signed:** 2026-08-06
**Trigger:** Operator lock-review 2026-08-06 · "95-98% production ready ·
would consider this ready to freeze and move into performance tracking
rather than adding more features"

---

## Post-lock stance

AEGIS v3.2 is being **LOCKED at end of session 2026-08-06** at the
following score baseline (operator's assessment):

| Area                  |  Score |
| --------------------- | -----: |
| Recommendation engine | 9.8/10 |
| Explainability        | 9.6/10 |
| Rotation logic        | 9.8/10 |
| Context engine        | 9.5/10 |
| UI-ready output       | 9.7/10 |
| Data richness         | 10/10  |

Post-lock focus: **performance tracking > feature additions.** Live
results and paper-trading returns will inform what actually needs
building vs what feels valuable.

---

## v2 Feature Roadmap (deferred · evidence-gated)

### V2-A · Market Regime UI panel
Show current regime prominently: Bull · Neutral · Bear · with days-since-flip
+ historical regime distribution vs benchmark returns.

Data: macro_regime.json (exists) + regime_history.jsonl (exists) · pure UI.

### V2-B · Sector Heatmap
Grid view: 11 sectors × 5 metrics (breadth · momentum · leadership rank ·
CIL sentiment · sector news) · color-coded green/yellow/red.

Data: sector_rotation.json + market_breadth.json + sector_news.json.

### V2-C · Portfolio Beta
For any currently-held basket · compute weighted beta vs benchmark ·
surface as portfolio-level risk metric.

Data: needs correlation_matrix + benchmark returns · already have both.

### V2-D · Factor Exposure Chart
Show portfolio exposure across Quality/Momentum/Value/Growth/Trend/
MeanReversion factors as a spider chart.

Data: attribution.per_model already tracked per rec · rollup by portfolio weight.

### V2-E · Earnings Countdown widget
For every held position · display days-to-next-earnings prominently.
Auto-reduce position sizing 3 days before high-impact earnings.

Data: economic_calendar.jsonl (exists · earnings category).

### V2-F · Dividend Calendar
Show ex-dividend dates for held positions · plan around gaps.

Data: needs corporate_actions.parquet ingest (partial today).

### V2-G · Macro Dashboard
Full FRED-driven macro panel: rates · CPI · unemployment · VIX with
percentile bands + narrative interpretation.

Data: reports/fred/ (all 12 series live) · pure UI.

### V2-H · Live Performance Attribution
Rolling 30d P&L attribution by:
- Model (which of 11 models actually earned)
- Sector (which sectors were net positive/negative)
- Signal type (rotation vs entry vs hold vs exit)

Extends existing feature_attribution monthly rollup to real-time.

### V2-I · Independent Runner 3 Universe
Currently R3 scores R2's top-15. NSE bhavcopy gives us 3292-row universe
with real turnover. R3 could pre-screen by liquidity + tradability and
score its own top-100 independently.

Per Runner 3 Deep Research PDF §7.5 Tier 2.

### V2-J · Real News NLP
Replace divergence-proxy in sector_news.py with actual headline classification:
- Fetch Google News RSS per sector
- NLP sentiment scoring (transformers or lexicon)
- Impact severity + expected duration per headline

Per Runner 3 Deep Research PDF §Sentiment/News.

### V2-K · Options Positioning Ingest
Currently R3 features_free reads PCR if file exists (empty). Build proper
NSE F&O ingest: OI · PCR · IV per stock. Feeds vol_adapter + R3.

Per Runner 3 Deep Research PDF §Options/Open Interest/PCR.

---

## v2 Governance

Each v2 item may only proceed when:
1. Live performance tracking produces evidence that CURRENT AEGIS's
   accuracy in that area is limiting outcomes, AND
2. Operator explicitly opens a research ticket citing the evidence

No speculative v2 additions. Data-driven only.

---

## What ships in the LOCK today (v3.2)

| Sprint | What |
|---|---|
| A | Recommendation Health Score |
| B | Adaptive Weight Proposals |
| C | XLSX Story column |
| D | Per-Ticker Timeline CLI |
| E | 3 rollup slices (sector · regime · per-model win rate) |
| F | Government-source ingests (FRED · EDGAR · NSE bhavcopy) |
| G | 6 CIL adapters + Runner 3 features extension + 3 XLSX columns |
| H-1 | R1 rich rendering parity |
| H-2 | Telegram operator guide (Monday reminder) |
| H-final | USA Runner 1 defensive derivative + Guard 7 monitors + cron wiring |
| H-nice | Risk Meter 🟢🟡🔴 + Sector Exposure % + Rotation Candidate detail |

Total: 11 sprint items · 14+ CIL adapters · 6 rollup engines · 3 government
source ingests · Guard 7 monitors 21 engines including USA R1 · both
markets have R1+R2 parity.

---

## Post-lock cadence

- **Daily**: R1+R2 for both markets · CIL 14-adapter composition · Guard 7 check · Telegram XLSX
- **Weekly**: Friday operator review of Rank Δ + Story + Alert columns
- **Monthly**: 6 rollups (calibration + rotation accuracy + feature attribution + sector + regime + model_winrate)
- **Runner 3 Day-30 gate**: 2026-09-09 · PASS/FAIL/DEFERRED
- **Runner 3 Day-90 CEO decision**: 2026-11-03 · A/B/C/D
- **v2 sprint kickoff**: only when operator + rollup evidence agree a specific v2-A through v2-K item is needed

---

## Signed 2026-08-06 · AEGIS v3.2 LOCKED
