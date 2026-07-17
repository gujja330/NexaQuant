"""UX030 · interactive commands.

Deterministic, evidence-based command handlers. No LLM calls.
Each handler takes (ctx, args_string) and returns Markdown text."""
from __future__ import annotations

from ux.telegram.lib import icons, renderer
from ux.telegram.lib.aggregator import (
    Context, top_buys, exits, current_holdings, portfolio_summary,
    champion_summary, regime_label, calibration_note,
)


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


def cmd_help(ctx: Context, _: str = "") -> str:
    lines = [
        "*AEGIS COMMANDS*",
        "",
        "/summary            — daily executive summary",
        "/portfolio          — full portfolio breakdown",
        "/buy                — new buy signals",
        "/exits              — exit signals",
        "/health             — portfolio health report",
        "/risk               — risk dashboard",
        "/champion           — current champion strategy",
        "/challengers        — challenger scoreboard",
        "/regime             — market regime snapshot",
        "/performance        — weekly review",
        "/confidence         — confidence calibration status",
        "/why <ticker>       — reasons for the current recommendation",
        "/doctor <ticker>    — strategy doctor diagnosis",
        "/history <ticker>   — historical rec + calibration for ticker",
        "/compare <a> <b>    — head-to-head between two tickers",
        "/sector <name>      — sector snapshot",
        "/help               — this menu",
    ]
    return "\n".join(lines)


def cmd_summary(ctx: Context, _: str = "") -> str:
    return renderer.render_executive_summary(ctx)


def cmd_portfolio(ctx: Context, _: str = "") -> str:
    port = portfolio_summary(ctx)
    holdings = current_holdings(ctx)
    lines = [
        f"💼 *Portfolio*",
        f"  type: `{port.get('portfolio_type')}`   allocator: `{port.get('allocator')}`",
        f"  positions: {port['n_positions']}   cash: {_fmt_pct(port['cash_allocation_pct']/100)}",
        f"  top-5 share: {_fmt_pct(port['top5_share'])}",
        "",
        f"*HOLDINGS ({len(holdings)})*",
    ]
    for h in holdings[:15]:
        w = h.get("current_weight")
        pnl = h.get("unrealised_pnl_pct")
        icon = icons.sector_icon(h.get("sector", ""))
        lines.append(f"  {icon} `{h.get('ticker'):<12}` "
                        f"w {_fmt_pct(w, 2):<7}  "
                        f"P&L {icons.change_arrow(pnl)} {_fmt_pct(pnl, 2)}")
    if len(holdings) > 15:
        lines.append(f"  … {len(holdings) - 15} more")
    return "\n".join(lines)


def cmd_buy(ctx: Context, _: str = "") -> str:
    return renderer.render_new_buys_summary(ctx, n=10)


def cmd_exits(ctx: Context, _: str = "") -> str:
    outs = exits(ctx)
    if not outs:
        return f"{icons.STATUS['info']} No exits today."
    lines = [f"{icons.STATUS['exit']} *EXITS ({len(outs)})*", ""]
    for o in outs:
        pnl = o.get("unrealised_pnl_pct")
        lines.append(f"  `{o.get('ticker')}`   "
                        f"P&L {icons.change_arrow(pnl)} {_fmt_pct(pnl, 2)}   "
                        f"weight {_fmt_pct(o.get('current_weight'), 2)}")
    return "\n".join(lines)


def cmd_health(ctx: Context, _: str = "") -> str:
    return renderer.render_portfolio_health(ctx)


def cmd_risk(ctx: Context, _: str = "") -> str:
    posture = regime_label(ctx)
    port = portfolio_summary(ctx)
    lines = [
        f"⚠ *Risk Dashboard*",
        f"_{renderer._now_ist_str()}_",
        "",
        f"📊 Regime:            {icons.REGIME.get(posture, posture)}",
        f"💵 Cash cushion:      {_fmt_pct(port['cash_allocation_pct']/100)}",
        f"🧩 Top-5 concentration: {_fmt_pct(port['top5_share'])}",
        f"🎯 Positions:         {port['n_positions']}",
    ]
    return "\n".join(lines)


