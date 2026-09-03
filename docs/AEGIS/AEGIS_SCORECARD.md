# AEGIS · SCORECARD
_regen `python scripts/aegis_scorecard.py` · 2026-09-03 12:21 UTC · replaces EVIDENCE_LOG + PDF_MATRIX + EXPERIMENT_REGISTRY + 28_REPORTS_

**PRODUCTION = FROZEN.** No R2 change. No push. Per CEO Development Freeze.

## 0 · TL;DR

- Architecture LOCKED · isolation CI green · R1 advisory · R2 sole production · R3 shadow-only
- 4 correct REJECT verdicts preserved (P0 · R3 baseline · NEG-PNL · POS-PNL)
- **Zero PROMOTE-CANDIDATE** · nothing meets promotion criteria
- Pytest 622/0 · xlsx_validator 24 PASS / 0 FAIL / 1 WARN

**PDF completeness ≠ Validation.** The audit hierarchy per CEO 2026-09-03:

```
PDF completeness → Implementation → Data/dependency → Experiment execution
     → Statistical validation → Evidence/gates → Production decision
```

This scorecard reports **Implementation** and **Validation** as SEPARATE columns.
A scaffolded module with a BLOCKED-EVIDENCE gate is ✅ Implementation · ❌ Validation.
A `FAIL` verdict is ✅ Implementation · ✅ Validation-executed · 🔴 result-rejected.

## 1 · Governance

| Item | State | Path |
|---|---|---|
| Controlling contract | V2 master prompt · IMMUTABLE | `docs/AEGIS/MASTER_CONTROLLING_PROMPT_2026-09-03_V2.md` |
| Runner registry | R1=RETIRED_ADVISORY · R2=PRODUCTION · R3=SHADOW_ONLY | `configs/aegis_runner_registry.yaml` |
| Retirement config | R1 retired | `configs/aegis_retirement.yaml` |
| Isolation CI | 9/9 pass | `tests/isolation/` |
| Standards CI | 8/8 pass | `tests/standards/` |
| Composite conviction table | 6/6 pass | `tests/composite/` |
| Signal Silence + MVS + Relaxation | 6/6 pass | `tests/governance/` |
| Enrichers + trial accounting | 10/10 pass | `tests/enrichers/` · `tests/research/` |
| MVS relaxation budget | used 0 · cap 15 · remaining 15 | `reports/research/governance/relaxation_log.jsonl` |

## 2 · Substrate (per market)

| Substrate | India | USA |
|---|---:|---:|
| Outcome Dataset · positions | 68 | 556 |
| Outcome Dataset · non-admin closed | 24 | 500 |
| Phase-0 gate (n≥50) | BLOCKED | PASS |
| Signal Ledger rows | 30 | 45 |
| Signal Ledger snapshots | 3 | 3 |
| PIT Universe rows | 3250 | 33540 |
| PIT Universe unique tickers | 50 | 516 |
| Fundamentals FS rows | 31 | 30 |
| KG PIT snapshots | 7 | 7 |
| R3 shadow ledger picks | — | 5 |
| Paper comparator ticks | 1 | 1 |

## 3 · Research results · Implementation vs Validation

**Implementation** = code exists · tests exist · module runnable.  
**Validation** = experiment executed against real substrate · statistical evidence produced.  
A module can be 🟢 Implementation and still 🟠 Validation if substrate is thin.

