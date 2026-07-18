"""Decision Center smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from decision_center.lib import snapshot, diff, summary, watchlist, exit_center       # noqa: E402


PASS, FAIL = 0, 0


def _check(label, cond, detail=""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))


def _snap(day, entries):
    return {
        "date": day,
        "n_recs": len(entries),
        "entries": entries,
    }


def _entry(ticker, action, intel=75, conf=0.85, held=False, pnl=None,
             entry=100, target=115, stop=93):
    return {
        "ticker": ticker, "sector": "TestSector", "industry": "TestInd",
        "action": action, "action_tier": snapshot.ACTION_TIER.get(action, 0),
        "intelligence_score": intel, "confidence": conf,
        "entry_price": entry, "target_1": target, "stop_loss": stop,
        "currently_held": held, "unrealised_pnl_pct": pnl,
        "sizing_verdict": "PASS", "fusion_action": action,
    }


def test_diff_first_run():
    today = _snap("2026-07-18", [_entry("AAA", "Buy")])
    r = diff.compute_diff(today, None)
    _check("first_run flagged", r["first_run"] is True)
    _check("changes empty", r["n_changes"] == 0)
    _check("action_counts populated", r["action_counts"] == {"Buy": 1})


def test_diff_new_and_removed():
    y = _snap("2026-07-17", [_entry("AAA", "Buy"), _entry("BBB", "Hold")])
    t = _snap("2026-07-18", [_entry("BBB", "Hold"), _entry("CCC", "Strong-Buy")])
    r = diff.compute_diff(t, y)
    kinds = [c["kind"] for c in r["changes"]]
    _check("NEW fires on CCC", "NEW" in kinds)
    _check("REMOVED fires on AAA", "REMOVED" in kinds)


def test_diff_upgrade_downgrade():
    y = _snap("2026-07-17", [_entry("AAA", "Hold"), _entry("BBB", "Buy")])
    t = _snap("2026-07-18", [_entry("AAA", "Buy"),  _entry("BBB", "Hold")])
    r = diff.compute_diff(t, y)
    aaa = next(c for c in r["changes"] if c["ticker"] == "AAA")
    bbb = next(c for c in r["changes"] if c["ticker"] == "BBB")
    _check("AAA UPGRADED", aaa["kind"] == "UPGRADED")
    _check("BBB DOWNGRADED", bbb["kind"] == "DOWNGRADED")


def test_diff_intelligence_delta_material():
    y = _snap("2026-07-17", [_entry("AAA", "Buy", intel=60)])
    t = _snap("2026-07-18", [_entry("AAA", "Buy", intel=70)])
    r = diff.compute_diff(t, y)
    kinds = [c["kind"] for c in r["changes"]]
    _check("INTELLIGENCE_UP fires on +10 delta", "INTELLIGENCE_UP" in kinds)


def test_diff_target_hit_on_held_position():
    y = _snap("2026-07-17", [_entry("AAA", "Buy", held=True, pnl=0.02)])
    # Today: pnl reaches (target-entry)/entry = (115-100)/100 = 0.15 within 2% zone
    t = _snap("2026-07-18", [_entry("AAA", "Buy", held=True, pnl=0.14)])
    r = diff.compute_diff(t, y)
    kinds = [c["kind"] for c in r["changes"]]
    _check("TARGET_HIT fires when pnl in target zone", "TARGET_HIT" in kinds)


def test_diff_stop_hit():
    y = _snap("2026-07-17", [_entry("AAA", "Buy", held=True, pnl=-0.01)])
    t = _snap("2026-07-18", [_entry("AAA", "Buy", held=True, pnl=-0.08)])
    r = diff.compute_diff(t, y)
    kinds = [c["kind"] for c in r["changes"]]
    _check("STOP_HIT fires when pnl in stop zone", "STOP_HIT" in kinds)


def test_summary_first_run_paragraph():
    r = {"first_run": True, "action_counts": {"Buy": 44, "Avoid": 127, "Hold": 19}}
    p = summary.build_paragraph(r)
    _check("first-run paragraph mentions Baseline",
            "Baseline" in p or "baseline" in p)


def test_summary_stable_paragraph():
    r = {"first_run": False, "n_changes": 0, "counts_by_kind": {}, "action_counts": {}}
    p = summary.build_paragraph(r)
    _check("stable-day paragraph is emitted",
            "No material changes" in p or "stable" in p)


def test_watchlist_picks_near_buy():
    today = _snap("2026-07-18", [
        _entry("AAA", "Hold",       intel=68),   # near buy
        _entry("BBB", "Buy",        intel=72),   # already Buy — skip
        _entry("CCC", "Watchlist",  intel=65),   # near buy
        _entry("DDD", "Sell",       intel=50),   # not near buy
    ])
    yesterday = _snap("2026-07-17", [
        _entry("AAA", "Hold", intel=64),
        _entry("CCC", "Watchlist", intel=62),
    ])
    w = watchlist.watchlist_candidates(today, yesterday)
    tickers = [x["ticker"] for x in w]
    _check("AAA in watchlist", "AAA" in tickers)
    _check("CCC in watchlist", "CCC" in tickers)
    _check("BBB (already Buy) NOT in watchlist", "BBB" not in tickers)
    _check("DDD (Sell) NOT in watchlist", "DDD" not in tickers)
    # AAA had +4 trend, CCC had +3 — AAA should be first
    if len(w) >= 2:
        _check("higher-trend ticker ranked first", w[0]["ticker"] == "AAA")


def test_exit_center_flags_held_stop_hit():
    today = _snap("2026-07-18", [
        _entry("AAA", "Buy", held=True, pnl=-0.10),   # deep drawdown
    ])
    d = diff.compute_diff(today, None)
    exits = exit_center.exit_candidates(today, d)
    _check("held drawdown flagged in exit_center", len(exits) == 1)
    if exits:
        _check("severity is CRITICAL or HIGH",
                exits[0]["severity"] in ("CRITICAL", "HIGH"),
                detail=exits[0]["severity"])


def test_notifications_include_new_strong_buy():
    y = _snap("2026-07-17", [_entry("BBB", "Buy")])
    t = _snap("2026-07-18", [
        _entry("BBB", "Buy"),
        _entry("AAA", "Strong-Buy"),
    ])
    d = diff.compute_diff(t, y)
    notif = exit_center.notifications(t, d, [], [])
    kinds = [n["kind"] for n in notif]
    _check("NEW_STRONG_BUY notification fires", "NEW_STRONG_BUY" in kinds)


def test_deterministic():
    today = _snap("2026-07-18", [_entry("AAA", "Buy", intel=70),
                                    _entry("BBB", "Hold", intel=55)])
    yesterday = _snap("2026-07-17", [_entry("AAA", "Buy", intel=60),
                                        _entry("BBB", "Hold", intel=55)])
    d1 = diff.compute_diff(today, yesterday)
    d2 = diff.compute_diff(today, yesterday)
    _check("diff is deterministic",
            d1["counts_by_kind"] == d2["counts_by_kind"])


def main() -> int:
    print("=" * 72); print("  DECISION CENTER · SMOKE TESTS"); print("=" * 72)
    test_diff_first_run(); print()
    test_diff_new_and_removed(); print()
    test_diff_upgrade_downgrade(); print()
    test_diff_intelligence_delta_material(); print()
    test_diff_target_hit_on_held_position(); print()
    test_diff_stop_hit(); print()
    test_summary_first_run_paragraph(); print()
    test_summary_stable_paragraph(); print()
    test_watchlist_picks_near_buy(); print()
    test_exit_center_flags_held_stop_hit(); print()
    test_notifications_include_new_strong_buy(); print()
    test_deterministic(); print()
    print(f"  {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
