# AEGIS - Architecture v3.0

**Generated:** 2026-07-29  ·  **Layman-friendly, image-first**

## Version history

| Version | Date | Highlights |
|---|---|---|
| v1.0 | 2026-07-18 | Initial architecture (India only) |
| v2.0 | 2026-07-18 | USA parallel deployment · dual-market |
| v2.3 | 2026-07-29 | Snapshot persistence · CEO summary · Evolution |
| **v3.0** | **2026-07-29** | **Backtrack · AI Scorecard · Sector Attribution · Command Center** |

---

## 1 · What is AEGIS

AEGIS is an **advisory-only investment platform** that reads market data, runs 11 AI models
daily, and produces one crisp Telegram message telling the operator: what to buy, what to
sell, what to rotate, and why. **It never executes trades.**

![Overview](images/images/aegis_v3.0_overview.png)

---

## 2 · The Daily Pipeline (9 stages)

Every business day, both markets (India NSE 200 + USA Dow 30) run the same deterministic
9-stage flow. Every stage is idempotent per date · every output is auditable.

![Pipeline](images/images/aegis_v3.0_pipeline_flow.png)

---

## 3 · Data Sources We Ingest Daily

10 data categories fed by USA orchestrator + India equivalents. Every ingest is idempotent · every fetch is append-only · missing data degrades gracefully.

| Category | Source | What we extract | Refresh |
|---|---|---|---|
| Universe | manifest.jsonl | NSE 200 (India) · Dow 30 (USA) tickers | on change |
| Market data | yfinance | OHLCV daily bars · adjusted closes | daily post-close |
| Fundamentals | yfinance info + statements | P/E · P/B · ROE · D/E · margins · growth · cashflow | daily |
| News | yfinance / RSS aggregator | headline sentiment · polarity · count | daily |
| Earnings | yfinance earnings | next earnings date · last surprise · EPS actual vs est | daily |
| Insider | yfinance transactions | insider net-buy/sell 90d · # transactions | daily |
| ETF flows | yfinance ETF holdings | sector-ETF net flow proxy · style tilts | daily |
| Macro | yfinance macro tickers | 10y yield · DXY · gold · WTI oil · VIX · rate change | daily |
| Corp. actions | yfinance actions | dividends · splits · days-since-last | daily |
| SEC 13F (USA) | public 13F filings | top institutional holders · % change QoQ | quarterly |

---

## 4 · The Feature Store · 81 Features in 11 Categories

Every raw datum is transformed into one or more features that the AI models consume. All 81 features are versioned, schema-fingerprinted, and stored in `features/{market}/YYYY-MM-DD.parquet`.

| Category | Count | What it captures | Examples |
|---|:---:|---|---|
| Technical | 26 | price · momentum · trend · volatility · drawdown | close, RSI, ATR, sma_50, sma_200, drawdown_60d, position_52w |
| Fundamental | 8 | profitability · leverage · valuation · growth · cashflow | fund_roe, fund_debt_to_equity, fund_trailing_pe, fund_profit_margin, fund_earnings_growth, fund_free_cashflow_yield |
| Macro | 8 | rates · currency · commodities · risk | macro_10y, macro_dxy, macro_gold, macro_wti_oil, macro_vix, macro_10y_chg_1m_pct |
| Institutional | 7 | insider · institutional ownership | insider_net_90d, insider_buy_90d, inst_pct_owned, inst_top_holder_pct |
| Market Intel | 7 | regime · breadth · liquidity | mi_regime, mi_composite_score, mi_breadth_above_20ma_pct, mi_liquidity_5v20_pct |
| Identity | 5 | market · ticker · sector · currency · date | market, ticker, sector, asof, currency |
| News | 5 | sentiment · polarity | news_sentiment, news_polarity_ratio, news_n_positive, news_n_negative |
| Sector | 4 | sector rank · leadership | sector_return_1m_pct, sector_rank, sector_is_leader, sector_is_laggard |
| Earnings | 4 | next-earnings-date · surprise · EPS | earn_days_to_next, earn_last_surprise_pct, earn_last_eps_reported |
| Corporate actions | 4 | dividend · split · time-since | ca_days_since_last_dividend, ca_last_dividend_amount, ca_last_split_ratio |
| Historical | 3 | per-ticker learning-corpus stats | hist_ticker_win_rate, hist_ticker_n_trades, hist_ticker_avg_return_pct |

