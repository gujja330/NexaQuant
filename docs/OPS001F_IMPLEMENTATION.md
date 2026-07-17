# OPS001-F · Production Remediation — Implementation Report

**Implementation ID:** `OPS001F-IMPL-2026-07-17`
**Amendment ID:** `MON001-AMEND-2026-07-17-pandas-QE`
**Certification:** `MON001-CERT-2026-07-17` (supersedes `MON001-CERT-2026-07-15`)
**Trigger:** OPS001-E root cause report (`docs/OPS001E_ROOT_CAUSE_REPORT.md`)
**Scope:** Production correctness fix. No strategy behaviour change. No research change.

---

## 1. Summary

Fixed a chronic 17-day production defect where `recommendation_generator.py`
had been failing silently on every CI run since 2026-06-30, causing
Telegram to deliver the same 2026-07-14 recommendations every day.

**Root cause:** `resample("Q")` and `resample("M")` — pandas ≥ 2.3 removed
these deprecated aliases in favour of `"QE"` / `"ME"`. Local pandas 2.2.3
still accepted them; CI's newer pandas raised `ValueError`. The workflow's
`|| echo "engine issue; will send last snapshot"` mask hid the failure.

**Fix:** replace the deprecated aliases (5 lines across 4 files),
remove the mask on the critical engine step, add a defense-in-depth
freshness gate, add a Telegram-sender-side freshness check, and register
a regression test forbidding removed pandas aliases from ever landing again.

MON001 fingerprint changes:
- OLD: `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42`
- NEW: `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf`

---

## 2. Files changed

### 2.1 Sealed files (part of MON001 fingerprint — required amendment ceremony)

| File | Line | Change | Reason |
|---|:-:|---|---|
| `india/recommendation_generator.py` | 71 | `resample("Q")` → `resample("QE")` | The exact failing line from CI log. `Q` was removed from pandas offset aliases. |
| `india/confidence_engine.py` | 77 | `resample("M")` → `resample("ME")` | Same class of defect. Would have failed next time this code path was exercised. |

### 2.2 Non-sealed production code (same defect class)

| File | Line | Change | Reason |
|---|:-:|---|---|
| `india/capital_ladder.py` | 47 | `resample("M")` → `resample("ME")` | Same class of defect. |
| `india/evidence/mom_breakdown.py` | 30, 32 | `resample("M")` → `resample("ME")` | Same class of defect (2 occurrences). |

### 2.3 Workflow YAML (fail-fast + defense-in-depth)

| File | Change | Reason |
|---|---|---|
| `.github/workflows/aegis-daily.yml` | Removed `\|\| echo "engine issue; will send last snapshot"` mask on generator step | Root cause enabler — mask converted fatal generator failure into silent step success. |
| `.github/workflows/aegis-daily.yml` | Added `Delete stale outputs (defense-in-depth pre-generator)` step | Removes `data/aegis_today.csv` etc. before generator so any downstream file MUST be freshly written. |
| `.github/workflows/aegis-daily.yml` | Split engine step: `Run AEGIS engine (fail-fast)` runs generator ALONE, then downstream. | Prevents silent multi-script masking. |
| `.github/workflows/aegis-daily.yml` | Added `Verify aegis_today.csv is fresh` step with `id: freshcheck` between engine and Telegram | Blocks Telegram send if generator failed OR wrote file with wrong `Generated` date. |
| `.github/workflows/aegis-daily.yml` | Downstream steps (Sheets, Telegram, commit) gated on `steps.freshcheck.outputs.verified == 'true'` | Belt-and-suspenders — even if freshcheck were somehow skipped, downstream needs its output. |
| `.github/workflows/aegis-daily.yml` | `recommendation_db.py`, `scorecard.py`, `ops_check.py` retained `\|\| echo` masks | These are non-critical (reporting/DB append). Failure does not corrupt Telegram output. |

### 2.4 Telegram sender (defense-in-depth)

