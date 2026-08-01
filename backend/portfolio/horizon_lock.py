"""R006 · Phase 4 · Horizon Lock (dynamic-per-rec for R2 · static for R1).

Operator directive 2026-08-01:
    "runner 1 is static i guess, runner 2 should be complete dynamic"

Model:
    · Runner 1  → STATIC · horizon fixed by legacy CSV (2 months / 60d)
    · Runner 2  → DYNAMIC · each position's horizon comes from the engine's
      per-rec `position_plan.time_horizon_days` value · LOCKED at OPEN
      · never mutated for the lifetime of that specific position

The "no mixed horizons" invariant from Issue #8 still applies · but at
the POSITION level (a single position's horizon never changes) · not at
the RUNNER level (different R2 positions CAN have different horizons ·
that's what "dynamic" means).

Called by portfolio_manager · never by the delivery engine.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

FALLBACK_HORIZON_DAYS = 17


def _config_path(root: Path) -> Path:
    return root / "configs" / "runner_horizons.json"


def _load_config(root: Path) -> dict:
    p = _config_path(root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def horizon_for_rec(root: Path, runner: str, rec: Mapping) -> int:
    """Return the horizon (days) for a single recommendation.

    Precedence for Runner 2:
        1. rec.position_plan.time_horizon_days  (engine's dynamic decision)
        2. rec.time_horizon_days                (some older shape)
        3. runner2.fallback_horizon_days from config
        4. FALLBACK_HORIZON_DAYS (17)

    Precedence for Runner 1 (SEALED):
        1. runner1.static_horizon_days from config (default 60)
    """
    cfg = _load_config(root).get("runners") or {}
    runner_cfg = cfg.get(runner) or {}
    source = runner_cfg.get("horizon_source")

    if source == "static_csv" or runner == "runner1":
        # Runner 1 is static · 60 days by default
        return int(runner_cfg.get("static_horizon_days") or 60)

    # Runner 2 (or anything dynamic) · read from the rec itself
    pp = rec.get("position_plan") or {} if isinstance(rec, Mapping) else {}
    h = pp.get("time_horizon_days") or rec.get("time_horizon_days") if isinstance(rec, Mapping) else None
    if isinstance(h, (int, float)) and h > 0:
        return int(h)

    return int(runner_cfg.get("fallback_horizon_days") or FALLBACK_HORIZON_DAYS)


def is_dynamic_runner(root: Path, runner: str) -> bool:
    cfg = _load_config(root).get("runners") or {}
    return (cfg.get(runner) or {}).get("horizon_source") == "dynamic_per_rec"


def validate_no_position_horizon_mutation(root: Path, runner: str) -> dict:
    """Detect if any position's horizon changed between OPEN and now.

    Reads portfolio_ledger to check that a ticker's horizon_days recorded
    at OPEN matches all subsequent HOLD/REBALANCE events for that same
    ticker. A change = bug (Issue #8 · horizon should be locked-at-open).
    """
    from .portfolio_ledger import load_all_events
    events = load_all_events(root, runner=runner)
    per_ticker_horizons: dict[str, set] = {}
    for e in events:
        if e.horizon_days is None:
            continue
        per_ticker_horizons.setdefault(e.ticker, set()).add(int(e.horizon_days))

    mutated = {t: sorted(hs) for t, hs in per_ticker_horizons.items() if len(hs) > 1}
    return {
        "verdict":       "OK" if not mutated else "MUTATED",
        "n_positions":   len(per_ticker_horizons),
        "n_mutated":     len(mutated),
        "mutated":       mutated,
    }
