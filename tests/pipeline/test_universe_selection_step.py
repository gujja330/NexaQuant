"""The USA selection step, as wired into production.

Covers the ten cases the CEO listed for Phase C. The one that matters most
is `TestProductionCallPath` - before this step existed, both
`backend/universe/top_selection.py` and `backend/universe/risk_alerts.py`
had ZERO production callers, so every number measured from them described
code that never ran. These tests exercise the real entry point
(`scripts/ci_universe_selection.run`) and assert the workflow invokes it.

tmp_path-isolated throughout. Nothing reads or writes a live ledger,
registry, workbook or history.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.ci_universe_selection as step  # noqa: E402
from backend.universe import top_selection as T  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
ASOF = "2026-11-03"


def _snapshot(n, asof=ASOF, completeness_ok=True, sectors=None):
    rows = []
    for i in range(n):
        r = {
            "ticker": "T%04d" % i, "asof": asof,
            "sector": (sectors[i % len(sectors)] if sectors else "Unknown"),
            "close": 100.0 + i, "volume": 1_000_000 + i * 10,
            "return_20d_pct": float(n - i), "return_60d_pct": float(n - i),
            "adx_14": 25.0, "price_above_sma50": 1, "price_above_sma200": 1,
            "volatility_20d": 20.0, "max_drawdown_60d_pct": -5.0,
            "hist_ticker_win_rate": 50.0, "hist_ticker_n_trades": 5,
        }
        if not completeness_ok and i % 10 == 0:
            for c in ("return_20d_pct", "return_60d_pct", "adx_14",
                      "volatility_20d", "hist_ticker_win_rate", "close",
                      "volume", "max_drawdown_60d_pct",
                      "price_above_sma50", "price_above_sma200",
                      "hist_ticker_n_trades"):
                r[c] = None
        rows.append(r)
    return pd.DataFrame(rows)


def _repo(tmp_path, market="usa", n=520, target=248, enabled=True,
          held=(), asof=ASOF, recs=None, completeness_ok=True, sectors=None):
    """A minimal tree the step can run against."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "universe_selection.json").write_text(json.dumps({
        market: {"universe_selection_enabled": enabled,
                 "target_count": target,
                 "preserve_existing_universe": False,
                 "min_completeness": 0.60},
        "india": {"universe_selection_enabled": False,
                  "preserve_existing_universe": True,
                  "target_count": None},
    }), encoding="utf-8")

    sp = step.snapshot_path(tmp_path, market, asof)
    sp.parent.mkdir(parents=True, exist_ok=True)
    _snapshot(n, asof, completeness_ok, sectors).to_parquet(sp)

    rd = step.reports_dir(tmp_path, market)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "recommendations.json").write_text(json.dumps({
        "market": market, "asof": asof,
        "recommendations": recs if recs is not None else [],
    }), encoding="utf-8")

    if held:
        p = tmp_path / "reports" / "research" / "opportunity_registry.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps({
            "opportunity_id": "USA-R2-%s-20260801-x%02d" % (t, i),
            "market": market, "runner": "R2", "ticker": t,
            "created_date": "2026-08-01", "status": "ACTIVE",
            "initial_signal": "BUY", "last_seen_date": asof,
            "ts_utc": "2026-08-01T00:00:00+00:00",
        }) for i, t in enumerate(held)), encoding="utf-8")
    return tmp_path


# ───────────────────────────────── 1. exactly 248 ranked slots

