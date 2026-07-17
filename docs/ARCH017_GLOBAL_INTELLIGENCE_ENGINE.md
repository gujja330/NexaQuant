# ARCH017 — Global Intelligence Engine

## The Missing Top Half of AEGIS

**Document type:** Design specification · Market Intelligence Layer entry point
**Status:** DRAFT · design only · NO code · NO parameter tuning · NO production changes
**Owner role:** Chief Investment Officer · Head of Research · Head of Data
**Author:** AEGIS engineering
**Date opened:** 2026-07-17
**Parent constitution:** [`ARCH001A_INVESTMENT_PHILOSOPHY.md`](ARCH001A_INVESTMENT_PHILOSOPHY.md) — every clause below is compliant with Articles I, II, III, VII, VIII
**Parent data model:** [`ARCH017A_MARKET_DATA_CANONICAL_MODEL.md`](ARCH017A_MARKET_DATA_CANONICAL_MODEL.md) — every field name, every timestamp, every confidence value below is inherited from ARCH017A
**Consumers:** ARCH018 · ARCH019 · ARCH020 · ARCH022 · ARCH023 · ARCH024 · ARCH025 (all read ARCH017's outputs)
**Sealed files touched:** 0. Production code touched: 0. Parameters tuned: 0.

---

## 0.  Preamble & non-negotiables

1. This document is **design specification** only. Nothing is implemented by this document; no data feed is turned on; no production pipeline is changed.
2. ARCH017 is the **entry point** of Phase 2 (Market Intelligence Layer). Every ARCH018-025 depends directly or indirectly on ARCH017's outputs.
3. ARCH017 **never** emits BUY / SELL / EXIT signals. It emits *context*. Downstream consumers translate context into portfolio actions. See §7 (Output contract).
4. ARCH017 must comply with ARCH017A's canonical model. If any consumer needs a new data source, that source is added to ARCH017A first (§4.4 variable catalogue), then referenced here.

---

## 1.  Motivation — the Infosys-in-context example

Today AEGIS scores a stock like Infosys at 92 and recommends BUY. Yet a professional analyst, faced with the same score, will pause and ask:

> *Is IT sector strong? Is Nasdaq falling? Is USD strengthening? Are US recession fears elevated? Are FIIs selling IT? Is it earnings season? Is INR weakening? Is enterprise tech spending contracting?*

Same stock. Same score. **Different correct answer** depending on the world outside.

That check — the whole set of contextual conditions — is what ARCH017 codifies. AEGIS today starts near the bottom of the investment hierarchy:

```
Global Markets         ← ARCH017 (missing)
Macroeconomy           ← ARCH017 (missing)
Country                ← ARCH017 (missing)
Sector                 ← ARCH018 (planned)
Industry               ← ARCH018 (planned)
Company                ← AEGIS today
Portfolio              ← AEGIS today
```

ARCH017 adds the missing top three tiers.

**The operator's framing (verbatim):** *"AEGIS currently answers 'Is this stock good?' Professional funds answer 'Is this stock good — given today's market?' Those are completely different questions."*

---

## 2.  Scope

### 2.1  In scope

- Ingestion catalogue for global, macro, and country-level data (per ARCH017A §4.4 variable catalogue)
- Feature engineering: normalisation methods to convert raw values into ARCH017A NormalizedIndicators (§6)
- Classification rules for global market posture (Risk-On/Off/Rotating/Neutral/Unknown), liquidity, USD, vol regime, rates regime — all per ARCH017A §7 enums
- CompositeScore recipes: Global Risk, Macro, Liquidity, USD, Vol — per ARCH017A §8
- Confidence propagation from RawObservation through DerivedMetric through NormalizedIndicator to CompositeScore
- Refresh cadence per input variable
- Failure-mode handling (source outage, staleness, feed conflict)
- Output contract (what consumers read)

### 2.2  Out of scope

- Sector-level intelligence (ARCH018)
- Regime detection labels (ARCH019 subsumes ARCH017's regime output)
- Knowledge-graph edges (ARCH020)
- Portfolio decisions (ARCH024 / ARCH025 / RISK001-C)
- LLM-based news processing (ARCH026)
- India-specific corporate data (already handled by the sealed AEGIS recommendation engine)
- Storage engineering (in ARCH017A §12)

---

## 3.  Data inventory — the variables ARCH017 owns

Every variable below is registered in ARCH017A §4.4 variable catalogue on ARCH017 approval. Grouped by tier.

### 3.1  Global equity indices

| variable_key | Description | Cadence | Canonical source | Tier |
|:--|:--|:-:|:--|:-:|
| `equity_index.us.spx.close` | S&P 500 close | daily | Yahoo Finance | 2 |
| `equity_index.us.ndx.close` | Nasdaq 100 close | daily | Yahoo Finance | 2 |
| `equity_index.us.djia.close` | Dow Jones Industrial Avg close | daily | Yahoo Finance | 2 |
| `equity_index.jp.n225.close` | Nikkei 225 close | daily | Yahoo Finance | 2 |
| `equity_index.hk.hsi.close` | Hang Seng close | daily | Yahoo Finance | 2 |
| `equity_index.cn.shcomp.close` | Shanghai Composite close | daily | Yahoo Finance | 2 |
| `equity_index.uk.ftse.close` | FTSE 100 close | daily | Yahoo Finance | 2 |
| `equity_index.de.dax.close` | DAX close | daily | Yahoo Finance | 2 |
| `equity_index.fr.cac.close` | CAC 40 close | daily | Yahoo Finance | 2 |
| `equity_index.sg.sti.close` | Straits Times Index | daily | Yahoo Finance | 2 |
| `equity_futures.sgx_nifty.close` | SGX Nifty (pre-market Nifty proxy) | intraday | operator-manual or paid | 3 or 1 |

### 3.2  Volatility indices

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `volatility.us.vix.close` | CBOE VIX (US equity vol) | daily | Yahoo Finance | 2 |
| `volatility.us.vvix.close` | VIX-of-VIX | daily | Yahoo Finance | 2 |
| `volatility.jp.vnky.close` | Nikkei volatility | daily | Yahoo Finance | 2 |
| `volatility.india.india_vix.close` | India VIX | daily | NSE public + yfinance | 2 |

### 3.3  Currencies

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `fx.dxy.close` | Dollar Index (DXY) | daily | Yahoo Finance | 2 |
| `fx.usd_inr.close` | USD/INR spot | daily | Yahoo Finance / RBI reference | 2 |
| `fx.eur_usd.close` | EUR/USD | daily | Yahoo Finance | 2 |
| `fx.usd_jpy.close` | USD/JPY | daily | Yahoo Finance | 2 |
| `fx.usd_cny.close` | USD/CNY (offshore) | daily | Yahoo Finance | 2 |
| `fx.usd_gbp.close` | USD/GBP | daily | Yahoo Finance | 2 |

### 3.4  Commodities

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `commodity.brent.close` | Brent crude | daily | Yahoo Finance | 2 |
| `commodity.wti.close` | WTI crude | daily | Yahoo Finance | 2 |
| `commodity.gold.close` | Gold spot | daily | Yahoo Finance | 2 |
| `commodity.silver.close` | Silver spot | daily | Yahoo Finance | 2 |
| `commodity.copper.close` | Copper spot | daily | Yahoo Finance | 2 |
| `commodity.natural_gas.close` | Natural gas | daily | Yahoo Finance | 2 |

### 3.5  Rates

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `rates.us.10y.yield` | US Treasury 10Y yield | daily | Yahoo Finance | 2 |
| `rates.us.2y.yield` | US Treasury 2Y yield | daily | Yahoo Finance | 2 |
| `rates.us.3m.yield` | US 3-month T-bill | daily | Yahoo Finance / FRED | 2 |
| `rates.india.10y.yield` | India G-Sec 10Y yield | daily | RBI / NSE Fixed Income | 2 |
| `rates.india.repo.rate` | RBI repo rate | on-change | RBI announcements | 1 |
| `rates.us.fed_funds.rate` | Fed Funds target midpoint | on-change | Federal Reserve | 1 |

Note: US 2s10s slope is a `DerivedMetric`, not a RawObservation (§5.1).

### 3.6  Macro data

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `macro.us.cpi.yoy` | US CPI year-on-year | monthly | BLS / FRED | 1 |
| `macro.us.core_cpi.yoy` | US Core CPI YoY | monthly | BLS / FRED | 1 |
| `macro.us.pmi_mfg` | US ISM Manufacturing PMI | monthly | ISM release | 1 |
| `macro.us.pmi_services` | US ISM Services PMI | monthly | ISM release | 1 |
| `macro.us.nfp` | US Non-Farm Payrolls | monthly | BLS | 1 |
| `macro.us.unemployment_rate` | US unemployment | monthly | BLS | 1 |
| `macro.us.gdp_qoq_annualised` | US GDP QoQ (annualised) | quarterly | BEA | 1 |
| `macro.india.cpi.yoy` | India CPI YoY | monthly | MOSPI | 1 |
| `macro.india.wpi.yoy` | India WPI YoY | monthly | Office of Economic Adviser | 1 |
| `macro.india.iip.yoy` | India IIP YoY | monthly | MOSPI | 1 |
| `macro.india.pmi_mfg` | India PMI Manufacturing | monthly | IHS Markit / S&P Global | 1 |
| `macro.india.gdp_yoy` | India GDP YoY | quarterly | MOSPI | 1 |

### 3.7  Central bank & policy

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `policy.us.fomc.meeting_date` | Next FOMC date | scheduled | Federal Reserve calendar | 1 |
| `policy.us.fomc.dots_median_1y_ahead` | Median dot 1-year ahead | quarterly | Fed SEP release | 1 |
| `policy.us.fomc.statement_sentiment` | Hawkish/Dovish/Neutral (LLM-tagged per ARCH026) | on-release | derived | 3 |
| `policy.india.mpc.meeting_date` | Next MPC date | scheduled | RBI calendar | 1 |
| `policy.india.mpc.stance` | Accommodative / Neutral / Withdrawal of accommodation | on-release | RBI communiqué | 1 |

### 3.8  Flow

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `flow.india.fii.cash_net` | FII net cash-market flow (₹ crore) | daily | NSE | 2 |
| `flow.india.dii.cash_net` | DII net cash flow (₹ crore) | daily | NSE | 2 |
| `flow.india.fii.futures_oi_change` | FII net index-futures OI change | daily | NSE F&O | 2 |
| `flow.india.fii.debt_net` | FII net debt flow | daily | SEBI / NSDL | 2 |

### 3.9  Breadth (India)

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `breadth.india.advance_count` | NSE advancing issues | daily | NSE | 2 |
| `breadth.india.decline_count` | NSE declining issues | daily | NSE | 2 |
| `breadth.india.new_high_52w` | NSE 52-week highs | daily | NSE | 2 |
| `breadth.india.new_low_52w` | NSE 52-week lows | daily | NSE | 2 |

### 3.10  Liquidity proxies

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `liquidity.us.credit_spread.ig` | US Investment-Grade credit spread (bps) | daily | FRED (ICE BofA option-adjusted) | 1 |
| `liquidity.us.credit_spread.hy` | US High-Yield spread (bps) | daily | FRED | 1 |
| `liquidity.us.overnight_repo` | Overnight reverse repo balance | daily | Fed H.4.1 release | 1 |
| `liquidity.global.dollar_index_stress` | DXY + credit spread composite | daily | derived | 2 |

### 3.11  India domestic equity markers

| variable_key | Description | Cadence | Source | Tier |
|:--|:--|:-:|:--|:-:|
| `equity_index.india.nifty50.close` | Nifty 50 close | daily | NSE / yfinance | 2 |
| `equity_index.india.nifty_bank.close` | Bank Nifty close | daily | NSE / yfinance | 2 |
| `equity_index.india.nifty_it.close` | Nifty IT close | daily | NSE / yfinance | 2 |
| `equity_index.india.nifty500.close` | Nifty 500 close | daily | NSE / yfinance | 2 |
| `equity_index.india.smallcap.close` | Nifty Smallcap 100 close | daily | NSE / yfinance | 2 |
| `equity_index.india.midcap.close` | Nifty Midcap 100 close | daily | NSE / yfinance | 2 |

Note: Nifty 50 and its family are technically both "global" (from AEGIS's global-context lens) and "target" (AEGIS trades in this universe). They live in ARCH017 because the *context* signals derived from them (breadth, momentum, volatility) inform Global Risk composite.

### 3.12  Summary

- **~60 variables** across 11 tiers
- **Cadence mix:** ~35 daily, ~15 monthly, ~5 quarterly, ~5 on-event
- **Source-tier mix:** ~15 Tier-1 (authoritative), ~40 Tier-2 (secondary/aggregator), ~5 Tier-3 (best-effort)
- **All variables are tenant-generic.** No hardcoded thresholds; no operator-specific tickers.

---

## 4.  DerivedMetrics — computed from raw

Every DerivedMetric below is registered in ARCH017A §5 with a canonical `metric_key` and `formula_key`.

### 4.1  Rates-derived

- **`derived.us.2s10s.slope_bps`** — `rates.us.10y.yield - rates.us.2y.yield` × 100. Formula `slope_2y_10y v1.0`.
- **`derived.us.3m10y.slope_bps`** — `rates.us.10y.yield - rates.us.3m.yield` × 100. Alternative recession-signal proxy.
- **`derived.us.real_10y.yield`** — `rates.us.10y.yield - macro.us.cpi.yoy`. Real rate.
- **`derived.india.real_10y.yield`** — `rates.india.10y.yield - macro.india.cpi.yoy`.
- **`derived.india_us.rate_diff.10y_bps`** — India 10Y minus US 10Y. Capital-flow proxy.

### 4.2  Volatility-derived

- **`derived.vix.ma_20d`** — 20-day moving average of VIX.
- **`derived.india_vix.ma_20d`** — 20-day MA of India VIX.
- **`derived.vix.spike_flag`** — 1 if `volatility.us.vix.close > 1.5 × derived.vix.ma_20d`, else 0.

### 4.3  Currency-derived

- **`derived.dxy.ma_50d`** — 50-day moving average of DXY.
- **`derived.usd_inr.pct_change_5d`** — 5-day % change in USD/INR.
- **`derived.usd_inr.pct_change_20d`** — 20-day.

### 4.4  Commodity-derived

- **`derived.brent.pct_change_20d`** — 20-day % change in Brent.
- **`derived.gold_silver_ratio`** — Gold price / Silver price. Historical stress indicator.
- **`derived.copper_gold_ratio`** — Copper / Gold. Growth vs safety.

### 4.5  Equity momentum

- **`derived.spx.mom_20d`** — S&P 500 20-day price momentum (rate of change).
- **`derived.spx.mom_60d`** — 60-day.
- **`derived.spx.mom_120d`** — 120-day.
- Similar `mom_20d/60d/120d` for Nasdaq, Hang Seng, Nikkei, Nifty 50, Bank Nifty.
- **`derived.spx.above_200dma.flag`** — 1 if SPX > 200-day MA.

### 4.6  Breadth-derived

- **`derived.india.advance_decline_line`** — cumulative sum of `advance_count - decline_count`.
- **`derived.india.new_high_ratio`** — `new_high_52w / (new_high_52w + new_low_52w)` (0-1 scale).

### 4.7  Flow-derived

- **`derived.india.fii_5d_flow`** — 5-day rolling sum of FII net cash.
- **`derived.india.fii_20d_flow`** — 20-day rolling sum.
- **`derived.india.dii_5d_flow`** — 5-day DII.
- **`derived.india.fii_dii_ratio_20d`** — abs(FII 20d) / abs(DII 20d) — who's driving?

### 4.8  Cross-market

- **`derived.overnight.gap_prediction`** — SGX Nifty pre-market minus previous Nifty close, expressed as % of previous close.
- **`derived.us_asia.risk_transfer_flag`** — 1 if US closed with SPX_mom_5d < 0 AND Asian markets opened negative next session.

Total: **~35 DerivedMetrics**. All deterministic; recomputed daily; versioned per ARCH017A §11.

---

## 5.  NormalizedIndicators — the 0-100 scale

Every NormalizedIndicator below maps one or more DerivedMetrics onto [0, 100], per ARCH017A §6. **Higher value = more risk-on / more supportive** by universal convention. Direction is documented per indicator.

### 5.1  Global equity momentum block

| indicator_key | Underlying | Method | Direction |
|:--|:--|:--|:--|
| `norm.us_equity_momentum` | Average of `derived.spx.mom_20d/60d/120d` | `zscore_rolling_252d` | 100 = strong bull; 0 = crash |
| `norm.asia_equity_momentum` | Nikkei + Hang Seng + Shanghai momentum | Same | Same |
| `norm.india_equity_momentum` | Nifty50 + BankNifty momentum | Same | Same |

### 5.2  Rates block

| indicator_key | Underlying | Direction |
|:--|:--|:--|
| `norm.us_yield_curve_inversion` | `derived.us.2s10s.slope_bps`; more inverted = *lower* norm (i.e. 20 when deeply inverted) | 100 = steep upward; 0 = deeply inverted (recession-signal) |
| `norm.us_real_yield` | `derived.us.real_10y.yield`; higher real yield = *tighter financial conditions* → lower norm | 100 = negative real yield; 0 = high positive real |
| `norm.india_us_rate_diff` | `derived.india_us.rate_diff.10y_bps`; wider diff = *pulls capital to India* | 100 = wide favourable diff; 0 = narrow / negative |

### 5.3  Volatility block

| indicator_key | Underlying | Direction |
|:--|:--|:--|
| `norm.vix` | 100 minus VIX percentile — higher VIX = lower norm | 100 = calm; 0 = spike |
| `norm.india_vix` | Same for India VIX | Same |
| `norm.vix_spike_flag` | `derived.vix.spike_flag`; binary → 0 or 100 | 100 = no spike; 0 = spike |

### 5.4  USD & currencies block

| indicator_key | Underlying | Direction |
|:--|:--|:--|
| `norm.usd_strength` | DXY percentile (rolling 252d); strong dollar = *risk-off* for emerging markets | 100 = weak dollar (risk-on for EM); 0 = strong dollar |
| `norm.inr_stability` | Rolling 5-day and 20-day USD/INR change; more volatile INR = riskier | 100 = stable; 0 = sharp depreciation |

### 5.5  Commodities block

| indicator_key | Underlying | Direction |
|:--|:--|:--|
| `norm.oil_stability` | Brent 20d % change; sharp spike = *risk-off* (input cost pressure) | 100 = stable/falling; 0 = sharp spike |
| `norm.gold_stress` | Gold rally vs SPX (safety flight); higher gold price momentum + falling equities = risk-off | 100 = gold stable; 0 = gold spiking with equity fall |
| `norm.copper_growth_signal` | `derived.copper_gold_ratio` percentile | 100 = strong growth signal; 0 = defensive |

### 5.6  Liquidity block

| indicator_key | Underlying | Direction |
|:--|:--|:--|
| `norm.us_ig_credit_health` | `liquidity.us.credit_spread.ig`; wider = *risk-off* | 100 = tight spreads (healthy); 0 = wide spreads (stress) |
| `norm.us_hy_credit_health` | `liquidity.us.credit_spread.hy` | Same |
| `norm.global_dollar_liquidity` | Composite of overnight repo, DXY, credit spreads | 100 = flush; 0 = tight |

### 5.7  Breadth block (India)

| indicator_key | Underlying | Direction |
|:--|:--|:--|
| `norm.india_breadth` | `derived.india.new_high_ratio` (percentile-mapped) | 100 = broad rally; 0 = narrow / distribution |
| `norm.india_advance_decline` | AD line 20d slope percentile | 100 = advancers dominant; 0 = decliners dominant |

### 5.8  Flow block (India)

| indicator_key | Underlying | Direction |
|:--|:--|:--|
| `norm.india_fii_flow` | `derived.india.fii_20d_flow` percentile | 100 = strong FII inflow; 0 = outflow |
| `norm.india_dii_offset` | If FII selling but DII buying → 100; both selling → 0 | 100 = domestic offset present; 0 = broad selling |

### 5.9  Macro block

| indicator_key | Underlying | Direction |
|:--|:--|:--|
| `norm.us_inflation_pressure` | `macro.us.core_cpi.yoy` percentile; higher = tighter Fed | 100 = disinflation; 0 = high inflation |
| `norm.us_growth_pmi` | `macro.us.pmi_mfg + macro.us.pmi_services` blend | 100 = strong expansion; 0 = deep contraction |
| `norm.india_growth_pmi` | `macro.india.pmi_mfg` percentile | Same |
| `norm.india_cpi_pressure` | `macro.india.cpi.yoy`; high = tighter RBI | 100 = low; 0 = high |

### 5.10  Total NormalizedIndicator count

**~25 indicators.** All map to [0, 100]. All carry confidence per ARCH017A §9.

---

## 6.  Classifications — the discrete labels

Every Classification below uses ARCH017A §7 enums. Composite formulas (§7 below) reference these.

### 6.1  Global market posture (`Classification.global_posture`)

Enum: `{Risk-On, Risk-Off, Rotating, Neutral, Unknown}` (ARCH017A §7.1).

Rules:

```
posture =
    Risk-On           if composite.global_risk > 65 AND confidence >= 0.7
    Risk-Off          if composite.global_risk < 35 AND confidence >= 0.7
    Rotating          if abs(norm.us_equity_momentum - norm.us_hy_credit_health) > 30
                          AND confidence >= 0.7
                          (equity says risk-on but credit says risk-off, or vice versa)
    Neutral           if 35 <= composite.global_risk <= 65 AND confidence >= 0.7
    Unknown           if confidence < 0.7
```

### 6.2  Liquidity posture (`Classification.liquidity`)

Enum: `{Improving, Stable, Deteriorating, Unknown}`.

Rules:

```
liquidity =
    Improving        if 5-day change of composite.liquidity > +5 AND confidence >= 0.7
    Deteriorating    if 5-day change of composite.liquidity < -5 AND confidence >= 0.7
    Stable           otherwise (with confidence >= 0.7)
    Unknown          if confidence < 0.7
```

### 6.3  USD posture (`Classification.usd`)

Enum: `{Bullish, Neutral, Weak, Unknown}`.

Rules:

```
usd =
    Bullish          if norm.usd_strength < 30  (i.e. dollar strong = weakness for EM)
                          AND confidence >= 0.7
    Weak             if norm.usd_strength > 70
                          AND confidence >= 0.7
    Neutral          if 30 <= norm.usd_strength <= 70
                          AND confidence >= 0.7
    Unknown          otherwise

    NOTE: "Bullish USD" here means bullish for the dollar itself (bad for EM/India).
    The convention is deliberate — matches financial industry usage.
```

### 6.4  Volatility regime (`Classification.vol_regime`)

Enum: `{Calm, Elevated, Spiking, Unknown}`.

Rules:

```
vol_regime =
    Spiking          if volatility.us.vix.close > 1.5 * derived.vix.ma_20d
                          OR volatility.us.vix.close > 30
    Elevated         if volatility.us.vix.close > 22 AND not Spiking
    Calm             if volatility.us.vix.close < 15
                          AND derived.vix.ma_20d < 18
    Unknown          otherwise or if confidence < 0.7
```

### 6.5  Rates regime (`Classification.rates`)

Enum: `{Hiking, Cutting, On-Hold, Unknown}`.

Rules:

```
rates =
    Hiking           if last 2 US FOMC actions have raised Fed Funds
                          OR US 2Y yield is above 6-month MA and rising
    Cutting          if last 2 FOMC actions have lowered Fed Funds
                          OR US 2Y yield is below 6-month MA and falling
    On-Hold          otherwise
    Unknown          if data stale
```

---

## 7.  CompositeScores — what consumers see

Per ARCH017A §8. All in [0, 100] with `contribution_to_composite` breakdown for explainability.

### 7.1  `composite.global_risk` — the headline

Weighted blend of the NormalizedIndicators most tightly correlated with global equity risk-on/off. Weights are v1 draft; will be revised via ARCH029 calibration studies.

| Component | Weight | Rationale |
|:-:|:-:|:--|
| `norm.us_equity_momentum` | 0.20 | Largest equity market's own trend |
| `norm.vix` | 0.15 | Fear gauge |
| `norm.usd_strength` | 0.10 | EM risk-off signal |
| `norm.us_hy_credit_health` | 0.10 | Bond-market risk-off signal |
| `norm.us_yield_curve_inversion` | 0.10 | Recession signal |
| `norm.us_growth_pmi` | 0.08 | Growth surprise |
| `norm.oil_stability` | 0.08 | Input-cost stress |
| `norm.india_fii_flow` | 0.07 | Local flow signal |
| `norm.india_breadth` | 0.07 | Local participation signal |
| `norm.india_vix` | 0.05 | Local fear gauge |
| **Sum** | **1.00** | |

Formula: `value_0_100 = sum(weight_i × value_0_100_i)`; classification per §6.1.

### 7.2  `composite.macro` — macroeconomic tone

| Component | Weight |
|:-:|:-:|
| `norm.us_growth_pmi` | 0.30 |
| `norm.us_inflation_pressure` | 0.25 |
| `norm.india_growth_pmi` | 0.20 |
| `norm.india_cpi_pressure` | 0.15 |
| `norm.us_real_yield` | 0.10 |

### 7.3  `composite.liquidity` — plumbing health

| Component | Weight |
|:-:|:-:|
| `norm.us_ig_credit_health` | 0.30 |
| `norm.us_hy_credit_health` | 0.25 |
| `norm.global_dollar_liquidity` | 0.25 |
| `norm.usd_strength` | 0.10 |
| `norm.india_us_rate_diff` | 0.10 |

### 7.4  `composite.usd` — dollar posture (single indicator elevated to composite for consumer convenience)

Directly = `norm.usd_strength` mapped to Classification per §6.3.

### 7.5  Confidence propagation

Every CompositeScore inherits confidence per ARCH017A §9:

```
confidence(composite) = sum(weight_i × confidence_i)
```

If any single component has `confidence < 0.5`, the composite's classification is forced to `Unknown` regardless of `value_0_100`.

---

## 8.  Refresh cadence & pipeline flow

### 8.1  When each variable refreshes

| Variable class | Refresh | Trigger |
|:--|:--|:--|
| Global equity indices (US close) | daily | 04:00 IST (US markets closed by then; yfinance has data) |
| Asian markets | daily | 15:30 IST (Asian close) |
| Volatility indices | daily | with equities |
| Currencies | daily | 07:00 IST + 20:00 IST (two snapshots to catch London and NY sessions) |
| Commodities | daily | 07:00 IST |
| Rates | daily | 07:00 IST (US close) + 18:00 IST (India close) |
| Macro (monthly) | on-release | scheduled by release calendar; ingest tries daily but writes only when new |
| Central bank | on-event | scheduled + fallback daily check |
| Flow (FII/DII/breadth) | daily | 18:00 IST (post-close India) |
| SGX Nifty pre-market | intraday | 07:00 - 09:00 IST |

### 8.2  Compute cadence for downstream entities

- **DerivedMetrics** — recomputed once daily at 06:00 IST after all overnight feeds have landed.
- **NormalizedIndicators** — recomputed with DerivedMetrics.
- **Classifications** — recomputed with NormalizedIndicators.
- **CompositeScores** — recomputed with all above.
- **MemorySnapshot** (ARCH022) — one daily write at end of the compute cycle (07:00 IST).

### 8.3  Pre-open publish

At **08:30 IST**, ARCH017 publishes the day's context bundle for consumption by ARCH018-025 and by the recommendation engine at 09:00 IST (before market open at 09:15 IST). This gives 45 minutes of buffer.

---

## 9.  Output contract — what consumers actually read

### 9.1  The daily context bundle

At 08:30 IST, ARCH017 publishes:

```
{
    asof_date_ist:            "2026-07-18",
    asof_utc:                 "2026-07-18T03:00:00Z",
    published_at_utc:         "2026-07-18T03:00:12Z",
    code_sha:                 "0a3f570…",
    schema_version:           "ARCH017A v1.0",
    weighting_version:        "ARCH017 v1.0",

    composites: {
        global_risk:          {value: 81, classification: "Risk-On", confidence: 0.89},
        macro:                {value: 62, classification: "Neutral", confidence: 0.85},
        liquidity:            {value: 68, classification: "Improving", confidence: 0.83},
        usd:                  {value: 44, classification: "Neutral", confidence: 0.92}
    },

    classifications: {
        global_posture:       "Risk-On",
        liquidity:            "Improving",
        usd:                  "Neutral",
        vol_regime:           "Calm",
        rates:                "On-Hold"
    },

    contributions: {
        global_risk_top5: [
            {indicator: "norm.us_equity_momentum",     contribution: 18.2},
            {indicator: "norm.vix",                    contribution: 13.4},
            {indicator: "norm.us_hy_credit_health",    contribution: 8.9},
            ...
        ]
    },

    warnings: [
        // any feed_outage(variable) events, staleness flags, confidence < 0.7 flags
    ],

    consumer_hints: {
        recommendation_engine:   "GREEN - proceed normally",
        adaptive_holding:        "GREEN - can extend holds up to +20%",
        adaptive_exit:           "GREEN - normal exit stops",
        sector_engine:           "GREEN - use full sector cascade",
        // Consumer-specific advisory strings; consumers may ignore.
    }
}
```

### 9.2  What ARCH017 **never** emits

Per operator's explicit constraint (repeated here from §0):

- ❌ BUY recommendation
- ❌ SELL recommendation
- ❌ EXIT signal
- ❌ Weight change
- ❌ Any single-stock action

ARCH017 emits *context*. Downstream consumers (ARCH018, ARCH024, ARCH025, RISK001-C) translate context into portfolio actions per their own designs, subject to ARCH001A Article VI (Rules 1-10) and Article III (objective function).

### 9.3  Consumers and what they read

| Consumer | Reads |
|:--|:--|
| **ARCH018** Sector Intelligence | `composites.macro`, `composites.liquidity`, `classifications.usd`, sector-specific NormalizedIndicators from ARCH017 |
| **ARCH019** Regime Detection | All Classifications + confidence-weighted composites; produces `Classification.regime` |
| **ARCH020** Knowledge Graph | Variables catalogue (to know what nodes exist); dependencies from empirical correlation of the daily bundle over history |
| **ARCH021** Dependency Engine | Composites and classifications for shock propagation |
| **ARCH022** Market Memory | All of the above at daily snapshot |
| **ARCH023** Decision Attribution | `contributions` field for the Shapley decomposition |
| **ARCH024** Adaptive Holding | Classifications + `consumer_hints.adaptive_holding` |
| **ARCH025** Adaptive Exit | Classifications + `consumer_hints.adaptive_exit`, feeds ARCH002 L6 modulator |
| **Recommendation engine (future)** | `consumer_hints.recommendation_engine` — advisory only; sealed core still runs whatever it runs |
| **ARCH026** AI Research Assistant | Full bundle for context grounding when producing research notes |

---

## 10.  Failure modes and handling

Per ARCH017A §10 and Article II Rule 8 (uncertainty → reduce).

### 10.1  Single-feed outage

- Log `feed_outage(variable_key)` event
- Attempt fallback source per ARCH017A §10.3
- If fallback also fails: mark the downstream DerivedMetric as `confidence = 0` (staleness component)
- If the affected variable feeds a composite: reduce the composite's confidence proportionally
- If the reduced confidence drops the composite below the classification threshold: force classification to `Unknown`

### 10.2  Cross-market inconsistency

If two independent classifications disagree beyond a documented tolerance (e.g. equity momentum says Risk-On but credit spreads say Risk-Off), the `global_posture` becomes `Rotating` (§6.1). Consumers interpret Rotating as a special signal — reduce exposure, avoid new admissions in high-beta names.

### 10.3  Staleness

Per ARCH017A §10.4. Monthly / quarterly variables handled with longer staleness windows. Consumers see the actual staleness in `confidence_components.C_freshness`.

### 10.4  Regime transition

When `classifications.regime` (ARCH019) transitions to a different label, ARCH017 records the transition in `warnings` and includes `previous_label` + `duration_days_at_previous`. Consumers may act more conservatively during the first N days after a regime transition (definition per consumer).

### 10.5  Emergency mode

If `composite.global_risk` drops below 15 or `classifications.vol_regime = Spiking` for two consecutive sessions, ARCH017 sets `warnings.emergency_mode = true`. Consumers interpret per their design; ARCH024/025 tighten stops, ARCH002 L8 (kill switch) evaluates independently.

---

## 11.  Governance & amendment

Per ARCH001A Article X and ARCH017A §13. Specifically for ARCH017:

- **Variable additions** — a new variable requires an amendment to ARCH017A's variable catalogue *plus* an amendment to ARCH017's §3 inventory *plus* a documented purpose (which downstream indicator / composite will use it).
- **Weight changes** — changing any composite weight (§7) requires a new `weighting_version`. Old rows retain the old weighting_version for reproducibility.
- **Classification threshold changes** — changing the numeric thresholds in §6 requires a new `formula_version` and pre-registered impact analysis.
- **New composite** — requires a new document referencing this one, not an in-place edit.

---

## 12.  Rollout plan (design; not authorised yet)

If ARCH017 is approved:

| Phase | Duration | Guardrails |
|:--|:-:|:--|
| **Design** (this doc) | complete on approval | 0 code |
| **Ingest scaffolding** | 1 week | `research/market_intelligence/ingest/` — writes to `data/market_intelligence/raw/` (new directory); untouched by production pipeline |
| **DerivedMetric backfill** | 1 week | Compute against 5+ years of historical raw data; verify consistency with known events (VIX spike Aug 2015, March 2020, etc.) |
| **Composite backfill** | 1 week | Compute daily composites for the same history |
| **Shadow publish** | 4 weeks | Daily bundle published to `reports/global_intelligence_YYYY-MM-DD.json`; NO consumer reads it in production; operator eyeballs |
| **Consumer integration (advisory only)** | 4 weeks | ARCH018/019/023/024/025 designs — none live yet — reference the bundle as input |
| **Live** | pending | Only after RISK001-C ships (Phase 1 complete) |

Rollout does not touch the sealed baseline or the recommendation engine.

---

## 13.  Non-goals

- ARCH017 does not implement ingest code (that's post-approval).
- ARCH017 does not decide sector weights (ARCH018).
- ARCH017 does not classify regimes with the full 12-label taxonomy (ARCH019).
- ARCH017 does not process news text (ARCH026).
- ARCH017 does not perform LLM inference (ARCH026 augments with LLM sentiment; ARCH017 is deterministic).
- ARCH017 does not touch the sealed AEGIS core.
- ARCH017 does not produce trading decisions.

---

## 14.  Constitutional compliance (ARCH001A + ARCH017A)

| Clause | Compliance |
|:--|:--|
| ARCH001A Article I clause 1.1 (Never lose capital) | ARCH017 emits context; consumers decide; Article VI Rule 7 (Risk Controller veto) survives |
| ARCH001A Article II clause 2.3 (Uncertainty) | Every score has confidence per ARCH017A §9 |
| ARCH001A Article II Rule 8 (Uncertainty → reduce) | Low-confidence composites force classification to `Unknown`; consumers see and reduce |
| ARCH001A Article III (Objective function) | ARCH017 does not alter the objective function; it provides inputs the function's regime-adaptive λ (§4.3) uses |
| ARCH001A Article IV (Research) | Weights (§7) are documented, versioned, and calibrated via ARCH029; not tuned mid-flight |
| ARCH001A Article VII clause 7.1 (Sealed) | ARCH017 lives entirely outside the sealed baseline |
| ARCH001A Article VII clause 7.6 (Tenant-generic) | All ~60 variables are tenant-generic; the variable catalogue (§3) is data, not code |
| ARCH001A Article VII clause 7.8 (Reproducibility) | Every row carries code_sha, formula_version, weighting_version |
| ARCH001A Article VIII clause 8.2 (Explainability) | `contributions.global_risk_top5` in the output bundle explains the score |
| ARCH017A §2 (Design principles) | ARCH017 satisfies all seven principles (tenant-generic, immutable, explicit confidence, traceable, UTC, idempotent, fail-loud) |

---

## 15.  Integrity + sign-off

- Sealed files touched: **0**
- Production code touched: **0**
- Parameters tuned: **0**
- MON001 fingerprint: `e4c070673568c52d…` (invariant)
- `cumulative_strategy_search`: **38** (unchanged)
- Approvals required: operator sign-off on ARCH017A + ARCH017 together (this doc depends on the schema)
- **Effective date:** upon operator approval (pending)
- **Version:** DRAFT / v0.9 (proposed v1.0 on approval)

---

## 16.  Change log

| Date | Change | Author | Version |
|:--|:--|:--|:--|
| 2026-07-17 | Initial design — ~60 variables inventoried, ~35 DerivedMetrics, ~25 NormalizedIndicators, 5 Classifications, 4 CompositeScores, output contract, rollout plan | AEGIS engineering | DRAFT / v0.9 |
