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


# Static well-known company-name lookups per market. Used when the
# universe.json name is missing or equal to the ticker (which is the
# case for the dynamic S&P 500 + MidCap 400 universes populated by
# refresh_universe.py from Wikipedia — those come without names).
# When universe.json DOES carry names (Dow 30, NSE 200), those win.
_INDIA_COMPANY_NAMES = {
    "LUPIN": "Lupin",             "HEROMOTOCO": "Hero MotoCorp",
    "CHAMBLFERT": "Chambal Fert.", "PIDILITIND": "Pidilite",
    "SUNPHARMA": "Sun Pharma",     "ICICIBANK": "ICICI Bank",
    "TCS": "TCS",                  "HCLTECH": "HCL Tech",
    "NAUKRI": "Info Edge",         "COALINDIA": "Coal India",
    "BATAINDIA": "Bata India",     "BIOCON": "Biocon",
    "AMBER": "Amber Ent.",         "JSWENERGY": "JSW Energy",
    "PATANJALI": "Patanjali",       "TATAELXSI": "Tata Elxsi",
    "GUJGASLTD": "Gujarat Gas",    "KPITTECH": "KPIT Tech",
    "BANDHANBNK": "Bandhan Bank",  "KALYANKJIL": "Kalyan Jewel.",
    "VEDL": "Vedanta",             "ITC": "ITC",
    "GODREJIND": "Godrej Ind.",    "SONACOMS": "Sona Comstar",
    "LODHA": "Lodha",              "PNB": "Punjab Natl. Bank",
    "HINDZINC": "Hindustan Zinc",   "FORTIS": "Fortis Healthcare",
    "NTPC": "NTPC",                "IRCTC": "IRCTC",
    "TATAPOWER": "Tata Power",     "BEL": "Bharat Electronics",
    "APOLLOHOSP": "Apollo Hosp.",   "BHARTIARTL": "Bharti Airtel",
    "POWERGRID": "Power Grid",     "RELIANCE": "Reliance Ind.",
    "KOTAKBANK": "Kotak Bank",     "TATAMOTORS": "Tata Motors",
    "LTIM": "LTIMindtree",         "PEL": "Piramal Ent.",
}
_USA_COMPANY_NAMES = {
    "AAPL": "Apple",              "MSFT": "Microsoft",
    "NVDA": "NVIDIA",             "AMZN": "Amazon",
    "GOOGL": "Alphabet",          "META": "Meta Platforms",
    "TSLA": "Tesla",              "AVGO": "Broadcom",
    "JPM": "JPMorgan Chase",      "V": "Visa",
    "WMT": "Walmart",             "JNJ": "Johnson & Johnson",
    "PG": "Procter & Gamble",     "UNH": "UnitedHealth",
    "HD": "Home Depot",           "KO": "Coca-Cola",
    "MCD": "McDonald's",          "DIS": "Walt Disney",
    "CSCO": "Cisco",              "CRM": "Salesforce",
    "VZ": "Verizon",              "INTC": "Intel",
    "BA": "Boeing",               "CAT": "Caterpillar",
    "MRK": "Merck",               "NKE": "Nike",
    "IBM": "IBM",                 "GS": "Goldman Sachs",
    "AXP": "American Express",    "TRV": "Travelers",
    "MMM": "3M",                  "CVX": "Chevron",
    "AMGN": "Amgen",              "HON": "Honeywell",
    "NFLX": "Netflix",            "AMD": "AMD",
    "ADBE": "Adobe",              "TMUS": "T-Mobile",
    "CMCSA": "Comcast",           "QCOM": "Qualcomm",
    "COST": "Costco",             "PEP": "PepsiCo",
    "BLK": "BlackRock",           "SPGI": "S&P Global",
    "SBUX": "Starbucks",          "PYPL": "PayPal",
}


def _company_name(ticker: str, market: str) -> str:
    """Return best-known company short name for a ticker; empty if unknown."""
    if not ticker:
        return ""
    short = _short_ticker(ticker).upper()
    src = _INDIA_COMPANY_NAMES if market == "india" else _USA_COMPANY_NAMES
    return src.get(short, "")


def _ticker_with_name(ticker: str, market: str, width: int = 22) -> str:
    """Format `TICKER (Name)` · falls back to just ticker when name unknown."""
    short = _short_ticker(ticker)
    name = _company_name(ticker, market)
    if name:
        return f"{short} ({name})"
    return short


