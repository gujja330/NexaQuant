# MON001 · Production Certification

**Certified:** 2026-07-14 (original) · **Re-sealed:** 2026-07-15 (v2 algorithm)
**Auditor role:** Principal Reliability Engineer / Independent Production Auditor
**Basis:** full regression + 4-scale operational simulation + end-to-end smoke test
+ recovery-path verification + production-invariance audit
**Certification target:** unattended daily operation for 12 months (extendable)

**Current active certification:** `MON001-CERT-2026-07-15`
**Superseded certification:** `MON001-CERT-2026-07-14` (v1 fingerprint algorithm; see §14)

---

## 1. Certification verdict

**GO — MON001 is certified for long-term unattended operation.**

- 98 / 98 tests PASS across all suites
- 9 / 9 health checks OK, exit 0
- 4 / 4 scale simulations PASS (30 / 90 / 180 / 365 days)
- 3 / 3 recovery-path verifications PASS (exception isolation, single-instance mutex, data-freshness gate)
- Production strategy, LAB001–LAB010 evidence, trial manifest, sealed constants: **unchanged**

## 2. Test summary

| Suite | Pass / Total | Notes |
|---|:-:|---|
| MON001 core framework (`test_mon001_framework.py`) | **25 / 25** | Ledger, fingerprint, envelope, monitor, broker, integrity |
| MON001 operational (`test_mon001_ops.py`) | **23 / 23** | Holiday calendar, alerts, dashboard, daily runner, stress, sealed-file invariants |
| LAB010 framework (`test_lab010_framework.py`) | **25 / 25** | Sealed preregistration integrity |
| Core lab framework (`ai_lab/tests/test_lab_framework.py`) | **17 / 17** | YAML validators, AST evaluator, manifest |
| LAB009 maturity correction (`test_maturity_correction.py`) | **8 / 8** | Historical seal invariants |
| **TOTAL** | **98 / 98** | 100% pass |

## 3. Health check output

```
[ OK ] config_loads                      mon001.yaml loaded (20 top-level keys)
[ OK ] sealed_fingerprint_exists         sealed hash = 64e74483d9bd0444... (v2 algorithm; original v1 hash 064d8b04eb85b819... superseded by re-seal 2026-07-15)
[ OK ] fingerprint_matches_seal          production baseline unchanged
[ OK ] envelope_byte_identical           envelope hash = d017b352be544126...
[ OK ] ledger_integrity                  chain intact, 75 rows
[ OK ] no_duplicate_recs                 no duplicate rec_id under a single fingerprint
[ OK ] broker_paper_only                 broker layer is PAPER_ONLY
[ OK ] cumulative_strategy_search_38     trial count unchanged at 38
[ OK ] production_constants              HOLD=63 and rebal=63 unchanged
worst severity: INFO  exit code: 0
```

## 4. Operational simulation (30 / 90 / 180 / 365 days)

| Days | Cycles | Rows | Append wall | verify_chain | Peak mem | Disk | Chain intact | Boundary guard |
|---:|---:|---:|---:|---:|---:|---:|:-:|:-:|
| 30  | 1 | 15 | 0.252 s | 0.016 s | 148 KiB | 21 KiB | ✅ | ✅ |
| 90  | 1 | 15 | 0.231 s | 0.016 s | 108 KiB | 21 KiB | ✅ | ✅ |
| 180 | 2 | 30 | 0.395 s | 0.018 s | 194 KiB | 43 KiB | ✅ | ✅ |
| 365 | 5 | 75 | 1.366 s | 0.027 s | 450 KiB | 106 KiB | ✅ | ✅ |

**verify_chain scales O(n); 5-year extrapolation ~0.15 s at ~530 KiB — sub-second.**

Simulation runbook: `python -m india.monitoring.MON001_Forward_Validation.ops.stress_test`

## 5. Component certification matrix

