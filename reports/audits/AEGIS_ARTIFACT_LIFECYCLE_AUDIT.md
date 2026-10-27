# AEGIS — Artifact Lifecycle Audit (Phase B)
**2026-10-27 · read-only audit · no code changed by this document**

Baseline: branch `main`, HEAD `4dbb96b9f`, `origin/main` `83c7d4d36`
(2 behind; both `aegis-bot` artifact refreshes, **0 code files**).
60 stashes and 55 untracked files preserved untouched.

Scope: `scripts/aegis_daily_v2.py` (81 steps),
`.github/workflows/aegis-daily.yml`, and the producers/validators they call.

---

## 1 · Headline numbers

| Measure | Value |
|---|---|
| Orchestrator steps | 81 |
| Distinct declared artifacts | 138 |
| **Persisted via `git add`** | **39 (28%)** |
| **No persistence mechanism at all** | **99 (72%)** |
| `actions/upload-artifact` steps in the workflow | **1** |
| REQUIRED (non-optional) steps whose outputs never persist | **16** |
| Steps declaring **no** artifacts (unverifiable by construction) | **16** |

The single CI-artifact step is `telegram-delivery-log`
(`retention-days: 30`), covering only
`reports/telegram_delivery_*.jsonl` and
`reports/telegram_command_center_*.jsonl`.

**So for 99 of 138 declared artifacts there is neither a Git commit nor a
CI artifact. They exist only inside the runner and are destroyed when the
job ends.**

---

## 2 · Live proof from today's CI run

Today's India run (`fec9554b2`, 05:34 UTC) gives a controlled comparison —
same run, same producers, differing only in whether a `git add` line exists:

| Artifact | `git add` line? | Committed by today's run? |
|---|---|---|
| `reports/feature_store_summary.json` | yes (added 2026-10-26) | **YES** |
| `reports/sized_positions.json` | no | NO |
| `reports/risk_report.json` | no | NO |
| `reports/portfolio_v3.json` | no | NO |
| `reports/portfolio_state.json` | no | NO |
| `reports/portfolio_history.parquet` | no | NO |

This is the mechanism, demonstrated rather than inferred.

---

## 3 · Critical artifact trace

### 3.1 Portfolio / risk subsystem

| Field | `reports/portfolio_history.parquet` |
|---|---|
| Scope | India (market column), authoritative state |
| Producer | `india/portfolio_engine/run.py:166-168` → `backend.persistence.append_snapshot_row` |
| Inputs | `reports/portfolio_v3.json` (its own output, re-read) |
| Exec position | orchestrator step **25** |
| Freshness rule | **none declared anywhere** |
| **Declared in `produces`?** | **NO** — staleness detection cannot see it |
| Persistence | **NONE** — not in `git add`, not in upload-artifact |
| Append semantics | append-only, **dedupes on (market, asof)** — replay replaces the row |
| Failure behavior | **FAIL-OPEN — `append_snapshot_row` never raises** (`history_writer.py:68`) |
| Consumers | `backend/history_quality/engine.py:29`, `backend/replay/controller.py:302,444`, capital-weighted accounting |
| Empty semantics | empty = no dated weights = capital weighting impossible |
| Classification | **REQUIRED / authoritative durable state** |
| Current coverage | 71 rows, asof **2026-03-02 → 2026-09-03** |

**This is the most serious defect in the pipeline.** The only source of
dated portfolio weights has no persistence mechanism, no declared freshness
rule, is invisible to staleness detection, and its writer swallows its own
failures. All four at once.

| Artifact | Producer | Step | `produces`? | Persistence | Empty valid? |
|---|---|---|---|---|---|
| `reports/sized_positions.json` | `india/risk_engine/run.py` | 24 | yes | **none** | **YES** when all recs are HOLD |
| `reports/risk_report.json` | same | 24 | yes | **none** | yes |
| `reports/portfolio_v3.json` | `india/portfolio_engine/run.py` | 25 | yes | **none** | yes (follows sizing) |
| `reports/portfolio_diff.json` | same | 25 | yes | **none** | yes |
| `reports/portfolio_state.json` | same | 25 | yes | **none** | yes |
| `reports/ai_portfolio_narrative.json` | same | 25 | yes | **none** | diagnostic |

Both producers are `optional: True`, so a hard failure does not fail the run.

### 3.2 Feature substrate

| Artifact | Producer | Step | Notes |
|---|---|---|---|
| `features/<market>/<asof>.parquet` | `india/feature_store/run.py:70` → `build_and_persist` | 10 | declared as `features/india/{asof}.parquet` — **`{asof}` now expanded** (fixed 2026-10-26); writer is **immutable**, writes `.rebuilt_HHMMSS` sibling rather than overwriting |
| `features/manifest.jsonl` | `append_manifest` | 10 | `git add` **added 2026-10-26** |
| `reports/feature_store_summary.json` | step 10 | 10 | `git add` **added 2026-10-26** — confirmed persisting today |

Selection: `list_snapshots()` globs `features/<market>/*.parquet`, skips
`.rebuilt`, returns sorted dates. Correct — the earlier "newest = 2026-07-21"
symptom was local snapshot loss, since recovered from `stash@{0}`.

### 3.3 Validation / certification

| Artifact | Producer | Step | Persistence |
|---|---|---|---|
| `reports/backend_validation{,_summary}.json` | `india/backend_validation/run.py` | **6** | `git add` yes |
| `reports/ops_check.json` | `scripts/aegis_ops_check.py` | ~45 | `git add` added 2026-10-26 |
| `reports/context/run_certification_india.txt` | `contract.runner` | workflow | `git add` added 2026-10-24 |
| `reports/context/orchestrator_verdict_india.json` | `aegis_daily_v2` main() | end | `git add` added 2026-10-26 |