def _header(market: str, asof: str) -> list[str]:
    market_name = "🇮🇳 India NSE 200" if market == "india" else "🇺🇸 USA S&P 500 + MidCap 400"
    weekday = ""
    try:
        weekday = datetime.fromisoformat(asof).strftime("%a")
    except Exception:
        pass
    return [
        f"🏢 *AEGIS DAILY* · {market_name}",
        f"📅 {asof}" + (f" ({weekday})" if weekday else ""),
        SEPARATOR,
    ]


def _ceo_call(cs: Mapping) -> list[str]:
    """Top block — the 30-second recommendation."""
    lines = ["🎯 *CEO CALL TODAY*"]
    action = cs.get("recommended_action") or "no signal"
    lines.append(f"   {action}")
    regime = cs.get("market_regime") or "unknown"
    actionable = cs.get("actionable_count") or 0
    rotations = cs.get("rotations_count") or 0
    lines.append(f"   🌐 Market: {regime}   ·   ⚡ Actionable: {actionable}   ·   🔄 Rotations: {rotations}")
    # Discipline warnings surface right below the CEO call.
    warnings = cs.get("discipline_warnings") or []
    for w in warnings[:3]:
        lines.append(f"   ⚠️ {w}")
    return lines


def _rotation_calls(recs: Sequence[Mapping], market: str, max_rows: int = 3) -> list[str]:
    """Every rec with should_rotate=True · ranked by expected alpha."""
    rots = []
    for r in recs:
        ri = r.get("rotation_intelligence") or {}
        if ri.get("should_rotate"):
            rots.append({
                "from":  r.get("ticker") or "",
                "to":    ri.get("replacement_ticker") or "",
                "alpha": ri.get("expected_alpha_delta_pct") or 0,
                "edge":  ri.get("edge") or 0,
            })
    if not rots:
        return []
    rots.sort(key=lambda x: -abs(x["alpha"]))
    lines = ["", f"🔄 *ROTATION SIGNALS ({len(rots)})*",
             "   _Sell weaker positions, buy stronger ones — expected alpha gain_"]
    for r in rots[:max_rows]:
        from_name = _ticker_with_name(r["from"], market)
        to_name = _ticker_with_name(r["to"], market)
        lines.append(f"   🔻 {from_name}")
        lines.append(f"      ⬇️ replace with")
        lines.append(f"   🟢 {to_name}   +{r['alpha']:.1f}% expected alpha")
    if len(rots) > max_rows:
        lines.append(f"   _...+{len(rots) - max_rows} more rotation signals_")
    return lines


def _actionable_entries(recs: Sequence[Mapping], market: str,
                          max_rows: int = 4) -> list[str]:
    """Recs with is_actionable_entry — ranked by ensemble_score."""
    picks = [r for r in recs
              if (r.get("investor_action") or {}).get("is_actionable_entry")]
    picks.sort(key=lambda r: -(r.get("ensemble_score") or 0))
    if not picks:
        return []
    lines = ["", f"🟢 *NEW BUY IDEAS ({len(picks)})*",
             "   _If you don't own these, consider entering_"]
    for r in picks[:max_rows]:
        t = _ticker_with_name(r.get("ticker") or "?", market)
        ia = r.get("investor_action") or {}
        pp = r.get("position_plan") or {}
        ez = pp.get("entry_zone") or {}
        alloc = pp.get("suggested_allocation_pct") or 0
        hdays = pp.get("time_horizon_days") or 0
        entry = ia.get("entry") or "?"
        # Emoji per entry-level
        emoji = "🟢🟢" if entry == "BUY" and (r.get("percentile_action") == "STRONG_BUY") else "🟢"
        lines.append(f"   {emoji} *{t}*")
        lines.append(f"      💰 {entry} · size {alloc}% of capital · hold ~{hdays} days")
        if ez.get("stop_loss") is not None and ez.get("target_1") is not None:
            lines.append(
                f"      📥 Buy zone: {_fmt_price(ez.get('ideal_buy_low'), market)}"
                f"–{_fmt_price(ez.get('ideal_buy_high'), market)}"
            )
            lines.append(
                f"      🛡 Stop: {_fmt_price(ez.get('stop_loss'), market)}"
                f"   🎯 Target: {_fmt_price(ez.get('target_1'), market)}"
            )
        else:
            cp = _fmt_price(ez.get("current_price"), market)
            lines.append(f"      💵 Current: {cp}")
    if len(picks) > max_rows:
        lines.append(f"   _...+{len(picks) - max_rows} more new-buy ideas_")
    return lines


