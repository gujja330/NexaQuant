# What Influences Indian Stocks — full list + what we can embed

Every meaningful driver of NSE stocks, the direction of its effect, the free data source, and
whether it's **embeddable** into the engine. Honest rule throughout: we embed what we can get
*systematically and free*; news *headlines* we can't predict, so we capture them via their
*footprint* (volatility + price), not the text.

Legend — Embed: ✅ free data now · ⚠️ partial/needs work · ❌ not systematic (proxy instead)

## 1. GLOBAL MARKETS (overnight lead → next-day open)
| Driver | Effect on India | Source | Embed |
|---|---|---|---|
| **US S&P 500 / Nasdaq** | risk-on/off lead; tech → IT | `^GSPC` ✅ (have) | ✅ |
| **GIFT Nifty (overnight futures)** | direct next-day gap signal | broker/livemint | ⚠️ |
| **China (Shanghai/Hang Seng)** | **metals, commodities, EM flows** | `000001.SS`, `^HSI` | ✅ |
| **Europe (FTSE/DAX), Japan (Nikkei)** | global risk sentiment, exports | `^FTSE`,`^GDAXI`,`^N225` | ✅ |
| **US VIX / India VIX** | fear gauge → de-risk | `^VIX`, `^INDIAVIX` ✅ (have) | ✅ |

## 2. MACRO / RATES / FLOWS (the biggest slow drivers)
| Driver | Effect | Source | Embed |
|---|---|---|---|
| **US Fed rates / US 10y yield** | high → FII outflows from India | `^TNX` | ✅ |
| **US Dollar Index (DXY)** | strong $ → FII selling → India ↓ | `DX-Y.NYB` | ✅ |
| **USD/INR** | rupee weak → FII out, IT/pharma exporters ↑, importers ↓ | `INR=X` | ✅ |
| **Crude oil (Brent/WTI)** | India imports oil → high oil = inflation, deficit, ↓ | `CL=F`,`BZ=F` (have WTI) | ✅ |
| **Gold** | safe-haven sentiment | `GC=F` (have) | ✅ |
| **FII / DII daily flows** | **huge** — FII selling sinks the market | NSE/Moneycontrol daily | ⚠️ scrape |
| **RBI policy, CPI inflation, GDP/IIP/PMI** | rates, liquidity, growth | RBI/MOSPI + event cal | ⚠️ calendar |
| **Budget, reforms, elections, monsoon** | policy/rural demand shocks | event calendar | ⚠️ calendar |

## 3. SECTOR / COMMODITY LINKAGES (your EV / metals idea)
| Sector | Up when… | Down/avoid when… | Sector index |
|---|---|---|---|
| **Metals** (Tata Steel, JSW, Hindalco) | China stimulus, LME metals ↑ | **China weak, metals ↓** → avoid | `^CNXMETAL` |
| **IT** (TCS, Infy, Wipro) | US/EU IT spend ↑, USD/INR ↑ | US recession fears | `^CNXIT` |
| **Auto / EV** (Maruti, Tata Motors, M&M) | demand ↑, fuel ↓, EV policy, festive | chip shortage, high rates | `^CNXAUTO` |
| **Banks/Fin** | credit growth, rate cuts | NPAs, liquidity squeeze | `^NSEBANK` |
| **Energy/Oil** (Reliance, ONGC) | crude ↑ (upstream), refining margins | crude crash | `^CNXENERGY` |
| **Pharma** | US generic pricing, exports | US FDA actions | `^CNXPHARMA` |
| **FMCG** | rural demand, good monsoon, low inflation | inflation, weak rural | `^CNXFMCG` |
| **Realty/Infra** | rate cuts, govt capex | high rates | `^CNXINFRA` |

→ **Sector rotation** = rank these sector indices by momentum, **tilt into strong / avoid weak**
(exactly "metals down → skip metal stocks; EV/auto up → prefer autos"). EV is a *curated basket*
(spans auto + components), not a single index. ✅ embeddable via sector indices.

## 4. OTHER-COUNTRY DEPENDENCIES (your specific question)
- **China** → India **metals/commodities** + EM risk sentiment (China stimulus lifts metals).
- **USA** → India **IT revenue**, **pharma exports/FDA**, overall risk + **FII flows**.
- **Europe** → IT/auto exports, global growth.
- **Middle East / OPEC** → **crude oil** → India inflation/rupee/deficit (geopolitics matters).
- **Global chips (Taiwan)** → auto/electronics supply.
- **Global supply chains / freight** → input costs, margins.

## 5. STOCK-SPECIFIC
| Driver | Embed |
|---|---|
| **Earnings results** (ride PEAD, never pre-predict) | ✅ calendar (have) |
| Analyst estimate **revisions / upgrades** | ⚠️ |
| Promoter pledging, management actions | ❌ |
| **Index inclusion/exclusion** (Nifty rejig) | ⚠️ |
| Corporate actions (split/bonus/buyback) | ⚠️ |
| **News headlines** (orders, scams, war) | ❌ → captured via **VIX spike + price/volume** |

---

## What we EMBED into the engine (free, systematic) — the plan
1. **Global-macro context block** (✅ now): S&P, China, DXY, US-10y, crude, gold, USD/INR, VIX →
   a daily **risk-on/off + bias score** that tilts/sizes the picker and de-risks in stress.
2. **Sector-momentum rotation** (✅): rank sector indices, prefer strong sectors, avoid weak →
   your EV-up / metals-down logic.
3. **Correlation cap** (✅, built): never hold 5 look-alike names.
4. **Earnings/PEAD + event calendar** (⚠️): ride post-result drift, size down into results/RBI/Fed.
5. **FII/DII flows, estimate revisions** (⚠️ later): need scraping; high value, more work.
6. **News text** (❌): not predicted — captured by VIX + abnormal price/volume (its footprint).

**Honest principle:** we don't *predict* news/geopolitics; we **react** to their measurable
footprint (volatility, price, sector moves, flows) — that's the part that's real and testable.
