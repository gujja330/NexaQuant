# AEGIS Phase 2 production closure

## Status on November 24, 2026

India and USA remain uncertified. Stage execution, published state, market price integrity, episode coverage, and investment decision evidence are separate checks. The local runner builds in isolation and returns a failing status when a required stage fails. No live Telegram delivery or production-data migration was performed.

## State protection and recovery

The runner creates one copied workspace per market under the sibling directory `.prism-aegis-local`, which stays on the same volume as the repository. The runner acquires an OS-backed single-writer lock and recovers unfinished publications before beginning a new attempt. Each workspace has its own sources and report paths. Staged children get the staged import path. Telegram secrets and dotenv files stay outside the workspace. Angel settings are passed to children through the environment. The runner pins the output root to the staged workspace even if the parent shell specifies a different output root.

An attempt can be **attempted**, **failed**, **completed in staging**, or **certified and published**. The journal is the authoritative record of a committed publication. Build-only execution produces no delivery receipt. Shared research has a separate staged P0/P1 transaction.

The runner validates the workbook via the build-only sender and compares the dated workbook with the validated undated alias before promotion. The publication journal records SHA-256 for previous and staged files. Prior versions are saved under the run's `before` directory. Files are replaced atomically one at a time, with workbooks last. Recovery restores a prior version or removes a file created by the interrupted transaction. It checks the recorded hashes before touching paths and preserves artifact timestamps during replacement and recovery. A failure for one market leaves the other market eligible to run.

Publication rejects a rewritten opportunity registry, other-market registry events, and evidence loss in protected lineage and snapshot ledgers. Publication scopes follow explicit market paths and market names in shared output paths. Untagged shared artifacts still need a producer-by-producer review. The lock covers the canonical local runner. Direct scripts and scheduled external jobs do not participate in that lock. Multi-file publication is journaled, so a reader outside the runner can see an in-progress set. Hard process termination was tested. Broader regression testing also surfaced two concurrent Windows lifecycle reads that returned no data during atomic replacement. Lifecycle reads now retry transient file access and surface malformed data. Power loss and simultaneous legacy writers remain unverified.

Isolated tests cover failed staging, market-path isolation, a workbook replacement failure, interrupted publication with a real child-process exit, idempotent recovery, preserved registry history, subprocess timeout, and an external edit detected before publication. The phase-one flat backup of 136 files remains a separate recovery source.

## Historical episodes

The 23 previously flagged CURRENT exclusions are retired R1 episodes. The delivery policy keeps them in the registry for audit. Their exact IDs and available price evidence are in [retired-active-exclusions.csv](aegis-phase2/retired-active-exclusions.csv). No historical records were reclassified as investments.

A scan of 101 locally available Git revisions of the opportunity registry found zero IDs outside the current local ledger. This is evidence for the tracked registry only. It does not cover discarded artifacts, missing Git history, or all durable audit stores. See [registry history scan](aegis-phase2/registry-history-outside-local.json) and the [phase-one episode reconciliation](AEGIS_LOCAL_EPISODE_RECONCILIATION.csv).

The existing USA lineage recovery added all 18 eligible aged-out closures in isolation, with zero duplicates on repeat. Local self-heal now checks child return codes and invokes the existing reconciler after the workbook rebuild. Unaccounted in-window closures still fail. The recovered test ledger was kept separate from live production.

## Price integrity

The sender previously checked the legacy unified history population even after rebuilding the final two-sheet workbook. It now checks final CURRENT episodes and REALIZED EXIT rows of the same workbook sent through the XLSX validator. Administrative, advisory, and stop-breach rows remain distinct evidence. Saved-workbook testing produced the following snapshot.

| Market | PI1 | PI2 | PI5 as of November 24 |
| --- | --- | --- | --- |
| India | 197 prices checked, zero failures | 149 exits checked, zero failures | 47 active tickers checked, zero stale |
| USA | 268 prices checked, zero failures | 176 exits checked, zero failures | 89 active tickers checked, all 89 last bars dated November 17 |

PI1 and PI2 preserve their existing prior-session comparison policy. The strictly same-date investment audit below produces lower coverage. Neither result proves the original transaction price on its own. The canonical lifecycle still resolves historical entry prices from bars. India uses adjusted closes in its historical downloader and unadjusted closes in refresh. USA's rolling five-year downloader uses adjusted data. Preserving trade-price and adjusted-price bases separately remains open.