| Experiment | Market | Impl | Val | Result | Recommendation |
|---|---|---|---|---|---|
| P0 exit-bridge (k=2,m=3,60d) | INDIA | 🟢 | 🔴 exec | n=20 · Δ=0.750% · p=0.295 · **FAIL** | REJECT these params · run P0-EXTENSION-01 |
| P0 exit-bridge (k=2,m=3,60d) | USA | 🟢 | 🔴 exec | n=479 · Δ=-0.029% · p=0.561 · **FAIL** | REJECT these params · run P0-EXTENSION-01 |
| P1 joint Platt | USA | 🟢 | 🟠 | n=12 · INSUFFICIENT_SAMPLE | RESEARCH FURTHER · needs n≥50 |
| P2 α,β (9 trials) | USA | 🟢 | 🟠 | best (α=0.0, β=0.0) lift=0.000 · BLOCKED (regime features thin) | RESEARCH FURTHER |
| P3 KG γ (5 trials) | USA | 🟢 | 🟠 | n_communities=0 · BLOCKED (KG PIT UNKNOWN) | RESEARCH FURTHER · real KG persistence |
| P4 Cap × Sector LR | USA | 🟢 | 🟠 | n_cells=2 · LR n=0 · BLOCKED (cap/invest incomplete) | RESEARCH FURTHER |
| P5.1-5.5 | USA | 🟢 | 🟠 | 5 subitems scaffolded · sample-limited | P5.5 KEEP · rest RESEARCH FURTHER |
| NEG-PNL-CONTROL-60D | INDIA | 🟢 | 🔴 exec | n=67 · 9 variants all FAIL or null · **REJECT** (correct) | KEEP family · no R2 tightening |
| NEG-PNL-CONTROL-60D | USA | 🟢 | 🔴 exec | n=536 · 9 variants all FAIL or null · **REJECT** (correct) | KEEP family · no R2 tightening |
| POS-PNL-CAPTURE-60D | INDIA | 🟢 | 🔴 exec | n=3050 · 16 winner defs · 100% misses = C_FUNNEL_STAGE · **REJECT loosening** | KEEP family · alt candidate path = NEW ticket |
| POS-PNL-CAPTURE-60D | USA | 🟢 | 🔴 exec | n=31476 · 16 winner defs · 100% misses = C_FUNNEL_STAGE · **REJECT loosening** | KEEP family · alt candidate path = NEW ticket |
| Joint P&L Pareto | USA | 🟢 | 🔴 exec | pareto size=1 (null action) · **REJECT all** | KEEP engine |
| R3 Tier-1 GBM | USA | 🟢 | 🔴 exec | n_train=500 · Brier=0.255 · AUC=0.447 · ECE=0.011 · baseline gap ? > tol · Tier-2 BLOCKED | KEEP gate |
| R1 attribution | INDIA | 🟢 | 🟠 | r1_archive_days=0 · early_warnings=0 · BLOCKED (archive gap) | RESEARCH FURTHER · start R1 daily archive |
| R1 attribution | USA | 🟢 | 🟠 | r1_archive_days=0 · early_warnings=0 · BLOCKED (archive gap) | RESEARCH FURTHER · start R1 daily archive |
| Composite daily loop | INDIA | 🟢 | 🟠 | n_tickers=16 · R3 admitted?=no (trailing_n<50) · shadow only | KEEP as shadow · REJECT sizing promotion |
| Composite daily loop | USA | 🟢 | 🟠 | n_tickers=21 · R3 admitted?=no (trailing_n<50) · shadow only | KEEP as shadow · REJECT sizing promotion |
| R3 Tier-2 · stacking | both | 🟢 | ❌ | BLOCKED-EVIDENCE (R3 shadow <20) | KEEP gate · lifts when Day-30 fires |
| R3 Tier-2 · BMA | both | 🟢 | ❌ | BLOCKED-EVIDENCE | KEEP gate |
| R3 Tier-2 · factor-neutral | both | 🟢 | ❌ | BLOCKED-EVIDENCE | KEEP gate |
| R3 Tier-2 · promoter-governance | india | 🟢 | ❌ | BLOCKED-EVIDENCE + REQUIRES_LIVE_SOURCE (NSE SAST/BSE) | KEEP gate · India-only · NOT_APPLICABLE USA |
| R3 Tier-2 · transcript-tone (Q&A sep) | both | 🟢 | ❌ | BLOCKED-EVIDENCE + transcript ingest missing | KEEP gate |
| R3 Tier-2 · multi-horizon | both | 🟢 | ❌ | BLOCKED-EVIDENCE | KEEP gate |
| R3 Tier-3 · GraphSAGE | both | 🟢 | ❌ | BLOCKED-EVIDENCE (shadow ≥60 + community persistent ≥90d) | KEEP gate |
| R3 Tier-3 · Engle-Granger pairs | both | 🟢 | ❌ | BLOCKED-EVIDENCE + short-sell infra absent | KEEP gate |
| R3 Tier-3 · CUSUM regime | both | 🟢 | ❌ | BLOCKED-EVIDENCE (needs historical transition-date labels) | KEEP gate |
| CRASH_DETECTOR_01 + RECOVERY_DETECTOR_01 | both | 🟢 | 🟢 exec | 0 fires today (no −3σ days in window) · **result preserved** | KEEP · additive to base regime enricher |
| L5 Related-Party + Transcript Tone Q&A-sep | both | 🟢 | ❌ | Modules exist · data sources absent (RPT + transcript ingest) | RESEARCH FURTHER · wire sources |
| L4 India FII/DII + Options PCR shim | india | 🟢 | ❌ | REQUIRES_LIVE_SOURCE marker · adapter placeholder | RESEARCH FURTHER · wire NSE ingest |

