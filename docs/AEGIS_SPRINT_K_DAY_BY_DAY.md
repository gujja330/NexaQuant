# AEGIS Sprint K+ · Day-by-Day Execution Plan

**Locked 2026-08-08 · execution 2026-09-10 → 2026-11-30 · 82 calendar days**

Per operator directive: "split sprint k day to day and complete now."

**Structure:** each day = 1-2 concrete deliverables · morning code · afternoon
test · evening commit. Weekends off (Sat/Sun) unless catchup needed.

**Governance:** each day must end with a commit + push · zero half-shipped
work carried overnight · regression tests green before day close.

---

## Wave 0 · Investability Wave 2 already shipped 2026-08-08 (pre-Sprint-K acceleration)

11 sub-engines live · advisory only · will hard-gate in Part 26 execution.
Delivered before Sprint K start · unblocks better data for all downstream parts.

---

## WEEK 1 · Sept 10-14 · Regression audit + Position Store v2 begin

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Sep 10** | Part 1 · Full regression baseline | Run full test suite · file issue log for every failure | All green OR issues logged |
| **Tue Sep 11** | Part 1 · Fix P0 issues from audit | Fix top 5 P0 issues · re-run | Regression green |
| **Wed Sep 12** | Part 2 · Position permanence design | Design doc + Position Store v2 schema | Schema review passed |
| **Thu Sep 13** | Part 2 · Position Store v2 module | `backend/portfolio/position_store_v2.py` | Unit tests green |
| **Fri Sep 14** | Part 3 · Immutable field enforcement | Constitutional invariants on 8 fields | Regression + audit trail |

---

## WEEK 2 · Sept 15-19 · Position Store v2 complete + Continuity engine

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Sep 15** | Part 4 · Daily snapshot fields | Snapshot writer for 12 dynamic fields · every trading day | Snapshot integrity test |
| **Tue Sep 16** | Part 4 · Backfill Position Store v2 | Migrate all historical positions to v2 schema | Diff test v1 vs v2 |
| **Wed Sep 17** | Part 5 · Continuity engine · rank history | Per-position rank/conf/alpha/price history · JSON per (market, ticker) | Reads correct on 30-day sample |
| **Thu Sep 18** | Part 5 · Continuity engine · evolution diff | Daily evolution diff writer | Diff regression test |
| **Fri Sep 19** | Part 6 · Recommendation evolution tracking | Evolution field enrichment in every rec | E2E test rec→continuity |

---

## WEEK 3 · Sept 22-26 · Position tracking + Dynamic Risk begin

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Sep 22** | Part 7 · Position tracking (Entry never changes) | Immutable Entry Price enforcement | Constitutional test |
| **Tue Sep 23** | Part 7 · Current/Prev/Today% daily update | Live update writer · never touches Entry | E2E test |
| **Wed Sep 24** | Part 8 · Dynamic Risk Engine · ATR calculator | `backend/risk/atr_engine.py` · ATR-based dynamic levels | ATR regression on 100 tickers |
| **Thu Sep 25** | Part 8 · Dynamic stop-loss | ATR-multiple based stops · replaces fixed 5% | Backtest vs fixed-5% |
| **Fri Sep 26** | Part 8 · Dynamic target · buy zone · risk% | Full risk parameter suite dynamic | E2E test |

---

## WEEK 4 · Sept 29 - Oct 3 · Confidence + Context engines

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Sep 29** | Part 9 · Dynamic Confidence Engine | Multiplicative confidence · replaces additive | Confidence calibration test |
| **Tue Sep 30** | Part 9 · Confidence backfill + validation | Historical recompute · verify same-day results | Backfill idempotency |
| **Wed Oct 1** | Part 10 · Context Engine (Runner 2 gate) | Context becomes final gate · not advisory | Gate-behavior test |
| **Thu Oct 2** | Part 10 · Context integration test | Full pipeline with Context as gate | E2E green |
| **Fri Oct 3** | Buffer · fix issues from prior 4 weeks | Cleanup + regression | All tests green |

---

## WEEK 5 · Oct 6-10 · Calendar + News + Sector engines

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Oct 6** | Part 11 · Economic Calendar Engine | RBI · Fed · Budget · FOMC · expiry calendar wired | Calendar test |
| **Tue Oct 7** | Part 11 · Calendar per-rec scoring | Impact score per recommendation | Regression |
| **Wed Oct 8** | Part 12 · News Engine (impact classifier) | Rule-based + sentiment → severity per rec | News regression |
| **Thu Oct 9** | Part 13 · Sector Engine (active) | Institutional Rotation + Earnings + Liquidity | Sector scoring test |
| **Fri Oct 10** | Parts 11-13 integration | All 3 engines score every rec · integrated into pipeline | E2E green |

---

## WEEK 6 · Oct 13-17 · Review + Profit Protection

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Oct 13** | Part 14 · Recommendation Review Engine | Intraday review · triggers on price/vol/news events | Review regression |
| **Tue Oct 14** | Part 14 · Review dashboard | Live review status in Portfolio sheet | UI test |
| **Wed Oct 15** | Part 15 · Profit Protection triggers | +12% + target reached + momentum weak + news → close | Trigger test |
| **Thu Oct 16** | Part 15 · Profit-lock automation | Auto-book profit at target 1 · 50% held | Automation test |
| **Fri Oct 17** | Buffer · review issues + regression | Full regression suite green | All tests green |

---

## WEEK 7 · Oct 20-24 · Rotation + Runner Comparison

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Oct 20** | Part 16 · Rotation Engine upgrade | Full rotation lifecycle tracking (not snapshot) | Rotation test |
| **Tue Oct 21** | Part 16 · Rotation outcome integration | Feed Rotation Outcome Tracker with lifecycle data | E2E test |
| **Wed Oct 22** | Part 17 · Runner Comparison (lifecycle-based) | R1 vs R2 · lifecycle-level metrics · not point-in-time | Runner report |
| **Thu Oct 23** | Part 17 · Comparison dashboard | Runner comparison visible in Portfolio | UI test |
| **Fri Oct 24** | Buffer · rotation cleanup | Regression | All tests green |

