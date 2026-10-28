"""Guard 7 must grade the market it is sending, and must still bite.

CEO 2026-10-28 · This is the guard that blocked every USA delivery.

`run_health_check(root)` took no market and ENGINES was one flat list, so
a USA send was graded against India's artifacts:

    [guard7:health] BLOCKING send · 3 critical engines failed
      X reports/context/cil_run_india.json        age 49.5d > threshold 1d
      X reports/research/health_scores_india.json age 49.5d > threshold 1d
      X reports/fii_dii_flow.json                 age 49.5d > threshold 2d

India never tripped it because India's own run rewrites those files first.
The USA workflow does not run India's CIL engine, so the USA runner only
ever had the committed copies - frozen at 2026-09-08.

Two kinds of test here, deliberately:

  1. SCOPE  - the right rows are graded for each market.
  2. BITE   - with the scope fix in place the guard can STILL go RED.

(2) matters more than (1). Narrowing a check is the easiest way to turn a
blocking guard into one that always passes, and a guard that cannot fail
is worse than no guard because it reads as protection. Every bite test
builds its own tree under tmp_path - none of them touch the repo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.context import health_monitor as hm

REPO = Path(__file__).resolve().parents[2]


# ── helpers · isolated fixtures only ─────────────────────────────────
def _rows(scope):
    """The rows run_health_check would grade for `scope`."""
    return [r for r in hm.ENGINES if scope is None or r[4] in (None, scope)]


def _write(root: Path, rel: str, min_bytes: int, asof: str | None,
           age_days: float = 0.0):
    """Write a row's file · `age_days` backdates the MTIME too.

    Both have to be backdated. _check_one computes
        effective_age = min(mtime_age, asof_age)
    so a file rewritten today carrying a 50-day-old `asof` is graded
    FRESH. That is a real weakness - a daily rewrite of stale content
    passes - but it is pre-existing behaviour with both markets riding on
    it, so these tests encode what the code DOES rather than quietly
    changing it. See the note in the module docstring of health_monitor.
    """
    import os
    import time
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if rel.endswith(".json"):
        body = {"asof": asof, "pad": "x" * (min_bytes + 500)}
        p.write_text(json.dumps(body), encoding="utf-8")
    else:
        p.write_bytes(b"x" * (min_bytes + 500))
    if age_days:
        t = time.time() - age_days * 86400.0
        os.utime(p, (t, t))
    return p


def _healthy_tree(tmp_path: Path, scope: str) -> Path:
    """A root where every row in `scope` passes · the control case."""
    from datetime import date
    today = date.today().isoformat()
    root = tmp_path / ("root_%s" % scope)
    for rel, _crit, _days, min_b, _mkt in _rows(scope):
        _write(root, rel, min_b, today)
    return root


# ── 1 · scope ────────────────────────────────────────────────────────
def test_every_registry_row_declares_a_market():
    for row in hm.ENGINES:
        assert len(row) == 5, (
            "ENGINES row %r is not a 5-tuple · an un-scoped row is graded "
            "against BOTH markets, which is the original defect" % (row,))
        assert row[4] in (None, "india", "usa"), (
            "%s declares market %r · must be None, 'india' or 'usa'"
            % (row[0], row[4]))


def test_usa_scope_excludes_india_only_artifacts():
    graded = {r[0] for r in _rows("usa")}
    for p in ("reports/context/cil_run_india.json",
              "reports/research/health_scores_india.json",
              "reports/fii_dii_flow.json"):
        assert p not in graded, (
            "%s is graded on a USA send · nothing on the USA runner "
            "regenerates it, so it is stale on every run and blocks "
            "delivery forever" % p)


def test_india_scope_excludes_usa_only_artifacts():
    graded = {r[0] for r in _rows("india")}
    for p in ("usa/reports/runner1_orphans.json",
              "reports/context/cil_run_usa.json",
              "reports/research/health_scores_usa.json"):
        assert p not in graded, "%s is graded on an India send" % p


def test_usa_keeps_equivalent_coverage_not_reduced_coverage():
    """Dropping India's rows must not mean USA checks less."""
    graded = {r[0] for r in _rows("usa")}
    for p in ("reports/context/cil_run_usa.json",
              "reports/research/health_scores_usa.json"):
        assert p in graded, (
            "%s is missing · the India row it replaces was CRITICAL, so "
            "removing one without adding the other weakens the guard" % p)
    crit = {r[0] for r in _rows("usa") if r[1] == "CRITICAL"}
    assert len(crit) >= 10, (
        "only %d CRITICAL rows survive a USA send · the scope filter has "
        "gutted the guard" % len(crit))


def test_default_scope_is_unchanged_behaviour(tmp_path):
    """market=None still grades everything · old callers are safe."""
    assert len(_rows(None)) == len(hm.ENGINES)
    r = hm.run_health_check(tmp_path, None)
    assert r["market_scope"] == "all"
    assert r["n_engines"] == len(hm.ENGINES)
    assert r["n_skipped_other_market"] == 0


