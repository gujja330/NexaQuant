"""Decision Center · exit center.

Enumerates held positions that require operator attention today with
the specific reason(s) they need to be reviewed. Every entry is
advisory — the exit center never places an order."""
from __future__ import annotations


def exit_candidates(today_snapshot: dict, diff: dict) -> list[dict]:
    """Return held positions that need action, with all reasons stacked."""
    entries = today_snapshot.get("entries") or []
    held = [e for e in entries if e.get("currently_held")]

    # Index diff changes per ticker
    by_ticker: dict[str, list[dict]] = {}
    for c in (diff.get("changes") or []):
        by_ticker.setdefault(c["ticker"], []).append(c)

    exits = []
    for e in held:
        ticker = e.get("ticker")
        reasons: list[str] = []

        # Rule 1: target hit
        for c in by_ticker.get(ticker, []):
            if c["kind"] == "TARGET_HIT":
                reasons.append(f"TARGET HIT · {c['reason']}")
            elif c["kind"] == "STOP_HIT":
                reasons.append(f"STOP LOSS · {c['reason']}")
            elif c["kind"] == "DOWNGRADED":
                reasons.append(f"DOWNGRADED · {c['reason']}")
            elif c["kind"] == "SIZING_WARNING":
                reasons.append(f"SIZING WARNING · {c['reason']}")
            elif c["kind"] == "INTELLIGENCE_DOWN":
                reasons.append(f"INTELLIGENCE DECLINED · {c['reason']}")

        # Rule 2: today's action is exit-side
        if e.get("action") in ("Sell", "Reduce", "Avoid"):
            reasons.append(f"ACTION IS {e['action']}")

        # Rule 3: sizing verdict BLOCK regardless of diff
        if e.get("sizing_verdict") == "BLOCK":
            reasons.append("SIZING VERDICT: BLOCK")

        # Rule 4: severe unrealised loss (P/L below -8%)
        pnl = e.get("unrealised_pnl_pct")
        if pnl is not None and pnl <= -0.08:
            reasons.append(f"DRAWDOWN {pnl*100:+.1f}% (>= 8% loss)")

        # Rule 5: fusion action disagrees with raw action strongly
        fa = e.get("fusion_action")
        if fa in ("Reduce", "Avoid") and e.get("action") not in ("Sell", "Reduce", "Avoid"):
            reasons.append(f"FUSION SAYS {fa} (raw says {e.get('action')})")

        if reasons:
            exits.append({
                "ticker":            ticker,
                "sector":            e.get("sector"),
                "action":            e.get("action"),
                "intelligence_score":e.get("intelligence_score"),
                "current_weight":    e.get("current_weight"),
                "unrealised_pnl_pct":e.get("unrealised_pnl_pct"),
                "entry_price":       e.get("entry_price"),
                "target_1":          e.get("target_1"),
                "stop_loss":         e.get("stop_loss"),
                "reasons":           reasons,
                "severity":          _severity(reasons),
            })

    exits.sort(key=lambda x: -_severity_rank(x["severity"]))
    return exits


def _severity(reasons: list[str]) -> str:
    txt = " | ".join(reasons).upper()
    if any(k in txt for k in ("STOP LOSS", "BLOCK", "TARGET HIT")):
        return "CRITICAL"
    if any(k in txt for k in ("DOWNGRADED", "DRAWDOWN", "FUSION SAYS")):
        return "HIGH"
    if any(k in txt for k in ("WARNING", "INTELLIGENCE DECLINED", "ACTION IS")):
        return "MEDIUM"
    return "LOW"


def _severity_rank(sev: str) -> int:
    return {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(sev, 0)


def notifications(today_snapshot: dict, diff: dict,
                     exits: list[dict], watchlist: list[dict]) -> list[dict]:
    """Priority-tiered notifications for the operator surface."""
    notif = []

    # CRITICAL — every exit-center CRITICAL row
    for x in exits:
        if x["severity"] == "CRITICAL":
            notif.append({
                "priority": "CRITICAL",
                "ticker":   x["ticker"],
                "kind":     "EXIT_REVIEW",
                "detail":   f"{x['ticker']}: {'; '.join(x['reasons'])}",
            })

    # HIGH — new Strong-Buy
    for c in (diff.get("changes") or []):
        if c["kind"] == "NEW" and c.get("today_action") == "Strong-Buy":
            notif.append({
                "priority": "HIGH",
                "ticker":   c["ticker"],
                "kind":     "NEW_STRONG_BUY",
                "detail":   f"New Strong-Buy: {c['ticker']} ({c.get('sector')})",
            })

    # HIGH — upgraded to Strong-Buy
    for c in (diff.get("changes") or []):
        if c["kind"] == "UPGRADED" and c.get("today_action") == "Strong-Buy":
            notif.append({
                "priority": "HIGH",
                "ticker":   c["ticker"],
                "kind":     "UPGRADED_TO_STRONG_BUY",
                "detail":   f"{c['ticker']}: {c['yesterday_action']} → Strong-Buy",
            })

    # MEDIUM — every exit_center HIGH row
    for x in exits:
        if x["severity"] == "HIGH":
            notif.append({
                "priority": "MEDIUM",
                "ticker":   x["ticker"],
                "kind":     "EXIT_REVIEW",
                "detail":   f"{x['ticker']}: {'; '.join(x['reasons'])}",
            })

    # MEDIUM — new Buy candidates
    for c in (diff.get("changes") or []):
        if c["kind"] == "NEW" and c.get("today_action") == "Buy":
            notif.append({
                "priority": "MEDIUM",
                "ticker":   c["ticker"],
                "kind":     "NEW_BUY",
                "detail":   f"New Buy: {c['ticker']} ({c.get('sector')})",
            })

    # LOW — watchlist entries with positive trend
    for w in watchlist:
        if w.get("intel_trend") is not None and w["intel_trend"] > 2:
            notif.append({
                "priority": "LOW",
                "ticker":   w["ticker"],
                "kind":     "WATCHLIST_RISING",
                "detail":   f"{w['ticker']}: intelligence rising ({w['intel_trend']:+.1f}), "
                              f"{w['gap_to_buy']:.1f} pts from Buy threshold",
            })

    return notif