class TestRankedSlotCount:
    def test_exactly_248_ranked_slots_when_enough_are_eligible(self, tmp_path):
        r = step.run(_repo(tmp_path, n=520), "usa", ASOF, write=False)
        assert r["state"] == step.STATE_APPLIED
        assert r["counts"]["ranked"] == 248
        assert r["target_ranked_slots"] == 248

    def test_248_is_slots_not_the_total(self, tmp_path):
        """The decision the CEO made explicitly."""
        held = tuple("T%04d" % i for i in range(400, 460))   # 60 held
        r = step.run(_repo(tmp_path, n=520, held=held), "usa", ASOF,
                     write=False)
        c = r["counts"]
        assert c["ranked"] == 248
        assert c["open_positions"] == 60
        assert c["selected_union"] == 308, "248 ranked + 60 held"
        assert c["selected_union"] > 248

    def test_fewer_eligible_than_the_target_takes_them_all(self, tmp_path):
        r = step.run(_repo(tmp_path, n=100), "usa", ASOF, write=False)
        assert r["counts"]["ranked"] <= 100
        assert r["counts"]["selected_union"] <= 100


# ───────────────────────────────── 2 + 3. open positions survive

class TestOpenPositionsSurvive:
    def test_every_open_position_is_selected(self, tmp_path):
        held = tuple("T%04d" % i for i in range(300, 380))
        r = step.run(_repo(tmp_path, n=520, held=held), "usa", ASOF,
                     write=False)
        sel = {T.bare_ticker(t) for t in r["selected_tickers"]}
        missing = [h for h in held if T.bare_ticker(h) not in sel]
        assert not missing, missing[:5]

    def test_a_held_name_outside_the_top_248_is_retained(self, tmp_path):
        """The snapshot ranks by descending return, so T0500 is near-last."""
        held = ("T0500", "T0510", "T0519")
        r = step.run(_repo(tmp_path, n=520, held=held), "usa", ASOF,
                     write=False)
        sel = {T.bare_ticker(t) for t in r["selected_tickers"]}
        for h in held:
            assert T.bare_ticker(h) in sel, "%s is held and must survive" % h
        assert r["counts"]["ranked"] == 248, "and it did not consume a slot"

    def test_held_count_is_reported_separately_from_ranked(self, tmp_path):
        held = tuple("T%04d" % i for i in range(500, 520))
        r = step.run(_repo(tmp_path, n=520, held=held), "usa", ASOF,
                     write=False)
        c = r["counts"]
        assert c["ranked"] + c["open_positions"] == c["selected_union"]


# ───────────────────────────────── 4. deterministic union

class TestDeterministicUnion:
    def test_two_runs_agree_exactly(self, tmp_path):
        held = ("T0500", "T0001")
        root = _repo(tmp_path, n=520, held=held)
        a = step.run(root, "usa", ASOF, write=False)
        b = step.run(root, "usa", ASOF, write=False)
        assert a["selected_tickers"] == b["selected_tickers"]
        assert a["counts"] == b["counts"]

    def test_the_union_has_no_duplicate_identities(self, tmp_path):
        held = tuple("T%04d" % i for i in range(0, 40))   # all inside top 248
        r = step.run(_repo(tmp_path, n=520, held=held), "usa", ASOF,
                     write=False)
        bares = [T.bare_ticker(t) for t in r["selected_tickers"]]
        assert len(bares) == len(set(bares))

    def test_a_held_name_already_ranked_is_not_counted_twice(self, tmp_path):
        held = ("T0000", "T0001", "T0002")       # top of the ranking
        r = step.run(_repo(tmp_path, n=520, held=held), "usa", ASOF,
                     write=False)
        c = r["counts"]
        assert c["selected_union"] == len(set(
            T.bare_ticker(t) for t in r["selected_tickers"]))


# ───────────────────────────────── 5. completeness exclusions hold

class TestCompletenessExclusions:
    def test_insufficient_completeness_names_stay_excluded(self, tmp_path):
        r = step.run(_repo(tmp_path, n=520, completeness_ok=False),
                     "usa", ASOF, write=False)
        reasons = r["exclusion_reasons"]
        assert reasons.get("INSUFFICIENT_DATA_COMPLETENESS", 0) == 52
        assert r["counts"]["eligible"] == 468

    def test_exclusion_reasons_are_recorded_not_just_counted(self, tmp_path):
        r = step.run(_repo(tmp_path, n=520, completeness_ok=False),
                     "usa", ASOF, write=False)
        assert set(r["exclusion_reasons"]) >= {"INSUFFICIENT_DATA_COMPLETENESS"}