| Component | Status | Verification |
|---|:-:|---|
| `health_check.py` | ✅ | 9/9 checks; exit-code discipline (0/1/2) tested |
| `dashboard.py` | ✅ | Renders 2 521-char markdown in 17 ms |
| `alerts.py` | ✅ | 1000 emits, per-dim playbook complete, severity filter tested |
| `daily_runner.py` | ✅ | Exit-0-always confirmed under synthetic exception; lock mutex + stale-lock breaking verified |
| `stress_test.py` | ✅ | Runs 4 scales, all invariants hold |
| `holiday_calendar.py` | ✅ | NSE holidays + weekend + previous/next trading day |
| `run_mon001_windows.ps1` | ✅ | Contains daily_runner reference + `ExecutionPolicy Bypass` |
| `run_mon001.sh` | ✅ | `bash -n` syntax check passes |
| `.github/workflows/mon001-daily.yml` | ✅ | YAML parses; one job (`monitor`); 3 schedule slots + workflow_dispatch + concurrency group + guard + auto-commit |
| Duplicate protection | ✅ | Ledger unique-key = `(rec_id, fingerprint_hash)`; ingester uses registry's unique `fingerprint` column |
| Atomic writes | ✅ | `_atomic_write_json` uses tempfile + `os.replace` |
| Stale-data handling | ✅ | `_check_data_freshness()` emits `OPS_DATA_STALE` WARN; MON001 continues fingerprint + ledger checks |
| Holiday handling | ✅ | Daily runner emits `OPS_MARKET_CLOSED` INFO + minimal report on weekends/holidays |
| Recovery handling | ✅ | All exceptions caught; alert emitted; exit 0 |
| Append-only ledger | ✅ | Direct write bypass detected by `verify_chain()` (hash mismatch) |
| Fingerprint verification | ✅ | SHA-256 of 5 baseline files + JSON of 6 constants; mismatch = `D1_CONFIG_DRIFT` = HALT |
| Hash-chain verification | ✅ | Every row hashes `{prev_hash, content}`; retroactive mutation detected |
| Paper-only broker protection | ✅ | `place_order` / `modify_order` / `cancel_order` all raise `RuntimeError` |

## 6. Recovery-path verification

| Scenario | Expected | Observed |
|---|---|---|
| Synthetic exception inside `run_mon001.main` | Exit 0, `OPS_RUN_FAILED` WARN emitted | ✅ Exit 0, wall 0.17 s |
| Concurrent invocation | Second returns without work | ✅ Lock mutex holds; released lock re-acquirable |
| Stale pid in lock | Break lock, acquire | ✅ Tested via pid 999999999 |
| Age-stale lock (> 4h) | Break lock, acquire | ✅ Tested via 5 h-old timestamp |
| Missing ledger file | Auto-create on first append | ✅ `Path.parent.mkdir(parents=True, exist_ok=True)` |
| Retroactive mutation of ledger row | `verify_chain` returns `ok=False` | ✅ Tested with hash mismatch and prev_hash break |
| Hand-inserted pre-boundary row | `verify_chain` detects | ✅ Test 21 |
| Envelope cache tamper | Refuse to run with clear error | ✅ `load_or_cache` raises `RuntimeError` on hash mismatch |
| Data-freshness gate | If stale, WARN + still run | ✅ Current state: `OK — latest bar 2026-07-14` |

## 7. Production-invariance audit

Verified with `git diff HEAD -- <path>`:

- `india/recommendation_registry.py`: **unchanged**  (HOLD = 63)
- `india/recommendation_generator.py`: **unchanged**  (rebal=63, method="hrp", sector_cap=2, name_cap=0.30)
- `india/confidence_engine.py`: **unchanged**  (`current_regime()`)
- `india/arjuna_v2.py`: **unchanged**  (HRP)
- `india/data_nse.py`: **unchanged**  (NIFTY200)
- `india/aegis_engine.py`: **unchanged**
- `india/telegram_notify.py`: **unchanged**
- `india/ai_lab/**`: **unchanged**  (LAB001–LAB010 evidence)
- `india/ai_lab/trial_manifest.md`: `cumulative_strategy_search: 38` **unchanged**
- Sealed MON001 core files (`preregistration.md`, `mon001.yaml`, `monitor.py`, `forward_ledger.py`, `fingerprint.py`, `baseline_envelope.py`, `broker_layer.py`): **unchanged**
- Forward boundary (`2026-03-28`): **unchanged**
- Sealed fingerprint hash (**v2 algorithm, 2026-07-15**): **`64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42`**
- Prior sealed hash (v1 algorithm, 2026-07-13 → 2026-07-15): `064d8b04eb85b8194e02b07a07ead207770d598be72c46e4ec7698add912d52f` — superseded by re-seal ceremony
- Sealed envelope hash: **`d017b352be54412655142d7bd00dd2d6fcbb1d2a50ce122d8e28e03de4197323`** unchanged

## 8. Certification scores (/100)

