"""UX030 smoke tests. Deterministic fixture context."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from ux.telegram.lib import icons, renderer, commands, notification_rules              # noqa: E402
from ux.telegram.lib.aggregator import Context                                          # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _fake_context() -> Context:
    return Context(
        recommendations = {
            "recommendations": [
                {"ticker": "AAA", "recommendation": "Strong-Buy",
                  "composite_decision_score": 92, "conviction_pct": 88,
                  "confidence": 0.92, "score": 85, "sector": "Health Care",
                  "currently_held": False,
                  "ideal_entry_low": 100, "ideal_entry_high": 105,
                  "target_1": 120, "target_2": 135, "stop_loss": 92,
                  "expected_hold_days": 45,
                  "reasons_for": ["Above 200DMA", "Sector leader", "Momentum rising"],
                  "reasons_against": []},
                {"ticker": "BBB", "recommendation": "Sell",
                  "composite_decision_score": 25, "conviction_pct": 40,
                  "confidence": 0.4, "score": 30, "sector": "Materials",
                  "currently_held": True, "current_weight": 0.05,
                  "unrealised_pnl_pct": -0.08,
                  "reasons_for": [], "reasons_against": ["Below 200DMA", "Sector weak"]},
                {"ticker": "CCC", "recommendation": "Hold",
                  "composite_decision_score": 60, "conviction_pct": 55,
                  "confidence": 0.65, "score": 60, "sector": "Financial Services",
                  "currently_held": True, "current_weight": 0.07,
                  "unrealised_pnl_pct": 0.03,
                  "reasons_for": ["Stable"], "reasons_against": []},
            ],
        },
        portfolio = {
            "portfolios": [{
                "portfolio_type": "balanced", "portfolio_display": "Balanced 20",
                "allocator": "hrp", "n_positions": 20,
                "cash_allocation_pct": 25.0,
                "positions": [
                    {"ticker": f"T{i}", "weight": 0.05, "sector": "s", "industry": "i"}
                    for i in range(20)
                ],
            }],
        },
        champion = {
            "champion": {"strategy": "top_5_ew", "composite_score": 95.9,
                          "sharpe": 0.97, "cagr": 0.25, "max_dd_pct": -25.0,
                          "win_rate": 0.61},
            "current_regime": {"global_posture": "Neutral"},
        },
        challenger_scoreboard = {
            "leaderboard": [
                {"rank": 1, "strategy": "top_5_ew", "composite_score": 95.9,
                  "sharpe": 0.97, "cagr": 0.25},
                {"rank": 2, "strategy": "top_20_ew", "composite_score": 87.2,
                  "sharpe": 1.06, "cagr": 0.24},
            ],
        },
        regime_comparison = {
            "regime_report": {
                "regime_windows": {"Risk-On": 640, "Neutral": 330, "Risk-Off": 130},
                "regime_champions": {
                    "Risk-On":  {"strategy": "top_5_ew",  "cagr": 0.45},
                    "Risk-Off": {"strategy": "top_20_ew", "cagr": 3.44},
                    "Neutral":  {"strategy": "top_5_ew",  "cagr": 1.12},
                },
            },
        },
        calibration = {
            "best_method": "platt_scaling",
            "raw_metrics": {"ece": 0.287},
            "calibrated_metrics": {"ece": 0.002},
            "governance": "Retrain only when new data available",
        },
        global_context = {"classifications": {"global_posture": "Neutral"}},
        promotion = {"promotion": {"decision": "initial_champion",
                                     "reason": "no prior champion recorded"}},
    )


def test_icons_registry():
    _check("STATUS has buy/hold/exit",
            all(k in icons.STATUS for k in ("buy", "hold", "exit")))
    _check("GRADES has A/B/C",
            all(k in icons.GRADES for k in ("A", "B", "C")))
    _check("REGIME has Risk-On/Off/Neutral",
            all(k in icons.REGIME for k in ("Risk-On", "Risk-Off", "Neutral")))


def test_confidence_stars():
    _check("95% -> 5 stars", icons.confidence_stars(95) == "★★★★★")
    _check("80% -> 3 stars", icons.confidence_stars(80) == "★★★☆☆")
    _check("87% -> 4 stars", icons.confidence_stars(87) == "★★★★☆")
    _check("60% -> 1 star",  icons.confidence_stars(60) == "★☆☆☆☆")
    _check("None -> empty",  icons.confidence_stars(None) == "☆☆☆☆☆")


def test_progress_bar():
    _check("0%  -> all empty",  icons.progress_bar(0)   == "░" * 10)
    _check("100% -> all full",  icons.progress_bar(100) == "█" * 10)
    _check("50% -> 5 full",     icons.progress_bar(50)  == "█" * 5 + "░" * 5)


def test_render_executive_summary_deterministic():
    ctx = _fake_context()
    s1 = renderer.render_executive_summary(ctx)
    s2 = renderer.render_executive_summary(ctx)
    _check("executive summary is deterministic", s1 == s2)
    _check("contains BUY count", "BUY:" in s1)
    _check("contains champion strategy name", "top_5_ew" in s1)
    _check("contains regime badge", "Neutral" in s1)


def test_render_buy_alert():
    ctx = _fake_context()
    msg = renderer.render_buy_alert(ctx, "AAA")
    _check("buy alert mentions ticker", "AAA" in msg)
    _check("buy alert has Entry", "Entry" in msg)
    _check("buy alert has Stop", "Stop" in msg)
    _check("buy alert has reasons",
            "Above 200DMA" in msg or "Sector leader" in msg)


def test_render_exit_alert():
    ctx = _fake_context()
    msg = renderer.render_exit_alert(ctx, "BBB")
    _check("exit alert mentions ticker", "BBB" in msg)
    _check("exit alert has P&L", "P&L" in msg)


def test_render_health():
    ctx = _fake_context()
    msg = renderer.render_portfolio_health(ctx)
    _check("health has Overall Grade", "Overall Grade" in msg)
    _check("health has champion", "top_5_ew" in msg)


def test_commands_dispatch():
    ctx = _fake_context()
    _check("/help returns menu",       "COMMANDS" in commands.dispatch(ctx, "/help"))
    _check("/summary returns text",    len(commands.dispatch(ctx, "/summary")) > 100)
    _check("/champion returns update", "CHAMPION" in commands.dispatch(ctx, "/champion"))
    _check("/regime returns dashboard","Market Regime" in commands.dispatch(ctx, "/regime"))
    _check("/confidence returns platt","platt_scaling" in commands.dispatch(ctx, "/confidence"))
    _check("unknown cmd is graceful",  "Unknown" in commands.dispatch(ctx, "/foo"))
    _check("non-slash prompts help",   "help" in commands.dispatch(ctx, "hello").lower())


def test_commands_why_and_compare():
    ctx = _fake_context()
    _check("/why AAA has reasons",   "Above 200DMA" in commands.dispatch(ctx, "/why AAA"))
    _check("/why unknown ticker",    "No recommendation" in commands.dispatch(ctx, "/why ZZZ"))
    out = commands.dispatch(ctx, "/compare AAA BBB")
    _check("/compare shows both tickers", "AAA" in out and "BBB" in out)


def test_commands_sector():
    ctx = _fake_context()
    out = commands.dispatch(ctx, "/sector Health Care")
    _check("/sector Health Care surfaces AAA", "AAA" in out)


def test_notification_rules():
    d = notification_rules.classify("stop_loss_hit")
    _check("stop_loss_hit is CRITICAL", d.priority == "CRITICAL")
    _check("stop_loss_hit sends now", d.send_now is True)

    d2 = notification_rules.classify("buy")
    _check("buy is MEDIUM",           d2.priority == "MEDIUM")
    _check("buy rolls into digest",   d2.send_now is False)

    ruleset = notification_rules.summarise_ruleset()
    _check("ruleset has 5 priorities", set(ruleset["priorities"]) ==
            {"CRITICAL", "HIGH", "MEDIUM", "LOW", "SILENT"})


def test_commands_count():
    _check(">=17 commands defined", len(commands.COMMANDS) >= 17)


def main() -> int:
    print("=" * 70)
    print("  UX030 v0.1 SMOKE TESTS")
    print("=" * 70)
    test_icons_registry(); print()
    test_confidence_stars(); print()
    test_progress_bar(); print()
    test_render_executive_summary_deterministic(); print()
    test_render_buy_alert(); print()
    test_render_exit_alert(); print()
    test_render_health(); print()
    test_commands_dispatch(); print()
    test_commands_why_and_compare(); print()
    test_commands_sector(); print()
    test_notification_rules(); print()
    test_commands_count(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
