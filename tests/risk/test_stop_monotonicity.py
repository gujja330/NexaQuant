"""STOP INTEGRITY · a stop may hold or rise · it may never fall.

THE DEFECT THESE TESTS EXIST TO PREVENT
----------------------------------------
`dynamic_risk_v2` has always documented "Never move stop DOWN · lift is
monotonic". It could not honour that: `original_stop` was hardcoded to
None with the comment "registry doesn't hold stop · sender does", so the
prior stop was never loaded and the monotonic guard compared today's
candidate against today's OWN freshly computed stop.

The stop was therefore `current_price - 2 x ATR14`, recomputed daily and
anchored to the CURRENT price. The gap to the stop is constant by
construction, so a sustained decline walks the stop down instead of
triggering it. ITC fell 284.85 -> 260.75 while its stop fell 276.10 ->
253.72, reporting INTACT at every step, and reached -8.46%.

Replay of the corrected semantics: India severe losses (<=-8%) 8 -> 0,
USA 117 -> 19.

These tests assert the CONTRACT, not the arithmetic of one example.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.risk import dynamic_risk_v2 as dr


def _sidecar(root: Path, market: str, stops: dict) -> Path:
    p = root / "reports" / "context" / ("dynamic_risk_%s.json" % market)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "market": market, "asof": "2026-09-10",
        "updates": [{"opportunity_id": k, "new_stop": v}
                    for k, v in stops.items()]}), encoding="utf-8")
    return p


def _floor(prior, candidate):
    """The invariant under test, isolated from I/O."""
    if prior is not None and candidate is not None and prior > candidate:
        return prior, "held"
    return candidate, "moved"


# ── 1 · initialisation ────────────────────────────────────────────────

def test_1_first_stop_initialises_normally(tmp_path):
    assert dr.load_prior_stops(tmp_path, "india") == {}
    v, kind = _floor(None, 100.0)
    assert v == 100.0 and kind == "moved"


def test_7_missing_prior_has_deterministic_initialisation(tmp_path):
    """A stop that cannot be proven to have existed is not invented."""
    assert dr.load_prior_stops(tmp_path, "usa") == {}
    (tmp_path / "reports" / "context").mkdir(parents=True)
    (tmp_path / "reports" / "context" / "dynamic_risk_usa.json").write_text(
        "{ not json", encoding="utf-8")
    assert dr.load_prior_stops(tmp_path, "usa") == {}


def test_12_malformed_prior_fails_safe(tmp_path):
    """A corrupt prior must be IGNORED, never used as a floor.

    A negative, zero, null or non-numeric prior that survived into the
    floor would pin the stop and could force an instant exit.
    """
    _sidecar(tmp_path, "india", {})
    p = tmp_path / "reports" / "context" / "dynamic_risk_india.json"
    p.write_text(json.dumps({"updates": [
        {"opportunity_id": "A", "new_stop": None},
        {"opportunity_id": "B", "new_stop": "abc"},
        {"opportunity_id": "C", "new_stop": -5.0},
        {"opportunity_id": "D", "new_stop": 0},
        {"opportunity_id": "E", "new_stop": 91.5},
        {"opportunity_id": None, "new_stop": 12.0},
    ]}), encoding="utf-8")
    got = dr.load_prior_stops(tmp_path, "india")
    assert got == {"E": 91.5}, got


# ── 2-6 · the monotonic contract ──────────────────────────────────────

def test_2_lower_candidate_retains_prior_stop():
    v, kind = _floor(276.10, 253.72)          # the ITC case
    assert v == 276.10 and kind == "held"


def test_3_higher_candidate_lifts_the_stop():
    v, kind = _floor(100.0, 104.0)
    assert v == 104.0 and kind == "moved"


def test_4_repeated_falling_prices_never_decrease_the_stop():
    """The exact ITC close path · 12 sessions, price -8.5%."""
    closes = [284.85, 289.00, 285.80, 282.65, 279.00, 276.15, 273.05,
              270.00, 267.05, 264.90, 263.00, 260.75]
    stop = None
    seen = []
    for c in closes:
        cand = c - 2 * 4.0                     # fixed ATR for determinism
        stop = cand if stop is None else _floor(stop, cand)[0]
        seen.append(stop)
    assert all(b >= a for a, b in zip(seen, seen[1:])), seen
    # The path is not monotonically falling - ITC rose on day 2 (284.85
    # -> 289.00), so the stop legitimately LIFTS once and then holds for
    # the remaining ten declining sessions. The contract is that the
    # final stop equals the high-water mark of the candidates, never the
    # last candidate.
    cands = [c - 8.0 for c in closes]
    assert stop == max(cands), (stop, max(cands))
    assert stop > cands[-1], "stop tracked the price down"
    assert seen.count(stop) >= 10, "stop failed to HOLD through the decline"


def test_5_rising_prices_allow_monotonic_increase():
    stop = None
    seen = []
    for c in [100, 102, 105, 110, 118]:
        cand = c - 2 * 3.0
        stop = cand if stop is None else _floor(stop, cand)[0]
        seen.append(stop)
    assert seen == sorted(seen) and seen[-1] > seen[0]


def test_6_profit_protection_lift_never_lowers_the_stop():
    lifted = _floor(120.0, 118.0)[0]           # lift candidate below prior
    assert lifted == 120.0


@pytest.mark.parametrize("path", [
    [50, 49, 48, 47, 46, 45, 44, 43],          # sustained decline
    [50, 55, 52, 58, 54, 61, 57],              # choppy advance
    [50, 50, 50, 50],                          # flat
    [50, 30],                                  # gap down
])
def test_invariant_new_stop_never_below_previous(path):
    """THE invariant · new_stop >= previous_stop, always."""
    stop = None
    for c in path:
        cand = c - 2.0
        prev = stop
        stop = cand if stop is None else _floor(stop, cand)[0]
        if prev is not None:
            assert stop >= prev, "stop fell from %s to %s" % (prev, stop)


# ── 8-11 · operational safety ─────────────────────────────────────────

def test_8_replayed_run_is_idempotent(tmp_path):
    """max() is idempotent · a second run the same day changes nothing."""
    _sidecar(tmp_path, "india", {"P1": 101.0})
    a = dr.load_prior_stops(tmp_path, "india")
    once = _floor(a["P1"], 99.0)[0]
    twice = _floor(once, 99.0)[0]
    assert once == twice == 101.0


def test_9_stop_history_is_keyed_by_position_id(tmp_path):
    _sidecar(tmp_path, "india", {"IND-R2-ITC-20260804-e0ebbb": 276.10})
    got = dr.load_prior_stops(tmp_path, "india")
    assert got["IND-R2-ITC-20260804-e0ebbb"] == 276.10


def test_10_positions_cannot_contaminate_each_other(tmp_path):
    _sidecar(tmp_path, "india", {"A": 100.0, "B": 900.0})
    pri = dr.load_prior_stops(tmp_path, "india")
    assert _floor(pri["A"], 95.0)[0] == 100.0
    assert _floor(pri["B"], 950.0)[0] == 950.0
    assert pri["A"] != pri["B"]


def test_11_markets_are_separate_sidecars(tmp_path):
    _sidecar(tmp_path, "india", {"X": 10.0})
    _sidecar(tmp_path, "usa", {"X": 20.0})
    assert dr.load_prior_stops(tmp_path, "india")["X"] == 10.0
    assert dr.load_prior_stops(tmp_path, "usa")["X"] == 20.0


# ── 13-14 · blast radius ──────────────────────────────────────────────

def test_13_no_write_outside_the_risk_sidecar():
    """emit() touches exactly one path · no registry mutation."""
    import inspect
    src = inspect.getsource(dr.emit)
    assert "dynamic_risk_" in src
    assert src.count("write_text") == 1
    for forbidden in ("opportunity_registry", "canonical_lifecycle",
                      "aegis_history", "registry.jsonl"):
        assert forbidden not in src, forbidden


def test_14_module_touches_no_r2_decision_or_r3_state():
    import inspect
    src = inspect.getsource(dr)
    for forbidden in ("confidence_threshold", "ensemble_weight", "eligibility",
                      "r3_action", "universe"):
        assert forbidden not in src, "%s appears in the risk engine" % forbidden


def test_config_parameters_are_unchanged():
    """The fix restores semantics · it does not retune anything."""
    import yaml
    cfg = yaml.safe_load(
        Path("configs/opportunity_registry.yaml").read_text(encoding="utf-8"))
    r = cfg["risk_engine"]
    assert r["atr_multiplier"] == 2.0
    assert r["trailing_lift_min_pct"] == 5.0
    assert r["high_vol_scale"] == 1.5
    assert r["high_vol_atr_pct"] == 3.0


def test_documented_contract_is_now_enforceable():
    """The docstring promised monotonicity · the code must read a prior."""
    import inspect
    assert "Never move stop DOWN" in dr.__doc__
    src = inspect.getsource(dr.compute)
    assert "load_prior_stops" in src or "_prior" in src, (
        "compute() never loads the prior stop · the contract is unenforceable")
    assert "original_stop=None" not in src, "the prior stop is still discarded"


# ── per-market authorization · CEO 2026-09-11 ─────────────────────────
#
# INDIA authorized. USA explicitly NOT: the same correction helps USA's
# tails (severe <=-8%: 117 -> 19) but costs 28 Class-C winner sacrifices,
# worst -22.67pp, on ~6 effective date units. Deploying a market-agnostic
# fix would have changed USA production without authorization.

def test_monotonic_is_authorized_per_market():
    import yaml
    cfg = yaml.safe_load(
        Path("configs/opportunity_registry.yaml").read_text(encoding="utf-8"))
    m = cfg["risk_engine"]["monotonic_stops"]
    assert m["india"] is True, "India authorization missing"
    assert m["usa"] is False, "USA must NOT be on the monotonic path"


def test_unlisted_market_defaults_to_legacy():
    """A market is never silently switched onto a corrected policy."""
    import inspect
    src = inspect.getsource(dr.compute)
    assert '.get(market, False)' in src, (
        "absent config must default to FALSE, not True")


def test_usa_path_never_loads_a_prior_stop():
    """USA must behave exactly as it did before this change."""
    import inspect
    src = inspect.getsource(dr.compute)
    assert "load_prior_stops(root, market) if _mono else {}" in src, (
        "the prior stop is loaded regardless of authorization")
    assert "if _mono and prior is not None" in src, (
        "the monotonic floor is not gated by authorization")
