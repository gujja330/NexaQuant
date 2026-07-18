# AEGIS · Version Manifest

**Platform version:** `v2.1.0-RC1`
**Release candidate date:** 2026-07-18
**Architecture:** LOCKED (see [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md))

## Engine versions

| Engine | Version | Last major change |
|---|---|---|
| Research Foundation (Global · Sector · Industry · Company) | v1.5 | DEV017-DEV020 · unchanged since Phase 1 |
| Adaptive Recommendation Engine | **v2.1** | v2.1 Intelligence Fusion (this release) |
| Risk & Capital Engine | **v2.0** | v2.0 position sizing + risk budget |
| Validation Engine | **v2.0** | v2.0 live paper-trading harness |
| Knowledge Graph (Foundation extension) | **v1.6** | v1.6 stress propagation |
| Decision Center | **v1.0** | new · overnight diff + exit center |
| Delivery Layer · Telegram (sealed) | v1.0 | OPS001 baseline |
| Delivery Layer · Telegram (UX030 opt-in) | **v1.1** | new rich renderer |
| Delivery Layer · Executive Dashboard | **v2.0** | investor-first rewrite |

## Constitution

- [NEXAQUANT_MANIFESTO.md](NEXAQUANT_MANIFESTO.md) — mission
- [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) — 14 ADRs
- [ENGINE_EVOLUTION_GUIDE.md](ENGINE_EVOLUTION_GUIDE.md) — architecture
- [PHASE2_MASTER_ROADMAP.md](PHASE2_MASTER_ROADMAP.md) — delivery contract
- [AEGIS_RESEARCH_AGENDA_2035.md](AEGIS_RESEARCH_AGENDA_2035.md) — long-horizon backlog

## Runtime

- Python 3.12
- Dependencies: `requirements.txt`, `requirements-dashboard.txt`
- Fingerprint (MON001 baseline): `e4c070673568c52d…` — INVARIANT since Phase 1

## Semver policy

- `MAJOR.MINOR.PATCH-QUAL`
- `MAJOR` — breaking change to a JSON contract or governance policy
- `MINOR` — new engine version bump within an existing engine
- `PATCH` — bug fix or non-functional improvement
- `QUAL` — RC / beta / stable qualifier

`v2.1.0-RC1` = major 2 (Phase 2 · post-locked architecture) · minor 1
(Intelligence Fusion) · patch 0 · RC1 (first release candidate).
