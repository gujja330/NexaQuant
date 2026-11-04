# Release record · 2026-11-04

**Remote SHA:** `bfa1b22c40edd14e2e7e93f29277d085732f0f24`
**Range pushed:** `be3bde693..bfa1b22c4` (32 commits, 107 files)
**Merge:** true merge of `origin/main` into `main` at `efa82f014` — no
rebase, no reset, no force-push, no history rewritten.

---

## What shipped

| change | commit |
| --- | --- |
| Snapshot authority: canonical is the served snapshot | `3d0a832cc` |
| Bar window: cutoff before window, 260 bars, `sma_200` reachable | `80b8e7b1f` |
| Feature granularity (81/81) + semantic quality checker | `08b6c5d7e` |
| 52-week range uses 252 bars or abstains | `3afb2e5a3` |
| Feature-quality reports + persistence proposal | `0c3fe0976` |
| Revert of a masking artifact (see below) | `bfa1b22c4` |

## Regression gate

```
python -m pytest tests/pipeline/ backend/tests/ tests/standards/ -q -rs
HEAD efa82f014 · start 2026-11-04T05:24:23Z
1514 passed · 2 failed · 0 skipped · 2 warnings · 1139.71s (18:59)
```

Two failures, both established baseline and both independently
reproduced on a targeted rerun (143 passed, same 2 failed):

- `test_snapshot_for_recs_asof_exists` — the USA recommendation-history
  archive is absent locally. The writer fix shipped earlier at
  `4b87a0165`; producing the file needs a USA pipeline run.
- `test_no_hardcoded_dates_in_production_code` — 13 violations across 8
  files, none of which this release touches.

---

## The seven macro Parquet files — why they are in this release

`data/raw/india/global/{DXY,GOLD,OIL,SPX,US10Y,USDINR,USVIX}.parquet`

They are **intentional release contents** and they were **misattributed
to commit `3afb2e5a3`**. Both statements are true and the distinction
matters to a reviewer reading the history.

### How they got into the wrong commit

`git checkout stash@{0} -- <path>` updates the worktree **and stages the
result**. It was used to restore files that an earlier `git stash push`
had displaced; they were still in the index when the 52-week commit was
made, so that commit carries eight files beyond the two it names.

### Why they belong in the release anyway

| | last observation | `macro_dxy` |
| --- | --- | --- |
| previously committed | 2026-10-23 | 101.81 |
| shipped in this release | **2026-11-03** | **101.728** |

`backend/feature_store/macro_series.py` declares `max_age_days = 5` for
every macro series. Against observations ending 2026-10-23, an asof of
2026-11-03 is **11 days** stale, so every macro feature exceeds its
budget and correctly abstains. Measured on the stale copies: macro
coverage **0.0 of 8** in both markets, and the India snapshot verdict
dropped to WARNING.

So without these files the macro correction delivered in Phase 1 holds
on one developer machine and nowhere else. Shipping them is what makes
it hold in CI.

### The gap they do not close

Nothing in either workflow refreshes `data/raw/india/global/`. The
freshness of these files depends on someone running
`india/global_risk.py --fetch` locally and committing the result. That
is a scheduled-producer gap, filed separately, not fixed here.

## The eighth file, which was deliberately kept out

`reports/recommendation_lifecycle.json` was displaced and restored the
same way, but was reverted to origin's copy before the push.

Two producers write that one path with incompatible schemas:

| producer | keys | date field |
| --- | --- | --- |
| committed | `schema_version`, `records`, `by_ticker` | `asof` = 2026-07-29 |
| daily | `engine`, `run_utc`, `by_state`, `win_rate` | **no `asof`** |

`test_india_upstream_dates_are_consistent_with_recommendations` reads
`asof` and treats an unparseable one as a warning rather than an error.
So the daily writer removing that key is what has kept the check green
over an artifact that is 97 days stale. Pushing the no-`asof` version
would have propagated that masking to the remote and hidden a real
staleness defect from every future run.

The file is therefore byte-identical to what was already on origin. The
schema collision remains open.

---

## Deployment

| run | workflow | conclusion |
| --- | --- | --- |
| `41782641152` | AEGIS CI | **success** |
| `41782641136` | AEGIS Daily (India) | see below |
| `41782641276` | ENG001 Regression | failure — **pre-existing** |

ENG001 has failed on all 12 most recent runs, back to 2026-10-24, at the
same step (`Full regression + invariance guards`), across unrelated
SHAs and both `push` and `schedule` events. Verified on `8286c5d37`
(2026-11-01) and `cd57a4f4d` (2026-10-30), both predating this work.

`aegis-usa.yml` is schedule-only (11:17 / 16:43 UTC) and was **not**
triggered by this push.

## What CI does NOT consume

**No `features/` file was pushed.** Verified: zero `features/` paths in
`be3bde693..bfa1b22c4`, and no 2026-11-03 or 2026-11-04 snapshot exists
in the remote tree. `features/manifest.jsonl` stays at 300 lines on the
remote against a dirty local 306.

Consequence: the promoted canonical snapshots
(India `51fe7dca7caa3692…`, USA `c63bdee55f1ee952…`) are **local
evidence only**. CI builds its own snapshot for its own asof each run.
That is the intended arrangement — see
`PROPOSED_CHANGE_snapshot_persistence.md` for why committing the daily
population would be worse, not better — but it means local promotion is
not deployment of those bytes.

## Open defects, reported and deliberately unfixed

1. Nothing refreshes `data/raw/india/global/` in CI.
2. `reports/recommendation_lifecycle.json` — two producers, one path,
   incompatible schemas; a staleness check passes only by accident.
3. The test suite writes into the live `features/` tree —
   `backend/tests/test_sprint25.py:106` calls
   `build_and_persist(_ROOT, ...)` and `:151` runs
   `india/feature_store/run.py` with `cwd=_ROOT`. On 2026-11-04 that
   produced 6 India and 12 USA snapshot files and appended 6 entries to
   the tracked manifest. None of it shipped; none of it was deleted.
