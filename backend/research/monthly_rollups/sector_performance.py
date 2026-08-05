"""Sprint E · Sector Performance rollup.

For every closed position in the month, group by sector · compute
sector-level win rate + median return + n · flag sectors where
you're consistently WINNING or LOSING.

Feeds into rebalance decisions: if Healthcare consistently loses at
your R2 confidence bucket, either drop Healthcare picks or recalibrate
Healthcare-specific confidence.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


MIN_POSITIONS_PER_SECTOR = 5


@dataclass
class SectorRow:
    sector: str
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
                "ticker": t.replace(".NS", "").replace(".BO", ""),
                "raw_ticker": t,
                "ret_pct": ((last - entry) / entry) * 100.0,
            })
    except Exception:
        pass
    return rows


def _sector_map(root: Path, market: str) -> dict:
    """Build ticker → sector lookup from recommendations archive."""
    reports = root / ("usa/reports" if market == "usa" else "reports")
    hist_dir = reports / "recommendations_history" / market
    if not hist_dir.exists(): return {}
    mapping = {}
    for p in sorted(hist_dir.glob("*.json"))[-30:]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            for r in d.get("recommendations") or []:
                t = (r.get("ticker") or "").replace(".NS", "").replace(".BO", "")
                s = r.get("sector") or ""
                if t and s: mapping[t] = s
        except Exception:
            continue
    return mapping


def compute(root: Path, market: str, month: str) -> dict:
    positions = _load_positions(root, market, month)
    sector_map = _sector_map(root, market)

    by_sector: dict[str, list[float]] = {}
    for p in positions:
        s = sector_map.get(p["ticker"], "Unknown")
        by_sector.setdefault(s, []).append(p["ret_pct"])

    def _median(xs):
        if not xs: return None
        s = sorted(xs); return s[len(s) // 2]

    rows: list[SectorRow] = []
    for sector, rets in by_sector.items():
        wins = sum(1 for r in rets if r > 0)
        rows.append(SectorRow(
            sector=sector, n_positions=len(rets), n_wins=wins,
            win_rate_pct=round(wins / len(rets) * 100.0, 1) if rets else None,
            median_return_pct=round(_median(rets), 2),
            total_return_pct=round(sum(rets), 2),
            insufficient_data=len(rets) < MIN_POSITIONS_PER_SECTOR,
        ))
    rows.sort(key=lambda r: -(r.median_return_pct or 0))

    return {
        "engine":                 "aegis.research.sector_performance.v1",
        "generated_utc":          datetime.now(timezone.utc).isoformat(),
        "market":                 market, "month": month,
        "n_positions":            len(positions),
        "n_sectors":              len(rows),
        "insufficient_data":      len(positions) < MIN_POSITIONS_PER_SECTOR,
        "min_positions_per_sector": MIN_POSITIONS_PER_SECTOR,
        "sectors":                [asdict(r) for r in rows],
    }


def render_md(rep: dict) -> str:
    lines = [f"# Sector Performance · {rep['market'].upper()} · {rep['month']}",
                "",
                f"Positions: **{rep['n_positions']}** · Sectors: **{rep['n_sectors']}**",
                ""]
    if rep["insufficient_data"]:
        lines.append(f"> ⚠️ INSUFFICIENT DATA (n={rep['n_positions']})\n")
    lines += ["| Sector | n | Wins | Win % | Median % | Total % | Flag |",
                 "|---|---|---|---|---|---|---|"]
    for s in rep["sectors"]:
        flag = "⚠️ small" if s["insufficient_data"] else ""
        lines.append(f"| {s['sector']} | {s['n_positions']} | {s['n_wins']} | "
                          f"{s['win_rate_pct']}% | {s['median_return_pct']}% | "
                          f"{s['total_return_pct']}% | {flag} |")
    return "\n".join(lines) + "\n"
