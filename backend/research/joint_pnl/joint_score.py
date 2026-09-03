"""Joint positive+negative scoring for a candidate strategy.

Ingest:
    NEG-PNL-CONTROL-60D variants (from E-016 output)
    POS-PNL-CAPTURE-60D per-winner-definition metrics (from E-017 output)

Emit:
    per-strategy joint score card
    a Pareto frontier: strategies that dominate on BOTH sides at once
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def build_joint_score(neg_variant: dict, pos_definition: dict) -> dict:
    """Compose one candidate strategy's joint metrics.

    neg_variant · one entry from panel.counterfactual_variants
    pos_definition · one entry from panel.per_winner_definition (a chosen def)
    """
    # NEG side · protection + damage
    prot = neg_variant.get("protection", {}) or {}
    damg = neg_variant.get("damage", {}) or {}
    delta_pnl = prot.get("delta", 0.0)          # counterfactual - actual (can be negative)
    n_winners_sac = damg.get("n_winners_sacrificed", 0)
    winner_sac_rate = damg.get("winner_sacrifice_rate", 0.0)
    forfeited_upside = damg.get("forfeited_upside_sum", 0.0)
    n_deep_avoided = prot.get("n_deep_losses_avoided", 0)

    # POS side · winner capture
    tp = pos_definition.get("tp", 0)
    fp = pos_definition.get("fp", 0)
    fn = pos_definition.get("fn", 0)
    prec = pos_definition.get("precision", 0.0)
    rec = pos_definition.get("recall", 0.0)
    f1 = pos_definition.get("f1", 0.0)
    missed_cost = pos_definition.get("missed_winner_cost_sum_pct", 0.0)

    # Joint score · weighted combination (weights predeclared · not tuned)
    # Positive terms increase score; negative terms decrease it.
    # This is a research diagnostic · not a production decision function.
    JOINT_WEIGHTS = {
        "delta_pnl":            1.0,
        "winner_capture":       0.5,      # per +1 winner captured
        "winner_sacrifice":    -1.0,      # per +1 winner destroyed
        "deep_loss_avoided":    0.3,
        "forfeited_upside":    -0.5,      # per +1% forfeited
    }
    raw_score = (
        JOINT_WEIGHTS["delta_pnl"]            * delta_pnl
        + JOINT_WEIGHTS["winner_capture"]     * tp
        + JOINT_WEIGHTS["winner_sacrifice"]   * n_winners_sac
        + JOINT_WEIGHTS["deep_loss_avoided"]  * n_deep_avoided
        + JOINT_WEIGHTS["forfeited_upside"]   * forfeited_upside
    )

    return {
        "neg_variant_id": (f"static_pct@{neg_variant.get('threshold_pct')}"
                           if neg_variant.get("doctrine") == "static_pct"
                           else f"static_time@{neg_variant.get('timing_days')}d"),
        "pos_definition_id": pos_definition.get("_id"),
        "delta_pnl":                delta_pnl,
        "n_winners_sacrificed":     n_winners_sac,
        "winner_sacrifice_rate":    winner_sac_rate,
        "n_deep_losses_avoided":    n_deep_avoided,
        "forfeited_upside_sum":     forfeited_upside,
        "pos_precision":            prec,
        "pos_recall":               rec,
        "pos_f1":                   f1,
        "pos_tp":                   tp,
        "pos_fp":                   fp,
        "pos_fn":                   fn,
        "missed_winner_cost_sum":   missed_cost,
        "joint_score_raw":          round(raw_score, 4),
        "joint_weights_used":       JOINT_WEIGHTS,
        "governance_note": (
            "Diagnostic score only · does NOT authorize production change. "
            "A high joint_score_raw is a candidate for further research (WF + "
            "OOS + stat-sig + MT correction), not a promotion signal."
        ),
    }


def joint_pnl_frontier(root: Path, market: str,
                       neg_panel_path: str | None = None,
                       pos_panel_path: str | None = None,
                       pos_definition_key: str = "h20_t10pct") -> dict:
    """Cross NEG variants × chosen POS winner definition · emit joint score
    per pair · report which strategies dominate BOTH sides."""
    r = root / "reports" / "research"
    neg_path = Path(neg_panel_path) if neg_panel_path else (r / "neg_pnl_control_60d" / f"panel_{market}.json")
    pos_path = Path(pos_panel_path) if pos_panel_path else (r / "pos_pnl_capture_60d" / f"panel_{market}.json")
    if not neg_path.exists():
        return {"market": market, "status": "NEG_PANEL_MISSING", "expected": str(neg_path)}
    if not pos_path.exists():
        return {"market": market, "status": "POS_PANEL_MISSING", "expected": str(pos_path)}

    neg = json.loads(neg_path.read_text(encoding="utf-8"))
    pos = json.loads(pos_path.read_text(encoding="utf-8"))
    pos_def = (pos.get("per_winner_definition") or {}).get(pos_definition_key, {}).copy()
    if not pos_def:
        return {"market": market, "status": "POS_DEFINITION_MISSING",
                "asked": pos_definition_key,
                "available": list((pos.get("per_winner_definition") or {}).keys())}
    pos_def["_id"] = pos_definition_key

    pairs = []
    for v in (neg.get("counterfactual_variants") or []):
        pairs.append(build_joint_score(v, pos_def))

    # Pareto frontier · dominant on {delta_pnl ↑, tp ↑, winners_sacrificed ↓, forfeited_upside ↓}
    def _dominates(a, b):
        return (a["delta_pnl"] >= b["delta_pnl"]
                and a["pos_tp"] >= b["pos_tp"]
                and a["n_winners_sacrificed"] <= b["n_winners_sacrificed"]
                and a["forfeited_upside_sum"] <= b["forfeited_upside_sum"]
                and (a["delta_pnl"] > b["delta_pnl"]
                     or a["pos_tp"] > b["pos_tp"]
                     or a["n_winners_sacrificed"] < b["n_winners_sacrificed"]
                     or a["forfeited_upside_sum"] < b["forfeited_upside_sum"]))

    frontier = []
    for i, cand in enumerate(pairs):
        dominated = False
        for j, other in enumerate(pairs):
            if i == j: continue
            if _dominates(other, cand):
                dominated = True; break
        if not dominated: frontier.append(cand)

    payload = {
        "market": market,
        "pos_definition_used": pos_definition_key,
        "n_neg_variants": len(neg.get("counterfactual_variants") or []),
        "n_joint_pairs": len(pairs),
        "pareto_frontier_size": len(frontier),
        "pairs": pairs,
        "pareto_frontier": frontier,
        "governance_reminder": (
            "Pareto frontier is diagnostic only. Even a frontier strategy "
            "must clear: PIT audit + walk-forward + OOS + statistical "
            "significance + multiple-testing correction (n_trials from "
            "both NEG family × POS family) + evidence gate + paper period "
            "+ explicit CEO authorization before any production consideration."
        ),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out_dir = r / "joint_pnl"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"panel_{market}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    return payload


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--pos-def", default="h20_t10pct")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = joint_pnl_frontier(root, m, pos_definition_key=args.pos_def)
        print(json.dumps(r, indent=2, default=str)[:2500])


if __name__ == "__main__":
    main()