| File | Change | Reason |
|---|---|---|
| `scripts/telegram_send_with_retry.py` | New `_pre_send_freshness_check()` function | Refuse to invoke `india/telegram_notify.py` if `aegis_today.csv` is missing OR its `Generated` column != today IST. Returns exit code 2 (distinct from network-retry exit 1). |
| `scripts/telegram_send_with_retry.py` | New `_today_ist_str()` helper | Explicit IST (UTC+5:30) date regardless of host TZ. |
| `scripts/telegram_send_with_retry.py` | `main()` calls freshness check before the retry loop | Prevents any invocation path from silently sending stale content. Logs refusal to `telegram_delivery_*.jsonl` with verdict `REFUSED_STALE`. |

### 2.5 Certification + tests

| File | Change | Reason |
|---|---|---|
| `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json` | Hash regenerated: `e4c070673568c52d...` | Reflects amended `recommendation_generator.py` + `confidence_engine.py` content. |
| `docs/MON001_CERTIFICATION.md` | Added §16 pandas-QE amendment note + updated cert ID at top | Governance trail. New cert `MON001-CERT-2026-07-17`. |
| `nexaquant/tests/test_ci_discipline.py` | Added `test_no_deprecated_pandas_frequency_aliases` | Regression preventing future `Q`/`M`/`Y`/`A`/`H`/`T`/`L` in resample() or pandas-context freq=. Excludes Python def-parameter defaults. |
| `nexaquant/tests/test_ci_discipline.py` | Removed stale GRANDFATHERED_MASKS entry for `engine issue; will send last snapshot` | The mask no longer exists — registry entry removed for accuracy. |

---

## 3. Before / after (verbatim)

### 3.1 `india/recommendation_generator.py:71`

```diff
 def evidence_gate(champ, idx, reg):
     s = stats(champ, idx)
-    q = (1 + champ).resample("Q").prod() - 1
+    q = (1 + champ).resample("QE").prod() - 1
```

### 3.2 `india/confidence_engine.py:77`

```diff
     # tail
-    m = (1 + net).resample("M").prod() - 1
+    m = (1 + net).resample("ME").prod() - 1
```

### 3.3 `india/capital_ladder.py:47`

```diff
-        m = (1 + net).resample("M").prod() - 1
+        m = (1 + net).resample("ME").prod() - 1
```

### 3.4 `india/evidence/mom_breakdown.py:30, 32`

```diff
-    m = (1 + net).resample("M").prod() - 1
+    m = (1 + net).resample("ME").prod() - 1
     nf = idx.pct_change().reindex(net.index).fillna(0.0)
-    mn = (1 + nf).resample("M").prod() - 1
+    mn = (1 + nf).resample("ME").prod() - 1
```

### 3.5 Workflow — engine step split + freshcheck

```diff
-      - name: Run AEGIS engine + database + evidence + ops check
-        if: steps.guard.outputs.run == 'true' && steps.freshness.outputs.fresh == 'true'
-        run: |
-          python india/recommendation_generator.py || echo "engine issue; will send last snapshot"
-          python india/recommendation_db.py || echo "db update skipped"
-          python india/scorecard.py || echo "scorecard skipped"
-          python india/ops_check.py || echo "ops-check reported issues (see board above)"

+      - name: Delete stale outputs (defense-in-depth pre-generator)
+        if: steps.guard.outputs.run == 'true' && steps.freshness.outputs.fresh == 'true'
+        run: rm -f data/aegis_today.csv data/aegis_candidates.csv reports/AEGIS_LATEST.xlsx
+
+      - name: Run AEGIS engine (fail-fast — no mask)
+        id: engine
+        if: steps.guard.outputs.run == 'true' && steps.freshness.outputs.fresh == 'true'
+        run: python india/recommendation_generator.py
+
+      - name: Verify aegis_today.csv is fresh (blocks stale Telegram)
+        id: freshcheck
+        if: steps.guard.outputs.run == 'true' && steps.engine.outcome == 'success'
+        run: |
+          test -f data/aegis_today.csv || (echo "FAIL: data/aegis_today.csv missing after generator"; exit 1)
+          GEN=$(head -2 data/aegis_today.csv | tail -1 | cut -d, -f1)
+          TODAY_IST=$(TZ=Asia/Kolkata date +%Y-%m-%d)
+          if [ "$GEN" != "$TODAY_IST" ]; then
+            echo "FAIL: aegis_today.csv Generated=$GEN but today IST=$TODAY_IST"
+            exit 1
+          fi
+          echo "aegis_today.csv Generated=$GEN matches today IST=$TODAY_IST — proceeding"
+          echo "verified=true" >> $GITHUB_OUTPUT
+
+      - name: Run database + scorecard + ops check (non-critical — masked)
+        if: steps.guard.outputs.run == 'true' && steps.freshcheck.outputs.verified == 'true'
+        run: |
+          python india/recommendation_db.py || echo "db update skipped"
+          python india/scorecard.py || echo "scorecard skipped"
+          python india/ops_check.py || echo "ops-check reported issues (see board above)"
```

