"""Sprint E · Regime Performance rollup.

For every closed position, tag with the macro regime that was ACTIVE at
the entry date · aggregate win rate + median return per regime.

Answers: does our ensemble work in bull regimes only? Bear? Neutral?
Feeds the macro_regime_stability policy layer.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


MIN_POSITIONS_PER_REGIME = 5


@dataclass
class RegimeRow:
    regime: str
    n_positions: int
    n_wins: int
    win_rate_pct: float | None
    median_return_pct: float | None
    total_return_pct: float | None
    insufficient_data: bool


def _load_positions(root: Path, market: str, month: str) -> list[dict]:
    reports = root / ("usa/reports" if market == "usa" else "reports")
    p = reports / "position_store" / market / "positions.json"
    if not p.exists(): return []
    rows = []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        for t, pos in (d.get("positions") or {}).items():
            fs = pos.get("first_seen_date") or ""
            if not fs.startswith(month): continue
            entry = pos.get("first_seen_price") or 0
            last = pos.get("last_seen_price") or entry
            if not entry: continue
            rows.append({
                "ticker": t, "entry_date": fs,
                "ret_pct": ((last - entry) / entry) * 100.0,
            })
    except Exception:
        pass
    return rows


def _regime_at(root: Path, market: str, asof: str) -> str:
    """Look up macro regime that was active at asof · fallback to 'unknown'."""
    p = root / "reports" / "research" / "regime_history.jsonl"
    if not p.exists(): return "unknown"
    best = None
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        if d.get("market") != market: continue
        if (d.get("asof") or "") <= asof:
            if best is None or (d.get("asof") or "") > (best.get("asof") or ""):
                best = d
    return (best.get("regime") if best else "unknown") or "unknown"


def compute(root: Path, market: str, month: str) -> dict:
    positions = _load_positions(root, market, month)
    by_regime: dict[str, list[float]] = {}
    for p in positions:
        regime = _regime_at(root, market, p["entry_date"])
        by_regime.setdefault(regime, []).append(p["ret_pct"])

    def _median(xs):
        if not xs: return None
        s = sorted(xs); return s[len(s) // 2]

    rows: list[RegimeRow] = []
    for regime, rets in by_regime.items():
        wins = sum(1 for r in rets if r > 0)
        rows.append(RegimeRow(
            regime=regime, n_positions=len(rets), n_wins=wins,
            win_rate_pct=round(wins / len(rets) * 100.0, 1) if rets else None,
            median_return_pct=round(_median(rets), 2),
            total_return_pct=round(sum(rets), 2),
            insufficient_data=len(rets) < MIN_POSITIONS_PER_REGIME,
        ))
    rows.sort(key=lambda r: -(r.median_return_pct or 0))

    return {
        "engine":                  "aegis.research.regime_performance.v1",
        "generated_utc":           datetime.now(timezone.utc).isoformat(),
        "market":                  market, "month": month,
        "n_positions":             len(positions),
        "n_regimes":               len(rows),
        "insufficient_data":       len(positions) < MIN_POSITIONS_PER_REGIME,
        "min_positions_per_regime": MIN_POSITIONS_PER_REGIME,
        "regimes":                 [asdict(r) for r in rows],
    }


def render_md(rep: dict) -> str:
    lines = [f"# Regime Performance · {rep['market'].upper()} · {rep['month']}",
                "",
                f"Positions: **{rep['n_positions']}** · Regimes seen: **{rep['n_regimes']}**",
                ""]
    if rep["insufficient_data"]:
        lines.append(f"> ⚠️ INSUFFICIENT DATA (n={rep['n_positions']})\n")
    lines += ["| Regime | n | Wins | Win % | Median % | Total % | Flag |",
                 "|---|---|---|---|---|---|---|"]
    for r in rep["regimes"]:
        flag = "⚠️ small" if r["insufficient_data"] else ""
        lines.append(f"| {r['regime']} | {r['n_positions']} | {r['n_wins']} | "
                          f"{r['win_rate_pct']}% | {r['median_return_pct']}% | "
                          f"{r['total_return_pct']}% | {flag} |")
    return "\n".join(lines) + "\n"
