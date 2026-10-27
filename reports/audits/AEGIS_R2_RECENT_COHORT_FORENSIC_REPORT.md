# AEGIS R2 — Recent-Cohort Forensic Report
**2026-10-27 · read-only investigation · no production change · nothing promoted**

Baseline verified: branch `main`, HEAD `4dbb96b9f`, `origin/main` `83c7d4d36`
(2 behind — both `aegis-bot` artifact refreshes, **0 code files**), 60 stashes
and 55 untracked files preserved untouched.

---

## 1 · Executive conclusion

**The September–October improvement is not real. The recent cohort is
materially WORSE, and only appears better because of how it was measured.**

Benchmark-matched, per position, over identical entry→exit windows:

| Cohort | n | Trade | NIFTY-matched | **Alpha** | Beat index | Hold |
|---|---|---|---|---|---|---|
| Earlier · entry < 2026-09-27 | 98 | −2.33% | −2.44% | **+0.11%** | 37.8% | 17.7d |
| Recent · entry ≥ 2026-09-27 | 40 | −2.98% | **+0.15%** | **−3.13%** | **12.5%** | 13.1d |

In the earlier, falling market the cohort roughly matched the index. In the
recent, flat market the index was flat and the cohort still lost ~3% —
underperforming on 87.5% of trades.

Three things combined to make that look like an improvement:

1. **Accounting** — a mixed realized+unrealized average compared against a
   realized-only one
2. **Survivorship** — 43 closed losers had already left the visible sheet
3. **Regime** — the market stopped falling, lifting the open marks

**No code changed.** The same R2 implementation was exposed to a different
market and measured inconsistently.

---

## 2 · The four reported figures are NOT comparable

This is the central defect, and it was introduced in the prior session's
analysis — recorded here as a correction rather than quietly fixed.

| Figure | Actual basis | n | Recomputed |
|---|---|---|---|
| −2.49% full period | **realized only** | 145 | −2.51% |
| −3.18% recent closed | **realized only** | 43 | −3.18% |
| +4.39% recent open | **unrealized mark** | 26 | +4.39% |
| −0.33% recent cohort | **MIXED realized + unrealized** | 69 | −0.33% |

The claim "the recent cohort averages −0.33% versus the full-period −2.49%,
a genuine improvement" compared a **mixed** statistic to a **realized-only**
statistic. The −0.33% is better only because 26 open positions marked at
+4.39% were blended into it.

Like-for-like, realized only, one definition throughout:

```
pre-2026-09-27  cohort realized : n=102  mean -2.23%
post-2026-09-27 cohort realized : n= 43  mean -3.18%
full-period     realized        : n=145  mean -2.51%
```

**The recent cohort is 0.95pp worse, not better.**

---

## 3 · Implementation timeline — nothing changed

| Component | Earlier period | Recent period | Change date | Evidence | Effect |
|---|---|---|---|---|---|
| R2 scoring / ranking | unchanged | unchanged | none | 0 commits to `india/recommendation_intelligence/`, `backend/recommendation/` 2026-09-20..10-05 | none |
| Risk engine / sizing | unchanged | unchanged | none | 0 commits to `india/risk_engine/` in window | none |
| Configs | unchanged | unchanged | none | 0 commits to `configs/` in window | none |

Hypotheses A (scoring change), B (entry/eligibility change) and C (exit/stop
change) are **REJECTED on code evidence**: no commit touched those paths in
the window. The improvement cannot be attributed to an implementation change
because there was none.

---

## 4 · Cohort reconciliation

| Set | Count | Basis |
|---|---|---|
| Admitted since 2026-09-27 | **69** | reconciles to reported total |
| — still open | 26 | unrealized mark at 2026-10-27 |
| — closed (REALIZED EXIT) | 43 | realized |
| closed with benchmark-matchable window | 40 | 3 excluded: <2 index bars between entry and exit |

The 3 excluded positions are **reported, not dropped silently**. They are
same-day or next-day exits where the index window is too short to compute a
matched return; they remain in the realized figures (n=43) and are absent
only from the alpha table (n=40).

Note: the full-period realized count is now **145**, not the 143 quoted
earlier — today's run closed 2 more positions. Immaterial to conclusions.

---

## 5 · Why the open positions look green

India, cohort admitted since 2026-09-27:

| | Count | Green | Mean |
|---|---|---|---|
| **Still open — what the sheet shows** | 26 | **73%** | **+4.39%** |
| Already closed — same cohort | 43 | 12% | −3.18% |
| **Whole cohort** | **69** | **35%** | **−0.33%** |

The sheet shows **26 of 69** positions — the 38% that survived. The reds look
small precisely *because* the large ones exit at −3 to −4% and move to EXIT
HISTORY. This is textbook survivorship, and it is a property of the VIEW, not
of the strategy.

---

## 6 · Hypothesis dispositions

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| A | R2 scoring/ranking improved | **REJECTED** | 0 commits in window |
| B | Entry timing / eligibility improved | **REJECTED** | 0 commits in window |
| C | Exit / stop behaviour changed | **REJECTED** | 0 commits in window |
| D | Market regime improved | **CONFIRMED** | NIFTY −6.25% earlier vs −0.78% recent |
| E | Shorter holds / different exposure | **CONFIRMED (minor)** | 17.7d → 13.1d |
| F | Open positions are a survivor subset | **CONFIRMED** | 26 of 69 visible; closed 43 at 12% green |
| G | Fewer extreme losses is an accounting artifact | **CONFIRMED** | mixed vs realized-only basis |
| H | Missing / stale / mismatched snapshots | **PARTIALLY** | see §8 |
| I | Random variation / start date chosen after seeing results | **CANNOT EXCLUDE** | 40 independent-ish trades, start date selected post hoc |

