"""Top-stock selection · point-in-time, deterministic, non-destructive.

Every test builds its own snapshot DataFrame and writes only into
tmp_path. None of them read the repository's feature store, registry or
ledgers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.universe import top_selection as ts  # noqa: E402

ASOF = "2026-11-03"


def _snap(n=20, *, market="usa", asof=ASOF, sectors=None, **over):
    rows = []
    for i in range(n):
        rows.append({
            "market": market, "ticker": "TK%02d" % i, "asof": asof,
            "sector": (sectors[i % len(sectors)] if sectors else "Unknown"),
            "close": 100.0 + i, "volume": 1_000_000 - i * 1000,
            "return_20d_pct": 10.0 - i * 0.5,
            "return_60d_pct": 20.0 - i * 0.7,
            "adx_14": 40.0 - i * 0.6,
            "price_above_sma50": 1.0, "price_above_sma200": 1.0,
            "volatility_20d": 1.0 + i * 0.1,
            "max_drawdown_60d_pct": -5.0 - i * 0.4,
            "hist_ticker_win_rate": 0.6, "hist_ticker_n_trades": 10.0,
        })
    df = pd.DataFrame(rows)
    for k, v in over.items():
        df[k] = v
    return df


def _cfg(**over):
    c = dict(ts.DEFAULTS["usa"])
    c.update(over)
    return c


# ── configurable candidate counts ───────────────────────────────────

@pytest.mark.parametrize("top_n,expect", [(None, 20), (10, 10), (5, 5)])
def test_candidate_count_is_configurable(tmp_path, top_n, expect):
    sel, a = ts.select(tmp_path, "usa", _snap(20), ASOF, _cfg(top_n=top_n))
    assert len(sel) == expect
    assert a["selected"] == expect
    assert a["universe_in"] == 20


def test_top_n_larger_than_the_universe_is_not_an_error(tmp_path):
    sel, a = ts.select(tmp_path, "usa", _snap(5), ASOF, _cfg(top_n=50))
    assert len(sel) == 5 and a["excluded"] == 0


def test_the_full_universe_remains_the_source_population(tmp_path):
    """A shortlist is a selection · nothing is deleted."""
    snap = _snap(20)
    sel, a = ts.select(tmp_path, "usa", snap, ASOF, _cfg(top_n=5))
    assert len(snap) == 20, "the input snapshot was mutated"
    assert a["universe_in"] == 20 and a["selected"] == 5
    assert a["exclusion_reasons"][ts.EXCL_RANK] == 15


# ── determinism ─────────────────────────────────────────────────────

def test_selection_is_deterministic(tmp_path):
    snap = _snap(30)
    a1 = ts.select(tmp_path, "usa", snap, ASOF, _cfg(top_n=10))[1]
    a2 = ts.select(tmp_path, "usa", snap, ASOF, _cfg(top_n=10))[1]
    assert a1["selected_tickers"] == a2["selected_tickers"]


def test_ties_break_on_ticker_not_input_order(tmp_path):
    """Identical features · the order must not depend on row order."""
    snap = _snap(6)
    for c in ("return_20d_pct", "return_60d_pct", "adx_14", "volatility_20d",
              "max_drawdown_60d_pct", "close", "volume"):
        snap[c] = 1.0
    fwd = ts.select(tmp_path, "usa", snap, ASOF, _cfg(top_n=3))[1]
    rev = ts.select(tmp_path, "usa", snap.iloc[::-1].reset_index(drop=True),
                    ASOF, _cfg(top_n=3))[1]
    assert fwd["selected_tickers"] == rev["selected_tickers"]
    assert fwd["selected_tickers"] == sorted(fwd["selected_tickers"])


# ── point-in-time ───────────────────────────────────────────────────

def test_a_row_for_another_date_is_excluded_as_stale(tmp_path):
    snap = _snap(5)
    snap.loc[0, "asof"] = "2026-10-01"
    sel, a = ts.select(tmp_path, "usa", snap, ASOF, _cfg())
    assert a["exclusion_reasons"][ts.EXCL_STALE] == 1
    assert "TK00" not in a["selected_tickers"]


def test_selection_reads_only_snapshot_columns(tmp_path):
    """No lookahead path exists · a future column is simply not consulted."""
    snap = _snap(10)
    snap["future_return_30d"] = [100.0] * 9 + [-100.0]   # a leak if used
    base = ts.select(tmp_path, "usa", _snap(10), ASOF, _cfg(top_n=3))[1]
    leaky = ts.select(tmp_path, "usa", snap, ASOF, _cfg(top_n=3))[1]
    assert base["selected_tickers"] == leaky["selected_tickers"]


def test_the_asof_is_recorded_on_the_audit(tmp_path):
    a = ts.select(tmp_path, "usa", _snap(3), ASOF, _cfg())[1]
    assert a["asof"] == ASOF
    assert a["selection_version"] == ts.SELECTION_VERSION


# ── liquidity, price and completeness ───────────────────────────────

def test_a_price_floor_excludes_and_records(tmp_path):
    snap = _snap(5)
    snap.loc[0, "close"] = 1.0
    a = ts.select(tmp_path, "usa", snap, ASOF, _cfg(min_price=50.0))[1]
    assert a["exclusion_reasons"][ts.EXCL_PRICE] == 1


def test_a_dollar_volume_floor_excludes_and_records(tmp_path):
    snap = _snap(5)
    snap.loc[0, "volume"] = 1.0
    a = ts.select(tmp_path, "usa", snap, ASOF,
                  _cfg(min_dollar_volume=1_000_000.0))[1]
    assert a["exclusion_reasons"][ts.EXCL_LIQUIDITY] == 1


def test_an_incomplete_row_is_excluded_with_its_reason(tmp_path):
    snap = _snap(5)
    for c in ("close", "volume", "return_20d_pct", "return_60d_pct",
              "adx_14", "volatility_20d", "max_drawdown_60d_pct",
              "hist_ticker_win_rate", "hist_ticker_n_trades"):
        snap.loc[0, c] = None
    a = ts.select(tmp_path, "usa", snap, ASOF, _cfg(min_completeness=0.6))[1]
    assert a["exclusion_reasons"][ts.EXCL_COMPLETENESS] == 1
    assert a["selected"] == 4


def test_a_duplicate_ticker_is_eliminated_once(tmp_path):
    snap = pd.concat([_snap(3), _snap(3).head(1)], ignore_index=True)
    a = ts.select(tmp_path, "usa", snap, ASOF, _cfg())[1]
    assert a["exclusion_reasons"][ts.EXCL_DUPLICATE] == 1
    assert len(a["selected_tickers"]) == len(set(a["selected_tickers"])) == 3


# ── missing data abstains · it never scores zero ────────────────────

def test_a_missing_criterion_abstains_rather_than_scoring_zero(tmp_path):
    """Scoring a gap as 0 is indistinguishable from scoring it as bad."""
    snap = _snap(6)
    snap["hist_ticker_win_rate"] = None
    snap["hist_ticker_n_trades"] = None
    sel, a = ts.select(tmp_path, "usa", snap, ASOF, _cfg())
    assert a["abstention_counts"]["evidence"] == len(sel)
    assert all("evidence" in e["abstained"] for e in a["selected_evidence"])
    # and the surviving criteria still produce a usable score
    assert all(e["selection_score"] is not None for e in a["selected_evidence"])


def test_abstention_does_not_penalise_the_ticker(tmp_path):
    """Two tickers, identical but one missing evidence · scores stay close."""
    snap = _snap(2)
    snap.loc[1, "hist_ticker_win_rate"] = None
    snap.loc[1, "hist_ticker_n_trades"] = None
    a = ts.select(tmp_path, "usa", snap, ASOF, _cfg())[1]
    by = {e["ticker"]: e for e in a["selected_evidence"]}
    assert by["TK01"]["components"]["evidence"] is None
    assert by["TK01"]["selection_score"] is not None


# ── sector concentration ────────────────────────────────────────────

def test_a_sector_cap_limits_concentration(tmp_path):
    snap = _snap(9, sectors=["Energy", "Tech", "Health"])
    a = ts.select(tmp_path, "usa", snap, ASOF, _cfg(max_per_sector=2))[1]
    assert a["selected"] == 6
    assert set(a["sector_distribution"].values()) == {2}
    assert a["exclusion_reasons"][ts.EXCL_SECTOR_CAP] == 3


def test_an_absent_sector_becomes_unknown_not_a_crash(tmp_path):
    """Measured reality · the snapshot's sector column is empty today."""
    snap = _snap(6)
    snap["sector"] = None
    a = ts.select(tmp_path, "usa", snap, ASOF, _cfg(max_per_sector=2))[1]
    assert a["sector_distribution"] == {"UNKNOWN": 2}
    assert a["selected"] == 2, (
        "with one undifferentiated sector a cap of 2 can only keep 2 · "
        "this is why the empty sector column matters")


