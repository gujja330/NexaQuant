# AEGIS Governance Rule · Substrate Before Sophistication

**Locked:** 2026-09-04 by CEO
**Governance tier:** STANDING RULE · not one-off correction
**Precedent:** This is the same lesson learned repeatedly · v3.1 institutional-intelligence expansion, 20-folders-vs-20-programs, and now Tier 2/3 R3 techniques ahead of fundamentals substrate. Codified here so it stops being re-argued.

---

## The rule

**No Tier 2/3 R3 technique and no new R2 P-item gets scheduled work while any F0X domain feeding it has not reached a real historical-sample `Tested` stage in the 13-stage Coverage Tracker.**

Mechanical priority ordering. Not a judgment call. Not a debate.

## What "feeding it" means (dependency map)

| Sophistication item | Depends on substrate at Tested stage |
|---|---|
| R3 II.1 Stacking (Tier 2) | F01+F02+F03 (Quality + Balance + Accounting) |
| R3 II.1 GNN (Tier 2/3) | D13 KG communities (mature) + F01 (quality features) |
| R3 II.1 BMA (Tier 2) | Any base-model IC series that exists at Tested |
| R3 II.2 Factor-neutral (Tier 2) | F04 (Valuation) + F05 (Growth) |
| R3 II.4 Governance India (Tier 2) | D11 governance data at Tested |
| R3 II.5 Transcript tone (Tier 2) | D12 narrative-signal data at Tested |
| R2 P3 KG Community-Relative | F01-F05 at Tested + D13 at Tested |
| R2 P4 Cap × Sector | F01-F05 at Tested + realized-outcome dataset at Tested |
| R2 P5.2 Regime-conditional weights | Per-regime IC data at Tested (each regime bucket ≥30 samples) |

## What Tested means

Per 13-stage Coverage Tracker · `Tested` requires:
- Feature computed on real data (both markets)
- Cross-sectional or temporal test executed
- Result JSON emitted under `reports/research/`
- DSR-deflated where multiple variants tested

## Enforcement

- Every research candidate proposal must cite which substrate-items feed it AND their current Coverage-Tracker stage before work is scheduled.
- STP T1 must fail if the candidate depends on a substrate item still at `PIT-ready` or earlier.
- Only exception · candidate is itself a substrate item OR is a data-pipeline unblocker.

## Consequences of violating the rule

Every past violation produced the same failure class:
- Complex technique built on missing substrate → NOT_WORTH verdict after work is sunk
- OR technique passes on partial substrate → false-positive PROMOTE that fails silently at production time

## Concrete implication as of 2026-09-04

- P3, P4, R3 Tier 2/3 · **BLOCKED** by this rule until F01-F05 reaches `Tested` (currently `Populated` for most sub-signals · waiting for accumulator PIT history).
- P1 (Confidence Calibration) · exempt · it operates on delivered R2 confidence numbers, not on unbuilt substrate.
- P2 (Sector/Regime Ranking) · already ran through STP · NOT_WORTH · no follow-up until D06 sub-signals mature.
- P5 items · same rule · check dependency before scheduling.

## P1 exemption · reasoned exception · NOT a template

**Item exempt:** P1 Confidence Calibration on Delivered Output (V2 §P1)

**Basis for exemption:**
- P1's required substrate is **the R2 recommendation pipeline's own delivered output** — a stream of `(raw_confidence, calibrated_confidence, action, forward_outcome)` observations that the production system generates every day it runs.
- That substrate is **already being produced** as a side-effect of R2 running · it is not "unbuilt" · it is not blocked on data acquisition · it is not blocked on external vendors.
- P1's evidence gate (ECE ≤ 0.05 sustained across 4 weekly refits) IS itself an accumulation requirement on that same substrate · this is not an exemption from evidence discipline · it is a different form of evidence discipline.

**What this exemption does NOT establish:**
- It does NOT create a general precedent that any item can proceed if a plausible reason is invented for why its missing data is "different."
- It does NOT exempt any R2 P-item other than P1.
- It does NOT exempt any R3 Tier 2/3 item.
- It does NOT permit "small exploratory versions" of P3, P4, or later P-items.

**Reasoning that must be preserved to grant a similar exemption in the future:**
1. The candidate operates on data that the production system generates as a normal by-product of running.
2. The candidate does NOT depend on any F0X or Dxx sub-signal being at `Tested` stage.
3. The candidate's own evidence gate imposes an accumulation requirement on the same live-production data.
4. Not granting the exemption would freeze work on an item whose substrate is already flowing · which is different from freezing work on an item whose substrate does not exist.

Any future exemption request must state all four conditions explicitly. Absence of any one condition = no exemption.

## Amendment

This rule can only be lifted by verbatim CEO override · "override the substrate-before-sophistication rule". It replaces any prior instruction that scheduled sophistication work while substrate was thin.

---