def cmd_champion(ctx: Context, _: str = "") -> str:
    return renderer.render_champion_update(ctx)


def cmd_challengers(ctx: Context, _: str = "") -> str:
    lb = ctx.challenger_scoreboard.get("leaderboard", []) or []
    if not lb:
        return f"{icons.STATUS['info']} No challenger scoreboard available."
    lines = [f"🏆 *Challenger Scoreboard*", ""]
    for row in lb:
        marker = "*" if row["rank"] == 1 else " "
        lines.append(
            f"  {marker}{row['rank']}. `{row['strategy']:<20}` "
            f"score {_fmt_num(row['composite_score']):<7}  "
            f"Sh {_fmt_num(row.get('sharpe')):<6}  "
            f"CAGR {_fmt_pct(row.get('cagr'))}"
        )
    return "\n".join(lines)


def cmd_regime(ctx: Context, _: str = "") -> str:
    posture = regime_label(ctx)
    rc = ctx.regime_comparison.get("regime_report", {}) or {}
    windows = rc.get("regime_windows", {}) or {}
    champs = rc.get("regime_champions", {}) or {}
    lines = [
        f"📊 *Market Regime*",
        f"",
        f"Current:  {icons.REGIME.get(posture, posture)}",
        f"",
        f"*Historical Windows*",
    ]
    for label, n in windows.items():
        lines.append(f"  {icons.REGIME.get(label, label)}   {n} days")
    if champs:
        lines += ["", "*Regime Champions*"]
        for label, info in champs.items():
            lines.append(f"  {icons.REGIME.get(label, label):<20} "
                            f"`{info['strategy']}`   CAGR {_fmt_pct(info.get('cagr'))}")
    return "\n".join(lines)


def cmd_performance(ctx: Context, _: str = "") -> str:
    return renderer.render_weekly_review(ctx)


def cmd_confidence(ctx: Context, _: str = "") -> str:
    c = calibration_note(ctx)
    if not c or not c.get("best_method"):
        return f"{icons.STATUS['info']} Confidence calibration not yet run."
    return "\n".join([
        f"📐 *Confidence Calibration*",
        f"",
        f"  method:       `{c['best_method']}`",
        f"  raw ECE:      {_fmt_num(c.get('raw_ece'), 4)}",
        f"  calibrated:   {_fmt_num(c.get('cal_ece'), 4)}",
        f"",
        f"_{c.get('governance') or ''}_",
    ])


def cmd_why(ctx: Context, args: str = "") -> str:
    ticker = (args or "").strip().upper()
    if not ticker:
        return "Usage: `/why <TICKER>`"
    rec = renderer._find_rec(ctx, ticker)
    if rec is None:
        return f"{icons.STATUS['warning']} No recommendation for `{ticker}`."
    reasons = rec.get("reasons_for", []) or []
    against = rec.get("reasons_against", []) or []
    lines = [
        f"🔎 *Why `{ticker}`?*",
        f"_{icons.rec_icon(rec.get('recommendation'))}_",
        "",
    ]
    if reasons:
        lines += ["*FOR*"] + [f"  {icons.STATUS['success']} {r}" for r in reasons[:6]]
    if against:
        lines += ["", "*AGAINST*"] + [f"  {icons.STATUS['warning']} {r}" for r in against[:6]]
    return "\n".join(lines)


def cmd_doctor(ctx: Context, args: str = "") -> str:
    ticker = (args or "").strip().upper()
    if not ticker:
        return "Usage: `/doctor <TICKER>`"
    diagnoses = ctx.strategy_doctor.get("diagnoses", []) or []
    match = [d for d in diagnoses if str(d.get("ticker", "")).upper() == ticker]
    if not match:
        return f"{icons.STATUS['info']} No diagnoses on file for `{ticker}`."
    lines = [f"🩺 *Doctor: `{ticker}`*", ""]
    for d in match[:5]:
        lines.append(f"  {icons.STATUS['warning']} {d.get('category', 'unknown')}: {d.get('detail', '')}")
    return "\n".join(lines)


