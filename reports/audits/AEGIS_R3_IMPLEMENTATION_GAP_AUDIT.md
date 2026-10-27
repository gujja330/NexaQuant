# AEGIS R3 — Implementation Gap Audit
**2026-10-27 · read-only audit · no R3 code changed · nothing promoted**

Baseline: branch `main`, HEAD `4dbb96b9f`, `origin/main` `83c7d4d36`
(2 behind; `aegis-bot` artifact refreshes, 0 code files).

---

## 1 · Headline finding

**R3 is not an unfinished recommendation system. It is a working
falsification engine that has correctly rejected everything it tested.**

The 1,697 `ABSTAIN` observations are not a missing feature. They are the
aggregate of **11 specialist families, each blocked for a different and
documented reason**, several of them *after* being built, trained and
explicitly killed by a methodological gate.

R3 states this itself, in `master_status.py`:

> "Engineering is present; evidence is absent."

So the premise "R3 is not fully implemented, so it permanently abstains"
is **not supported**. The implementation exists. The evidence does not.

---

## 2 · Verification of the reported state

| Reported | Verified | Source |
|---|---|---|
| 1,697 observations | **1,697** | `reports/research/r3/shadow/ledger_india.jsonl` |
| 37 dates | **37** (`ledger_dates`) | `summary_india.json` |
| All ABSTAIN | **TAKE 0 · AVOID 0 · ABSTAIN 1697** | `action_counts` |
| No emitting model | `OOS_status: "NOT_APPLICABLE · no model is emitting"` ×1697 | ledger |
| Zero validated specialists | `validated_specialists: []` | summary |
| R3 refers to R2 signals | ledger carries `r2_engine`, `r2_signal`, `r2_confidence_pct` | ledger |
| PIT integrity | `PIT_status: "PIT_OK · inputs as-of the candidate date"` ×1697 | ledger |

Ledger span 2026-09-08 → 2026-10-26, 93 tickers, 26 R2 candidates seen on
the latest date. R3 module count: **26 files** under
`backend/research/r3_program/`.

---

## 3 · Specialist-by-specialist classification

Classification uses the audit's required categories. The critical column is
the last one.

| Class | Name | Disposition | Category |
|---|---|---|---|
| R3-A | Cohort description | `DESCRIPTIVE_ONLY` | **Implemented · correctly not decision-capable by design** |
| R3-B | Confidence robustness | `RESEARCH_ONLY` | **Implemented · correctly blocked by gate** |
| R3-C | Temporal / sequence | `INSUFFICIENT_SUBSTRATE` | **Blocked by missing data** |
| R3-D | — | `INSUFFICIENT_SUBSTRATE` | **Blocked by missing data** |
| R3-E | Multi-filter | `NOT_VALIDATED` | **Implemented · correctly blocked by gate** |
| R3-F | Market / sector | `NOT_AVAILABLE_AT_ASOF` | **Blocked by missing data** |
| R3-G | Exit / target | `NOT_VALIDATED` | **Implemented · correctly blocked by gate** |
| R3-H | External recommendations | `DESCRIPTIVE_ONLY` | **Stopped by prior decision** |
| R3-I | Intraday | `BLOCKED` | **Blocked by missing data** |
| R3-J | — | `RESEARCH_ONLY` | **Implemented · correctly blocked by gate** |
| R3-K | — | `INSUFFICIENT_SUBSTRATE` | **Blocked by missing data** |

**Zero specialists are classified "incomplete implementation."**
Five are blocked by absent substrate; four by validation gates; two are
descriptive by design.

---

## 4 · The rejections are real, and they are rigorous

These are preserved verbatim in `master_status.PRESERVED` and must not be
softened. They are the strongest evidence that R3 works as intended.

| Experiment | Disposition | Why |
|---|---|---|
| R3-C-TEMP Wave 1C · TCN / GRU / Transformer | **REJECTED** | "date leakage across the split; **killed by construction, not by score**" |
| II.1-GBM Wave 1D headline | **INVALIDATED** | AUC **1.000 / 0.974** kept as AUDIT HISTORY only — R-multiple tautology, `stop_distance` alone reached 0.853, 51.6% synthetic 5% default stops, neither split controlling ticker and date jointly |
| R3-G-EXIT Wave 1D-E · absolute-target falsification | **REJECTED** | "no absolute target both beat its baseline and added economic value · the R-multiple edge was **an artefact of the R definition**" |
| R3-E-2C · seven-filter research | **REJECTED** | "0 of 4 India and 0 of 6 USA dimensions survive once significance moves to **ticker units** (row p=0.000 → ticker p=0.386); incremental AUC +0.0138, CI [−0.074, +0.105]" |
| R3-G-EXIT Wave 1D-C · corrected validator | **PARTIAL** | joint ticker × date holdout, real vs default stops segmented |
| R3-G-EXIT Waves 1A/1B | **ACCEPTED** | entry coverage 12.4% → 100%; 547 India / 79 USA episodes; peak +1.573R decaying to +0.274R |

