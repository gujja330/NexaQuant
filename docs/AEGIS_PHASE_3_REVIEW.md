# AEGIS Phase 3 findings

## Production status

The November 24 combined local run exited 1 in staging. No workbooks were promoted and no Telegram messages were sent.

| Market | Stages completed | Certification blocker |
| --- | --- | --- |
| India | Market refresh through November 23, freshness, R1 | V2 rejected same-day SSoT reuse. The corrected step passed in isolation and still needs a combined rerun. Backend validation separately reported five stale datasets. |
| USA | Price refresh for 513 of 520 requests. Daily ops found all 19 required artifacts and passed all nine schema checks. | Backend validation failed 64 of 85 datasets and the required operations check returned CRITICAL. Contract, workbook and research certification did not run. |

The USA refresh did not return current bars for GGP, IQVIA, LVMH, MBIA, SCANA, SNDK and TSYS. None is in the active position registry. The staged CNP parquet was compared cell for cell with the saved parquet across all 1,254 original rows. It preserved every row and added four through November 23. [India stages](aegis-phase3/india-stage-results.json), [USA stages](aegis-phase3/usa-stage-results.json), [USA operations report](aegis-phase3/usa-ops-check.json), [USA validation summary](aegis-phase3/usa-backend-validation-summary.json), [USA refresh manifest](aegis-phase3/usa-staged-market-data-freshness.json)

### Confirmed engineering fixes