def test_a_typo_in_market_is_refused_not_silently_ignored():
    """'USA ' or 'us' must not skip every scoped row and report GREEN."""
    for bad in ("us", "nse", "USA1", "both"):
        with pytest.raises(ValueError):
            hm.run_health_check(REPO, bad)


def test_scope_is_recorded_in_the_payload(tmp_path):
    r = hm.run_health_check(tmp_path, "usa")
    assert r["market_scope"] == "usa"
    assert r["n_skipped_other_market"] > 0
    assert any("india" in p for p in r["skipped_other_market"])
    assert "[usa]" in hm.render_summary(r)
    assert "not graded" in hm.render_summary(r)


# ── 2 · the guard must still BITE ────────────────────────────────────
def test_healthy_usa_tree_is_green(tmp_path):
    """Control case · if this is not GREEN the bite tests prove nothing."""
    root = _healthy_tree(tmp_path, "usa")
    r = hm.run_health_check(root, "usa")
    assert r["overall_verdict"] == "GREEN", (
        "a fully fresh USA tree graded %s · critical fails: %s"
        % (r["overall_verdict"], [f["path"] for f in r["critical_fails"]]))


@pytest.mark.parametrize("victim", [
    "reports/context/cil_run_usa.json",
    "reports/research/health_scores_usa.json",
    "usa/reports/runner1_orphans.json",
    "reports/macro_regime.json",
])
def test_a_missing_usa_critical_still_blocks(tmp_path, victim):
    """Delete one CRITICAL row · the USA send must go RED."""
    root = _healthy_tree(tmp_path, "usa")
    (root / victim).unlink()
    r = hm.run_health_check(root, "usa")
    assert r["overall_verdict"] == "RED", (
        "%s was deleted and the USA guard still said %s · the scope fix "
        "has made this guard unable to fail" % (victim, r["overall_verdict"]))
    assert victim in [f["path"] for f in r["critical_fails"]]


def test_a_stale_usa_critical_still_blocks(tmp_path):
    """Staleness - the exact failure mode - must still be caught."""
    root = _healthy_tree(tmp_path, "usa")
    _write(root, "reports/context/cil_run_usa.json", 400, "2026-09-08",
           age_days=50)
    r = hm.run_health_check(root, "usa")
    assert r["overall_verdict"] == "RED"
    f = [x for x in r["critical_fails"]
         if x["path"] == "reports/context/cil_run_usa.json"]
    assert f and f[0]["verdict"] == "STALE"


def test_a_skeleton_usa_critical_still_blocks(tmp_path):
    """An empty file is not a healthy engine."""
    root = _healthy_tree(tmp_path, "usa")
    (root / "reports/context/cil_run_usa.json").write_text(
        "{}", encoding="utf-8")
    r = hm.run_health_check(root, "usa")
    assert r["overall_verdict"] == "RED"


def test_india_staleness_no_longer_blocks_usa(tmp_path):
    """The regression itself · India rot must not stop a USA send."""
    root = _healthy_tree(tmp_path, "usa")
    for rel in ("reports/context/cil_run_india.json",
                "reports/research/health_scores_india.json",
                "reports/fii_dii_flow.json"):
        _write(root, rel, 400, "2026-09-08", age_days=49.5)
    r = hm.run_health_check(root, "usa")
    assert r["overall_verdict"] == "GREEN", (
        "India artifacts rotted and the USA send went %s · this is the bug "
        "that kept USA from ever delivering" % r["overall_verdict"])
    # and the same tree, graded as India, must still fail
    ri = hm.run_health_check(root, "india")
    assert ri["overall_verdict"] == "RED", (
        "those files are genuinely stale · India must still be blocked")


def test_emit_keeps_markets_from_clobbering_each_other(tmp_path):
    for m in ("india", "usa"):
        hm.emit(tmp_path, hm.run_health_check(tmp_path, m))
        p = tmp_path / "reports" / "context" / ("health_monitor_%s.json" % m)
        assert p.exists(), "%s has no own health file · the second market " \
                           "to run overwrites the first" % m
        assert json.loads(p.read_text(encoding="utf-8"))["market_scope"] == m
    # canonical path still written · fresh_opportunities.py reads it
    assert (tmp_path / "reports" / "context" / "health_monitor.json").exists()


def test_sender_passes_the_market_to_the_guard():
    """Source-level · the call site is what regressed."""
    src = (REPO / "scripts" / "telegram_command_center_send.py").read_text(
        encoding="utf-8")
    assert "_hc(_ROOT, _hc_market)" in src, (
        "the sender calls the health check without a market again · a USA "
        "send will be graded against India's artifacts")
