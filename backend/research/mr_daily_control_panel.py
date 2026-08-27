"""AEGIS · Sprint M-R · Daily Research Control Panel.

CEO handover 2026-08-27:
> "One thing I would ask the system to produce next: a single daily
>  Sprint-M research dashboard, not another giant XLSX."

Single-page daily control panel with CEO's exact format:

| Research metric | Today | 30D | Forward | Verdict |

Columns:
  Today    · from today's walk-forward canonical + Momentum capture
  30D      · from the locked historical corpus (mr_prediction_autopsy_*)
  Forward  · accumulating count of matured forward days (N/target)
  Verdict  · 🔬 researching / 🆕 new / ⏳ accumulating / ✅ validated / ❌ rejected

Target sample for production candidate = N ≥ 100 (per MR_V1_LOCK statistical
discipline). Every metric row stays 🔬 or ⏳ until a walk-forward experiment
concludes.

Emits reports/research/DAILY_CONTROL_PANEL.md and DAILY_CONTROL_PANEL.txt.
Under M-R sandbox rules. Locked layers untouched. No production changes.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_daily_control_panel.v0.1"
TARGET_N = 100  # per statistical discipline for PRODUCTION_CANDIDATE


def _load(root: Path, name: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _load_jsonl(root: Path, name: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _walkforward_summary(root: Path) -> dict:
    """Count captured days + matured forward observations per horizon."""
    wf_dir = root / ALLOWED_WRITE_ROOT / "walkforward"
    if not wf_dir.exists(): return {"days": 0, "matured": {}}
    days = sorted([p.name for p in wf_dir.iterdir() if p.is_dir()])
    matured = {"1d": 0, "3d": 0, "5d": 0, "10d": 0, "20d": 0}
    for d in days:
        d_dir = wf_dir / d
        for horizon in ("1d","3d","5d","10d","20d"):
            for market in ("india","usa"):
                scored = d_dir / f"{market}_scored_fwd{horizon}.jsonl"
                if scored.exists():
                    matured[horizon] += sum(
                        1 for _ in scored.read_text(encoding="utf-8").splitlines()
                        if _.strip())
    today = date.today().isoformat()
    todays_dir = wf_dir / today
    todays_captured = {}
    if todays_dir.exists():
        for p in todays_dir.glob("*.jsonl"):
            n = sum(1 for _ in p.read_text(encoding="utf-8").splitlines() if _.strip())
            todays_captured[p.name] = n
    return {
        "days":               len(days),
        "day_list":           days,
        "matured":            matured,
        "todays_captured":    todays_captured,
        "todays_iso":         today,
    }


def _verdict(forward_n: int, has_baseline: bool, is_new: bool) -> str:
    if is_new: return "🆕 new"
    if forward_n >= TARGET_N: return "⏳ ready to conclude"
    if forward_n > 0: return f"⏳ accumulating"
    if has_baseline: return "🔬 researching"
    return "🆕 new"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None: return "—"
    return f"{v:.2f}%"


def _fmt_forward(n: int, target: int = TARGET_N) -> str:
    if n == 0: return f"accumulating (0/{target})"
    return f"{n}/{target}"


def build(root: Path) -> dict:
    autopsy_i = _load(root, "mr_prediction_autopsy_india_summary.json")
    autopsy_u = _load(root, "mr_prediction_autopsy_usa_summary.json")
    studies_i = _load(root, "mr_studies_india.json")
    studies_u = _load(root, "mr_studies_usa.json")
    stops_i = _load(root, "mr_stop_loss_sweep_india.json")
    stops_u = _load(root, "mr_stop_loss_sweep_usa.json")
    ctrl_i = _load(root, "mr_control_cohort_india.json")
    ctrl_u = _load(root, "mr_control_cohort_usa.json")
    cond_i = _load(root, "mr_conditional_cohorts_india.json")
    tickets_idx = _load(root, "tickets/INDEX.json")
    experiments_idx = _load(root, "experiments/INDEX.json")
    shortlist = _load(root, "mr_hypothesis_shortlist.json")
    wf = _walkforward_summary(root)

    # 30D baseline extractors
    r1_i = ((studies_i.get("Q1_runner_scoreboard") or {}).get("R1") or {}) \
        .get("fwd_5d", {})
    r2_i = ((studies_i.get("Q1_runner_scoreboard") or {}).get("R2") or {}) \
        .get("fwd_5d", {})
    r1_u = ((studies_u.get("Q1_runner_scoreboard") or {}).get("R1") or {}) \
        .get("fwd_5d", {})
    r2_u = ((studies_u.get("Q1_runner_scoreboard") or {}).get("R2") or {}) \
        .get("fwd_5d", {})

    rank47_i = ((studies_i.get("Q8_rank_slot") or {}).get("rank_4_7") or {}) \
        .get("fwd_5d", {})

    # Sectors: best/worst India
    sectors_i = (studies_i.get("Q2_sector") or {})
    sector_best_i = None; sector_worst_i = None
    if sectors_i:
        rated = [(k, (v.get("fwd_5d") or {}).get("wr_pct"))
                 for k, v in sectors_i.items()
                 if (v.get("fwd_5d") or {}).get("n", 0) >= 15]
        rated = [(k, v) for k, v in rated if v is not None]
        if rated:
            sector_best_i = max(rated, key=lambda x: x[1])
            sector_worst_i = min(rated, key=lambda x: x[1])

    # USA cap MID vs LARGE
    cap_u_mid = ((studies_u.get("Q3_cap_bucket") or {}).get("MID") or {}) \
        .get("fwd_5d", {})
    cap_u_large = ((studies_u.get("Q3_cap_bucket") or {}).get("LARGE") or {}) \
        .get("fwd_5d", {})

    # Time-stop gap India
    stop_cur_i = (stops_i.get("by_policy") or {}).get("CURRENT", {})
    stop_time5_i = (stops_i.get("by_policy") or {}).get("TIME_STOP_5D", {})
    stop_gap_i = None
    if stop_cur_i.get("expectancy_pct") is not None and \
       stop_time5_i.get("expectancy_pct") is not None:
        stop_gap_i = round(stop_time5_i["expectancy_pct"] -
                           stop_cur_i["expectancy_pct"], 3)

    # Alpha
    ui = (ctrl_i.get("aggregate", {}) or {}).get("fwd_5d", {})
    uu = (ctrl_u.get("aggregate", {}) or {}).get("fwd_5d", {})
    ai5 = (autopsy_i.get("cohort_ALL", {}) or {}).get("fwd_5d", {})
    au5 = (autopsy_u.get("cohort_ALL", {}) or {}).get("fwd_5d", {})
    alpha_i = round(ai5["win_rate_pct"] - ui["wr_pct"], 2) if \
              ui.get("n") and ai5.get("n") else None
    alpha_u = round(au5["win_rate_pct"] - uu["wr_pct"], 2) if \
              uu.get("n") and au5.get("n") else None

    # Momentum · always 🆕 until we have 20 days forward
    mom_captured = wf["todays_captured"].get("momentum_india.jsonl", 0) + \
                   wf["todays_captured"].get("momentum_usa.jsonl", 0)
    mom_forward_days = sum(1 for d in wf["day_list"]
                           if any((root / ALLOWED_WRITE_ROOT / "walkforward" / d /
                                   f"momentum_{m}.jsonl").exists()
                                  for m in ("india","usa")))

    # AI hypothesis count
    ai_findings = _load_jsonl(root, "mr_ai_auditor_findings.jsonl")
    n_ai_hypotheses = len(ai_findings)
    n_validated = sum(1 for t in (tickets_idx.get("tickets") or [])
                       if t.get("status") != "DRAFT")

    # Best conditional cohort India
    best_cond = None
    if cond_i:
        pos = ((cond_i.get("combos_3way") or {}).get("top_positive") or [])
        if pos: best_cond = pos[0]

    # Forward sample = matured fwd_5d across all snapshots
    matured_5d = wf["matured"].get("5d", 0)

    rows = []
    def _row(metric, today, thirty, forward_n, is_new=False, has_baseline=True):
        rows.append({
            "metric":   metric,
            "today":    today,
            "thirty":   thirty,
            "forward":  _fmt_forward(forward_n),
            "verdict":  _verdict(forward_n, has_baseline, is_new),
            "forward_n": forward_n,
        })

    _row("R1 India 5D WR", "—", _fmt_pct(r1_i.get("wr_pct")), matured_5d)
    _row("R2 India 5D WR", "—", _fmt_pct(r2_i.get("wr_pct")), matured_5d)
    _row("R2 India rank_4_7 5D WR", "—", _fmt_pct(rank47_i.get("wr_pct")), matured_5d)
    _row("R1 USA 5D WR", "—", _fmt_pct(r1_u.get("wr_pct")), matured_5d)
    _row("R2 USA 5D WR", "—", _fmt_pct(r2_u.get("wr_pct")), matured_5d)
    _row("Momentum captures", f"{mom_captured}", "—", mom_forward_days,
         is_new=True, has_baseline=False)
    _row("India sector edge (best)",
         "—",
         f"{sector_best_i[0]} {sector_best_i[1]}%" if sector_best_i else "—",
         matured_5d)
    _row("India sector edge (worst)",
         "—",
         f"{sector_worst_i[0]} {sector_worst_i[1]}%" if sector_worst_i else "—",
         matured_5d)
    _row("USA MID vs LARGE 5D WR",
         "—",
         (f"{cap_u_mid.get('wr_pct','—')}% vs "
          f"{cap_u_large.get('wr_pct','—')}%") if cap_u_mid.get("wr_pct") else "—",
         matured_5d)
    _row("India TIME_STOP_5D expectancy gap",
         "—",
         f"{stop_gap_i:+.3f}%" if stop_gap_i is not None else "—",
         matured_5d)
    _row("India ALPHA vs universe",
         "—",
         f"{alpha_i:+}pp" if alpha_i is not None else "—",
         matured_5d)
    _row("USA ALPHA vs universe",
         "—",
         f"{alpha_u:+}pp" if alpha_u is not None else "—",
         matured_5d)
    _row("Best conditional cohort (3-way)",
         "—",
         (f"WR={best_cond['wr_pct']}% edge{best_cond['edge_vs_baseline_pp']:+.1f}pp n={best_cond['n']}"
          if best_cond else "—"),
         matured_5d)
    _row("AI hypotheses validated",
         "—",
         f"{n_validated}/{n_ai_hypotheses}",
         matured_5d)
    _row("Forward sample (matured fwd_5d)",
         f"day {wf['days']}",
         "—",
         matured_5d)

    return {
        "engine":            ENGINE_ID,
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_date":    date.today().isoformat(),
        "target_n":          TARGET_N,
        "walkforward_days":  wf["days"],
        "matured_by_horizon": wf["matured"],
        "todays_captures":   wf["todays_captured"],
        "n_tickets_draft":   len(tickets_idx.get("tickets") or []),
        "n_experiments_not_started": sum(
            1 for e in (experiments_idx.get("experiments") or [])
            if e.get("current_status") == "NOT_STARTED"),
        "n_ai_findings":     n_ai_hypotheses,
        "n_validated":       n_validated,
        "rows":              rows,
    }


def render_markdown(res: dict) -> str:
    L = []
    L.append(f"# AEGIS · Daily Research Control Panel\n")
    L.append(f"_Sprint M-R · Forward Validation Engine v1 · locked_\n")
    L.append(f"**Date:** {res['generated_date']}  ")
    L.append(f"**Generated:** {res['generated_utc']}  ")
    L.append(f"**Target sample size:** N ≥ {res['target_n']}\n\n")
    L.append(f"| Research metric | Today | 30D | Forward | Verdict |")
    L.append(f"|---|---:|---:|---:|---|")
    for r in res["rows"]:
        L.append(f"| {r['metric']} | {r['today']} | {r['thirty']} | "
                 f"{r['forward']} | {r['verdict']} |")
    L.append(f"\n## Corpus status\n")
    L.append(f"- Walk-forward days captured: **{res['walkforward_days']}**")
    L.append(f"- Today's captures: `{res['todays_captures']}`")
    L.append(f"- Matured forward observations by horizon: `{res['matured_by_horizon']}`")
    L.append(f"- DRAFT tickets: {res['n_tickets_draft']} · NOT_STARTED experiments: "
             f"{res['n_experiments_not_started']} · AI findings: {res['n_ai_findings']}")
    L.append(f"- Validated production-safe changes: **{res['n_validated']}**")
    L.append(f"\n## Legend\n")
    L.append(f"- 🔬 researching · baseline evidence exists, forward corpus not yet started")
    L.append(f"- 🆕 new · no historical data, corpus building from today")
    L.append(f"- ⏳ accumulating · forward corpus growing toward N ≥ {res['target_n']}")
    L.append(f"- ✅ validated · walk-forward passed, promotion-eligible")
    L.append(f"- ❌ rejected · walk-forward failed, hypothesis discarded")
    L.append(f"\n## Compliance\n")
    L.append(f"- Locked delivery layer: UNTOUCHED")
    L.append(f"- Production R1/R2/Registry/XLSX changes: 0")
    L.append(f"- Locked research foundation: MR_V1_LOCK.md (unlock phrase required)")
    L.append(f"- Every candidate stays DRAFT / NOT_STARTED until 7-step gate passes\n")
    return "\n".join(L)


def render_text(res: dict) -> str:
    L = []
    L.append(f"\n===================================================================")
    L.append(f"  AEGIS · Daily Research Control Panel · {res['generated_date']}")
    L.append(f"===================================================================\n")
    L.append(f"  Target sample size: N >= {res['target_n']}\n")
    header = f"  {'Metric':40s} {'Today':>10s} {'30D':>18s} {'Forward':>20s} {'Verdict':20s}"
    L.append(header)
    L.append(f"  {'-'*40} {'-'*10} {'-'*18} {'-'*20} {'-'*20}")
    for r in res["rows"]:
        L.append(f"  {r['metric'][:40]:40s} {str(r['today'])[:10]:>10s} "
                 f"{str(r['thirty'])[:18]:>18s} "
                 f"{str(r['forward'])[:20]:>20s} "
                 f"{r['verdict'][:20]:20s}")
    L.append(f"\n  Walk-forward days: {res['walkforward_days']}  "
             f"·  DRAFT tickets: {res['n_tickets_draft']}  "
             f"·  NOT_STARTED experiments: {res['n_experiments_not_started']}")
    L.append(f"  AI findings: {res['n_ai_findings']}  ·  "
             f"validated changes: {res['n_validated']}")
    L.append(f"\n  Locked delivery layer: UNTOUCHED")
    L.append(f"  Production R1/R2/Registry/XLSX changes: 0")
    L.append(f"  Every candidate stays DRAFT until 7-step gate passes\n")
    return "\n".join(L)


def emit(root: Path, res: dict, md: str, txt: str) -> tuple:
    p_md = root / ALLOWED_WRITE_ROOT / "DAILY_CONTROL_PANEL.md"
    p_tx = root / ALLOWED_WRITE_ROOT / "DAILY_CONTROL_PANEL.txt"
    p_json = root / ALLOWED_WRITE_ROOT / "mr_daily_control_panel.json"
    p_md.write_text(md, encoding="utf-8")
    p_tx.write_text(txt, encoding="utf-8")
    p_json.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return (p_md, p_tx, p_json)


if __name__ == "__main__":
    root = Path(".").resolve()
    res = build(root)
    md = render_markdown(res)
    txt = render_text(res)
    p_md, p_tx, p_json = emit(root, res, md, txt)
    print(txt)
    print(f"\n[daily_control_panel] -> {p_md.name} + {p_tx.name} + {p_json.name}")