# ── audit trail ─────────────────────────────────────────────────────

def test_the_audit_records_every_required_field(tmp_path):
    a = ts.select(tmp_path, "usa", _snap(8), ASOF, _cfg(top_n=4))[1]
    for k in ("market", "asof", "selection_version", "config", "weights",
              "universe_in", "eligible", "selected", "excluded",
              "exclusion_reasons", "sector_distribution",
              "data_completeness_mean", "abstention_counts",
              "selected_tickers", "selected_evidence", "selected_utc"):
        assert k in a, "audit is missing %s" % k
    ev = a["selected_evidence"][0]
    for k in ("ticker", "sector", "selection_score", "components",
              "abstained", "data_completeness"):
        assert k in ev
    assert set(ev["components"]) == set(ts.CRITERIA)


def test_the_audit_is_written_and_reloadable(tmp_path):
    a = ts.select(tmp_path, "usa", _snap(5), ASOF, _cfg(top_n=2))[1]
    p = ts.write_audit(tmp_path, "usa", ASOF, a)
    assert p.exists() and "selection_usa_2026-11-03.json" in p.name
    back = json.loads(p.read_text(encoding="utf-8"))
    assert back["selected"] == 2
    # written only under reports/universe
    for f in tmp_path.rglob("*.json"):
        assert "reports/universe" in f.as_posix()


