"""A gate must not recite last month's verdict as today's. CEO 2026-11-26.

WHAT WENT WRONG
---------------
USA stopped delivering and the certificate blamed price drift:

    DELIVERY_READY -> BLOCK
      [PI1] 2426 positions checked - 690 unexplained drift
      [PI2] 1316 exits checked - 320 drifted > 0.5%

None of it described that morning. Those exact strings came out of
reports/context/price_integrity_usa.json, a file whose own header said
asof 2026-10-28, generated 2026-10-28T03:36:29Z - twenty-nine days
before the run that quoted it.

It could never have been anything else. The producer,
check_price_integrity in the contract runner, was written
`if market == "india"`. The consumer, delivery_gate.decide, reads
price_integrity_<market>.json for whichever market it is handed and
blocks on PI1/PI2/PI5 FAIL. A market-GATED producer feeding a
market-BLIND consumer is a one-way door: on the last day anything wrote
USA's report it happened to be FAIL, and from then on every run copied
that fossil into its workspace, blocked on it, and left it exactly as
stale as it found it.

Measured on 2026-11-26 against that same run's own workspace:

    fossil  2426 positions - 690 unexplained - 1316 exits - 320 drifted
    actual   286 positions -   0 unexplained -  176 exits -   0 drifted
            -> PI1 PASS - PI2 PASS

The 2426 was not even the wrong answer to the right question. The
workbook held 286 rows; the fossil was measuring a 7247-row population
that no longer existed.

WHAT IS ASSERTED HERE
---------------------
That the producer is not gated to one market, and that a report older
than the run is refused rather than believed. Refused, not ignored: it
still blocks, because absent evidence must never read as ALLOW. What it
must not do is name PI1/PI2 and send the next operator hunting 690
drifts that stopped existing weeks ago.

Nothing here weakens the gate. A FRESH FAIL still blocks, under its own
code - that case is asserted too, because a "freshness fix" that quietly
stopped blocking real drift would be worse than the bug it replaced.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import backend.delivery.delivery_gate as DG

_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _ROOT / "backend" / "pipeline" / "contract" / "runner.py"


def _seed(root: Path, market: str, *, pig_asof: str, run_asof: str,
          pi1: str = "PASS", pi2: str = "PASS", pi5: str = "PASS") -> None:
    """A minimal context: a lifecycle that dates the run, and a report."""
    ctx = root / "reports" / "context"
    ctx.mkdir(parents=True, exist_ok=True)
    (ctx / ("canonical_lifecycle_%s.json" % market)).write_text(json.dumps({
        "schema_version": "test", "market": market, "asof": run_asof,
        "counts": {}, "current": [], "exits": [], "input_freshness": [],
    }), encoding="utf-8")
    (ctx / ("price_integrity_%s.json" % market)).write_text(json.dumps({
        "market": market, "asof": pig_asof, "verdict": "FAIL",
        "n_positions_checked": 2426, "n_exits_checked": 1316,
        "checks": [
            {"code": "PI1", "name": "Entry-price alignment", "status": pi1,
             "detail": "2426 positions checked - 690 unexplained drift"},
            {"code": "PI2", "name": "Exit-price alignment", "status": pi2,
             "detail": "1316 exits checked - 320 drifted > 0.5%"},
            {"code": "PI5", "name": "Freshness", "status": pi5,
             "detail": "511 active tickers - 11 stale"},
        ],
    }), encoding="utf-8")


# -----------------------------------------------------------------
# 1 - the producer is not gated to one market
# -----------------------------------------------------------------

class TestTheProducerRunsForEveryMarket:

    def test_check_price_integrity_is_not_inside_a_market_conditional(self):
        """The one-way door, closed at its hinge.

        Found by AST rather than by text: the call must not sit under any
        `if market == ...` branch, however that branch is spelled.
        """
        tree = ast.parse(_RUNNER.read_text(encoding="utf-8"))

        def calls_it(node) -> bool:
            return any(isinstance(n, ast.Call)
                       and isinstance(n.func, ast.Name)
                       and n.func.id == "check_price_integrity"
                       for n in ast.walk(node))

        gated = [n for n in ast.walk(tree)
                 if isinstance(n, ast.If)
                 and "market" in ast.dump(n.test)
                 and any(calls_it(b) for b in n.body)]
        assert not gated, (
            "check_price_integrity sits under a market conditional - a "
            "market-gated producer feeding a market-blind gate is how "
            "USA blocked on a 29-day-old verdict for four weeks")

    def test_it_is_still_actually_called(self):
        """Un-gating is worthless if the call were removed instead."""
        tree = ast.parse(_RUNNER.read_text(encoding="utf-8"))
        assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "check_price_integrity"
                   for n in ast.walk(tree))


# -----------------------------------------------------------------
# 2 - a report older than the run is refused, not believed
# -----------------------------------------------------------------

class TestAStaleReportIsRefused:

    def test_the_exact_usa_fossil_blocks_as_stale(self, tmp_path):
        """The measured 2026-11-26 failure, reproduced."""
        _seed(tmp_path, "usa", pig_asof="2026-10-28", run_asof="2026-11-26",
              pi1="FAIL", pi2="FAIL", pi5="FAIL")
        d = DG.decide(tmp_path, "usa")
        assert "PI:STALE" in d.blocking_codes
        assert d.verdict == "BLOCK"

    def test_a_stale_verdict_is_never_quoted(self, tmp_path):
        """The operator must not be sent after 690 vanished drifts."""
        _seed(tmp_path, "usa", pig_asof="2026-10-28", run_asof="2026-11-26",
              pi1="FAIL", pi2="FAIL", pi5="FAIL")
        d = DG.decide(tmp_path, "usa")
        assert "PI1" not in d.blocking_codes
        assert "PI2" not in d.blocking_codes
        assert "PI5" not in d.blocking_codes
        joined = " ".join(d.reasons)
        assert "690" not in joined and "2426" not in joined, (
            "a verdict about another month must not be restated as this "
            "run's reason - that is what cost four weeks")

    def test_the_reason_names_both_dates(self, tmp_path):
        """Enough to diagnose without opening a file."""
        _seed(tmp_path, "usa", pig_asof="2026-10-28", run_asof="2026-11-26",
              pi1="FAIL")
        reason = " ".join(r for r in DG.decide(tmp_path, "usa").reasons
                          if "PI:STALE" in r)
        assert "2026-10-28" in reason and "2026-11-26" in reason

    def test_stale_blocks_even_when_every_check_passed(self, tmp_path):
        """Staleness is not about the verdict - an old PASS is equally
        uninformative about today, and silence must not read as ALLOW."""
        _seed(tmp_path, "usa", pig_asof="2026-10-28", run_asof="2026-11-26")
        d = DG.decide(tmp_path, "usa")
        assert "PI:STALE" in d.blocking_codes
        assert d.verdict == "BLOCK"


# -----------------------------------------------------------------
# 3 - the gate keeps its teeth
# -----------------------------------------------------------------

class TestAFreshReportIsStillJudged:

    @pytest.mark.parametrize("code", ["PI1", "PI2", "PI5"])
    def test_a_fresh_fail_still_blocks_under_its_own_code(self, tmp_path,
                                                          code):
        """The thing that must survive a freshness fix."""
        kw = {"pi1": "PASS", "pi2": "PASS", "pi5": "PASS"}
        kw[code.lower()] = "FAIL"
        _seed(tmp_path, "usa", pig_asof="2026-11-26",
              run_asof="2026-11-26", **kw)
        d = DG.decide(tmp_path, "usa")
        assert code in d.blocking_codes
        assert "PI:STALE" not in d.blocking_codes
        assert d.verdict == "BLOCK"

    def test_a_fresh_all_pass_report_adds_no_price_blocker(self, tmp_path):
        """2026-11-26 USA, measured: PI1 PASS / PI2 PASS over 286 rows."""
        _seed(tmp_path, "usa", pig_asof="2026-11-26", run_asof="2026-11-26")
        d = DG.decide(tmp_path, "usa")
        for c in ("PI1", "PI2", "PI5", "PI:STALE"):
            assert c not in d.blocking_codes

    def test_a_report_ahead_of_the_run_is_not_called_stale(self, tmp_path):
        """A replay of an older day legitimately reads a newer report."""
        _seed(tmp_path, "usa", pig_asof="2026-11-26", run_asof="2026-11-24",
              pi1="FAIL")
        d = DG.decide(tmp_path, "usa")
        assert "PI:STALE" not in d.blocking_codes
        assert "PI1" in d.blocking_codes

    def test_india_is_unaffected(self, tmp_path):
        """India's producer always ran - its fresh path must not change."""
        _seed(tmp_path, "india", pig_asof="2026-11-26",
              run_asof="2026-11-26")
        d = DG.decide(tmp_path, "india")
        assert "PI:STALE" not in d.blocking_codes