Legacy India reported 369 unexplained entry drifts and 854 inferred corporate-action explanations. The reports are preserved in full in the evidence directory. The prior inference treated any matching-prefix event in a broad window as an explanation. The guard now requires the exact symbol, a post-entry split inside the as-of window, and a split factor that accounts for the numerical difference. Dividend and demerger adjustments still require separate evidence. The renderer now accepts a frozen snapshot only for matching market, ticker, runner, and entry date and fills a missing value. It logs conflicts and leaves existing entry dates and prices in place.

Provider requests now use the existing alias configuration for MM and LTIM, including the sender's sector and price-guard corporate-action lookups. LTM is the verified exchange symbol for LTIM. TATAMOTORS to TMPV and Gujarat Gas's arrangement involve corporate actions, so historical series were kept separate pending continuity evidence. PEL and the remaining invalid, delisted, or stale symbols still need case-level verification. USA refresh now translates exchange class-share notation for provider requests while keeping canonical symbols in filenames. The live provider returned November 23 bars for both BF.B and BRK.B after translation. Readiness preserves the class suffix in coverage reports. USA daily prices now stop at the last completed regular exchange session. A live VIX probe confirmed that the producer excluded the partial November 24 value and retained November 23. [NSE LTIM circular](https://nsearchives.nseindia.com/content/circulars/FAOP72935.pdf), [NSE Clearing Tata Motors circular](https://nsearchives.nseindia.com/content/circulars/CMPT70934.pdf), [Gujarat Energy exchange filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_210488_05112026181948_iXBRL_WEB.html)

Evidence includes the [India final-sheet checks](aegis-phase2/india-workbook-price-integrity.json), [USA final-sheet checks](aegis-phase2/usa-workbook-price-integrity.json), [India legacy discrepancy register](aegis-phase2/india-legacy-price-discrepancies.json), and [USA legacy discrepancy register](aegis-phase2/usa-legacy-price-discrepancies.json). The archived report review classified 1,223 India PI1 differences, representing 369 previously unexplained and 854 previously attributed to corporate actions. None was reproduced by the exact recorded post-entry split factor using the saved price pair. This leaves provider basis, transaction-price provenance, and other corporate actions open. Legacy rows do not carry episode IDs. The detailed review records candidate registry IDs and ambiguity. [India PI1 classification](aegis-phase2/india-legacy-pi1-classification.json), [USA PI1 classification](aegis-phase2/usa-legacy-pi1-classification.json)

The public data provider returned November 23 bars for all 89 stale USA CURRENT tickers. An isolated append-only trial kept every existing row and brought 88 of 89 past PI5. CNP stayed blocked because its adjusted overlap moved 0.60181%. A declared $0.24 dividend with a November 19 record date is consistent with the difference. Price-basis continuity still needs verification for that series and for the full universe. [Provider coverage](aegis-phase2/usa-active-provider-freshness.json), [Append-only trial](aegis-phase2/usa-active-price-append-trial.json), [CenterPoint dividend announcement](https://investors.centerpointenergy.com/news-releases/news-release-details/centerpoint-energy-declares-regular-common-stock-dividend-13)

## USA research

The pre-reset Git revision `b6fc76e77a27efc4e8a81db0d886dbeb2eb7d1c0` contains 18 USA position-store records. The empty current store is the result of the historical S&P 500 reset. Against the archived input in isolation, P0 emitted 15 USA and 240 India rows. The original fallback tagged 174 rows as closed using a market, runner and ticker join. After requiring the entry date too and rejecting exit dates before entry, P1 read the rebuilt 255 rows and found 23 with matching exit observations. A matched legacy observation by itself does not establish a realized registry close. AXP, NKE and CSCO have archived entry prices and no matching runner rank in either the tested input or the pre-reset rank ledger. The results are historical recovery candidates. Current USA coverage and production restoration remain open. [Research recovery evidence](aegis-phase2/usa-research-recovery.json)

## Local versus GitHub stage matrix

The machine-readable inventories capture workflow order and commands, nested stage order, required inputs, declared outputs, optional flags, timeouts, and available prior evidence. Phase-two production execution remains pending for the nested stages. [India inventory](aegis-phase2/india-stage-inventory.json) and [USA inventory](aegis-phase2/usa-stage-inventory.json)

| Stage | India | USA | Phase-two evidence |
| --- | --- | --- | --- |
| Data refresh and freshness | Present | Present inside USA daily | Saved workbook audit and stage plan. Fresh combined refresh still pending. |
| R1 and V2 generation | Present | USA daily instead | Earlier ledger evidence only. |
| Artifact and ops checks | India artifact check added | USA ops check added | Pending staged execution. |
| Feature snapshot and universe gate | India nested feature producer | USA snapshot and strict selection added | Pending staged execution. |
| SSoT | Required nested producer, followed by sealed-output verification | Required nested producer, followed by sealed-output verification | Saved India verification passed on all 228 recommendations. Fresh runs pending. |
| Registry admission and dynamic exits | India-only mutation scope for local V2 | Existing materializer, risk and exit bridge wired per market | Phase-two real mutation scope still pending. |
| Run contract, self-heal | Staged commands added | Staged commands added | USA isolated lineage recovery verified. India's standalone staged contract returned exit code 0 with CERTIFIED against saved inputs. The Windows CLI now writes UTF-8 certification output. [India staged contract](aegis-phase2/india-staged-contract.txt) USA contract stopped in DATA_READY on stale feature snapshots (November 4), bars (November 17), and macro regime (November 18). A separate staged refresh returned exit code 0 for USA macro ingestion, macro intelligence, and the 516-row feature snapshot. With completed-session S&P 500 and VIX bars restored, the intermarket survey had zero critical stale or missing series. Rerunning the USA contract left full-universe price freshness as the remaining DATA_READY blocker. Fresh contracted scoring, full price-data validation, and research recovery remain pending. [Initial USA staged contract](aegis-phase2/usa-staged-contract.txt), [Staged upstream recovery](aegis-phase2/usa-staged-upstream-recovery.json), [USA staged contract after context refresh](aegis-phase2/usa-staged-contract-after-context.txt) |
| Delivery preflight, build and postflight | Staged through existing scripts | Staged through existing scripts | Saved-sheet validation returned WARN for both markets. The staged build-only sequence passed India in 783.0 seconds and blocked USA in 259.2 seconds on stale market intelligence and narrative. Full sequence pending. The standalone USA intelligence producer then returned 0 in staging and its context health check went from 17/19 to 19/19. USA daily now treats that producer as required. |
| Research P0 and P1 | Isolated archive test | Isolated archive test | Current complete dataset blocked. |
| Telegram | Separate approved handoff | Separate approved handoff | Build-only verification. |
| GitHub artifact, Git persistence and alerts | Workflow infrastructure | Workflow infrastructure | Local transaction replaces publication mechanics. |

The country orchestrators already invoke guarded SSoT. The former top-level command attempted to publish a second time and could hit the same-day snapshot refusal. It now checks the existing archive, recommendations, and GREEN health for the same as-of date. Repeat validation leaves the sealed file byte-identical. The position store is updated by the nested SSoT enricher. That path can report an update error and continue, and a same-day archive check does not prove current USA position-store coverage.

Remaining parity work includes independent verification of workflow-only fundamentals accumulators and required parity gates, actual stage inputs and mutations, and the effect of untagged shared outputs. The workflow files and schedules were left intact. The controlled build used existing recommendations and data with refresh, regeneration, and research disabled. It returned exit code 1 overall, left live workbooks untouched, and made no Telegram delivery. Its India candidate predates the final validator performance change. [Run evidence](aegis-phase2/staged-execution-evidence.json)

## Decision and historical profit-capture audit

The saved books contain 48 India and 92 USA current episodes. Exact-date bar evidence agrees with both displayed entry and current prices for 46 India and 87 USA. Audit-only bridge evidence matched 47 India and 83 USA ACTIVE decisions, all HOLD. The remaining one India and nine USA rows lack a matching decision in that artifact. The USA price substrate is stale. Where stop history, original targets, thesis, or momentum were absent or unverified, the report records them as unavailable.

ACTIVE+ is a lifecycle classification for the BUY family and is independent of percentage return. The bridge can evaluate stop, target, and horizon. Registry closes in enforce mode require an authoritative dynamic stop context. The India staged contract flagged 28 target values at or below current price. The workbook already withholds those stored values, preserving the canonical record. Workbook target fallback can display an ATR-derived level even where the bridge has no T1/T2. A historical high above today's displayed target is a comparison for investigation. It does not establish that a mandatory target was known and reached on that date. A quoted stop return is conditional on execution and is not a realized return.

Examples with same-date price agreement include one India episode above 30% with a 34.21% return and 28.48% at its quoted stop. Four India episodes fall in the 20–30% band and one of those has a stop below entry. Two USA rows exceed 30% on their saved bars, which remain stale. The bucket report supports follow-up rather than a strategy change.

The November 24 NTPC and TATAPOWER loss-avoidance rows have no entry date and do not match current position IDs. The loss-avoidance output is advisory for the research/command-center layer. The lifecycle shows an advisory/historical NTPC record and a TATAPOWER stop-breach mark. Neither establishes a missed enforceable exit of a current R2 episode. The sender now feeds loss avoidance from workbook CURRENT using exact position IDs. On the saved books it found six India and 38 USA losing rows, yielding zero EXIT verdicts in each market. USA evidence still uses stale inputs. [India CURRENT advisory check](aegis-phase2/india-current-loss-avoidance.json), [USA CURRENT advisory check](aegis-phase2/usa-current-loss-avoidance.json)

The realized history contains 149 India and 176 USA REALIZED EXIT records. Same-date bar prices agree with both displayed prices on 141 India and 35 USA realized rows. Profit-capture calculations use this narrower set and exclude intraday highs on entry and exit sessions when execution times are unknown. Original targets, stop histories, and earlier exit signals still need point-in-time reconstruction. [India decisions](aegis-phase2/india-current-decisions.csv), [USA decisions](aegis-phase2/usa-current-decisions.csv), [HOLD buckets](aegis-phase2/workbook-audit-summary.json), [India profit capture](aegis-phase2/india-realized-profit-capture.csv), [USA profit capture](aegis-phase2/usa-realized-profit-capture.csv), [NTPC and TATAPOWER evidence](aegis-phase2/india-exit-contradictions.json)

## Metric reconciliation

The India alpha mismatch was reproduced. It joined 170 current loss-attribution exits to seven winners from August 25. Alpha now uses a single exit population with the same win flags and average win-to-average loss formula as loss attribution. India therefore produces 170 exits, 25 wins, 14.7% win rate, a 1.19 mean win-to-loss ratio, and −2.27% mean exit return. The average uses all recorded rows including neutral outcomes. The USA version uses the same computation, but its saved loss report was dated September 8. The staged success condition still depends on fresh inputs.

Loss attribution walks 90-day registry CLOSED episodes with available close-to-close returns and includes structural/admin/rotation classifications. It uses a >0.5% win threshold, all included exits in the win-rate denominator, >0.5% and <−0.5% samples for its mean win-loss ratio, and separate category counts. P1 consumes P0's position-level dataset with resolved closed status and outcome returns. Its profit factor divides aggregate gains by aggregate losses, and expectancy is mean return. An earlier 33-closed P1 result is not evidence for the current dataset. The 157 NEW and 46 RE-ENTRY records count opportunity entries, with separate forward-horizon cohort outcomes.

The staged legacy India banner reproduced 457 exits, 8.1% win rate, and 329 zero-return rotation artifacts excluded by its legacy calculation path. The final workbook had 149 REALIZED EXIT records plus 26 other India rows. The differing populations explain much of the count gap. The older banner calculation and all retirement and administrative inclusion policies still need complete source-to-metric verification. [Metric reconciliation evidence](aegis-phase2/performance-metric-reconciliation.json)

## Verification

The consolidated targeted run passed 129 tests with three skipped. The final local state protection suite passed seven tests, including inherited output-root and Telegram environment isolation. The loss-attribution and loss-avoidance suite passed 16 tests. The run contract and universe coverage suite had 84 passes and one failure against live saved USA inputs. Its freshness test detected stale S&P 500, VIX, and macro regime inputs. Three isolated SSoT and USA session tests passed. The saved-workbook validator had zero FAIL findings for each market. These are isolated and artifact-level results. They do not certify fresh production runs.

## Windows runbook

```powershell
python --version
python -m pip check
python scripts/aegis_run_all.py --market both --skip-refresh --skip-regen --skip-research --stage-only
python scripts/aegis_run_all.py --market both --stage-only
python scripts/aegis_run_all.py --market both --recover-only
Get-ChildItem ..\.prism-aegis-local -Directory
```

Review the child stage summary, the run directory's `attempt.json`, `stages.json`, and any `publication.json`, plus the staged price, lineage and workbook validation reports. An interrupted publication is recovered under the same lock. Keep the backups for the most recent certified run and any open incident. A manual restore should use journal checksums and the documented earlier version. The target daily command is `python scripts/aegis_run_all.py --market both`. Use stage-only on the current unclosed production blockers. Separate live delivery remains approval-gated.

## Acceptance items still open

- Refresh USA bars and prove price-basis continuity without overwriting original entry evidence.
- Reconcile all legacy PI rows and resolve exchange-action and provider-identity cases.
- Restore current USA research through episode-keyed authoritative evidence and validate fresh P0/P1.
- Complete the stage parity matrix with real clean runs and verify shared publication scope.
- Reconstruct historical stop, target, thesis, and decision evidence for unresolved audit rows.
- Certify both markets on the same input date, verify safe repeat execution, and complete delivery preflight.