- **USA price refresh.** The writer now preserves existing bars and verifies five overlapping closes before adding new rows on the same basis. It tests both provider close series and fails when neither agrees. It requests a short window for recent series and preserves the scoring membership. The daily price request list now also includes active, non-retired registry tickers outside the scoring list.
- **CNP.** The November 19 cash dividend was $0.24. The prior close was $39.88, so the implied adjustment was about 0.602%. The provider's adjusted close reproduced that factor. The saved series matched the provider's raw close over the overlap. An isolated append added four bars through November 23 and preserved all 1,254 old rows for the series used by episode `USA-R2-CNP-20260928-4b9940`. This verifies the refresh at the saved basis. It does not identify a broker entry fill. [CNP calculation](aegis-phase3/cnp-price-basis.json), [CenterPoint dividend history](https://investors.centerpointenergy.com/stock-information/dividends-splits)
- **India same-day SSoT.** V2 previously marked guarded SSoT red when its recommendations stayed sealed for the same day. It now accepts reuse after archive, recommendation and GREEN-health verification. The staged single-step regression passed with zero critical failures.
- **Stop audit dates.** The exit bridge formerly searched earlier bars using today's trailing stop and wrote the retrospective date into the reason. New output records evaluation date and close-observation date separately. The exit rules, historical records and registry closure date policy remain locked. All 137 India R2 stop exits in the saved book have a legacy trigger date from this path, so those historical dates alone cannot prove when the stop became actionable. [Stop-date evidence](aegis-phase3/india-stop-date-audit.csv)

The India backend validation report also showed five stale datasets, including company, global, industry and sector context and the legacy learning corpus. This is a separate source problem. Relabelling the verified SSoT result does not refresh those inputs.

### USA universe and data coverage

| Scope | Saved evidence |
| --- | ---: |
| Configured master across named lists | 919 unique symbols |
| Legacy S&P 500 plus MidCap list | 918 |
| Active production scoring, feature snapshot and freshness universe | 516 |
| Daily requests for live configuration before retries | 520, including four benchmarks |
| Stored daily equity parquets | 904 |
| Non-retired ACTIVE registry episodes | 83 |
| Non-retired active symbols outside current scoring | 0 |
| Historical closed registry tickers | 508 |
| Tickers with saved USA opportunity outcomes | 507 |

The production setting is already `sp500`. The file behind it was fetched on July 29 and holds 516 symbols. S&P DJI reported 503 constituents in its October dashboard. The active file needs an evidence-based membership reconciliation. The local list named Nasdaq-100 is a 30-name subset. Nasdaq and S&P DJI report 101 securities for their full Nasdaq-100 and S&P 100 references. These counts do not establish membership overlap. [USA inventory](aegis-phase3/usa-universe-summary.json), [Per-symbol classification](aegis-phase3/usa-universe-freshness.csv), [S&P 500 index report](https://www.spglobal.com/spdji/en/documents/performance-reports/dashboard-sp-500-factor.pdf), [S&P 100 index](https://www.spglobal.com/spdji/en/indices/equity/sp-100/), [Nasdaq-100 index](https://indexes.nasdaqomx.com/Index/Overview/ndx)

Against the saved wide universe, 508 members had stale bars and eight had no bars. The file list identifies both populations by symbol, alongside retired, closed, active, and research membership. The breadth gate uses the newest eligible bar, while the publication price gate additionally checks active episodes. Historical-only securities remain preserved and can sit outside the daily refresh. The configured broad alternative implies roughly 922 per-symbol calls before retries if it uses the same benchmark set. A defensible relative opportunity-quality and historical execution-cost comparison across S&P 100, Nasdaq-100 and S&P 500 still needs point-in-time member files. Attempts to retrieve dated issuer holdings CSV from the public pages returned HTML. No universe was resized.

### USA research coverage

The pre-reset archival recovery remains valid as a research candidate set. It does not restore fresh current P0/P1. The current USA position store has no historical entries. Among 242 distinct USA R2 IDs in the available sealed decisions, 230 lack a snapshot on the recorded entry date and the other 12 show conflicting entry quotes across snapshots. The archived 15 P0 candidates were kept separate. Choosing a later quote or resetting an older position to today's close would change the original entry evidence. Current market-complete P0/P1 still needs an episode-keyed source with authoritative original prices. [USA sealed-entry audit](aegis-phase3/usa-sealed-entry-provenance.csv), [Phase 2 recovery baseline](aegis-phase2/usa-research-recovery.json)

## Investment research

### India performance reconciliation

The November 24 workbook uses the 149 R2 rows classified as REALIZED EXIT. It counts 30 positive returns, a 20.13% win rate under a greater-than-zero rule, and a −2.44% arithmetic mean. The loss-attribution report walks registry CLOSED episodes in its 90-calendar-day lookback and requires a price-derived return. It counted 170 records, 25 returns greater than +0.5%, a 14.71% rate and a −2.27% mean. It includes administrative and retired history that the realized production view excludes.

All 149 workbook episodes matched unique registry identities and had exactly the same return in both reports. Using +0.5% on those same 149 gives 25 wins. The other 21 records comprise 16 R2 and five R1 records, including 10 phantom administrations, four registry-sync closes, six rotations and one retired-runner cleanup. These are valid separate views. Use the realized-workbook population for the saved production win rate and the loss-attribution population for the registry diagnostic. The workbook profit factor uses aggregate positive returns divided by aggregate absolute negative returns. Alpha's loss-attribution ratio uses mean winner divided by mean loser. [Exact reconciliation](aegis-phase3/india-performance-reconciliation.csv)

### Broad market, sector and stock selection

| Cohort | Paired / total | Mean stock | Mean date-matched market | Excess |
| --- | ---: | ---: | ---: | ---: |
| India R2 open | 45 / 47 | +9.93% | +8.68% | +1.25 pp |
| India R2 realized | 140 / 149 | −2.54% | −0.46% | −2.08 pp |
| India R2 realized, exits November 10 onward | 12 / 12 | +1.26% | +11.79% | −10.53 pp |
| USA R2 open, saved stale marks | 78 / 83 | +1.78% | −3.94% | +5.71 pp |
| USA R2 realized | 35 / 176 | −2.64% | −0.40% | −2.25 pp |

Each row uses saved prices on exact entry and endpoint sessions. Workbook and saved prices must agree within 0.5% at both endpoints. The benchmarks are the local Nifty 50 and S&P 500 **price** indices, with no dividend reinvestment model. India open winners overlapped in exposure and dates. The paired results are proxies for arithmetic excess, not a risk- or capital-weighted estimate. Among 16 usable India Financial Services rows, the stock mean was +12.92%, Nifty 50 +8.86%, and the Nifty Bank exposure proxy +12.05% over the same windows. Much of that group's excess coincides with bank exposure. This proxy is imperfect for the non-bank names. Against the supplemental Nifty 500 price series, the same 45 open episodes averaged +3.98 pp excess and the same 140 realized episodes averaged ?1.32 pp. USA sector coverage was limited to one open and three realized observations. Complete sector and size attribution and independent stock price validation remain open. [Supplemental benchmark results](aegis-phase3/supplementary-benchmark-summary.json) [Episode benchmark observations](aegis-phase3/episode-benchmark-attribution.csv), [NSE price and total-return definitions](https://betanseapi.nseindia.com/static/products-services/indices-faqs)

### Holding horizon and profit protection

The live exit bridge compares calendar days held against a configured or fallback horizon and can exit earlier on the stop or target. These values are maximum decision windows in that path. They are not minimum hold periods. The separate India Dynamic Holding engine produced staged recommendations with 9–17 days. The workbook and modeled horizons should be interpreted with their source and unit.

On the same 107 India pre-November entry episodes, simulated net close-to-close returns at 3, 5, 10, 15 and 20 sessions were −0.38%, −0.27%, −0.90%, −1.18% and +0.11%. A fixed 20-session exit and three experimental stop variants used the same sample and 20 bps round-trip costs. The 5% initial stop, break-even after an earlier +8% high and 8% trailing variant returned −0.90%, −0.81% and −0.56%, with mean holding periods 13.34, 13.31 and 12.83 sessions. Stops used only prior highs, filled at the worse of the stop or a gap open, and excluded the exit-session high in the MFE lower bound. The quoted stop results exclude a benchmark close at an unknown intraday fill time. These tests cannot select an optimal alternative. Four eligible India rows reached a 60-session counterfactual and none reached 90. November vintages had no mature 20-session cohort by this cutoff. [Trial observations](aegis-phase3/historical-entry-exit-trials.csv), [Horizon and exit summary](aegis-phase3/historical-entry-exit-summary.csv)

### Profitable positions and targets

All 27 blank R2 targets in the India workbook have stored targets at or below the last price and are intentionally withheld by the renderer. This includes PNB, UNIONBANK, MM, TATAELXSI, SHRIRAMFIN, BALKRISIND, SBIN, EXIDEIND, AXISBANK and IOC. The paired bridge audit records HOLD for those episodes and no T1/T2. This does not establish a transition into a new trailing mode. The positive gains at quoted stops are conditional on execution.

LODHA, YESBANK and BANDHANBNK had saved post-entry highs above the currently displayed levels. The bridge checks the latest close against its live T1/T2 fields, which were empty in the saved audit for all three. A historical high above a later displayed value does not prove a previously actionable target or missed exit. [Target fields and episode evidence](aegis-phase3/india-target-audit.csv)

### Opportunities, disagreement, and re-entry

The saved 228-name India score and recommendation artifacts attribute disagreement to 214 candidate rows. The workbook shows 162. Those are distinct same-day artifacts. The model vectors and sign classifications are included, but do not explain the workbook number without its exact upstream score snapshot. The existing rule uses directional votes divided by all scoring models, including model scores inside its neutral band. No threshold changed. [Per-model evidence](aegis-phase3/india-model-disagreement.json)

Sealed prior scores let us compare contemporaneous conflicts with next-session marked performance. In the mature November slice, 1,296 disagreement observations over six signal dates averaged +2.51% net at five sessions. The would-be-new side had only two observations of one ticker and averaged −3.90%. The two groups are too imbalanced to measure an admission advantage. The separately implemented screens for sector-relative strength, sector leaders, pullbacks, volume breakout, earnings surprise and post-correction rebound also use next-session entry and 20 bps round-trip cost. Five-session quality pullbacks averaged +1.36 pp net excess in November on 21 observations over six dates, versus −1.05 pp before November on 125 observations. The unstable sign, multiple hypotheses and overlapping observations preclude promotion. Earnings surprise is the available proxy. Earnings acceleration and fundamental improvement need successive point-in-time fundamentals. [Sealed forward comparison](aegis-phase3/india-sealed-horizon-comparison.csv), [Opportunity trials](aegis-phase3/india-opportunity-comparison.csv)

The India saved opportunity dataset reproduces 50 wins in 139 mature NEW events with −0.60% mean and 13 wins in 21 mature RE-ENTRY events with +2.77% mean. The 157 and 46 headline counts include immature events. The saved USA file had zero mature 20-day observations for either cohort. Across four matched India entry weeks, re-entry averaged +8.12 pp above NEW, with one week contributing a +21.29 pp spread. Overlapping observation windows and small counts limit interpretation. [Week-matched results](aegis-phase3/india-reentry-week-matched.json) [India re-entry evidence](aegis-phase3/india-reentry-evidence.json), [USA re-entry evidence](aegis-phase3/usa-reentry-evidence.json)

### Capital and remaining research

The 10- and 20-slot equal-budget experiments compared holding for 20 sessions with rotating at most one holding per score event with a 0.20 score advantage. Orders used the next session's close and 10 bps per side. September simulations halted after one trade session when held marks were absent. A separate November start ran through November 18 and then halted on another held-mark gap. Returns through the same endpoint were +1.01% at 10 slots and roughly +3.45% at 20 slots, versus +8.26% for Nifty 50. Differences between the hold and rotate schedules were negligible before the halt. Missing held prices were not filled with future quotes or treated as sales. Physical stop-order fills, sector caps, correlations, real capital constraints and wider price histories are needed before this can support a portfolio policy. [Funded simulation paths](aegis-phase3/india-capital-trial-paths.csv), [Machine-readable results](aegis-phase3/summary.json)

1. Establish immutable entry and exit sources and fresh full-universe stage evidence before production certification.
2. Pair exact historical windows with verified sector and size benchmarks and measure added value over the strongest eligible alternatives.
3. Re-test re-entry and pullback hypotheses on later non-overlapping cohorts. Keep current entry thresholds and position sizing governed by the existing contract.
4. Evaluate the genuine index alternatives on dated memberships before changing the scoring universe.

Reproduce the read-only price, exit and research experiments using `python scripts/audit_aegis_phase3.py --asof 2026-11-24 --out docs/aegis-phase3`. For live readiness use the staged procedure in the [Phase 2 Windows runbook](AEGIS_LOCAL_STABILIZATION_PHASE_2.md). Fresh full-run completion, repeat-run certification, market-complete current research, and comparative strategy approval remain open.