# -----------------------------------------------------------------
# 4 - no reference date, no staleness claim
# -----------------------------------------------------------------

class TestItDoesNotInventAReferenceDate:

    def test_without_a_lifecycle_asof_no_stale_claim_is_made(self, tmp_path):
        """Guessing today() here would re-create the freshness-theatre
        class: a check that passes judgement without opening the data."""
        ctx = tmp_path / "reports" / "context"
        ctx.mkdir(parents=True, exist_ok=True)
        (ctx / "price_integrity_usa.json").write_text(json.dumps({
            "market": "usa", "asof": "2026-10-28",
            "checks": [{"code": "PI1", "name": "n", "status": "FAIL",
                        "detail": "d"}],
        }), encoding="utf-8")
        d = DG.decide(tmp_path, "usa")
        assert "PI:STALE" not in d.blocking_codes
        assert "PI1" in d.blocking_codes, (
            "with no reference date the report is all we have - it must "
            "still be judged, not waved through")

    def test_a_report_with_no_asof_is_not_called_stale(self, tmp_path):
        _seed(tmp_path, "usa", pig_asof="", run_asof="2026-11-26",
              pi1="FAIL")
        d = DG.decide(tmp_path, "usa")
        assert "PI:STALE" not in d.blocking_codes
        assert "PI1" in d.blocking_codes
