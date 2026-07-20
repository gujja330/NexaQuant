"""AEGIS USA · Telegram renderer.

Builds the 5-message set for USA daily delivery. USD ($) throughout.
Same visual structure as India's UX030 renderer, adapted to USA data
+ S&P 500 benchmark + Dow/NASDAQ/NYSE exchanges.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


_USA = Path(__file__).resolve().parents[2]
REPORTS = _USA / "reports"


def _load(name: str) -> dict:
    p = REPORTS / name
    if not p.exists(): return {}
    try:    return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _esc(s) -> str:
    """Escape Telegram-Markdown unsafe underscores in any string value we
    render directly (e.g. `insufficient_evidence` from JSON payloads)."""
    if s is None: return "—"
    return str(s).replace("_", r"\_")


def _usd(v) -> str:
    if v is None: return "—"
    try:    return f"${float(v):,.2f}"
    except Exception: return "—"


def _pct(v, sign=True, places=2) -> str:
    if v is None: return "—"
    try:    x = float(v) * 100
    except Exception: return "—"
    return f"{x:{'+' if sign else ''}.{places}f}%"


def _now_ny() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M EDT")


def render_morning_brief() -> str:
    recs = _load("recommendations.json")
    n = len(recs.get("recommendations") or [])
    ac = recs.get("action_counts") or {}
    n_buys = (ac.get("Strong-Buy") or 0) + (ac.get("Buy") or 0) + (ac.get("Accumulate") or 0)
    return "\n".join([
        f"🌅 *AEGIS USA · Morning Brief*",
        f"_{_now_ny()}_",
        f"",
        f"📊 Market: USA · USD ($) · S&P 500 benchmark",
        f"🎯 Recs today: {n} · Buys: {n_buys}",
    ])


def render_top_opportunities(n: int = 5) -> str:
    recs   = _load("recommendations.json")
    prices = _load("price_context.json").get("tickers") or {}
    all_recs = recs.get("recommendations") or []
    buys = [r for r in all_recs if r.get("recommendation") in ("Strong-Buy", "Buy", "Accumulate")]
    buys.sort(key=lambda r: r.get("composite_decision_score") or 0, reverse=True)
    picks = buys[:n]

    if not picks:
        return "🟢 *TOP OPPORTUNITIES · USA*\n\nNo Buy signals today."

    lines = [
        f"🟢 *TOP OPPORTUNITIES · USA*  🇺🇸",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for r in picks:
        t = r.get("ticker") or "?"
        sector = r.get("sector") or "—"
        rank = r.get("overall_rank")
        action = r.get("recommendation") or "Buy"
        score = r.get("composite_decision_score")
        conf = (r.get("confidence") or 0) * 100
        ee = r.get("entry_exit") or {}
        cmp_val = ee.get("latest_close")
        target = ee.get("target_1"); stop = ee.get("stop_loss")
        hold = ee.get("expected_holding_days")
        stop_pct = ee.get("stop_loss_pct")
        pc = prices.get(t) or {}
        if pc.get("available"):
            cmp_val = pc.get("cmp") or cmp_val

        upside_pct = ((target - cmp_val) / cmp_val * 100) if (cmp_val and target) else None
        gain_per_sh = (target - cmp_val) if (cmp_val and target) else None
        up_icon = "🟢" if (upside_pct or 0) > 0 else "🔴"

        lines.append(f"`{t}` · {sector} · #{int(rank) if rank else '?'}")
        row = f"    "
        if cmp_val is not None: row += _usd(cmp_val)
        if target is not None:  row += f" → {_usd(target)}"
        if upside_pct is not None:
            row += f"  {up_icon} +{upside_pct:.1f}%"
            if gain_per_sh is not None:
                row += f" · +${gain_per_sh:,.0f}/sh"
        lines.append(row)
        bits = [action.upper() if action else "BUY"]
        if stop is not None:
            s = f"Stop {_usd(stop)}"
            if stop_pct is not None: s += f" ({stop_pct:+.1f}%)"
            bits.append(s)
        if hold: bits.append(f"Hold {int(hold)}d")
        if score is not None: bits.append(f"Score {score:.0f}/100")
        if conf: bits.append(f"Conf {conf:.0f}%")
        lines.append("    " + " · ".join(bits))
    return "\n".join(lines)


def render_portfolio_health() -> str:
    risk = _load("risk_latest.json").get("portfolio_risk") or {}
    intel = _load("intelligence_summary.json")
    return "\n".join([
        f"❤️ *PORTFOLIO HEALTH · USA*",
        f"",
        f"Positions: {risk.get('n_positions', 0)} · Deployed: {(risk.get('total_weight', 0) * 100):.1f}%",
        f"Cash: {(risk.get('cash_pct', 0) * 100):.1f}% · Vol: {(risk.get('portfolio_vol_annual', 0) * 100):.1f}% ann",
        f"Verdict: {_esc(risk.get('verdict', '—'))}",
        f"Avg Intelligence: {(intel.get('avg_intelligence') or 0):.1f}/100",
    ])


def render_benchmark() -> str:
    bm = _load("benchmark.json").get("portfolio") or {}
    ops = _load("ops_check.json")
    lc = _load("recommendation_lifecycle.json")
    days = lc.get("coverage", {}).get("n_days_archived", 0)
    return "\n".join([
        f"🏆 *ALPHA vs S&P 500 · USA*",
        f"",
        f"Trades benchmarked: {bm.get('n_trades_benchmarked', 0)}",
        f"Verdict: {_esc(bm.get('verdict', 'insufficient evidence'))}",
        f"",
        f"Archive Maturation: {days}/30 days · Winner Genome activates at 30",
        f"Ops verdict: {ops.get('verdict', '—')}",
    ])


def render_executive_summary() -> str:
    recs = _load("recommendations.json")
    risk = _load("risk_latest.json").get("portfolio_risk") or {}
    bm = _load("benchmark.json").get("portfolio") or {}
    ac = recs.get("action_counts") or {}
    ops = _load("ops_check.json")

    return "\n".join([
        f"📋 *EXECUTIVE SUMMARY · USA*",
        f"_{_now_ny()}_",
        f"",
        f"📈 Recommendations: {len(recs.get('recommendations') or [])}",
        f"    Strong-Buy: {ac.get('Strong-Buy', 0)} · Buy: {ac.get('Buy', 0)} · Accumulate: {ac.get('Accumulate', 0)}",
        f"    Hold: {ac.get('Hold', 0)} · Reduce: {ac.get('Reduce', 0)} · Sell: {ac.get('Sell', 0)}",
        f"",
        f"💼 Portfolio: {risk.get('n_positions', 0)} positions · "
        f"{(risk.get('total_weight', 0) * 100):.1f}% deployed",
        f"    Risk verdict: {_esc(risk.get('verdict', '—'))}",
        f"",
        f"🏆 Alpha vs S&P 500: {_esc(bm.get('verdict', 'insufficient evidence'))}",
        f"🔐 Ops: {ops.get('verdict', '—')}",
        f"",
        f"Advisory only · USD ($) · Not investment advice",
    ])


def render_all() -> list[tuple[str, str]]:
    """Returns list of (label, message) tuples for the sender."""
    return [
        ("morning_brief",      render_morning_brief()),
        ("top_opportunities",  render_top_opportunities(n=5)),
        ("portfolio_health",   render_portfolio_health()),
        ("benchmark",          render_benchmark()),
        ("executive_summary",  render_executive_summary()),
    ]
