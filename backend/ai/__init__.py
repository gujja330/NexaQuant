"""AI agents — embedded across every sprint (hybrid architecture).

Each agent reads structured, deterministic engine output and produces
a narrative + evidence + confidence. **Agents do not generate
recommendations, calculations, or scores** — that's the deterministic
engines' job.

**Determinism contract:** Sprint 2 agents are template-driven narrative
generators (same input → same output, no randomness, no LLM API calls,
no clock reads). This makes them replayable for walk-forward validation.
A future upgrade can swap the template engine for an LLM call as long
as the same contract is honored (versioned model, temperature=0, cached
outputs pinned to the freeze date).
"""