def test_counts_reconcile(tmp_path):
    sel, a = ts.select(tmp_path, "usa", _snap(25), ASOF, _cfg(top_n=10))
    assert a["selected"] == len(sel)
    assert a["selected"] + a["excluded"] == a["universe_in"]
    assert sum(a["exclusion_reasons"].values()) == a["excluded"]


# ── India behaviour is preserved ────────────────────────────────────

def test_india_defaults_to_the_full_universe(tmp_path):
    """No silent shrinking of a market that currently works."""
    assert ts.DEFAULTS["india"]["top_n"] is None
    assert ts.DEFAULTS["usa"]["top_n"] is None
    snap = _snap(30, market="india")
    sel, a = ts.select(tmp_path, "india", snap, ASOF,
                       ts.load_config(tmp_path, "india"))
    assert len(sel) == 30 and a["excluded"] == 0


def test_config_file_overrides_defaults_per_market(tmp_path):
    p = tmp_path.joinpath(*ts.CONFIG_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"usa": {"top_n": 7}}), encoding="utf-8")
    assert ts.load_config(tmp_path, "usa")["top_n"] == 7
    assert ts.load_config(tmp_path, "india")["top_n"] is None


def test_a_malformed_config_does_not_resize_the_universe(tmp_path):
    p = tmp_path.joinpath(*ts.CONFIG_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    assert ts.load_config(tmp_path, "usa")["top_n"] is None


def test_both_markets_run_through_the_same_code_path(tmp_path):
    for m in ("india", "usa"):
        sel, a = ts.select(tmp_path, m, _snap(10, market=m), ASOF,
                           _cfg(top_n=4))
        assert a["market"] == m and len(sel) == 4


# ── 248 target · enabled/disabled semantics ─────────────────────────

def _cfg248(**over):
    c = dict(ts.DEFAULTS["usa"])
    c.update({"universe_selection_enabled": True, "target_count": 248})
    c.update(over)
    return c


def test_the_usa_target_is_248_ranked_slots(tmp_path):
    cfg = _cfg248(ignore_open_positions=True)
    sel, a = ts.select(tmp_path, "usa", _snap(300), ASOF, cfg)
    assert a["effective_top_n"] == 248
    assert a["target_count"] == 248
    assert len(sel) == 248
    assert a["selection_enabled"] is True


def test_fewer_eligible_than_the_target_processes_all(tmp_path):
    sel, a = ts.select(tmp_path, "usa", _snap(120), ASOF,
                       _cfg248(ignore_open_positions=True))
    assert len(sel) == 120
    assert a["exclusion_reasons"].get(ts.EXCL_RANK) is None


def test_more_eligible_than_the_target_selects_the_target(tmp_path):
    sel, a = ts.select(tmp_path, "usa", _snap(400), ASOF,
                       _cfg248(ignore_open_positions=True))
    assert len(sel) == 248
    assert a["exclusion_reasons"][ts.EXCL_RANK] == 152


def test_a_disabled_market_ignores_its_target_count(tmp_path):
    """A target sitting in config for a disabled market must be inert."""
    cfg = dict(ts.DEFAULTS["india"])
    cfg["target_count"] = 50           # present but selection is OFF
    assert ts.effective_top_n(cfg) is None
    sel, a = ts.select(tmp_path, "india", _snap(228, market="india"), ASOF, cfg)
    assert len(sel) == 228
    assert a["selection_enabled"] is False


def test_enabling_usa_cannot_shrink_india(tmp_path):
    """The explicit cross-market guarantee."""
    p = tmp_path.joinpath(*ts.CONFIG_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "usa": {"universe_selection_enabled": True, "target_count": 248},
        "india": {"universe_selection_enabled": False,
                  "preserve_existing_universe": True},
    }), encoding="utf-8")
    assert ts.effective_top_n(ts.load_config(tmp_path, "usa")) == 248
    assert ts.effective_top_n(ts.load_config(tmp_path, "india")) is None
    sel, a = ts.select(tmp_path, "india", _snap(228, market="india"), ASOF,
                       ts.load_config(tmp_path, "india"))
    assert len(sel) == 228, "India was resized by a USA setting"


