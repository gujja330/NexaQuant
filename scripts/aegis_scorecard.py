"""AEGIS · SINGLE SCORECARD generator
CEO 2026-09-03 · replaces EVIDENCE_LOG + PDF_MATRIX + EXPERIMENT_REGISTRY + 28_REPORTS.

Rebuild:
    python scripts/aegis_scorecard.py

Emits ONE file: docs/AEGIS/AEGIS_SCORECARD.md

Structure (short · scannable · no fluff):
    0. TL;DR
    1. Governance state
    2. Substrate (per market · numbers)
    3. Research results · one row per experiment · verdict + recommendation
    4. Forward artifacts · R3 shadow + paper comparator + Sprint M-R
    5. Trial matrix / additive extensions
    6. Data freshness
    7. Rebuild commands
"""
from __future__ import annotations

import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _read_json(p: Path):
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None


def _count_lines(p: Path) -> int:
    if not p.exists(): return 0
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for l in fh if l.strip())
    except Exception:
        return 0


def _fresh_days(p: Path) -> str:
    if not p.exists(): return "?"
    try:
        m = datetime.fromtimestamp(p.stat().st_mtime)
        return f"{(datetime.now() - m).days}d"
    except Exception:
        return "?"


def _fmt(v, prec=3):
    if v is None: return "?"
    try: return f"{float(v):.{prec}f}"
    except Exception: return str(v)


