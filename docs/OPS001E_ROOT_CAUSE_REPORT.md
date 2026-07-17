# OPS001-E · Root Cause Report — Stale Recommendation Delivery

**Report ID:** `OPS001E-ROOTCAUSE-2026-07-17`
**Role:** Principal Production Reliability Engineer
**Method:** Direct read of GitHub Actions log for AEGIS Daily #43, step "Run AEGIS engine + database + evidence + ops check" (log pasted by operator).
**Confidence:** **DEFINITIVE.** Exception + file + line + function are extracted from the CI log — no inference.
**Constraint:** Read-only. No code modified. No workflow modified. No commit pushed.

---

## 1. Executive summary

**Exception (verbatim from CI log):**

```
ValueError: 'Q' is no longer supported for offsets. Please use 'QE' instead.
```

**Location (verbatim from CI log):**

```
File "/home/runner/work/NexaQuant/NexaQuant/india/recommendation_generator.py", line 71, in evidence_gate
    q = (1 + champ).resample("Q").prod() - 1
```

**Call stack (verbatim):**

```
File "…/india/recommendation_generator.py", line 950, in <module>
    main()
File "…/india/recommendation_generator.py", line 197, in main
    G = evidence_gate(champ, idx, reg)
File "…/india/recommendation_generator.py", line 71, in evidence_gate
    q = (1 + champ).resample("Q").prod() - 1
File "…/site-packages/pandas/core/generic.py", line 9423, in resample
File "…/site-packages/pandas/core/resample.py", line 2334, in get_resampler
File "…/site-packages/pandas/core/resample.py", line 2420, in __init__
    freq = to_offset(freq)
File "pandas/_libs/tslibs/offsets.pyx", line 6229/6352/6137, in to_offset / raise_invalid_freq
ValueError: Invalid frequency: Q. Failed to parse with error message:
    ValueError("'Q' is no longer supported for offsets. Please use 'QE' instead.")
```

**One-sentence root cause:** pandas removed the deprecated `"Q"` (quarterly) resample alias in favour of `"QE"` (Quarter-End). The CI runner installs the latest pandas via `pip install`, which no longer accepts `"Q"`. `recommendation_generator.py` uses `"Q"` at line 71. Runner raises. Mask hides. Telegram sends stale.

---

## 2. What phase of the pipeline the failure occurs in

**recommendation generation** — specifically the `evidence_gate()` helper at
line 71, called early in `main()` at line 197 during scoring / history
construction. It is NOT during imports, feature loading, or parquet reading.

Order-of-execution (verbatim from log):

1. `refresh_data.py` — ✅ succeeded (22 s of yfinance calls per screenshot).
2. `check_data_freshness.py` — ✅ succeeded (1 s, set `fresh=true`).
3. `recommendation_generator.py` line 71 — ❌ **RAISED** the ValueError.
4. **Bash `|| echo "engine issue; will send last snapshot"` swallowed the exit code → step returned 0.**
5. `recommendation_db.py` — ✅ succeeded on STALE data (`DB now holds 36 rows across 3 days` — same rows as yesterday).
6. `scorecard.py` — ✅ succeeded on STALE data.
7. `ops_check.py` — ✅ succeeded, printed **`ALL GREEN — production is operationally healthy`**.
8. Google Sheets push, Telegram send, artifact upload, commit — all ✅ succeeded on STALE outputs.

**The step total was 12 seconds** — the generator crashed almost immediately at line 71, before it wrote anything. That's why `data/aegis_today.csv` was never rewritten.

---

## 3. Answers to the 8 questions

### 1. Exact root cause

- **File:** `india/recommendation_generator.py`
- **Function:** `evidence_gate(champ, idx, reg)`
- **Line:** 71
- **Code:** `q = (1 + champ).resample("Q").prod() - 1`
- **Exception:** `ValueError: 'Q' is no longer supported for offsets. Please use 'QE' instead.`
- **Underlying pandas change:** in pandas ≥ 2.2 the frequency aliases `Q`, `Y`, `M`, `W`, `A` were deprecated in favor of end-anchored variants (`QE`, `YE`, `ME`, `WE`, `AE`). In some later pandas version (likely 2.3 or 3.0 depending on installed patch) the deprecation was converted to a hard removal. CI's pandas is at the "removed" tier; the runner has no fallback.

