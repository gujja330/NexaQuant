"""AEGIS · Sprint M-R · CEO Dashboard · Forward Validation M1.

Consumes every M-R output JSON and produces the CEO's exact requested
template:

    AEGIS FORWARD VALIDATION — M1
    DATA / OVERALL / STRATEGIES / SECTORS / CAP /
    TECHNICAL / FUNDAMENTAL / STOP LOSS / WINNERS /
    LOSERS / AI HYPOTHESES / VALIDATED CHANGES

Emits a text version (for terminal) + a markdown version (for the
research report). Both under reports/research/.

Under M-R sandbox rules. Writes only under reports/research/.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_ceo_dashboard.v1.0"


def _load(root: Path, name: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _load_jsonl(root: Path, name: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _fmt(v, digits=2, suffix="", none_str="—"):
    if v is None: return none_str
    if isinstance(v, (int, float)):
        return f"{v:.{digits}f}{suffix}"
    return str(v)


def _unique_stocks(rows: list) -> int:
    return len({r.get("ticker") for r in rows if r.get("ticker")})


def _n_days(rows: list) -> int:
    return len({r.get("prediction_date") for r in rows if r.get("prediction_date")})


def _panel_line(panel: dict, hz: str = "fwd_5d") -> str:
    m = panel.get(hz, {}) if isinstance(panel, dict) else {}
    if not m or not m.get("n"): return "—"
    return (f"n={m['n']:>4d} WR={m['wr_pct']:>5.2f}% "
            f"avg={m['avg_pct']:+.3f}%")


def build_market_section(root: Path, market: str) -> dict:
    autopsy_rows = _load_jsonl(root, f"mr_prediction_autopsy_{market.lower()}.jsonl")
    autopsy_sum  = _load(root, f"mr_prediction_autopsy_{market.lower()}_summary.json")
    studies      = _load(root, f"mr_studies_{market.lower()}.json")
    stops        = _load(root, f"mr_stop_loss_sweep_{market.lower()}.json")
    missed       = _load(root, f"mr_missed_winners_{market.lower()}.json")
    ctrl         = _load(root, f"mr_control_cohort_{market.lower()}.json")
    lp           = _load(root, f"mr_loss_prevention_{market.lower()}.json")
    genome       = _load(root, f"mr_winner_loser_genome_{market.lower()}.json")
    rank         = _load(root, f"mr_feature_ranking_{market.lower()}.json")
    score        = _load(root, f"mr_score_usefulness_{market.lower()}.json")

    cohort_all = autopsy_sum.get("cohort_ALL", {}) if isinstance(autopsy_sum, dict) else {}
    fwd1 = cohort_all.get("fwd_1d", {})
    fwd5 = cohort_all.get("fwd_5d", {})
    fwd10 = cohort_all.get("fwd_10d", {})
    fwd20 = cohort_all.get("fwd_20d", {})

    # Strategy scoreboard
    q1 = studies.get("Q1_runner_scoreboard", {}) if isinstance(studies, dict) else {}

    # Sectors sorted by fwd_5d WR (min n=15)
    q2 = studies.get("Q2_sector", {}) if isinstance(studies, dict) else {}
    sectors_ranked = []
    for k, panel in q2.items():
        m5 = panel.get("fwd_5d", {})
        if m5.get("n", 0) >= 15 and m5.get("wr_pct") is not None:
            sectors_ranked.append({
                "sector": k, "n": panel.get("n"),
                "wr_5d": m5["wr_pct"], "avg_5d": m5["avg_pct"],
                "mfe": panel.get("avg_mfe_pct"),
                "mae": panel.get("avg_mae_pct"),
                "stop_hit_pct": panel.get("stop_hit_rate_pct"),
            })
    sectors_ranked.sort(key=lambda s: -s["wr_5d"])
    best_sectors = sectors_ranked[:3]
    worst_sectors = sectors_ranked[-3:] if len(sectors_ranked) >= 3 else []

    # Cap
    q3 = studies.get("Q3_cap_bucket", {}) if isinstance(studies, dict) else {}

    # Technical top predictors
    q4 = studies.get("Q4_technicals", {}) if isinstance(studies, dict) else {}

    # Fundamental
    q5 = studies.get("Q5_fundamentals", {}) if isinstance(studies, dict) else {}

    # Feature ranking top-3
    top_features = (rank.get("ranking") or [])[:3] if isinstance(rank, dict) else []

    # Stop-loss MAE distribution + best policy
    stops_bp = stops.get("by_policy", {}) if isinstance(stops, dict) else {}
    best_pol = None
    if stops_bp:
        eligible = [(k, v) for k, v in stops_bp.items()
                    if v.get("expectancy_pct") is not None]
        if eligible:
            best_pol = max(eligible, key=lambda kv: kv[1]["expectancy_pct"])

    # Winners / losers
    genome_g = genome.get("genome", {}) if isinstance(genome, dict) else {}
    w = genome_g.get("cohort_WINNER", {})
    l = genome_g.get("cohort_LOSER", {})
    genome_signals = genome_g.get("genome_signals", [])

    # Loss classification
    lp_class = lp.get("by_classification", {}) if isinstance(lp, dict) else {}
    lp_anti = lp.get("top_anti_signals", {}) if isinstance(lp, dict) else {}

    # Alpha vs universe
    ur = (ctrl.get("aggregate", {}) or {}).get("fwd_5d", {}) if isinstance(ctrl, dict) else {}
    alpha_wr = None
    alpha_avg = None
    if ur.get("n") and fwd5.get("n"):
        alpha_wr = round(fwd5["win_rate_pct"] - ur["wr_pct"], 2)
        alpha_avg = round(fwd5["avg_pct"] - ur["avg_pct"], 3)

    return {
        "market":            market.upper(),
        "n_predictions":     len(autopsy_rows),
        "unique_stocks":     _unique_stocks(autopsy_rows),
        "trading_days":      _n_days(autopsy_rows),
        "cohort_all_fwd1":   fwd1,
        "cohort_all_fwd5":   fwd5,
        "cohort_all_fwd10":  fwd10,
        "cohort_all_fwd20":  fwd20,
        "avg_mfe_pct":       cohort_all.get("avg_mfe_pct"),
        "avg_mae_pct":       cohort_all.get("avg_mae_pct"),
        "stop_hit_rate_pct": cohort_all.get("stop_hit_rate_pct"),
        "strategies":        q1,
        "sectors_best":      best_sectors,
        "sectors_worst":     worst_sectors,
        "cap_buckets":       q3,
        "technicals":        q4,
        "fundamentals":      q5,
        "top_features":      top_features,
        "stop_best_policy":  best_pol,
        "stop_policies":     stops_bp,
        "cohort_winner":     w,
        "cohort_loser":      l,
        "genome_signals":    genome_signals,
        "loss_classification": lp_class,
        "loss_anti_signals": lp_anti,
        "loss_rate_pct":     lp.get("loss_rate_pct") if isinstance(lp, dict) else None,
        "preventable_pct":   lp.get("preventable_pct") if isinstance(lp, dict) else None,
        "control_fwd5":      ur,
        "alpha_wr":          alpha_wr,
        "alpha_avg":         alpha_avg,
        "universe_size":     ctrl.get("universe_size") if isinstance(ctrl, dict) else None,
        "capture_rate_pct":  missed.get("capture_rate_pct") if isinstance(missed, dict) else None,
        "n_big_winners_missed": missed.get("n_big_winners_missed_ge5pct") if isinstance(missed, dict) else None,
        "score_verdicts":    (score.get("audits") or {}) if isinstance(score, dict) else {},
    }


def _render_market_text(sec: dict) -> str:
    """Render one market's section in CEO's ASCII template."""
    lines = []
    lines.append(f"\n════════════════════════════════════════════════════════════════════")
    lines.append(f"  AEGIS FORWARD VALIDATION — M1 · {sec['market']}")
    lines.append(f"════════════════════════════════════════════════════════════════════\n")

    # DATA
    lines.append(f"DATA")
    lines.append(f"  Predictions:      {sec['n_predictions']}")
    lines.append(f"  Unique stocks:    {sec['unique_stocks']}")
    lines.append(f"  Trading days:     {sec['trading_days']}")
    lines.append(f"")

    # OVERALL
    lines.append(f"OVERALL (all runners combined)")
    for hz_name, key in (("Win rate fwd_1d", "cohort_all_fwd1"),
                          ("Win rate fwd_5d", "cohort_all_fwd5"),
                          ("Win rate fwd_10d","cohort_all_fwd10"),
                          ("Win rate fwd_20d","cohort_all_fwd20")):
        m = sec.get(key, {})
        if m.get("n"):
            lines.append(f"  {hz_name:20s} {m['win_rate_pct']:.2f}%  "
                         f"(n={m['n']}, avg={m['avg_pct']:+.3f}%)")
    lines.append(f"  Avg MFE:             {_fmt(sec['avg_mfe_pct'],3,'%')}")
    lines.append(f"  Avg MAE:             {_fmt(sec['avg_mae_pct'],3,'%')}")
    lines.append(f"  Stop-hit rate:       {_fmt(sec['stop_hit_rate_pct'],2,'%')}")
    if sec.get("control_fwd5", {}).get("n"):
        lines.append(f"")
        lines.append(f"  ALPHA vs universe baseline (same days):")
        lines.append(f"    Universe   n={sec['control_fwd5']['n']} "
                     f"WR={sec['control_fwd5']['wr_pct']}%  "
                     f"avg={sec['control_fwd5']['avg_pct']:+.3f}%")
        lines.append(f"    AEGIS      n={sec['cohort_all_fwd5'].get('n','—')} "
                     f"WR={sec['cohort_all_fwd5'].get('win_rate_pct','—')}%  "
                     f"avg={sec['cohort_all_fwd5'].get('avg_pct','—')}%")
        lines.append(f"    ALPHA      WR{sec['alpha_wr']:+.2f}pp  "
                     f"avg{sec['alpha_avg']:+.3f}%")
    lines.append(f"")

    # STRATEGIES
    lines.append(f"STRATEGIES")
    for k, panel in sec["strategies"].items():
        f5 = panel.get("fwd_5d", {})
        f10 = panel.get("fwd_10d", {})
        if not f5.get("n"): continue
        lines.append(f"  {k:10s} n={panel['n']:>4d}  "
                     f"5D WR={f5['wr_pct']:>5.2f}% avg={f5['avg_pct']:+.3f}%  "
                     f"10D avg={_fmt(f10.get('avg_pct'),3,'%')}  "
                     f"MFE={_fmt(panel.get('avg_mfe_pct'),3,'%')}  "
                     f"MAE={_fmt(panel.get('avg_mae_pct'),3,'%')}")
    if "MOMENTUM" not in sec["strategies"]:
        lines.append(f"  MOMENTUM   n=0  · historical snapshots not captured · "
                     f"start forward capture from today")
    lines.append(f"")

    # SECTORS
    lines.append(f"SECTORS  (min n=15 to qualify)")
    lines.append(f"  Best:")
    for s in sec["sectors_best"]:
        lines.append(f"    {s['sector']:16s} n={s['n']:>3d}  "
                     f"WR={s['wr_5d']:>5.2f}%  avg={s['avg_5d']:+.3f}%")
    if sec["sectors_worst"] and len(sec["sectors_best"]) >= 3:
        lines.append(f"  Worst:")
        for s in sec["sectors_worst"]:
            lines.append(f"    {s['sector']:16s} n={s['n']:>3d}  "
                         f"WR={s['wr_5d']:>5.2f}%  avg={s['avg_5d']:+.3f}%")
    lines.append(f"")

    # CAP
    lines.append(f"MARKET CAP (avg-dollar-volume liquidity proxy)")
    for k in ("LARGE","MID","SMALL","UNKNOWN"):
        panel = sec["cap_buckets"].get(k) or {}
        f5 = panel.get("fwd_5d", {})
        if not f5.get("n"): continue
        lines.append(f"  {k:8s} n={panel['n']:>4d}  "
                     f"WR={f5['wr_pct']:>5.2f}%  avg={f5['avg_pct']:+.3f}%")
    lines.append(f"")

    # TECHNICAL
    lines.append(f"TECHNICAL · best predictors (WR-spread)")
    for tf in sec["top_features"]:
        lines.append(f"  {tf['rank']}. {tf['feature']:22s} "
                     f"spread={tf['wr_spread_pp']:>5.2f}pp  n={tf['n_used']:>4d}  "
                     f"verdict={tf['verdict']}")
    lines.append(f"")

    # TECHNICAL bucket detail (RSI + trend + ma20 + momentum)
    lines.append(f"TECHNICAL · bucket detail")
    for sub in ("rsi_bucket","trend","ma20_dist_bucket","momentum_20d_bucket"):
        panels = (sec["technicals"].get(sub) or {})
        if not any(p.get("fwd_5d",{}).get("n") for p in panels.values()): continue
        lines.append(f"  ~ {sub} ~")
        for k, p in panels.items():
            f5 = p.get("fwd_5d", {})
            if not f5.get("n"): continue
            lines.append(f"    {k:20s} n={p['n']:>4d}  "
                         f"WR={f5['wr_pct']:>5.2f}%  avg={f5['avg_pct']:+.3f}%")
    lines.append(f"")

    # FUNDAMENTAL
    lines.append(f"FUNDAMENTAL · bucket detail (current-snapshot · not historical)")
    fund_lines = 0
    for sub in ("roe_bucket","pe_bucket","quality_bucket"):
        panels = (sec["fundamentals"].get(sub) or {})
        panels_with_n = {k:p for k,p in panels.items() if p.get("fwd_5d",{}).get("n")}
        if not panels_with_n: continue
        lines.append(f"  ~ {sub} ~")
        for k, p in panels_with_n.items():
            f5 = p.get("fwd_5d", {})
            lines.append(f"    {k:20s} n={p['n']:>4d}  "
                         f"WR={f5['wr_pct']:>5.2f}%  avg={f5['avg_pct']:+.3f}%")
            fund_lines += 1
    if fund_lines == 0:
        lines.append(f"  (fundamentals parquet has {sec['market']}-specific coverage gap · "
                     f"no bucket qualifies)")
    lines.append(f"")

    # STOP LOSS
    lines.append(f"STOP LOSS · policy sweep (12 policies replayed)")
    cur = sec["stop_policies"].get("CURRENT") or {}
    if cur:
        lines.append(f"  CURRENT policy   n={cur.get('n','—')}  "
                     f"WR={cur.get('wr_pct','—')}%  "
                     f"avg={cur.get('avg_pct','—')}%  "
                     f"PF={cur.get('profit_factor','—')}  "
                     f"stop-hit={cur.get('stop_hit_rate_pct','—')}%  "
                     f"cat>10%={cur.get('catastrophic_gt10pct_pct','—')}%")
    if sec["stop_best_policy"]:
        name, m = sec["stop_best_policy"]
        lines.append(f"  BEST policy      {name}  expectancy={m['expectancy_pct']:+.3f}%  "
                     f"WR={m['wr_pct']}%  PF={m.get('profit_factor','—')}  "
                     f"cat>10%={m['catastrophic_gt10pct_pct']}%")
        if cur.get("expectancy_pct") is not None:
            gap = round(m["expectancy_pct"] - cur["expectancy_pct"], 3)
            lines.append(f"  Expectancy gap:  {gap:+.3f}% vs CURRENT")
    lines.append(f"  Avg MAE:         {_fmt(sec['avg_mae_pct'],3,'%')}  "
                 f"(the average dip before recovery or stop)")
    lines.append(f"")

    # WINNERS
    lines.append(f"WINNERS (fwd_5d > +0.5%)")
    if sec["cohort_winner"].get("n"):
        w = sec["cohort_winner"]
        lines.append(f"  n={w['n']}")
        if w.get("runners"):
            top_runner = list(w["runners"].items())[0]
            lines.append(f"  Dominant runner: {top_runner[0]} ({top_runner[1].get('pct')}%)")
        if w.get("bands"):
            top_band = list(w["bands"].items())[0]
            lines.append(f"  Dominant band:   {top_band[0]} ({top_band[1].get('pct')}%)")
        wc = w.get("confidence_stats", {}) or {}
        if wc.get("avg") is not None:
            lines.append(f"  Avg confidence:  {wc['avg']}%")
        lines.append(f"  Avg MFE:         {w.get('mfe_pct_avg')}%")
        lines.append(f"  Avg MAE:         {w.get('mae_pct_avg')}%")
    lines.append(f"")

    # LOSERS
    lines.append(f"LOSERS (fwd_5d < -0.5%)")
    if sec["cohort_loser"].get("n"):
        l = sec["cohort_loser"]
        lines.append(f"  n={l['n']}")
        if l.get("runners"):
            top_runner = list(l["runners"].items())[0]
            lines.append(f"  Dominant runner: {top_runner[0]} ({top_runner[1].get('pct')}%)")
        if l.get("bands"):
            top_band = list(l["bands"].items())[0]
            lines.append(f"  Dominant band:   {top_band[0]} ({top_band[1].get('pct')}%)")
        lc = l.get("confidence_stats", {}) or {}
        if lc.get("avg") is not None:
            wc = sec["cohort_winner"].get("confidence_stats", {}) or {}
            delta = round(lc["avg"] - wc.get("avg", 0), 2) if wc.get("avg") is not None else "—"
            lines.append(f"  Avg confidence:  {lc['avg']}%  (winners {wc.get('avg','—')}% · "
                         f"delta {delta})")
        lines.append(f"  Avg MFE:         {l.get('mfe_pct_avg')}%")
        lines.append(f"  Avg MAE:         {l.get('mae_pct_avg')}%")
        lines.append(f"")
        lines.append(f"  Loss rate:       {sec['loss_rate_pct']}%")
        lines.append(f"  Preventable %:   {sec['preventable_pct']}%")
        lines.append(f"  Loss classification (avoidability):")
        for k, v in sec["loss_classification"].items():
            lines.append(f"    {k:32s} {v}")
        lines.append(f"")
        lines.append(f"  Top anti-signals in loser cohort:")
        for k, v in list(sec["loss_anti_signals"].items())[:6]:
            lines.append(f"    {k:40s} {v}")
    lines.append(f"")

    # MISSED WINNERS
    if sec.get("capture_rate_pct") is not None:
        lines.append(f"MISSED WINNERS (universe scan, >=+5% fwd_5d)")
        lines.append(f"  Universe size:    {sec['universe_size']}")
        lines.append(f"  Capture rate:     {sec['capture_rate_pct']}%")
        lines.append(f"  Big winners missed: {sec['n_big_winners_missed']}")
        lines.append(f"")

    # SCORE USEFULNESS
    lines.append(f"SCORE USEFULNESS (KEEP / PRUNE verdict)")
    for name, a in sec["score_verdicts"].items():
        v = a.get("verdict")
        spread = a.get("wr_spread_pp")
        mono = a.get("monotonicity")
        lines.append(f"  {name:22s} verdict={v:20s} "
                     f"spread={spread}pp  monotonicity={mono}")
    lines.append(f"")

    return "\n".join(lines)


def build_ai_hypotheses(root: Path) -> list:
    """Compact list drawn from mr_ai_auditor_findings.jsonl."""
    findings = _load_jsonl(root, "mr_ai_auditor_findings.jsonl")
    return [{
        "id":       f["finding_id"],
        "severity": f["severity"],
        "market":   f["market"],
        "claim":    f["claim"],
        "caveat":   f["caveat"],
    } for f in findings]


def build_validated_changes(root: Path) -> list:
    """Read tickets/INDEX.json — every ticket is DRAFT; nothing is validated
    for production until walk-forward gate passes."""
    idx = _load(root, "tickets/INDEX.json")
    return idx.get("tickets", []) if isinstance(idx, dict) else []


def render_full_text(root: Path) -> str:
    parts = []
    parts.append(f"\n=====================================================================")
    parts.append(f"       AEGIS · FORWARD VALIDATION ENGINE v1 · CEO DASHBOARD (M1)")
    parts.append(f"=====================================================================")
    parts.append(f"generated_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    parts.append(f"engine:        {ENGINE_ID}")
    parts.append(f"status:        FOUNDATION COMPLETE · INTEGRATION DEFERRED")
    parts.append(f"locked layers: UNTOUCHED (R1, R2, XLSX contract, canonical JSON, "
                 f"ensemble weights)\n")
    for market in ("india","usa"):
        sec = build_market_section(root, market)
        parts.append(_render_market_text(sec))

    # AI HYPOTHESES
    parts.append(f"\n=====================================================================")
    parts.append(f"  AI HYPOTHESES (proposes only · never applies)")
    parts.append(f"=====================================================================\n")
    hyps = build_ai_hypotheses(root)
    for h in hyps:
        parts.append(f"  [{h['id']}] {h['severity']:8s} {h['market']}")
        parts.append(f"    CLAIM  : {h['claim']}")
        parts.append(f"    CAVEAT : {h['caveat']}")
        parts.append(f"")

    # TOP HYPOTHESES SHORTLIST
    shortlist = _load(root, "mr_hypothesis_shortlist.json")
    if shortlist and shortlist.get("shortlist"):
        parts.append(f"\n=====================================================================")
        parts.append(f"  TOP HYPOTHESES · walk-forward candidates (n={shortlist['top_n']})")
        parts.append(f"=====================================================================\n")
        parts.append(f"  Ranked by: severity*3 + verdict*2 + evidence*1 + preventability*2")
        parts.append(f"  Considered: {shortlist['n_tickets_considered']} DRAFT tickets\n")
        for r in shortlist["shortlist"]:
            parts.append(f"  #{r['rank']} · score {r['score']}  ·  {r['market']}  ·  {r['severity']}")
            parts.append(f"    ticket:      {r['ticket_id']}")
            parts.append(f"    title:       {r['title']}")
            parts.append(f"    n_evidence:  {r['n_evidence']}  ·  verdict: {r['verdict']}")
            parts.append(f"    hypothesis:  {r['hypothesis'][:200]}")
            parts.append(f"")

    # WALK-FORWARD EXPERIMENTS
    exp_idx = _load(root, "experiments/INDEX.json")
    if exp_idx and exp_idx.get("experiments"):
        parts.append(f"\n=====================================================================")
        parts.append(f"  WALK-FORWARD EXPERIMENTS · registry")
        parts.append(f"=====================================================================\n")
        for e in exp_idx["experiments"]:
            parts.append(f"  · {e['experiment_id']}")
            parts.append(f"      market:    {e['market']}")
            parts.append(f"      metric:    {e['metric']}")
            parts.append(f"      min N:     {e['min_sample_size']}")
            parts.append(f"      window:    {e['observation_window_days']} days")
            parts.append(f"      status:    {e['current_status']} (never auto-runs)")
            parts.append(f"")

    # VALIDATED CHANGES
    parts.append(f"\n=====================================================================")
    parts.append(f"  VALIDATED CHANGES  (production-promoted proposals)")
    parts.append(f"=====================================================================\n")
    tickets = build_validated_changes(root)
    if not tickets:
        parts.append(f"  None yet.\n")
    else:
        n_validated = sum(1 for t in tickets if t.get("status") != "DRAFT")
        if n_validated == 0:
            parts.append(f"  None yet.")
            parts.append(f"  {len(tickets)} DRAFT ticket(s) awaiting CEO review + "
                         f"walk-forward gate:")
            for t in tickets:
                parts.append(f"    · {t['ticket_id']}")
                parts.append(f"      title:    {t['title']}")
                parts.append(f"      market:   {t['market']}")
                parts.append(f"      n_evid:   {t['n_evidence']}")
                parts.append(f"      verdict:  {t['statistical_verdict']}")
                parts.append(f"      status:   {t['status']} (never auto-promoted)")
                parts.append(f"")
    parts.append(f"=====================================================================")
    parts.append(f"                            END OF DASHBOARD")
    parts.append(f"=====================================================================\n")
    return "\n".join(parts)


def render_markdown(text: str) -> str:
    """Wrap the text output in code fences for a stable-format markdown dashboard."""
    return (f"# AEGIS · Forward Validation Engine v1 · CEO Dashboard (M1)\n\n"
            f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}._\n\n"
            f"```\n{text}\n```\n")


def emit(root: Path, text: str, md: str) -> tuple:
    t_p = root / ALLOWED_WRITE_ROOT / "CEO_DASHBOARD_M1.txt"
    m_p = root / ALLOWED_WRITE_ROOT / "CEO_DASHBOARD_M1.md"
    t_p.write_text(text, encoding="utf-8")
    m_p.write_text(md, encoding="utf-8")
    return (t_p, m_p)


if __name__ == "__main__":
    root = Path(".").resolve()
    text = render_full_text(root)
    md = render_markdown(text)
    t_p, m_p = emit(root, text, md)
    print(text)
    print(f"\n[ceo_dashboard] wrote {t_p.name} + {m_p.name}")
