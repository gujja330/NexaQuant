# M-R v1 · Research → Production Decision Table

**Generated:** 2026-08-27
**Locked by:** [MR_V1_LOCK.md](MR_V1_LOCK.md) + [PRODUCTION_LOCK.md](../../PRODUCTION_LOCK.md)
**Rule:** No row below is "Safe to integrate = YES" until it passes the 7-step promotion gate.

---

## Reading key

- **Evidence** · what the M-R engines actually measured
- **Improvement found?** · YES if edge over baseline > 5pp *and* statistically significant
- **Expected impact** · quantified best-case gain if the improvement is validated
- **Safe to integrate?** · NO until walk-forward N ≥ 100 forward predictions + CEO approval + full 7-step gate

---

| Area | Evidence | Improvement found? | Expected impact | Safe to integrate? |
|---|---|---|---|---|
| **R1** | INDIA n=314 · 5D WR 20.81% · avg -0.98% · lower than R2 in India. USA n=80 · 5D WR 54.55% · avg +0.18% · higher than R2 in USA. | **YES · per-market weighting**. R1 needs downweighting in India, upweighting in USA. | Compound-shadow experiment `T5_negative_alpha` targets combined WR lift ≥ 3pp above universe. | **NO** · needs walk-forward validation on N ≥ 100 forward days per market. |
| **R2** | INDIA n=237 · 5D WR 32.16% · avg -0.40% · dominant in winners cohort (54.46%). USA n=1008 · WR 40.88% · avg -0.37%. | **YES · R2 rank_4_7 is India's ONLY positive cohort** (47.37% WR, +0.53% avg). Winning formula `R2 + rank_4_7 + rsi=STRONG` has WR 72.73%, +46.96pp edge. | If R2 rank_4_7 slot is preserved and R1 top-3 slot is filtered, India WR could lift from 25.77% toward baseline 32.25%. | **NO** · needs shadow experiment E2 `top3_rank_inversion` + walk-forward. |
| **Momentum** | **DATA GAP** · n=0 historical snapshots. First forward capture executed 2026-08-27 (INDIA 3 rows, USA 106 rows). | **UNKNOWN** · cannot evaluate until corpus builds. | Not measurable yet. First measurement after ≥ 20 forward trading days. | **NO** · zero evidence. Do NOT remove Momentum · only measure it going forward. |
| **Sectors** | INDIA: Industrials 80% WR n=16 (best) · Energy 0% WR n=14 (worst) · Pharma 15.79%, FMCG 14.29%, Financials 7.14%, Metal 11.11%. USA: sector-flat (S&P 500 uniformly Large-Cap sector-tagged). | **YES · India sector filter candidate** (sub-25% WR sectors: Energy, Financials, Metal, FMCG, Pharma). USA: no useful signal. | India sector filter could remove ~40% of predictions and lift residual WR by an estimated 3-5pp · needs walk-forward to confirm. | **NO** · sector cohorts have n=14-33 · below production-candidate threshold n≥100. |
| **Market cap** | INDIA: LARGE n=459 WR 25.45% · MID n=92 WR 27.42%. USA: LARGE n=459 WR 35.96% · **MID n=622 WR 46.60%, +0.10% avg** (only USA positive-avg cohort). | **YES · USA MID-cap tilt**. USA is currently LARGE-heavy · shifting more weight to MID cap has clear edge. India: no cap edge. | USA MID-cap WR beats LARGE by 10.64pp on n=622+459 · robust sample. | **NO** · needs shadow experiment on universe expansion + walk-forward. |
| **Technicals** | India top predictors (WR spread): rsi_14 25.5pp · confidence 23.88pp (anti-signal) · sector 22.86pp · ma20_dist 19.2pp. USA top: rank_slot 100pp (n=113) · ma20_dist 24.1pp · trend 18pp · vol 17.1pp. India RSI OVERSOLD 43.75% > OVERBOUGHT 14.29%. India `ma20_dist +1..+5` 37.17% WR (best bucket). | **YES · multiple**. RSI-bucket filter, MA20-distance filter, momentum-20d filter all show significant WR spread. Best conditional combo `R2 · rank_4_7 · rsi=STRONG` 72.73% WR n=22. | Adding technical filters to R1 ranker could invert its current negative alpha. Best conditional n=22-31 · directional evidence, not production-candidate. | **NO** · individual buckets are `PRODUCTION_CANDIDATE` but combined filter needs walk-forward. |
| **Fundamentals** | **DATA GAP** · fundamentals parquet has India 228 tickers only · coverage too thin to compute buckets. | **UNKNOWN** · cannot evaluate on current corpus. | Not measurable. | **NO** · zero evidence. Data-fix ticket needed to close parquet coverage gap first. |
| **Stop-loss** | INDIA · CURRENT expectancy -0.886% · TIME_STOP_5D -0.613% (best, +0.273pp) · catastrophic-rate CURRENT 0.20% vs TIME_STOP_5D 0.00%. USA · CURRENT -0.63% expectancy · TRAILING_10 +0.29% (best, +0.921pp). | **YES both markets**. India: TIME_STOP_5D advisory experiment. USA: TRAILING_10 shadow candidate. | India ~0.27% expectancy per trade + zero catastrophic loss. USA ~0.92% expectancy per trade. | **NO** · shadow-advisory experiment E5 registered · walk-forward on N≥100 advisory events required. |
| **AI research** | 9 AI Auditor findings emitted with claim + caveat. F001 CRITICAL India negative alpha. F003 HIGH India confidence anti-signal. F006 HIGH India loss preventability 86.89%. F007 HIGH India capture rate 10.88%. | **N/A · AI is a research analyst not a decision maker** (per feedback_no_more_ai_agents). All findings are hypotheses awaiting evidence. | AI hypotheses become the SOURCE for tickets which become experiments which become validated changes. | **NO · never · by design**. AI can never auto-promote. Every finding routes through the same 7-step gate as human-authored tickets. |