# ───────────────────────────────── 6. India never invokes it

class TestIndiaIsUntouched:
    def test_the_step_refuses_india_outright(self, tmp_path):
        r = step.run(_repo(tmp_path, market="india", n=228), "india", ASOF,
                     write=False)
        assert r["state"] == step.STATE_REFUSED_MARKET
        assert r["exit"] == step.EXIT_REFUSED
        assert "unchanged by instruction" in r["reason"]

    def test_refusal_does_not_depend_on_the_config_flag(self, tmp_path):
        """Even a config that enables India is refused.

        `preserve_existing_universe` is one edit away from being wrong, so
        the market check is the guarantee and the config is not.
        """
        root = _repo(tmp_path, market="india", n=228)
        (root / "config" / "universe_selection.json").write_text(json.dumps({
            "india": {"universe_selection_enabled": True,
                      "target_count": 100,
                      "preserve_existing_universe": False}}), encoding="utf-8")
        r = step.run(root, "india", ASOF, write=False)
        assert r["state"] == step.STATE_REFUSED_MARKET

    def test_only_usa_is_allowed(self):
        assert step.ALLOWED_MARKETS == ("usa",)
        assert "india" not in step.ALLOWED_MARKETS

    def test_the_india_workflow_does_not_call_the_step(self):
        src = (_REPO / ".github/workflows/aegis-daily.yml").read_text(
            encoding="utf-8")
        assert "ci_universe_selection" not in src

    def test_refusing_writes_nothing(self, tmp_path):
        root = _repo(tmp_path, market="india", n=228)
        before = {p for p in root.rglob("*") if p.is_file()}
        step.run(root, "india", ASOF, write=True)
        assert {p for p in root.rglob("*") if p.is_file()} == before


# ───────────────────────────────── 7. research population untouched

class TestHistoricalPopulationUntouched:
    def test_the_step_never_imports_the_research_modules(self):
        import inspect
        src = inspect.getsource(step)
        for forbidden in ("priority_intelligence", "episode_dataset",
                          "outcome_resolver", "r3_program"):
            assert forbidden not in src, forbidden

    def test_the_registry_file_is_not_modified(self, tmp_path):
        held = ("T0500",)
        root = _repo(tmp_path, n=520, held=held)
        p = root / "reports" / "research" / "opportunity_registry.jsonl"
        before = p.read_bytes()
        step.run(root, "usa", ASOF, write=True)
        assert p.read_bytes() == before, "the registry is read-only here"

    def test_writes_land_only_under_reports_universe(self, tmp_path):
        root = _repo(tmp_path, n=520, held=("T0500",))
        before = {p for p in root.rglob("*") if p.is_file()}
        step.run(root, "usa", ASOF, write=True)
        new = {p for p in root.rglob("*") if p.is_file()} - before
        assert new, "the step must leave evidence"
        for p in new:
            assert "universe" in p.parts, p


# ───────────────────────────────── 8. risk alerts