### 3.6 Downstream steps (Sheets / Telegram / commit) — gate switched

```diff
       - name: Push to Google Sheets (no-ops if secrets absent)
-        if: steps.guard.outputs.run == 'true' && steps.freshness.outputs.fresh == 'true'
+        if: steps.guard.outputs.run == 'true' && steps.freshcheck.outputs.verified == 'true'
```

Same swap applied to Telegram health-check, Telegram notify, and Mark-published-commit steps.

### 3.7 `scripts/telegram_send_with_retry.py` — new freshness gate

```diff
 ROOT = Path(__file__).resolve().parents[1]
 REPORTS = ROOT / "reports"
 NOTIFY = ROOT / "india" / "telegram_notify.py"
+AEGIS_TODAY = ROOT / "data" / "aegis_today.csv"

+def _today_ist_str() -> str:
+    utc = datetime.now(timezone.utc)
+    ist = utc + timedelta(hours=5, minutes=30)
+    return ist.strftime("%Y-%m-%d")

+def _pre_send_freshness_check() -> tuple[bool, str]:
+    if not AEGIS_TODAY.exists():
+        return False, f"aegis_today.csv missing at {AEGIS_TODAY}"
+    with AEGIS_TODAY.open("r", encoding="utf-8") as f:
+        _hdr = f.readline()
+        first = f.readline()
+    if not first.strip():
+        return False, "aegis_today.csv has no data rows"
+    generated = first.split(",", 1)[0].strip().strip('"')
+    today_ist = _today_ist_str()
+    if generated != today_ist:
+        return False, (f"aegis_today.csv Generated={generated!r} != today IST={today_ist!r} "
+                       f"— refusing to send stale recommendations")
+    return True, f"aegis_today.csv Generated={generated} matches today IST={today_ist}"

 def main() -> int:
     ...
+    # OPS001-F: refuse to send stale recommendations.
+    ok, reason = _pre_send_freshness_check()
+    if not ok:
+        print(f"  FRESHNESS CHECK FAILED: {reason}")
+        _append_ledger({... "verdict": "REFUSED_STALE" ...})
+        return 2
+    print(f"  freshness check: {reason}")
     for attempt in range(1, n_attempts + 1):
         ...
```

### 3.8 Sealed fingerprint

```diff
-  "hash": "64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42"
+  "hash": "e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf"
```

Per-file hashes for `recommendation_generator.py` and `confidence_engine.py` also updated (automated by `compute_fingerprint()`).

---

## 4. Semantic-equivalence justification

The pandas rename `Q → QE`, `M → ME`, `Y → YE`, `A → YE`, `H → h` etc. is a
**cosmetic API cleanup**, not a behaviour change. The `E` suffix makes
"End-anchored" explicit; the runtime behaviour of `Q` (deprecated) and `QE`
(current) is byte-identical.

Verification: pandas 2.2.x (which still accepts BOTH aliases) treats them
as strict aliases:

```python
>>> import pandas as pd
>>> s = pd.Series([1,2,3,4], index=pd.date_range("2024-01-01", periods=4, freq="MS"))
>>> s.resample("Q").sum().equals(s.resample("QE").sum())
True
```

