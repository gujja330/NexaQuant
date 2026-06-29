# The AEGIS Research Handbook

*The constitution of the project. Every experiment — USA or India, now or in two years — follows this. When
in doubt, this document wins. It changes only by deliberate amendment, never to fit a result.*

---

## 1. Philosophy
AEGIS is a **quantitative research platform**, not a model. Its product is **evidence**, not features.

- **Promote evidence, not features.** A dataset added is not progress. A *validated* (or honestly rejected)
  hypothesis is progress.
- **A rejection is a win.** Killing a false lead protects the production baseline and is logged with the same
  weight as a promotion. The platform's credibility comes from what it *refuses* to promote.
- **Honesty over optimism.** Report the unflattering number. "Insufficient power" and "no evidence" are
  valid, valuable verdicts.
- **Production is sacred.** India production is frozen. Research never touches a live baseline; promotion is a
  separate, deliberate, gated step.

## 2. Point-in-time (PIT) — non-negotiable
- Use the timestamp the data was **knowable** (SEC `filed`, announcement, publish), never the period it
  describes. Period-end ≠ availability.
- Reconstruct features **as known at each past rebalance**. If you can't establish when a value became
  public, you cannot use it.
- Universe must be PIT too (no survivorship: include names that later delisted/were removed).

## 3. Leakage prevention (the RC001.2 lesson, mandatory)
A naive walk-forward once showed IC **+0.287**; embargoing overlapping labels collapsed it to **+0.083**.
~70% was leakage. Therefore:
- **Overlap embargo.** If the forward-return window (H days) exceeds the rebalance cadence (C days), adjacent
  dates' labels overlap. ALWAYS (a) drop training rows whose label window overlaps the test date, and
  (b) measure significance (IC-IR) on **non-overlapping dates only** (stride = ceil(H/C)).
- **No feature computed from the future.** Z-scores, ranks, normalizations use only data ≤ as-of date.
- **Persistent features + overlapping labels = memorization.** Watch for it in any ML cycle.
- **Suspiciously high is suspicious.** Real cross-sectional factor ICs are ~0.02–0.06. An IC ≫ 0.1 from a
  simple factor is a leakage alarm until proven otherwise.

## 4. Metrics
- **IC** — Spearman rank corr(signed factor, forward return), per date.
- **IC-IR** — mean IC ÷ std(IC) × √(n non-overlapping dates). The significance measure. **Read IC-IR, not a
  single IC.**
- **Lift** — forward-return percentile of the factor-tilted selection minus the price-only baseline.
- **Effective N** — non-overlapping dates × cross-section. Always report it; it bounds every claim.
- **Confidence** — how much to trust the *verdict* (separate from the verdict itself). Derived from
  non-overlap power + IC stability: **High** = \|IC-IR\| ≥ 2 and effective N ≥ 6 (a result, promote or
  reject, you can lean on); **Medium** = \|IC-IR\| ≥ 1 and N ≥ 6 (directional); **Low** = otherwise (too
  few/unstable). Tells a reader instantly whether "investigate" means *promising* or *can't tell yet*.

## 5. Promotion criteria (ALL must hold)
1. mean IC > **0.03**
2. \|IC-IR\| > **2.0** (on non-overlapping dates)
3. lift > **+0.02** over the price-only baseline
4. **Economic story** — a plausible reason it works (no story → suspect overfit)
5. **Robustness** — survives sector/size/regime slicing (RC001.6/.7 pattern)

Meeting these = **PROMOTE to paper-forward tracking**, never straight into a live baseline. A feature enters
production only after an independent forward paper record and a quarterly-review sign-off.

## 6. Rejection / Investigate criteria
- **REJECT** when criteria fail with adequate power, or the lead is explained away (e.g. a size/regime
  artifact). Rejection is final unless a *new* dataset or hypothesis reopens it.
- **INVESTIGATE** (🟡) when there is a real directional lead but power is insufficient — log it, name the
  specific follow-up, do **not** promote.
- **Frozen-not-rejected** — a knob parked because the current data can't decide; reopen only with new evidence.

## 7. Statistical-significance rules
- Significance comes from **non-overlapping** observations only.
- Beware multiple testing: testing 10 factors will surface one "significant" by chance — favor pre-registered
  hypotheses and require an economic story.
- A null on thin data is **"no evidence,"** not "proven false." Widen power before concluding either way.

## 8. Evidence standards
- Every claim is backed by a re-runnable script and a logged number. No hand-waving.
- Keep the cached PIT panel so results are reproducible without re-fetching.
- Report scope and caveats inline (coverage, history length, effective N).

## 9. The experiment template (every RC)
1. **Question** — one sentence, falsifiable.
2. **Dataset & PIT method** — source, timestamp used, how reconstructed.
3. **Factors / hypothesis** — pre-registered, with expected sign and economic story.
4. **Method** — cadence, horizon, embargo, universe.
5. **Gate thresholds** — the §5 numbers, fixed before running.
6. **Result** — IC / IC-IR / lift / effective N.
7. **Verdict** — PROMOTE / INVESTIGATE / REJECT + why.
8. **Leaderboard row appended.**

## 10. The Leaderboard — single source of truth
- `markets/research/LEADERBOARD.csv` is permanent institutional memory. **Every** experiment appends a row;
  **never overwrite history.** A re-test is a new row, not an edit.
- `RESEARCH_DASHBOARD.md` is the auto-generated executive rollup (`tools/research_dashboard.py`).
- Over hundreds of rows this becomes the knowledge base that stops us re-testing dead ideas.

## 11. Programs & governance
- Work is grouped into **Programs** (Fundamentals, Earnings, Insider, ETF, Macro, News, AI) — see
  `markets/research/RESEARCH_ROADMAP.md`. Finish extracting one program's signal before opening the next.
- The research **framework is locked** (`core/`). Gains come from new hypotheses + evidence, not engine
  rewrites. Touch `core/` only to fix a genuine defect.
- **Quarterly review** (`docs/QUARTERLY_REVIEW.md`) is the only promotion gate: review the dashboard, decide
  promotions/rejections, confirm production stays frozen unless a feature has earned its forward record.

## 12. Cross-market promotion path
The long-term flow — and the only way into production:
```
Research (USA) → Evidence → Validated feature → Shared library
        → Promotion → India Lab → India Production → (Europe / Japan / ...)
```
A signal that works in **both** markets is far stronger evidence than one market alone. That cross-market
lift, not a single backtest, is what earns promotion.

---
*Amendment log: created 2026-06-29 (v1) alongside RC001 close, programs structure, and the Leaderboard/
Dashboard. Amend deliberately; date every change.*