class TestRiskAlerts:
    def test_an_excluded_sell_is_alerted(self, tmp_path):
        recs = [{"ticker": "T0519", "action": "SELL",
                 "calibrated_confidence": 0.5, "ensemble_score": -0.3}]
        r = step.run(_repo(tmp_path, n=520, recs=recs), "usa", ASOF,
                     write=False)
        assert "T0519" in r["risk_alerts"]["tickers"]
        assert r["coverage"]["SELL"]["coverage_pct"] == 0.0

    def test_a_selected_sell_is_not_alerted(self, tmp_path):
        recs = [{"ticker": "T0000", "action": "SELL"}]
        r = step.run(_repo(tmp_path, n=520, recs=recs), "usa", ASOF,
                     write=False)
        assert r["risk_alerts"]["n_alerts"] == 0
        assert r["coverage"]["SELL"]["coverage_pct"] == 100.0

    def test_coverage_is_reported_per_family(self, tmp_path):
        recs = ([{"ticker": "T%04d" % i, "action": "BUY"} for i in range(5)]
                + [{"ticker": "T051%d" % i, "action": "SELL"}
                   for i in range(4)])
        r = step.run(_repo(tmp_path, n=520, recs=recs), "usa", ASOF,
                     write=False)
        cov = r["coverage"]
        assert cov["BUY"]["coverage_pct"] == 100.0
        assert cov["SELL"]["coverage_pct"] == 0.0
        assert cov["ALL_ACTIONABLE"]["n"] == 9

    def test_a_held_but_excluded_sell_is_critical(self, tmp_path):
        """Should be impossible · it means the exemption failed."""
        recs = [{"ticker": "ZZZZ", "action": "SELL"}]
        r = step.run(_repo(tmp_path, n=520, recs=recs, held=("ZZZZ",)),
                     "usa", ASOF, write=False)
        # ZZZZ is not in the snapshot, so it cannot be selected, but it IS
        # held - exactly the condition that must be loud.
        assert r["risk_alerts"]["n_critical"] == 1

    def test_the_known_residual_is_carried(self, tmp_path):
        r = step.run(_repo(tmp_path, n=520), "usa", ASOF, write=False)
        assert r["risk_alerts"]["known_residual"] == ["AKAM", "DAL", "GPC"]


# ───────────────────────────────── 9. bad inputs fail safely

class TestBadInputsFailSafely:
    def test_a_missing_snapshot_reports_no_snapshot(self, tmp_path):
        root = _repo(tmp_path, n=10)
        step.snapshot_path(root, "usa", ASOF).unlink()
        r = step.run(root, "usa", ASOF, write=False)
        assert r["state"] == step.STATE_NO_SNAPSHOT
        assert r["exit"] == step.EXIT_NO_INPUT

    def test_yesterdays_snapshot_is_not_silently_used(self, tmp_path):
        """Freshness theatre · a snapshot for another date is not today's."""
        root = _repo(tmp_path, n=520, asof="2026-11-02")
        r = step.run(root, "usa", ASOF, write=False)
        assert r["state"] == step.STATE_NO_SNAPSHOT

    def test_an_empty_snapshot_reports_no_snapshot(self, tmp_path):
        root = _repo(tmp_path, n=10)
        pd.DataFrame().to_parquet(step.snapshot_path(root, "usa", ASOF))
        assert step.run(root, "usa", ASOF, write=False)["state"] == \
            step.STATE_NO_SNAPSHOT

    def test_a_malformed_snapshot_reports_no_snapshot(self, tmp_path):
        root = _repo(tmp_path, n=10)
        step.snapshot_path(root, "usa", ASOF).write_bytes(b"not a parquet")
        assert step.run(root, "usa", ASOF, write=False)["state"] == \
            step.STATE_NO_SNAPSHOT

    def test_missing_recommendations_do_not_crash_the_step(self, tmp_path):
        root = _repo(tmp_path, n=520)
        (step.reports_dir(root, "usa") / "recommendations.json").unlink()
        r = step.run(root, "usa", ASOF, write=False)
        assert r["state"] == step.STATE_APPLIED
        assert r["risk_alerts"]["n_alerts"] == 0
        assert r["coverage"]["ALL_ACTIONABLE"]["coverage_pct"] is None

    def test_malformed_recommendations_do_not_crash_the_step(self, tmp_path):
        root = _repo(tmp_path, n=520)
        (step.reports_dir(root, "usa") / "recommendations.json").write_text(
            "{not json", encoding="utf-8")
        assert step.run(root, "usa", ASOF, write=False)["state"] == \
            step.STATE_APPLIED

    def test_selection_disabled_is_a_clean_no_op(self, tmp_path):
        r = step.run(_repo(tmp_path, n=520, enabled=False), "usa", ASOF,
                     write=False)
        assert r["state"] == step.STATE_DISABLED
        assert r["exit"] == step.EXIT_OK


# ───────────────────────────────── 10. the real production call path