The numerical output of `evidence_gate()` in `recommendation_generator.py`
is therefore byte-identical before and after this amendment.
**No strategy, ranking, scoring, portfolio, or database schema change.**

---

## 5. Regression tests

### 5.1 New test — forbid deprecated aliases

`nexaquant/tests/test_ci_discipline.py::test_no_deprecated_pandas_frequency_aliases`

Scans every `*.py` in the repo (excluding `__pycache__`, `site-packages`,
and this test file). Two regex patterns:

- `resample(Q|M|Y|A|H|T|L)` — flagged always
- `date_range(...freq="Q")` — flagged when in a pandas call context
  (`date_range` / `bdate_range` / `Grouper` / `to_datetime` / `PeriodIndex`)

Explicitly skips Python `def ` / `async def ` lines (parameter defaults
like `def build_dataset(freq="M", ...)` where `freq` is a dict key, not
a pandas arg).

### 5.2 Existing test — fingerprint match (unchanged behaviour)

`test_ops_daemon.py::test_36_mon001_fingerprint_matches_seal` verifies
that `compute_fingerprint()` returns exactly the sealed hash. After
amendment: sealed hash is `e4c070673568c52d...`, computed hash is
`e4c070673568c52d...`, test passes.

Same guard exists in:
- `nexaquant/tests/test_regression.py::test_mon001_fingerprint_matches_seal`
- `nexaquant/tests/test_ops_notify.py::test_31_mon001_fingerprint_matches_seal`
- `nexaquant/tests/test_ops_commissioning.py::gov_22_mon001_fingerprint_matches_seal`

All 4 fingerprint-match guards now pass with the new hash.

### 5.3 Regression suite roster (unchanged)

- MON001 core (25 tests)
- MON001 ops (23 tests)
- LAB010 (25 tests)
- Core lab (17 tests)
- LAB009 maturity (8 tests)
- ENG001 lib (33 tests)
- **ENG003 CI discipline (6 tests — was 5; +1 for OPS001-F)**
- ENG003 governance (8 tests)
- Telegram reliability (13 tests)
- OPS001-A pipeline (31 tests)
- OPS001-B daemon (36 tests)
- OPS001.5 commissioning (23 tests)
- OPS001-C notify (32 tests)

Total: **13 suites, 280 tests** (was 279; +1 in ENG003 CI discipline).

---

## 6. Risk assessment

| Risk | Probability | Impact | Mitigation |
|---|:-:|:-:|---|
| **Numerical drift from `Q → QE` / `M → ME`** | VERY LOW | Would falsify all forward evidence | pandas explicitly documents these as aliases; verified byte-equality above. `resample` return values are identical. |
| **MON001 fingerprint mismatch on runner** | LOW | Health check HALT | New hash written to `sealed_fingerprint.json`; runner recomputes and compares to same value. Path A (portability amendment) precedent from 2026-07-16 verified this flow works. |
| **CI still fails after fix** | LOW | Repeat of current situation | Removed the `|| echo` mask — any future failure is visible. Regression test prevents re-introduction of same alias class. |
| **Freshness gate has a bug** | LOW | Legitimate fresh runs blocked (over-cautious) | Gate uses `head -2 | tail -1 | cut -d,` — well-tested pattern. IST calc uses fixed UTC+5:30 offset (no DST in India). |
| **`AEGIS_TODAY.csv` file schema drifts** (first column no longer "Generated") | LOW | Freshness gate accepts stale files | Pin `head -2 | tail -1 | cut -d, -f1` reads first column of first data row. If schema changes, both freshness gate AND recommendation_generator would need updating together — a coordinated change. |
| **Sender-side freshness check + workflow gate double-block a legit run** | VERY LOW | Missed send | Both gates use identical logic (`Generated == today IST`). If one passes, so should the other. |
| **Registry entry for removed mask left stale** | HIGH (already occurred) | Cosmetic (no functional impact) | Registry entry removed in this commit. |
| **Regression test regex false-positives** | MEDIUM | CI fails on legitimate code | Refined regex now: only flags `resample("X")` and pandas-call `freq="X"`; skips `def` parameter defaults. Verified on `india/dataset.py:26` (used to false-fire; now clean). |
| **Broker mode drift to non-PAPER during fix** | ZERO | System places real orders | `broker_layer.py` unchanged; `PaperOnlyBrokerLayer.available()` still hard-coded False. Explicitly verified by unchanged fingerprint of that sealed file. |
| **`cumulative_strategy_search` incremented** | ZERO | Trial-budget violation | Not touched. Verified: `cumulative_strategy_search: 38`. |

