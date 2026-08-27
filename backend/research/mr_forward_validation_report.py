"""AEGIS · Sprint M-R · AEGIS_FORWARD_VALIDATION_REPORT.

Assembles the CEO's exact 18-section master research report from every
M-R engine output. This is the SINGLE research control center.

Sections:
   1. Executive summary
   2. R1
   3. R2
   4. Momentum
   5. Sector
   6. Market cap
   7. Winners
   8. Losers
   9. Stop-loss
  10. MFE / MAE
  11. Technical factors
  12. Fundamental factors
  13. Quality / Investability / Urgency validation
  14. Regime analysis
  15. Failure patterns
  16. Candidate improvements
  17. Out-of-sample validation
  18. Recommendations for production

Emits reports/research/AEGIS_FORWARD_VALIDATION_REPORT.md.
Under M-R sandbox rules. No production changes.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean

from backend.research.mr_runner import ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_forward_validation_report.v1.0"


def _load(root: Path, name: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _load_jsonl(root: Path, name: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _fmt(v, digits=2, suffix=""):
    if v is None: return "—"
    if isinstance(v, (int,float)): return f"{v:.{digits}f}{suffix}"
    return str(v)


def _panel_row(k: str, panel: dict) -> str:
    m5 = panel.get("fwd_5d", {}) if isinstance(panel, dict) else {}
    if not m5.get("n"): return ""
    m10 = panel.get("fwd_10d", {})
    return (f"| {k} | {panel.get('n',0)} | {m5['wr_pct']}% | {m5['avg_pct']:+}% | "
            f"{_fmt(m10.get('avg_pct'),2,'%')} | {_fmt(panel.get('avg_mfe_pct'),3,'%')} | "
            f"{_fmt(panel.get('avg_mae_pct'),3,'%')} | {_fmt(panel.get('stop_hit_rate_pct'),2,'%')} |")


def build(root: Path) -> str:
    autopsy_i = _load(root, "mr_prediction_autopsy_india_summary.json")
    autopsy_u = _load(root, "mr_prediction_autopsy_usa_summary.json")
    autopsy_rows_i = _load_jsonl(root, "mr_prediction_autopsy_india.jsonl")
    autopsy_rows_u = _load_jsonl(root, "mr_prediction_autopsy_usa.jsonl")
    studies_i = _load(root, "mr_studies_india.json")
    studies_u = _load(root, "mr_studies_usa.json")
    stops_i = _load(root, "mr_stop_loss_sweep_india.json")
    stops_u = _load(root, "mr_stop_loss_sweep_usa.json")
    lp_i = _load(root, "mr_loss_prevention_india.json")
    lp_u = _load(root, "mr_loss_prevention_usa.json")
    ctrl_i = _load(root, "mr_control_cohort_india.json")
    ctrl_u = _load(root, "mr_control_cohort_usa.json")
    missed_i = _load(root, "mr_missed_winners_india.json")
    missed_u = _load(root, "mr_missed_winners_usa.json")
    regime_i = _load(root, "mr_market_regime_india.json")
    regime_u = _load(root, "mr_market_regime_usa.json")
    rank_i = _load(root, "mr_feature_ranking_india.json")
    rank_u = _load(root, "mr_feature_ranking_usa.json")
    score_i = _load(root, "mr_score_usefulness_india.json")
    score_u = _load(root, "mr_score_usefulness_usa.json")
    genome_i = _load(root, "mr_winner_loser_genome_india.json")
    genome_u = _load(root, "mr_winner_loser_genome_usa.json")
    tickets_idx = _load(root, "tickets/INDEX.json")
    experiments_idx = _load(root, "experiments/INDEX.json")
    shortlist = _load(root, "mr_hypothesis_shortlist.json")

    # Walk-forward days already captured
    wf_dir = root / ALLOWED_WRITE_ROOT / "walkforward"
    wf_days = sorted([p.name for p in wf_dir.iterdir() if p.is_dir()]) if wf_dir.exists() else []

    L = []
    L.append(f"# AEGIS_FORWARD_VALIDATION_REPORT\n")
    L.append(f"_Sprint M-R · Forward Validation Engine v1 · sandbox_\n")
    L.append(f"**Generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}  ")
    L.append(f"**Engine:** `{ENGINE_ID}`  ")
    L.append(f"**Status:** FOUNDATION COMPLETE · INTEGRATION DEFERRED  ")
    L.append(f"**Locked layers:** UNTOUCHED · zero production changes.\n\n---\n")

    # 1. Executive summary
    L.append(f"## 1 · Executive summary\n")
    L.append(f"| | INDIA | USA |")
    L.append(f"|---|---:|---:|")
    L.append(f"| Predictions ingested | {autopsy_i.get('n_predictions','—')} | {autopsy_u.get('n_predictions','—')} |")
    for hz in ("fwd_1d","fwd_5d","fwd_10d","fwd_20d"):
        ai = (autopsy_i.get("cohort_ALL",{}) or {}).get(hz, {})
        au = (autopsy_u.get("cohort_ALL",{}) or {}).get(hz, {})
        L.append(f"| {hz} WR | {_fmt(ai.get('win_rate_pct'),2,'%')} | {_fmt(au.get('win_rate_pct'),2,'%')} |")
        L.append(f"| {hz} avg | {_fmt(ai.get('avg_pct'),3,'%')} | {_fmt(au.get('avg_pct'),3,'%')} |")
    # Alpha
    ui = (ctrl_i.get("aggregate",{}) or {}).get("fwd_5d",{})
    uu = (ctrl_u.get("aggregate",{}) or {}).get("fwd_5d",{})
    ai5 = (autopsy_i.get("cohort_ALL",{}) or {}).get("fwd_5d",{})
    au5 = (autopsy_u.get("cohort_ALL",{}) or {}).get("fwd_5d",{})
    if ui.get("n") and ai5.get("n"):
        alpha_i = round(ai5["win_rate_pct"] - ui["wr_pct"], 2)
    else: alpha_i = None
    if uu.get("n") and au5.get("n"):
        alpha_u = round(au5["win_rate_pct"] - uu["wr_pct"], 2)
    else: alpha_u = None
    L.append(f"| Universe-baseline 5D WR | {_fmt(ui.get('wr_pct'),2,'%')} | {_fmt(uu.get('wr_pct'),2,'%')} |")
    L.append(f"| **AEGIS alpha (5D WR)** | **{_fmt(alpha_i,2,'pp')}** | **{_fmt(alpha_u,2,'pp')}** |")
    L.append(f"\n**Headline:** ")
    if alpha_i is not None and alpha_i < 0:
        L.append(f"India AEGIS is currently **BELOW** random-universe baseline "
                 f"({alpha_i}pp). ")
    if alpha_u is not None and alpha_u > 0:
        L.append(f"USA AEGIS is **ABOVE** baseline (+{alpha_u}pp, small positive edge).\n")

    # 2. R1
    L.append(f"\n---\n\n## 2 · R1 Runner\n")
    for mk, s in (("INDIA", studies_i), ("USA", studies_u)):
        r1 = (s.get("Q1_runner_scoreboard") or {}).get("R1")
        if not r1: continue
        L.append(f"\n### {mk} · R1")
        L.append(f"| Bucket | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |")
        L.append(f"|---|---:|---:|---:|---:|---:|---:|---:|")
        row = _panel_row("R1", r1)
        if row: L.append(row)

    # 3. R2
    L.append(f"\n---\n\n## 3 · R2 Runner\n")
    for mk, s in (("INDIA", studies_i), ("USA", studies_u)):
        r2 = (s.get("Q1_runner_scoreboard") or {}).get("R2")
        if not r2: continue
        L.append(f"\n### {mk} · R2")
        L.append(f"| Bucket | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |")
        L.append(f"|---|---:|---:|---:|---:|---:|---:|---:|")
        row = _panel_row("R2", r2)
        if row: L.append(row)

    # 4. Momentum
    L.append(f"\n---\n\n## 4 · Momentum\n")
    mom_i = (studies_i.get("Q1_runner_scoreboard") or {}).get("MOMENTUM")
    mom_u = (studies_u.get("Q1_runner_scoreboard") or {}).get("MOMENTUM")
    if not mom_i and not mom_u:
        L.append(f"**DATA GAP:** No historical Momentum snapshots exist. Momentum "
                 f"recommendations were not captured into `aegis_history.xlsx` "
                 f"beyond the current-day feed. Walk-forward capture starts "
                 f"today · `python -m backend.research.mr_walkforward_snapshot "
                 f"--snapshot --market both` needs to run daily from now on to "
                 f"build the corpus. First actionable measurement expected after "
                 f"20 trading days.")

    # 5. Sector
    L.append(f"\n---\n\n## 5 · Sector analysis\n")
    for mk, s in (("INDIA", studies_i), ("USA", studies_u)):
        panels = s.get("Q2_sector") or {}
        if not panels: continue
        L.append(f"\n### {mk}")
        L.append(f"| Sector | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |")
        L.append(f"|---|---:|---:|---:|---:|---:|---:|---:|")
        sorted_panels = sorted(panels.items(),
                               key=lambda kv: -((kv[1].get("fwd_5d",{}) or {}).get("wr_pct") or 0))
        for k, panel in sorted_panels:
            row = _panel_row(k, panel)
            if row: L.append(row)

    # 6. Market cap
    L.append(f"\n---\n\n## 6 · Market cap\n")
    for mk, s in (("INDIA", studies_i), ("USA", studies_u)):
        panels = s.get("Q3_cap_bucket") or {}
        if not panels: continue
        L.append(f"\n### {mk}")
        L.append(f"| Cap | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |")
        L.append(f"|---|---:|---:|---:|---:|---:|---:|---:|")
        for k in ("LARGE","MID","SMALL","UNKNOWN"):
            panel = panels.get(k)
            if not panel: continue
            row = _panel_row(k, panel)
            if row: L.append(row)

    # 7. Winners
    L.append(f"\n---\n\n## 7 · Winners (fwd_5d > +0.5%)\n")
    for mk, g in (("INDIA", genome_i), ("USA", genome_u)):
        w = (g.get("genome",{}) or {}).get("cohort_WINNER",{})
        if not w.get("n"): continue
        L.append(f"\n### {mk} · n={w['n']}")
        wc = w.get("confidence_stats", {}) or {}
        L.append(f"- Runner mix: `{w.get('runners')}`")
        L.append(f"- Band mix: `{w.get('bands')}`")
        L.append(f"- Confidence avg: {_fmt(wc.get('avg'),2,'%')}  (range {wc.get('min')}-{wc.get('max')})")
        L.append(f"- Avg MFE: {_fmt(w.get('mfe_pct_avg'),3,'%')}  ·  Avg MAE: {_fmt(w.get('mae_pct_avg'),3,'%')}")
        L.append(f"- Stop-hit rate: {_fmt(w.get('stop_hit_rate_pct'),2,'%')}")

    # 8. Losers
    L.append(f"\n---\n\n## 8 · Losers (fwd_5d < -0.5%)\n")
    for mk, g, lp in (("INDIA", genome_i, lp_i), ("USA", genome_u, lp_u)):
        l = (g.get("genome",{}) or {}).get("cohort_LOSER",{})
        if not l.get("n"): continue
        L.append(f"\n### {mk} · n={l['n']}")
        lc = l.get("confidence_stats", {}) or {}
        L.append(f"- Runner mix: `{l.get('runners')}`")
        L.append(f"- Band mix: `{l.get('bands')}`")
        L.append(f"- Confidence avg: {_fmt(lc.get('avg'),2,'%')}  (range {lc.get('min')}-{lc.get('max')})")
        L.append(f"- Avg MFE: {_fmt(l.get('mfe_pct_avg'),3,'%')}  ·  Avg MAE: {_fmt(l.get('mae_pct_avg'),3,'%')}")
        L.append(f"- Stop-hit rate: {_fmt(l.get('stop_hit_rate_pct'),2,'%')}")
        L.append(f"- Loss rate: {_fmt(lp.get('loss_rate_pct'),2,'%')}  ·  Preventable: {_fmt(lp.get('preventable_pct'),2,'%')}")
        L.append(f"- Classification: `{lp.get('by_classification')}`")

    # 9. Stop-loss
    L.append(f"\n---\n\n## 9 · Stop-loss policy sweep\n")
    for mk, s in (("INDIA", stops_i), ("USA", stops_u)):
        by_pol = s.get("by_policy") or {}
        if not by_pol: continue
        L.append(f"\n### {mk}")
        L.append(f"| Policy | n | WR | avg% | median% | PF | stop-hit% | cat>10%% | worst% | days |")
        L.append(f"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for pol, m in by_pol.items():
            if not m.get("n"): continue
            L.append(f"| {pol} | {m['n']} | {m['wr_pct']}% | {m['avg_pct']:+} | "
                     f"{m['median_pct']:+} | {_fmt(m.get('profit_factor'))} | "
                     f"{m['stop_hit_rate_pct']} | {m['catastrophic_gt10pct_pct']} | "
                     f"{m['worst_pct']:+} | {_fmt(m.get('avg_days_held'))} |")

    # 10. MFE / MAE
    L.append(f"\n---\n\n## 10 · MFE / MAE distribution\n")
    for mk, a in (("INDIA", autopsy_i), ("USA", autopsy_u)):
        cohort = a.get("cohort_ALL", {}) or {}
        L.append(f"\n### {mk}")
        L.append(f"- Avg MFE: **{_fmt(cohort.get('avg_mfe_pct'),3,'%')}**")
        L.append(f"- Avg MAE: **{_fmt(cohort.get('avg_mae_pct'),3,'%')}**")
        L.append(f"- Stop-hit rate: {_fmt(cohort.get('stop_hit_rate_pct'),2,'%')}")
        if cohort.get('avg_mae_pct') is not None and cohort.get('avg_mfe_pct') is not None:
            reward_risk = round(cohort['avg_mfe_pct'] / abs(cohort['avg_mae_pct']), 2) \
                          if cohort['avg_mae_pct'] else None
            L.append(f"- Reward:risk (MFE/|MAE|): **{reward_risk}**")

    # 11. Technical factors
    L.append(f"\n---\n\n## 11 · Technical factors\n")
    for mk, s in (("INDIA", studies_i), ("USA", studies_u)):
        L.append(f"\n### {mk}")
        for sub in ("rsi_bucket","trend","vol_bucket","ma20_dist_bucket","momentum_20d_bucket"):
            panels = (s.get("Q4_technicals") or {}).get(sub) or {}
            if not panels: continue
            L.append(f"\n**{sub}**")
            L.append(f"| Bucket | n | 5D WR | 5D avg |")
            L.append(f"|---|---:|---:|---:|")
            for k, p in panels.items():
                m = p.get("fwd_5d", {})
                if not m.get("n"): continue
                L.append(f"| {k} | {p['n']} | {m['wr_pct']}% | {m['avg_pct']:+}% |")

    # 12. Fundamental factors
    L.append(f"\n---\n\n## 12 · Fundamental factors\n")
    for mk, s in (("INDIA", studies_i), ("USA", studies_u)):
        panels_any = False
        for sub in ("roe_bucket","pe_bucket","quality_bucket"):
            panels = (s.get("Q5_fundamentals") or {}).get(sub) or {}
            for k, p in panels.items():
                if p.get("fwd_5d",{}).get("n"): panels_any = True; break
            if panels_any: break
        if not panels_any:
            L.append(f"\n### {mk}\n_(fundamentals parquet coverage gap · no bucket qualifies)_")
            continue
        L.append(f"\n### {mk}")
        for sub in ("roe_bucket","pe_bucket","quality_bucket"):
            panels = (s.get("Q5_fundamentals") or {}).get(sub) or {}
            if not any(p.get("fwd_5d",{}).get("n") for p in panels.values()): continue
            L.append(f"\n**{sub}**")
            L.append(f"| Bucket | n | 5D WR | 5D avg |")
            L.append(f"|---|---:|---:|---:|")
            for k, p in panels.items():
                m = p.get("fwd_5d", {})
                if not m.get("n"): continue
                L.append(f"| {k} | {p['n']} | {m['wr_pct']}% | {m['avg_pct']:+}% |")

    # 13. Quality / Investability / Urgency validation
    L.append(f"\n---\n\n## 13 · Quality / Investability / Urgency validation\n")
    for mk, sc in (("INDIA", score_i), ("USA", score_u)):
        L.append(f"\n### {mk}")
        L.append(f"| Score | expected | actual | WR spread | **VERDICT** |")
        L.append(f"|---|---|---|---:|---|")
        for name, a in (sc.get("audits") or {}).items():
            L.append(f"| {name} | {a['expected_direction']} | {a['monotonicity']} | "
                     f"{_fmt(a.get('wr_spread_pp'),2,'pp')} | **{a['verdict']}** |")
        # Bucket detail
        for name, a in (sc.get("audits") or {}).items():
            buckets_with_n = {k: v for k, v in a.get("buckets",{}).items() if v.get("n")}
            if not buckets_with_n: continue
            L.append(f"\n**{mk} · {name} bucket detail:**\n")
            L.append(f"| Bucket | n | 5D WR | 5D avg | 10D WR | 10D avg |")
            L.append(f"|---|---:|---:|---:|---:|---:|")
            for k, v in buckets_with_n.items():
                L.append(f"| {k} | {v['n']} | {_fmt(v.get('wr_5d'),2,'%')} | "
                         f"{_fmt(v.get('avg_5d'),3,'%')} | {_fmt(v.get('wr_10d'),2,'%')} | "
                         f"{_fmt(v.get('avg_10d'),3,'%')} |")

    # 14. Regime analysis
    L.append(f"\n---\n\n## 14 · Regime analysis\n")
    for mk, s, r in (("INDIA", studies_i, regime_i), ("USA", studies_u, regime_u)):
        panels = s.get("Q6_regime") or {}
        if not panels: continue
        L.append(f"\n### {mk}")
        L.append(f"- Regime distribution across window: `{r.get('regime_distribution')}`\n")
        L.append(f"| Regime | n | 5D WR | 5D avg | 10D avg | MFE | MAE | stop-hit |")
        L.append(f"|---|---:|---:|---:|---:|---:|---:|---:|")
        for k, p in panels.items():
            row = _panel_row(k, p)
            if row: L.append(row)

    # 15. Failure patterns
    L.append(f"\n---\n\n## 15 · Failure patterns (anti-signals at entry)\n")
    for mk, lp in (("INDIA", lp_i), ("USA", lp_u)):
        anti = lp.get("top_anti_signals") or {}
        if not anti: continue
        L.append(f"\n### {mk} · n_losses={lp.get('n_losses')}")
        L.append(f"| Anti-signal at entry | count |")
        L.append(f"|---|---:|")
        for k, v in list(anti.items())[:15]:
            L.append(f"| {k} | {v} |")

    # 16. Candidate improvements
    L.append(f"\n---\n\n## 16 · Candidate improvements (DRAFT tickets · never auto-applied)\n")
    if shortlist and shortlist.get("shortlist"):
        L.append(f"\nTop {shortlist['top_n']} candidates ranked by "
                 f"severity×3 + verdict×2 + evidence×1 + preventability×2:\n")
        L.append(f"| Rank | Score | Market | Severity | Verdict | n_evid | Title |")
        L.append(f"|---:|---:|---|---|---|---:|---|")
        for r in shortlist["shortlist"]:
            L.append(f"| {r['rank']} | {r['score']} | {r['market']} | {r['severity']} | "
                     f"{r['verdict']} | {r['n_evidence']} | {r['title']} |")

    # 17. Out-of-sample validation
    L.append(f"\n---\n\n## 17 · Out-of-sample validation\n")
    if wf_days:
        L.append(f"\n**Forward-captured days so far:** {len(wf_days)}\n")
        for d in wf_days:
            L.append(f"- `{d}` ")
            d_dir = wf_dir / d
            for p in sorted(d_dir.glob("*.jsonl")):
                rows = _load_jsonl(root, f"walkforward/{d}/{p.name}")
                L.append(f"  - `{p.name}` · n_predictions={len(rows)}")
    if experiments_idx and experiments_idx.get("experiments"):
        L.append(f"\n**Registered walk-forward experiments (from candidate improvements):**\n")
        L.append(f"| Experiment | Metric | Min N | Window | Status |")
        L.append(f"|---|---|---:|---:|---|")
        for e in experiments_idx["experiments"]:
            L.append(f"| `{e['experiment_id']}` | {e['metric']} | {e['min_sample_size']} | "
                     f"{e['observation_window_days']}d | **{e['current_status']}** |")
    if len(wf_days) < 20:
        L.append(f"\n**Status:** IN_PROGRESS · walk-forward corpus needs "
                 f"≥20 trading days before any experiment can conclude. "
                 f"Daily snapshot capture must run from today forward. "
                 f"Every experiment stays `NOT_STARTED` until CEO enables it.")

    # 18. Recommendations for production
    L.append(f"\n---\n\n## 18 · Recommendations for production\n")
    L.append(f"\n**Current recommendation:** *No production changes.*\n")
    L.append(f"\nEvery candidate improvement from §16 is `status: DRAFT`. Every "
             f"walk-forward experiment from §17 is `status: NOT_STARTED`. The 7-step "
             f"promotion gate applies verbatim to each:\n")
    gate = [
        "1. Research Ticket accepted by CEO",
        "2. Walk-forward test on N ≥ 100 forward predictions",
        "3. Full regression pass on locked delivery invariants (BLOCK == 0)",
        "4. CEO explicit approval + lock-override phrase",
        "5. Config-toggle OFF by default in a new SPRINT_ID branch",
        "6. Paper-trading period ≥ 30 sessions with green metrics",
        "7. Production promotion under new SPRINT_ID with L4 evidence",
    ]
    for step in gate:
        L.append(f"- {step}")
    L.append(f"\n**Locked layers · verbatim untouched:** R1 runner, R2 runner, "
             f"Registry, `backend/delivery/xlsx_contract.py`, "
             f"`backend/delivery/xlsx_validator.py`, "
             f"`scripts/telegram_command_center_send.py` canonical JSON emit, "
             f"`configs/ensemble_weights_adaptive.yaml`, `model_registry.jsonl`.\n")
    L.append(f"\n**Data gaps to close before promotion:**\n"
             f"- Momentum historical snapshots (start forward capture now)\n"
             f"- USA investability shadow file (94% PENDING band)\n"
             f"- Fundamentals parquet coverage (India 228 tickers only)\n"
             f"- Walk-forward corpus depth (day-0 captured today only)\n")

    L.append(f"\n---\n\n## Appendix · files consumed\n")
    files = [
        "mr_prediction_autopsy_{market}.jsonl",
        "mr_prediction_autopsy_{market}_enriched.jsonl",
        "mr_prediction_autopsy_{market}_summary.json",
        "mr_studies_{market}.json",
        "mr_stop_loss_sweep_{market}.json",
        "mr_loss_prevention_{market}.json",
        "mr_control_cohort_{market}.json",
        "mr_missed_winners_{market}.json",
        "mr_market_regime_{market}.json",
        "mr_feature_ranking_{market}.json",
        "mr_score_usefulness_{market}.json",
        "mr_winner_loser_genome_{market}.json",
        "mr_hypothesis_shortlist.json",
        "tickets/INDEX.json + 5 DRAFT tickets",
        "experiments/INDEX.json + 5 NOT_STARTED experiments",
        "walkforward/{date}/{market}.jsonl (day-0 captures)",
    ]
    for f in files:
        L.append(f"- `reports/research/{f}`")

    L.append(f"\n## Reproduce\n\n```bash\npython -m backend.research.mr_v1_pipeline --market both\npython -m backend.research.mr_forward_validation_report\npytest tests/research/ -q\n```\n")
    return "\n".join(L)


def emit(root: Path, body: str) -> Path:
    p = root / ALLOWED_WRITE_ROOT / "AEGIS_FORWARD_VALIDATION_REPORT.md"
    p.write_text(body, encoding="utf-8")
    return p


if __name__ == "__main__":
    root = Path(".").resolve()
    body = build(root)
    p = emit(root, body)
    print(f"[forward_validation_report] wrote {p} · {len(body)} bytes · "
          f"{body.count(chr(10))} lines")
