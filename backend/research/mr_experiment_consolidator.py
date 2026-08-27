"""AEGIS · Sprint M-R · Experiment Consolidator (CEO close-out).

Reduces the 5 registered walk-forward experiments to the 3 focused ones
requested for close-out:
   X1 · india_r1_r2_ranking   (folds E1 confidence + E2 top-3 rank + E3 compound)
   X2 · stop_loss_time_5d     (folds E5)
   X3 · technical_filter      (RSI + MA20 · new · evidence-backed)

Old experiments are marked SUPERSEDED_BY (or ARCHIVED_LOW_PRIORITY for
E4 band-boundary) so nothing is deleted · continuity of evidence is
preserved.

Under M-R sandbox rules. Writes only under reports/research/experiments/.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_experiment_consolidator.v0.1"


def _load(root: Path, rel: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / rel
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


PROMOTION_GATE = [
    "1. Research Ticket accepted by CEO",
    "2. Walk-forward test on N >= 100 forward predictions",
    "3. Full regression pass on locked delivery invariants (BLOCK == 0)",
    "4. CEO explicit approval + lock-override phrase",
    "5. Config-toggle OFF by default in a new SPRINT_ID branch",
    "6. Paper-trading period >= 30 sessions with green metrics",
    "7. Production promotion under new SPRINT_ID with L4 evidence",
]
LOCKED_LAYERS = [
    "R1 recommendation runner",
    "R2 recommendation runner",
    "Registry orphan-close",
    "backend/delivery/xlsx_contract.py",
    "backend/delivery/xlsx_validator.py",
    "scripts/telegram_command_center_send.py canonical INVESTMENT_ACTIVE JSON",
    "configs/ensemble_weights_adaptive.yaml",
    "model_registry.jsonl",
]


def build_x1(today: str) -> dict:
    return {
        "experiment_id":     "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking",
        "source_tickets":    ["aegis_mr_ticket_20260827_india_confidence_anti_signal",
                              "aegis_mr_ticket_20260827_india_top3_rank_inversion",
                              "aegis_mr_ticket_20260827_india_negative_alpha"],
        "market":            "INDIA",
        "title":             "India R1/R2 Ranking · confidence + top-3 slot filter",
        "hypothesis":        (
            "Two mechanisms compound to produce India's negative alpha vs "
            "universe: (a) R1 top-3 slot is anti-correlated with outcome "
            "when ma20_dist is outside +1..+5, and (b) confidence 70-85 "
            "band is an anti-signal. Applying both filters in shadow should "
            "raise India 5D WR toward or above universe baseline 32.25%."),
        "metric":            "shadow_5D_WR",
        "secondary_metrics": ["shadow_5D_avg_pct","shadow_top3_5D_WR",
                              "shadow_rank_4_7_5D_WR","daily_new_rec_count_delta"],
        "min_sample_size":   100,
        "observation_window_days": 30,
        "null_hypothesis":   (
            "Applying the R1 top-3 + confidence filters does not change "
            "shadow 5D WR by more than +/-3pp vs production R1."),
        "acceptance_criteria": (
            "Shadow 5D WR >= production 5D WR + 5pp AND shadow avg > "
            "production avg + 0.3% on n>=100 forward India predictions."),
        "rejection_criteria": (
            "Shadow 5D WR < production - 3pp OR daily rec-count drops >30% "
            "for 5 consecutive days."),
        "shadow_wire_up":    (
            "Sandbox: reads today's canonical India + LIVE parquet features · "
            "applies rule_X1_r1_r2_ranking · emits shadow rows to "
            "reports/research/experiments/{id}/{date}/shadow.jsonl. Never "
            "touches production R1."),
        "safety_gate":       [
            "No production R1/R2/Registry/XLSX/ensemble/config changes.",
            "Shadow output MUST live under reports/research/experiments/.",
            "Any regression in current delivery invariants (BLOCK != 0) aborts.",
        ],
        "promotion_gate":    PROMOTION_GATE,
        "do_not_touch":      LOCKED_LAYERS,
        "risk":              (
            "Confidence may be calibrated on a non-return objective. "
            "Top-3 slot changes could reduce daily new-rec count · monitor."),
        "current_status":    "ACTIVE_SHADOW",
        "first_snapshot_date": today,
        "days_of_evidence":  1,
        "attempts":          [],
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine":            ENGINE_ID,
        "experiment_id_family": EXPERIMENT_ID,
    }


def build_x2(today: str) -> dict:
    return {
        "experiment_id":     "aegis_mr_experiment_20260827_x2_stop_loss_time_5d",
        "source_tickets":    ["aegis_mr_ticket_20260827_india_stop_policy"],
        "market":            "INDIA",
        "title":             "India TIME_STOP_5D advisory · loss-control experiment",
        "hypothesis":        (
            "Historical sweep shows TIME_STOP_5D expectancy -0.613% vs "
            "CURRENT -0.886% (gap +0.273%) AND catastrophic-loss rate 0.00% "
            "vs 0.20%. Advisory-only shadow should confirm this gap "
            "prospectively before any stop policy change."),
        "metric":            "expectancy_gap_vs_current",
        "secondary_metrics": ["catastrophic_loss_rate","MFE_captured",
                              "profit_factor","stop_hit_rate"],
        "min_sample_size":   100,
        "observation_window_days": 30,
        "null_hypothesis":   (
            "Advisory TIME_STOP_5D exit does not improve median forward-return "
            "from advisory date by more than +/-0.1%."),
        "acceptance_criteria": (
            "Median advisory return over next 5D >= median current-policy "
            "return + 0.3% AND catastrophic-loss rate <= current on n>=100 "
            "advisory events."),
        "rejection_criteria": (
            "MFE-captured drops by more than 0.5% vs current · signals "
            "that time-exit is forfeiting winners."),
        "shadow_wire_up":    (
            "Sandbox: for every India ACTIVE position aged >=5 sessions from "
            "recommended_date/entry_date, emit TIME_EXIT_ADVISORY. Does NOT "
            "modify Registry, XLSX exit history, or Telegram."),
        "safety_gate":       [
            "No production stop-policy or exit-decision changes.",
            "Shadow advisory MUST live under reports/research/experiments/.",
            "Any regression in current delivery invariants (BLOCK != 0) aborts.",
        ],
        "promotion_gate":    PROMOTION_GATE,
        "do_not_touch":      LOCKED_LAYERS,
        "risk":              (
            "Time-exit forfeits longer-holding winners. Track MFE-captured."),
        "current_status":    "ACTIVE_SHADOW",
        "first_snapshot_date": today,
        "days_of_evidence":  1,
        "attempts":          [],
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine":            ENGINE_ID,
        "experiment_id_family": EXPERIMENT_ID,
    }


def build_x3(today: str) -> dict:
    return {
        "experiment_id":     "aegis_mr_experiment_20260827_x3_usa_mid_cap_tilt",
        "source_tickets":    ["derived_from_mr_studies_Q3_cap_bucket"],
        "market":            "USA",
        "title":             "USA MID-cap tilt · cap-weighted selection experiment",
        "hypothesis":        (
            "30D corpus shows USA MID cap n=622 · 5D WR=46.60% · avg=+0.10% "
            "(only USA positive-avg cohort) beats LARGE n=459 · 5D WR=35.96% "
            "· avg=-0.84% by 10.64pp WR. Tilting selection toward MID and "
            "away from LARGE in shadow should confirm this prospectively."),
        "metric":            "shadow_mid_5D_WR - shadow_large_5D_WR",
        "secondary_metrics": ["shadow_mid_avg","shadow_large_avg",
                              "cap_bucket_distribution_delta","MAE_by_cap"],
        "min_sample_size":   100,
        "observation_window_days": 30,
        "null_hypothesis":   (
            "MID vs LARGE 5D WR gap is within +/-3pp forward · in which "
            "case the 30D signal was noise/regime-specific."),
        "acceptance_criteria": (
            "shadow MID 5D WR - LARGE 5D WR >= 8pp on n>=100 forward USA "
            "predictions AND MID avg > LARGE avg by >= 0.5%."),
        "rejection_criteria": (
            "MID - LARGE gap < 3pp forward OR MID catastrophic-loss rate "
            "> LARGE + 0.5pp."),
        "shadow_wire_up":    (
            "Sandbox: reads today's canonical USA + LIVE parquet cap-bucket "
            "features · applies rule_X3_usa_mid_cap_tilt · emits shadow "
            "BOOST_TO_MID_TILT or DEMOTE_FROM_LARGE_TILT tags to "
            "reports/research/experiments/{id}/{date}/shadow.jsonl. Does "
            "NOT modify USA R1/R2, canonical, or Telegram."),
        "safety_gate":       [
            "No production USA runner or universe changes.",
            "Shadow tags MUST live under reports/research/experiments/.",
            "Any regression in current delivery invariants (BLOCK != 0) aborts.",
        ],
        "promotion_gate":    PROMOTION_GATE,
        "do_not_touch":      LOCKED_LAYERS,
        "risk":              (
            "MID vs LARGE gap may be regime-specific (drawdown-window "
            "artifact). Regularize with 5D + 10D + 20D acceptance. USA MID "
            "corpus depth may be volatility-driven."),
        "current_status":    "ACTIVE_SHADOW",
        "first_snapshot_date": today,
        "days_of_evidence":  1,
        "attempts":          [],
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine":            ENGINE_ID,
        "experiment_id_family": EXPERIMENT_ID,
    }


def build_xa_archived_technical_filter(today: str) -> dict:
    """Retained under ARCHIVED_FOR_LATER · will fire shadow rows for
    evidence continuity but not counted as a focused experiment."""
    return {
        "experiment_id":     "aegis_mr_experiment_20260827_x3_technical_filter",
        "source_tickets":    ["derived_from_mr_studies_technicals"],
        "market":            "INDIA",
        "title":             "Technical filter · RSI + MA20 evidence-backed edges",
        "hypothesis":        (
            "India OVERSOLD_lt30 RSI has 43.75% 5D WR (+18pp vs baseline). "
            "India above_+1_+5 ma20_dist has 37.17% WR (+11pp). India WEAK "
            "30-45 RSI has 18.25% WR (-7pp) and below_-5_-1 ma20_dist has "
            "17.97% WR (-8pp). Positive-filter tag on the good buckets and "
            "negative-filter tag on the bad ones should predict forward "
            "outcomes prospectively."),
        "metric":            "positive_filter_5D_WR - negative_filter_5D_WR",
        "secondary_metrics": ["positive_filter_avg","negative_filter_avg",
                              "no_filter_baseline_5D_WR"],
        "min_sample_size":   100,
        "observation_window_days": 30,
        "null_hypothesis":   (
            "Positive-filter and negative-filter tags produce forward 5D WR "
            "that differ by less than 5pp on N>=100 observations."),
        "acceptance_criteria": (
            "positive_filter_5D_WR - negative_filter_5D_WR >= 15pp on n>=100 "
            "total tagged observations."),
        "rejection_criteria": (
            "positive_filter_5D_WR - negative_filter_5D_WR < 3pp · signals "
            "that historical buckets don't survive out-of-sample."),
        "shadow_wire_up":    (
            "Sandbox: apply rule_X3_technical_filter to today's snapshot · "
            "records POSITIVE_FILTER / NEGATIVE_FILTER / MIXED / NO_FILTER "
            "tag per position. Does NOT change R1/R2 output."),
        "safety_gate":       [
            "No production ranker or selection changes.",
            "Shadow tags MUST live under reports/research/experiments/.",
            "Any regression in current delivery invariants (BLOCK != 0) aborts.",
        ],
        "promotion_gate":    PROMOTION_GATE,
        "do_not_touch":      LOCKED_LAYERS,
        "risk":              (
            "Overfitting to 30-day corpus. Positive/negative buckets could "
            "reverse in a different regime · regularize with 5D + 10D + 20D "
            "acceptance."),
        "current_status":    "ARCHIVED_FOR_LATER",
        "first_snapshot_date": today,
        "days_of_evidence":  1,
        "attempts":          [],
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine":            ENGINE_ID,
        "experiment_id_family": EXPERIMENT_ID,
    }


def build_e1(today: str) -> dict:
    return {
        "experiment_id":     "aegis_mr_experiment_20260827_e1_india_r1_filter",
        "source_evidence":   ["mr_studies_india.json:Q8_rank_slot.top3",
                              "mr_score_usefulness_india.json:audits.confidence_pct"],
        "market":            "INDIA",
        "title":             "E1 · India R1 negative filter (weakest cohorts)",
        "hypothesis":        (
            "R1 top-3 with ma20_dist outside +1..+5 (n=82, 14.5% WR) AND "
            "R1 confidence 70-85 anti-signal (n=103, 13.16% WR) are the two "
            "weakest R1 cohorts. Filtering them should raise R1 5D WR toward "
            "R2 baseline 32.16%."),
        "metric":            "shadow_R1_5D_WR (after filter)",
        "min_sample_size":   100,
        "observation_window_days": 30,
        "acceptance_criteria": "Filtered R1 5D WR >= production R1 + 5pp on n>=100",
        "rejection_criteria": "Filtered R1 5D WR < production R1 - 3pp",
        "promotion_gate":    PROMOTION_GATE,
        "do_not_touch":      LOCKED_LAYERS,
        "current_status":    "ACTIVE_SHADOW",
        "first_snapshot_date": today,
        "days_of_evidence":  1,
        "attempts":          [],
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine":            ENGINE_ID,
        "experiment_id_family": EXPERIMENT_ID,
        "ceo_final_status":  "FROZEN in MR_V1_EXPERIMENTS_FROZEN.md",
    }


def build_e2(today: str) -> dict:
    return {
        "experiment_id":     "aegis_mr_experiment_20260827_e2_india_r2_rank_4_7_boost",
        "source_evidence":   ["mr_conditional_cohorts_india.json:combos_3way.top_positive[0]"],
        "market":            "INDIA",
        "title":             "E2 · India R2 rank_4_7 + RSI STRONG positive-boost",
        "hypothesis":        (
            "Conditional 3-way `R2 · rank_4_7 · rsi=STRONG` shows 5D WR "
            "72.73% (n=22, +46.96pp edge, sig+). Boost-tag matching R2 "
            "predictions forward · N>=100 promotion decision."),
        "metric":            "shadow_boost_5D_WR",
        "min_sample_size":   100,
        "observation_window_days": 30,
        "acceptance_criteria": "Boost cohort 5D WR >= 55% on n>=100 AND avg > 0.5%",
        "rejection_criteria": "Boost cohort 5D WR < 40% (regime overfit)",
        "promotion_gate":    PROMOTION_GATE,
        "do_not_touch":      LOCKED_LAYERS,
        "current_status":    "ACTIVE_SHADOW",
        "first_snapshot_date": today,
        "days_of_evidence":  1,
        "attempts":          [],
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine":            ENGINE_ID,
        "experiment_id_family": EXPERIMENT_ID,
        "ceo_final_status":  "FROZEN in MR_V1_EXPERIMENTS_FROZEN.md",
    }


def build_e3(today: str) -> dict:
    return {
        "experiment_id":     "aegis_mr_experiment_20260827_e3_stop_loss_cross_market",
        "source_evidence":   ["mr_stop_loss_sweep_india.json:by_policy",
                              "mr_stop_loss_sweep_usa.json:by_policy"],
        "market":            "CROSS_MARKET",
        "title":             "E3 · Stop-loss cross-market · India TIME_STOP_5D + USA TRAILING_10",
        "hypothesis":        (
            "INDIA · TIME_STOP_5D expectancy +0.273% + 0.00% catastrophic on "
            "n=500. USA · TRAILING_10 expectancy +0.921% PF 1.309 on n=625. "
            "Advisory-only shadow confirms both prospectively."),
        "metric":            "expectancy_gap_vs_current per market",
        "min_sample_size":   100,
        "observation_window_days": 30,
        "acceptance_criteria": (
            "INDIA: advisory median return >= CURRENT median + 0.3% AND "
            "cat-loss <= CURRENT on n>=100. USA: advisory net of TRAILING_10 "
            ">= CURRENT + 0.5% expectancy on n>=100."),
        "rejection_criteria": "MFE-captured drops by >0.5% vs CURRENT",
        "promotion_gate":    PROMOTION_GATE,
        "do_not_touch":      LOCKED_LAYERS,
        "current_status":    "ACTIVE_SHADOW",
        "first_snapshot_date": today,
        "days_of_evidence":  1,
        "attempts":          [],
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine":            ENGINE_ID,
        "experiment_id_family": EXPERIMENT_ID,
        "ceo_final_status":  "FROZEN in MR_V1_EXPERIMENTS_FROZEN.md",
    }


SUPERSEDED_MAP_V2 = {
    "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking":
        ("SUPERSEDED_BY", "aegis_mr_experiment_20260827_e1_india_r1_filter"),
    "aegis_mr_experiment_20260827_x2_stop_loss_time_5d":
        ("SUPERSEDED_BY", "aegis_mr_experiment_20260827_e3_stop_loss_cross_market"),
    "aegis_mr_experiment_20260827_x3_usa_mid_cap_tilt":
        ("ARCHIVED_FOR_LATER", None),
    "aegis_mr_experiment_20260827_x3_technical_filter":
        ("ARCHIVED_FOR_LATER", None),
}


SUPERSEDED_MAP = {
    "aegis_mr_experiment_20260827_india_confidence_anti_signal":
        ("SUPERSEDED_BY", "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking"),
    "aegis_mr_experiment_20260827_india_top3_rank_inversion":
        ("SUPERSEDED_BY", "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking"),
    "aegis_mr_experiment_20260827_india_negative_alpha":
        ("SUPERSEDED_BY", "aegis_mr_experiment_20260827_x1_india_r1_r2_ranking"),
    "aegis_mr_experiment_20260827_india_stop_policy":
        ("SUPERSEDED_BY", "aegis_mr_experiment_20260827_x2_stop_loss_time_5d"),
    "aegis_mr_experiment_20260827_india_band_boundary":
        ("ARCHIVED_LOW_PRIORITY", None),
}


def _mark_v2_superseded(root: Path) -> list:
    marked = []
    for old_id, (status, new_id) in SUPERSEDED_MAP_V2.items():
        p = root / ALLOWED_WRITE_ROOT / "experiments" / f"{old_id}.json"
        if not p.exists(): continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        d["current_status"] = status
        if new_id: d["superseded_by"] = new_id
        d["v2_consolidator_stamp_utc"] = \
            datetime.now(timezone.utc).isoformat(timespec="seconds")
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
        marked.append({"experiment_id": old_id, "new_status": status,
                       "superseded_by": new_id})
    return marked


def _mark_superseded(root: Path) -> list:
    marked = []
    for old_id, (status, new_id) in SUPERSEDED_MAP.items():
        p = root / ALLOWED_WRITE_ROOT / "experiments" / f"{old_id}.json"
        if not p.exists(): continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        d["current_status"] = status
        if new_id: d["superseded_by"] = new_id
        d["consolidator_stamp_utc"] = \
            datetime.now(timezone.utc).isoformat(timespec="seconds")
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
        marked.append({"experiment_id": old_id, "new_status": status,
                       "superseded_by": new_id})
    return marked


def consolidate(root: Path) -> dict:
    today = date.today().isoformat()
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    created = []
    # CEO FINAL · 3 focused experiments (E1/E2/E3)
    for builder in (build_e1, build_e2, build_e3):
        e = builder(today)
        p = exp_dir / f"{e['experiment_id']}.json"
        p.write_text(json.dumps(e, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
        created.append(e["experiment_id"])
    # Archived X-series (retained for evidence continuity, not focused)
    for builder in (build_x1, build_x2, build_x3, build_xa_archived_technical_filter):
        e = builder(today)
        p = exp_dir / f"{e['experiment_id']}.json"
        # Ensure X-series marked non-focused
        if e.get("current_status") == "ACTIVE_SHADOW":
            e["current_status"] = "ARCHIVED_FOR_LATER"
        p.write_text(json.dumps(e, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
        created.append(e["experiment_id"])
    marked = _mark_superseded(root)
    marked_v2 = _mark_v2_superseded(root)

    # Refresh INDEX with current status of all files
    tickets = []
    for p in sorted(exp_dir.glob("aegis_mr_experiment_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        tickets.append({
            "experiment_id":         d.get("experiment_id"),
            "source_ticket_id":      d.get("source_ticket_id") or
                                     (d.get("source_tickets") or [None])[0],
            "market":                d.get("market"),
            "current_status":        d.get("current_status"),
            "min_sample_size":       d.get("min_sample_size"),
            "observation_window_days": d.get("observation_window_days"),
            "metric":                d.get("metric"),
            "first_snapshot_date":   d.get("first_snapshot_date"),
            "days_of_evidence":      d.get("days_of_evidence"),
            "superseded_by":         d.get("superseded_by"),
        })
    idx = {
        "engine":       ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_experiments": len(tickets),
        "n_focused_active": sum(1 for t in tickets
                                if t.get("current_status") == "ACTIVE_SHADOW"),
        "n_superseded": sum(1 for t in tickets
                            if "SUPERSEDED" in (t.get("current_status") or "")),
        "n_archived":   sum(1 for t in tickets
                            if "ARCHIVED" in (t.get("current_status") or "")),
        "experiments":  tickets,
    }
    (exp_dir / "INDEX.json").write_text(
        json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "engine":       ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "created":      created,
        "marked":       marked,
        "index":        idx,
    }


def render_console(res: dict):
    print(f"\n======== EXPERIMENT CONSOLIDATOR ========")
    print(f"  CREATED (3 focused ACTIVE_SHADOW):")
    for c in res["created"]:
        print(f"    · {c}")
    print(f"\n  MARKED (5 superseded/archived):")
    for m in res["marked"]:
        note = f"→ {m['superseded_by']}" if m['superseded_by'] else "(no successor)"
        print(f"    · {m['experiment_id']} · {m['new_status']} {note}")
    idx = res["index"]
    print(f"\n  INDEX totals: {idx['n_experiments']} experiments · "
          f"{idx['n_focused_active']} ACTIVE_SHADOW · "
          f"{idx['n_superseded']} SUPERSEDED_BY · "
          f"{idx['n_archived']} ARCHIVED")


if __name__ == "__main__":
    root = Path(".").resolve()
    res = consolidate(root)
    render_console(res)
    print(f"\n[experiment_consolidator] done")