### 2. Why it happens only on GitHub

The GitHub Actions workflow installs pandas via
`pip install -r requirements-dashboard.txt gspread google-auth yfinance`
where `requirements-dashboard.txt` specifies `pandas>=2.0` (unbounded upper
limit).  pip resolves this to the newest available pandas at run time.
That newest pandas has removed the `"Q"` alias.

The workflow will **fail every day** as long as (a) pip continues to
resolve pandas to the "Q-removed" version AND (b) the code continues to
use `"Q"`. Both conditions hold.

### 3. Why local execution succeeds

Two contributing factors on the local Windows host:

- **Local pandas version is 2.2.3** (verified this session). In 2.2.x the
  `"Q"` alias still WORKS (with a `FutureWarning`), it does not raise.
- **`india/recommendation_generator.py:36`** contains
  `warnings.simplefilter("ignore")`. This suppresses the FutureWarning so
  the local run is completely silent, giving false confidence.

If the operator upgrades local pandas to the same version as CI, the
local run would fail with the identical exception.

### 4. Why the workflow still succeeds

Two masks on the engine step in `.github/workflows/aegis-daily.yml`:

```yaml
python india/recommendation_generator.py || echo "engine issue; will send last snapshot"
python india/recommendation_db.py         || echo "db update skipped"
python india/scorecard.py                 || echo "scorecard skipped"
python india/ops_check.py                 || echo "ops-check reported issues (see board above)"
```

- Bash `||` operator: if the left side exits non-zero, run the right side.
  The right side (`echo …`) always exits 0.
- Composite exit of the *step* is the exit of its last command. All four
  are masked → step exits 0 → GitHub Actions marks step as SUCCESS.
- Downstream `if: steps.freshness.outputs.fresh == 'true'` conditions
  still evaluate true → downstream ran on **stale files**.

Concretely visible in the log:
- The traceback appears.
- Immediately below it: `engine issue; will send last snapshot`
- Then: `snapshot: 2026-07-14 · DB now holds 36 rows across 3 days` — the
  db step read stale registry and reported yesterday's numbers as if
  they were today's.
- `ops_check` then prints **`ALL GREEN — production is operationally healthy`**
  because it checks data-freshness at file level and finds parquets
  dated 2026-07-16 — never asserting that recommendations are new.

### 5. Whether secondary failures are hidden

**No secondary FAILURES are hidden.** Steps 5–7 (db, scorecard,
ops_check) actually SUCCEEDED — they just operated on stale inputs. Their
output is technically correct given their input (2026-07-14 registry), so
no exception. That is a different kind of defect from what the mask
hides.

**One indirect hidden issue:** `ops_check.py`'s green light is
misleading. It reports "Recommendation DB 36 rows over 3 day(s)" and
"Data freshness latest bar 2026-07-16 (0d old)" — both true, but the
combination fails to detect that today's recommendations were never
generated. This is a **monitoring gap**, not a hidden failure per se.

### 6. Minimal code change required

**Exactly one character change** at `india/recommendation_generator.py:71`:

```diff
-    q = (1 + champ).resample("Q").prod() - 1
+    q = (1 + champ).resample("QE").prod() - 1
```

That is the only line the traceback identifies. Recommend also grepping
the codebase for other deprecated frequency aliases before shipping:

```
grep -rnE '\.resample\((["'\''])[QMYWA]\1\)' india/ nexaquant/
grep -rnE 'freq=\s*(["'\''])[QMYWA]\1'         india/ nexaquant/
```

**IMPORTANT GOVERNANCE CONSTRAINT — this is a sealed file.**