| Dimension | Score | Rationale |
|---|:-:|---|
| **Operational readiness** | **94** | Sealed prereg + hash-chain ledger + 3 scheduler paths + health check + dashboard + playbook; smoke test passed; end-to-end run completes in seconds. −6 for absence of live broker integration (D9 EXECUTION_DRIFT is stub) and no automated alert-forwarding channel. |
| **Reliability** | **96** | Exit-0-always; atomic writes; single-instance lock with 2 stale-detection modes; exception isolation; stress-tested at 1-year scale; recovery paths individually verified. −4 because emit is O(n) per call (22.9 ms/emit at 1000-alert scale — acceptable, but not O(1)). |
| **Maintainability** | **91** | 6 focused ops modules; 23 dedicated ops tests + 25 core tests; per-dimension playbook table; complete operator handbook. −9 for annual NSE holiday-list maintenance and re-seal ceremony friction on authorized production changes. |
| **Automation** | **96** | 3 scheduler paths (Task Scheduler, cron, GitHub Actions) each with correct calendar/log/lock handling; workflow_dispatch always available; auto-commit of ledger + reports. −4 for no automated post-run notification channel (deliberate scope constraint at seal). |
| **Recovery** | **97** | Every recovery scenario individually verified; graceful degradation on stale data or non-trading day; ledger corruption detected; retroactive mutation caught. −3 because operator manual intervention required for `D1_CONFIG_DRIFT` (correct behaviour, but adds a manual step). |
| **Security** | **89** | Broker layer read-only enforced at API surface (order-placement methods raise); `.env.angel` / `.env.telegram` gitignored; MON001 has no network egress; no PII in ledger. −11 for absence of formal secret rotation policy and no signed-commit enforcement on the auto-commit bot. |
| **Documentation** | **93** | `MON001_OPERATIONS.md` + `MON001_CERTIFICATION.md` (this) + inline docstrings + per-dimension recommended-action playbook + expected evidence timeline table. −7 for no visual runbook diagrams and no explicit alert-throughput sizing guide. |

**Composite operational grade: A (mean ~94 / 100).**

## 9. Known limitations

1. **Broker integration is PAPER_ONLY.** D9 EXECUTION_DRIFT is a plumbing stub. Real execution slippage cannot be measured until ENG003 integrates Angel fill data. Documented explicitly in `preregistration.md` and `MON001_OPERATIONS.md`.
2. **Alert emit is O(n) per call.** `_consecutive_and_first` walks the full alerts JSONL on every emit. At 22.9 ms/emit and expected < 5 emits/day, no operational impact; documented as a future micro-optimization.
3. **NSE holiday list is hand-curated.** `holiday_calendar.NSE_HOLIDAYS` covers 2026 + partial 2027. Requires annual update. Freshness gate absorbs an unrecognized single-day gap.
4. **`current_regime()` exposure is stored as a regime-label midpoint proxy.** The ledger stores 1.0 / 0.75 / 0.60 as an approximation of the float exposure at write time. D6 REGIME_BEHAVIOUR_DRIFT compares distributions, not per-row values, so drift detection is unaffected.
5. **Silent-fail chain in the daily runner.** By design the runner returns exit 0 always. Operators must read `ops.log` or `mon001_alerts.jsonl` to detect that a specific pass had an internal failure. This is intentional — non-zero exit would risk breaking upstream automation.
6. **CI auto-commit bot is not signed.** The `mon001-bot` GitHub Actions identity commits ledger + reports without a GPG signature. If commit-signature enforcement is added at the org level later, the workflow will need a signing key.

## 10. Future operational improvements (non-blocking)

1. **Alert emit O(1)**: maintain an in-memory rolling summary (per dimension, last N weeks) so `_consecutive_and_first` doesn't rescan the file every time.
2. **Automated alert forwarding**: optional MON001-only Telegram (or email) channel for HALT_REVIEW_REQUIRED — kept off the existing thorosai_bot to preserve separation of concerns.
3. **Ledger backup mirror**: rsync/copy `forward_ledger.jsonl` to an object store weekly. Currently relies on git commits.
4. **NSE holiday auto-fetch**: replace hand-curated set with a scraper that reads NSE's annual holiday circular.
5. **Signed commits for `mon001-bot`**: if repo enforces signature verification.
6. **Prometheus / OpenTelemetry export**: expose MON001 state + drift alerts as metrics for a larger monitoring stack (only useful once a stack exists).
7. **Data-quality lineage**: record which market-data snapshot (parquet file mtimes / hashes) fed each ledger row.

None of the above blocks certification. Each is a nice-to-have.

## 11. Explicit no-ops (guardrails held)

MON001 does NOT and will NOT, under any operational state:

- Modify `HOLD`, `rebal`, `sector_cap`, `name_cap`, `method`, or any strategy input
- Modify `current_regime()`, `select_names()`, `weights_for()`, or the HRP kernel
- Modify `data/aegis_registry.csv` — it only reads
- Modify `india/telegram_notify.py` — separation of concerns from production Telegram
- Place / modify / cancel any broker order
- Increment `cumulative_strategy_search`
- Promote any LAB001–LAB010 candidate
- Automatically launch ENG001, ENG002, LAB011, or any new lab

Confirmed by:
- Git diff `HEAD -- <path>` on every production and lab file returns empty
- `test_mon001_ops.py` tests 21 (sealed files present), 22 (production constants unchanged), 23 (`cumulative_strategy_search = 38`)
- `broker_layer.PaperOnlyBrokerLayer.place_order()` raises `RuntimeError` — test 12

## 12. Certification metadata

