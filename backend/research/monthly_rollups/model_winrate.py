"""Sprint E · Per-Model Win Rate rollup.

Complements feature_attribution.py (which measures per-model CONTRIBUTION
share). This one measures per-model WIN RATE: for every closed position,
which models had this ticker in their top-3 picks? Did those tickers win?

Same input data · different lens · together they give a complete picture:
    · Feature Attribution → "how much did each model drive this pick"
    · Model Win Rate      → "how often was each model correct"

A model can have high contribution (loud voice) but low win rate (loud
but wrong). Both metrics are needed to decide re-weighting.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


MIN_PICKS_PER_MODEL = 5


@dataclass
class ModelWinRow:
    model_id: str
    label: str
    n_picks: int
    n_wins: int
    n_losses: int
    win_rate_pct: float | None
    median_return_pct: float | None
    insufficient_data: bool


def _load_outcomes(root: Path, market: str, month: str) -> list[dict]:
    reports = root / ("usa/reports" if market == "usa" else "reports")
    p = reports / "position_store" / market / "positions.json"
    if not p.exists(): return []
    out = []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        for t, pos in (d.get("positions") or {}).items():
            fs = pos.get("first_seen_date") or ""
            if not fs.startswith(month): continue
            entry = pos.get("first_seen_price") or 0
            last = pos.get("last_seen_price") or entry
            if not entry: continue
            out.append({
                "ticker":   t.replace(".NS", "").replace(".BO", ""),
                "raw_ticker": t,
                "entry_date": fs,
                "ret_pct":  ((last - entry) / entry) * 100.0,
            })
    except Exception:
        pass
    return out


def _rec_snapshot(root: Path, market: str, asof: str) -> list[dict]:
    reports = root / ("usa/reports" if market == "usa" else "reports")
    p = reports / "recommendations_history" / market / f"{asof}.json"
    if not p.exists(): return []
    try:
        return (json.loads(p.read_text(encoding="utf-8")).get("recommendations")
                    or [])
    except Exception:
        return []


def compute(root: Path, market: str, month: str) -> dict:
    outcomes = _load_outcomes(root, market, month)
    snap_cache: dict[str, list[dict]] = {}
    model_stats: dict[str, dict] = {}

    TOP_N_SHARE = 15.0    # a model "picked" this ticker if its share was ≥15%

    for o in outcomes:
        if o["entry_date"] not in snap_cache:
            snap_cache[o["entry_date"]] = _rec_snapshot(root, market, o["entry_date"])
        snap = snap_cache[o["entry_date"]]
        rec = next((r for r in snap
                        if (r.get("ticker") or "").upper() == o["raw_ticker"].upper()
                        or (r.get("ticker") or "").upper() == o["ticker"].upper()), None)
        if not rec: continue
        per_model = (rec.get("attribution") or {}).get("per_model") or []
        for m in per_model:
            share = m.get("share_pct")
            if not isinstance(share, (int, float)) or share < TOP_N_SHARE:
                continue
            mid = m.get("model_id") or "?"
            model_stats.setdefault(mid, {
                "model_id": mid, "label": m.get("label") or mid,
                "returns": [],
            })
            model_stats[mid]["returns"].append(o["ret_pct"])

    def _median(xs):
        if not xs: return None
        s = sorted(xs); return s[len(s) // 2]

    rows: list[ModelWinRow] = []
    for mid, d in model_stats.items():
        rets = d["returns"]
        wins = sum(1 for r in rets if r > 0)
        rows.append(ModelWinRow(
            model_id=mid, label=d["label"],
            n_picks=len(rets), n_wins=wins, n_losses=len(rets) - wins,
            win_rate_pct=round(wins / len(rets) * 100.0, 1) if rets else None,
            median_return_pct=round(_median(rets), 2) if rets else None,
            insufficient_data=len(rets) < MIN_PICKS_PER_MODEL,
        ))
    rows.sort(key=lambda r: -(r.win_rate_pct or 0))

    return {
        "engine":                "aegis.research.model_winrate.v1",
        "generated_utc":         datetime.now(timezone.utc).isoformat(),
        "market":                market, "month": month,
        "min_picks_per_model":   MIN_PICKS_PER_MODEL,
        "top_n_share_threshold": TOP_N_SHARE,
        "n_positions":           len(outcomes),
        "n_models":              len(rows),
        "models":                [asdict(r) for r in rows],
    }


def render_md(rep: dict) -> str:
    lines = [f"# Per-Model Win Rate · {rep['market'].upper()} · {rep['month']}",
                "",
                f"Positions: **{rep['n_positions']}** · "
                f"Models seen (share≥{rep['top_n_share_threshold']}%): "
                f"**{rep['n_models']}**",
                "",
                "| Model | n Picks | Wins | Losses | Win % | Median % | Flag |",
                "|---|---|---|---|---|---|---|"]
    for m in rep["models"]:
        flag = "⚠️ small" if m["insufficient_data"] else ""
        lines.append(f"| {m['model_id']} | {m['n_picks']} | {m['n_wins']} | "
                          f"{m['n_losses']} | {m['win_rate_pct']}% | "
                          f"{m['median_return_pct']}% | {flag} |")
    return "\n".join(lines) + "\n"