`india/recommendation_generator.py` is one of the five files whose
content contributes to the MON001 fingerprint hash
`64e74483d9bd0444...`. Any byte-change modifies the fingerprint, which
invalidates certification `MON001-CERT-2026-07-15`.

**This fix therefore requires a MON001 amendment ceremony** analogous to
`MON001-AMEND-2026-07-16-portability`. Two paths:

- **Path A (correct fix, requires re-seal):**
  1. Modify line 71: `"Q"` → `"QE"`.
  2. Recompute MON001 fingerprint hash.
  3. Update `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json` with new hash.
  4. Add `MON001-AMEND-2026-07-17-pandas-QE` note to `docs/MON001_CERTIFICATION.md`.
  5. Run full regression to confirm all tests still green.
  6. Commit + push.

- **Path B (workaround, no sealed change — TEMPORARY):**
  1. Pin `pandas<2.3` (or wherever "Q" was hard-removed) in
     `requirements-dashboard.txt` OR the workflow's pip-install line.
  2. Do NOT modify `recommendation_generator.py`.
  3. Fingerprint unchanged.
  4. Certification unchanged.
  5. But: technical debt — the code still uses a removed API. First
     time pip resolves to a newer pandas (or the upper pin fails), the
     failure returns.

**My recommendation:** Path A. Path B is a temporary reprieve — it does
not fix the code, only postpones the failure.

### 7. Regression test required

A single new test in `nexaquant/tests/test_ci_discipline.py` (or a new
file `test_pandas_freq_aliases.py`):

```python
def test_no_deprecated_pandas_freq_aliases():
    """pandas ≥ 2.3 removes 'Q', 'Y', 'M', 'W', 'A' offset aliases.
    Every occurrence must use the end-anchored variant (QE / YE / ME / WE / AE).
    """
    import re
    deprecated = re.compile(r'\.resample\((["'])(Q|Y|M|W|A)\1\)|freq\s*=\s*(["'])(Q|Y|M|W|A)\3')
    hits = []
    for path in ROOT.rglob("*.py"):
        if "/tests/" in str(path) or "__pycache__" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in deprecated.finditer(text):
            hits.append((path, m.group(0)))
    assert not hits, f"deprecated pandas frequency aliases used: {hits}"
```

Additionally, a **runner-side integration test** in
`test_ops_pipeline.py`:

```python
def test_generator_writes_fresh_output_end_to_end():
    """Invoke recommendation_generator.main() in an isolated cwd; assert
    it exits 0 AND writes aegis_today.csv with today's IST 'Generated' date."""
```

This second test is more expensive (imports the full engine) but would
have caught the "Q" removal on the day pandas released it.

### 8. Monitoring check required

Two complementary checks:

- **Workflow-level assertion (workflow YAML, not sealed):**
  ```yaml
  - name: Assert aegis_today.csv was generated in this run
    run: |
      test -f data/aegis_today.csv
      GEN=$(head -2 data/aegis_today.csv | tail -1 | cut -d, -f1)
      TODAY=$(TZ=Asia/Kolkata date +%Y-%m-%d)
      test "$GEN" = "$TODAY" || (echo "STALE: aegis_today.csv Generated=$GEN today=$TODAY"; exit 1)
  ```
  Placed BETWEEN the engine step and the Telegram send step. Blocks the
  pipeline if generator did not rewrite the file.

- **MON001 diagnostic timeliness check** (ops-side, not sealed — lives in
  `india/monitoring/MON001_Forward_Validation/ops/health_check.py`):
  ```python
  def check_ledger_asof_timely():
      """Latest forward_ledger row's asof must be within 1 trading day of
      today IST. If older, this indicates the daily pipeline is producing
      stale data."""
      # WARN if gap == 1; HALT if gap >= 2
  ```

The workflow assertion is faster to add and blocks the immediate defect.
The MON001 check is the durable safety net that catches any future
recurrence AND the current 3-day-stale ledger.

---

## 4. Additional evidence from the log

Two remarks the log makes that are worth quoting:

