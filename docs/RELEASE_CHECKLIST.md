# NexaQuant · Release Checklist

**Purpose:** every "release" (any change that gets pushed to `origin/main` and
thereby propagates to the production pipeline via CI) must satisfy this list.

A **release** is any push to `main`, regardless of whether it contains code,
docs, tests, or configuration. Because CI auto-runs the daily pipeline against
`main`, every push IS a release.

---

## 0. Pre-push gate

- [ ] `git status` shows only expected file changes
- [ ] `git diff --stat HEAD` matches the intent of the PR body
- [ ] No `_extract_pdf.py`, `_pdf_text.txt`, or other scratch files staged
- [ ] No `.env*` files staged (verify: `git diff --cached --name-only | grep -i env`)
- [ ] No absolute Windows paths in any staged file
- [ ] `docs/chat_transcript_*.md`, `PUSH_INSTRUCTIONS.md`, LAB007
      `_parity_scratch/` still untracked (these are local-only artefacts)

## 1. Regression gate

- [ ] `python nexaquant/tests/test_regression.py` — 6 suites PASS, 5 invariance guards HOLD
- [ ] `python nexaquant/tests/test_ci_discipline.py` — PASS
- [ ] `python nexaquant/tests/test_governance.py` — PASS

## 2. Sealed-file invariance

- [ ] MON001 fingerprint hash matches `docs/MON001_CERTIFICATION.md`
- [ ] `HOLD = 63`
- [ ] `rebal = 63`
- [ ] `cumulative_strategy_search: 38`
- [ ] `forward_boundary_asof: "2026-03-28"`
- [ ] LAB001–LAB010 artefacts: `git diff HEAD -- india/ai_lab/` returns empty
- [ ] MON001 sealed core files: `git diff HEAD -- <sealed set>` returns empty

## 3. Post-push (within 30 min)

- [ ] `.github/workflows/eng001-regression.yml` → green
- [ ] Next scheduled `.github/workflows/aegis-daily.yml` → green
- [ ] Next scheduled `.github/workflows/mon001-daily.yml` → green
- [ ] Telegram alert on next daily run reflects fresh recommendations (asof
      matches or exceeds previous trading day)

## 4. Rollback plan

- [ ] Commit is trivially revertible via `git revert <sha>`
- [ ] Revert would not itself violate any invariant
- [ ] If migrations are involved (ENG002-style), the wrapper ABI is preserved so
      reverts don't cascade to callers

## 5. Communication

- [ ] Commit message > 3 lines explaining what + why + what NOT touched
- [ ] Any invariance verification results included in commit body
- [ ] Co-author trailer if pair-produced

## 6. Emergency abort

If any of the following occur after push, IMMEDIATELY:

- MON001 CONFIG_DRIFT alert → operator review; do NOT modify strategy
- Daily pipeline fails silently → investigate `logs/`, do not commit fixes
  until root cause understood
- Trial manifest changed unexpectedly → git revert the offending commit

**Never modify production strategy to make a monitoring/CI failure go away.**
