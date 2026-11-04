# PROPOSED CHANGE · feature-snapshot persistence and the dangling manifest

**Status:** proposed, NOT implemented. Filed 2026-11-04 at the CEO's
instruction to keep workflow changes out of the current promotion.

**Scope:** two workflow-level defects found while validating the
snapshot-authority contract. Neither is a code bug; both are gaps in
what CI keeps.

---

## Defect 1 · the manifest references files that were never committed

`features/manifest.jsonl` is committed — [aegis-daily.yml:486](../../.github/workflows/aegis-daily.yml)
carries `git add features/manifest.jsonl`. It is an append-only ledger
and now holds 306+ entries, each with a `path` field naming the snapshot
it describes.

The snapshots themselves stopped being committed after **2026-07-21**:

| market | tracked canonical files | newest tracked |
| --- | --- | --- |
| india | 95 | 2026-07-21 |
| usa | 139 | 2026-07-21 |

Locally there are 244 canonical files. So for every date since
2026-07-22 the manifest asserts the existence of a snapshot that is not
in the repository. Anyone reading the ledger — a replay, an audit, a new
clone — sees a complete record and finds nothing behind it.

This is the produce-then-discard pattern: the evidence is generated
every run and committed by nothing.

### Why not simply commit the snapshots

Three reasons, and they argue for fixing the ledger rather than the
payload:

1. They are rebuildable. USA builds via
   `scripts/ci_build_feature_snapshot.py --market usa`
   ([aegis-usa.yml:205](../../.github/workflows/aegis-usa.yml)); India
   via `india/feature_store/run.py` inside the orchestrator. CI does not
   read a committed snapshot — it makes its own.
2. Volume. ~108 KB (India) and ~194 KB (USA) per day, every weekday,
   forever, in a repository that already carries 927 changed artifact
   files per CI commit.
3. Under the new snapshot-authority contract a committed canonical file
   **wins** over a fresh rebuild. That is correct for an operator
   promotion and wrong as an accident: a stale committed snapshot would
   silently outrank the day's own build. Today no tracked snapshot
   exists for any October or November date, so the risk is latent, not
   live — but committing the daily population would create it.

### Proposed fix

Record the snapshot's fate in the manifest entry rather than implying
persistence. Add to each `append_manifest` record:

```
"persisted":  "artifact" | "git" | "runner-local"
"sha256":     "<hash of the file as written>"
```

A reader can then tell a snapshot that is retrievable from one that
existed only on a runner for six minutes. This is a change to
`backend/feature_store/feature_snapshot.py` and
`backend/feature_store/feature_history.py`, plus a test asserting that
no manifest entry claims `git` unless the path is tracked.

---

## Defect 2 · the day's substrate is not retrievable after the run

Neither workflow uploads the feature snapshot. The `upload-artifact`
steps cover the morning report
([aegis-usa.yml:283](../../.github/workflows/aegis-usa.yml)) and a
failing-XLSX diagnostic ([:303](../../.github/workflows/aegis-usa.yml)),
and nothing else.

The consequence: when a run produces a questionable recommendation there
is no way to inspect the features it was scored from. The snapshot is
built, read by scoring, and discarded with the runner. Every diagnosis
of a past day therefore has to *rebuild* the substrate and hope the
inputs have not moved — and they do move. The raw price parquets are
appended daily, so a rebuild on 2026-11-04 of the 2026-11-03 snapshot is
not the snapshot that ran. That was measured during this promotion: the
2026-11-03 canonical built pre-merge contained no 2026-11-03 bar at all,
because the bar arrived with a later CI commit.

### Proposed fix

Add one step to each workflow, after the snapshot build and before the
gates:

```yaml
      - name: Upload feature snapshot + quality report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: feature-substrate-<market>-${{ github.run_id }}
          path: |
            features/<market>/*.parquet
            reports/context/feature_quality_<market>_*.json
            reports/context/macro_feature_quality_<market>.json
          retention-days: 30
```

Cost: zero git growth, one upload of ~200–400 KB per run. Benefit: any
run's substrate is downloadable for 30 days, which is the window in
which questions actually get asked.

`retention-days: 30` matches the existing morning-report upload, so no
retention policy changes — the CEO excluded that from this release.

---

## What is NOT proposed

- Committing the 244 daily snapshots, or any part of them.
- Committing the 403 untracked working-tree files.
- Changing retention on any existing upload.
- Changing the snapshot-authority contract, which is already landed and
  tested.

## Acceptance criteria, if approved

1. A manifest entry names its persistence mode and the hash of what was
   written.
2. A test fails if an entry claims `git` for an untracked path.
3. Both workflows upload the snapshot and both quality reports.
4. A completed run's artifact can be downloaded and its snapshot hash
   matched against the manifest entry for that date.
5. No snapshot is added to git by either workflow.
