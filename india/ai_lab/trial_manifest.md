# AI Lab — Cumulative Trial Manifest (Lab-wide)

Every experiment across every Lab folder updates this file BEFORE reporting outcomes. DSR
`n_trials` reads `cumulative_strategy_search` below. The multi-testing burden the DSR corrects
for reflects the FULL search history across all Labs — not a per-Lab local count.

**Counting rule** (Bailey-López de Prado convention):
- **Strategy-search trial** = a distinct hypothesis × parameter × policy combination tested for its
  effect on portfolio outcomes. Increments `cumulative_strategy_search`.
- **Cost-sensitivity variant** = the SAME strategy under different friction assumptions. Robustness
  stress test only. Does NOT increment the count.
- **Baseline / null / control** = the frozen production strategy or a reference (e.g. hold-to-mature,
  or the current dynamic exposure). NOT a new search trial; recorded but not counted.
- **Same-config rerun** (bug fix, scaffold change) = NOT a new search. Recorded with "rerun".

## Cumulative counts

```
cumulative_strategy_search: 32
last_updated: 2026-07-13
```

Arithmetic:
- LAB006 total: 15 (Rule B) + 12 (Rule C provisional) + 0 (Rule C audit rerun, same configs) + 1 (Rule C1) = **28**
- LAB007 new: 4 (candidates A, B, C, D; N0 is control) = **4**
- **Total: 28 + 4 = 32**

## Ledger

### LAB006 — Exit Strategy (closed 2026-07-13)

| Rule | Date | Configs | Category | Count | Outcome |
|---|---|---|---|---|---|
| Baseline (hold-to-mature, 100% invested) | 2026-07-13 | 1 | reference | 0 | — |
| Rule B (vol-spike) | 2026-07-13 | k ∈ {1.6, 1.8, 2.0, 2.5, 3.0} × {P1, P2, P3} | strategy-search | 15 | ALL REJECTED |
| Rule C (trailing stop) | 2026-07-13 | stop ∈ {5, 8, 10, 12}% × {P1, P2, P3} | strategy-search | 12 | ALL REJECTED |
| Rule C cost sensitivity (provisional) | 2026-07-13 | top-3 configs × {30, 50} bps | cost-stress | 0 | (not counted) |
| Rule C audit-closure rerun | 2026-07-13 | same 12 configs, fixed scaffold | rerun | 0 | (not counted; ALL still REJECTED) |
| Rule C1 (regime-gated 5% P3 Weak) | 2026-07-13 | 1 pre-registered strategy | strategy-search | 1 | REJECTED (2/6 gates) |
| Rule C1 cost stress | 2026-07-13 | 1 config × {30, 50} bps | cost-stress | 0 | (not counted) |
| Rule A (score-drop) | forward-collect | — | not-yet-testable | 0 | Deferred to Q1 2027 |
| Rule D (sentiment) | forward-collect | — | not-yet-testable | 0 | Deferred to Q1 2027 |
| **LAB006 subtotal** | — | — | — | **28** | 0 promoted, 0 advisory |

### LAB007 — Dynamic Exposure / Position Sizing (opened 2026-07-13)

| Config | Category | Count | Notes |
|---|---|---|---|
| N0 — production dynamic exposure (control) | reference | 0 | Not a new search trial |
| A — milder India gates (0.75 replaces 0.6, both India gates only) | strategy-search | 1 | Global gates unchanged |
| B — stronger India gates (0.45 replaces 0.6, both India gates only) | strategy-search | 1 | Global gates unchanged |
| C — smooth India-VIX taper (linear 1.0→0.6 across trailing 60th→90th VIX pctile) | strategy-search | 1 | Nifty + all global gates unchanged |
| D — fixed 0.85 constant | strategy-search | 1 | No regime input |
| Cost variants (each candidate × {30, 50} bps) | cost-stress | 0 | (not counted) |
| **LAB007 subtotal (new)** | — | **4** | Sealed pre-registration before execution |

## Correction note (2026-07-13)

Earlier LAB006 C1 report cited n_trials = 30. The actual LAB006 count is 28. The "30" was a
silent fallback default in `exit_lab.py:read_trial_manifest_count()` — the reader's regex
patterns `\(as-of.*?\)` and `\(all-time\)` did not match the amended LAB006 manifest labels
("before C1 run" / "including C1 evaluation"), so the fallback fired without raising.

**Fix in scaffold**: `read_trial_manifest_count()` will be changed to raise `LookupError` on
regex miss, never silent-fallback. Applied before LAB007 executes any candidate.

## Update protocol

1. Every new experiment MUST append its row to the LAB section BEFORE reporting outcomes.
2. Update the `cumulative_strategy_search:` field at the top.
3. Never modify past counts to fit a new hypothesis.
4. If a scaffold change re-runs old configs, mark as "rerun" and count 0.
5. Retracted evidence (e.g. Rule B PBO after audit) does NOT reduce trial count — those searches
   happened; only interpretation changes.