Every feature carries governance metadata: version · owner · created date · business rationale · economic intuition · dependencies.

---

## 5 · The 11 AI Models · How They Think

| Model | Thesis in one line | Signal driven by |
|---|---|---|
| Momentum | buy what's already going up | 1m/3m/6m returns, RSI |
| Trend | buy what's above rising trend line | sma_50 vs sma_200, ADX |
| Value | buy the cheap ones | P/E, P/B, EV/EBITDA |
| Growth | buy the fast-growing | earnings_growth, revenue_growth |
| Quality | buy the well-run | ROE, profit margin, low D/E |
| MeanReversion | buy the oversold, sell the overbought | distance from moving avg, RSI extremes |
| News | amplify by sentiment | news_sentiment, polarity ratio |
| Macro | tilt with macro regime | VIX, DXY, yields, rate-change |
| Sector | prefer leaders, avoid laggards | sector_rank, sector return 1m |
| Event | act around earnings, corporate actions | days_to_earnings, surprise |
| AI-Hybrid | learns non-linear combinations | gradient-boosted composite |



AEGIS runs 11 specialist models in parallel · their scores are blended into one ensemble
score per ticker. Weights are **adaptive** — yesterday's information-coefficient tunes
tomorrow's weights automatically.

![Ensemble](images/images/aegis_v3.0_ensemble.png)

**Plain English:** the platform learns from itself. If the Sector model has been the best
predictor for the last 60 days, its weight auto-increases. If News has been noisy, its
weight auto-drops. No manual retuning · no bias.

---

## 6 · AI Narrators & Explainers (LLM Layer)

Six AI narrators locked by Constitutional Article 37 — one per intelligence domain. Each reads the day's numerical outputs and produces a human-readable explanation.

| Locked narrator | What it explains | Reads from |
|---|---|---|
| Market Analyst | regime · breadth · sector leadership | reports/market_intelligence.json |
| Macro Analyst | rates · currency · commodities · impact matrix | reports/macro_intelligence.json |
| Recommendation Analyst | why BUY/HOLD/SELL · what changed vs prior day | reports/recommendations.json |
| Portfolio Analyst | concentration · sector tilt · rebalance needed | reports/portfolio_v3.json |
| Risk Analyst | VaR/CVaR · stop-hit risk · drawdown risk | reports/risk_report.json |
| Learning Analyst | what recent wins/losses teach us | reports/learning.parquet |

Utility explainers (data-quality, feature-anomaly, feature-conflict, feature-importance, feature-research, model-analyst, execution-analyst, evidence-summarizer) run alongside but are not locked.

---

## 7 · Downstream Engines · Everything After the Ensemble

The ensemble score is the START, not the finish. 19 downstream engines refine it into a complete institutional decision.

| Engine | What it produces | L4 |
|---|---|:---:|
| Recommendation Intelligence v3 | raw BUY/HOLD/SELL from ensemble + regime + calibration | CONSUMED |
| SSoT Bridge | unified recommendations.json for all consumers | ✓ |
| Percentile Classifier | cross-sectional ranking · institutional pattern | ✓ |
| Investor-Actionable Enricher | entry / if_holding / position_plan / why per rec | ✓ |
| Rotation Intelligence | should_rotate + replacement_ticker + expected alpha | ✓ |
| Lifecycle State Machine | 9-state per-ticker: DISCOVERED → BUY → HOLD → ROTATED | ✓ |
| Dynamic Holding | 12-factor composite predicts holding period in days | ✓ |
| Capital Rotation | keep_score vs candidate_score · edge threshold | ✓ |
| Opportunity Cost | every HOLD justifies 'why not rotate' | ✓ |
| Risk Engine | fractional Kelly · sector cap · VIX-adjusted · VaR/CVaR | ✓ |
| Portfolio Engine v3 | N-name portfolio construction · cash policy | ✓ |
| Learning Engine | closed trades → next-day IC → adaptive weights | ✓ |
| Execution Simulator | paper-trade fills · slippage model | ✓ |
| Position Store | per-ticker high_water + trailing stop + first_seen | ✓ |
| Snapshot Persistence | daily archive · foundation for Backtrack | ✓ |
| Backtrack Engine | per-ticker timeline across all snapshot dates | ✓ |
| AI Performance Scorecard | 6 institutional metrics · 84/100 live on 1060 trades | ✓ |
| Sector/Decision Attribution | per-model contribution to every rec's final score | ✓ |
| Command Center | one crisp Telegram message · both markets | ✓ |

