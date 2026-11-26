# AEGIS local stabilization

This is the phase-one record. [Phase 2 production closure](AEGIS_LOCAL_STABILIZATION_PHASE_2.md) describes the current staging and recovery controls, additional audit evidence, and open certification blockers.

## Status on 2026-11-24

India and USA remain uncertified for local production. The first pass fixes failure propagation and local delivery controls. The sender still writes workbooks and derived state before completing all validation. The one-time snapshot below provides a recovery source for the captured files. Automatic rollback, crash recovery, single-writer enforcement, and atomic promotion of certified outputs remain open.

## Local execution and verification

| Stage | India | USA | Evidence and remaining work |
| --- | --- | --- | --- |
| Standalone bar refresh and freshness | Unverified | N/A | India now runs the CI freshness script before regeneration. USA refresh remains inside USA daily. |
| Recommendation generation | Unverified | Unverified | India runs R1 followed by V2. The saved V2 report has 81 steps, 55 successes, seven optional failures, no critical failures, and an ops-check finding. The old V2 exit code counted optional failures as fatal locally. The local caller now requests the workflow's required-step semantics. Injected optional failure, required timeout, and required no-refresh cases passed. The saved report alone does not identify the earlier 1,812.7-second run. USA daily has its own child-stage result handling. |
| SSoT enrichment | Unverified | Unverified | Executes only after successful regeneration for the same market. |
| Local workbook build and validation | Blocked by saved integrity findings | Blocked by saved integrity findings | Saved India report has PI1 and PI5 failures. Saved USA report has PI1, PI2, and PI5 failures. A fresh verdict requires a controlled run. |
| Workflow contract and artifact verification | Pending parity audit | Pending parity audit | GitHub runs additional steps described below. |
| Research P0 and P1 | Partial data verified in isolation | Blocked | The USA position store declares 18 positions and contains an empty positions map. The P0 CLI blocks publishing a one-market result, and P1 is blocked when P0 fails. |
| Live Telegram | N/A in local default | N/A in local default | Explicit opt-in. No messages sent during this pass. |

Failure injection with mocked child commands verified that an India V2 failure blocks India SSoT and workbook generation while USA continues. The inverse USA failure leaves India running. A P0 failure blocks P1. All three scenarios returned 1. Targeted A23, lineage, and portfolio-reconciliation tests returned 63 passed and 3 skipped in 54.79 seconds after the A23 reader change. Python 3.12.10 is installed. `pip check` found no broken requirements and warned about an invalid `~orch` distribution.

The isolated P0 builder streamed the existing workbook and generated 240 India outcomes in 17.55 seconds. P1 consumed those exact temporary outputs in 0.64 seconds (160 closed and 80 open). This test did not produce USA coverage. Git commit cc864bfb3 explicitly cleared the USA position store during the S&P 500 reset. Restore or rebuild only after reconciling the authorized reset, episode registry, and current research contract. Outputs from the isolated test were kept outside the repository.

## Historical reconciliation baseline

Latest registry state by market and opportunity ID:

| Market | HEAD active | HEAD closed | Local active | Local closed | HEAD IDs missing locally | Active-to-closed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| India | 68 | 191 | 63 | 203 | 0 | 12 |
| USA | 234 | 599 | 100 | 738 | 0 | 139 |

The shared append ledger is `reports/research/opportunity_registry.jsonl`. Deduplication uses market plus opportunity ID and keeps the latest ledger row. `HEAD` and the local `origin/main` reference have no divergent commits. The actual remote was not queried. This comparison does not establish that the closures were legitimate, that entry prices remained immutable, or that every episode appears in the correct portfolio or historical output. The registry includes multiple runners and is not the publication population. Current workbook sheet names are `CURRENT` and `EXIT HISTORY` for both markets. Existing canonical portfolio JSONs have 49 India and 162 USA investment active records. They require episode-level reconciliation against workbook rows, including row types and explicit exclusions.

A23 has existing episode-aware code and regression tests. Its Exit History ID scan now streams rows in one pass rather than repeatedly reparsing the workbook. The self-heal script also still has a ticker-based comparison before its separate episode check. The saved preflight reports are dated November 7 and contain no blockers at that time. The India report records 11 durable lineage entries. The November 24 read-only A23 run accounted for 167 India closures (149 represented, 18 in lineage) with zero unaccounted. USA had 657 accountable closures (639 represented and 18 unaccounted). All 18 closed between August 14 and August 21, outside the November 24 workbook retention window. On a separate copy of the USA registry, workbook, and lineage, the existing reconciler recorded the 18 episodes and reduced the unaccounted count to zero. Running it again recorded zero new entries and left zero unaccounted. The sender now runs that same reconciliation before its final A23 and delivery gates. This verification did not change the live lineage files. USA feature-store freshness remains unverified.

