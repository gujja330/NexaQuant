"""Explainability Layer · Layer 3 of the Research Platform.

Answers the daily question "why did the leader win today?" by decomposing
today's edge across:
    · sector attribution   · which sectors drove the delta
    · biggest disagreement · today's highest-impact BUY_vs_WAIT etc.
    · top winner / loser   · per runner
    · pick-set differences · what R2 held that R1 didn't (and vice versa)

Emits reports/research/explainability_YYYY-MM-DD.json daily · one file
per day so we can trace the narrative over the 60/90-day window.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.research.explainability.v1.20260731"


def _load_positions(root: Path, runner: str) -> dict:
    p = root / "reports" / "research" / runner / "positions.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("positions") or {}
    except Exception:
        return {}


def _ret(pos: dict) -> float:
    entry = pos.get("entry_price") or 0
    last = pos.get("last_seen_price") or 0
    if entry <= 0:
        return 0.0
    return (last / entry - 1.0) * 100


def compute_daily_explainability(root: Path, as_of: str | None = None) -> dict:
    """Emit today's explainability report and return it."""
    as_of = as_of or date.today().isoformat()

    r1 = _load_positions(root, "runner1")
    r2 = _load_positions(root, "runner2")

    r1_ret = round(sum(_ret(p) for p in r1.values()) / len(r1), 3) if r1 else 0.0
    r2_ret = round(sum(_ret(p) for p in r2.values()) / len(r2), 3) if r2 else 0.0
    edge = round(r2_ret - r1_ret, 3)
    leader = "RUNNER_2" if edge > 0 else ("RUNNER_1" if edge < 0 else "TIE")

    # Pick set diffs
    r1_tickers = set(r1.keys())
    r2_tickers = set(r2.keys())
    only_r1 = sorted(r1_tickers - r2_tickers)
    only_r2 = sorted(r2_tickers - r1_tickers)
    shared = sorted(r1_tickers & r2_tickers)

    def _top_bottom(pos_map: dict, k: int = 3):
        pairs = [(t, _ret(p)) for t, p in pos_map.items()]
        pairs.sort(key=lambda x: x[1])
        losers = [{"ticker": t, "ret_pct": round(r, 3)} for t, r in pairs[:k]]
        winners = [{"ticker": t, "ret_pct": round(r, 3)} for t, r in pairs[-k:][::-1]]
        return winners, losers

    r1_winners, r1_losers = _top_bottom(r1)
    r2_winners, r2_losers = _top_bottom(r2)

    # Biggest single-position edge in R2's favor · picks R2 has that R1 doesn't
    biggest_edge = None
    if only_r2:
        cand = sorted(((t, _ret(r2[t])) for t in only_r2),
                        key=lambda x: x[1], reverse=True)
        if cand:
            biggest_edge = {"ticker": cand[0][0], "ret_pct": round(cand[0][1], 3),
                              "why_it_helps": "R2-only pick that outperformed"}

    # Biggest single-position miss · picks R1 has that R2 doesn't
    biggest_miss = None
    if only_r1:
        cand = sorted(((t, _ret(r1[t])) for t in only_r1),
                        key=lambda x: x[1])
        if cand:
            biggest_miss = {"ticker": cand[0][0], "ret_pct": round(cand[0][1], 3),
                              "why_it_hurt": "R1-only pick that underperformed"}

    # Sector attribution (uses sectors from disagreement store's live snapshot)
    try:
        from .disagreement_store import _load_runner1_actions, _load_runner2_actions
        r1_actions = _load_runner1_actions(root)
        r2_actions = _load_runner2_actions(root)

        def _by_sector(pos_map, action_map):
            agg = {}
            for t, p in pos_map.items():
                sec = (action_map.get(t) or {}).get("sector") or "Unknown"
                agg.setdefault(sec, []).append(_ret(p))
            return {s: round(sum(v) / len(v), 3) for s, v in agg.items() if v}

        r1_by_sec = _by_sector(r1, r1_actions)
        r2_by_sec = _by_sector(r2, r2_actions)
        sector_deltas = []
        for sec in set(r1_by_sec) | set(r2_by_sec):
            delta = round(r2_by_sec.get(sec, 0) - r1_by_sec.get(sec, 0), 3)
            sector_deltas.append({
                "sector":       sec,
                "r1_avg_pct":   r1_by_sec.get(sec, 0.0),
                "r2_avg_pct":   r2_by_sec.get(sec, 0.0),
                "delta_pp":     delta,
            })
        sector_deltas.sort(key=lambda x: abs(x["delta_pp"]), reverse=True)
        sector_deltas = sector_deltas[:8]
    except Exception:
        sector_deltas = []

    report = {
        "engine":              "aegis.research.explainability.v1",
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "as_of":               as_of,
        "run_utc":             datetime.now(timezone.utc).isoformat(),
        "r1_avg_return_pct":   r1_ret,
        "r2_avg_return_pct":   r2_ret,
        "edge_pp":             edge,
        "leader_today":        leader,
        "pick_sets": {
            "n_shared":        len(shared),
            "n_only_r1":       len(only_r1),
            "n_only_r2":       len(only_r2),
            "shared":          shared[:20],
            "only_r1":         only_r1[:20],
            "only_r2":         only_r2[:20],
        },
        "biggest_edge":        biggest_edge,
        "biggest_miss":        biggest_miss,
        "r1_top_winners":      r1_winners,
        "r1_top_losers":       r1_losers,
        "r2_top_winners":      r2_winners,
        "r2_top_losers":       r2_losers,
        "sector_attribution":  sector_deltas,
        "narrative":           _build_narrative(leader, edge, biggest_edge, biggest_miss,
                                                    sector_deltas),
    }
    out = root / "reports" / "research" / f"explainability_{as_of}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _build_narrative(leader, edge, biggest_edge, biggest_miss, sector_deltas) -> str:
    parts = []
    if leader == "TIE":
        parts.append("Both runners tied today.")
    else:
        parts.append(f"{leader} led by {abs(edge):.2f}pp.")
    if biggest_edge:
        parts.append(f"Biggest win: {biggest_edge['ticker']} "
                          f"({biggest_edge['ret_pct']:+.2f}%) — R2-only pick.")
    if biggest_miss:
        parts.append(f"Biggest miss: {biggest_miss['ticker']} "
                          f"({biggest_miss['ret_pct']:+.2f}%) — R1-only pick.")
    if sector_deltas:
        top = sector_deltas[0]
        parts.append(f"Top sector delta: {top['sector']} "
                          f"({top['delta_pp']:+.2f}pp in R2 favor).")
    return " ".join(parts)