class TestProductionCallPath:
    def test_the_usa_workflow_invokes_the_step(self):
        """Before this, the selector had zero production callers."""
        src = (_REPO / ".github/workflows/aegis-usa.yml").read_text(
            encoding="utf-8")
        assert "python scripts/ci_universe_selection.py --market usa" in src

    def test_the_workflow_commits_the_selection_evidence(self):
        src = (_REPO / ".github/workflows/aegis-usa.yml").read_text(
            encoding="utf-8")
        assert "reports/universe/selection_applied_usa.json" in src
        assert "reports/universe/risk_alerts_usa_" in src

    def test_the_step_actually_calls_the_selector(self, tmp_path, monkeypatch):
        """Traced · not inferred from the output shape."""
        calls = []
        real = T.select

        def _spy(root, market, snapshot, asof, config=None):
            calls.append({"market": market, "asof": asof,
                          "rows": len(snapshot)})
            return real(root, market, snapshot, asof, config)

        monkeypatch.setattr(step._ts, "select", _spy)
        step.run(_repo(tmp_path, n=520), "usa", ASOF, write=False)
        assert len(calls) == 1
        assert calls[0] == {"market": "usa", "asof": ASOF, "rows": 520}

    def test_the_step_actually_calls_the_risk_alert_builder(self, tmp_path,
                                                            monkeypatch):
        from backend.universe import risk_alerts as RA
        calls = []
        real = RA.build

        def _spy(root, market, **kw):
            calls.append(market)
            return real(root, market, **kw)

        monkeypatch.setattr(step._ra, "build", _spy)
        step.run(_repo(tmp_path, n=520), "usa", ASOF, write=False)
        assert calls == ["usa"]

    def test_the_cli_runs_end_to_end_and_exits_zero(self, tmp_path):
        root = _repo(tmp_path, n=520, held=("T0500",))
        p = subprocess.run(
            [sys.executable, str(_REPO / "scripts" / "ci_universe_selection.py"),
             "--market", "usa", "--asof", ASOF, "--root", str(root),
             "--strict"],
            capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, p.stderr[-2000:]
        assert "APPLIED" in p.stdout
        assert "ranked 248" in p.stdout
        written = step.result_path(root, "usa")
        assert written.exists()
        rec = json.loads(written.read_text(encoding="utf-8"))
        assert rec["counts"]["ranked"] == 248

    def test_the_cli_exits_nonzero_for_a_refused_market(self, tmp_path):
        root = _repo(tmp_path, market="india", n=228)
        p = subprocess.run(
            [sys.executable, str(_REPO / "scripts" / "ci_universe_selection.py"),
             "--market", "india", "--asof", ASOF, "--root", str(root),
             "--strict"],
            capture_output=True, text=True, timeout=300)
        assert p.returncode == step.EXIT_REFUSED
        assert "REFUSED_MARKET" in p.stdout


# ───────────────────────────────── honest abstention reporting

class TestAbstentionIsReportedHonestly:
    def test_abstained_criteria_are_counted(self, tmp_path):
        r = step.run(_repo(tmp_path, n=520), "usa", ASOF, write=False)
        assert isinstance(r["abstention_counts"], dict)

    def test_an_absent_sector_is_not_invented(self, tmp_path):
        """Snapshot sector is 'Unknown' · it must not become a real sector."""
        r = step.run(_repo(tmp_path, n=520), "usa", ASOF, write=False)
        dist = r["sector_distribution"]
        assert set(dist) <= {"Unknown", "UNKNOWN", ""}, dist

    def test_a_real_sector_is_carried_through(self, tmp_path):
        r = step.run(_repo(tmp_path, n=520, sectors=["Tech", "Health"]),
                     "usa", ASOF, write=False)
        assert set(r["sector_distribution"]) == {"Tech", "Health"}

    def test_scoring_is_not_claimed_to_be_filtered(self, tmp_path):
        r = step.run(_repo(tmp_path, n=520), "usa", ASOF, write=False)
        assert "does not filter its input" in r["note"]