[Episode reconciliation CSV](AEGIS_LOCAL_EPISODE_RECONCILIATION.csv) records 1,104 market and opportunity-ID comparisons, including the 18 USA A23 gaps. Among registry-active IDs, 48 India and 92 USA matched CURRENT exactly. Another 15 India and eight USA IDs require exclusion review. The saved canonical portfolio projections contain no episode IDs, so they cannot resolve those cases by exact ID without additional source joins.

## Defects and changes

| Defect | Evidence | Primary fix | Remaining |
| --- | --- | --- | --- |
| Local stages ran against failed upstream outputs | Previous parent recorded failures and continued into SSoT, workbook rebuild, and send | `scripts/aegis_run_all.py` now gates stages by market, distinguishes blocked stages, runs India freshness, and uses the parent Python interpreter and repo import path | Inventory and validate nested stages and workflow parity |
| P0 import failed | Python gives the package directory precedence over the same-named module | Renamed the combined builder to `backend/research/canonical_outcome_dataset.py`, kept the per-market research package, updated the CLI import, streamed the workbook in one pass, and added a market-coverage check before publication | Recover the USA research position source and validate the full pipeline input provenance |
| Price-integrity failure reached delivery | Delivery gate used an empty set of blocking price checks | `backend/delivery/delivery_gate.py` and the sender enforce PI1, PI2, PI5, and block when a price, validation, or gate check raises | Reconcile adjusted prices, exit prices, and dates using source evidence |
| Sender reported success for incomplete outputs | Stale recommendations and zero rows previously returned success. Canonical rebuild errors were swallowed | `scripts/telegram_command_center_send.py` returns failure for those paths and keeps build-only out of send heartbeat and Sheets sync | Stage workbook writes before validation and publish only after success |
| Stale or missing active bars | India PI5 lists LTIM, TATAMOTORS, PEL, and GUJGASLTD | No data changes in this pass. Existing aliases already map MM to M&M in the India refresh path | Verify provider call sites and exchange identity continuity for each affected symbol |

The saved India price report checked 2,023 positions with 369 unexplained entry-price differences and 854 explained by corporate actions. The saved USA report lists 690 unexplained entry differences, 320 exit-price differences, and 11 stale or missing tickers. Treat these as report findings pending reproduction against the final sheets and authoritative episode inputs.

## GitHub and local execution

The production workflows are `.github/workflows/aegis-daily.yml` and `.github/workflows/aegis-usa.yml`. In addition to market engines and sender work, they run lifecycle self-heal, the run contract, delivery preflight and postflight, and workflow-specific checks. India includes an orchestrator critical-step gate, artifact verification, and history persistence. USA includes feature snapshot and universe selection gates, ops checks, and a second self-heal pass. Both include workflow-only persistence and delivery reporting. The canonical local command now exercises the sender's per-market workbook build and validations but does not yet reproduce every independent gate or state transition in those workflows.

## Snapshot and operating commands

The verified pre-run snapshot is beside the repo under `prism-stabilization\20261124T092551Z-8beab507\snapshot`. The sibling manifest records SHA-256 for 136 files, including workbook copies, registry and position-store data, and delivery lineage. This captures current workspace state with unverified certification. No Git push, pull, commit, historical data correction, or Telegram delivery was performed.

```powershell
python --version
python -m pip check
python scripts/aegis_run_all.py --help
python scripts/aegis_run_all.py --market both
python scripts/aegis_run_all.py --market india
python scripts/aegis_run_all.py --market usa
python scripts/aegis_run_all.py --market both --preview-only
```

The USA recovery evidence is in \`lineage-test/reconcile-evidence.json\` under the snapshot run directory.

Run the production commands only in a controlled workspace until atomic promotion and recovery are verified. The trailing table shows PASS, FAIL, or BLOCKED for requested local stages. Check `$LASTEXITCODE` immediately after a run. Review `reports/context/orchestrator_verdict_india.json`, `reports/context/price_integrity_<market>.json`, and `reports/context/xlsx_validation_<market>.json` for detailed failures. For recovery, compare a snapshot copy to the affected file and verify its hash against the manifest before any restore. Reconcile the ledger and both markets first because the registry is shared. Live Telegram requires explicit approval and the `--send` flag.

## Remaining acceptance work

- [ ] Build the full nested-stage inventory and environment readiness check.
- [ ] Reconcile every affected episode across registry, canonical portfolio, workbook, exit history, and durable lineage.
- [ ] Reproduce the India V2 and SSoT errors and verify USA feature freshness.
- [ ] Resolve PI1, PI2, and PI5 with authoritative data and preserve immutable entry evidence.
- [ ] Close local versus workflow gate differences.
- [ ] Implement transactional publication, single-writer protection, and recovery.
- [ ] Run both markets stage by stage in an isolated workspace and verify the full run twice for the same data date.

