# AEGIS · v2.1.0-RC1 Release Notes

**Release Candidate 1 · 2026-07-18**

Phase 2 development is complete. This is the first release candidate
of the platform for institutional research operator use.

---

## What ships in RC1

**Ten engines · 91 documents · 94 report files · 90+ smoke tests.**

- Research Intelligence Foundation (Global · Sector · Industry · Company · Knowledge Graph v1.6)
- Adaptive Recommendation Engine v2.1 (with Intelligence Fusion)
- Risk & Capital Engine v2.0 (position sizing + risk budget)
- Validation Engine v2.0 (live paper-trading harness)
- DNA Feedback Loop v1.5 (pattern priors)
- Decision Center v1.0 (overnight diff + exit center)
- Executive Dashboard v2.0 (investor-first, 2 pages, realtime)
- Telegram UX030 sender (opt-in, rich messages)
- Daily orchestrator (one-command pipeline)

Full component versions in [VERSION.md](VERSION.md).
Full commit history in [CHANGELOG.md](../CHANGELOG.md).

## Verdict

**READY** — as a research operator's workbench.
**CONDITIONAL** — for institutional multi-tenant deployment (see below).

**Overall production readiness: 8.0/10** — see
[PHASE2_PRODUCTION_AUDIT.md](PHASE2_PRODUCTION_AUDIT.md).

## Success criteria (from PHASE2_MASTER_ROADMAP.md §10)

| Criterion | Status |
|---|:---:|
| Better allocation | ✅ Risk & Capital v2.0 |
| Better capital preservation | ✅ position sizing + risk budget · alerts fire |
| Better calibration | ⚠️ v2.0 signal rebuild lifted Precision@10 +20pp; tier discrimination remains MARGINAL |
| Better validation | ⚠️ paper harness running · 30-day continuous operation still accruing |
| Better expectancy | ⚠️ profit-factor reporting live; 2-quarter validation window not yet observed |
| Better explainability | ✅ full evidence chain per rec · Fusion Why-Buy chip grid · DNA lookups |

3 of 6 solid. 3 partial (all dependent on time, not code).

## Known limitations (all deferred by governance)

- **Confidence signal is a top-K identifier, not a probability** — governance ADR-008 documents this
- **Delivery layer opt-in only** — sealed OPS001 wrapper remains production
- **Single-tenant** — DEV035 governance is Phase 3
- **India-only equity universe** — Multi-Asset engine is Phase 3
- **Batch ingestion only** — real-time is Phase 3
- **Small learning sample (1,060 trades)** — accrues over time; not blocked on code

## Operator quick start

```
# STEP 1  Run pipeline
python scripts/aegis_daily_v2.py

# STEP 2  Send Telegram
python scripts/telegram_send_with_retry.py --attempts 4

# STEP 3  Open dashboard
python ux/dashboard/frontend/serve.py
# then http://127.0.0.1:8765/ux/dashboard/frontend/index.html
```

Full guide in [HOWTO_RUN_AEGIS.md](HOWTO_RUN_AEGIS.md).

## Deployment

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for Docker, systemd,
and Windows Task Scheduler.

## Rollback

- The `main` branch is the release channel.
- Every daily automated commit is tagged `[skip ci]` — you can revert
  any of them safely without re-triggering the pipeline.
- Production tag: `v2.1.0-RC1`.
- To roll back to the last stable Phase 1 baseline (before Phase 2
  engines), reset to commit `0e955b1` (DEV027 + DEV028 Sprint 14).

## Health check

```
python scripts/aegis_health_check.py
```

Prints platform state + reports mtime + orchestrator ledger tail.
Exits 0 if healthy, 1 if any critical artifact is missing or stale.

## What's next (Phase 3 · not required for RC1)

- Live market data + real-time CMP
- Broker integration (advisory-only)
- Multi-asset (ETF / gold / debt / FX)
- Mobile / PWA experience
- Multi-tenant + enterprise governance
- Cloud deployment (multi-region)

None of these are blockers on the current release. All are new
capabilities, not gap-fills.

## Governance stack (for the record)

- [NEXAQUANT_MANIFESTO.md](NEXAQUANT_MANIFESTO.md)
- [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) — 14 ADRs
- [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) — constitution
- [PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md) — delivery contract
- [AEGIS_RESEARCH_AGENDA_2035.md](AEGIS_RESEARCH_AGENDA_2035.md) — long-horizon backlog

## Signing off

Every metric in this release is drawn from live `reports/*` artifacts.
No number is invented. Advisory-only per ADR-002. Fingerprint
`e4c070673568c52d…` unchanged.

**Recommended action:** tag `v2.1.0-RC1` on `main` and proceed to
production deployment via [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).