Hypothesis I deserves emphasis: **2026-09-27 was chosen after observing that
recent positions looked green.** Any statistic computed on a window selected
for its appearance is exploratory by construction. The alpha result happens
to be negative, so the bias works against the favourable reading — but the
same bias would have inflated a positive one.

---

## 7 · Selection versus exit attribution

The mechanism is the informative part, and it is the opposite of intuition.

- **Falling market** (earlier): index −2.44% on matched windows, cohort
  −2.33%, alpha **+0.11%**. The stop cut alongside a falling index, so
  relative damage was ~neutral.
- **Flat market** (recent): index **+0.15%**, cohort −2.98%, alpha **−3.13%**,
  beat rate **12.5%**, holds shortened to 13.1d.

Shorter holds plus sharply negative alpha in a flat tape is the signature of
being **whipsawed** — stopped out on noise when there is no trend in either
direction. So the exit mechanic appears **most destructive in a flat market**,
not in a falling one.

This is a hypothesis with supporting evidence, not an established mechanism.
It is testable: measure stop-exit frequency and MAE-before-exit conditioned
on realized index volatility.

Consistent with the prior PIT finding: `ensemble_score` ranks monotonically
across 5 buckets while every bucket loses. Ranking information exists;
profitability does not follow from it.

---

## 8 · Data-quality limitations

1. **No capital weighting.** All figures are equal-weighted per-trade
   percentages. `size` is null on every CURRENT row, exit records carry no
   size, and `reports/portfolio_history.parquet` holds dated weights only to
   2026-09-03. No drawdown, exposure or turnover can be computed.
2. **No transaction costs.** No cost model is applied. All figures are gross.
   With ~13–18 day holds and a −2 to −3% mean, costs would worsen every
   number.
3. **Benchmark matching is close-to-close** on entry+1 → exit, which is not
   an execution model.
4. **3 of 43 closed positions** lack a matchable index window (§4).
5. **Start date selected post hoc** (§6, hypothesis I).
6. **Local snapshot gap recovered**, not reconstructed: India 2026-09-10/11/15,
   10-24, 10-26 restored from `stash@{0}`, validated at 228 rows and 81
   columns against the manifest. Nothing fabricated.

---

## 9 · Confirmed findings versus hypotheses

**Confirmed:**
- the four quoted figures use three different bases and are not comparable
- realized like-for-like, the recent cohort is worse (−3.18% vs −2.23%)
- benchmark-matched alpha collapsed from +0.11% to −3.13%
- no R2 code or config changed in the window
- the market fell far less in the recent window
- the visible sheet is a survivor subset

**Hypothesis, not established:**
- the stop is most destructive in flat markets (§7)
- the alpha difference is attributable to the exit rather than to selection

**Cannot be determined with current data:**
- capital-weighted or cost-adjusted performance
- whether 40 trades across a post-hoc window carry any inferential weight

---

## 10 · Most informative next test

**Condition stop-exit behaviour on realized index volatility.** If the
whipsaw hypothesis holds, stop-exit frequency and give-back should rise as
trend strength falls, independent of direction. That is computable from
existing bars and the sealed snapshots, needs no new strategy, and would
distinguish "the exit is mis-calibrated to regime" from "selection has no
edge" — the two explanations that currently remain live.

**Prerequisite:** restoring portfolio accounting (`portfolio_engine`), without
which no capital-weighted or cost-adjusted statement is possible.

---

## 11 · Reproduction

```
# cohort + comparability
python -W ignore -c "<see §2 block>"   # reads reports/context/canonical_lifecycle_india.json
# benchmark-matched alpha
python -W ignore -c "<see §1 block>"   # + data/raw/india/NSEI_D1.parquet
# code-change check
git log --oneline --since=2026-09-20 --until=2026-10-05 -- \
  india/recommendation_intelligence/ backend/recommendation/ india/risk_engine/ configs/
```

Source artifacts: `reports/context/canonical_lifecycle_india.json` (asof
2026-10-27), `data/raw/india/NSEI_D1.parquet`,
`reports/research/r3/shadow/{ledger,summary}_india.json`.

---

## 12 · R3 status — for the record

R3 is **not** the source of any pick. 1,697 observations across 37 dates,
**all ABSTAIN**: TAKE 0, AVOID 0. `OOS_status: "NOT_APPLICABLE · no model is
emitting"`. `validated_specialists: []`; every specialist sits at
DESCRIPTIVE_ONLY, RESEARCH_ONLY, INSUFFICIENT_SUBSTRATE, NOT_VALIDATED or
NOT_AVAILABLE_AT_ASOF. The ledger records `r2_engine`, `r2_signal` and
`r2_confidence_pct` — it shadows R2 and declines to act.

There is therefore **no R3 candidate to freeze or track**. Any 90-day
prospective programme must be pointed at R2.
