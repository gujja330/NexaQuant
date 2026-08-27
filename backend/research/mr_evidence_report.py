"""AEGIS · Sprint M-R · Compact Daily Evidence Report.

CEO handover 2026-08-27:
> "Build one compact daily research report. I would want one table like:
>  | Experiment | Forward N | Baseline WR | Experiment WR | Δ WR |
>    Avg return | Status |
>  No storytelling. Just evidence."

Reads the walk-forward scored files under reports/research/walkforward/,
joins them against each frozen experiment's daily shadow output, and
produces exactly the compact table CEO specified. No narrative.

Status column values:
  ACCUMULATING   · forward N < 100
  READY_TO_JUDGE · forward N >= 100 and acceptance evaluation not run yet
  PASSED         · promotion evaluation passed
  FAILED         · promotion evaluation failed / rejected
  NEED_DATA      · zero forward observations at any horizon yet

Under M-R sandbox rules. Zero production side effects.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean

from backend.research.mr_runner import ALLOWED_WRITE_ROOT
from backend.research.mr_experiment_runner import FOCUSED_EXPERIMENTS

ENGINE_ID = "aegis.mr_evidence_report.v0.1"

TARGET_N = 100
WIN = 0.5
LOSS = -0.5


def _load_shadow_rows(root: Path, experiment_id: str) -> list:
    """Read every shadow.jsonl for an experiment across all dates."""
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments" / experiment_id
    if not exp_dir.exists(): return []
    rows = []
    for d_dir in sorted(exp_dir.iterdir()):
        if not d_dir.is_dir(): continue
        for shadow_p in d_dir.glob("shadow*.jsonl"):
            for ln in shadow_p.read_text(encoding="utf-8").splitlines():
                if not ln.strip(): continue
                try: rows.append(json.loads(ln))
                except Exception: continue
    return rows


def _load_scored_lookup(root: Path) -> dict:
    """Build a {(snap_date, market, ticker) → scored_row} lookup from
    every walk-forward *_scored_fwd5d.jsonl."""
    wf_dir = root / ALLOWED_WRITE_ROOT / "walkforward"
    if not wf_dir.exists(): return {}
    lookup: dict = {}
    for d_dir in sorted(wf_dir.iterdir()):
        if not d_dir.is_dir(): continue
        snap = d_dir.name
        for scored_p in d_dir.glob("*_scored_fwd5d.jsonl"):
            market = scored_p.stem.split("_")[0].upper()
            for ln in scored_p.read_text(encoding="utf-8").splitlines():
                if not ln.strip(): continue
                try:
                    r = json.loads(ln)
                    tk = str(r.get("ticker","")).upper()
                    if tk: lookup[(snap, market, tk)] = r
                except Exception: continue
    return lookup


def _baseline_wr_avg(root: Path, market: str) -> tuple:
    """Historical 30D baseline (5D WR + avg) from mr_prediction_autopsy summary."""
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_summary.json"
    if not p.exists(): return (None, None)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        f5 = (d.get("cohort_ALL") or {}).get("fwd_5d", {})
        return (f5.get("win_rate_pct"), f5.get("avg_pct"))
    except Exception:
        return (None, None)


def _operator_status(current: str) -> str:
    """CEO 2026-08-27 · map internal states to compact operator labels."""
    if current in ("NEED_DATA","ACCUMULATING"): return "SHADOW"
    if current == "READY_TO_JUDGE": return "READY"
    if current == "PASSED": return "PROMOTABLE"
    if current == "FAILED": return "REJECTED"
    return "SHADOW"


def _evaluate_experiment(root: Path, experiment_id: str,
                         scored_lookup: dict,
                         market_filter: str = None) -> dict:
    """Join shadow decisions to scored outcomes and compute metrics.
       market_filter='INDIA' or 'USA' scopes to a single market for
       cross-market experiments (E3)."""
    shadow_rows = _load_shadow_rows(root, experiment_id)
    if market_filter:
        shadow_rows = [r for r in shadow_rows
                        if str(r.get("market","")).upper() == market_filter.upper()]
    fired_scored = []
    for r in shadow_rows:
        if not r.get("rule_fired"): continue
        snap = r.get("iso")
        market = str(r.get("market","")).upper()
        tk = str(r.get("ticker","")).upper()
        key = (snap, market, tk)
        if key in scored_lookup:
            scored = scored_lookup[key]
            fwd5 = scored.get("fwd_5d_pct")
            if isinstance(fwd5, (int, float)):
                fired_scored.append({
                    "ticker":   tk,
                    "market":   market,
                    "snap":     snap,
                    "shadow":   r.get("shadow_decision"),
                    "fwd_5d":   fwd5,
                    "mfe":      scored.get("mfe_pct_h5d"),
                    "mae":      scored.get("mae_pct_h5d"),
                    "outcome":  scored.get("outcome_label"),
                    "stop_hit": scored.get("stop_hit_within_h5d"),
                })
    n = len(fired_scored)
    if n == 0:
        # Determine total shadow rows so we can still say something
        fired = sum(1 for r in shadow_rows if r.get("rule_fired"))
        return {
            "forward_n":      0,
            "fired_total":    fired,
            "shadow_days":    len({r.get("iso") for r in shadow_rows if r.get("iso")}),
            "wr_pct":         None,
            "avg_pct":        None,
            "delta_wr_pp":    None,
            "status":         "NEED_DATA",
        }
    wins = sum(1 for r in fired_scored if r["fwd_5d"] > WIN)
    losses = sum(1 for r in fired_scored if r["fwd_5d"] < LOSS)
    wr = round(wins / n * 100, 2)
    avg = round(mean(r["fwd_5d"] for r in fired_scored), 3)
    # Market for baseline
    market_counter = Counter(r["market"] for r in fired_scored)
    dom_market = market_counter.most_common(1)[0][0].lower() if market_counter else "india"
    base_wr, base_avg = _baseline_wr_avg(root, dom_market)
    delta_wr = round(wr - (base_wr or 0), 2) if base_wr is not None else None
    if n >= TARGET_N:
        status = "READY_TO_JUDGE"
    else:
        status = "ACCUMULATING"
    return {
        "forward_n":      n,
        "fired_total":    sum(1 for r in shadow_rows if r.get("rule_fired")),
        "shadow_days":    len({r.get("iso") for r in shadow_rows if r.get("iso")}),
        "wr_pct":         wr,
        "avg_pct":        avg,
        "wins":           wins,
        "losses":         losses,
        "delta_wr_pp":    delta_wr,
        "baseline_wr_pct": base_wr,
        "baseline_avg_pct": base_avg,
        "dominant_market": dom_market.upper(),
        "status":         status,
    }


def build(root: Path) -> dict:
    scored_lookup = _load_scored_lookup(root)
    rows = []
    for exp_id in FOCUSED_EXPERIMENTS:
        # CEO 2026-08-27 · E3 splits into India + USA rows for reporting
        if "e3_stop_loss_cross_market" in exp_id:
            for mkt, label in (("INDIA","E3 India stop"),
                                ("USA","E3 USA trailing")):
                m = _evaluate_experiment(root, exp_id, scored_lookup,
                                          market_filter=mkt)
                m["operator_status"] = _operator_status(m["status"])
                rows.append({"experiment_id": exp_id,
                             "display_name": label,
                             "market_scope": mkt,
                             **m})
        else:
            m = _evaluate_experiment(root, exp_id, scored_lookup)
            m["operator_status"] = _operator_status(m["status"])
            # Human display name
            if "e1_india_r1_filter" in exp_id:
                dn = "E1 R1 filter"
            elif "e2_india_r2_rank_4_7_boost" in exp_id:
                dn = "E2 R2 boost"
            else:
                dn = exp_id.replace("aegis_mr_experiment_20260827_","")
            rows.append({"experiment_id": exp_id,
                         "display_name": dn,
                         **m})
    return {
        "engine":         ENGINE_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_date": date.today().isoformat(),
        "target_n":       TARGET_N,
        "scored_lookup_size": len(scored_lookup),
        "rows":           rows,
    }


def _fmt(v, digits=2, suffix=""):
    if v is None: return "—"
    if isinstance(v, (int, float)): return f"{v:.{digits}f}{suffix}"
    return str(v)


def render_markdown(res: dict) -> str:
    L = []
    L.append(f"# AEGIS · Compact Daily Evidence Report\n")
    L.append(f"_Sprint M-R · Frozen experiments only · {res['generated_date']}_\n")
    # CEO 2026-08-27 · exact column labels
    L.append(f"| Experiment | Forward N | WR | Avg return | Baseline | Edge | Status |")
    L.append(f"|---|---:|---:|---:|---:|---:|:---|")
    for r in res["rows"]:
        name = r.get("display_name") or r["experiment_id"].replace(
            "aegis_mr_experiment_20260827_","")
        fwd = (f"accumulating ({r['forward_n']}/{res['target_n']})"
               if r['forward_n'] < res['target_n']
               else f"{r['forward_n']}/{res['target_n']}")
        L.append(f"| {name} | {fwd} | "
                 f"{_fmt(r.get('wr_pct'),2,'%')} | "
                 f"{_fmt(r.get('avg_pct'),3,'%')} | "
                 f"{_fmt(r.get('baseline_wr_pct'),2,'%')} | "
                 f"{_fmt(r.get('delta_wr_pp'),2,'pp')} | "
                 f"{r.get('operator_status','SHADOW')} |")
    L.append(f"\n**Target sample per experiment:** N ≥ {res['target_n']}")
    L.append(f"**Scored-lookup depth:** {res['scored_lookup_size']} matured "
             f"(snap_date, market, ticker) forward observations")
    L.append(f"**Locked · zero production changes · zero storytelling.**")
    return "\n".join(L)


def render_text(res: dict) -> str:
    L = []
    L.append(f"\n===================================================================")
    L.append(f"  AEGIS · Compact Daily Evidence Report · {res['generated_date']}")
    L.append(f"===================================================================\n")
    L.append(f"  {'Experiment':22s} {'Fwd N':>22s} {'WR':>7s} "
             f"{'Avg':>8s} {'Base':>7s} {'Edge':>8s} Status")
    L.append(f"  {'-'*22} {'-'*22} {'-'*7} {'-'*8} {'-'*7} {'-'*8} " + "-"*11)
    for r in res["rows"]:
        name = (r.get("display_name") or r["experiment_id"].replace(
            "aegis_mr_experiment_20260827_",""))[:22]
        fwd_s = (f"accumulating ({r['forward_n']}/{res['target_n']})"
                 if r['forward_n'] < res['target_n']
                 else f"{r['forward_n']}/{res['target_n']}")
        L.append(f"  {name:22s} {fwd_s:>22s} "
                 f"{_fmt(r.get('wr_pct'),1,'%'):>7s} "
                 f"{_fmt(r.get('avg_pct'),2,'%'):>8s} "
                 f"{_fmt(r.get('baseline_wr_pct'),1,'%'):>7s} "
                 f"{_fmt(r.get('delta_wr_pp'),1,'pp'):>8s} "
                 f"{r.get('operator_status','SHADOW')}")
    L.append(f"\n  target N per experiment = {res['target_n']}")
    L.append(f"  scored-lookup depth = {res['scored_lookup_size']}")
    L.append(f"  locked · zero production changes\n")
    return "\n".join(L)


def emit(root: Path, res: dict, md: str, txt: str) -> tuple:
    p_md = root / ALLOWED_WRITE_ROOT / "EVIDENCE_REPORT.md"
    p_tx = root / ALLOWED_WRITE_ROOT / "EVIDENCE_REPORT.txt"
    p_json = root / ALLOWED_WRITE_ROOT / "mr_evidence_report.json"
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
    print(f"\n[evidence_report] -> {p_md.name} + {p_tx.name} + {p_json.name}")