# Companion Rule · Push Discipline (locked 2026-09-05)

Codified here because this project has already re-litigated "single push at end" twice (once as GAP-3 in the original sprint doc, again in the current session). Same recurrence pattern the substrate rule was built to end.

## The rule

- **Commit locally** after every verified fix. Commits are cheap · they protect work · they cost nothing.
- **Push to origin only on explicit instruction, or at a genuine session boundary** (context/session limit hit · "stopping for now" · session end). Not automatically at the end of every round of fixes.
- Local commits can and should pile up between pushes — three, five, ten logical commits sitting locally unpushed is fine and is what git is for.
- What's being minimized · **how often origin/main changes** and **how often CI runs** · NOT how often work gets checkpointed.

## Exception · time-sensitive changes

If a change is itself time-sensitive · something a live cron run today or another process depends on today · **flag that explicitly and ask** before deciding to hold it. Do not silently batch something that shouldn't wait.

Examples of time-sensitive:
- Fix required for tonight's cron to succeed
- CI-blocking regression that will halt tomorrow's pipeline
- Delivery contract change that must ship before next scheduled Telegram send

Examples of NOT time-sensitive (batch safely):
- Governance/documentation edits
- Research reports · verdicts · analysis artifacts
- Test additions
- Refactors + code hygiene
- New research modules that only run on manual dispatch

## Amendment

Same rule as above · verbatim CEO override "override the push-discipline rule" required to lift.

---

# Companion Rule · Display Results Before Commit (locked 2026-09-05)

## The rule

Before any commit, show actual before/after evidence sized to the change · not a prose description of what was done.

- **Numbers/reconciliation** · explicit old → new format. Precedent: `"WORKED_LEGACY 31→30, REJECTED 7→8"`. Every numeric change held to this standard.
- **Sheet/workbook changes** · the actual new rows or cells rendered from the built workbook. Precedent: the three new 00_Health rows shown as literal Python tuples this round. Never "rows added successfully."
- **Config/registry edits** · the diff of changed lines. Never a prose paraphrase of what changed.
- **Test additions** · the assertion pattern + pass count. Precedent: `"Fri→Mon=1 · Fri→Tue=2 · Fri→Fri=0 · unit-tested"`.

## Sizing rule

Match evidence density to change size · a one-line typo fix needs the one-line diff, not a table · a governance-rule addition needs the new paragraphs literally, not "governance doc updated." Not more, not less.

## Not-a-new-burden clause

This is mostly already happening in the good updates (P0 reclassification numbers, freshness unit-test cases). Making it a standing rule just means it happens every time · including for smaller changes where it's tempting to skip.

## Amendment

Verbatim CEO override "override the display-results rule" required to lift.

---

# Companion Rule · Session-Start Unpushed-Work Tripwire (locked 2026-09-05)

## The rule

**Every session · before any other work · run:**

```
git log --oneline origin/main..HEAD
```

If the output is non-empty · surface the unpushed commit list to the operator immediately · do not proceed with new work until the operator has acknowledged the backlog and decided (push · continue holding · investigate).

## Why this is needed

Under the old "push every round" habit, `origin/main` was always current · there was never a question of what existed only locally. Under the new push-discipline rule (above), local commits can pile up for a while — the intended benefit. But this widens the gap between "committed" and "safe" · one lost laptop / crash / context-limit event with commits sitting unpushed = work exists nowhere else.

## Sizing

One `git log` command · zero seconds if backlog is empty · a single visible surface if not. Cheap. Natural companion to a rule that deliberately widens the committed-vs-safe gap.

## Amendment

Verbatim CEO override "override the session-start tripwire rule" required to lift.

---

# Companion Rule · Session-Boundary Pushes Stay Atomic (locked 2026-09-05)

## The rule

When the eventual push happens at a session boundary or explicit instruction · **push the full linear history as-is** · fast-forward only · **never squash multiple logical fixes into one commit for a "tidier" push**.

Explicitly forbidden without CEO instruction:
- `git rebase -i` to squash local commits before push
- `git commit --amend` on multiple prior commits
- `git reset --soft` + single new commit collapsing local history
- Any "cleanup" commit rewriting that removes distinct commit boundaries

Explicitly permitted:
- `git pull --rebase origin main` to keep linear history against incoming bot commits (this rebases the local commits over new remote work · does NOT squash them)
- Any fast-forward push of N commits as N commits on origin

## Why this is needed

The whole reason S16 mandates one commit per logical fix (in the Sprint A standards) was to keep history reviewable and avoid the rebase-conflict cascades documented in the original git-hygiene incidents. Squashing at push time would silently undo that.

Each local commit is a review boundary · a bisect point · a revert unit. Multiple accumulated local commits are MORE valuable per commit at that granularity than one collapsed super-commit would be, not less. The push does not tidy history · it publishes it.

## Amendment

Verbatim CEO override "override the atomic-push rule" required to lift.
