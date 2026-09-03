"""Composite Meta-Ensemble Engine

Composite_Score(stock) = Σ Trust_Weight(r) × Runner_Score_r(stock)  for r ∈ admitted

Trust_Weight(r):
  = 0                                  if trailing_closed_trades(r) < 50   (sample floor)
  = 0                                  if runner_admission(r) != ADMITTED  (GAP 2)
  = softmax_over_admitted(trailing_ic(r))   otherwise

Cross-runner conviction table (pasted-plan §7):
  All 3 agree             → MAX_CONVICTION
  R2 + R3 agree           → NEAR_FULL
  R1 + R2 agree           → FULL
  R1 + R3 agree, R2 silent → MANUAL_REVIEW
  Only R2                 → EXISTING_R2_SIZING
  Only R1                 → REDUCED_SIZE
  2-of-3 conflict         → WATCH_ONLY
  All silent              → NO_POSITION
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]

SAMPLE_FLOOR = 50


def _load_registry(root: Path) -> dict:
    import yaml
    p = root / "configs" / "aegis_runner_registry.yaml"
    if not p.exists(): return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def admission_state(root: Path, runner: str,
                    trailing_closed_trades: int) -> str:
    """Return ADMITTED or NOT_ADMITTED for a runner given trailing sample.

    R1, R2 default ADMITTED from Day 0 · R3 admitted only when trailing_n >= 50.
    """
    reg = _load_registry(root)
    comp = reg.get("composite", {})
    states = comp.get("admission_state", {})
    policy = states.get(runner, "ADMITTED_FROM_DAY_0")
    if policy == "ADMITTED_FROM_DAY_0":
        return "ADMITTED"
    if policy == "ADMITTED_ON_TRAIL_N_50":
        return "ADMITTED" if trailing_closed_trades >= SAMPLE_FLOOR else "NOT_ADMITTED"
    return "NOT_ADMITTED"


def trust_weight(trailing_ic: float,
                 trailing_closed_trades: int,
                 admission: str) -> float:
    """Apply sample floor + admission gate."""
    if admission != "ADMITTED":
        return 0.0
    if trailing_closed_trades < SAMPLE_FLOOR:
        return 0.0
    # Simple mapping · positive IC → positive weight · downstream normalizes.
    return max(0.0, float(trailing_ic))


def compute_composite_score(runner_scores: dict[str, float],
                            trailing_ic: dict[str, float],
                            trailing_n: dict[str, int],
                            root: Path = _ROOT) -> dict:
    """runner_scores  · {"R1": s1, "R2": s2, "R3": s3}
       trailing_ic    · {"R1": ic1, "R2": ic2, "R3": ic3}
       trailing_n     · {"R1": n1, "R2": n2, "R3": n3}
    """
    admissions = {r: admission_state(root, r, trailing_n.get(r, 0))
                  for r in ("R1", "R2", "R3")}
    raw_w = {r: trust_weight(trailing_ic.get(r, 0.0),
                             trailing_n.get(r, 0),
                             admissions[r])
             for r in ("R1", "R2", "R3")}
    total = sum(raw_w.values())
    norm_w = {r: (raw_w[r] / total) if total > 0 else 0.0 for r in raw_w}
    composite = sum(norm_w[r] * float(runner_scores.get(r, 0.0)) for r in norm_w)

    # Cross-runner conviction · pasted-plan §7
    signals = {r: (1 if float(runner_scores.get(r, 0)) > 0 else
                   (-1 if float(runner_scores.get(r, 0)) < 0 else 0))
               for r in ("R1", "R2", "R3")}
    n_active = sum(1 for s in signals.values() if s != 0)
    same_sign = all(signals[r] == signals["R2"] and signals[r] != 0
                    for r in ("R1", "R2", "R3"))
    conviction = "NO_POSITION"
    if same_sign and n_active == 3:
        conviction = "MAX_CONVICTION"
    elif signals["R2"] != 0 and signals["R3"] == signals["R2"] and signals["R1"] == 0:
        conviction = "NEAR_FULL"
    elif signals["R2"] != 0 and signals["R1"] == signals["R2"] and signals["R3"] == 0:
        conviction = "FULL"
    elif signals["R1"] != 0 and signals["R3"] == signals["R1"] and signals["R2"] == 0:
        conviction = "MANUAL_REVIEW"
    elif signals["R2"] != 0 and signals["R1"] == 0 and signals["R3"] == 0:
        conviction = "EXISTING_R2_SIZING"
    elif signals["R1"] != 0 and signals["R2"] == 0 and signals["R3"] == 0:
        conviction = "REDUCED_SIZE"
    elif n_active >= 2 and not same_sign:
        conviction = "WATCH_ONLY_CONFLICT"

    return {
        "composite_score": composite,
        "trust_weights_normalized": norm_w,
        "trust_weights_raw": raw_w,
        "admissions": admissions,
        "conviction": conviction,
        "n_runners_active": n_active,
        "runner_signals": signals,
    }