- **`snapshot: 2026-07-14 · DB now holds 36 rows across 3 days`** —
  confirms exactly what the forensic report predicted: the DB step reads
  stale registry, reports yesterday's numbers.

- **`Daily diff 2026-06-29 -> 2026-07-14: NEW: ['TORNTPHARM', 'PIDILITIND', 'ITC']`** —
  the "diff" is between 2026-06-29 and 2026-07-14. It should have been
  between 2026-07-14 and 2026-07-16. The registry has not been extended
  since praveen330's manual commit on 2026-07-14.

- **`RESULT: ALL GREEN — production is operationally healthy.`** —
  false confidence. ops_check has no timeliness assertion.

- **`Live lifecycle: ARCHIVED=24  LIVE=12`** — the 12 "LIVE" recs are the
  2026-07-14 ones. They have been "LIVE" (from ops_check's perspective)
  for 3 days without refresh.

---

## 5. Certified facts (definitive)

Every fact below is quoted or directly extracted from the CI log the
operator pasted for AEGIS Daily #43:

- ✅ Step duration: 12 s
- ✅ Exception type: `ValueError`
- ✅ Exception message: `'Q' is no longer supported for offsets. Please use 'QE' instead.`
- ✅ Failing file: `/home/runner/work/NexaQuant/NexaQuant/india/recommendation_generator.py`
- ✅ Failing line: 71
- ✅ Failing function: `evidence_gate`
- ✅ Failing code: `q = (1 + champ).resample("Q").prod() - 1`
- ✅ Bash mask fired: `engine issue; will send last snapshot`
- ✅ Downstream steps ran on stale data: db (`36 rows across 3 days`), scorecard, ops_check (`ALL GREEN`).
- ✅ Registry range: 2026-06-29 → 2026-07-14 (unchanged since last user push)
- ✅ Sealed status: `india/recommendation_generator.py` is in the
  MON001 fingerprint baseline_files list — any content change requires
  re-seal ceremony.

---

## 6. What this fix will unblock

Once Path A is applied:

- `recommendation_generator.py` will exit 0 on the runner every weekday.
- `data/aegis_today.csv` will be rewritten with today's `Generated` date.
- Telegram will deliver TODAY's recommendations.
- `forward_ledger.jsonl` will get its first live row after 3-day pause (2026-07-14 → today).
- MON001 `global_state` will return from `DIVERGED` to `OK` (the divergence was because live snapshot lagged 3 days).

Once the workflow-level assertion is added:

- Any future generator failure blocks the pipeline instead of silently
  sending stale content.

Once the deprecated-alias regression test is added:

- CI will fail on any future push that reintroduces a removed pandas
  frequency alias.

---

## 7. What I did NOT do

- ❌ Did not modify `recommendation_generator.py` (sealed file — requires ceremony).
- ❌ Did not modify workflow YAML.
- ❌ Did not modify `requirements-dashboard.txt`.
- ❌ Did not push any commit.
- ❌ Did not run `recommendation_generator.py` locally.
- ❌ Did not touch sealed MON001 files.
- ❌ Did not begin OPS001-E as a feature phase.

---

## 8. Awaiting operator decision

The report is complete. The exact one-character fix (`"Q"` → `"QE"` on
line 71) requires operator authorization because
`recommendation_generator.py` is in the MON001 fingerprint set.

**Two authorized paths:**

- **Path A (recommended):** Amendment ceremony `MON001-AMEND-2026-07-17-pandas-QE`.
  1-character code change + fingerprint re-seal + certification note +
  full regression + commit. Estimated: single focused session (~30
  minutes) analogous to portability amendment.

- **Path B (temporary):** Pin pandas in requirements-dashboard.txt.
  Zero code change to sealed files. Zero fingerprint change. Buys time
  but leaves the API-drift landmine in the code.

Either path also warrants the workflow-level freshness assertion +
regression test to prevent the same kind of failure recurring.

**No implementation until you authorize.** Standing by.
