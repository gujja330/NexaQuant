"""P5.1 · Ensemble Disagreement Display + Sizing.

Reads per-model scores from R2 ensemble.json · computes disagreement metrics:
  · stdev(scores) normalized to [0,1] across day's candidate set
  · IQR
  · fraction of models scoring 0 (abstention count)

Correlation with realized-return-error is DEFERRED to when outcome_dataset has
enough matured samples per candidate (evidence-waiting).

Governance · pure infrastructure · NOT a sizing rule yet. Output artifact
consumed by future sizing multiplier only after P1 calibration gate clears.
"""
from __future__ import annotations
import json
import math
from datetime import datetime
from pathlib import Path


def _stdev(vals: list[float]) -> float:
    if len(vals) < 2: return 0.0
    mu = sum(vals) / len(vals)
    var = sum((v - mu)**2 for v in vals) / (len(vals) - 1)
    return math.sqrt(var) if var > 0 else 0.0


def _iqr(vals: list[float]) -> float:
    if len(vals) < 4: return 0.0
    s = sorted(vals)
    q1 = s[len(s)//4]
    q3 = s[3*len(s)//4]
    return q3 - q1


def compute_disagreement_for_snapshot(root: Path, market: str) -> dict:
    """Read latest ensemble.json for market · compute per-ticker disagreement."""
    p = (root / market / "reports" / "ensemble.json"
         if market.lower() == "usa"
         else root / "reports" / "ensemble.json")
    if not p.exists():
        return {"market": market, "status": "MISSING", "reason": "ensemble.json not found"}
    j = json.loads(p.read_text(encoding="utf-8"))
    top = j.get("top_10") or []
    if not top:
        return {"market": market, "status": "EMPTY"}
    rows = []
    all_stdev = []
    for entry in top:
        per_model = entry.get("per_model_score") or {}
        scores = [float(v) for v in per_model.values()]
        abstains = sum(1 for v in scores if v == 0.0)
        active = [v for v in scores if v != 0.0]
        if not active: continue
        s = _stdev(active)
        i = _iqr(active)
        all_stdev.append(s)
        rows.append({
            "ticker": entry.get("ticker"),
            "n_models_total": len(scores),
            "n_models_abstained": abstains,
            "n_models_active": len(active),
            "stdev_active": round(s, 4),
            "iqr_active": round(i, 4),
            "min_score": round(min(active), 4),
            "max_score": round(max(active), 4),
            "abstention_rate": round(abstains / len(scores), 3) if scores else 0,
        })
    # Normalize stdev to [0,1] across the day's set
    max_s = max(all_stdev) if all_stdev else 1.0
    for r, s in zip(rows, all_stdev):
        r["disagreement_norm"] = round(s / max_s, 4) if max_s > 0 else 0.0
    return {
        "market": market,
        "status": "OK",
        "asof": j.get("asof"),
        "n_candidates_scored": len(rows),
        "per_ticker": rows,
        "aggregate_median_disagreement": round(sorted(all_stdev)[len(all_stdev)//2], 4) if all_stdev else 0.0,
        "governance": "V2 §P5.1 · display only · sizing rule DEFERRED until P1 calibration gate clears",
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def emit_report(root: Path, market: str) -> Path:
    result = compute_disagreement_for_snapshot(root, market)
    out = root / "reports" / "research" / "r2_upgrades" / f"p5_1_disagreement_{market}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return out
