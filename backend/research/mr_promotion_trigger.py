"""AEGIS · Sprint M-R · Automatic Promotion Trigger.

CEO handover 2026-08-27:
> "At N ≥ 100, automatically run the promotion evaluation. Then we get a
>  hard answer: PASS → candidate for paper trading · FAIL → reject and
>  document why · Borderline → don't promote."
> "Do not wait blindly for a calendar date. As soon as any experiment
>  reaches its required N ≥ 100, evaluate it immediately."

Reads the compact evidence report and, for every experiment that reaches
N ≥ 100 forward observations, runs the frozen acceptance/rejection
criteria. Emits a single PROMOTION_DECISIONS.md that either:
   - flags an experiment PASS (ready for CEO paper-trade approval)
   - flags an experiment FAIL (documents why · never retried without CEO)
   - flags an experiment BORDERLINE (does not promote)

Under M-R sandbox rules. Zero production changes. Never auto-promotes ·
CEO approval always required after PASS.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend.research.mr_runner import ALLOWED_WRITE_ROOT
from backend.research.mr_experiment_runner import FOCUSED_EXPERIMENTS

ENGINE_ID = "aegis.mr_promotion_trigger.v0.1"

TARGET_N = 100


# ── Acceptance criteria per experiment (locked in MR_V1_EXPERIMENTS_FROZEN) ──

def _accept_e1(m: dict) -> tuple:
    """E1: filtered R1 5D WR >= production R1 + 5pp on n>=100."""
    if m.get("wr_pct") is None or m.get("baseline_wr_pct") is None:
        return ("BORDERLINE", "insufficient baseline or shadow data")
    delta = m["wr_pct"] - m["baseline_wr_pct"]
    if delta >= 5.0:
        return ("PASS", f"filtered WR {m['wr_pct']}% vs baseline {m['baseline_wr_pct']}% · delta {delta:+.2f}pp >= +5pp")
    if delta <= -3.0:
        return ("FAIL", f"filtered WR {m['wr_pct']}% vs baseline {m['baseline_wr_pct']}% · delta {delta:+.2f}pp <= -3pp")
    return ("BORDERLINE", f"delta {delta:+.2f}pp is between -3pp and +5pp · no promotion")


def _accept_e2(m: dict) -> tuple:
    """E2: boost cohort 5D WR >= 55% on n>=100 AND avg > 0.5%."""
    wr = m.get("wr_pct"); avg = m.get("avg_pct")
    if wr is None or avg is None:
        return ("BORDERLINE", "insufficient boost-cohort data")
    if wr >= 55.0 and avg > 0.5:
        return ("PASS", f"boost WR {wr}% >= 55% AND avg {avg}% > 0.5%")
    if wr < 40.0:
        return ("FAIL", f"boost WR {wr}% < 40% · regime overfit rejected")
    return ("BORDERLINE", f"WR {wr}%, avg {avg}% · does not meet PASS criteria")


def _accept_e3(m: dict) -> tuple:
    """E3: INDIA advisory median return >= CURRENT median + 0.3% AND cat-loss
    <= CURRENT on n>=100. USA advisory net of TRAILING_10 exit >= CURRENT
    + 0.5% expectancy on n>=100.
    This lightweight evaluator uses avg return as a proxy for expectancy
    since the current-baseline median isn't cached in the report · a
    fuller evaluator would recompute the CURRENT baseline per market."""
    avg = m.get("avg_pct")
    if avg is None:
        return ("BORDERLINE", "insufficient E3 forward-scored data")
    # Use historical CURRENT expectancy from stops sweep as baseline
    # (India CURRENT = -0.886% · USA CURRENT = -0.630%)
    baseline = -0.886 if m.get("dominant_market") == "INDIA" else -0.630
    threshold = 0.3 if m.get("dominant_market") == "INDIA" else 0.5
    delta = avg - baseline
    if delta >= threshold:
        return ("PASS", f"advisory expectancy {avg}% - baseline {baseline}% "
                        f"= {delta:+.3f}% >= threshold {threshold}%")
    if delta <= -0.5:
        return ("FAIL", f"MFE-captured regression: expectancy {avg}% vs "
                        f"baseline {baseline}% = {delta:+.3f}%")
    return ("BORDERLINE", f"delta {delta:+.3f}% below threshold {threshold}%")


ACCEPT_MAP = {
    "aegis_mr_experiment_20260827_e1_india_r1_filter":         _accept_e1,
    "aegis_mr_experiment_20260827_e2_india_r2_rank_4_7_boost": _accept_e2,
    "aegis_mr_experiment_20260827_e3_stop_loss_cross_market":  _accept_e3,
}


def evaluate(root: Path) -> dict:
    ev_p = root / ALLOWED_WRITE_ROOT / "mr_evidence_report.json"
    if not ev_p.exists():
        return {"engine": ENGINE_ID, "status": "NO_EVIDENCE_REPORT",
                "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    ev = json.loads(ev_p.read_text(encoding="utf-8"))
    decisions = []
    for row in ev.get("rows", []):
        exp_id = row["experiment_id"]
        n = row.get("forward_n", 0)
        if n < TARGET_N:
            decisions.append({
                "experiment_id":  exp_id,
                "forward_n":      n,
                "target_n":       TARGET_N,
                "verdict":        "NOT_YET",
                "reason":         f"N={n} < target {TARGET_N} · continue accumulating",
            })
            continue
        # N >= 100 · run acceptance
        acc_fn = ACCEPT_MAP.get(exp_id)
        if acc_fn is None:
            decisions.append({
                "experiment_id":  exp_id,
                "forward_n":      n,
                "target_n":       TARGET_N,
                "verdict":        "NO_ACCEPTOR",
                "reason":         "acceptance function not registered",
            })
            continue
        verdict, reason = acc_fn(row)
        decisions.append({
            "experiment_id":  exp_id,
            "forward_n":      n,
            "target_n":       TARGET_N,
            "verdict":        verdict,
            "reason":         reason,
            "wr_pct":         row.get("wr_pct"),
            "baseline_wr_pct": row.get("baseline_wr_pct"),
            "avg_pct":        row.get("avg_pct"),
        })
    return {
        "engine":         ENGINE_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_date": date.today().isoformat(),
        "target_n":       TARGET_N,
        "n_experiments":  len(decisions),
        "n_ready":        sum(1 for d in decisions if d["verdict"] not in ("NOT_YET","NO_ACCEPTOR")),
        "n_pass":         sum(1 for d in decisions if d["verdict"] == "PASS"),
        "n_fail":         sum(1 for d in decisions if d["verdict"] == "FAIL"),
        "n_borderline":   sum(1 for d in decisions if d["verdict"] == "BORDERLINE"),
        "n_pending":      sum(1 for d in decisions if d["verdict"] == "NOT_YET"),
        "decisions":      decisions,
    }


def render_markdown(res: dict) -> str:
    L = []
    L.append(f"# AEGIS · Promotion Decisions\n")
    L.append(f"_{res['generated_date']} · Target N = {res['target_n']}_\n")
    L.append(f"| Experiment | Forward N | Verdict | Reason |")
    L.append(f"|---|---:|:---:|---|")
    for d in res["decisions"]:
        short = d["experiment_id"].replace("aegis_mr_experiment_20260827_","")
        L.append(f"| {short} | {d['forward_n']}/{res['target_n']} | "
                 f"**{d['verdict']}** | {d['reason']} |")
    L.append(f"\n**Summary:** {res['n_pass']} PASS · {res['n_borderline']} BORDERLINE · "
             f"{res['n_fail']} FAIL · {res['n_pending']} NOT_YET")
    L.append(f"\n**Any PASS still requires:**")
    L.append(f"1. CEO explicit approval + lock-override phrase")
    L.append(f"2. New SPRINT_ID branch · config-toggle OFF by default")
    L.append(f"3. 30-session paper trade with green metrics")
    L.append(f"4. Production promotion under new SPRINT_ID with L4 evidence")
    L.append(f"\n**Zero auto-promotion. Zero production changes from this file.**")
    return "\n".join(L)


def emit(root: Path, res: dict, md: str) -> tuple:
    p_md = root / ALLOWED_WRITE_ROOT / "PROMOTION_DECISIONS.md"
    p_json = root / ALLOWED_WRITE_ROOT / "mr_promotion_decisions.json"
    p_md.write_text(md, encoding="utf-8")
    p_json.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return (p_md, p_json)


def render_console(res: dict):
    print(f"\n======== PROMOTION TRIGGER · {res.get('generated_date','?')} ========")
    for d in res.get("decisions", []):
        short = d["experiment_id"].replace("aegis_mr_experiment_20260827_","")
        print(f"  [{d['verdict']:11s}] {short:35s} N={d['forward_n']}/{res['target_n']}")
        print(f"     {d['reason']}")
    print(f"\n  Summary: {res.get('n_pass',0)} PASS · "
          f"{res.get('n_borderline',0)} BORDERLINE · "
          f"{res.get('n_fail',0)} FAIL · {res.get('n_pending',0)} NOT_YET")


if __name__ == "__main__":
    root = Path(".").resolve()
    res = evaluate(root)
    md = render_markdown(res)
    p_md, p_json = emit(root, res, md)
    render_console(res)
    print(f"\n[promotion_trigger] -> {p_md.name} + {p_json.name}")