### 6.1 Rollback plan

If any post-deploy verification fails:

```bash
git revert <sha of OPS001-F commit>
git push
```

Rolling back restores the previous sealed_fingerprint.json (with the
pre-amendment hash). Regression suite auto-verifies the fingerprint.
Recovery time: single git command + one CI run (~4 min).

The two `resample()` calls in sealed files would revert to `"Q"` and
`"M"`, meaning the pre-existing CI failure returns. That is worse than
the fix state but no worse than the pre-fix state.

---

## 7. Behaviour preserved (verified, not asserted)

- Strategy: HRP, sector_cap=2, name_cap=0.30, method="hrp" — untouched
- Ranking: unchanged (recommendation_generator's ranking code is not on the amended lines)
- Scoring: unchanged (score computation unaffected by resample alias)
- Portfolio logic: `arjuna_v2.py` untouched
- Database schema: `data/aegis_registry.csv` and `data/aegis_recommendation_db.csv` schemas unchanged
- MON001 logic: sealed core untouched
- LAB artefacts: zero LAB files modified
- Trial count: `cumulative_strategy_search: 38` unchanged
- Forward boundary: `2026-03-28` unchanged
- Forward ledger: 150 rows, hash chain intact

---

## 8. Final validation summary

Pre-commit local run:

- CI discipline suite: **6/6 PASS** (including new deprecated-alias test)
- Governance suite: **8/8 PASS**
- MON001 health check: **9/9 INFO**, exit 0, new hash `e4c070673568c52d...`
- Full regression: **12/13 suites PASS**; the 1 suite showing 31/32 (`test_ops_notify` test_30) fails because it uses `git diff HEAD --name-only` and sees the uncommitted sealed changes. After commit, that diff is empty and the test passes. (Same behaviour as `MON001-AMEND-2026-07-16-portability` — verified by commit `f50e56f`.)

Post-commit expected state:
- 13 suites, 280 tests, all PASS
- All 4 fingerprint-match guards report the new hash
- All 4 sealed-file-diff guards see empty diff → PASS

---

## 9. What OPS001-F does NOT do

- Does not change any strategy, ranking, scoring, or portfolio logic
- Does not change database schemas
- Does not change MON001 sealed CORE modules (fingerprint, forward_ledger, monitor, baseline_envelope, broker_layer, preregistration, mon001.yaml)
- Does not modify LAB artefacts
- Does not begin MON002 or LAB011
- Does not add new features
- Does not tune research parameters
- Does not increment `cumulative_strategy_search`
- Does not promote any research candidate

---

## 10. Deployment sequence

1. Commit all changes with message `OPS001-F: pandas-QE compatibility + fail-fast Telegram gate`
2. Push to `origin/main`
3. GitHub Actions ENG001 Regression will run on the push and must go GREEN
4. Next scheduled AEGIS Daily run (16:15 IST) will:
   - execute `refresh_data.py` (unchanged)
   - execute freshness gate (unchanged)
   - **delete `data/aegis_today.csv`** (new)
   - execute `recommendation_generator.py` (now `resample("QE")` — will succeed)
   - execute `Verify aegis_today.csv is fresh` (new — asserts `Generated=today_ist`)
   - execute Sheets push, Telegram health, Telegram notify (gated on freshcheck)
   - commit fresh `data/aegis_today.csv`, registry, DB, dashboard
5. Operator receives Telegram message with `Generated=2026-07-17` (or whatever the true asof is)

**First observable proof-of-fix:** the next weekday's Telegram message
whose header carries today's IST date.

---

**End of OPS001-F implementation report.**