def _actionable_exits(recs: Sequence[Mapping], market: str,
                        max_rows: int = 4) -> list[str]:
    exits = [r for r in recs
              if (r.get("investor_action") or {}).get("if_holding") in ("REDUCE", "EXIT")]
    exits.sort(key=lambda r: r.get("ensemble_score") or 0)   # worst first
    if not exits:
        return []
    lines = ["", f"🔴 *EXITS IF YOU HOLD ({len(exits)})*",
             "   _If any of these are in your portfolio, act on them_"]
    for r in exits[:max_rows]:
        t = _ticker_with_name(r.get("ticker") or "?", market)
        ia = r.get("investor_action") or {}
        action = ia.get("if_holding") or "?"
        emoji = "🔴🔴" if action == "EXIT" else "🟠"
        # Discipline check: if the exit reason class is RANK_ONLY / churn
        # AND ensemble_score is still positive, flag it.
        score = r.get("ensemble_score") or 0
        churn_warn = "   ⚠️ still positive-score — confirm intended" if (
            action in ("REDUCE", "EXIT") and score > 0) else ""
        risks = ((r.get("why") or {}).get("top_risks") or [None])[0]
        risks_short = (str(risks)[:80] + "...") if risks and len(str(risks)) > 80 else (risks or "")
        lines.append(f"   {emoji} *{t}*   →   {action}{churn_warn}")
        if risks_short:
            lines.append(f"      ⚠️ Reason: {risks_short}")
    if len(exits) > max_rows:
        lines.append(f"   _...+{len(exits) - max_rows} more exit signals_")
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
        lines.append("💼 *PORTFOLIO PULSE*")
    if top_opp.get("ticker"):
        lines.append(
            f"   🎯 Top opportunity: {_ticker_with_name(top_opp['ticker'], market)} · "
            f"{top_opp.get('action', '?')} · size {top_opp.get('allocation_pct', 0)}%"
        )
    if top_risk.get("ticker"):
        lines.append(
            f"   ⚠️ Top risk: {_ticker_with_name(top_risk['ticker'], market)} · "
            f"{top_risk.get('if_holding', '?')}"
        )
    return lines


def _ai_scorecard_line(payload: Mapping, market: str) -> list[str]:
    """v2.4: one-line AI Scorecard right below CEO CALL.
    v3.0 expansion: also list per-metric star breakdown so operator sees
    WHICH dimensions the AI is strong/weak on, not just the overall grade."""
    sc = payload.get("ai_scorecard") or {}
    if not sc or not sc.get("overall_score"):
        return []
    stars = "⭐" * max(0, min(5, sc.get("overall_stars") or 0))
    n = sc.get("n_trades") or 0
    verdict = (sc.get("verdict") or "-").replace("_", " ")
    period = f"{sc.get('period_start', '')[:10]} → {sc.get('period_end', '')[:10]}"
    lines = [
        "",
        f"📊 *AI PERFORMANCE SCORECARD*",
        f"   {stars}   {sc.get('overall_score')}/100 · {verdict}",
        f"   {n} closed trades · {period}",
    ]
    # Per-metric breakdown (load full scorecard if available)
    try:
        from pathlib import Path
        sc_path = Path("reports/ai_scorecard.json") if market == "india" else None
        if sc_path and sc_path.exists():
            full = json.loads(sc_path.read_text(encoding="utf-8"))
            metrics = full.get("metrics") or []
            if metrics:
                # Emoji per metric name for quick visual parsing
                emoji_map = {
                    "Recommendation Accuracy": "🎯",
                    "Exit Timing":              "🚪",
                    "Target Hit Rate":          "🏹",
                    "Risk Control":             "🛡",
                    "Rotation Quality":         "🔄",
                    "Confidence Calibration":   "📐",
                }
                for m in metrics:
                    name = m.get("name", "?")
                    e = emoji_map.get(name, "•")
                    st = "⭐" * (m.get("stars") or 0)
                    v = m.get("value", "-")
                    lines.append(f"   {e} {name}: {st} ({v})")
    except Exception:
        pass
    return lines


