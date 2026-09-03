"""AEGIS · Consolidated Validation Report
Sprint A · CEO 2026-09-03 · "where is back-validation / forward-validation results?"

Aggregates every validation artifact this session produces (P0-P5, R3)
alongside prior back-tests + Sprint M-R forward validation into a single
per-market report + top-level index so the operator sees ALL evidence in
one place.

Sources (both markets · gracefully skips missing):
  Back-validation (retrospective replay · what would have happened):
    reports/research/r2_upgrades/p0_exit_bridge_replay_{market}.json
    reports/research/r2_upgrades/p1_calibration_{market}.json
    reports/research/r2_upgrades/p2_sector_regime_{market}.json
    reports/research/r2_upgrades/p3_kg_community_{market}.json
    reports/research/r2_upgrades/p4_cap_sector_{market}.json
    reports/research/r2_upgrades/p5_{market}.json
    reports/research/r3/models/gbm_tier1_{market}.json
    reports/research/r3/baseline_replicate_{market}.json
    reports/research/short_term_momentum_backtest_{market}.json
    reports/research/loss_guard_backtest_{market}.json
    reports/research/backtest_2y.json   (both markets · same file)
  Forward-validation (live realized · what actually happened):
    reports/research/mr_forward_validation_{market}.json
    reports/research/AEGIS_FORWARD_VALIDATION_REPORT.md    (narrative)
    reports/research/r3/shadow_ledger.jsonl                (R3 shadow · Day 0+)
    reports/research/r3/day30_gate_{market}.json           (once shadow matures)
    reports/research/r3/day60_scorecard_{market}.json
    reports/research/r3/day90_promotion_{market}.json

Emits:
  reports/research/AEGIS_VALIDATION_SUMMARY_{market}.md
  reports/research/aegis_validation_summary_{market}.json
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _read_json(p: Path):
    if not p.exists(): return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(p: Path):
    if not p.exists(): return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _line_count(p: Path) -> int:
    if not p.exists(): return 0
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for line in fh if line.strip())
    except Exception:
        return 0


def collect(root: Path, market: str) -> dict:
    r = root / "reports" / "research"
    payload = {
        "market": market,
        "asof": datetime.now().strftime("%Y-%m-%d"),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),

        # ---- Back-validation (retrospective) ----
        "back_validation": {
            "p0_exit_bridge_replay": _read_json(r / "r2_upgrades" / f"p0_exit_bridge_replay_{market}.json"),
            "p1_calibration":        _read_json(r / "r2_upgrades" / f"p1_calibration_{market}.json"),
            "p2_sector_regime":      _read_json(r / "r2_upgrades" / f"p2_sector_regime_{market}.json"),
            "p3_kg_community":       _read_json(r / "r2_upgrades" / f"p3_kg_community_{market}.json"),
            "p4_cap_sector":         _read_json(r / "r2_upgrades" / f"p4_cap_sector_{market}.json"),
            "p5_remaining":          _read_json(r / "r2_upgrades" / f"p5_{market}.json"),
            "r3_gbm_tier1":          _read_json(r / "r3" / "models" / f"gbm_tier1_{market}.json"),
            "r3_baseline_gate":      _read_json(r / "r3" / f"baseline_replicate_{market}.json"),
            "short_term_momentum":   _read_json(r / f"short_term_momentum_backtest_{market}.json"),
            "loss_guard":            _read_json(r / f"loss_guard_backtest_{market}.json"),
        },

        # ---- Forward-validation (live) ----
        "forward_validation": {
            "mr_forward_validation":     _read_json(r / f"mr_forward_validation_{market}.json"),
            "r3_shadow_ledger_lines":    _line_count(r / "r3" / "shadow_ledger.jsonl"),
            "r3_day30_gate":             _read_json(r / "r3" / f"day30_gate_{market}.json"),
            "r3_day60_scorecard":        _read_json(r / "r3" / f"day60_scorecard_{market}.json"),
            "r3_day90_promotion":        _read_json(r / "r3" / f"day90_promotion_{market}.json"),
        },

        # ---- Standing comparator (permanent yardstick · Sprint A P5.5) ----
        "standing_comparator": {
            "note": "Equal-weight top-10 · 3-mo momentum · monthly rebalance · never optimized",
            "engine": "backend.research.r2_upgrades.p5_remaining_upgrades:p5_5_standing_comparator_returns",
        },

        # ---- Substrate row counts (proves each layer is real) ----
        "substrate": {
            "outcome_dataset":  _read_json(r / "outcome_dataset" / f"{market}.summary.json"),
            "signal_ledger":    _read_json(r / "signal_ledger" / f"{market}.summary.json"),
            "pit_universe":     _read_json(r / "pit_universe" / f"{market}.summary.json"),
            "fundamentals":     _read_json(r / "fundamentals_feature_store" / f"{market}.summary.json"),
        },

        # ---- Governance ----
        "governance": {
            "trial_accounting": _read_json(r / "trial_accounting" / f"{market}.json"),
            "signal_funnel":    _read_json(r / "r2_signal_funnel" / market / "latest.json"),
            "momentum_funnel":  _read_json(r / "momentum_funnel" / market / "latest.json"),
        },
    }
    return payload


def _fmt_gate(d: dict, ok_key: str = "gate_pass", detail_keys: list = None) -> str:
    if not isinstance(d, dict): return "no data"
    ok = d.get(ok_key)
    if ok is None: ok = d.get("P0_GATE_PASS")
    badge = "PASS" if ok else ("FAIL" if ok is False else "N/A")
    parts = [badge]
    for k in (detail_keys or []):
        v = d.get(k)
        if v is not None: parts.append(f"{k}={v}")
    return " · ".join(parts)


def render_md(root: Path, market: str, payload: dict) -> Path:
    md_lines: list[str] = []
    md_lines.append(f"# AEGIS · Validation Summary · {market.upper()}")
    md_lines.append(f"_generated {payload['generated_utc']} · Sprint A consolidator_\n")

    # ---- Executive summary ----
    md_lines.append("## Executive Summary\n")
    md_lines.append("| Component | Status | Key metric |")
    md_lines.append("|---|---|---|")

    bv = payload["back_validation"]
    fv = payload["forward_validation"]
    sub = payload["substrate"]

    # Outcome dataset gate
    if sub.get("outcome_dataset"):
        od = sub["outcome_dataset"]
        gate = "PASS" if od.get("phase0_gate_50_closed") else "BLOCKED"
        md_lines.append(f"| Phase 0 · Outcome Dataset ≥50 closed | **{gate}** | {od.get('n_closed_non_admin',0)} non-admin closed positions |")

    # P0
    if bv.get("p0_exit_bridge_replay"):
        p0 = bv["p0_exit_bridge_replay"]
        n = p0.get("n_positions", 0)
        gate_status = p0.get("P0_GATE_STATUS") or ("PASS" if p0.get("P0_GATE_PASS") else "FAIL")
        delta = p0.get("mean_delta_pct")
        ci = p0.get("paired_bootstrap", {}) or {}
        detail = f"n={n} · Δ={round(delta*100, 3) if delta is not None else '?'}%" if delta is not None else f"n={n}"
        if ci.get("ci_low") is not None:
            detail += f" · 95%CI [{round(ci['ci_low']*100,3)}%, {round(ci['ci_high']*100,3)}%] · p={round(ci.get('p_value_two_sided',0),3)}"
        md_lines.append(f"| P0 · Dynamic exit-bridge replay | **{gate_status}** | {detail} |")

    # P1
    if bv.get("p1_calibration"):
        p1 = bv["p1_calibration"]
        md_lines.append(f"| P1 · Joint Platt calibration | **{p1.get('gate_status','?')}** | n={p1.get('n',0)} · ECE_after={p1.get('ece_after','?')} |")

    # P2
    if bv.get("p2_sector_regime"):
        p2 = bv["p2_sector_regime"]
        best = p2.get("best", {}) or {}
        base = p2.get("baseline_alpha0_beta0", {}) or {}
        md_lines.append(f"| P2 · Sector/regime ranking | best (α={best.get('alpha')}, β={best.get('beta')}) | Sharpe {round(best.get('trade_sharpe',0),3)} vs base {round(base.get('trade_sharpe',0),3)} · lift {round(p2.get('sharpe_lift_over_baseline',0),3)} |")

    # P3
    if bv.get("p3_kg_community"):
        p3 = bv["p3_kg_community"]
        best = p3.get("best", {}) or {}
        md_lines.append(f"| P3 · KG community γ | best γ={best.get('gamma','?')} | lift {round(p3.get('lift_vs_baseline',0),4)} · {p3.get('n_communities',0)} communities |")

    # P4
    if bv.get("p4_cap_sector"):
        p4 = bv["p4_cap_sector"]
        lr = p4.get("likelihood_ratio_test", {}) or {}
        md_lines.append(f"| P4 · Cap×Sector LR test | {('SECTOR ADDS INFO' if lr.get('sector_adds_information') else 'NO EDGE')} | p={lr.get('p_value','?')} · df={lr.get('df','?')} · n={lr.get('n',0)} |")

    # R3 GBM
    if bv.get("r3_gbm_tier1"):
        r3 = bv["r3_gbm_tier1"]
        md_lines.append(f"| R3 · Tier 1 GBM (shadow) | trained | n={r3.get('n_train',0)} · Brier={round(r3.get('brier',0),4)} · AUC={round(r3.get('auc',0),3)} · ECE={round(r3.get('ece',0),4)} |")

    # R3 baseline gate
    if bv.get("r3_baseline_gate"):
        bg = bv["r3_baseline_gate"]
        md_lines.append(f"| R3 · Baseline-replicate gate | **{('PASS' if bg.get('gate_pass') else 'BLOCKED')}** | IC gap {round(bg.get('gap',0),4)} vs tol {round(bg.get('tolerance',0),4)} |")

    # Forward validation
    if fv.get("mr_forward_validation"):
        mr = fv["mr_forward_validation"]
        md_lines.append(f"| Forward · MR ingestion (Sprint M-R) | {mr.get('n_observations','?')} obs | ingested through {mr.get('asof','?')} |")
    md_lines.append(f"| Forward · R3 shadow ledger | {fv.get('r3_shadow_ledger_lines',0)} picks logged | Day-30 gate not yet fired |")
    for k in ("r3_day30_gate", "r3_day60_scorecard", "r3_day90_promotion"):
        d = fv.get(k)
        if d and isinstance(d, dict):
            md_lines.append(f"| Forward · {k} | {d.get('GATE_2_OF_3') or d.get('recommendation') or 'run'} | see JSON |")

    md_lines.append("")

    # ---- Back-validation detail ----
    md_lines.append("## Back-Validation Detail (retrospective replay)\n")
    md_lines.append(f"**P0 · Dynamic exit-bridge**\n")
    if bv.get("p0_exit_bridge_replay"):
        p0 = bv["p0_exit_bridge_replay"]
        p0_params = p0.get("parameters", {}) or {}
        md_lines.append(f"- Positions replayed: **{p0.get('n_positions',0)}**")
        md_lines.append(f"- Actual mean return: {round((p0.get('mean_actual_return_pct',0) or 0)*100, 3)}%")
        md_lines.append(f"- Counterfactual mean return: {round((p0.get('mean_counterfactual_return_pct',0) or 0)*100, 3)}%")
        md_lines.append(f"- Δ (counter − actual): {round((p0.get('mean_delta_pct',0) or 0)*100, 3)}%")
        md_lines.append(f"- OHLC ambiguous days: {p0.get('n_ohlc_ambiguous_days',0)} ({round(100*p0.get('n_ohlc_ambiguous_pct',0),2)}%) · resolved pessimistic-stop-first (CANONICAL 1)")
        pb = p0.get("paired_bootstrap", {}) or {}
        md_lines.append(f"- Paired bootstrap 95% CI: [{round((pb.get('ci_low',0) or 0)*100,3)}%, {round((pb.get('ci_high',0) or 0)*100,3)}%] · p={round(pb.get('p_value_two_sided',0) or 0, 3)}")
        md_lines.append(f"- Parameters: k_stop={p0_params.get('k_stop')} · m_target={p0_params.get('m_target')} · horizon={p0_params.get('horizon_days')}d · ATR-14")
        md_lines.append(f"- Counterfactual exit reasons: {p0.get('counterfactual_exit_reasons', {})}")
        md_lines.append(f"- **Gate:** {p0.get('P0_GATE_STATUS') or ('PASS' if p0.get('P0_GATE_PASS') else 'FAIL')}")
    else:
        md_lines.append("- (no P0 output yet)")

    md_lines.append("\n**Prior back-tests (pre-Sprint-A · preserved for continuity)**\n")
    for k, label in [
        ("short_term_momentum", "Short-term momentum"),
        ("loss_guard",          "Loss guard"),
    ]:
        d = bv.get(k)
        if d:
            md_lines.append(f"- {label}: n={d.get('n_samples') or d.get('n_exits_analyzed', 0)}")

    md_lines.append("")

    # ---- Forward-validation detail ----
    md_lines.append("## Forward-Validation Detail (live realized outcomes)\n")
    if fv.get("mr_forward_validation"):
        mr = fv["mr_forward_validation"]
        md_lines.append(f"- Sprint M-R Forward Validation Engine: **{mr.get('n_observations','?')} observations** through {mr.get('asof','?')}")
        md_lines.append(f"- Horizons: {mr.get('forward_horizons_days')}")
    md_lines.append("- Sprint M-R narrative report: `reports/research/AEGIS_FORWARD_VALIDATION_REPORT.md`")
    md_lines.append(f"- R3 shadow ledger picks: **{fv.get('r3_shadow_ledger_lines', 0)}** · Day-30 gate fires when ≥20 accumulated")
    md_lines.append("")

    # ---- Substrate ----
    md_lines.append("## Substrate row counts\n")
    for k, d in sub.items():
        if not d: continue
        if isinstance(d, dict):
            n = d.get("n_rows") or d.get("n_positions") or d.get("n_rows_total") or 0
            md_lines.append(f"- {k}: {n} rows")

    md_lines.append("")
    md_lines.append("## Governance snapshot")
    tr = payload.get("governance", {}).get("trial_accounting")
    if tr:
        md_lines.append(f"- Trial accounting: {tr.get('n_ok', 0)}/{tr.get('n_experiments_declared', 0)} OK · {tr.get('n_missing',0)} MISSING · {tr.get('n_drift',0)} DRIFT")
    sf = payload.get("governance", {}).get("signal_funnel")
    if sf:
        bn = sf.get("bottleneck", {})
        md_lines.append(f"- R2 funnel bottleneck: {bn.get('transition','?')} · dropped {bn.get('drop',0)}")
    mf = payload.get("governance", {}).get("momentum_funnel")
    if mf:
        bn = mf.get("bottleneck", {})
        md_lines.append(f"- Momentum funnel bottleneck: {bn.get('transition','?')} · dropped {bn.get('drop',0)}")

    md_lines.append("")

    out = root / "reports" / "research" / f"AEGIS_VALIDATION_SUMMARY_{market.upper()}.md"
    out.write_text("\n".join(md_lines), encoding="utf-8")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa", "both"), default="both")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india", "usa"] if args.market == "both" else [args.market]

    index_lines = ["# AEGIS · Validation Index", ""]
    for m in markets:
        payload = collect(root, m)
        md_path = render_md(root, m, payload)
        json_path = root / "reports" / "research" / f"aegis_validation_summary_{m}.json"
        json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"[validation] {m} · md={md_path.relative_to(root)} · json={json_path.relative_to(root)}")
        index_lines.append(f"- **{m.upper()}** · [Summary]({md_path.name}) · [JSON]({json_path.name})")
    (root / "reports" / "research" / "AEGIS_VALIDATION_INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
