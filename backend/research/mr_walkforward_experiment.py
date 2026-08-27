"""AEGIS · Sprint M-R · Walk-Forward Experiment Registry · Sprint M.

For each hypothesis in the ranked shortlist, spec a structured walk-forward
experiment with:

  experiment_id           · derived from hypothesis ticket
  hypothesis              · one-line statement
  null_hypothesis         · what we would see if AEGIS is fine as-is
  metric                  · primary success metric (e.g. shadow 5D WR)
  secondary_metrics       · profit_factor · MAE · MFE · catastrophic-rate
  min_sample_size         · from statistical discipline (100 for PROD-candidate)
  acceptance_criteria     · quantitative threshold to pass
  rejection_criteria      · when to abort or roll back
  shadow_wire_up          · how the shadow variant is produced (no prod change)
  observation_window_days · how long to run
  current_status          · NOT_STARTED / IN_PROGRESS / PASSED / FAILED / ABORTED
  first_snapshot_date     · when day-0 was captured (None until started)
  days_of_evidence        · count of forward days recorded so far
  attempts                · list of prior runs

Emits reports/research/experiments/{experiment_id}.json + INDEX.json.
Emits nothing that changes production. All experiments start NOT_STARTED
until CEO explicitly enables them.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_walkforward_experiment.v0.1"


DEFAULT_OBS_WINDOW = 30
DEFAULT_MIN_N = 100


def _load(root: Path, name: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _spec_for(hyp: dict) -> dict:
    """Return the structured experiment spec derived from a hypothesis."""
    tid = hyp["ticket_id"]
    lower = tid.lower()
    market = hyp.get("market","")
    exp_id = tid.replace("aegis_mr_ticket", "aegis_mr_experiment")

    base = {
        "experiment_id":     exp_id,
        "source_ticket_id":  tid,
        "market":            market,
        "hypothesis":        hyp.get("hypothesis",""),
        "expected_effect":   hyp.get("expected_effect",""),
        "proposed_rule":     hyp.get("proposed_rule",""),
        "risk":              hyp.get("risk",""),
        "current_status":    "NOT_STARTED",
        "min_sample_size":   DEFAULT_MIN_N,
        "observation_window_days": DEFAULT_OBS_WINDOW,
        "first_snapshot_date": None,
        "days_of_evidence":  0,
        "attempts":          [],
        "engine":            ENGINE_ID,
        "experiment_id_family": EXPERIMENT_ID,
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shadow_wire_up":    (
            "Sandbox shadow output only · reads production R1/R2 canonical "
            "and applies the proposed rule OUTSIDE the delivery layer. Writes "
            "shadow rows to reports/research/walkforward/{date}/{exp_id}.jsonl. "
            "Never touches XLSX, canonical JSON, Registry, or Telegram."),
        "safety_gate":       [
            "No production R1/R2/Registry/XLSX/ensemble/config changes.",
            "Shadow output MUST live under reports/research/walkforward/.",
            "Any regression in current delivery invariants (BLOCK != 0) aborts.",
        ],
    }

    # Per-hypothesis specifics
    if "confidence_anti_signal" in lower:
        base.update({
            "metric":             "shadow_5D_WR",
            "secondary_metrics":  ["shadow_5D_avg_pct","shadow_10D_avg_pct",
                                   "shadow_MAE_avg","stop_hit_rate"],
            "null_hypothesis":    ("Inverting confidence contribution to R1 India "
                                   "does not change shadow 5D WR by more than "
                                   "+/-2pp vs production."),
            "acceptance_criteria": (
                "Shadow 5D WR >= production 5D WR + 5pp AND shadow avg > "
                "production avg + 0.3% on n>=100 forward India predictions."),
            "rejection_criteria": (
                "Shadow 5D WR < production - 2pp OR shadow catastrophic-loss "
                "rate > production + 0.3pp."),
        })
    elif "top3_rank_inversion" in lower:
        base.update({
            "metric":             "shadow_top3_5D_WR",
            "secondary_metrics":  ["shadow_rank_4_7_5D_WR","universe_ma20_hit_rate",
                                   "shadow_MAE_avg","daily_new_rec_count_delta"],
            "null_hypothesis":    ("Gating R1 top-3 through MA20-dist +1..+5 does "
                                   "not change shadow top-3 5D WR by more than "
                                   "+/-3pp."),
            "acceptance_criteria": (
                "Shadow top-3 5D WR >= production top-3 5D WR + 10pp AND does "
                "NOT reduce rank_4_7 quality by more than 2pp on n>=50 top-3 "
                "candidates."),
            "rejection_criteria": (
                "Daily rec-count drop > 30% for 5 consecutive days OR shadow "
                "top-3 5D WR < production top-3 - 3pp."),
        })
    elif "band_boundary" in lower:
        base.update({
            "metric":             "band_ordering_monotonicity",
            "secondary_metrics":  ["per_band_5D_WR","per_band_avg_pct"],
            "null_hypothesis":    ("Re-tuning OK/MARGINAL split does not restore "
                                   "monotonic ordering QUALITY > OK > MARGINAL > "
                                   "AVOID."),
            "acceptance_criteria": (
                "Shadow band ordering becomes strictly monotonic in 5D WR with "
                "n>=100 per band across the observation window. Regularized "
                "cross-validation split must survive at least one holdout."),
            "rejection_criteria": (
                "Any band flips ordering within the window · treat as overfit "
                "and abort."),
        })
    elif "stop_policy" in lower:
        base.update({
            "metric":             "expectancy_gap_vs_current",
            "secondary_metrics":  ["catastrophic_loss_rate","MFE_captured",
                                   "profit_factor","stop_hit_rate"],
            "null_hypothesis":    ("Advisory TIME_STOP_5D exit does not improve "
                                   "median forward-return from advisory date by "
                                   "more than +/-0.1%."),
            "acceptance_criteria": (
                "Median advisory return over next 5D >= median current-policy "
                "return + 0.3% AND catastrophic-loss rate <= current on n>=100 "
                "advisory events."),
            "rejection_criteria": (
                "MFE-captured drops by more than 0.5% vs current · signals "
                "that time-exit is forfeiting winners."),
        })
    elif "negative_alpha" in lower:
        base.update({
            "metric":             "shadow_alpha_vs_universe",
            "secondary_metrics":  ["compound_5D_WR","per_component_attribution"],
            "null_hypothesis":    ("Compound shadow of T1+T2+T3+T4 does not lift "
                                   "AEGIS-India above 0-alpha vs universe."),
            "acceptance_criteria": (
                "Compound-shadow 5D WR >= universe-WR + 3pp AND compound-shadow "
                "avg > universe avg on n>=100 forward India predictions."),
            "rejection_criteria": (
                "Any single component regresses beyond -2pp WR when compared "
                "to production baseline · re-run components in isolation."),
        })
    else:
        base.update({
            "metric":             "primary_forward_metric_TBD",
            "secondary_metrics":  ["avg_pct","MAE_avg"],
            "null_hypothesis":    "No effect vs production baseline.",
            "acceptance_criteria": "Beat baseline on n>=100 forward observations.",
            "rejection_criteria": "Regress on baseline on n>=30 forward observations.",
        })
    return base


def build(root: Path) -> list:
    shortlist = _load(root, "mr_hypothesis_shortlist.json")
    if not shortlist: return []
    hyps = shortlist.get("shortlist") or []
    return [_spec_for(h) for h in hyps]


def emit(root: Path, experiments: list) -> tuple:
    dst_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    dst_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for e in experiments:
        p = dst_dir / f"{e['experiment_id']}.json"
        p.write_text(json.dumps(e, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
        paths.append(p)
    idx = {
        "engine":       ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_experiments": len(experiments),
        "experiments": [{
            "experiment_id":       e["experiment_id"],
            "source_ticket_id":    e["source_ticket_id"],
            "market":              e["market"],
            "current_status":      e["current_status"],
            "min_sample_size":     e["min_sample_size"],
            "observation_window_days": e["observation_window_days"],
            "metric":              e["metric"],
        } for e in experiments],
    }
    idx_p = dst_dir / "INDEX.json"
    idx_p.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")
    return (paths, idx_p)


def render_console(experiments: list):
    print(f"\n======== WALK-FORWARD EXPERIMENTS · n={len(experiments)} ========")
    for e in experiments:
        print(f"\n  [{e['experiment_id']}]")
        print(f"    market:     {e['market']}")
        print(f"    metric:     {e['metric']}")
        print(f"    min N:      {e['min_sample_size']}")
        print(f"    window:     {e['observation_window_days']} days")
        print(f"    status:     {e['current_status']}")
        print(f"    acceptance: {e['acceptance_criteria']}")
        print(f"    rejection:  {e['rejection_criteria']}")


if __name__ == "__main__":
    root = Path(".").resolve()
    experiments = build(root)
    paths, idx = emit(root, experiments)
    render_console(experiments)
    print(f"\n[walkforward_experiment] wrote {len(paths)} experiments + INDEX "
          f"-> {idx.parent}")
