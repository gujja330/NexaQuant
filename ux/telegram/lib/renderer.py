"""UX030 · Telegram message renderer.

Every message type from the spec has a `render_*` function that takes a
`Context` (from aggregator) and returns a **Telegram-Markdown string**.

Design principles:
- Mobile-first. Every message reads on a phone screen in <= 30 seconds.
- No hardcoded tickers / sectors / companies — all pulled from context.
- Deterministic — same context in, same string out.
- No LLM calls; every "AI summary" is a rule-based synthesis of the context.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ux.telegram.lib import icons
from ux.telegram.lib.aggregator import (
    Context, top_buys, exits, current_holdings, portfolio_summary,
    champion_summary, regime_label, calibration_note,
)


BRAND = "NEXAQUANT · AEGIS"


def _fmt_pct(x, digits=1):
    if x is None:
        return "n/a"
    try:
        return f"{float(x)*100:.{digits}f}%" if abs(float(x)) < 3 else f"{float(x):.{digits}f}%"
    except Exception:
        return "n/a"


def _fmt_num(x, digits=2):
    if x is None:
        return "n/a"
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "n/a"


def _now_ist_str() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d · %H:%M IST")


# ═══════════════════════════════════════════════════════════════════════
# 1. Daily Executive Summary
# ═══════════════════════════════════════════════════════════════════════
def render_executive_summary(ctx: Context) -> str:
    buys      = top_buys(ctx, n=1)
    all_buys  = top_buys(ctx, n=99)
    all_exits = exits(ctx)
    holdings  = current_holdings(ctx)

    posture = regime_label(ctx)
    champ = champion_summary(ctx)
    port  = portfolio_summary(ctx)

    top_buy = buys[0] if buys else None
    top_ticker = (top_buy or {}).get("ticker", "-")
    top_conf   = (top_buy or {}).get("confidence")
    top_conf_pct = None if top_conf is None else float(top_conf) * 100

    ai_summary = _daily_ai_summary(posture, len(all_buys), len(all_exits), port["cash_allocation_pct"])

    lines = [
        f"🏢 *{BRAND} · Daily*",
        f"_{_now_ist_str()}_",
        "",
        f"{icons.STATUS['buy']} *BUY:*  {len(all_buys)}    "
        f"{icons.STATUS['hold']} *HOLD:* {len(holdings) - len(all_exits)}    "
        f"{icons.STATUS['exit']} *EXIT:* {len(all_exits)}",
        "",
        f"📊 *Market Regime:* {icons.REGIME.get(posture, posture)}",
        f"🏆 *Champion:* `{champ['strategy']}`   Sharpe {_fmt_num(champ.get('sharpe'))}",
        "",
        f"💼 *Portfolio*",
        f"  positions: {port['n_positions']}   cash: {_fmt_pct(port['cash_allocation_pct']/100)}",
        f"  top-5 concentration: {_fmt_pct(port['top5_share'])}",
        "",
    ]
    if top_buy is not None:
        stars = icons.confidence_stars(top_conf_pct)
        lines += [
            f"🥇 *Top Opportunity*",
            f"  `{top_ticker}`   {stars}   conf {_fmt_num(top_conf_pct, 0)}%",
            "",
        ]
    if all_exits:
        exit_tickers = "  ".join(f"`{e.get('ticker')}`" for e in all_exits[:5])
        lines += [
            f"{icons.STATUS['warning']} *Exits:* {exit_tickers}",
            "",
        ]

    lines += [
        f"🤖 *AI Summary*",
        f"  _{ai_summary}_",
        "",
        f"👇 Reply /help for commands",
    ]
    return "\n".join(lines)


def _daily_ai_summary(regime: str, n_buys: int, n_exits: int, cash_pct: float) -> str:
    """3-sentence rule-based synthesis."""
    s = []
    if regime == "Risk-Off":
        s.append("Weak market regime.")
    elif regime == "Risk-On":
        s.append("Constructive market regime.")
    else:
        s.append("Neutral market regime.")

    if n_buys == 0 and n_exits > 0:
        s.append("No fresh buys today; trimming risk.")
    elif n_exits > n_buys:
        s.append("Defensive posture: more exits than entries.")
    elif n_buys > 0 and n_exits == 0:
        s.append("Deploying capital into fresh opportunities.")
    else:
        s.append("Rebalancing without net directional change.")

    if cash_pct >= 40:
        s.append("Maintain defensive cash buffer.")
    elif cash_pct >= 20:
        s.append("Cash buffer within normal band.")
    else:
        s.append("Cash near minimum; sizing discipline is tight.")

    return " ".join(s)


# ═══════════════════════════════════════════════════════════════════════
# 2. Buy Alert
# ═══════════════════════════════════════════════════════════════════════
def render_buy_alert(ctx: Context, ticker: str) -> str:
    rec = _find_rec(ctx, ticker)
    if rec is None:
        return f"{icons.STATUS['warning']} No recommendation on file for `{ticker}`."

    conf = rec.get("confidence")
    conf_pct = None if conf is None else float(conf) * 100
    ee = rec.get("entry_exit", {}) or {}
    ideal_low = rec.get("ideal_entry_low", ee.get("ideal_entry_low"))
    ideal_high = rec.get("ideal_entry_high", ee.get("ideal_entry_high"))
    t1 = rec.get("target_1", ee.get("target_1"))
    t2 = rec.get("target_2", ee.get("target_2"))
    sl = rec.get("stop_loss", ee.get("stop_loss"))
    hold_days = rec.get("expected_hold_days", ee.get("expected_hold_days"))
    expiry = _expiry_from_days(hold_days)
    reasons = rec.get("reasons_for", []) or []

    sector = rec.get("sector", "-")
    icon = icons.sector_icon(sector)

    lines = [
        f"{icons.STATUS['buy']} *BUY ALERT*   {icon} `{ticker}`",
        f"_{icons.rec_icon(rec.get('recommendation'))}_",
        "",
        f"📥 *Entry:*  {_fmt_num(ideal_low)} — {_fmt_num(ideal_high)}",
        f"🎯 *Target 1:* {_fmt_num(t1)}   *Target 2:* {_fmt_num(t2)}",
        f"🛑 *Stop:*   {_fmt_num(sl)}",
        "",
        f"⚖ *Confidence:* {icons.confidence_stars(conf_pct)}  {_fmt_num(conf_pct, 0)}%",
        f"⏳ *Hold:* ~{hold_days or 'n/a'} days   {expiry}",
        f"🏭 *Sector:* {sector}",
    ]
    if reasons:
        lines += ["", "*WHY*"]
        lines += [f"  {icons.STATUS['success']} {r}" for r in reasons[:5]]
    return "\n".join(lines)


def _expiry_from_days(days) -> str:
    if not isinstance(days, (int, float)) or days <= 0:
        return ""
    d = int(days)
    return f"⌛ expires in ~{d} days"


def _find_rec(ctx: Context, ticker: str) -> dict | None:
    recs = ctx.recommendations.get("recommendations", []) or []
    for r in recs:
        if str(r.get("ticker", "")).upper() == ticker.upper():
            return r
    return None


# ═══════════════════════════════════════════════════════════════════════
# 3. Exit Alert
# ═══════════════════════════════════════════════════════════════════════
def render_exit_alert(ctx: Context, ticker: str) -> str:
    rec = _find_rec(ctx, ticker)
    if rec is None:
        return f"{icons.STATUS['warning']} No recommendation on file for `{ticker}`."

    pnl = rec.get("unrealised_pnl_pct")
    weight = rec.get("current_weight")
    reasons = rec.get("reasons_against", []) or []
    lines = [
        f"{icons.STATUS['exit']} *EXIT ALERT*   `{ticker}`",
        f"_{icons.rec_icon(rec.get('recommendation'))}_",
        "",
        f"💰 *P&L:*  {icons.change_arrow(pnl)} {_fmt_pct(pnl, 2)}",
        f"⚖ *Weight released:* {_fmt_pct(weight, 2)}",
    ]
    if reasons:
        lines += ["", "*WHY EXIT*"]
        lines += [f"  {icons.STATUS['warning']} {r}" for r in reasons[:5]]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# 4. Portfolio Health
# ═══════════════════════════════════════════════════════════════════════
def render_portfolio_health(ctx: Context) -> str:
    port = portfolio_summary(ctx)
    champ = champion_summary(ctx)
    posture = regime_label(ctx)

    hhi_est = port["top5_share"]  # crude proxy for concentration
    diversification_grade = "A" if hhi_est < 0.30 else ("B" if hhi_est < 0.50 else "C")
    risk_level = "Low" if posture == "Risk-On" else ("High" if posture == "Risk-Off" else "Medium")
    overall = "A" if diversification_grade == "A" and risk_level in ("Low", "Medium") else "B"

    health_score = int(round(
        (60 if diversification_grade == "A" else 45 if diversification_grade == "B" else 30) +
        (30 if risk_level == "Low" else 20 if risk_level == "Medium" else 10)
    ))

    return "\n".join([
        f"💼 *Portfolio Health*",
        f"_{_now_ist_str()}_",
        "",
        f"📊 *Overall Grade:*   {icons.GRADES.get(overall, overall)}",
        f"📈 *Health:* {icons.progress_bar(health_score)}  {health_score}/100",
        "",
        f"🎯 *Positions:*        {port['n_positions']}",
        f"💵 *Cash:*             {_fmt_pct(port['cash_allocation_pct']/100)}",
        f"🧩 *Top-5 share:*      {_fmt_pct(port['top5_share'])}",
        f"🌐 *Diversification:* {icons.GRADES.get(diversification_grade)}",
        f"⚠ *Risk level:*      {icons.risk_icon(risk_level)}",
        "",
        f"🏆 *Champion:*  `{champ['strategy']}`",
        f"   Sharpe {_fmt_num(champ.get('sharpe'))}   Max DD {_fmt_num(champ.get('max_dd_pct'))}%",
        f"📊 *Regime:*   {icons.REGIME.get(posture, posture)}",
    ])


# ═══════════════════════════════════════════════════════════════════════
# 5. Risk Alert
# ═══════════════════════════════════════════════════════════════════════
def render_risk_alert(ctx: Context, alert: dict) -> str:
    kind = alert.get("type", "unknown")
    ticker = alert.get("ticker", "")
    detail = alert.get("detail", "")
    return "\n".join([
        f"{icons.STATUS['alert']} *RISK ALERT*   `{ticker}`",
        f"*Type:* {kind}",
        f"",
        f"_{detail}_",
    ])


# ═══════════════════════════════════════════════════════════════════════
# 6. Strategy Change Alert
# ═══════════════════════════════════════════════════════════════════════
def render_champion_update(ctx: Context) -> str:
    champ = champion_summary(ctx)
    promo = ctx.promotion.get("promotion", {}) or {}
    decision = promo.get("decision", "hold_champion")
    reason = promo.get("reason", "")
    icon = "🏆" if decision in ("initial_champion", "promote_challenger", "hold_champion") else "⚠"

    # Telegram Markdown treats a single '_' as an italic marker. Decision
    # strings like `initial_champion` and reason strings that contain
    # underscores would leave an unclosed italic (parse error at the
    # trailing '_'). Wrap identifiers in backticks (code span → literal
    # underscores) instead of italic underscores; escape underscores in
    # free-text `reason` as `\_`.
    def _esc_underscores(s: str) -> str:
        return s.replace("_", r"\_")

    lines = [
        f"{icon} *CHAMPION STRATEGY UPDATE*",
        "",
        f"*Current Champion:*  `{champ['strategy']}`",
        f"  composite: {_fmt_num(champ.get('composite_score'))}",
        f"  Sharpe: {_fmt_num(champ.get('sharpe'))}   CAGR: {_fmt_pct(champ.get('cagr'))}",
        f"  Max DD: {_fmt_num(champ.get('max_dd_pct'))}%",
        "",
        f"*Decision:* `{decision}`",
        _esc_underscores(reason) if reason else "",
    ]
    return "\n".join(l for l in lines if l != "")


# ═══════════════════════════════════════════════════════════════════════
# 7. Weekly / Monthly Review (compact table)
# ═══════════════════════════════════════════════════════════════════════
def render_weekly_review(ctx: Context) -> str:
    leaderboard = ctx.challenger_scoreboard.get("leaderboard", []) or []
    posture = regime_label(ctx)
    lines = [
        f"📅 *Weekly Review*",
        f"_{_now_ist_str()}_",
        "",
        f"📊 *Regime:*  {icons.REGIME.get(posture, posture)}",
        "",
        f"🏆 *Leaderboard*",
    ]
    for row in leaderboard[:5]:
        marker = "*" if row["rank"] == 1 else " "
        lines.append(f"  {marker}{row['rank']}. `{row['strategy']:<18}`   "
                        f"score {_fmt_num(row['composite_score'])}   "
                        f"Sharpe {_fmt_num(row.get('sharpe'))}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# 8. New Buy Alert (fresh entry)
# ═══════════════════════════════════════════════════════════════════════
def render_new_buys_summary(ctx: Context, n: int = 5) -> str:
    """Legacy-style formatter — matches the operator's tracking template:

        TICKER · Sector · Rank #N
            ₹CMP → Target ₹T  🟢 +X.X% · +Y/sh
            BUY · Stop ₹S (-Z%) · Hold Ndays · Score S/100

    Rendered so the operator can visually scan the same shape as the
    sealed legacy paper-portfolio Telegram.
    """
    buys = top_buys(ctx, n=n)
    if not buys:
        return f"{icons.STATUS['info']} No fresh buys today. See Current Holdings."

    lines = [
        f"{icons.STATUS['buy']} *TOP OPPORTUNITIES*",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for b in buys:
        ticker = b.get("ticker") or "?"
        sector = b.get("sector") or "—"
        rank   = b.get("overall_rank")
        action = b.get("recommendation") or "Buy"
        conf   = b.get("confidence")
        conf_pct = None if conf is None else float(conf) * 100
        score  = b.get("composite_decision_score")

        ee = b.get("entry_exit") or {}
        cmp_val  = ee.get("latest_close")
        target   = ee.get("target_1")
        stop     = ee.get("stop_loss")
        stop_pct = ee.get("stop_loss_pct")     # already percent, negative
        hold     = ee.get("expected_holding_days")

        # Upside/gain
        if cmp_val and target:
            upside_pct = (target - cmp_val) / cmp_val * 100
            gain_per_sh = target - cmp_val
        else:
            upside_pct = None
            gain_per_sh = None

        up_icon = "🟢" if (upside_pct or 0) > 0 else "🔴"

        # Header row: TICKER · Sector · rank
        header = f"`{ticker}` · {sector}"
        if rank:
            header += f" · #{int(rank)}"
        lines.append(header)

        # Price row: CMP → Target  icon +X.X% · +Y/sh
        price_row = f"    "
        if cmp_val is not None:
            price_row += f"₹{cmp_val:,.2f}"
        if target is not None:
            price_row += f" → ₹{target:,.2f}"
        if upside_pct is not None:
            price_row += f"  {up_icon} +{upside_pct:.1f}%"
            if gain_per_sh is not None:
                price_row += f" · +₹{gain_per_sh:,.0f}/sh"
        lines.append(price_row)

        # Action row: BUY · Stop ₹S (-Z%) · Hold Nd · Score S · Conf C%
        action_bits = [action.upper() if action else "BUY"]
        if stop is not None:
            stop_str = f"Stop ₹{stop:,.2f}"
            if stop_pct is not None:
                stop_str += f" ({stop_pct:+.1f}%)"
            action_bits.append(stop_str)
        if hold:
            action_bits.append(f"Hold {int(hold)}d")
        if score is not None:
            action_bits.append(f"Score {score:.0f}/100")
        if conf_pct is not None:
            action_bits.append(f"Conf {conf_pct:.0f}%")
        lines.append("    " + " · ".join(action_bits))

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# 9. Morning Market Brief (short)
# ═══════════════════════════════════════════════════════════════════════
def render_morning_brief(ctx: Context) -> str:
    posture = regime_label(ctx)
    n_buys = len(top_buys(ctx, n=99))
    n_exits = len(exits(ctx))
    return "\n".join([
        f"🌅 *Morning Brief*   _{_now_ist_str()}_",
        f"📊 Regime: {icons.REGIME.get(posture, posture)}",
        f"{icons.STATUS['buy']} Buys today: {n_buys}   {icons.STATUS['exit']} Exits: {n_exits}",
    ])
