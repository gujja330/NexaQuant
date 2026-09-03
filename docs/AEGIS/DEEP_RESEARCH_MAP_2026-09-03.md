# AEGIS · Deep Research Map · 2026-09-03

**Owner:** CEO directive 2026-09-03 · "Deep Investment Research · Investment Intelligence Audit."
**Purpose:** For every important dimension of investable edge / risk / failure · document what AEGIS needs · what exists today · what I can build alone · what needs external data · what needs statistical validation before promotion.

**Governance:** No implementation from this doc without CEO ack per-domain. Every row eventually gets a `KEEP / REJECT / RESEARCH FURTHER / PROMOTE-CANDIDATE` verdict. `Development Freeze` for R2 remains in effect until evidence earns a change.

---

## The 20 domains (CEO 2026-09-03 verbatim scope)

**1. Business quality** — revenue growth · earnings growth · margin quality · ROIC/ROE · FCF generation · FCF conversion · working capital · capital allocation · reinvestment economics

**2. Balance-sheet risk** — D/E · Net Debt/EBITDA · interest coverage · debt maturity/refinancing · liquidity/current ratio · cash quality · off-balance-sheet exposure

**3. Accounting quality** — Piotroski · Beneish · Sloan · cash-vs-profit divergence · receivables · inventory · one-offs · auditor signals

**4. Valuation** — P/E · EV/EBITDA · FCF yield · P/B · PEG · DCF · reverse DCF · relative · sector-relative · growth-adjusted

**5. Growth quality** — revenue accel · EPS accel · estimate revisions · guidance · surprise · forward growth vs price · durability

**6. Industry / sector** — momentum · leadership · relative strength · cycle · pricing power · capacity · competition · input cost · valuation dispersion

**7. Macro** — rates · inflation · GDP · FX · credit · liquidity · yield curve · commodity regime · financial conditions

**8. Market structure / flows** — FII/DII · Options PCR · short interest · volume · liquidity · institutional ownership · concentration · crowding

**9. Technical / price behaviour** — momentum · trend · RSI · ATR · volatility · volume confirmation · breakout quality · relative strength · drawdown/recovery · tail behaviour

**10. Corporate events** — earnings calendar · surprise · corporate actions · buybacks · dilution · rights issues · M&A · management changes

**11. Governance** — promoter pledge · related parties · insider transactions · auditor quality · board independence · controversies · capital allocation

**12. Narrative / information** — news sentiment · transcript prepared · transcript Q&A · guidance language · management consistency · narrative-vs-numbers divergence

**13. Knowledge graph** — communities · stability · ownership · supplier/customer · peers

**14. Risk** — single-stock · sector concentration · factor concentration · correlation · liquidity · gap · event · tail · drawdown · stress

**15. Portfolio construction** — sizing · Kelly · correlation-aware · sector caps · factor neutrality · turnover · capacity · cash allocation

**16. Exit science** — dynamic ATR · target · stop · time · signal deterioration · regime exit · MAE/MFE · winner preservation · loss containment

**17. Cross-market / global** — India · USA · USD/INR · US rates → India · global risk regime · commodity transmission

**18. Data integrity** — PIT universe · PIT fundamentals · PIT sector · PIT KG · survivorship · look-ahead · revision · missing-data · delisting

**19. Statistical robustness** — walk-forward · OOS · DSR · Reality Check · multiple testing · bootstrap · regime splits · stability

**20. Failure research** — missed winners · realised losers · zero-entry · model disagreement · data failure · regime failure · portfolio failure

---

## Capability matrix · what I can genuinely do alone

**Legend**
- 🟢 CAN — I can develop AND run test against real substrate today
- 🟡 PARTIAL — I can build scaffold + math + tests · but empirical validation blocked on data/time
- 🔴 CANNOT — needs external data source · calendar time · or domain-expert judgement I don't have
- ⚫ ALREADY DONE — already shipped in prior work