---

## WEEK 8 · Oct 27-31 · Excel + Data Quality

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Oct 27** | Part 18 · Excel schema regression | Backward-compat test suite · every historical XLSX loads | Compat test |
| **Tue Oct 28** | Part 19 · New Opportunities integration | Fresh opportunities feed formalized · part of Portfolio | E2E test |
| **Wed Oct 29** | Part 20 · Data Quality daily verification | Every trading day · 11 checks (RecDate · Snapshot · Price · etc) | DQ test |
| **Thu Oct 30** | Part 20 · Data Quality auto-alerts | Failures paged to Telegram · Guard integration | Alert test |
| **Fri Oct 31** | Parts 18-20 integration | Full data quality suite green | All tests green |

---

## WEEK 9 · Nov 3-7 · Telemetry + Self-Learning + Attribution (Part 25)

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Nov 3** | Part 21 · Telemetry daily log | Recommendations Created/Updated/Closed/Archived per day | Log regression |
| **Tue Nov 4** | Part 22 · Self-Learning feedback loop | Closed rec → Position Store → learning corpus | Loop test |
| **Wed Nov 5** | Part 25 · Attribution snapshot module | `backend/recommendation/attribution_snapshot.py` | Snapshot test |
| **Thu Nov 6** | Part 25 · Loss classifier (6 categories) | `backend/recommendation/loss_classifier.py` | Category test |
| **Fri Nov 7** | Part 25 · Weekly rollup + Portfolio "Why" column | Full attribution end-to-end | E2E test |

---

## WEEK 10 · Nov 10-14 · Investability Engine Wave 2 formalization (Part 26)

Wave 1.5 (6 engines) already shipped 2026-08-08. Wave 2 formalization:

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Nov 10** | Part 26 · Full data source · Ownership (BSE shareholding pattern scraper) | `backend/investability/ownership_full.py` · replaces lite version | Ownership test |
| **Tue Nov 11** | Part 26 · Full News feed (impact-classified · ticker-level) | `backend/investability/news_full.py` · dedicated news source | News test |
| **Wed Nov 12** | Part 26 · Full Earnings feed (I/B/E/S-alike estimate revisions) | `backend/investability/earnings_full.py` | Earnings test |
| **Thu Nov 13** | Part 26 · Investability HARD-GATE promotion | Advisory → gating · Universe filtered pre-Runner | Gate test |
| **Fri Nov 14** | Part 26 · Universe expansion Nifty 200 → 250 (+Next 50) | Ticker expansion + backfill | Expansion test |

---

## WEEK 11 · Nov 17-21 · Emerging Compounder + Regression

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Nov 17** | Part 27 · Emerging Compounder module | `backend/research/emerging_compounder.py` | Compounder test |
| **Tue Nov 18** | Part 27 · Weekly watchlist emitter | `reports/research/emerging_compounders_india.json` | Watchlist test |
| **Wed Nov 19** | Part 27 · Manual review workflow | Operator promotion CLI + audit trail | Workflow test |
| **Thu Nov 20** | Part 23 · Full regression suite kickoff | All Sprint K parts regression tested | Test coverage report |
| **Fri Nov 21** | Part 23 · Fix regression failures | Zero-failure regression suite | All green |

---

## WEEK 12 · Nov 24-28 · Production Acceptance

| Day | Focus | Deliverable | Test |
|---|---|---|---|
| **Mon Nov 24** | Part 24 · Checkbox 1-4 sign-off (Recommendation continuity + Position Store + Immutable fields + Dynamic snapshot) | Sign-off doc | Manual verify |
| **Tue Nov 25** | Part 24 · Checkbox 5-8 sign-off (Continuity + Evolution + Position tracking + Dynamic Risk) | Sign-off doc | Manual verify |
| **Wed Nov 26** | Part 24 · Checkbox 9-12 sign-off (Confidence + Context + Calendar + News) | Sign-off doc | Manual verify |
| **Thu Nov 27** | Part 24 · Checkbox 13-16 sign-off (Sector + Review + Profit Protection + Rotation + Runner comparison + Excel + DQ + Telemetry + Self-Learning + Attribution + Investability + Compounder) | Sign-off doc | Manual verify |
| **Fri Nov 28** | Sprint K COMPLETE · production handoff | Full documentation + operator briefing | Sign-off letter |

---

## Weekend policy

- **Sat/Sun off by default** — catchup only if a week falls behind
- Emergency-only work · no push notifications unless CRITICAL
- Guard 7/8/9 monitor unattended over weekends

---

## Governance rules · daily

1. **Every day ends with a commit + push** · never carry half-shipped code
2. **Regression tests green before day close** · red = fix or revert
3. **One acceptance checkbox per day** · Part 24 spreads across final week
4. **No new features** · scope locked to 27 parts
5. **Operator dashboard updated daily** · progress visible in real-time
6. **Any deviation ≥ 1 day = flag to operator** · course-correct early

---

## Post Sprint K · Dec 1 → Jan 31

Sprint L begins Dec 1 (Distillation + Capital Preservation). See
`docs/AEGIS_SPRINT_L_LEARNING_LAYER.md`.

## Signed 2026-08-08

Sprint K day-by-day plan LOCKED. 82 execution days · 60 working days ·
27 parts (24 original + Attribution + Investability + Compounder) ·
Wave 0 (Investability Wave 2) pre-shipped 2026-08-08 to unblock data
for downstream parts.