An AUC of **1.000** was correctly thrown away as a tautology. Sequence
models were killed for leakage *before* their scores were considered.
Significance that held at row level collapsed at ticker level and the result
was rejected rather than reported.

**This is what a correctly functioning research gate looks like.** Any
change that makes R3 emit TAKE/AVOID without clearing these gates would
discard exactly this discipline.

---

## 5 · What "completing R3" can and cannot mean

**It cannot mean making R3 emit.** No code change produces validated
evidence, and lowering a gate to raise coverage is the one move the
directive and standing governance both forbid.

Three genuine, separable paths:

### 5a · Supply missing substrate (data acquisition, not code)

| Class | Missing | What would unblock it |
|---|---|---|
| R3-I Intraday | **No intraday bars exist on disk.** `backend/intraday` holds feed/session_clock/signals/execution scaffolding with no price substrate | persisted 1m/5m bars with exchange timestamps; session-aware PIT snapshots; intraday outcome definition with costs |
| R3-F Sector | the `sector` column is not usable as sector information | a real PIT sector mapping with coverage |
| R3-C/D/K | insufficient history depth | **CANON-2** — sealed-snapshot replay from on-disk history |

### 5b · Find a hypothesis that survives the gates (research, no guarantee)

The only live candidate is **`rank_separation`** (added 2026-10-27):
`ensemble_score` separates monotonically across 5 buckets on 29 sealed PIT
snapshots, IC +0.141, positive on 96.6% of dates.

**Not established.** Daily snapshots with a 20-day horizon overlap, so the
naive t=11.1 is inflated ~√20; Newey-West gives ~5.6 and is itself stretched
at n=29/lag=20; the truly non-overlapping sample is 1–3 observations. And
every bucket is negative — ranking information, not profitability.

### 5c · Improve the decision *contract* without changing dispositions

R3 already records, per observation: `evidence_tier`, `OOS_status`,
`PIT_status`, `abstain_probability`, `take_probability`, `avoid_probability`,
`severe_loss_probability`, `survival_probability`, `uncertainty`,
`contributing_specialists`, `known_failure_modes`, `regime_state`,
`sector_state`, `technical_state`, `fundamental_state`, `cluster_state`,
`model_versions`, `prediction_version`, `production_impact`.

That is already a decision record with reason, uncertainty, provenance and
validation status — item 2 of the completion plan is **substantially already
built**. The gap is not the contract; it is that no specialist is authorised
to populate TAKE/AVOID.

---

## 6 · What is genuinely missing (confirmed gaps)

1. **Coverage reporting as a first-class metric.** `action_counts` shows
   abstention totals, but there is no explicit "coverage = non-abstain /
   eligible" series tracked over time, so "abstaining on everything" is not
   currently expressed as a measured property that could fail a gate.
2. **No R3-vs-R2 incremental comparison harness.** R3 observes R2 but there
   is no artifact answering "would following R3's abstentions have beaten
   following R2?" — which, given 100% abstention, is currently the question
   of whether *not trading* beat R2. Given R2's realized −2.51%, that is a
   testable and possibly favourable comparison.
3. **No prospective shadow ledger with fixed horizons.** The ledger records
   decisions and outcomes but not pre-declared 5/10/20-day evaluation
   horizons, which the 90-day design requires.
4. **Persistence.** R3 artifacts are covered by `git add` for
   `reports/research/r3/...`, but the Phase B audit found 99 of 138 pipeline
   artifacts unpersisted; R3's evidence chain inherits that risk.

Items 1–3 are real, safe, research-only engineering. **None requires
touching a disposition or a gate.**

---

## 7 · Governance implications

- R3 remains research-only; `production_impact` is recorded per observation
  and `R3 production writes = 0` is enforced by the run contract's
  DELIVERY_READY gate.
- The 11 dispositions and the PRESERVED rejections must be read forward
  verbatim. `master_status.PRESERVED` is explicitly documented as "never
  recomputed, never softened."
- **No specialist may be promoted** by this or any adjacent work.
- An honest answer to "is R3 complete?" is: **its machinery is complete; its
  evidence is absent, and that absence is itself the finding.**

---

## 8 · Recommended next step

The highest-value R3 work is **gap item 2**: build the R3-vs-R2 incremental
comparison. It is cheap, needs no new substrate, changes no disposition, and
answers a question that is currently unasked —

> R3 abstained on all 1,697 observations. R2's realized mean is −2.51%.
> Did abstaining beat participating?

If yes, R3's *existing* output already has decision value as a veto, with no
new model required. If no, that is also informative.

**Prerequisite:** the Phase B/C persistence repair, so a 90-day R3 evidence
programme does not accumulate into artifacts that are destroyed with each
runner.
