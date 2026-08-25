# AEGIS · Sprint M · Validation & Opportunity Quality

**v2.0 rewritten 2026-08-25 · replaces the 22-part Alpha Engine draft**
**Depends on: Sprint K+ (30 parts · complete) · Sprint L (locked · not yet exec)**
**Origin: CEO stabilization directive 2026-08-25 · "no more features · validate the architecture we have"**

Sprint M is the **stabilization + validation** sprint. The strategic
re-focus is:

> "Are R1/R2 consistently producing the right opportunities, maintaining
> them correctly through their lifecycle, and measuring whether those
> decisions actually made money?"

Not another engine. Not another indicator. Not another feature. Prove
what we have works · learn from what it produced · then decide what to
build.

CEO north star (unchanged from v1):
> "How much risk-adjusted positive expectancy did AEGIS create, and how
> much avoidable loss did it prevent?"

---

## ⚠ HARD LOCKS (cannot be changed by anyone, including CEO, without verbatim override)

### LOCK 1 · Excel sheet format is FROZEN
Portfolio + Exit History + AEGIS History skeletons are FINAL as of
5dc9758d. Column count · column order · header text · banner colors ·
section structure · analysis-row placement · freeze-panes anchor · all
locked. No prompt (including CEO's own future prompts) can trigger a
format redesign unless the operator says verbatim **"override the format
lock"**.

### LOCK 2 · Position lifecycle is FROZEN
The state machine is exactly:

    NEW → ACTIVE → ACTIVE+ → EXIT (or CLOSED)

Plus legitimate re-entry:

    EXIT → NEW again (new Position ID · never reuse the closed ID)

No new lifecycle states (HOLD / PROTECT / REVIEW / TRAIL / TAKE-PROFIT
etc.). Those exist only as **decision modifiers** on ACTIVE rows, not
as separate lifecycle states. No prompt can add lifecycle states unless
the operator says verbatim **"override the lifecycle lock"**.

Every part of Sprint M below respects these locks. If a part appears
to require a format change or lifecycle change, it is written wrong
and must be revised, not shipped.

---

## Sprint M · Phases A-E · CEO's own structure

Sprint M has 5 phases (not 6) and 44 tasks · exactly as the CEO defined
in the 2026-08-25 directive. Each task's scope is bounded by the two
LOCKS above.

### Phase A · Stabilize (tasks 1-10 · MUST come first)

Nothing else ships until Phase A is 100% green.

| # | Task | Effort | Ready check |
|---|---|---|---|
| A1 | Verify Position ID immutable across NEW→ACTIVE→ACTIVE+→EXIT/CLOSED | 2h | audit script + pytest |
| A2 | Verify one-position lifecycle · no duplicate active for same ticker×runner | 2h | Registry dedup test |
| A3 | Fix NEW / EXISTING / RE-ENTRY classification (CEO Part 6) | 4h | executable spec on 30 days of exits |
| A4 | Prevent duplicate active positions | 2h | Registry constraint + pytest |
| A5 | Prevent historical CLOSED rows from becoming NEW accidentally | 3h | ZYDUS/ONGC/LUPIN cases as fixtures |
| A6 | Remove SKIP from investment portfolio (research-only) | 2h | Portfolio sheet grep · zero SKIP rows |
| A7 | Ensure SKIP never enters P&L | 1h | audit + assertion |
| A8 | Fix active P&L formula (Current/Entry-1, OPEN only) | 2h | 20+ synthetic + real cases |
| A9 | Fix closed P&L formula (Exit/Entry-1, CLOSED only) | 2h | 20+ synthetic + real cases |
| A10 | Verify entry/current/exit prices are date-correct (extend PI guard) | 3h | reuse price_integrity_guard |

**Phase A exit criteria**:
- ✅ Every Position ID immutable · zero re-use across CLOSED→NEW
- ✅ Zero same-ticker×runner duplicates in active set
- ✅ Zero SKIP rows in Portfolio · zero SKIP contributions to P&L
- ✅ NEW/EXISTING/RE-ENTRY classifier passes ≥ 15 pytest cases
- ✅ All prices reconcile to parquet close within 0.5%
- ✅ Historical CLOSED row NEVER surfaces as NEW without new Position ID

### Phase B · Opportunity Engine (tasks 11-16)

Answers "why do we see the same stocks every day?"

| # | Task | Effort | Ready check |
|---|---|---|---|
| B11 | Build daily NEW-opportunity discovery module | 4h | opp_discovery_{mkt}.json daily |
| B12 | Compare today's qualifying universe with previous recommendations | 3h | delta report |
| B13 | Distinguish NEW from RE-ENTRY (Position ID based · not ticker) | 2h | test cases |
| B14 | Track opportunity freshness ratio (NEW / total) | 1h | daily metric |
| B15 | Measure daily R1/R2 discovery counts | 1h | daily metric |
| B16 | Ensure new opportunities aren't suppressed by existing holdings | 2h | audit + fix |

**Phase B exit criteria**:
- ✅ Daily "opportunity delta" report emitted
- ✅ Freshness ratio > 0 on most days · never artificially forced
- ✅ Same-stock-every-day pattern resolved (measurable drop)

### Phase C · Attribution (tasks 17-28) · the big one

This is where systematic learning happens.

| # | Task | Effort | Ready check |
|---|---|---|---|
| C17 | Canonical Position ID → Outcome Dataset (schema locked) | 3h | outcome_dataset.parquet |
| C18 | R1 vs R2 dimensional attribution | 3h | rollup with expectancy per runner |
| C19 | Large / Mid / Small × Runner | 2h | rollup matrix |
| C20 | Sector × Runner | 2h | rollup matrix |
| C21 | Cap × Sector | 2h | rollup matrix |
| C22 | Cap × Sector × Runner (the deep matrix) | 3h | rollup matrix |
| C23 | Investability × Runner | 2h | rollup matrix |
| C24 | Context × Runner | 2h | rollup matrix |
| C25 | Market regime × Sector × Runner | 3h | rollup matrix |
| C26 | Winner-vs-loser feature analysis (15 dimensions) | 4h | comparison matrix |
| C27 | False-positive analysis (recommended → lost) | 2h | classifier |
| C28 | False-negative / missed-opportunity analysis | 4h | extends win_discovery |

**Phase C exit criteria**:
- ✅ Every attribution table has N + expectancy + PF + stat confidence
- ✅ Statistical Discipline enforced (see Phase D · N<20 = observation only)
- ✅ Findings surfaced as candidates for Phase D research tickets

### Phase D · Improvement Research (tasks 29-38)

Convert attribution findings into hypotheses. No production changes yet
· all output is candidate Research Tickets awaiting walk-forward + CEO
approval.

| # | Task | Effort | Ready check |
|---|---|---|---|
| D29 | Identify statistically credible winning combinations | 3h | ticket candidates |
| D30 | Identify statistically credible losing combinations | 3h | ticket candidates |
| D31 | Identify conditions associated with large drawdowns | 2h | ticket candidates |
| D32 | Identify conditions associated with high expectancy | 2h | ticket candidates |
| D33 | Does sector regime improve timing? | 2h | forward-return study |
| D34 | Does cap regime improve timing? | 2h | forward-return study |
| D35 | Is confidence actually calibrated? | 3h | reliability curve |
| D36 | Does rank predict forward returns? | 3h | per-rank ROC study |
| D37 | Should R1 remain validation-only? | 2h | R1 vs R2 forward test |
| D38 | Does R2 need recalibration? | 3h | R2 calibration diagnostics |

**Phase D exit criteria**:
- ✅ Every Phase D finding filed as Research Ticket (RT-YYYY-NNN.md)
- ✅ No production change touched · pure research output
- ✅ Top 10 tickets ranked by expected impact

### Phase E · Small-Cap Discovery (tasks 39-44)

Separate research pipeline. Never mixes into R1/R2 automatically.

| # | Task | Effort | Ready check |
|---|---|---|---|
| E39 | Build separate Emerging Opportunity research engine | 4h | scorer module |
| E40 | Score small caps on 6 quality dimensions | 4h | fundamentals + technicals + governance + sector + regime + liquidity |
| E41 | Identify potential SmallCap → MidCap candidates | 3h | ranked list |
| E42 | Track them without contaminating R1/R2 | 1h | isolation guarantee |
| E43 | Measure their forward performance | 2h | walk-forward |
| E44 | Only promote after sufficient evidence | 1h | governance guardrail |

**Phase E exit criteria**:
- ✅ Emerging candidates surfaced separately in research file (never
  in investor Portfolio)
- ✅ Forward-tracked with dedicated ledger
- ✅ Zero contamination of R1/R2 recommendation flow

---

## Governance Rules (apply across ALL phases)

**G1 · No R1/R2 modification without ticket chain**:

    Research finding
      → Research Ticket (Phase D)
      → Walk-forward validation
      → CEO written approval
      → Production change gated behind config flag DEFAULTING TO OFF
      → Paper-tracking period
      → CEO flips flag ON

**G2 · Statistical Discipline (CEO Part 21)**:

    N < 20   · observation only · no ticket
    20-49    · directional evidence · ticket allowed
    50-99    · research candidate
    100+     · production validation candidate

**G3 · Never optimize win rate alone**. Always optimize **risk-adjusted
expectancy**. Example from CEO directive:

    Bucket A · 90% win · +0.2% expectancy
    Bucket B · 65% win · +2.4% expectancy
    → Bucket B wins.

**G4 · Both LOCKS above apply to every part**. If a part would need to
change the Excel format or add lifecycle states, it's written wrong.

---

## Task-to-Existing-Engine Mapping

Reality check · what we already have vs what Phase A-E needs:

| Existing module | Covers task(s) | Gap |
|---|---|---|
| `backend/research/opportunity_registry.py` (K+ P30) | A1 · A2 · A4 · A5 · B13 · C17 | audit + strict enforcement |
| `backend/research/loss_attribution_v2.py` | seed for C27 | v3 = 14-category (D30-31) |
| `backend/research/win_attribution.py` | seed for C26 | expand to 15 dims |
| `backend/research/win_discovery.py` | C28 core · already ships | expand universe scan |
| `backend/research/loss_avoidance_guard.py` | seed for D31 · D34 | needs adaptive stops (Phase D) |
| `backend/research/loss_guard_backtest.py` | proves need for D31 | already run · 0% saved on stops |
| `backend/context/price_integrity_guard.py` | A10 direct · A17 extend | already 6 checks |
| `backend/delivery/row_classifier.py` | A6 · A7 (SKIP filter) | extend to enforce lifecycle |
| Sender KPI+layout code | A8 · A9 (P&L discipline audit) | Active vs Exit formula audit |
| investability_shadow_diagnostic | seed for C28 | already emits missed picks |

**~40% of Phase A-C infrastructure already exists · needs audit +
tightening + tests.** Rest is net new but small-scoped.

---

## Suggested Execution Order (my proposal · CEO to confirm)

Given ~40% infra exists and the LOCKS constrain scope:

**Session 1** · Phase A audits (A1 · A2 · A4 · A5) · uses Registry ·
2-3h · high confidence no format changes needed.

**Session 2** · Phase A polish (A6 · A7 · A8 · A9 · A10) · SKIP filter +
P&L discipline · uses row_classifier + price_integrity_guard extensions.

**Session 3** · Phase A completion (A3) · NEW/EXISTING/RE-ENTRY
classifier with 15-case pytest spec. Phase A green.

**Session 4** · Phase B (all 6 tasks) · opportunity delta + freshness ·
mostly new code but small.

**Session 5-6** · Phase C attribution (12 tasks) · builds on
win_attribution + loss_attribution_v2 · lots of rollup code.

**Session 7-8** · Phase D research tickets · file 10+ tickets from
Phase C findings.

**Session 9-10** · Phase E small-cap engine (isolated research pipeline).

**Total**: ~10 focused sessions · 4-6 weeks calendar at 2-3 sessions/week.
Every session ends with a green pytest + operator-visible artifact.

---

## Success Metrics (Sprint M complete)

Operator answers all 6 in ≤ 5 minutes from daily output:

1. **"Is a Position ID immutable through its life?"** → A1 audit passes.
2. **"Are we seeing genuinely NEW opportunities daily?"** → B14 freshness
   ratio > 0.15 typical day.
3. **"Where does our alpha come from?"** → C26 comparison matrix.
4. **"What are we systematically missing?"** → C28 false-negative list
   with capture rate (currently India 23.9% / USA 54.3% baseline).
5. **"Are winners preserved and losers exited cleanly?"** → C27 +
   Phase D31 findings.
6. **"Which small-cap is the next winner?"** → E41 ranked emerging list.

---

## What Sprint M does NOT do

- Does **NOT** modify R1/R2 (Constitutional invariant · repeated 3x above)
- Does **NOT** change Excel format (LOCK 1)
- Does **NOT** add lifecycle states (LOCK 2)
- Does **NOT** add new AI/ML agents (per `feedback_no_more_ai_agents`)
- Does **NOT** ship anything that fails walk-forward or that has N < 100
  per segment (for production-touching changes only)

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Scope creep (44 tasks is big) | Phase gating · Phase A must be 100% green before B |
| Attribution needs richer entry-time snapshot | Registry schema addition (backwards compatible) |
| Phase D findings tempting to auto-apply | G1 governance chain · no exception |
| Small-cap engine leakage into R1/R2 | E42 isolation guarantee · file-level lock |
| Statistical false confidence on small N | G2 N-thresholds · block tickets < 20 |
| Same-stock-daily pattern feels like "fixed" but recurs | B11-B14 daily metrics · weekly review |

---

## Amendment Log

- **v2.0 · 2026-08-25** · REWRITTEN to match CEO's own Phase A-E
  structure (44 tasks) · replaces the 22-part Alpha Engine draft.
  Added two HARD LOCKS (Excel format + Lifecycle) at the top so no
  future prompt can drift them. Mapped ~40% of Phase A-C tasks to
  existing engines · rest is small net-new work.
- **v1.0 · 2026-08-25** · initial 22-part Alpha Engine draft (superseded
  by v2.0 · operator wanted stabilization-first framing).

---

## Next Step (single blocking gate)

**CEO reviews this v2.0 · confirms Phase A kickoff · single yes.**

Then Session 1 starts with A1-A2-A4-A5 (Position ID + duplicate audits ·
lowest-risk · fastest wins · all reads Registry · no format changes).