## 4 · Forward artifacts

- **R3 shadow ledger:** 5 picks · Day-30 gate fires at ≥20 · `reports/research/r3/shadow_ledger.jsonl`
- **Paper comparator (India):** 1 ticks · `reports/research/paper_comparator/india.jsonl`
- **Paper comparator (USA):** 1 ticks · `reports/research/paper_comparator/usa.jsonl`
- **Sprint M-R forward (pre-Sprint-A · INDIA):** n_obs=62 through 2026-08-27 · `reports/research/mr_forward_validation_india.json`
- **Sprint M-R forward (pre-Sprint-A · USA):** n_obs=546 through 2026-08-27 · `reports/research/mr_forward_validation_usa.json`
- **Sprint M-R narrative:** `reports\research\AEGIS_FORWARD_VALIDATION_REPORT.md` (India −6.48pp · USA +2.69pp through 2026-08-27)

## 5 · R3 Tier-2 / Tier-3 · Research Tickets (V2 §21)

Every ticket = own module + gate + PDF reference. Default BLOCKED-EVIDENCE until R3 shadow satisfies precondition.

| Ticket | Tier | Module | Gate |
|---|---:|---|---|
| R3-T2-STACKING | 2 | `backend.research.r3.tier2.stacking` | R3 shadow ≥20 picks |
| R3-T2-BMA | 2 | `backend.research.r3.tier2.bayesian_averaging` | R3 shadow ≥20 · OOF logloss per model |
| R3-T2-FACTOR-NEUTRAL | 2 | `backend.research.r3.tier2.factor_neutral` | R3 shadow ≥20 · size/value/mom PIT-avail |
| R3-T2-PROMOTER-GOVERNANCE | 2 | `backend.research.r3.tier2.promoter_governance` | India-only · NSE SAST + BSE disclosures wired |
| R3-T2-TRANSCRIPT-TONE | 2 | `backend.research.r3.tier2.transcript_tone` | Q&A SEPARATE per V2 §5 · transcript ingest wired |
| R3-T2-MULTI-HORIZON | 2 | `backend.research.r3.tier2.multi_horizon_consensus` | Per-horizon IC trailing window ≥60 |
| R3-T3-GNN-GRAPHSAGE | 3 | `backend.research.r3.tier3.gnn_graphsage` | R3 shadow ≥60 + community-percentile validated + KG persistent ≥90d |
| R3-T3-PAIR-STATARB | 3 | `backend.research.r3.tier3.pair_stat_arb` | R3 shadow ≥60 + short-selling infra |
| CUSUM_REGIME_SUPPLEMENT | 3 | `backend.research.r3.tier3.cusum_regime` | Regime source present (LANDED) + historical transition-date labels |

**Verdict:** all 9 tickets currently BLOCKED-EVIDENCE per V2 §21 (correct · Tier-2/3 gates on Phase-3 shadow evidence). Scaffolds + tests in place.

## 5b · Regime detectors · CRASH + RECOVERY (V2 §7 additive)

- **INDIA** · touched 0 rows · CRASH=0 · RECOVERY=0 · market_return_days=1615
- **USA** · touched 0 rows · CRASH=0 · RECOVERY=0 · market_return_days=1269

## 5c · Data-source shims (REQUIRES_LIVE_SOURCE)

