"""
MON001 baseline expected envelopes derived from LAB009 State C (period-corrected, `413a735`).

Reads LAB009 N0=63 diagnostics and constructs the ENVELOPE (min/median/max across the 4
phase indices, per cash level, at canonical cost). This is the SEALED envelope MON001
compares forward observations against.

The envelope is computed once at MON001 seal-init time and cached to a JSON file. On every
subsequent run, the envelope must be re-derivable BYTE-IDENTICAL from the LAB009 diagnostics
CSV — a divergence indicates either the LAB009 evidence was mutated (a research integrity
issue) or the envelope-building code changed (a MON001 code drift).

Reads-only against LAB009 evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


CANONICAL_KEYS = (
    "sharpe_full", "cagr_full", "max_dd_full", "sharpe_conf", "cost_drag",
)


def _canonical_dump(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str, indent=2)


def build_envelope(diagnostics_csv: Path, candidate: str, horizon_days: int,
                   canonical_cost_bps: float, cash_grid: list[float]) -> dict:
    """Return the sealed envelope structure.

    Uses phase-level rows (aggregate == 'phase') for the given candidate/horizon at the
    canonical cost. The envelope is {metric: {cash: {min, median, max, phases: [...]}}}.
    """
    df = pd.read_csv(diagnostics_csv)
    df = df[(df["candidate"] == candidate) & (df["horizon_days"] == horizon_days)
            & (df["aggregate"] == "phase") & (df["cost_bps"] == canonical_cost_bps)]
    if df.empty:
        raise ValueError(
            f"no phase rows for candidate={candidate} horizon={horizon_days} "
            f"cost={canonical_cost_bps} in {diagnostics_csv}")

    envelope: dict = {
        "source": {
            "diagnostics_csv": str(diagnostics_csv),
            "candidate": candidate,
            "horizon_days": horizon_days,
            "canonical_cost_bps": canonical_cost_bps,
            "cash_grid": list(cash_grid),
        },
        "metrics": {},
    }

    for cash in cash_grid:
        sub = df[df["cash_annual"] == cash].sort_values("phase_offset")
        for m in CANONICAL_KEYS:
            if m not in sub.columns:
                continue
            vals = [float(v) for v in sub[m].tolist()]
            if not vals:
                continue
            metric_key = m
            envelope["metrics"].setdefault(metric_key, {})
            envelope["metrics"][metric_key][str(cash)] = {
                "min": min(vals),
                "median": float(pd.Series(vals).median()),
                "max": max(vals),
                "phases": vals,
                "n_phases": len(vals),
            }

    # Also derive: median cost_drag = canonical_cagr - stress_cagr, from the "median" aggregate rows.
    med = pd.read_csv(diagnostics_csv)
    med = med[(med["candidate"] == candidate) & (med["horizon_days"] == horizon_days)
              & (med["aggregate"] == "median")]
    envelope["median_row"] = {}
    for cash in cash_grid:
        sub = med[(med["cash_annual"] == cash) & (med["cost_bps"] == canonical_cost_bps)]
        if sub.empty:
            continue
        row = sub.iloc[0]
        envelope["median_row"][str(cash)] = {
            "sharpe_full": float(row.get("sharpe_full", float("nan"))),
            "cagr_full": float(row.get("cagr_full", float("nan"))),
            "max_dd_full": float(row.get("max_dd_full", float("nan"))),
            "sharpe_conf": float(row.get("sharpe_conf", float("nan"))),
            "cost_drag": float(row.get("cost_drag", float("nan"))),
        }

    envelope["envelope_hash"] = hashlib.sha256(
        _canonical_dump({k: v for k, v in envelope.items() if k != "envelope_hash"})
        .encode("utf-8")).hexdigest()

    return envelope


def load_or_cache(cache_path: Path, diagnostics_csv: Path, candidate: str,
                  horizon_days: int, canonical_cost_bps: float,
                  cash_grid: list[float]) -> dict:
    """Load the cached envelope if present, else build+cache. Verifies byte-identity
    against the cache on every call — mismatch raises RuntimeError (envelope drift)."""
    fresh = build_envelope(diagnostics_csv, candidate, horizon_days,
                            canonical_cost_bps, cash_grid)
    if cache_path.exists():
        cached_text = cache_path.read_text(encoding="utf-8")
        cached = json.loads(cached_text)
        if cached.get("envelope_hash") != fresh["envelope_hash"]:
            raise RuntimeError(
                f"MON001 baseline envelope drift detected. Cached hash "
                f"{cached.get('envelope_hash')} != freshly-computed {fresh['envelope_hash']}. "
                f"Either the LAB009 diagnostics CSV was mutated or the envelope-building "
                f"code changed. MON001 refuses to run.")
        return cached
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(_canonical_dump(fresh), encoding="utf-8")
    return fresh
