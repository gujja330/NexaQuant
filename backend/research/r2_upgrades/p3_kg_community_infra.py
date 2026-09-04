"""P3 · KG Community-Relative Scoring · ENGINEERING INFRASTRUCTURE ONLY.

CEO 2026-09-05 Phase 4 exception: engineering may be developed provided that
substrate-before-sophistication rule is preserved and no promotion occurs.

Builds the computation path:
    global percentile + community percentile → γ-blended final_score
without wiring it into any production R2 code path. Evidence decision remains
frozen until F01-F05 substrate reaches `Tested`.

Reads:
  reports/research/kg/latest.json (community assignments per ticker)
  ensemble.json (base_score per ticker)

Writes (research-only):
  reports/research/r2_upgrades/p3_kg_community_relative_{market}.json
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path


def compute_community_relative_ranks(root: Path, market: str, gamma: float = 0.2) -> dict:
    """γ-blended (global + community) percentile ranking · read-only research.

    Governance: NEVER writes to configs/ensemble_weights_adaptive.yaml,
    NEVER writes to any production recommendation path. Emits research JSON only.
    """
    ens_p = (root / market / "reports" / "ensemble.json"
             if market.lower() == "usa"
             else root / "reports" / "ensemble.json")
    if not ens_p.exists():
        return {"status": "MISSING_ENSEMBLE", "market": market}
    ens = json.loads(ens_p.read_text(encoding="utf-8"))
    top = ens.get("top_10") or []
    if not top:
        return {"status": "EMPTY_ENSEMBLE", "market": market}

    # Load KG communities · try known locations
    kg_paths = [
        root / "reports" / "research" / "kg" / f"{market}_latest.json",
        root / "reports" / "research" / "kg" / "latest.json",
        root / "reports" / "kg_communities.json",
    ]
    community_of: dict[str, str] = {}
    kg_source = None
    for p in kg_paths:
        if p.exists():
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(j, dict):
                    # Try common shapes
                    for k in ("community_of", "ticker_community", "communities"):
                        if k in j and isinstance(j[k], dict):
                            community_of = {str(t).upper(): str(c) for t, c in j[k].items()}
                            kg_source = str(p.relative_to(root))
                            break
                if community_of: break
            except Exception: pass

    if not community_of:
        # No KG snapshot available · report as substrate-blocked
        return {"status": "KG_SUBSTRATE_MISSING", "market": market,
                 "paths_tried": [str(p.relative_to(root)) for p in kg_paths],
                 "note": "P3 infra ready · needs KG community snapshot to compute"}

    # Global percentile ranking
    scored = [(str(e.get("ticker","")).upper().split(".",1)[0],
                float(e.get("ensemble_score", 0))) for e in top]
    scored_sorted = sorted(scored, key=lambda x: x[1])
    global_pct = {t: i / max(len(scored_sorted) - 1, 1) for i, (t, _) in enumerate(scored_sorted)}

    # Community percentile · rank each ticker within its community
    from collections import defaultdict
    by_community: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for t, s in scored:
        c = community_of.get(t)
        if c: by_community[c].append((t, s))
    community_pct: dict[str, float] = {}
    for c, members in by_community.items():
        members_sorted = sorted(members, key=lambda x: x[1])
        n = len(members_sorted)
        for i, (t, _) in enumerate(members_sorted):
            community_pct[t] = i / max(n - 1, 1)

    # Blended final score
    rows = []
    for t, s in scored:
        g = global_pct.get(t, 0.5)
        c = community_pct.get(t, g)   # fallback to global if not in a community
        final = (1.0 - gamma) * g + gamma * c
        rows.append({"ticker": t, "base_score": round(s, 4),
                      "community_id": community_of.get(t),
                      "global_percentile": round(g, 4),
                      "community_percentile": round(c, 4),
                      "final_score": round(final, 4)})

    return {
        "status": "OK",
        "market": market,
        "gamma": gamma,
        "n_tickers": len(rows),
        "n_communities_used": len(by_community),
        "kg_snapshot_source": kg_source,
        "rows": rows,
        "governance": ("V2 §P3 · ENGINEERING ONLY · never modifies R2 production · "
                        "γ sweep + walk-forward evidence frozen until F01-F05 Tested "
                        "per substrate-before-sophistication rule"),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def emit_report(root: Path, market: str, gamma: float = 0.2) -> Path:
    r = compute_community_relative_ranks(root, market, gamma)
    out = root / "reports" / "research" / "r2_upgrades" / f"p3_kg_community_relative_{market}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    return out
