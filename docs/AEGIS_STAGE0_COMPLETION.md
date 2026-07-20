# AEGIS Stage 0.5 · Completion Report
**Runtime execution audit · 2026-07-20 · Evidence-backed**
**Stage 0 prerequisite for PRD (Stage 1) work**

---

## Critical findings (surfaced by this audit, not the file-based discovery)

These findings materially change what the PRD (Stage 1) must address.
Every one is backed by file + line evidence in the drilldowns.

### FINDING 1 · The "daily" pipeline runs on stale training data
- `reports/learning.parquet` (the 1060-trade corpus) is a **hard `requires:` dependency** of 4 steps in `scripts/aegis_daily_v2.py` — `adaptive_rec_v2` (line 58), `stock_validation` (104), `winner_genome` (135), `benchmark` (149).
- Its producer, `research/adaptive_learning/run.py`, was **run exactly once** — commit `59b2b31`, 2026-07-17 17:06:23.
- The daily pipeline has fired successfully on 2026-07-18, 07-19, and 07-20 against **the same frozen corpus** for 3+ days.
- No caller of `research/adaptive_learning/run.py` exists anywhere in the repo.

### FINDING 2 · All 4 intelligence tiers frozen but silently rendered as live
- `research/{global,sector,industry,company}_intelligence/` engines each ran exactly once (2026-07-17 sprint), never invoked since.
- BUT the SPA (`ux/dashboard/frontend/index.html`) **actively fetches and renders** `global_context.json`, `champion_strategy.json`, `challenger_scoreboard.json`, `confidence_calibration.json`, `strategy_doctor.json` — all frozen.
- `scripts/aegis_ops_check.py` only validates **existence + JSON-parseability**, never recency. Staleness produces NO HEALTHY/DEGRADED/CRITICAL signal.
- **Operator is seeing 3-day-stale intelligence tiles alongside live tiles, with no indication which is which.**

### FINDING 3 · News + fundamentals + FII/DII ingestion is completely unscheduled
- `india/news_sentiment.py`, `india/fii_dii.py` — only caller is `india/daily_run.py`.
- `india/daily_run.py` — only caller is `run_daily.bat`.
- `run_daily.bat` — declares itself explicitly non-primary ("PRIMARY SCHEDULER = GitHub Actions … This .bat is for local manual runs / laptop-only debugging"), grep across every `.yml/.yaml/.service/.timer/.ps1/.plist` returns zero references to it.
- `india/fundamentals_nse.py` — zero callers anywhere. Only invocation is the CLI usage comment in the file itself.
- **Conclusion:** the data ingestion pipelines that would give AEGIS non-technical signal ARE all coded, tested, and produce parquet outputs — but only when a human types `run_daily.bat`. They are not on any scheduler.

### FINDING 4 · Nexaquant daemon has never actually run
- Full daemon code exists at `nexaquant/ops/daemon.py` with signal handlers, PID lock, Scheduler, notify framework across 14 channels.
- Install templates at `deploy/{systemd,launchd,task-scheduler}/` reference `/opt/nexaquant` and `C:\opt\nexaquant`.
- Runtime state files (`reports/ops_daemon.lock`, `ops_run_state.json`, `ops_schedule_state.json`) **do not exist**.
- Unit-tested weekly by `eng001-regression.yml` — that's the only exercise the code gets.

### FINDING 5 · HMM regime detection is REJECTED-BY-DESIGN, not accidentally dormant
- Prior discovery flagged `india/regime_hmm.py` as an existing capability.
- `docs/ARJUNA_ALPHA_MASTER.md:48` explicitly: **"HMM was tested and LOST (1.06 vs 1.64) → rejected."**
- `india/config.py:56` defaults `regime = "global"`. `india/recommendation_generator.py:44` sets `regime="global"` in the live CONFIG.
- The live production regime engine is `india/confidence_engine.current_regime()` — simple 200-DMA + VIX + Global-Risk gate, not HMM.
- **The dormancy is a deliberate research finding, not an oversight to fix.**

### FINDING 6 · AI/ML models are ALSO frozen by policy
- `docs/ARJUNA_V4_ROADMAP.md`: `MODELS_FROZEN_UNTIL_DATA_ARRIVES = True` set as policy in `india/config.py`.
- Rationale: 7 price-only features on 300 holdings had AUC 0.47 (no skill). ML unfreezes only when point-in-time fundamentals + news archive + analyst revisions + alt data are populated.
- `india/ai_reopen.py` is the live trigger-status check.
- **PRD must respect this policy — reactivating ML requires the data-arrival milestones described in the roadmap.**

### FINDING 7 · ARCH017 / 017A / 018 documentation is out of sync with code
- All three docs self-declare **"Status: DRAFT · design only · NO code · NO production changes"** (each at line ~6, dated 2026-07-17).
- Yet `research/global_intelligence/` and `research/sector_intelligence/` have full code trees + committed JSON outputs from the SAME DAY.
- **Docs must be treated as aspirational until reconciled with code.**