def cmd_compare(ctx: Context, args: str = "") -> str:
    parts = (args or "").split()
    if len(parts) < 2:
        return "Usage: `/compare <TICKER_A> <TICKER_B>`"
    a, b = parts[0].upper(), parts[1].upper()
    ra = renderer._find_rec(ctx, a)
    rb = renderer._find_rec(ctx, b)
    if ra is None or rb is None:
        return f"{icons.STATUS['warning']} Missing rec for one of `{a}` / `{b}`."

    def row(label, ka, kb, fmt=_fmt_num):
        return f"  {label:<14} {fmt(ra.get(ka)):>10}   {fmt(rb.get(kb)):>10}"

    return "\n".join([
        f"⚖ *Compare*",
        f"                       `{a}`         `{b}`",
        row("score",       "composite_decision_score", "composite_decision_score"),
        row("conviction%", "conviction_pct", "conviction_pct"),
        row("confidence",  "confidence", "confidence"),
        row("score raw",   "score", "score"),
    ])


def cmd_history(ctx: Context, args: str = "") -> str:
    ticker = (args or "").strip().upper()
    if not ticker:
        return "Usage: `/history <TICKER>`"
    return f"{icons.STATUS['info']} History command is scoped for a future sprint (needs per-ticker rec history file)."


def cmd_sector(ctx: Context, args: str = "") -> str:
    name = (args or "").strip()
    if not name:
        return "Usage: `/sector <SECTOR NAME>`"
    recs = ctx.recommendations.get("recommendations", []) or []
    in_sector = [r for r in recs if str(r.get("sector", "")).lower() == name.lower()]
    if not in_sector:
        return f"{icons.STATUS['info']} No recommendations in sector `{name}`."
    icon = icons.sector_icon(name)
    lines = [f"{icon} *Sector: {name}*", ""]
    for r in sorted(in_sector, key=lambda x: -float(x.get("composite_decision_score") or 0))[:10]:
        lines.append(
            f"  `{r.get('ticker'):<12}`   "
            f"{icons.rec_icon(r.get('recommendation'))}   "
            f"score {_fmt_num(r.get('composite_decision_score'))}"
        )
    return "\n".join(lines)


COMMANDS = {
    "help":          {"handler": cmd_help,        "args": None,   "description": "list all commands"},
    "summary":       {"handler": cmd_summary,     "args": None,   "description": "daily executive summary"},
    "portfolio":     {"handler": cmd_portfolio,   "args": None,   "description": "portfolio breakdown"},
    "buy":           {"handler": cmd_buy,         "args": None,   "description": "new buy signals"},
    "exits":         {"handler": cmd_exits,       "args": None,   "description": "exit signals"},
    "health":        {"handler": cmd_health,      "args": None,   "description": "portfolio health"},
    "risk":          {"handler": cmd_risk,        "args": None,   "description": "risk dashboard"},
    "champion":      {"handler": cmd_champion,    "args": None,   "description": "champion strategy"},
    "challengers":   {"handler": cmd_challengers, "args": None,   "description": "challenger scoreboard"},
    "regime":        {"handler": cmd_regime,      "args": None,   "description": "market regime"},
    "performance":   {"handler": cmd_performance, "args": None,   "description": "weekly review"},
    "confidence":    {"handler": cmd_confidence,  "args": None,   "description": "calibration status"},
    "why":           {"handler": cmd_why,         "args": "<TICKER>",         "description": "reasons for rec"},
    "doctor":        {"handler": cmd_doctor,      "args": "<TICKER>",         "description": "strategy doctor"},
    "history":       {"handler": cmd_history,     "args": "<TICKER>",         "description": "rec history"},
    "compare":       {"handler": cmd_compare,     "args": "<TICKER_A> <B>",   "description": "head-to-head"},
    "sector":        {"handler": cmd_sector,      "args": "<SECTOR>",         "description": "sector snapshot"},
}


def dispatch(ctx: Context, text: str) -> str:
    """Parse `/cmd args...` and route to a handler."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return "Send /help to see the command menu."
    parts = text[1:].split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    entry = COMMANDS.get(cmd)
    if entry is None:
        return f"Unknown command `/{cmd}`. Try /help."
    return entry["handler"](ctx, args)
