"""Earnings sub-engine · 5% weight of Investability Score.

Wave 1.5: yfinance-derivable earnings signals:
    Earnings date proximity      · <7 days = event risk · reduce conviction
    Earnings trend (yoy)         · earnings growth positive
    EPS revisions (last quarter) · surprise positive
    Forward EPS growth expected  · analysts forecasting growth
    Payout ratio sustainable     · not paying more than earning

Wave 2 (Sprint K Part 26): dedicated estimate revisions feed (I/B/E/S-like)
· management guidance change detection · sell-side consensus trajectory.
"""
from __future__ import annotations

from datetime import date


def score(info: dict) -> tuple[float, dict]:
    signals = {}
    hits = 0
    total = 0

    def check(name, value, ok_fn, weight=1.0):
        nonlocal hits, total
        if value is None:
            signals[name] = {"value": None, "ok": None, "weight": weight}
            return
        try:
            ok = bool(ok_fn(value))
            total += weight
            signals[name] = {"value": value, "ok": ok, "weight": weight}
            if ok: hits += weight
        except (TypeError, ValueError):
            signals[name] = {"value": value, "ok": None, "weight": weight}

    # Earnings growth (yoy)
    check("earnings_growth_positive",
              info.get("earningsGrowth"),
              lambda v: v > 0, weight=2.0)
    check("earnings_growth_strong",
              info.get("earningsGrowth"),
              lambda v: v > 0.15, weight=1.5)

    # Quarterly earnings growth
    check("quarterly_earnings_growth",
              info.get("earningsQuarterlyGrowth"),
              lambda v: v > 0, weight=1.5)

    # Revenue growth
    check("revenue_growth",
              info.get("revenueGrowth"),
              lambda v: v > 0.05, weight=1.5)

    # Trailing EPS positive (profitable)
    check("trailing_eps_positive",
              info.get("trailingEps"),
              lambda v: v > 0, weight=2.0)

    # Forward EPS > Trailing EPS (analysts expect growth)
    trailing = info.get("trailingEps")
    forward = info.get("forwardEps")
    if trailing is not None and forward is not None:
        check("forward_eps_higher",
                  forward, lambda v: v > trailing, weight=1.5)

    # Payout ratio · sustainable dividend (0-70% healthy)
    check("payout_sustainable",
              info.get("payoutRatio"),
              lambda v: 0 <= v <= 0.70, weight=1.0)

    # Earnings date proximity · event risk if <7 days
    earnings_ts = info.get("earningsTimestamp")
    if earnings_ts:
        try:
            from datetime import datetime, timezone
            earnings_dt = datetime.fromtimestamp(earnings_ts, tz=timezone.utc).date()
            today = date.today()
            days = (earnings_dt - today).days
            check("earnings_not_imminent", days, lambda v: abs(v) > 7, weight=1.0)
        except Exception:
            pass

    score_0_100 = round(hits / total * 100, 1) if total else 50.0
    return score_0_100, {
        "engine":     "earnings.v1",
        "score":      score_0_100,
        "hits":       round(hits, 2),
        "total":      round(total, 2),
        "signals":    signals,
        "note":       "Wave 1.5 · Wave 2 adds analyst estimate revisions + guidance change detection",
    }