### FINDING 8 · India ↔ USA parity refined
Corrected from earlier "30-40%" estimate to specific gaps:
- USA **has** full parity on orchestration shape (13-step pipeline mirroring India v2) + always-on core (recommendations → validation → risk → fusion → IM → WG → DA → benchmark → morning_report → ops_check → telegram).
- USA has **ZERO** for: MON001 forward validation, champion/challenger, confidence calibration, portfolio construction / monitor, news ingestion, FII/DII ingestion, 4-tier hierarchy.
- USA's own `usa/research/fundamentals/run.py` exists but is **NOT wired into `usa/scripts/usa_daily.py`** (zero grep matches for "fundamentals" in the orchestrator).

### FINDING 9 · `dashboard_config.json` is orphaned
- Zero consumers in `ux/dashboard/frontend/serve.py` or `index.html`.
- SPA layout is hardcoded in `index.html`.
- The file is produced by `ux/dashboard/publish/bundle.py` and never read by anything at runtime.

### FINDING 10 · Two distinct `research/recommendations/` modules exist and must not be conflated
- India root: `research/recommendations/run.py` — zero callers, deprecated.
- USA: `usa/research/recommendations/run.py` — actively wired into `usa/scripts/usa_daily.py:63`, runs daily.

---

## The 12 Stage 0.5 deliverables

| # | Document | Purpose |
|---|---|---|
| 1 | [AEGIS_EXECUTION_FLOW.md](AEGIS_EXECUTION_FLOW.md) | Every scheduled + manual execution path with evidence |
| 2 | [AEGIS_DEPENDENCY_GRAPH.md](AEGIS_DEPENDENCY_GRAPH.md) | Which modules call which |
| 3 | [AEGIS_REPORT_LINEAGE.md](AEGIS_REPORT_LINEAGE.md) | Producer → consumer for every fresh `reports/*.json` |
| 4 | [AEGIS_DATA_LINEAGE.md](AEGIS_DATA_LINEAGE.md) | Where raw data comes from and how it flows |
| 5 | [AEGIS_RUNTIME_DISCOVERY.md](AEGIS_RUNTIME_DISCOVERY.md) | Intelligence + recommendation lineage (top-down) |
| 6 | [AEGIS_MODULE_REGISTRY.md](AEGIS_MODULE_REGISTRY.md) | Every module classified with runtime status |
| 7 | [AEGIS_CONFIGURATION_REGISTRY.md](AEGIS_CONFIGURATION_REGISTRY.md) | Every config file and its role |
| 8 | [AEGIS_DOCUMENT_REGISTRY.md](AEGIS_DOCUMENT_REGISTRY.md) | Every doc read, summarized |
| 9 | [AEGIS_AI_LAB_DISCOVERY.md](AEGIS_AI_LAB_DISCOVERY.md) | LAB001-010 status |
| 10 | [AEGIS_PRODUCTION_VS_RESEARCH.md](AEGIS_PRODUCTION_VS_RESEARCH.md) | Runtime-verified production/research split |
| 11 | [AEGIS_INDIA_USA_RUNTIME_COMPARISON.md](AEGIS_INDIA_USA_RUNTIME_COMPARISON.md) | Cell-by-cell India ↔ USA runtime parity |
| 12 | This file (`AEGIS_STAGE0_COMPLETION.md`) | Master summary + critical findings + Stage-1 prerequisites |

---

## Prerequisites for Stage 1 (PRD) work

The PRD may proceed once the operator has read and approved the 10 critical findings above. Specifically:

1. **Finding 1** must inform the PRD's data-freshness requirements. A production platform training against 3-day-stale corpora is not one — the PRD needs an explicit "who rebuilds learning.parquet and how often" answer.
2. **Finding 2** must inform the PRD's observability requirements. Rendering stale data as fresh is a trust failure. The PRD needs freshness SLAs per artifact and an ops-check that enforces them.
3. **Finding 3** must inform the PRD's data-ingestion policy. The PRD must decide whether fundamentals/news/FII-DII belong in the daily orchestrator or remain manual.
4. **Finding 5** and **Finding 6** must inform the PRD's ML/regime philosophy. Both HMM and ML are frozen by evidence; the PRD must not resurrect either without addressing the underlying evidence.
5. **Finding 7** must inform the PRD's documentation policy — the ARCH-* docs need reconciliation.
6. **Finding 8** must inform the PRD's parity target — every USA-side gap listed there is either a scope item or an accepted difference.

---

## What Stage 0.5 did NOT determine

Explicit gaps this audit could not close from static analysis alone:

- Whether `deploy/aegis-windows-task.ps1` is actually registered on the operator's local Windows machine (would require `Get-ScheduledTask` output).
- Whether the operator manually runs `run_daily.bat` on any cadence.
- What the operator's actual daily workflow is (audit inspected files, not human process).
- Whether `data/raw/india/fundamentals.parquet` / `news_sentiment.parquet` / `fii_dii.parquet` on disk are current (mtimes not checked — a future audit item).
- Contents of `.env.telegram` / `.env.angel` — deliberately not inspected per read-only discipline.

These become questions the operator must answer before Stage 1.

---

## Rules re-affirmed

- **No code changes** until Stages 0–8 are approved.
- Every architectural claim traces to a citation in one of the 12 deliverables.
- No "parity" statement without evidence in `AEGIS_INDIA_USA_RUNTIME_COMPARISON.md`.
- Contradictions with the earlier `AEGIS_REPO_DISCOVERY_v1.md` are logged (see §11 of the runtime audit and the individual drilldowns).

---

_End of Stage 0.5 completion report. Ready for operator review._
