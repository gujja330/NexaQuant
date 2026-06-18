# Stock Selection Checklist (research-backed)

A serious-analyst workflow: first eliminate bad stocks, then rank survivors by business quality,
catalyst, trend, and risk. The literature supports combining fundamentals, technicals, news/text,
and macro context — not relying on one signal. This is the human framework that Arjuna's engine
(and its AI refinement, see AI_ML_REFINEMENT_PLAN.md) operationalizes.

## 1) Universal "must-pass" checklist
**A. Business quality** — explainable in one sentence; revenue not one-customer/one-off; durable
moat (brand/scale/cost/switching/regulation/tech); stable/improving margins; positive (or clearly
turning) free cash flow; manageable debt; no chronic dilution/capital destruction.
**B. Valuation** — not expensive vs own history & peers; supported by growth/margins/catalyst; you
know exactly what must happen to justify it. (Profitable firms beat unprofitable; "cheap but weak" disappoints.)
**C. Trend & structure** — liquid enough for the horizon; price above key MAs or confirmed recovery;
volume supports the move; visible support/resistance; a pre-defined exit if the chart fails.
**D. Catalyst** — a specific reason to move (earnings, guidance, launch, regulation, contract, margin,
rates, sector cycle, restructuring) that changes future cash flows/risk and isn't already fully priced.
**E. Regime & sector** — sector in a favorable/improving phase; not fighting a weak sector; know the
stock's sensitivity to rates/oil/currency/global risk.

## 2) Horizon-specific
- **Intraday** (liquid names only): high volume, tight spreads, clean opening-range/breakout, clear
  news catalyst, market+sector aligned, defined stop BEFORE entry. Liquidity/volatility/structure > fundamentals.
- **Swing/Delivery (days–weeks)**: acceptable fundamentals + catalyst + confirmed daily trend + supportive
  sector + sane valuation + risk:reward ≥ 2:1. Fundamentals and technicals work together here.
- **Long term (compounders)**: durable revenue growth, real (not accounting) profitability, consistent
  cash flow, controlled debt/dilution, valuation leaving room to compound, good capital allocation, structural sector tailwind.

## 3) Research insights that should change how you pick
1. **Momentum works but crashes** — check crowding/regime/downside before chasing a run-up.
2. **Quality/profitability is not optional** — cheap + weak = trap (Novy-Marx).
3. **Value & momentum are opposite forces** — combining them reduces regime dependence (Asness-Moskowitz-Pedersen).
4. **Technical patterns add *incremental* info** — timing/risk tool, not a fundamentals replacement (Lo-Mamaysky-Wang).
5. **News sentiment helps when extracted properly** — supervised text models beat crude sentiment (Ke-Kelly-Xiu).
6. **Macro changes how micro-news is priced** — same earnings, different reaction by macro backdrop.
7. **Analyst recs = confirmation, not thesis** — best from experienced/accurate analysts.
8. **Earnings season creates effects** — attention -> opportunity AND traps (announcement premium / PEAD).
9. **Global factors matter** — broad USD is a key driver of EM (incl. India) returns.
10. **Same-sector names move together** — many stocks in one theme ≠ diversification.

## 4) Reject a stock if several are true
Can't explain the business; high debt + weak cash flow; poor/inconsistent earnings quality; depends on
repeated dilution; illiquid/manipulable; broken chart + heavy down-volume; hype with no measurable catalyst;
sector in broad downtrend with no independent edge; buying only because it already rose.

## 5) Scoring (0–5 per category, horizon decides weights)
- **Long-term**: business 5, profitability/CF 5, valuation 4, management 4, sector 3, trend 3, catalyst 2, regime 2
- **Swing**: trend 5, catalyst 5, sector 4, liquidity 4, valuation 3, business 3, news 3, regime 3
- **Intraday**: liquidity 5, volatility 5, clean levels 5, news 4, index/sector align 4, spread 4, time-of-day 3, fundamentals 1–2

## 6) How AI should be used
USE for: reading filings, summarizing calls, news-sentiment extraction, clustering similar names,
scoring sector momentum, spotting unusual volume/news bursts. DON'T use as: the final authority, a
replacement for reading the source, or a substitute for risk management. AI = ranking + alert engine, not oracle.

## 7) Daily workflow
1. Market regime (rates, USD, oil, inflation, global risk). 2. Strong vs weak sectors. 3. Screen quality/CF/debt.
4. Catalysts & news. 5. Confirm chart + volume. 6. Reject crowded momentum if crash risk high. 7. Buy only when
thesis + valuation + trend + risk all line up.

## 8) Final rule
A "proper stock" = business quality, valuation, trend, catalyst, and regime all agree. A "bad stock" fails on
≥2 at once. No single signal is enough — the best results combine fundamentals + technical timing + news + macro.

### Sources
Gu-Kelly-Xiu (Empirical Asset Pricing via ML); Novy-Marx (profitability); Asness-Moskowitz-Pedersen
(Value & Momentum Everywhere); Lo-Mamaysky-Wang (Foundations of Technical Analysis); Ke-Kelly-Xiu
(text/news); NBER (earnings announcement premium; momentum crashes); BIS (dollar beta & EM returns);
FINRA (concentration/correlation); SEC (filings/financials); CFA Institute (AI/text mining caveats).
