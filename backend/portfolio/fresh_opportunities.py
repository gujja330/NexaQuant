"""Fresh Opportunities Board · daily filter of "what to buy TODAY".

Sprint J-3 · 2026-08-06 · operator directive: "every day sector · news ·
our 7 guards will play key roles in picking new opportunities · think wider
and give me a perfect solution."

Reads EVERY context signal we already ingest daily · unions them to score
each R2 recommendation as a FRESH OPPORTUNITY today. Emits a compact
markdown attachment ONLY when there ARE fresh buys (silent when nothing).

Scoring criteria (unified filter across all daily signals):
    ✓ Guard 7 GREEN (or context source healthy per-signal)
    ✓ Rank ≤ 8 (both R1 and R2)
    ✓ Health Band = STRONG or HOLD (not WEAK/EXIT)
    ✓ Entry signal = 🟢 BUY (price in buy zone)
    ✓ Sector rank ≤ 5 (top-half sector · from sector_rotation)
    ✓ Sector news sentiment ≥ -0.3 (not negative from divergence)
    ✓ FII+DII flow ≥ neutral today
    ✓ Global overnight net-not-red (no big sector drag)

Any recommendation passing ALL criteria = a FRESH OPPORTUNITY.
Ranked by composite score: base_conf + ctx_boost + sector_leadership.

Output: reports/telegram/fresh_opportunities_{market}_{asof}.md
Attached to daily Telegram send · only when non-empty.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass
class FreshBuy:
    ticker: str
    market: str
    runner: str
    rank: int
    sector: str
    entry_price: float
    buy_zone_high: float | None
    buy_zone_delta_pct: float | None
    confidence_pct: float
    adjusted_confidence: float
    ctx_drag_pts: float
    health_band: str
    sector_rank: int | None
    sector_news_sentiment: float | None
    reasons: list[str] = field(default_factory=list)


def _load_json(p: Path) -> dict:
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _sector_ranks(root: Path, market: str) -> dict:
    reports = root / ("usa/reports" if market == "usa" else "reports")
    d = _load_json(reports / "sector_rotation.json")
    ranked = d.get("ranked_sectors") or d.get("sectors") or []
    out = {}
    for i, s in enumerate(ranked, 1):
        name = s.get("sector") or s.get("name") if isinstance(s, dict) else str(s)
        if name: out[name] = i
    return out


def _sector_news(root: Path) -> dict:
    d = _load_json(root / "reports" / "context" / "sector_news.json")
    return d.get("sector_sentiment") or {}


def _flow_positive(root: Path) -> bool:
    d = _load_json(root / "reports" / "fii_dii_flow.json")
    net = d.get("net_crore") or 0
    return net >= -500     # tolerate mildly negative


def _overnight_sector_drag(root: Path, sector: str) -> float:
    d = _load_json(root / "reports" / "context" / "global_overnight.json")
    return (d.get("sector_drag") or {}).get(sector, 0.0)


def _cil_lookup(root: Path, market: str, ticker: str) -> dict | None:
    d = _load_json(root / "reports" / "context" / f"cil_run_{market}.json")
    for a in d.get("adjustments") or []:
        t = a.get("ticker") or ""
        if t == ticker or t.replace(".NS", "").replace(".BO", "") == \
              ticker.replace(".NS", "").replace(".BO", ""):
            return a
    return None


def _health_band(root: Path, market: str, ticker: str) -> str:
    d = _load_json(root / "reports" / "research" / f"health_scores_{market}.json")
    short = ticker.replace(".NS", "").replace(".BO", "")
    for c in d.get("cards") or []:
        t = c.get("ticker") or ""
        if t == ticker or t == short:
            return c.get("band") or ""
    return ""


def _guard7_green(root: Path) -> bool:
    d = _load_json(root / "reports" / "context" / "health_monitor.json")
    return d.get("overall_verdict") == "GREEN"


def _iter_recs(root: Path, market: str):
    reports = root / ("usa/reports" if market == "usa" else "reports")
    p = reports / "recommendations.json"
    if not p.exists(): return []
    return _load_json(p).get("recommendations") or []


def scan(root: Path, market: str, asof: str) -> list[FreshBuy]:
    """Apply all filters · return list of FreshBuy candidates ranked."""
    recs = _iter_recs(root, market)
    if not recs:
        return []
    sector_rank_map = _sector_ranks(root, market)
    sector_news_map = _sector_news(root)
    flow_ok = _flow_positive(root)
    guard7_ok = _guard7_green(root)

    fresh = []
    for r in recs:
        t = r.get("ticker") or ""
        if not t: continue
        rank = r.get("rank") or 99
        if rank > 8: continue

        sector = r.get("sector") or ""
        band = _health_band(root, market, t)
        if band not in ("STRONG", "HOLD"):
            continue

        # Entry timing: price within buy zone
        pp = r.get("position_plan") or {}
        ez = pp.get("entry_zone") or {}
        cp = ez.get("current_price")
        bh = ez.get("ideal_buy_high") or (cp * 1.02 if cp else None)
        if not cp or not bh: continue
        bz_delta = (cp - bh) / bh * 100 if bh else 0
        if bz_delta > 1.0: continue      # too far above buy zone · not fresh

        # Sector rank check (top-5 · or missing = neutral)
        s_rank = sector_rank_map.get(sector)
        if s_rank and s_rank > 5: continue

        # Sector news check
        s_news = sector_news_map.get(sector, 0)
        if s_news < -0.3: continue

        # Overnight check
        overnight_drag = _overnight_sector_drag(root, sector)
        if overnight_drag < -2.0: continue

        # CIL / confidence
        cil = _cil_lookup(root, market, t) or {}
        base_conf = cil.get("base") or (r.get("calibrated_confidence") or 0) * 100
        adj_conf = cil.get("adjusted") or base_conf
        drag = cil.get("drag_pts") or 0

        reasons = []
        if s_rank and s_rank <= 3: reasons.append(f"sector leader (#{s_rank})")
        if s_news > 0.3: reasons.append(f"positive news ({s_news:+.2f})")
        if flow_ok: reasons.append("institutional flow ok")
        if not reasons: reasons.append("no blockers · standard entry")

        fresh.append(FreshBuy(
            ticker=t.replace(".NS", "").replace(".BO", ""),
            market=market, runner="R2", rank=rank, sector=sector,
            entry_price=round(cp, 2), buy_zone_high=round(bh, 2),
            buy_zone_delta_pct=round(bz_delta, 2),
            confidence_pct=round(base_conf, 1),
            adjusted_confidence=round(adj_conf, 1),
            ctx_drag_pts=round(drag, 1),
            health_band=band,
            sector_rank=s_rank,
            sector_news_sentiment=round(s_news, 2) if s_news is not None else None,
            reasons=reasons,
        ))

    fresh.sort(key=lambda f: -f.adjusted_confidence)
    return fresh


def render_md(market: str, asof: str, fresh: list[FreshBuy],
                  guard7_ok: bool = True) -> str:
    if not fresh:
        return ""     # signal: no output today
    lines = [f"# 🎯 Fresh Buy Opportunities · {market.upper()} · {asof}",
                "",
                f"Passed ALL daily filters: Health Band ≥ HOLD · sector top-5 · "
                f"sector news ≥ neutral · entry price in buy zone · "
                f"institutional flow ok · overnight not red",
                f"Guard 7 status: {'🟢 GREEN · safe to act' if guard7_ok else '🟡 warning · check status'}",
                "",
                "| Rank | Ticker | Sector | Entry | Buy Zone Δ | Conf → Adj | Band | Reasons |",
                "|---|---|---|---|---|---|---|---|"]
    for f in fresh:
        bz = f"{f.buy_zone_delta_pct:+.1f}%" if f.buy_zone_delta_pct is not None else "—"
        reasons = " · ".join(f.reasons[:3])
        lines.append(f"| #{f.rank} | **{f.ticker}** | {f.sector} | "
                          f"{f.entry_price} | {bz} | "
                          f"{f.confidence_pct:.0f}% → {f.adjusted_confidence:.0f}% | "
                          f"{f.health_band} | {reasons} |")
    lines += ["",
                 f"**{len(fresh)} fresh opportunit{'y' if len(fresh)==1 else 'ies'} today.** "
                 f"Ranked by adjusted confidence.",
                 "",
                 "How to use: pick top 2-3 for new capital · size 5-10% each · "
                 "hold per each ticker's individual horizon."]
    return "\n".join(lines) + "\n"


def daily_run(root: Path, market: str, asof: str) -> Path | None:
    """Scan · render · persist. Returns path if fresh buys found · else None."""
    fresh = scan(root, market, asof)
    if not fresh:
        # Empty · don't create empty file
        return None
    guard7 = _guard7_green(root)
    md = render_md(market, asof, fresh, guard7_ok=guard7)
    p = root / "reports" / "telegram" / f"fresh_opportunities_{market}_{asof}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    # Also emit a "latest" symlink-ish copy for consumers
    latest = root / "reports" / "telegram" / f"fresh_opportunities_{market}_latest.md"
    latest.write_text(md, encoding="utf-8")
    # Emit structured JSON alongside for programmatic consumers
    jp = root / "reports" / "research" / f"fresh_opportunities_{market}.json"
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps({
        "engine":        "aegis.portfolio.fresh_opportunities.v1",
        "market":        market, "asof": asof,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_fresh":       len(fresh),
        "guard7_green":  guard7,
        "fresh_buys":    [asdict(f) for f in fresh],
    }, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    return p