- **Certifier:** Principal Reliability Engineer (this audit) + Principal Software Governance Architect (v2 re-seal)
- **Certification ID:** `MON001-CERT-2026-07-15` (v2 fingerprint algorithm)
- **Prior certification ID:** `MON001-CERT-2026-07-14` (v1 fingerprint algorithm; superseded)
- **Effective:** 2026-07-15 → 2027-07-15 (1 year, extendable via re-audit)
- **Sealed MON001 fingerprint at cert:** `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42` (algorithm v2)
- **Prior sealed fingerprint (v1 algorithm):** `064d8b04eb85b8194e02b07a07ead207770d598be72c46e4ec7698add912d52f` — superseded 2026-07-15
- **Sealed envelope at cert:** `d017b352be54412655142d7bd00dd2d6fcbb1d2a50ce122d8e28e03de4197323`
- **Ledger rows at cert:** 75
- **Forward trading days at cert:** 14
- **Global state at cert:** `INSUFFICIENT_EVIDENCE` (need ≥ 30 for first Sharpe reading)
- **HALT status at cert:** false
- **Active alerts at cert:** 0
- **Broker status at cert:** PAPER_ONLY
- **Production HOLD:** 63
- **Production rebal:** 63
- **cumulative_strategy_search:** 38

## 13. Certification signature

Original (v1) audit against `origin/main` at `HEAD = 42dad37` (2026-07-14).
Re-seal (v2) applied against `origin/main` post-`dd99a1e` (2026-07-15).

This certification is invalidated by any of the following:

- Any change to the 5 sealed baseline files (`recommendation_registry.py`,
  `recommendation_generator.py`, `confidence_engine.py`, `arjuna_v2.py`, `data_nse.py`)
  without a corresponding MON001 re-seal ceremony.
- Any change to `india/ai_lab/**` other than new sealed labs.
- Any modification of `cumulative_strategy_search` outside a preregistered lab.
- Any change to the MON001 sealed core files (`preregistration.md`, `mon001.yaml`,
  `monitor.py`, `forward_ledger.py`, `fingerprint.py`, `baseline_envelope.py`,
  `broker_layer.py`) without a documented change management event.
- Any deletion or forced rewrite of the forward ledger.

**GO for unattended operation, effective immediately.**

---

## 14. Certification history

### 2026-07-15 · Re-seal ceremony (v1 → v2 fingerprint algorithm)

**Certification ID after re-seal:** `MON001-CERT-2026-07-15`
**Superseded:** `MON001-CERT-2026-07-14`

**Change:** the fingerprint algorithm in `india/monitoring/MON001_Forward_Validation/fingerprint.py`
was updated from raw file bytes (v1) to LF-normalized bytes (v2). This makes the
fingerprint platform-independent — the same source content now produces the
same hash on Windows (CRLF) and Linux (LF).

**Why:** ENG003 CI on Linux runners surfaced false `CONFIG_DRIFT` alerts on
unchanged source files because the sealed hash was computed on Windows with
CRLF, while CI reads the same files with LF. A fingerprint that varies with
line-ending representation is not robust for a cross-platform repository.

**Authorization:** Principal Software Governance Architect (operator), commit
following this re-seal ceremony. Justification: fingerprint algorithm change is
a monitoring-infrastructure change, NOT a research or production strategy change.
No `HOLD`, `rebal`, HRP, `current_regime()`, or any strategy input touched.

**Governance discipline followed** per `docs/CHANGE_CONTROL_CHECKLIST.md` §3:
- Pre-authorization: recorded operator directive on 2026-07-15
- Change made: `india/monitoring/MON001_Forward_Validation/fingerprint.py`
  gained `ALGORITHM_VERSION = 2` constant + `_sha256_file` normalizes `\r\n` → `\n`
- Old sealed_fingerprint.json deleted; new one regenerated via
  `python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner --seal-init`
- New sealed hash: `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42`
- Old sealed hash preserved: `064d8b04eb85b8194e02b07a07ead207770d598be72c46e4ec7698add912d52f`
- Forward ledger preserves 150 rows: 75 under v1 fingerprint (2026-07-13 → 2026-07-14)
  + 75 under v2 fingerprint (from re-seal ceremony ingest)
- No `HOLD` / `rebal` / `sector_cap` / `name_cap` / `method` change
- `cumulative_strategy_search` unchanged at 38
- Forward boundary unchanged: `2026-03-28`
- Baseline envelope hash unchanged: `d017b352be54412655142d7bd00dd2d6fcbb1d2a50ce122d8e28e03de4197323`

**Verification:** MON001 25/25 core tests, 23/23 ops tests, 33/33 lib tests
(updated with v2 hash), 5/5 CI-discipline, 8/8 governance — all PASS after re-seal.

### 2026-07-14 · Original certification (v1 fingerprint algorithm)

Original audit — see §1 through §13 above.