---

## Summary counts

| Verdict | Count |
|---|---:|
| Improvement found? · YES | 6 (R1, R2, Sectors, Market cap, Technicals, Stop-loss) |
| Improvement found? · UNKNOWN (data gap) | 2 (Momentum, Fundamentals) |
| Improvement found? · N/A (governance role) | 1 (AI research) |
| **Safe to integrate now?** | **0 of 9** |

## Path to first production integration

For any row to move from "Safe to integrate = NO" to "YES", every step of the 7-step promotion gate must pass:

1. **Research Ticket accepted by CEO** · 5 DRAFT tickets currently pending review
2. **Walk-forward test on N ≥ 100 forward predictions** · 0/100 today · corpus starts today and accumulates daily
3. **Full regression pass on locked delivery invariants (BLOCK == 0)** · verified today
4. **CEO explicit approval + lock-override phrase** · `override the mr v1 lock` NOT invoked
5. **Config-toggle OFF by default in a new SPRINT_ID branch** · not created
6. **Paper-trading period ≥ 30 sessions with green metrics** · not started
7. **Production promotion under new SPRINT_ID with L4 evidence** · not applicable yet

**Minimum time-to-first-integration:** ~30 trading days (walk-forward + paper trading) from ticket approval.

## Data-gaps blocking full decision

| Gap | Blocking area | Fix ticket |
|---|---|---|
| Momentum n=0 historical | Momentum row | Daily daemon runs (started 2026-08-27) |
| Fundamentals parquet coverage | Fundamentals row | Data-fix ticket · not yet drafted |
| USA canonical portfolio JSON local availability | USA walk-forward | CI generates it · captured on next CI run |
| USA investability shadow file coverage (94% PENDING) | USA band study | Data-fix ticket · not yet drafted |

## What DOES change today

- MR_V1 research foundation is **LOCKED** (measurement layer)
- 5 DRAFT tickets are queued for CEO review
- 5 walk-forward experiments are registered `NOT_STARTED`
- Daily walk-forward daemon captures canonical + Momentum going forward

## What does NOT change today

- No production R1/R2/Registry/XLSX/canonical/ensemble/config edits
- No push touches locked delivery layer
- The old `aegis_history.xlsx` is **preserved as historical evidence** · never deleted or overwritten
- All 30 XLSX validator invariants remain in force
- Every production-facing sender continues to receive the same output as before this research phase