def _attribution_top(payload: Mapping) -> list[str]:
    """v2.4: which models drove today's decisions."""
    a = payload.get("attribution_summary") or {}
    if not a:
        return []
    drivers = a.get("dominant_drivers") or {}
    if not drivers:
        return []
    top_two = list(drivers.items())[:2]
    sector_share = a.get("avg_sector_share_pct")
    lines = ["", "🧠 *WHAT DROVE TODAY'S DECISIONS*"]
    for label, count in top_two:
        lines.append(f"   • {label}: dominant on {count} rec(s)")
    if sector_share is not None:
        active_emoji = "🟢 active" if a.get("sector_engine_measurably_active") else "⚪ quiet"
        lines.append(f"   • Sector engine share: {sector_share}%   ({active_emoji})")
    return lines


def _runner1_orphans(payload: Mapping, market: str, max_rows: int = 5) -> list[str]:
    """v3.0 Option D: Runner 1's active picks that Runner 2 did NOT include.

    Runner 1 is the defensive/legacy engine · demoted to a validation layer.
    Its picks are NOT active AEGIS recommendations — but showing them here
    preserves continuity ('where did APOLLO go?') and lets the operator
    see what a conservative model thinks vs what Runner 2 v3 (canonical)
    chose to promote.
    """
    if market != "india":
        return []   # Runner 1 covers India only today
    rv = payload.get("runner1_validation") or {}
    orphans = rv.get("runner1_orphans") or []
    if not orphans:
        return []
    lines = ["", f"📜 *DEFENSIVE VIEW · Runner 1 picks Runner 2 skipped ({len(orphans)})*",
             "   _Legacy engine's active picks · not AEGIS canonical recs · shown for continuity_"]
    for o in orphans[:max_rows]:
        t = _ticker_with_name(o.get("ticker") or "", market)
        strength = o.get("strength") or "?"
        score = o.get("score")
        score_s = f" · score {score:.0f}/100" if isinstance(score, (int, float)) else ""
        reason_short = (o.get("reason") or "")[:70]
        lines.append(f"   • *{t}* — {strength}{score_s}")
        if reason_short:
            lines.append(f"     _{reason_short}_")
    if len(orphans) > max_rows:
        lines.append(f"   _...+{len(orphans) - max_rows} more defensive picks_")
    lines.append(f"   ↳ Runner 1 → validation layer only (Option D · Article 4 SSoT)")
    return lines


def _runner1_agreement_summary(payload: Mapping, market: str) -> list[str]:
    """v3.0: one-line "Runner 1 agrees with N of M today's picks" summary."""
    if market != "india":
        return []
    rv = payload.get("runner1_validation") or {}
    if not rv:
        return []
    consensus = rv.get("consensus_pct")
    counts = rv.get("agreement_counts") or {}
    if consensus is None:
        return []
    emoji = "🟢" if consensus >= 40 else ("🟡" if consensus >= 20 else "🟠")
    return [
        "",
        f"🤝 *DUAL-ENGINE VALIDATION*",
        f"   {emoji} Runner 1 agrees with {counts.get('AGREE', 0)}/{rv.get('n_runner2_recs', 0)} "
        f"of today's picks ({consensus}% consensus)",
        f"   Disagreements: {counts.get('DISAGREE', 0)} · "
        f"Neutral: {counts.get('NEUTRAL', 0)} · "
        f"Not tracked: {counts.get('NOT_TRACKED', 0)}",
    ]


def _integrity_footer(payload: Mapping) -> list[str]:
    run_utc = str(payload.get("run_utc") or "")[:16].replace("T", " ")
    return [
        "",
        SEPARATOR,
        f"🔐 Run {run_utc} UTC · AEGIS v3.0",
        f"⚖️ Advisory only · PAPER · Not investment advice",
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
        ("dual_engine",  _runner1_agreement_summary(payload, market)),
        ("ai_scorecard", _ai_scorecard_line(payload, market)),
        ("rotations",    _rotation_calls(recs, market)),
        ("new_buys",     _actionable_entries(recs, market)),
        ("exits",        _actionable_exits(recs, market)),
        ("r1_orphans",   _runner1_orphans(payload, market)),
        ("evolution",    _evolution_summary(recs)),
        ("attribution",  _attribution_top(payload)),
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
