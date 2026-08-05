"""Runner 3 · Institutional-flow-augmented swing engine (SHADOW ONLY).

Opened as Research Ticket `RL-Runner3` on 2026-08-05 per the evidence
triggers documented in `docs/AEGIS_RUNNER3_EXECUTION_PLAN.md`.

HARD CONSTRAINT: this package must NOT import from `adaptive_rec_v2` (R1)
or `backend.recommendation.ssot` (R2) except through public read-only
feature-store contracts. It writes ONLY to `reports/research/runner3/`.
Any breach = ticket violation.
"""
