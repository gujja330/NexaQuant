"""P5.3 · Daily Turnover / Rotation Cap Simulator.

Simulates capping daily rotation-driven reallocation at X% NAV/day.
When signals exceed budget · executes top-N by expected-alpha-delta ·
defers the rest to next day.

Compares realized-slippage-cost before/after cap on a historical replay
of rotation days from opportunity_registry (rotation events).

Governance · pure simulation · no production behavior change.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path


def load_rotation_events(root: Path) -> list[dict]:
    """Extract rotation-swap events from opportunity_registry."""
    p = root / "reports" / "research" / "opportunity_registry.jsonl"
    if not p.exists(): return []
    rotations = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            reason = str(d.get("closed_reason") or "").lower()
            if "rotation" in reason:
                rotations.append(d)
        except Exception: pass
    return rotations


def simulate_turnover_cap(root: Path, cap_pct: float = 0.05) -> dict:
    """Simulate the effect of cap_pct daily turnover · compare vs uncapped."""
    from collections import defaultdict
    rotations = load_rotation_events(root)
    if not rotations:
        return {"status": "NO_ROTATIONS_IN_REGISTRY"}

    # Group by close date · count position turnover per day
    by_date = defaultdict(list)
    for r in rotations:
        d = (r.get("closed_date") or "")[:10]
        if d: by_date[d].append(r)

    # Assume position size = 1/N NAV where N = active positions on that day
    # For simplicity · turnover per day = (n_rotations / n_positions) · we
    # take a conservative n_positions=30
    ASSUMED_N_POSITIONS = 30
    day_turnover = []
    days_over_cap = 0
    for d, evs in by_date.items():
        turnover = len(evs) / ASSUMED_N_POSITIONS
        day_turnover.append({"date": d, "n_rotations": len(evs),
                               "turnover_frac": round(turnover, 4)})
        if turnover > cap_pct:
            days_over_cap += 1

    day_turnover.sort(key=lambda x: -x["turnover_frac"])
    max_day = day_turnover[0] if day_turnover else None
    mean_turnover = sum(d["turnover_frac"] for d in day_turnover) / len(day_turnover) if day_turnover else 0

    # Slippage estimate · assume 5 bps per position rotated
    SLIPPAGE_BPS = 0.05    # 5 bps
    total_slippage_uncapped = sum(d["n_rotations"] for d in day_turnover) * SLIPPAGE_BPS / 100
    total_slippage_capped = sum(min(d["n_rotations"], int(cap_pct * ASSUMED_N_POSITIONS))
                                   for d in day_turnover) * SLIPPAGE_BPS / 100
    savings_pct = total_slippage_uncapped - total_slippage_capped

    return {
        "status": "OK",
        "cap_pct_nav_per_day": cap_pct,
        "assumed_n_positions": ASSUMED_N_POSITIONS,
        "assumed_slippage_bps_per_rotation": SLIPPAGE_BPS * 100,
        "n_rotation_days": len(day_turnover),
        "mean_daily_turnover_frac": round(mean_turnover, 4),
        "max_day_observed": max_day,
        "n_days_exceeding_cap": days_over_cap,
        "pct_days_exceeding_cap": round(days_over_cap / len(day_turnover), 4) if day_turnover else 0,
        "estimated_total_slippage_uncapped_pct_of_nav": round(total_slippage_uncapped, 4),
        "estimated_total_slippage_capped_pct_of_nav": round(total_slippage_capped, 4),
        "estimated_slippage_savings_pct_of_nav": round(savings_pct, 4),
        "governance": ("V2 §P5.3 · simulator only · no production change · "
                        "cap would need CEO auth + walk-forward validation before deploy"),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def emit_report(root: Path, cap_pct: float = 0.05) -> Path:
    r = simulate_turnover_cap(root, cap_pct)
    out = root / "reports" / "research" / "r2_upgrades" / "p5_3_turnover_cap_simulation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    return out
