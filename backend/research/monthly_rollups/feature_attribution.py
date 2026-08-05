"""Monthly rollup · Feature Attribution.

For every closed position in the month, pull the `attribution.per_model`
data from the entry-time rec snapshot (recommendations_history/{market}/
{asof}.json). Aggregate:

    · which model contributed most to picks that WON
    · which model contributed most to picks that LOST
    · does high-weight-share correlate with outcome?

Emits ranked lists per model:
    · win_share_pct     · % of the model's weighted contribution across wins
    · loss_share_pct    · same across losses
    · edge              · win_share - loss_share (positive = predictive)
    · n_wins / n_losses
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


MIN_POSITIONS_FOR_ROLLUP = 10


@dataclass
class ModelStat:
    model_id: str
    label: str
    n_wins: int
    n_losses: int
    win_avg_share_pct: float | None
    loss_avg_share_pct: float | None
    edge_pp: float | None      # win_avg - loss_avg · positive = predictive


def _outcomes_for_month(root: Path, market: str, month: str) -> list[dict]:
    """Return closed/open positions with (ticker, entry_date, ret_pct)."""
    reports = root / ("usa/reports" if market == "usa" else "reports")
    positions_file = reports / "position_store" / market / "positions.json"
    if not positions_file.exists(): return []
    rows = []
    try:
        d = json.loads(positions_file.read_text(encoding="utf-8"))
        for t, p in (d.get("positions") or {}).items():
            fs = p.get("first_seen_date") or ""
            if not fs.startswith(month): continue
            entry = p.get("first_seen_price") or 0
            last = p.get("last_seen_price") or entry
            if not entry: continue
            rows.append({
                "ticker": t.replace(".NS", "").replace(".BO", ""),
                "raw_ticker": t,
                "entry_date": fs,
                "ret_pct": ((last - entry) / entry) * 100.0,
            })
    except Exception:
        return []
    return rows


def _load_rec_snapshot(root: Path, market: str, asof: str) -> list[dict]:
    reports = root / ("usa/reports" if market == "usa" else "reports")
    p = reports / "recommendations_history" / market / f"{asof}.json"
    if not p.exists(): return []
    try:
        return (json.loads(p.read_text(encoding="utf-8")).get("recommendations")
                    or [])
    except Exception:
        return []


def compute(root: Path, market: str, month: str) -> dict:
    outcomes = _outcomes_for_month(root, market, month)
    if not outcomes:
        return {
            "engine":                    "aegis.research.feature_attribution.v1",
            "generated_utc":             datetime.now(timezone.utc).isoformat(),
            "market":                    market, "month": month,
            "n_positions":               0,
            "insufficient_data":         True,
            "min_positions_required":    MIN_POSITIONS_FOR_ROLLUP,
            "models":                    [],
        }
    # Cache per-day rec snapshots
    snap_cache: dict[str, list[dict]] = {}
    for o in outcomes:
        d = o["entry_date"]
        if d not in snap_cache:
            snap_cache[d] = _load_rec_snapshot(root, market, d)

    # Aggregate per-model contribution shares across wins vs losses
    model_stats: dict[str, dict] = {}
    n_wins = n_losses = 0
    for o in outcomes:
        snap = snap_cache.get(o["entry_date"]) or []
        rec = next((r for r in snap
                        if (r.get("ticker") or "").upper() == o["raw_ticker"].upper()
                        or (r.get("ticker") or "").upper() == o["ticker"].upper()), None)
        if not rec: continue
        per_model = (rec.get("attribution") or {}).get("per_model") or []
        is_win = o["ret_pct"] > 0
        (n_wins if is_win else n_losses)
        if is_win: n_wins += 1
        else:      n_losses += 1
        for m in per_model:
            mid = m.get("model_id") or "?"
            model_stats.setdefault(mid, {
                "model_id": mid, "label": m.get("label") or mid,
                "wins": [], "losses": [],
            })
            share = m.get("share_pct")
            if share is None: continue
            (model_stats[mid]["wins" if is_win else "losses"]).append(share)

    stats: list[ModelStat] = []
    for mid, d in model_stats.items():
        w = d["wins"]; l = d["losses"]
        win_avg = round(sum(w) / len(w), 2) if w else None
        loss_avg = round(sum(l) / len(l), 2) if l else None
        edge = round(win_avg - loss_avg, 2) if (win_avg is not None and loss_avg is not None) else None
        stats.append(ModelStat(
            model_id=mid, label=d["label"],
            n_wins=len(w), n_losses=len(l),
            win_avg_share_pct=win_avg, loss_avg_share_pct=loss_avg,
            edge_pp=edge,
        ))
    stats.sort(key=lambda s: -(s.edge_pp or 0))

    return {
        "engine":                 "aegis.research.feature_attribution.v1",
        "generated_utc":          datetime.now(timezone.utc).isoformat(),
        "market":                 market, "month": month,
        "n_positions":            len(outcomes),
        "n_wins":                 n_wins,
        "n_losses":               n_losses,
        "insufficient_data":      len(outcomes) < MIN_POSITIONS_FOR_ROLLUP,
        "min_positions_required": MIN_POSITIONS_FOR_ROLLUP,
        "models":                 [asdict(s) for s in stats],
    }


def render_md(rep: dict) -> str:
    lines = [f"# Feature Attribution · {rep['market'].upper()} · {rep['month']}",
                "",
                f"Positions: **{rep['n_positions']}** · Wins: **{rep.get('n_wins', 0)}** · "
                f"Losses: **{rep.get('n_losses', 0)}**",
                ""]
    if rep["insufficient_data"]:
        lines.append(f"> ⚠️ INSUFFICIENT DATA · n={rep['n_positions']} "
                          f"< min {rep['min_positions_required']} · directional only.\n")
    lines += ["| Model | Label | n Wins | n Losses | Win Share % | Loss Share % | Edge (pp) |",
                 "|---|---|---|---|---|---|---|"]
    for m in rep["models"][:20]:
        edge = f"{m['edge_pp']:+.2f}" if m["edge_pp"] is not None else "—"
        w = f"{m['win_avg_share_pct']}%" if m["win_avg_share_pct"] is not None else "—"
        l = f"{m['loss_avg_share_pct']}%" if m["loss_avg_share_pct"] is not None else "—"
        lines.append(f"| {m['model_id']} | {m['label']} | {m['n_wins']} | {m['n_losses']} | "
                          f"{w} | {l} | {edge} |")
    return "\n".join(lines) + "\n"