---

## 8 · The Investor Decision Layer

Every recommendation answers **six investor questions**: should I enter · what if I already
own it · how much · when · what changed · why.

![Decision Layer](images/images/aegis_v3.0_decision_layer.png)

A screener says *"BUY LUPIN"*. AEGIS says: **BUY LUPIN, alloc 5%, 17-day swing, enter
Rs 2352-2400, stop Rs 2234, target Rs 2661 / Rs 2946, add if you already own it, expected
alpha +60% vs BATAINDIA.**

---

## 9 · Anatomy of One Recommendation

Every rec in `reports/recommendations.json` carries eight enriched blocks.

![Rec structure](images/images/aegis_v3.0_rec_structure.png)

---

## 10 · AI Performance Scorecard (Live)

Trust is earned, not claimed. AEGIS measures itself against institutional benchmarks using
**1,060 historical closed trades**.

![Scorecard](images/images/aegis_v3.0_scorecard.png)

Five of six metrics hit institutional or top-tier level. The one below-target metric
(Rotation Quality PF 1.73 vs institutional 1.75+) is surfaced, not hidden.

---

## 11 · What Shipped · Six Cycles + v2.4

![Cycles](images/images/aegis_v3.0_cycles.png)

---

## 12 · What AEGIS Guarantees

- **Deterministic** — same inputs · same date · byte-identical outputs
- **Sealed contracts** — MON001 fingerprint + Feature Store schema + sealed research
  untouched since day one, protected by CI fingerprint checks
- **No hardcoded dates** — production code contains zero hardcoded date literals · CI
  guardrail enforces this
- **Single source of truth** — every consumer reads from the same
  `reports/recommendations.json` · no two pipelines can drift
- **Append-only history** — snapshots · position store · lifecycle ledger all append-only
- **Advisory only** — never executes trades · every output labelled PAPER

---

## 13 · Quality Gates (all green as of 2026-07-29)

| Gate | Status | Detail |
|---|:---:|---|
| Targeted regression suite | **168/168** | 13 test files across cycles 1-6 + v2.4 |
| India ops_check schema | **14/14** | all backend contracts satisfied |
| USA ops_check schema | **9/9** | HEALTHY · 85/85 backend datasets pass |
| Hardcode guardrail | **0 hits** | operator directive enforced by CI |
| Date consistency | **PASS** | ≤3d spread across all engines |
| Sealed contract fingerprints | **STABLE** | MON001 + FS schema + sealed research intact |
| Command Center · single sender | **LIVE** | legacy + UX030 retired in workflow |
| USA Telegram parity | **LIVE** | shared bot · USD content |
| Snapshot persistence | **ACTIVE** | day 1 archived both markets |
| AI Scorecard | **84/100** | institutional_grade on 1060 closed trades |

---

## 14 · What's Next (evidence, not features)

Shift from **building intelligence** to **building trust**. Next 30-day window auto-fills:

- **30-day Recommendation Journey** — per-ticker table across snapshot dates
- **Backtrack Timeline** — 7/30/90/365-day windows (engine already wired)
- **Monthly CEO Letter** — narrative from attribution + scorecard evidence
- **Full 1-3 year backtest** — against NIFTY + Dow benchmarks
- **Tune from evidence** — not from intuition · not from adding features

---

*End of AEGIS Architecture v3.0 · generated 2026-07-29 · prior versions preserved
under `docs/AEGIS_ARCHITECTURE_*.pdf`.*
