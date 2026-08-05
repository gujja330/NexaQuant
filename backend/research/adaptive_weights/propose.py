"""Adaptive Weight Proposal engine.

Reads:
    reports/research/monthly/feature_attribution_{market}_{month}.json
    reports/research/monthly/model_winrate_{market}_{month}.json
    configs/adaptive_ensemble_weights.json  (current live weights · READ-ONLY)

Writes:
    configs/proposed_ensemble_weights.json  (proposal · never auto-applied)

Method (transparent · reproducible):
    1. Start from current live weights
    2. For each model with rollup evidence:
        · edge_pp    = feature_attribution edge (win_share - loss_share)
        · winrate_pp = model_winrate.win_rate_pct - 50 (deviation from coin flip)
        · combined   = 0.5 × edge_pp + 0.5 × winrate_pp
    3. Adjust weight by combined × 0.005 (max ±5% relative change per proposal)
    4. Cap: no single model < 0.02 · no single model > 0.30
    5. Renormalise so weights sum to 1.0

Result: a diffable proposal file with reasoning. Operator runs
scripts/review_proposed_weights.py to see diff · approves manually by
copying to configs/adaptive_ensemble_weights.json.

DELIBERATELY conservative · no dramatic rebalances · slow drift toward
what evidence supports.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


MAX_RELATIVE_CHANGE = 0.05     # ±5% per proposal (tight guardrail)
MIN_WEIGHT = 0.02
MAX_WEIGHT = 0.30
ADJUSTMENT_SCALE = 0.005       # combined edge × this = weight delta


@dataclass
class WeightProposal:
    model_id: str
    label: str
    current_weight: float
    proposed_weight: float
    delta: float
    justification: str
    edge_pp: float | None = None
    winrate_pp: float | None = None
    n_samples: int = 0
    insufficient_data: bool = False


LIVE_WEIGHTS_CANDIDATES = [
    "reports/adaptive_ensemble_weights.json",   # daily-refreshed authoritative
    "configs/ensemble_weights_adaptive.yaml",   # reference source
    "configs/adaptive_ensemble_weights.json",   # legacy fallback
]


def _live_weights(root: Path) -> dict:
    for rel in LIVE_WEIGHTS_CANDIDATES:
        p = root / rel
        if not p.exists(): continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            # Prefer adaptive_weights key · else weights · else the whole dict
            for key in ("adaptive_weights", "weights"):
                if isinstance(d.get(key), dict):
                    return d[key]
            if all(isinstance(v, (int, float)) for v in d.values()):
                return d
        except Exception:
            continue
    return {}


def _load_attr(root: Path, market: str, month: str) -> dict:
    p = root / "reports" / "research" / "monthly" / \
            f"feature_attribution_{market}_{month}.json"
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _load_winrate(root: Path, market: str, month: str) -> dict:
    p = root / "reports" / "research" / "monthly" / \
            f"model_winrate_{market}_{month}.json"
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def compute(root: Path, market: str, month: str) -> dict:
    live = _live_weights(root)
    attr = _load_attr(root, market, month)
    winrate = _load_winrate(root, market, month)

    if not live:
        return {
            "engine":  "aegis.research.adaptive_weights.v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "market":  market, "month": month,
            "status":  "SKIP",
            "reason":  "no live weights file to base proposal on",
            "proposals": [],
        }

    attr_map = {m["model_id"]: m for m in (attr.get("models") or [])}
    win_map = {m["model_id"]: m for m in (winrate.get("models") or [])}

    proposals: list[WeightProposal] = []
    for mid, current in live.items():
        current_f = float(current)
        a = attr_map.get(mid) or {}
        w = win_map.get(mid) or {}
        edge = a.get("edge_pp")
        win_pct = w.get("win_rate_pct")
        n = w.get("n_picks") or a.get("n_wins", 0) + a.get("n_losses", 0)
        insufficient = a.get("insufficient_data", True) and w.get("insufficient_data", True)

        if insufficient:
            proposals.append(WeightProposal(
                model_id=mid, label=(a.get("label") or w.get("label") or mid),
                current_weight=round(current_f, 4),
                proposed_weight=round(current_f, 4), delta=0.0,
                justification="insufficient monthly data · no change proposed",
                edge_pp=edge, winrate_pp=(win_pct - 50 if win_pct is not None else None),
                n_samples=n, insufficient_data=True,
            ))
            continue

        edge_pp = float(edge) if edge is not None else 0.0
        winrate_pp = float(win_pct - 50) if win_pct is not None else 0.0
        combined = 0.5 * edge_pp + 0.5 * winrate_pp

        raw_delta = combined * ADJUSTMENT_SCALE
        # Cap relative change
        max_delta = current_f * MAX_RELATIVE_CHANGE
        delta = max(-max_delta, min(max_delta, raw_delta))
        proposed = max(MIN_WEIGHT, min(MAX_WEIGHT, current_f + delta))
        actual_delta = round(proposed - current_f, 4)

        justif = []
        if edge_pp > 0.5: justif.append(f"attribution edge +{edge_pp:.2f}pp")
        elif edge_pp < -0.5: justif.append(f"attribution edge {edge_pp:.2f}pp")
        if winrate_pp > 5: justif.append(f"win rate +{winrate_pp:.1f}pp above 50%")
        elif winrate_pp < -5: justif.append(f"win rate {winrate_pp:.1f}pp below 50%")
        if not justif: justif.append("mixed signals · minimal adjustment")

        proposals.append(WeightProposal(
            model_id=mid, label=(a.get("label") or w.get("label") or mid),
            current_weight=round(current_f, 4),
            proposed_weight=round(proposed, 4),
            delta=actual_delta,
            justification=" · ".join(justif),
            edge_pp=round(edge_pp, 2), winrate_pp=round(winrate_pp, 1),
            n_samples=n, insufficient_data=False,
        ))

    # Renormalise so sum = 1
    total_proposed = sum(p.proposed_weight for p in proposals)
    if total_proposed > 0:
        for p in proposals:
            p.proposed_weight = round(p.proposed_weight / total_proposed, 4)
            p.delta = round(p.proposed_weight - p.current_weight, 4)

    return {
        "engine":          "aegis.research.adaptive_weights.v1",
        "generated_utc":   datetime.now(timezone.utc).isoformat(),
        "market":          market, "month": month,
        "status":          "OK",
        "n_models":        len(proposals),
        "auto_applied":    False,     # explicitly · never auto
        "operator_action": "Review with scripts/review_proposed_weights.py · "
                              "approve by copying to configs/adaptive_ensemble_weights.json",
        "config_bounds": {
            "max_relative_change_per_proposal": MAX_RELATIVE_CHANGE,
            "min_weight":                       MIN_WEIGHT,
            "max_weight":                       MAX_WEIGHT,
            "adjustment_scale":                 ADJUSTMENT_SCALE,
        },
        "proposals":       [asdict(p) for p in proposals],
    }


def emit(root: Path, payload: dict) -> Path:
    p = root / "configs" / "proposed_ensemble_weights.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p
