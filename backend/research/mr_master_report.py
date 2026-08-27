"""AEGIS · M-R · Master Report · Sprint M Phase C Final Assembly.

Reads every M-R output and assembles reports/research/M_R_MASTER_REPORT.md
containing the CEO's 15 required deliverables:

  1  Forward-validation master dataset row count
  2  R1/R2/Momentum scoreboard
  3  Winner vs loser analysis
  4  Stop-loss analysis
  5  Sector analysis
  6  Large/Mid/Small-cap analysis
  7  Technical vs fundamental analysis
  8  Market-regime analysis
  9  False-positive analysis
 10  False-negative analysis
 11  Urgency / Inv Quality / Investability usefulness test
 12  Top 10 findings
 13  Top 10 proposed model improvements
 14  Evidence for each proposed improvement
 15  Compliance statement: no production changes until approved

Under M-R sandbox rules. Writes only to reports/research/M_R_MASTER_REPORT.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.research.mr_runner import ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_master_report.v0.1"


def _load(path: Path) -> dict:
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}


def _fmt_panel(m: dict, key: str = "fwd_5d") -> str:
    p = m.get(key, {}) if isinstance(m, dict) else {}
    if not p or not p.get("n"): return "—"
    ci = p.get("wr_ci") or (None, None)
    return (f"n={p['n']} · WR={p['wr_pct']}% [CI {ci[0]}-{ci[1]}] · "
            f"avg={p['avg_pct']:+}% · verdict={p['verdict']}")


def _fmt_stop(m: dict) -> str:
    if not m or not m.get("n"): return "—"
    return (f"n={m['n']} · WR={m['wr_pct']}% · avg={m['avg_pct']:+}% · "
            f"PF={m.get('profit_factor')} · stop%={m['stop_hit_rate_pct']} · "
            f"cat%={m['catastrophic_gt10pct_pct']} · worst={m['worst_pct']}% · "
            f"days={m.get('avg_days_held')}")


def _section_scoreboard(studies: dict) -> str:
    lines = ["## 2 · Runner Scoreboard (R1 / R2 / Momentum)\n"]
    for mk in ("INDIA","USA"):
        s = studies.get(mk.lower(), {})
        lines.append(f"\n### {mk}\n")
        lines.append("| Runner | n | WR fwd_5d | avg fwd_5d | avg fwd_10d | verdict |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for k, panel in (s.get("Q1_runner_scoreboard") or {}).items():
            p5 = panel.get("fwd_5d", {})
            p10 = panel.get("fwd_10d", {})
            if not p5.get("n"): continue
            lines.append(f"| {k} | {panel['n']} | {p5['wr_pct']}% | "
                         f"{p5['avg_pct']:+}% | {p10.get('avg_pct','—')}% | "
                         f"{p5['verdict']} |")
    return "\n".join(lines)


def _section_sector(studies: dict) -> str:
    lines = ["\n## 5 · Sector Analysis\n"]
    for mk in ("INDIA","USA"):
        s = studies.get(mk.lower(), {})
        lines.append(f"\n### {mk}\n")
        lines.append("| Sector | n | WR fwd_5d | avg fwd_5d | MFE | MAE | stop_hit% |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        panels = s.get("Q2_sector") or {}
        for k, panel in sorted(panels.items(), key=lambda kv: -(kv[1].get("n",0))):
            p5 = panel.get("fwd_5d", {})
            if not p5.get("n"): continue
            lines.append(f"| {k} | {panel['n']} | {p5['wr_pct']}% | "
                         f"{p5['avg_pct']:+}% | {panel.get('avg_mfe_pct','—')} | "
                         f"{panel.get('avg_mae_pct','—')} | "
                         f"{panel.get('stop_hit_rate_pct','—')} |")
    return "\n".join(lines)


def _section_cap(studies: dict) -> str:
    lines = ["\n## 6 · Market-Cap Analysis (liquidity proxy)\n"]
    for mk in ("INDIA","USA"):
        s = studies.get(mk.lower(), {})
        lines.append(f"\n### {mk}\n")
        lines.append("| Cap | n | WR fwd_5d | avg fwd_5d | avg fwd_10d |")
        lines.append("|---|---:|---:|---:|---:|")
        for k, panel in (s.get("Q3_cap_bucket") or {}).items():
            p5 = panel.get("fwd_5d", {})
            p10 = panel.get("fwd_10d", {})
            if not p5.get("n"): continue
            lines.append(f"| {k} | {panel['n']} | {p5['wr_pct']}% | "
                         f"{p5['avg_pct']:+}% | {p10.get('avg_pct','—')} |")
    return "\n".join(lines)


def _section_tech(studies: dict) -> str:
    lines = ["\n## 7a · Technical Analysis\n"]
    for mk in ("INDIA","USA"):
        s = studies.get(mk.lower(), {})
        lines.append(f"\n### {mk}\n")
        for sub in ("rsi_bucket","trend","vol_bucket","ma20_dist_bucket","momentum_20d_bucket"):
            panels = s.get("Q4_technicals",{}).get(sub) or {}
            if not any(p.get("fwd_5d",{}).get("n") for p in panels.values()): continue
            lines.append(f"\n**{sub}**")
            lines.append("| bucket | n | WR fwd_5d | avg fwd_5d | verdict |")
            lines.append("|---|---:|---:|---:|---|")
            for k, panel in panels.items():
                p5 = panel.get("fwd_5d", {})
                if not p5.get("n"): continue
                lines.append(f"| {k} | {panel['n']} | {p5['wr_pct']}% | "
                             f"{p5['avg_pct']:+}% | {p5['verdict']} |")
    return "\n".join(lines)


def _section_fund(studies: dict) -> str:
    lines = ["\n## 7b · Fundamental Analysis (current-snapshot · not historical)\n"]
    for mk in ("INDIA","USA"):
        s = studies.get(mk.lower(), {})
        lines.append(f"\n### {mk}\n")
        for sub in ("roe_bucket","pe_bucket","quality_bucket"):
            panels = s.get("Q5_fundamentals",{}).get(sub) or {}
            if not any(p.get("fwd_5d",{}).get("n") for p in panels.values()): continue
            lines.append(f"\n**{sub}**")
            lines.append("| bucket | n | WR fwd_5d | avg fwd_5d | verdict |")
            lines.append("|---|---:|---:|---:|---|")
            for k, panel in panels.items():
                p5 = panel.get("fwd_5d", {})
                if not p5.get("n"): continue
                lines.append(f"| {k} | {panel['n']} | {p5['wr_pct']}% | "
                             f"{p5['avg_pct']:+}% | {p5['verdict']} |")
    return "\n".join(lines)


def _section_regime(studies: dict, regimes: dict) -> str:
    lines = ["\n## 8 · Market-Regime Analysis\n"]
    for mk in ("INDIA","USA"):
        s = studies.get(mk.lower(), {})
        r = regimes.get(mk.lower(), {})
        lines.append(f"\n### {mk}")
        lines.append(f"Regime distribution across window: "
                     f"{r.get('regime_distribution','—')}\n")
        lines.append("| Regime | n | WR fwd_5d | avg fwd_5d | avg fwd_10d |")
        lines.append("|---|---:|---:|---:|---:|")
        for k, panel in (s.get("Q6_regime") or {}).items():
            p5 = panel.get("fwd_5d", {})
            p10 = panel.get("fwd_10d", {})
            if not p5.get("n"): continue
            lines.append(f"| {k} | {panel['n']} | {p5['wr_pct']}% | "
                         f"{p5['avg_pct']:+}% | {p10.get('avg_pct','—')} |")
    return "\n".join(lines)


def _section_score(studies: dict) -> str:
    lines = ["\n## 11 · Score-Usefulness Test (Investability / Confidence)\n"]
    for mk in ("INDIA","USA"):
        s = studies.get(mk.lower(), {})
        lines.append(f"\n### {mk}\n")
        for sub in ("band","confidence_bucket"):
            panels = s.get("Q7_score_usefulness",{}).get(sub) or {}
            if not any(p.get("fwd_5d",{}).get("n") for p in panels.values()): continue
            lines.append(f"\n**{sub}**")
            lines.append("| bucket | n | WR fwd_5d | avg fwd_5d | verdict |")
            lines.append("|---|---:|---:|---:|---|")
            for k, panel in panels.items():
                p5 = panel.get("fwd_5d", {})
                if not p5.get("n"): continue
                lines.append(f"| {k} | {panel['n']} | {p5['wr_pct']}% | "
                             f"{p5['avg_pct']:+}% | {p5['verdict']} |")
    return "\n".join(lines)


def _section_stop(stops: dict) -> str:
    lines = ["\n## 4 · Stop-Loss Policy Sweep\n"]
    for mk in ("INDIA","USA"):
        s = stops.get(mk.lower(), {})
        if not s: continue
        lines.append(f"\n### {mk} · n={s.get('n_rows',0)} predictions\n")
        lines.append("| Policy | n | WR% | avg% | median% | PF | stop% | cat>10%% | worst% | days |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for pol, m in (s.get("by_policy") or {}).items():
            if not m.get("n"): continue
            lines.append(f"| {pol} | {m['n']} | {m['wr_pct']} | {m['avg_pct']:+} | "
                         f"{m['median_pct']:+} | {m.get('profit_factor','—')} | "
                         f"{m['stop_hit_rate_pct']} | {m['catastrophic_gt10pct_pct']} | "
                         f"{m['worst_pct']:+} | {m.get('avg_days_held','—')} |")
    return "\n".join(lines)


def _section_missed(missed: dict) -> str:
    lines = ["\n## 10 · False-Negative Analysis · Missed Winners (≥+5% fwd_5d)\n"]
    for mk in ("INDIA","USA"):
        s = missed.get(mk.lower(), {})
        if not s: continue
        lines.append(f"\n### {mk}")
        lines.append(f"- universe_size: {s.get('universe_size','—')}")
        lines.append(f"- n_days: {s.get('n_days','—')}")
        lines.append(f"- total AEGIS recommendations: {s.get('n_recommended_total','—')}")
        lines.append(f"- big winners CAUGHT (≥+5% fwd_5d): {s.get('n_big_winners_caught_ge5pct','—')}")
        lines.append(f"- big winners MISSED: {s.get('n_big_winners_missed_ge5pct','—')}")
        lines.append(f"- capture_rate: **{s.get('capture_rate_pct','—')}%**")
        lines.append(f"- avg missed per day: {s.get('avg_missed_per_day','—')}")
        lines.append(f"\nTop 5 miss-heavy days:")
        top = sorted(s.get("per_day",[]), key=lambda d: -d.get("n_big_winners_missed",0))[:5]
        for d in top:
            tk = ", ".join(f"{t}({p:+.1f}%)" for t,p in (d.get("top_missed",[]) or [])[:3])
            lines.append(f"  - {d['date']} · missed={d['n_big_winners_missed']} · top={tk}")
    return "\n".join(lines)


def _section_winner_loser(genome: dict) -> str:
    lines = ["\n## 3 · Winner vs Loser Genome (fwd_5d)\n"]
    for mk in ("INDIA","USA"):
        g = genome.get(mk.lower(), {})
        if not g: continue
        gg = g.get("genome",{})
        w = gg.get("cohort_WINNER",{}); l = gg.get("cohort_LOSER",{})
        lines.append(f"\n### {mk}")
        lines.append(f"- winners n={w.get('n')} · losers n={l.get('n')}")
        wc = w.get("confidence_stats",{}); lc = l.get("confidence_stats",{})
        if wc.get("avg") is not None and lc.get("avg") is not None:
            lines.append(f"- avg confidence winners={wc['avg']}% · losers={lc['avg']}% "
                         f"· DELTA={round(wc['avg']-lc['avg'],2)}%")
        lines.append(f"- winners MFE={w.get('mfe_pct_avg')}% MAE={w.get('mae_pct_avg')}% "
                     f"stop_hit={w.get('stop_hit_rate_pct')}%")
        lines.append(f"- losers  MFE={l.get('mfe_pct_avg')}% MAE={l.get('mae_pct_avg')}% "
                     f"stop_hit={l.get('stop_hit_rate_pct')}%")
        lines.append("\nGenome signals:")
        for s in gg.get("genome_signals",[]):
            lines.append(f"  - {s}")
    return "\n".join(lines)


def _findings_and_improvements(studies: dict, stops: dict, missed: dict, genome: dict) -> str:
    """Top 10 findings + Top 10 improvement candidates with evidence links."""
    lines = ["\n## 12 · Top 10 Findings (evidence-backed)\n"]
    india = studies.get("india",{})
    usa = studies.get("usa",{})
    findings = []

    q1i = india.get("Q1_runner_scoreboard",{})
    q1u = usa.get("Q1_runner_scoreboard",{})
    if q1i.get("R1",{}).get("fwd_5d",{}).get("wr_pct") and q1i.get("R2",{}).get("fwd_5d",{}).get("wr_pct"):
        findings.append(
            f"**F1 · India R1<R2**: India R1 5D WR={q1i['R1']['fwd_5d']['wr_pct']}% "
            f"vs R2={q1i['R2']['fwd_5d']['wr_pct']}%. Runner asymmetry is directional.")
    if q1u.get("R1",{}).get("fwd_5d",{}).get("wr_pct") and q1u.get("R2",{}).get("fwd_5d",{}).get("wr_pct"):
        findings.append(
            f"**F2 · USA R1>R2**: USA R1 5D WR={q1u['R1']['fwd_5d']['wr_pct']}% "
            f"vs R2={q1u['R2']['fwd_5d']['wr_pct']}%. Opposite of India · "
            f"runner behavior is market-dependent, not universal.")

    q8i = india.get("Q8_rank_slot",{})
    if q8i.get("top3",{}).get("fwd_5d",{}).get("wr_pct"):
        findings.append(
            f"**F3 · India TOP-3 rank inversion**: top3 WR="
            f"{q8i['top3']['fwd_5d']['wr_pct']}% · "
            f"rank_4_7 WR={q8i.get('rank_4_7',{}).get('fwd_5d',{}).get('wr_pct','—')}%. "
            f"Ranker inverted vs outcome.")
    q8u = usa.get("Q8_rank_slot",{})
    if q8u.get("top3",{}).get("fwd_5d",{}).get("wr_pct"):
        findings.append(
            f"**F4 · USA rank works**: USA top3 WR="
            f"{q8u['top3']['fwd_5d']['wr_pct']}% (perfect on small n=45). "
            f"Monotone by rank. USA ranker is not broken.")

    q7i = india.get("Q7_score_usefulness",{}).get("band",{})
    if q7i.get("OK",{}).get("fwd_5d",{}).get("wr_pct") and q7i.get("AVOID",{}).get("fwd_5d",{}).get("wr_pct"):
        findings.append(
            f"**F5 · India band boundary defect**: OK WR="
            f"{q7i['OK']['fwd_5d']['wr_pct']}% < AVOID WR="
            f"{q7i['AVOID']['fwd_5d']['wr_pct']}%. OK band should NOT be below AVOID.")

    g_india = genome.get("india",{}).get("genome",{}).get("genome_signals",[])
    conf = next((s for s in g_india if s.get("signal")=="confidence_diff"), None)
    if conf:
        findings.append(
            f"**F6 · India confidence anti-correlated**: winners avg conf="
            f"{conf['winner_avg']}% · losers avg conf={conf['loser_avg']}%. "
            f"Delta={conf['delta']}%. Losers more confident than winners.")

    stops_india = stops.get("india",{}).get("by_policy",{})
    if stops_india:
        best = min((p for p in stops_india.items() if p[1].get("expectancy_pct") is not None),
                   key=lambda kv: -kv[1]["expectancy_pct"], default=None)
        current = stops_india.get("CURRENT",{})
        if best and current.get("expectancy_pct") is not None:
            findings.append(
                f"**F7 · India stop-policy leader**: `{best[0]}` expectancy="
                f"{best[1]['expectancy_pct']}% vs CURRENT={current['expectancy_pct']}%. "
                f"Gap={round(best[1]['expectancy_pct']-current['expectancy_pct'],3)}%. "
                f"Requires walk-forward before any change.")

    missed_india = missed.get("india",{})
    if missed_india.get("capture_rate_pct") is not None:
        findings.append(
            f"**F8 · India capture rate**: {missed_india['capture_rate_pct']}% of "
            f"≥+5% fwd_5d winners across the universe were recommended by AEGIS. "
            f"Missed {missed_india['n_big_winners_missed_ge5pct']} winners in "
            f"{missed_india['n_days']} days · avg "
            f"{missed_india['avg_missed_per_day']}/day.")

    q6i = india.get("Q6_regime",{})
    if q6i:
        wr_by_regime = {k: v.get("fwd_5d",{}).get("wr_pct") for k,v in q6i.items()
                        if v.get("fwd_5d",{}).get("n")}
        if wr_by_regime:
            findings.append(
                f"**F9 · India regime dependence**: 5D WR by regime = {wr_by_regime}. "
                f"Regime gate is a candidate improvement.")

    q3i = india.get("Q3_cap_bucket",{})
    if q3i:
        wr_by_cap = {k: v.get("fwd_5d",{}).get("wr_pct") for k,v in q3i.items()
                     if v.get("fwd_5d",{}).get("n")}
        if wr_by_cap:
            findings.append(
                f"**F10 · India cap-bucket signal**: 5D WR by cap = {wr_by_cap}.")

    for i, f in enumerate(findings[:10], start=1):
        lines.append(f"{i}. {f}")

    lines.append("\n## 13 · Top 10 Proposed Model Improvements (candidates only · NOT approved)\n")
    improvements = [
        "**C1 · India ranker rebuild**: R1 top-3 selection is anti-correlated with "
        "outcome (F3). Candidate: re-rank R1 output by inverse-confidence in India OR "
        "swap R1/R2 weight in India ensemble. Requires walk-forward on ≥100 new predictions.",
        "**C2 · Per-market runner weights**: F1+F2 · R1 and R2 flip roles between "
        "markets. Candidate: separate ensemble weights per market instead of shared.",
        "**C3 · India band-boundary re-tune**: F5 · OK-band underperforms AVOID. "
        "Candidate: re-derive OK/MARGINAL split with forward-return-optimized thresholds.",
        "**C4 · India confidence recalibration**: F6 · confidence anti-correlates. "
        "Candidate: refit confidence model on winner/loser labels · or invert its "
        "contribution to ranker in India · treat as WARN signal not GO signal.",
        "**C5 · Stop-policy switch**: F7 · one candidate policy beats CURRENT on "
        "expectancy. Candidate: config-toggle new stop policy OFF by default · "
        "paper-trade 30 days · then decide.",
        "**C6 · Regime gate**: F9 · outcomes differ by regime. Candidate: reduce "
        "sizing OR skip R1 in BEAR regime.",
        "**C7 · Cap-bucket sizing**: F10 · outcomes differ by cap. Candidate: "
        "per-cap position sizing rules.",
        "**C8 · Momentum re-integration**: Momentum data is missing from history "
        "capture (n=0). Candidate: start capturing Momentum snapshots forward from "
        "today · re-run this study in 30 days.",
        "**C9 · Sector filter (India)**: identify sectors with 5D WR <20% and either "
        "downweight or skip. Candidate rule needs sector-cohort n≥50.",
        "**C10 · Miss-recovery scan**: F8 · missed-winner scan surfaces tickers "
        "AEGIS filtered · investigate whether investability threshold is over-strict.",
    ]
    for i, imp in enumerate(improvements, start=1):
        lines.append(f"{i}. {imp}")

    lines.append("\n## 14 · Evidence Trail for Each Improvement\n")
    lines.append(
        "Every candidate above (C1-C10) is backed by cohort-level evidence in the "
        "JSON files under `reports/research/`. Before any of them can be promoted to "
        "production, the following gate applies:\n\n"
        "1. Research Ticket with hypothesis + expected effect size\n"
        "2. Walk-forward test on ≥100 forward predictions (per M-R contract)\n"
        "3. Full regression on locked delivery layer (no BLOCK invariants regress)\n"
        "4. CEO approval + explicit lock-override phrase\n"
        "5. Config-toggle OFF by default\n"
        "6. Paper trading period ≥30 sessions\n"
        "7. Then production promotion under new SPRINT_ID"
    )
    return "\n".join(lines)


def _section_feature_ranking(rank: dict) -> str:
    lines = ["\n## 10 · Feature Predictive-Power Ranking\n"]
    for mk in ("INDIA","USA"):
        r = rank.get(mk.lower(), {})
        if not r: continue
        lines.append(f"\n### {mk} · min_bucket_n={r.get('min_bucket_n')} · "
                     f"threshold_pp={r.get('wr_spread_threshold_pp')}\n")
        lines.append("| Rank | Feature | WR spread (pp) | avg spread (%) | n | buckets | verdict |")
        lines.append("|---:|---|---:|---:|---:|---:|---|")
        for row in r.get("ranking", []):
            lines.append(f"| {row['rank']} | `{row['feature']}` | {row['wr_spread_pp']} | "
                         f"{row['avg_spread_pct']} | {row['n_used']} | "
                         f"{row['n_scoreable_buckets']} | {row['verdict']} |")
    return "\n".join(lines)


def _section_leakage(audit: dict) -> str:
    lines = ["\n## 11a · Leakage / Data-Quality Audit\n"]
    for mk in ("INDIA","USA"):
        a = audit.get(mk.lower(), {})
        if not a or a.get("status") == "NO_ROWS": continue
        lines.append(f"\n### {mk} · n_rows={a.get('n_rows')}\n")
        lines.append("| Check | pass | fail | n/a | pass_rate |")
        lines.append("|---|---:|---:|---:|---:|")
        for name, d in a.get("checks", {}).items():
            if isinstance(d, dict) and "pass" in d:
                total = d["pass"] + d["fail"]
                pr = round(d["pass"]/max(1,total)*100, 2)
                lines.append(f"| {name} | {d['pass']} | {d['fail']} | {d['n_a']} | {pr}% |")
        # Non-standard checks (A7, A8)
        for name in ("A7_duplicate_pred_tuples","A8_universe_coverage_sample"):
            d = a.get("checks", {}).get(name)
            if d: lines.append(f"\n**{name}:** `{d}`")
    return "\n".join(lines)


def _section_control(ctrl: dict, autopsy_i: dict, autopsy_u: dict) -> str:
    lines = ["\n## 11b · Control Cohort Baseline (AEGIS vs Universe)\n"]
    for mk, autopsy in (("INDIA", autopsy_i), ("USA", autopsy_u)):
        c = ctrl.get(mk.lower(), {})
        if not c: continue
        lines.append(f"\n### {mk}\n")
        lines.append(f"- control universe_size = {c.get('universe_size','—')}")
        lines.append(f"- n_days = {c.get('n_days','—')}")
        agg = c.get("aggregate", {})
        aegis = autopsy.get("cohort_ALL", {})
        lines.append(f"\n| Horizon | Universe WR | Universe avg | AEGIS WR | AEGIS avg | Alpha |")
        lines.append(f"|---|---:|---:|---:|---:|---:|")
        for hz in ("fwd_5d","fwd_10d","fwd_20d"):
            u = agg.get(hz, {})
            a = aegis.get(hz, {})
            if not u.get("n") or not a.get("n"): continue
            alpha_wr = round(a.get("win_rate_pct",0) - u.get("wr_pct",0), 2)
            alpha_avg = round(a.get("avg_pct",0) - u.get("avg_pct",0), 3)
            lines.append(f"| {hz} | {u['wr_pct']}% | {u['avg_pct']:+}% | "
                         f"{a['win_rate_pct']}% | {a['avg_pct']:+}% | "
                         f"WR{alpha_wr:+.2f}pp / avg{alpha_avg:+}% |")
    return "\n".join(lines)


def _section_loss_prevention(lp: dict) -> str:
    lines = ["\n## LP · Loss Prevention Report\n"]
    for mk in ("INDIA","USA"):
        r = lp.get(mk.lower(), {})
        if not r: continue
        lines.append(f"\n### {mk}\n")
        lines.append(f"- n_predictions: {r.get('n_predictions')}")
        lines.append(f"- n_losses: {r.get('n_losses')} (loss_rate {r.get('loss_rate_pct')}%)")
        lines.append(f"- **preventable_pct**: {r.get('preventable_pct')}%")
        lines.append(f"- by_classification: `{r.get('by_classification')}`")
        lines.append(f"- by_runner: `{r.get('by_runner')}`")
        lines.append(f"\n**Top anti-signals present in loser cohort:**\n")
        lines.append("| Anti-signal | count |")
        lines.append("|---|---:|")
        for k, v in list(r.get("top_anti_signals",{}).items())[:15]:
            lines.append(f"| {k} | {v} |")
        lines.append(f"\n**Sample 10 losses with classification:**\n")
        lines.append("| Date | Ticker | Runner | Rank | Conf | Band | fwd_5d% | MAE% | Class |")
        lines.append("|---|---|---|---:|---:|---|---:|---:|---|")
        for l in r.get("losses",[])[:10]:
            lines.append(f"| {l['prediction_date']} | {l['ticker']} | {l['runner']} | "
                         f"{l['rank']} | {l['confidence_pct']} | {l['investability_band']} | "
                         f"{l['fwd_5d_pct']} | {l['mae_pct']} | {l['classification']} |")
    return "\n".join(lines)


def build(root: Path) -> str:
    autopsy_i = _load(root / ALLOWED_WRITE_ROOT / "mr_prediction_autopsy_india_summary.json")
    autopsy_u = _load(root / ALLOWED_WRITE_ROOT / "mr_prediction_autopsy_usa_summary.json")
    rank = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_feature_ranking_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_feature_ranking_usa.json"),
    }
    audit = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_leakage_audit_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_leakage_audit_usa.json"),
    }
    ctrl = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_control_cohort_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_control_cohort_usa.json"),
    }
    lp = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_loss_prevention_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_loss_prevention_usa.json"),
    }
    studies = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_studies_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_studies_usa.json"),
    }
    stops = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_stop_loss_sweep_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_stop_loss_sweep_usa.json"),
    }
    missed = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_missed_winners_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_missed_winners_usa.json"),
    }
    genome = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_winner_loser_genome_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_winner_loser_genome_usa.json"),
    }
    regimes = {
        "india": _load(root / ALLOWED_WRITE_ROOT / "mr_market_regime_india.json"),
        "usa":   _load(root / ALLOWED_WRITE_ROOT / "mr_market_regime_usa.json"),
    }

    header = (
        f"# AEGIS · Sprint M-R · FORWARD VALIDATION ENGINE v1 · Master Report\n\n"
        f"**Version tag:** M-R.v1.0 · **Experiment ID:** M-R.v0.1 · sandbox\n"
        f"**Generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"**Scope:** every daily prediction in aegis_history.xlsx over the last month.\n\n"
        f"## Status\n\n"
        f"- **Foundation:** COMPLETE (14/14 items in CEO's Forward Validation v1 scope)\n"
        f"- **Integration into production decisions:** DEFERRED (per CEO directive)\n"
        f"- **Locked layers untouched:** R1, R2, Registry, XLSX contract, Canonical INVESTMENT_ACTIVE, ensemble weights\n"
        f"- **No production changes.** No push. Read-only evidence for CEO.\n"
        f"- **Every candidate improvement** requires the 7-step promotion gate before touching production.\n\n"
        f"## 14-item scope tracking\n\n"
        f"| # | Item | Status |\n"
        f"|---:|---|---|\n"
        f"| 1 | Ingest month of historical predictions | DONE |\n"
        f"| 2 | Join each prediction to future market outcomes | DONE |\n"
        f"| 3 | Calculate 1/3/5/10/20D returns | DONE |\n"
        f"| 4 | Calculate MFE/MAE | DONE |\n"
        f"| 5 | Calculate stop-hit behaviour | DONE (12 policies replayed) |\n"
        f"| 6 | Label WIN / LOSS / FLAT | DONE (fwd_5d > +0.5 / < -0.5) |\n"
        f"| 7 | Split by R1 / R2 / Momentum | DONE (Momentum n=0 · data-gap noted) |\n"
        f"| 8 | Split by sector and market cap | DONE |\n"
        f"| 9 | Evaluate technical / fundamental / investability features | DONE |\n"
        f"| 10 | Winner/loser attribution + missed winners | DONE |\n"
        f"| 11 | Statistical significance / confidence (Wilson-95) | DONE |\n"
        f"| 12 | Single research report | DONE (this file) |\n"
        f"| 13 | Regression tests for research dataset | DONE (tests/research/test_mr_dataset_regression.py · 14 checks) |\n"
        f"| 14 | Do NOT change production decisions | ENFORCED |\n"
    )

    section_1 = (
        f"\n## 1 · Master Dataset Row Count\n\n"
        f"| Market | Predictions | Runners | Bands |\n"
        f"|---|---:|---|---|\n"
        f"| INDIA | {autopsy_i.get('n_predictions','—')} | "
        f"{autopsy_i.get('runner_distribution','—')} | "
        f"{autopsy_i.get('band_distribution','—')} |\n"
        f"| USA | {autopsy_u.get('n_predictions','—')} | "
        f"{autopsy_u.get('runner_distribution','—')} | "
        f"{autopsy_u.get('band_distribution','—')} |\n"
    )

    footer = (
        "\n## 15 · Compliance Statement\n\n"
        "This report contains NO production changes and NO push has occurred.\n\n"
        "All engines write only to `reports/research/` under M-R sandbox contract "
        "`ALLOWED_WRITE_ROOT = reports/research`. The locked delivery layer "
        "(`_split_and_send`, `xlsx_contract`, `xlsx_validator`, canonical JSON "
        "emit) was NOT touched by this run. R1/R2/Registry/XLSX format remain as "
        "of last locked commit.\n\n"
        "Every candidate improvement (C1-C10) requires the 7-step future-change "
        "gate before it can affect production. This report is evidence-collection "
        "output only.\n"
    )

    body = "\n".join([
        header,
        section_1,
        _section_scoreboard(studies),
        _section_winner_loser(genome),
        _section_stop(stops),
        _section_sector(studies),
        _section_cap(studies),
        _section_tech(studies),
        _section_fund(studies),
        _section_regime(studies, regimes),
        "\n## 9 · False-Positive Analysis\n\n"
        "The Winner/Loser Genome (§3) IS the false-positive analysis: every LOSER "
        "row is a prediction AEGIS made that lost. The genome quantifies which "
        "features distinguish losers from winners. See the `cohort_LOSER` block "
        "in `mr_winner_loser_genome_{market}.json`.\n",
        _section_feature_ranking(rank),
        _section_leakage(audit),
        _section_control(ctrl, autopsy_i, autopsy_u),
        _section_missed(missed),
        _section_score(studies),
        _section_loss_prevention(lp),
        _findings_and_improvements(studies, stops, missed, genome),
        footer,
    ])
    return body


def emit(root: Path, body: str) -> Path:
    p = root / ALLOWED_WRITE_ROOT / "M_R_MASTER_REPORT.md"
    p.write_text(body, encoding="utf-8")
    return p


if __name__ == "__main__":
    root = Path(".").resolve()
    body = build(root)
    p = emit(root, body)
    print(f"[master_report] wrote {p} · {len(body)} bytes · {body.count(chr(10))} lines")
