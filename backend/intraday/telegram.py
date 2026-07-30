"""Standalone Telegram renderer for intraday · ZERO import from
backend/delivery/telegram/. Separate from delivery pipeline entirely.

MSG format: single message per market per session-close (post-VALIDATED_90D)
OR post-backtest evidence panel (during HISTORICAL_BACKTEST phase).
"""
from __future__ import annotations

import json
from pathlib import Path


SEP = "━━━━━━━━━━━━━━━━━━━━━━"
TELEGRAM_HARD_CAP = 4096


def render_intraday_evidence(root: Path, market: str = "india") -> str:
    """Backtest evidence panel · shows historical performance of the intraday
    engine before live paper begins. Used during HISTORICAL_BACKTEST phase."""
    p = root / "reports" / "intraday" / "intraday_platform.json"
    if not p.exists():
        return ""
    try:
        rp = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    prog = rp.get("program") or {}
    bt = rp.get("backtest") or {}
    flag = "🇮🇳" if market == "india" else "🇺🇸"

    lines = [
        "⚡ *AEGIS INTRADAY · Ticket R004*",
        f"{flag} {market.upper()}  ·  📋 State: *{prog.get('lifecycle_state', 'OPEN')}*",
        SEP,
        f"🏛 Product status: {prog.get('product_status', 'DEFERRED')}",
    ]

    if not bt:
        lines += ["", "_No backtest yet · run backend/intraday/backtest first_"]
        return "\n".join(lines).strip()

    n = bt.get("n_trades", 0)
    if n == 0:
        lines += ["",
                     "📊 *BACKTEST · zero trades emitted so far*",
                     f"   Sessions replayed: {bt.get('n_sessions', 0)}",
                     "   Cause typically: insufficient intraday-bar cache",
                     "   → fetch bars via feed router · then re-run backtest"]
        return "\n".join(lines).strip()

    wr = (bt.get("win_rate") or 0) * 100
    pf = bt.get("profit_factor")
    lines += ["",
                 "📊 *BACKTEST · aggregate*",
                 f"   Sessions: {bt.get('n_sessions', 0)}  ·  Trades: {n}",
                 f"   Win rate: {wr:.0f}%  ·  Winners: {bt.get('n_winners', 0)}  ·  "
                 f"Losers: {bt.get('n_losers', 0)}",
                 f"   Avg winner: {bt.get('avg_winner', 0):+.2f}%  ·  "
                 f"Avg loser: {bt.get('avg_loser', 0):+.2f}%",
                 f"   Total P&L: {bt.get('total_pnl', 0):+.2f}%  ·  "
                 f"PF: {pf if pf is not None else '—'}"]

    # Per-slot breakdown (operator's 3-slot framework)
    by_slot = bt.get("by_slot") or {}
    if by_slot:
        lines += ["", "⏱ *BY TRADING SLOT* (operator's framework)"]
        slot_labels = {
            "high_volatility": "🔥 HIGH VOL (09:15-10:15)",
            "stable_trend":    "📈 STABLE TREND (10:15-14:30)",
            "square_off":      "🏁 SQUARE-OFF (14:30-15:30)",
        }
        for slot, stats in by_slot.items():
            lab = slot_labels.get(slot, slot)
            lines.append(f"   {lab}: n={stats.get('n', 0)}  "
                            f"win {stats.get('win_rate', 0)*100:.0f}%  "
                            f"avg {stats.get('avg_pnl_pct', 0):+.2f}%")

    # Per-signal attribution
    by_signal = bt.get("by_signal") or {}
    if by_signal:
        lines += ["", "🔬 *BY SIGNAL FACTORY*"]
        for sig, stats in sorted(by_signal.items(),
                                    key=lambda x: -(x[1].get("avg_pnl_pct") or 0)):
            lines.append(f"   {sig}: n={stats.get('n', 0)}  "
                            f"win {stats.get('win_rate', 0)*100:.0f}%  "
                            f"avg {stats.get('avg_pnl_pct', 0):+.2f}%")

    lines += ["",
                 SEP,
                 "_Ticket R004 · docs/AEGIS_INTRADAY_ARCHITECTURE.md · paper-only_",
                 "_Advances to PAPER_PORTFOLIO after Sharpe > 1.0 net-of-slippage_"]

    msg = "\n".join(lines).strip()
    if len(msg) > TELEGRAM_HARD_CAP:
        msg = msg[:TELEGRAM_HARD_CAP - 40] + "\n\n_...truncated..._"
    return msg


def render_intraday_session_close(root: Path, market: str = "india") -> str:
    """Post-session-close MSG for live paper (PAPER_PORTFOLIO+) phase.
    Reads reports/intraday/paper_{market}_{today}.json."""
    from datetime import date
    p = root / "reports" / "intraday" / f"paper_{market}_{date.today().isoformat()}.json"
    if not p.exists():
        return ""
    try:
        paper = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    trades = paper.get("trades") or []
    flag = "🇮🇳" if market == "india" else "🇺🇸"

    if not trades:
        return "\n".join([
            "⚡ *AEGIS INTRADAY · session close*",
            f"{flag} {market.upper()}  ·  📅 {paper.get('session_date', '?')}",
            SEP,
            "_Quiet session · no signal fires · standard_",
        ])

    winners = [t for t in trades if (t.get("pnl_pct") or 0) > 0]
    losers = [t for t in trades if (t.get("pnl_pct") or 0) < 0]
    total_pnl = sum((t.get("pnl_pct") or 0) for t in trades)

    lines = [
        "⚡ *AEGIS INTRADAY · session close*",
        f"{flag} {market.upper()}  ·  📅 {paper.get('session_date', '?')}",
        SEP,
        f"🎯 Signals executed: {len(trades)}  ·  "
        f"Session P&L: *{total_pnl:+.2f}%*",
        f"🟢 Winners {len(winners)}  ·  🔴 Losers {len(losers)}",
        "",
        "🟢 *WINNERS*",
    ]
    for t in winners:
        lines.append(f"   {t.get('ticker')}: {t.get('pnl_pct'):+.2f}% "
                        f"· held {t.get('held_min', 0)}m · {t.get('signal')}")
    lines.append("")
    lines.append("🔴 *LOSERS*")
    for t in losers:
        lines.append(f"   {t.get('ticker')}: {t.get('pnl_pct'):+.2f}% "
                        f"· held {t.get('held_min', 0)}m · reason: {t.get('exit_reason')}")

    lines += ["", SEP, "_Ticket R004 · paper-only · not a live product_"]
    msg = "\n".join(lines).strip()
    if len(msg) > TELEGRAM_HARD_CAP:
        msg = msg[:TELEGRAM_HARD_CAP - 40] + "\n\n_...truncated..._"
    return msg