def test_preserve_existing_universe_wins_over_a_stray_enable(tmp_path):
    cfg = dict(ts.DEFAULTS["india"])
    cfg["preserve_existing_universe"] = True
    cfg["top_n"] = 10                   # a stray experimental value
    assert ts.effective_top_n(cfg) is None


# ── open positions are never ranked out ─────────────────────────────

def _registry(root: Path, market: str, tickers, active=True):
    p = root / "reports" / "research" / "opportunity_registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"opportunity_id": "%s-R2-%s-1" % (market.upper(), t),
             "market": market, "runner": "R2", "ticker": t,
             "created_date": "2026-10-01",
             "status": "ACTIVE" if active else "CLOSED",
             "closed_date": "" if active else "2026-10-20",
             "ts_utc": "2026-10-01T12:00:00"} for t in tickers]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_a_held_name_survives_a_rank_cut(tmp_path):
    """A SELL candidate is a weak name · ranking it out unmonitors it."""
    _registry(tmp_path, "usa", ["TK19"])          # worst-ranked in _snap(20)
    sel, a = ts.select(tmp_path, "usa", _snap(20), ASOF,
                       _cfg(top_n=5, universe_selection_enabled=True,
                            target_count=5))
    assert "TK19" in a["selected_tickers"]
    assert a["kept_as_open_position"] == 1
    assert a["kept_by_rank"] == 5
    assert len(sel) == 6, "held names are a union, not a replacement"