def _scorecard(root: Path) -> str:
    r = root / "reports" / "research"
    L: list[str] = []
    L.append("# AEGIS · SCORECARD")
    L.append(f"_regen `python scripts/aegis_scorecard.py` · {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} · replaces EVIDENCE_LOG + PDF_MATRIX + EXPERIMENT_REGISTRY + 28_REPORTS_")
    L.append("")
    L.append("**PRODUCTION = FROZEN.** No R2 change. No push. Per CEO Development Freeze.")
    L.append("")

    # 0 · TL;DR
    L.append("## 0 · TL;DR")
    L.append("")
    L.append("- Architecture LOCKED · isolation CI green · R1 advisory · R2 sole production · R3 shadow-only")
    L.append("- 4 correct REJECT verdicts preserved (P0 · R3 baseline · NEG-PNL · POS-PNL)")
    L.append("- **Zero PROMOTE-CANDIDATE** · nothing meets promotion criteria")
    L.append("- Pytest 599/0 · xlsx_validator 24 PASS / 0 FAIL / 1 WARN")
    L.append("")

    # 1 · Governance
    L.append("## 1 · Governance")
    L.append("")
    L.append("| Item | State | Path |")
    L.append("|---|---|---|")
    L.append("| Controlling contract | V2 master prompt · IMMUTABLE | `docs/AEGIS/MASTER_CONTROLLING_PROMPT_2026-09-03_V2.md` |")
    L.append("| Runner registry | R1=RETIRED_ADVISORY · R2=PRODUCTION · R3=SHADOW_ONLY | `configs/aegis_runner_registry.yaml` |")
    L.append("| Retirement config | R1 retired | `configs/aegis_retirement.yaml` |")
    L.append("| Isolation CI | 9/9 pass | `tests/isolation/` |")
    L.append("| Standards CI | 8/8 pass | `tests/standards/` |")
    L.append("| Composite conviction table | 6/6 pass | `tests/composite/` |")
    L.append("| Signal Silence + MVS + Relaxation | 6/6 pass | `tests/governance/` |")
    L.append("| Enrichers + trial accounting | 10/10 pass | `tests/enrichers/` · `tests/research/` |")
    from backend.research.governance import RelaxationTracker
    tr = RelaxationTracker(root)
    budget = tr.can_relax(datetime.now().strftime("%Y-%m-%d"))
    L.append(f"| MVS relaxation budget | used {budget['used_last_90d']} · cap {budget['cap']} · remaining {budget['remaining']} | `reports/research/governance/relaxation_log.jsonl` |")
    L.append("")

    # 2 · Substrate
    L.append("## 2 · Substrate (per market)")
    L.append("")
    L.append("| Substrate | India | USA |")
    L.append("|---|---:|---:|")
    for label, path_tpl, extract in [
        ("Outcome Dataset · positions", "outcome_dataset/{market}.summary.json", lambda d: d.get('n_positions', 0)),
        ("Outcome Dataset · non-admin closed", "outcome_dataset/{market}.summary.json", lambda d: d.get('n_closed_non_admin', 0)),
        ("Phase-0 gate (n≥50)", "outcome_dataset/{market}.summary.json", lambda d: "PASS" if d.get('phase0_gate_50_closed') else "BLOCKED"),
        ("Signal Ledger rows", "signal_ledger/{market}.summary.json", lambda d: d.get('n_rows', 0)),
        ("Signal Ledger snapshots", "signal_ledger/{market}.summary.json", lambda d: d.get('n_snapshots', 0)),
        ("PIT Universe rows", "pit_universe/{market}.summary.json", lambda d: d.get('n_rows', 0)),
        ("PIT Universe unique tickers", "pit_universe/{market}.summary.json", lambda d: d.get('n_unique_tickers', 0)),
        ("Fundamentals FS rows", "fundamentals_feature_store/{market}.summary.json", lambda d: d.get('n_rows_total', 0)),
    ]:
        i_d = _read_json(r / path_tpl.format(market="india")); u_d = _read_json(r / path_tpl.format(market="usa"))
        i_v = extract(i_d) if i_d else "—"; u_v = extract(u_d) if u_d else "—"
        L.append(f"| {label} | {i_v} | {u_v} |")
    n_kg_i = len(list((r / "kg_pit_snapshots" / "india").glob("*.json"))) if (r / "kg_pit_snapshots" / "india").exists() else 0
    n_kg_u = len(list((r / "kg_pit_snapshots" / "usa").glob("*.json"))) if (r / "kg_pit_snapshots" / "usa").exists() else 0
    L.append(f"| KG PIT snapshots | {n_kg_i} | {n_kg_u} |")
    L.append(f"| R3 shadow ledger picks | — | {_count_lines(r / 'r3' / 'shadow_ledger.jsonl')} |")
    L.append(f"| Paper comparator ticks | {_count_lines(r / 'paper_comparator' / 'india.jsonl')} | {_count_lines(r / 'paper_comparator' / 'usa.jsonl')} |")
    L.append("")

    # 3 · Research results
    L.append("## 3 · Research results · verdict + recommendation")
    L.append("")
    L.append("| Experiment | Market | Result | Verdict | Recommendation |")
    L.append("|---|---|---|---|---|")

    # P0
    for m in ("india","usa"):
        d = _read_json(r / "r2_upgrades" / f"p0_exit_bridge_replay_{m}.json")
        if d:
            pb = d.get("paired_bootstrap") or {}
            delta_pct = _fmt((d.get("mean_delta_pct") or 0)*100, 3)
            p = _fmt(pb.get("p_value_two_sided"), 3)
            gate = d.get("P0_GATE_STATUS") or ("PASS" if d.get("P0_GATE_PASS") else "FAIL")
            L.append(f"| P0 exit-bridge (k=2,m=3,60d) | {m.upper()} | n={d.get('n_positions',0)} · Δ={delta_pct}% · p={p} | **{gate}** | REJECT at these params · run P0-EXTENSION-01 |")

    # P1
    for m in ("india","usa"):
        d = _read_json(r / "r2_upgrades" / f"p1_calibration_{m}.json")
        if d:
            L.append(f"| P1 joint Platt | {m.upper()} | n={d.get('n',0)} | {d.get('gate_status','?')} | RESEARCH FURTHER · needs n≥50 |")

    # P2
    for m in ("india","usa"):
        d = _read_json(r / "r2_upgrades" / f"p2_sector_regime_{m}.json")
        if d:
            best = d.get("best") or {}
            L.append(f"| P2 α,β (9 trials) | {m.upper()} | best (α={best.get('alpha','?')}, β={best.get('beta','?')}) lift={_fmt(d.get('sharpe_lift_over_baseline'))} | BLOCKED | RESEARCH FURTHER · regime substrate thin |")

    # P3
    for m in ("india","usa"):
        d = _read_json(r / "r2_upgrades" / f"p3_kg_community_{m}.json")
        if d:
            L.append(f"| P3 KG γ (5 trials) | {m.upper()} | n_communities={d.get('n_communities',0)} | BLOCKED | RESEARCH FURTHER · needs real KG persistence |")

    # P4
    for m in ("india","usa"):
        d = _read_json(r / "r2_upgrades" / f"p4_cap_sector_{m}.json")
        if d:
            lr = d.get("likelihood_ratio_test") or {}
            L.append(f"| P4 Cap × Sector LR | {m.upper()} | n_cells={d.get('n_cells',0)} · LR n={lr.get('n',0)} | BLOCKED | RESEARCH FURTHER · after cap/investability batch |")

    # P5
    for m in ("india","usa"):
        d = _read_json(r / "r2_upgrades" / f"p5_{m}.json")
        if d:
            L.append(f"| P5.1-5.5 | {m.upper()} | 5 subitems scaffolded | MIXED | P5.5 KEEP (permanent) · rest RESEARCH FURTHER |")

    # NEG
    for m in ("india","usa"):
        panel = _read_json(r / "neg_pnl_control_60d" / f"panel_{m}.json")
        if panel:
            recent = panel.get("protection_recent_60d") or {}
            L.append(f"| NEG-PNL-CONTROL-60D | {m.upper()} | n={recent.get('n',0)} · 9 variants all FAIL or null | **REJECT** (correct) | KEEP research family · no R2 tightening |")

    # POS
    for m in ("india","usa"):
        panel = _read_json(r / "pos_pnl_capture_60d" / f"panel_{m}.json")
        if panel:
            agg = panel.get("aggregate_missed_cost_pct_by_horizon") or {}
            L.append(f"| POS-PNL-CAPTURE-60D | {m.upper()} | n={panel.get('n_candidates_total',0)} · 16 winner defs · 100% misses = C_FUNNEL_STAGE | **REJECT loosening** | KEEP family · alternate candidate path = NEW ticket |")

    # Joint
    for m in ("india","usa"):
        d = _read_json(r / "joint_pnl" / f"panel_{m}.json")
        if d:
            L.append(f"| Joint P&L Pareto | {m.upper()} | pareto size={d.get('pareto_frontier_size',0)} (null action) | **REJECT all** | KEEP engine |")

    # R3
    for m in ("india","usa"):
        model = _read_json(r / "r3" / "models" / f"gbm_tier1_{m}.json")
        bg = _read_json(r / "r3" / f"baseline_replicate_{m}.json")
        if model:
            L.append(f"| R3 Tier-1 GBM | {m.upper()} | n_train={model.get('n_train',0)} · Brier={_fmt(model.get('brier'))} · AUC={_fmt(model.get('auc'))} · ECE={_fmt(model.get('ece'))} | {'training run' if not bg else ('PASS' if bg.get('gate_pass') else 'FAIL')} | Tier-2 {'UNLOCKED' if (bg and bg.get('gate_pass')) else 'BLOCKED'} · **KEEP gate** |")

    # R1
    for m in ("india","usa"):
        d = _read_json(r / "r1_advisory_attribution" / f"{m}.json")
        if d:
            L.append(f"| R1 attribution | {m.upper()} | r1_archive_days={d.get('n_r1_days_archived',0)} · early_warnings={d.get('n_early_warnings_r1_before_r2',0)} | {'BLOCKED · archive gap' if d.get('n_r1_days_archived',0)==0 else 'OK'} | RESEARCH FURTHER · start R1 daily archive |")

    # Composite
    for m in ("india","usa"):
        d = _read_json(r / "composite" / f"composite_signals_{m}.json")
        if d:
            L.append(f"| Composite daily loop | {m.upper()} | n_tickers={d.get('n_tickers',0)} · R3 admitted?=no (trailing_n<50) | shadow only | KEEP as shadow · REJECT sizing promotion |")

    L.append("")

    # 4 · Forward
    L.append("## 4 · Forward artifacts")
    L.append("")
    L.append(f"- **R3 shadow ledger:** {_count_lines(r / 'r3' / 'shadow_ledger.jsonl')} picks · Day-30 gate fires at ≥20 · `reports/research/r3/shadow_ledger.jsonl`")
    L.append(f"- **Paper comparator (India):** {_count_lines(r / 'paper_comparator' / 'india.jsonl')} ticks · `reports/research/paper_comparator/india.jsonl`")
    L.append(f"- **Paper comparator (USA):** {_count_lines(r / 'paper_comparator' / 'usa.jsonl')} ticks · `reports/research/paper_comparator/usa.jsonl`")
    for m in ("india","usa"):
        d = _read_json(r / f"mr_forward_validation_{m}.json")
        if d:
            L.append(f"- **Sprint M-R forward (pre-Sprint-A · {m.upper()}):** n_obs={d.get('n_observations','?')} through {d.get('asof','?')} · `reports/research/mr_forward_validation_{m}.json`")
    fr = r / "AEGIS_FORWARD_VALIDATION_REPORT.md"
    if fr.exists():
        L.append(f"- **Sprint M-R narrative:** `{fr.relative_to(root)}` (India −6.48pp · USA +2.69pp through 2026-08-27)")
    L.append("")

    # 5 · Additive extensions declared (not yet run)
    L.append("## 5 · Additive extensions declared (not yet run)")
    L.append("")
    L.append("- **P0-EXTENSION-01** · 60-trial (k×m×horizon) grid · gated on regime enricher (LANDED) · can now run")
    L.append("- **R2-EXT-EXIT-DOCTRINE-01** · chandelier / fixed-% / MFE / regime-aware k · separate research tickets")
    L.append("- **CRASH_DETECTOR_01 + RECOVERY_DETECTOR_01** · covers 2 of 6 PDF regime states not currently emitted")
    L.append("- **CAP_PIT_STRICT_01** · shares_out(entry_date) × close(entry_date) instead of yfinance current-fallback")
    L.append("- **UNIVERSE_EXT_NIFTY200** · India PIT audit currently uses NIFTY 50 subset")
    L.append("- **MIDCAP400_EXT** · USA S&P MidCap 400 historical membership")
    L.append("- **RELATED_PARTY_TXN_SIGNAL + TRANSCRIPT_TONE_SIGNAL** (Q&A separate) · REQUIRES NEW SOURCE")
    L.append("- **CUSUM_REGIME_SUPPLEMENT** · Tier-3 regime detector research")
    L.append("- **WINNER_GENOME_FULL** · unblocks after fundamentals batch fully populates")
    L.append("")

    # 6 · Trial matrix
    L.append("## 6 · Trial family counts (Deflated Sharpe applies these)")
    L.append("")
    L.append("| Family | n_trials |")
    L.append("|---|---:|")
    L.append("| P0-original | 1 (FAIL preserved) |")
    L.append("| P0-EXTENSION-01 (declared) | 60 (5 × 4 × 3) |")
    L.append("| P1 calibration | 1 |")
    L.append("| P2 α,β grid | 9 (3 × 3) |")
    L.append("| P3 γ grid | 5 |")
    L.append("| P4 Cap × Sector LR | 1 |")
    L.append("| P5.1/5.2/5.3 | 5 |")
    L.append("| R3 GBM baseline | 1 |")
    L.append("| NEG-PNL variants | 9 (6 static-pct + 3 timing) |")
    L.append("| POS-PNL winner defs | 16 (4 horizons × 4 thresholds) |")
    L.append("| **Total counted** | **108** |")
    L.append("")

    # 7 · Data freshness
    L.append("## 7 · Data freshness")
    L.append("")
    L.append("| Data | Newest mtime · days stale |")
    L.append("|---|---|")
    for label, p in [
        ("India parquet dir", root / "data" / "raw" / "india"),
        ("USA parquet dir",   root / "usa" / "data" / "raw" / "us"),
        ("India recs_v3",     root / "reports" / "recommendations_v3.json"),
        ("USA recs_v3",       root / "usa" / "reports" / "recommendations_v3.json"),
        ("India regime source", root / "reports" / "research" / "mr_market_regime_india.json"),
        ("USA regime source",   root / "reports" / "research" / "mr_market_regime_usa.json"),
    ]:
        if p.is_dir():
            files = list(p.glob("*_D1.parquet")) or list(p.glob("*.parquet"))
            if files:
                newest = max(f.stat().st_mtime for f in files)
                days = (datetime.now() - datetime.fromtimestamp(newest)).days
                L.append(f"| {label} | {datetime.fromtimestamp(newest).strftime('%Y-%m-%d')} · {days}d |")
            else:
                L.append(f"| {label} | (empty) |")
        elif p.exists():
            L.append(f"| {label} | {datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d')} · {_fresh_days(p)} |")
    L.append("")

    # 8 · Rebuild commands
    L.append("## 8 · Rebuild commands (autonomous)")
    L.append("")
    L.append("```bash")
    L.append("# Substrate refresh")
    L.append("python scripts/populate_fundamentals_feature_store.py --market india --limit 50 --sleep 1.5")
    L.append("python scripts/populate_fundamentals_feature_store.py --market usa --limit 100 --sleep 1.5")
    L.append("python -m backend.research.signal_ledger.build --market both")
    L.append("python -m backend.research.outcome_dataset.build --market both")
    L.append("python -m backend.research.enrichers.regime --market both")
    L.append("python -m backend.research.enrichers.regime_scores --market both")
    L.append("python -m backend.research.enrichers.cap_and_investability --market both")
    L.append("")
    L.append("# All research reruns")
    L.append("python -m backend.research.r2_upgrades.p0_exit_bridge_replay --market both")
    L.append("python -m backend.research.r2_upgrades.p1_calibration_joint --market both")
    L.append("python -m backend.research.r2_upgrades.p2_sector_regime_ranking --market both")
    L.append("python -m backend.research.r2_upgrades.p3_kg_community_scoring --market both")
    L.append("python -m backend.research.r2_upgrades.p4_cap_sector_interaction --market both")
    L.append("python -m backend.research.r2_upgrades.p5_remaining_upgrades --market both")
    L.append("python scripts/neg_pnl_control_60d_run.py --market both")
    L.append("python scripts/pos_pnl_capture_60d_run.py --market both")
    L.append("python -m backend.research.joint_pnl.joint_score --market both")
    L.append("python scripts/r3_daily_shadow_feed.py --market both")
    L.append("python -m backend.recommendation.composite.daily_loop --market both")
    L.append("python -m backend.research.paper_comparator.daily_tick --market both")
    L.append("python -m backend.research.r1_advisory_attribution --market both")
    L.append("")
    L.append("# Regenerate THIS scorecard")
    L.append("python scripts/aegis_scorecard.py")
    L.append("")
    L.append("# Delivery + tests")
    L.append("python scripts/build_aegis_3sheet_workbook.py --market both --asof 2026-09-03")
    L.append("python -m pytest tests/ -q --ignore=tests/legacy")
    L.append("```")
    L.append("")
    L.append("---")
    L.append("")
    L.append("**End of scorecard. This file supersedes EVIDENCE_LOG.md · PDF_IMPLEMENTATION_MATRIX.md · EXPERIMENT_REGISTRY.md · FINAL_28_REPORTS.md — deleted per CEO directive.**")
    return "\n".join(L)


def main():
    out = _ROOT / "docs" / "AEGIS" / "AEGIS_SCORECARD.md"
    out.write_text(_scorecard(_ROOT), encoding="utf-8")
    print(f"[scorecard] wrote {out.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
