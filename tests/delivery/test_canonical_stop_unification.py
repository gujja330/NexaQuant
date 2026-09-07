"""AEGIS · Delivery · CANONICAL R2 STOP UNIFICATION regression tests.

CEO 2026-09-07 · manual XLSX audit found `01_Investments` and `01_Portfolio`
reporting DIFFERENT stop states for the SAME position on the SAME day:

    BATAINDIA   Investments "EXIT · stop hit" @ 682.2286   Portfolio HOLD @ 642.7072
    CHAMBLFERT  Investments "EXIT · stop hit" @ 435.5929   Portfolio HOLD @ 403.0428
    ITC         Investments "EXIT · stop hit" @ 276.1      Portfolio HOLD @ 254.5

Root cause: `investments_sheet.build_investments_rows` hardcoded
`upstream_stop = None` in the ACTIVE loop, so `_stop_cell` always fell
through to `_stop_from_atr(entry_price, atr, k=2.0)` · a FRESH
ENTRY-ANCHORED stop · while `01_Portfolio` read the trailed stop from
`reports/context/dynamic_risk_{market}.json`. Two sources, two answers.

Directive:
> "That must become: dynamic_risk_v2 -> CANONICAL R2 STOP -> 01_Portfolio ->
>  01_Investments. For every R2 PID: Investments.stop == Portfolio.stop ==
>  dynamic_risk_v2.stop. Do not modify the risk engine itself."

These tests pin the CONSUMER contract. They must never be relaxed to make
a risk-engine change pass · the engine is out of scope by directive.
"""
import json
from pathlib import Path
from typing import Optional

import pytest

from backend.delivery.sheets.investments_sheet import _stop_cell, _stop_from_atr

ROOT = Path(__file__).resolve().parents[2]

# The three real contradictions from the CEO audit, pinned as fixtures.
FIXTURES = ("BATAINDIA", "CHAMBLFERT", "ITC")


def _stop_num(cell) -> Optional[float]:
    """Parse the numeric stop out of an Investments Dynamic Stop cell."""
    try:
        return float(str(cell).split(" ", 1)[0])
    except (TypeError, ValueError):
        return None


# -- Unit - _stop_cell honours the canonical stop ----------------------


def test_stop_cell_returns_canonical_stop_verbatim():
    """When dynamic_risk_v2 supplies a stop it is used AS-IS · never recomputed."""
    cell, prov = _stop_cell("R2", entry_price=700.0, atr=17.35,
                            has_dynamic_stop_upstream=True,
                            upstream_stop=642.7072,
                            require_canonical=True)
    assert prov == "dynamic_risk_v2"
    assert _stop_num(cell) == pytest.approx(642.7072)
    # And crucially NOT the entry-anchored ATR value it used to emit.
    assert _stop_num(cell) != pytest.approx(_stop_from_atr(700.0, 17.35, k=2.0))


def test_active_r2_without_canonical_stop_never_fabricates_atr():
    """An ACTIVE R2 row with no canonical stop must surface the gap.

    01_Portfolio shows "UNAVAILABLE · no canonical stop" -> Action REVIEW.
    01_Investments must not quietly invent an ATR number in its place ·
    that is precisely how the two sheets diverged.
    """
    cell, prov = _stop_cell("R2", entry_price=700.0, atr=17.35,
                            has_dynamic_stop_upstream=False,
                            upstream_stop=None,
                            require_canonical=True)
    assert prov == "missing_canonical_stop"
    assert cell.startswith("DATA_ERROR")
    assert _stop_num(cell) is None


def test_new_buy_rows_still_use_atr_initial_stop():
    """require_canonical=False path is unchanged · a NEW BUY has no trailed
    stop yet, so an ATR initial stop IS the correct answer there."""
    cell, prov = _stop_cell("R2", entry_price=700.0, atr=17.35,
                            has_dynamic_stop_upstream=False,
                            upstream_stop=None)
    assert prov == "atr14_fallback_k2"
    assert _stop_num(cell) == pytest.approx(_stop_from_atr(700.0, 17.35, k=2.0))