- **India FII/DII net flow** · `backend/research/fundamentals/providers/india_flow_adapter.py` · NSE FII/DII CSV feed not yet wired
- **India Options PCR** · same adapter · NSE option-chain API not yet wired
- **Related-Party Transactions (India)** + **Transcript Tone (both markets)** · Layer-5 extended module scaffolded · ingest sources pending

## 5d · Additive extensions declared

- **P0-EXTENSION-01** · 60-trial (k×m×horizon) grid · gated on regime enricher (LANDED) · can now run
- **R2-EXT-EXIT-DOCTRINE-01** · chandelier / fixed-% / MFE / regime-aware k · separate research tickets
- **CAP_PIT_STRICT_01** · shares_out(entry_date) × close(entry_date) instead of yfinance current-fallback
- **UNIVERSE_EXT_NIFTY200** · India PIT audit currently uses NIFTY 50 subset
- **MIDCAP400_EXT** · USA S&P MidCap 400 historical membership
- **WINNER_GENOME_FULL** · unblocks after fundamentals PIT accumulation

## 6 · Trial family counts (Deflated Sharpe applies these)

| Family | n_trials |
|---|---:|
| P0-original | 1 (FAIL preserved) |
| P0-EXTENSION-01 (declared) | 60 (5 × 4 × 3) |
| P1 calibration | 1 |
| P2 α,β grid | 9 (3 × 3) |
| P3 γ grid | 5 |
| P4 Cap × Sector LR | 1 |
| P5.1/5.2/5.3 | 5 |
| R3 GBM baseline | 1 |
| NEG-PNL variants | 9 (6 static-pct + 3 timing) |
| POS-PNL winner defs | 16 (4 horizons × 4 thresholds) |
| **Total counted** | **108** |

## 7 · Data freshness

| Data | Newest mtime · days stale |
|---|---|
| India parquet dir | 2026-09-03 · 0d |
| USA parquet dir | 2026-08-27 · 6d |
| India recs_v3 | 2026-09-01 · 1d |
| USA recs_v3 | 2026-09-02 · 0d |
| India regime source | 2026-08-27 · 6d |
| USA regime source | 2026-08-27 · 6d |

## 8 · Rebuild commands (autonomous)

```bash
# Substrate refresh
python scripts/populate_fundamentals_feature_store.py --market india --limit 50 --sleep 1.5
python scripts/populate_fundamentals_feature_store.py --market usa --limit 100 --sleep 1.5
python -m backend.research.signal_ledger.build --market both
python -m backend.research.outcome_dataset.build --market both
python -m backend.research.enrichers.regime --market both
python -m backend.research.enrichers.regime_scores --market both
python -m backend.research.enrichers.cap_and_investability --market both

# All research reruns
python -m backend.research.r2_upgrades.p0_exit_bridge_replay --market both
python -m backend.research.r2_upgrades.p1_calibration_joint --market both
python -m backend.research.r2_upgrades.p2_sector_regime_ranking --market both
python -m backend.research.r2_upgrades.p3_kg_community_scoring --market both
python -m backend.research.r2_upgrades.p4_cap_sector_interaction --market both
python -m backend.research.r2_upgrades.p5_remaining_upgrades --market both
python scripts/neg_pnl_control_60d_run.py --market both
python scripts/pos_pnl_capture_60d_run.py --market both
python -m backend.research.joint_pnl.joint_score --market both
python scripts/r3_daily_shadow_feed.py --market both
python -m backend.recommendation.composite.daily_loop --market both
python -m backend.research.paper_comparator.daily_tick --market both
python -m backend.research.r1_advisory_attribution --market both

# Regenerate THIS scorecard
python scripts/aegis_scorecard.py

# Delivery + tests
python scripts/build_aegis_3sheet_workbook.py --market both --asof 2026-09-03
python -m pytest tests/ -q --ignore=tests/legacy
```

---

**End of scorecard. This file supersedes EVIDENCE_LOG.md · PDF_IMPLEMENTATION_MATRIX.md · EXPERIMENT_REGISTRY.md · FINAL_28_REPORTS.md — deleted per CEO directive.**