def test_a_closed_position_gets_no_protection(tmp_path):
    _registry(tmp_path, "usa", ["TK19"], active=False)
    a = ts.select(tmp_path, "usa", _snap(20), ASOF,
                  _cfg(top_n=5, universe_selection_enabled=True,
                       target_count=5))[1]
    assert "TK19" not in a["selected_tickers"]
    assert a["kept_as_open_position"] == 0


def test_a_held_name_also_bypasses_the_sector_cap(tmp_path):
    _registry(tmp_path, "usa", ["TK08"])
    snap = _snap(9, sectors=["Energy", "Tech", "Health"])
    a = ts.select(tmp_path, "usa", snap, ASOF, _cfg(max_per_sector=1))[1]
    assert "TK08" in a["selected_tickers"]


def test_the_audit_says_why_each_name_was_kept(tmp_path):
    _registry(tmp_path, "usa", ["TK19"])
    a = ts.select(tmp_path, "usa", _snap(20), ASOF,
                  _cfg(top_n=3, universe_selection_enabled=True,
                       target_count=3))[1]
    by = {e["ticker"]: e["kept_because"] for e in a["selected_evidence"]}
    assert by["TK19"] == ts.KEEP_OPEN_POSITION
    assert by["TK00"] == ts.KEEP_RANK
    assert a["open_positions_in_market"] == 1


def test_an_unreadable_registry_does_not_crash_selection(tmp_path):
    p = tmp_path / "reports" / "research" / "opportunity_registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    sel, a = ts.select(tmp_path, "usa", _snap(10), ASOF, _cfg(top_n=4))
    assert len(sel) == 4 and a["open_positions_in_market"] == 0


def test_the_other_markets_positions_are_not_protected_here(tmp_path):
    _registry(tmp_path, "india", ["TK19"])
    a = ts.select(tmp_path, "usa", _snap(20), ASOF,
                  _cfg(top_n=5, universe_selection_enabled=True,
                       target_count=5))[1]
    assert "TK19" not in a["selected_tickers"]
    assert a["open_positions_in_market"] == 0


# ── the historical population is untouched ──────────────────────────

def test_selection_does_not_touch_the_registry(tmp_path):
    import hashlib
    _registry(tmp_path, "usa", ["TK01", "TK02"])
    p = tmp_path / "reports" / "research" / "opportunity_registry.jsonl"
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    ts.select(tmp_path, "usa", _snap(20), ASOF,
              _cfg(top_n=3, universe_selection_enabled=True, target_count=3))
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before, (
        "today's shortlist mutated the historical registry")


def test_a_suffixed_snapshot_ticker_still_matches_the_bare_registry(tmp_path):
    """The bug this guard was shipped with.

    India's snapshot carries AARTIIND.NS; the registry carries AARTIIND.
    Compared raw, the overlap is zero and open-position protection is
    silently inert for the one market we promised not to disturb.
    """
    _registry(tmp_path, "india", ["TK19"])          # bare, as the registry is
    snap = _snap(20, market="india")
    snap["ticker"] = snap["ticker"] + ".NS"         # suffixed, as the snapshot is
    a = ts.select(tmp_path, "india", snap, ASOF,
                  _cfg(top_n=5, universe_selection_enabled=True,
                       target_count=5))[1]
    assert a["open_positions_in_market"] == 1
    assert a["kept_as_open_position"] == 1, (
        "suffix mismatch made the protection inert")
    assert "TK19.NS" in a["selected_tickers"], "the original spelling is kept"
    by = {e["ticker"]: e["kept_because"] for e in a["selected_evidence"]}
    assert by["TK19.NS"] == ts.KEEP_OPEN_POSITION


@pytest.mark.parametrize("raw,want", [
    ("AARTIIND.NS", "AARTIIND"), ("sbin.ns", "SBIN"),
    ("RELIANCE.BO", "RELIANCE"), ("AAPL", "AAPL"), (" msft ", "MSFT"),
    (None, ""),
])
def test_bare_ticker_normalisation(raw, want):
    assert ts.bare_ticker(raw) == want
