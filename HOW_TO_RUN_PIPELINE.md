# AEGIS · How to Run the Pipeline

Locked 2026-08-21. One page. Two commands.

---

## Daily runs

```bash
python scripts/run_india.py         # ONLY India · impossible to touch USA
python scripts/run_usa.py           # ONLY USA   · impossible to touch India
```

Both wrappers strip stray `--market` / `--india` / `--usa` / `--both`
flags from the args before invoking the orchestrator, so country cannot
leak through. Each prints a banner at the top:

```
==================================================================
  [INDIA ONLY] USA pipeline WILL NOT run
==================================================================
```

If you see `[BOTH MARKETS]` you called the wrong entrypoint.

---

## Common flags (forwarded to `aegis_run_all.py`)

| Flag | What it does |
|---|---|
| `--skip-refresh` | skip stage 1 (market data refresh) |
| `--skip-regen` | skip stages 2+3 (regenerate recs + SSoT enrichment) |
| `--skip-xlsx` | skip stage 4 (rebuild unified XLSX) |
| `--skip-research` | skip stages 7+8 (P0 outcome + P1 attribution refresh) |
| `--dry-run` | preview Telegram message · do NOT send |
| `--preview-only` | stages 4+5 only · no data mutation · no send |
| `--force-stale` | bypass Guards 5+6 (SEND_FORCE_STALE=1) |
| `--asof YYYY-MM-DD` | date stamp (default: today) |
| `--open-xlsx` | open the XLSX in Excel when done (Windows) |

Examples:

```bash
python scripts/run_india.py                          # full India pipeline
python scripts/run_india.py --dry-run                # preview India, do not send
python scripts/run_india.py --skip-refresh           # rerun without touching market data
python scripts/run_usa.py --preview-only --open-xlsx # USA XLSX only + open in Excel
```

---

## Dual-market run (rare · CI + operator override only)

```bash
python scripts/aegis_run_all.py --market both
```

`aegis_run_all.py` requires `--market` explicitly · running it with no
flag will error out (fixes the 2026-08-21 "bare call defaulted to
both" trap). Prefer `run_india.py` / `run_usa.py` for daily use.

---

## Force a fresh fetch (bypass Part 29 staleness skip)

By default the orchestrator skips ingest steps whose artifacts are still
fresh (within their `staleness_skip_hours` window · see
`configs/opportunity_registry.yaml`). To force a full refetch (news
broke mid-day · schema changed upstream · etc):

```bash
python scripts/aegis_daily_v2.py --force-fresh    # India orchestrator direct
```

The wrappers pass through the flag transparently:

```bash
python scripts/run_india.py --force-fresh
```

---

## Where the output lands

| Path | What |
|---|---|
| `reports/recommendations.json` | India · today's SSoT rec set (all runners collapsed) |
| `usa/reports/recommendations.json` | USA · same schema |
| `reports/telegram/aegis_history_india.xlsx` | India Portfolio + Exit History (90d) + full history |
| `reports/telegram/aegis_history_usa.xlsx` | USA · same three sheets |
| `reports/context/new_opportunity_diagnostic_{market}.json` | NEW funnel + zero-reason narrative |
| `reports/context/rotation_suggestions_{market}.json` | Weakest-existing vs strongest-new pairs |
| `reports/context/daily_ops_diagnostic_{market}.json` | Wave 6 diagnostic + warnings |
| `reports/context/wave_regression_{market}.json` | Wave 7 acceptance-gate verdict |
| `reports/context/new_opp_guard_health_{market}.json` | Strong Guard verdict + attempts + penalty status |
| `reports/context/data_quality_gate_{market}.json` | Part 20 hard gate verdict |
| `reports/context/context_sector_gate_{market}.json` | Parts 10 + 13 gate verdicts |
| `reports/context/dynamic_risk_{market}.json` | Parts 8 + 15 · per-position stop updates |
| `reports/context/rec_review_{market}.json` | Parts 9 + 14 · confidence trajectory + review actions |
| `reports/research/opportunity_registry.jsonl` | Persistent event-sourced Opportunity Registry |

---

## Telegram delivery

Per operator policy 2026-08-18 · Telegram gets ONLY the per-market XLSX
(`aegis_history_india.xlsx` OR `aegis_history_usa.xlsx`). Never the
unified `aegis_history.xlsx`. Never preview / validation reports.

If you want to preview WITHOUT sending: `--dry-run`.

---

## Scheduled CI cadence (GitHub Actions)

| Workflow | Cron | IST |
|---|---|---|
| AEGIS Daily (India) | `30 0/1 * * 1-5` + `0 1/1 * * 1-5` + `30 1 * * 1-5` | 6:00 · 6:30 · 7:00 AM |
| AEGIS USA | `0 12 * * 1-5` + `30 12 * * 1-5` + `0 13 * * 1-5` | 5:30 · 6:00 · 6:30 PM (pre-market) |

Both also run on push to `main` for immediate validation of new commits.

---

## Troubleshooting

**"I ran India but USA showed in output"** → check the banner. If it
says `[BOTH MARKETS]` you called `aegis_run_all.py` without `--market`
(now errors) or with `--market both`. Use `scripts/run_india.py` next
time.

**"Same 15 tickers every day"** → NEW-Opp Strong Guard's held-penalty
fires when ≥ 60% of recs overlap with holdings. Tune in
`configs/opportunity_registry.yaml::new_opp_guard.held_penalty_pp`.

**"Pipeline took 60 min"** → first run of the day. Rerun the same day
hits Lever A cache and finishes in ~5 min. Full 60→15 min first-pass
target needs the remaining 6 ingest modules migrated to `parallel_map`
(only news is done so far).

**"XLSX shows old vocab (BUY/HOLD/PROTECT)"** → CI ran BEFORE the vocab
v5.0 collapse commits landed. Next CI run uses vocab v5.0.