| # | Domain | Scaffold code | Empirical test | What blocks the empirical test |
|---|---|---|---|---|
| 1 | Business quality | 🟡 | 🔴 | Historical fundamentals snapshots · today only |
| 2 | Balance-sheet risk | 🟡 | 🔴 | Same · plus debt-maturity data not in yfinance free tier |
| 3 | Accounting quality | ⚫ L1 (Piotroski/Beneish/Sloan) done · 🟡 rest | 🔴 | Historical statement snapshots · auditor-signal data source |
| 4 | Valuation | ⚫ L2 partial · 🟡 DCF/PEG/growth-adjusted | 🟡 | Static values today · rolling PIT accumulation missing |
| 5 | Growth quality | ⚫ L3 partial · 🟡 durability | 🔴 | Estimate revision history · consensus feed |
| 6 | Industry / sector | ⚫ sector regime · 🟡 pricing power / capacity | 🔴 | Industry-cycle indicators not in current data |
| 7 | Macro | ⚫ regime enricher (BULL/BEAR/HIGH_VOL/NEUTRAL) · 🟡 financial-conditions composite | 🟡 | Need to build FCI from rates+credit+FX+equity · doable |
| 8 | Flows | ⚫ shim for FII/DII + PCR (REQUIRES_LIVE_SOURCE) · 🟡 crowding/concentration | 🔴 | NSE FII/DII feed · options-chain scraper · 13F ingest |
| 9 | Technical / price | ⚫ momentum/RSI/ATR/vol · 🟡 breakout quality · tail behaviour | 🟢 | Have full parquet history · can compute all today |
| 10 | Corporate events | ⚫ earnings calendar · 🟡 buybacks/dilution/M&A | 🔴 | Corp-actions history in parquet dividends/splits · rest external |
| 11 | Governance (India) | ⚫ promoter-governance scaffold · 🟡 board/auditor/controversies | 🔴 | SEBI SAST · BSE disclosures · media watchdog feeds |
| 12 | Narrative | ⚫ transcript-tone (Q&A sep) scaffold · lexicon stub · 🟡 real NLP | 🔴 | Transcript ingest (SeekingAlpha/bamsec/MoneyControl) · not wired |
| 13 | Knowledge graph | ⚫ persistence hook · backfill scaffold · 🟡 supplier/customer graph | 🔴 | Daily KG runner must call the hook · historical UNKNOWN forever |
| 14 | Risk | ⚫ isolation/exit/dyn-stop · 🟡 factor/tail/liquidity | 🟡 | Factor-neutral needs cross-sectional regression daily · doable · but sample thin |
| 15 | Portfolio construction | ⚫ position store · 🟡 correlation-aware sizing · capacity | 🟡 | Historical portfolio state PIT not reconstructed |
| 16 | Exit science | ⚫ dynamic ATR · target · time · 🟡 signal-deterioration + regime exit | 🟢 | Have data · P0-EXT-01 already ran 60 trials · all FAIL |
| 17 | Cross-market / global | ⚫ India · USA parallel · 🟡 USD/INR · rates transmission | 🟡 | Need to wire FRED/RBI feeds for rates · doable |
| 18 | Data integrity | ⚫ PIT universe scaffold · walk-forward · 🟡 revision-bias audit | 🟡 | Historical constituent lists not sourced (NIFTY 200 · MidCap 400) |
| 19 | Statistical robustness | ⚫ walk-forward 252/63/21/5 · paired bootstrap · DSR · LR | 🟢 | Have full engine · applies to any experiment with sample |
| 20 | Failure research | ⚫ NEG-PNL · POS-PNL · joint P&L · zero-entry readout | 🟢 | Have engine · can extend to model/data/regime/portfolio failure |

## Totals

| Rating | Count |
|---|---:|
| 🟢 CAN develop + test end-to-end today | 4 domains (9 · 16 · 19 · 20) |
| ⚫ + 🟡 partly built · empirical validation blocked | 12 domains (need data/time) |
| 🔴 CANNOT do alone · needs external data source | 4 domains (11 India governance · 12 transcript · 10 corp actions beyond dividends/splits · 8 flows-live) |
| Total scaffoldable today | 20 (all can get scaffold code + math + gate) |
| Total statistically validatable today with real numbers | 4 (9, 16, 19, 20) |

