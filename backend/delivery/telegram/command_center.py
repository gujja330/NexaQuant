"""Command Center renderer · single crisp Telegram message per market.

Consumes the enriched `reports/recommendations.json` (or USA equivalent)
produced by cycles 3-4:
  - ceo_summary          → top of message (30-second glance)
  - investor_action      → Entry / If-Holding decisions per rec
  - rotation_intelligence → ROTATE X → Y with expected alpha
  - evolution            → what changed since previous snapshot
  - position_plan        → entry zone, stop, targets, allocation, horizon
  - why                  → top reasons + top risks

Design principles:
  · ONE message per market (not two chunks)
  · ~1800 char budget · full detail in dashboard/HTML
  · No HTML tags — plain text with Markdown-safe formatting
  · ASCII-safe arrows (->) · emojis for section visual hierarchy
  · CEO one-liner FIRST (the operator's "what should I do today")
  · Rotation calls next (highest institutional-value information)
  · Actionable entries with target/stop
  · Actionable exits with reason class (not just "rebalance")
  · Feedback loop: yesterday's evolution deltas if present

Article 101.2 compliant · pure rendering · zero new analytics.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.delivery.telegram.command_center.v1.20260729"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.delivery.telegram.command_center.v1"

# Character budget · Telegram hard cap is 4096 · reserve headroom.
BUDGET_CHARS = 3500
SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━"

# Currency symbols per market — plain-ASCII fallbacks used because
# Telegram Markdown mode + Windows CI cp1252 both stumble on some Unicode.
CURRENCY = {"india": "Rs", "usa": "$"}


def _fmt_price(v, market: str) -> str:
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "-"
    sym = CURRENCY.get(market, "")
    if f >= 1000:
        return f"{sym}{f:,.0f}"
    if f >= 100:
        return f"{sym}{f:.0f}"
    return f"{sym}{f:.2f}"


def _fmt_pct(v, ndigits: int = 1) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):+.{ndigits}f}%"
    except (TypeError, ValueError):
        return "-"


def _short_ticker(t: str) -> str:
    """Strip .NS / .BO suffixes to save chars on India tickers."""
    if not t:
        return "?"
    return str(t).split(".", 1)[0]


def _header(market: str, asof: str) -> list[str]:
    market_name = "India NSE 200" if market == "india" else "USA Dow 30"
    weekday = ""
    try:
        weekday = datetime.fromisoformat(asof).strftime("%a")
    except Exception:
        pass
    return [
        f"AEGIS · {market_name} · {asof}" + (f" ({weekday})" if weekday else ""),
        SEPARATOR,
    ]


def _ceo_call(cs: Mapping) -> list[str]:
    """Top block — the 30-second recommendation."""
    lines = ["*CEO CALL TODAY*"]
    action = cs.get("recommended_action") or "no signal"
    lines.append(f"  {action}")
    regime = cs.get("market_regime") or "unknown"
    actionable = cs.get("actionable_count") or 0
    rotations = cs.get("rotations_count") or 0
    lines.append(f"  Regime {regime} · Actionable {actionable} · Rotations {rotations}")
    # Cycle 5E: discipline warnings surface right below the CEO call.
    warnings = cs.get("discipline_warnings") or []
    for w in warnings[:3]:
        lines.append(f"  ⚠ {w}")
    return lines


def _rotation_calls(recs: Sequence[Mapping], market: str, max_rows: int = 3) -> list[str]:
    """Every rec with should_rotate=True · ranked by expected alpha."""
    rots = []
    for r in recs:
        ri = r.get("rotation_intelligence") or {}
        if ri.get("should_rotate"):
            rots.append({
                "from":  _short_ticker(r.get("ticker") or ""),
                "to":    _short_ticker(ri.get("replacement_ticker") or ""),
                "alpha": ri.get("expected_alpha_delta_pct") or 0,
                "edge":  ri.get("edge") or 0,
            })
    if not rots:
        return []
    rots.sort(key=lambda x: -abs(x["alpha"]))
    lines = ["", f"*ROTATIONS ({len(rots)})*"]
    for r in rots[:max_rows]:
        lines.append(f"  {r['from']} -> {r['to']}  a+{r['alpha']:.1f}%")
    if len(rots) > max_rows:
        lines.append(f"  ...+{len(rots) - max_rows} more")
    return lines


def _actionable_entries(recs: Sequence[Mapping], market: str,
                          max_rows: int = 4) -> list[str]:
    """Recs with is_actionable_entry — ranked by ensemble_score."""
    picks = [r for r in recs
              if (r.get("investor_action") or {}).get("is_actionable_entry")]
    picks.sort(key=lambda r: -(r.get("ensemble_score") or 0))
    if not picks:
        return []
    lines = ["", f"*NEW BUYS ({len(picks)})*"]
    for r in picks[:max_rows]:
        t = _short_ticker(r.get("ticker") or "?")
        ia = r.get("investor_action") or {}
        pp = r.get("position_plan") or {}
        ez = pp.get("entry_zone") or {}
        alloc = pp.get("suggested_allocation_pct") or 0
        horizon = pp.get("time_horizon_bucket") or "?"
        hdays = pp.get("time_horizon_days") or 0
        entry = ia.get("entry") or "?"
        if ez.get("stop_loss") is not None and ez.get("target_1") is not None:
            lines.append(
                f"  {t}  {entry} · alloc {alloc}% · {horizon} {hdays}d"
            )
            lines.append(
                f"     buy {_fmt_price(ez.get('ideal_buy_low'), market)}"
                f"-{_fmt_price(ez.get('ideal_buy_high'), market)}"
                f" · stop {_fmt_price(ez.get('stop_loss'), market)}"
                f" · T1 {_fmt_price(ez.get('target_1'), market)}"
            )
        else:
            cp = _fmt_price(ez.get("current_price"), market)
            lines.append(f"  {t}  {entry} · alloc {alloc}% · price {cp}")
    if len(picks) > max_rows:
        lines.append(f"  ...+{len(picks) - max_rows} more")
    return lines


def _actionable_exits(recs: Sequence[Mapping], market: str,
                        max_rows: int = 4) -> list[str]:
    exits = [r for r in recs
              if (r.get("investor_action") or {}).get("if_holding") in ("REDUCE", "EXIT")]
    exits.sort(key=lambda r: r.get("ensemble_score") or 0)   # worst first
    if not exits:
        return []
    lines = ["", f"*EXITS IF HOLDING ({len(exits)})*"]
    for r in exits[:max_rows]:
        t = _short_ticker(r.get("ticker") or "?")
        ia = r.get("investor_action") or {}
        action = ia.get("if_holding") or "?"
        # Discipline check: if the exit reason class is RANK_ONLY / churn
        # AND ensemble_score is still positive, flag it.
        score = r.get("ensemble_score") or 0
        warn = ""
        if action in ("REDUCE", "EXIT") and score > 0:
            warn = "  ⚠ still positive-score — confirm intended"
        risks = ((r.get("why") or {}).get("top_risks") or [None])[0]
        risks_short = (str(risks)[:60] + "...") if risks and len(str(risks)) > 60 else (risks or "")
        lines.append(f"  {t}  {action}{warn}")
        if risks_short:
            lines.append(f"     risk: {risks_short}")
    if len(exits) > max_rows:
        lines.append(f"  ...+{len(exits) - max_rows} more")
    return lines


def _evolution_summary(recs: Sequence[Mapping], max_rows: int = 3) -> list[str]:
    """Which recs materially changed since previous snapshot."""
    changes = []
    for r in recs:
        ev = r.get("evolution") or {}
        if ev.get("action_change") or ev.get("lifecycle_change") or (
            ev.get("rank_change") not in (None, 0)):
            changes.append({
                "ticker": _short_ticker(r.get("ticker") or "?"),
                "narrative": ev.get("narrative") or "",
                "is_new": ev.get("is_new"),
            })
    fresh = [c for c in changes if c["is_new"]]
    material = [c for c in changes if not c["is_new"]]
    if not (fresh or material):
        return []
    lines = ["", "*WHAT CHANGED SINCE LAST RUN*"]
    if material:
        for c in material[:max_rows]:
            n = c["narrative"][:80]
            lines.append(f"  {c['ticker']}: {n}")
    if fresh:
        fresh_ts = ", ".join(c["ticker"] for c in fresh[:5])
        more = f" +{len(fresh) - 5}" if len(fresh) > 5 else ""
        lines.append(f"  NEW: {fresh_ts}{more}")
    return lines


def _risk_pulse(cs: Mapping, recs: Sequence[Mapping], market: str) -> list[str]:
    """Portfolio concentration + top/bottom risk-adjacent picks."""
    top_opp = cs.get("top_opportunity") or {}
    top_risk = cs.get("top_risk") or {}
    lines = []
    if top_opp.get("ticker") or top_risk.get("ticker"):
        lines.append("")
        lines.append("*RISK PULSE*")
    if top_opp.get("ticker"):
        lines.append(
            f"  Top pick: {_short_ticker(top_opp['ticker'])} "
            f"({top_opp.get('action', '?')}) · alloc {top_opp.get('allocation_pct', 0)}%"
        )
    if top_risk.get("ticker"):
        lines.append(
            f"  Top risk: {_short_ticker(top_risk['ticker'])} "
            f"({top_risk.get('if_holding', '?')})"
        )
    return lines


def _integrity_footer(payload: Mapping) -> list[str]:
    run_utc = str(payload.get("run_utc") or "")[:16].replace("T", " ")
    engine = payload.get("investor_actionable_engine") or "aegis"
    return [
        "",
        SEPARATOR,
        f"Run {run_utc} · {engine}",
        "Advisory only · PAPER · Not investment advice",
    ]


def render_command_center_message(payload: Mapping, market: str,
                                       budget: int = BUDGET_CHARS) -> str:
    """Render single crisp Telegram message from enriched recommendations.json.

    Returns a single string ≤ budget chars. Sections are added in priority
    order (CEO call → rotations → new buys → exits → evolution → risk pulse
    → footer). If any section would push us over budget, later sections are
    truncated or dropped rather than mid-section.
    """
    if not payload:
        return "AEGIS: no data available"
    cs = payload.get("ceo_summary") or {}
    recs = payload.get("recommendations") or []
    asof = str(payload.get("asof") or "?")

    sections = [
        ("header",       _header(market, asof)),
        ("ceo_call",     _ceo_call(cs)),
        ("rotations",    _rotation_calls(recs, market)),
        ("new_buys",     _actionable_entries(recs, market)),
        ("exits",        _actionable_exits(recs, market)),
        ("evolution",    _evolution_summary(recs)),
        ("risk_pulse",   _risk_pulse(cs, recs, market)),
        ("footer",       _integrity_footer(payload)),
    ]

    out: list[str] = []
    used = 0
    for name, lines in sections:
        block = "\n".join(lines) + ("\n" if lines else "")
        if used + len(block) > budget:
            # Never truncate footer — it carries integrity info
            if name == "footer":
                out.extend(sections[-1][1])
                break
            # Otherwise drop the whole section rather than half-render
            continue
        out.extend(lines)
        used += len(block)

    return "\n".join(out).strip()


def load_and_render(reports_dir: Path, market: str,
                       budget: int = BUDGET_CHARS) -> tuple[str, dict]:
    """Load recommendations.json and render. Returns (message, meta)."""
    p = reports_dir / "recommendations.json"
    if not p.exists():
        return f"AEGIS {market}: recommendations.json missing", {"n_recs": 0}
    payload = json.loads(p.read_text(encoding="utf-8"))
    msg = render_command_center_message(payload, market, budget=budget)
    meta = {
        "n_recs":          len(payload.get("recommendations") or []),
        "asof":            payload.get("asof"),
        "budget_chars":    budget,
        "message_chars":   len(msg),
        "n_rotations":     (payload.get("ceo_summary") or {}).get("rotations_count", 0),
        "n_actionable":    (payload.get("ceo_summary") or {}).get("actionable_count", 0),
    }
    return msg, meta