### 3.4 Steps declaring no artifacts (16)

`multi_layer_stress_regime`, `multi_layer_crash_resilience`,
`multi_layer_runner_india`, `multi_layer_runner_usa`,
`multi_layer_forward_outcomes`, `aegis_r1_producer_audit`,
`aegis_3sheet_workbook`, `five_sheet_workbook_audit`,
`aegis_provenance_companion`, `aegis_overlap_classifier`,
`aegis_visual_signoff`, `aegis_determinism_hash`, and others.

These report `SUCCESS_UNVERIFIABLE` by construction: with nothing declared,
`_check_produced` cannot confirm anything was written. Note
`aegis_3sheet_workbook` is in this list — it produces the operator's
workbook.

---

## 4 · Dependency-order findings

```
step  6  backend_validation      ← validates datasets ...
step 10  feature_store
step 13  recommendation_intelligence
step 24  risk_engine             ← ... 18 steps before this producer runs
step 25  portfolio_engine
step 26  learning_engine
```

**Confirmed defect: validation precedes production.** `backend_validation`
grades `sized_positions`, `portfolio_*` and `learning_*` at step 6, while
their producers run at 24–26. Every run it therefore grades the files left
over from *before* today's run — and because of §2 those files are
permanently 2026-09-04.

That single ordering fact, combined with non-persistence, fully explains the
"35 datasets 28–43 days past a 1-day SLA" finding and the `ops_check`
CRITICAL verdict.

**It does not follow that all validation should move late.** `backend_validation`
also covers source data (`price_bars`, fundamentals, macro) that *must* be
checked before scoring. The correct repair is to **separate pre-flight
source validation from post-production artifact verification**, not to
relocate the existing step.

---

## 5 · Failure-propagation findings

| Question | Finding |
|---|---|
| Does a non-zero producer exit stop the run? | Only if `optional: False` **and** the orchestrator gate judges it. `risk_engine` and `portfolio_engine` are `optional: True`. |
| Can a green run contain a failed required producer? | **No longer** — the orchestrator gate (2026-10-24) fails on critical steps; non-refresh promoted to critical 2026-10-26. |
| Is an absent output detected? | Only if declared in `produces`. `portfolio_history.parquet` is not. |
| Does a malformed parquet/JSON fail the run? | **No** — `append_snapshot_row` is fail-open; `_artifact_asof` swallows exceptions. |
| Can downstream consume yesterday's artifact after today's producer fails? | **Yes** — artifacts are tracked, so a failure leaves the last committed copy in place looking plausible. |
| Are skipped steps recorded? | Yes — `SKIPPED_OPTIONAL` / `SUCCESS_CACHED` in the verdict. |
| Is a zero-row output distinguishable from a failure? | **NO** — this is the gap §6 addresses. |

**Today's concrete case:** `risk_engine` exits 0 with `sized: 0 active`
because all 228 recommendations are `HOLD`. That is **correct behaviour**.
The pipeline currently cannot distinguish it from a sizing failure, a stale
input, or a malformed recommendation file.

---

## 6 · Persistence policy (proposed)

| Cat | Definition | Artifacts | Mechanism | Retention |
|---|---|---|---|---|
| **A** | Source / config | code, `configs/*.yaml` | reviewed Git change | permanent |
| **B** | Reproducible run outputs | `sized_positions`, `risk_report`, `portfolio_v3`, `portfolio_diff`, `portfolio_state`, `ai_*_narrative` | **CI artifact** w/ run id + SHA + market | 30–90d |
| **C** | **Authoritative durable state** | **`portfolio_history.parquet`**, `features/manifest.jsonl`, `*_history.parquet` | **Git** (already tracked, small, dedupes on (market,asof)) | permanent |
| **D** | Research evidence | `reports/research/r3/**`, sealed `history/**` | Git, never auto-promoted | permanent |
| **E** | Ephemeral diagnostics | narratives, `*_decision_impact` | CI artifact, best-effort | 7–30d |

Rationale for `portfolio_history.parquet` in **C, not B**: a 30-day CI
artifact cannot hold a multi-month weight history, and capital-weighted
return requires the full series. It is **already tracked** in Git (last
committed 2026-09-04) and dedupes by (market, asof), so committing it is
both the existing convention and safe against duplication.

**Explicitly rejected:** reflexively adding all 99 unpersisted artifacts to
`git add`. That would commit large binaries and narrative JSON on every run
with no review value, and risks publishing files never audited for
sensitivity.

---

## 7 · Confirmed defects (ranked)

1. **`portfolio_history.parquet` has no persistence, no declared producer
   output, no freshness rule, and a fail-open writer.** Blocks all
   capital-weighted accounting.
2. **99 of 138 declared artifacts have no persistence mechanism.**
3. **`backend_validation` runs 18 steps before the producers it grades.**
4. **No VALID_EMPTY contract** — a legitimately empty portfolio is
   indistinguishable from a failure.
5. **16 steps declare no artifacts**, including the workbook producer, so
   they are permanently unverifiable.
6. **`append_snapshot_row` returns `None` on failure and the caller ignores
   it** (`portfolio_engine/run.py:167`).

## 8 · Rejected hypotheses

- *The portfolio/risk engines are dead.* **REJECTED** — both exit 0 and
  compute correctly on current inputs.
- *Producers stopped running.* **REJECTED** — they run daily; their output
  is discarded.
- *`list_snapshots` is buggy.* **REJECTED** — correct; the symptom was local
  snapshot loss, recovered from `stash@{0}` and validated.
- *Zero sized positions indicates failure.* **REJECTED** — all 228
  recommendations are `HOLD`; zero is correct.