def test_r1_ignores_canonical_stop_and_stays_advisory():
    """R1 is RETIRED_ADVISORY · no dynamic-exit protection, ever.
    Even if a canonical stop were passed, R1 must render SUGGESTED."""
    cell, prov = _stop_cell("R1", entry_price=700.0, atr=17.35,
                            has_dynamic_stop_upstream=True,
                            upstream_stop=642.7072,
                            require_canonical=True)
    assert "SUGGESTED" in cell
    assert prov == "atr14_suggested_r1_no_auto_exit"
    assert _stop_num(cell) != pytest.approx(642.7072)


# -- Integration - both sheets read the same source --------------------


def test_investments_and_portfolio_share_one_stop_loader():
    """Both sheets must resolve stops through `_load_dynamic_risk`.

    A second loader (or an inline re-read) is how divergence returns.
    """
    import inspect
    from backend.delivery.sheets import investments_sheet

    src = inspect.getsource(investments_sheet.build_investments_rows)
    assert "_load_dynamic_risk" in src, (
        "01_Investments no longer loads the canonical dynamic_risk_v2 stop · "
        "this is the exact regression that produced the BATAINDIA/CHAMBLFERT/"
        "ITC contradictions."
    )
    # Scan CODE only · the comment above the fix legitimately quotes the
    # old line, and matching it would make this test self-defeating.
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "dr_by_pid.get(" in code, (
        "ACTIVE loop no longer looks the canonical stop up by opportunity_id."
    )
    assert "require_canonical=True" in code, (
        "ACTIVE R2 rows may fall back to a fabricated entry-anchored ATR "
        "stop again · canonical stop unification reverted."
    )


@pytest.mark.parametrize("market", ["india", "usa"])
def test_canonical_stop_equality_against_live_artifact(market):
    """Hard requirement · for every R2 PID with a canonical stop:

        Investments.stop == Portfolio.stop == dynamic_risk_v2.stop

    Skips when the canonical artifact has not been produced in this tree ·
    the missing-artifact condition is asserted by 00_Health, not here.
    """
    p = ROOT / "reports" / "context" / f"dynamic_risk_{market}.json"
    if not p.exists():
        pytest.skip("canonical artifact not present: %s" % p)
    from scripts.build_aegis_3sheet_workbook import _load_dynamic_risk

    raw = json.loads(p.read_text(encoding="utf-8"))
    loaded = _load_dynamic_risk(ROOT, market)
    checked = 0
    for u in (raw.get("updates") or []):
        pid = u.get("opportunity_id")
        stop = u.get("new_stop")
        if not pid or stop is None:
            continue
        # 1 · loader (used by 01_Portfolio) is faithful to the artifact
        assert loaded[pid]["stop"] == stop, "%s loader drift" % pid
        # 2 · Investments renders that same number, not a recomputed one
        cell, prov = _stop_cell("R2", entry_price=1.0, atr=99.0,
                                has_dynamic_stop_upstream=True,
                                upstream_stop=loaded[pid]["stop"],
                                require_canonical=True)
        assert prov == "dynamic_risk_v2"
        # 01_Portfolio writes round(stop, 4) · Investments must match exactly
        assert _stop_num(cell) == pytest.approx(round(float(stop), 4))
        checked += 1
    assert checked > 0, "no canonical %s stops to verify" % market


def test_audit_fixture_tickers_resolve_to_canonical_stops():
    """BATAINDIA · CHAMBLFERT · ITC specifically · the CEO-audit fixtures."""
    p = ROOT / "reports" / "context" / "dynamic_risk_india.json"
    if not p.exists():
        pytest.skip("canonical india artifact not present")
    raw = json.loads(p.read_text(encoding="utf-8"))
    by_ticker = {str(u.get("ticker", "")).upper().split(".", 1)[0]: u
                 for u in (raw.get("updates") or [])}
    for t in FIXTURES:
        if t not in by_ticker:
            pytest.skip("%s not currently ACTIVE · fixture unavailable" % t)
        u = by_ticker[t]
        cell, prov = _stop_cell("R2", entry_price=u.get("entry_price") or 1.0,
                                atr=1.0,
                                has_dynamic_stop_upstream=True,
                                upstream_stop=u["new_stop"],
                                require_canonical=True)
        assert prov == "dynamic_risk_v2", t
        assert _stop_num(cell) == pytest.approx(round(float(u["new_stop"]), 4)), t