## Straight yes/no · can I develop AND test everything you gave

**Develop scaffold + math + tests + BLOCKED-EVIDENCE gates for all 20:** YES · I can ship all 20 domains as Research Tickets with the same discipline as R3 Tier-2/3 (each module carries `RESEARCH_TICKET`, `evaluate()`, default `BLOCKED-EVIDENCE`, unit tests).

**Empirically test all 20 today against real substrate with statistical rigour:** NO · only 4 of 20 have complete substrate + data + sample to produce a genuine PASS/FAIL/REJECT verdict today. The other 16 will honestly return `BLOCKED-EVIDENCE` or `INSUFFICIENT_SAMPLE` per V2 §33 discipline.

## What each 🔴 needs from external sources

| Domain | External source needed | Notes |
|---|---|---|
| 8 Flows-live | NSE FII/DII daily CSV · NSE option-chain API | free but rate-limited · scrapers to build |
| 10 Corp events (beyond splits/dividends) | Buybacks · M&A · rights issues · management changes | typically SEBI filings · RBI announcements · press releases |
| 11 Governance (India) | SEBI SAST/RPT disclosures · BSE announcements · board-composition · auditor changes | scrapers to build · legal-quality NLP needed |
| 12 Transcript ingest | SeekingAlpha / bamsec (USA) · MoneyControl / SmallCase (India) | many are paid · free tier scrapers fragile |

## What each 🟡 needs to become 🟢

- **Historical fundamentals accumulation** · start daily populator cron · N days → n rows per ticker (currently 1 asof)
- **Historical KG per-node community persistence** · daily KG runner calls `persist_pit_snapshot()` · accumulate 90+ days
- **Historical portfolio state PIT** · Registry already append-only · needs a nightly snapshot script
- **NIFTY 200 + MidCap 400 constituent history** · authoritative list source (NSE index rebalance PDFs · S&P methodology PDFs) · one-time scrape + change_events yaml
- **Rates/FX feed (macro depth)** · FRED (USA) · RBI Handbook (India) · CSV APIs free

## My honest recommendation before you say build

Rather than one giant "build all 20" batch that repeats the earlier mistake, do it in **three waves**, each with its own PDF-style acceptance gate:

**Wave 1 · 🟢 domains (4)** · genuine statistical results today
- Deep technical/price research (domain 9): breakout quality · tail behaviour · volume-confirmation lift over baseline
- Deep exit science (domain 16): signal-deterioration · regime exit · MAE/MFE frontier
- Statistical-robustness pass (domain 19): apply full WF/DSR/RC/LR framework to everything already run
- Failure research extension (domain 20): model-failure · data-failure · portfolio-failure decomposition

**Wave 2 · 🟡 domains (12)** · scaffold + gate + start substrate accumulation
- All get Research Ticket + module + BLOCKED-EVIDENCE default
- Data accumulation crons for fundamentals · portfolio state · KG communities · index constituents

**Wave 3 · 🔴 domains (4)** · declared additive extensions · external ingest work
- SEBI/NSE scrapers for governance + flows
- Transcript ingest evaluation
- Corp-events beyond splits/dividends

Each wave commits locally · no push · you review before authorising the next.

## What I will NOT do

- Adopt the seven-filter screenshot rules blindly · they get **researched**, not copied
- Change R2 in this work
- Promote anything
- Fabricate factor values when data is missing
- Skip DSR deflation on multi-trial searches
- Claim "validated" for a scaffold

## Final line

I can ship code scaffolds + math + tests + gates for all 20 domains. I can produce statistically-honest empirical results for 4 today. The other 16 will return BLOCKED-EVIDENCE with the specific blocker named per domain. Anything else would be dishonest per the V2 rules you set.
