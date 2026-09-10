"""A19 / A23 repair · sector propagation and historical lineage.

TWO DEFECTS, ONE ROOT CAUSE
----------------------------
The two-sheet contract renamed the exit sheet to "EXIT HISTORY". Three
consumers resolved that sheet by name from their own private alias lists,
none of which contained the new name. A19 therefore reported "Sector
column missing" and A23 reported hundreds of Registry-CLOSED tickers as
"silently lost". Neither was true, and the reconciliation proved it:
UNACCOUNTED_CLOSED was 0 in both markets.

Underneath the false alarm sat a real defect: no exit or current record
ever carried a sector at all, so A19 would have been correct for the wrong
reason. The fix propagates the canonical sector at the lifecycle layer.

These tests exist so a THIRD rename cannot reproduce either failure.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
from backend.delivery.sheets import workbook_two as w2
from backend.delivery.xlsx_contract import (EXIT_HISTORY_SHEET_ALIASES,
                                            resolve_exit_history_sheet,
                                            resolve_portfolio_sheet)

from conftest import lifecycle   # computes from SOURCE, never a committed artifact

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("india", "usa")


# ── the resolver · one list, every consumer ─────────────────────────────

def test_current_two_sheet_names_are_aliases():
    assert "EXIT HISTORY" in EXIT_HISTORY_SHEET_ALIASES
    from backend.delivery.xlsx_contract import PORTFOLIO_SHEET_ALIASES
    assert "CURRENT" in PORTFOLIO_SHEET_ALIASES


def test_resolver_finds_the_live_sheet_name():
    wb = Workbook()
    wb.remove(wb.active)
    wb.create_sheet("EXIT HISTORY")
    assert resolve_exit_history_sheet(wb) == "EXIT HISTORY"


def test_resolver_still_finds_legacy_names():
    for legacy in ("EXIT", "03_Exit_History", "Exit History (90d)"):
        wb = Workbook()
        wb.remove(wb.active)
        wb.create_sheet(legacy)
        assert resolve_exit_history_sheet(wb) == legacy


def test_resolver_returns_none_rather_than_guessing():
    wb = Workbook()
    wb.remove(wb.active)
    wb.create_sheet("Something Else")
    assert resolve_exit_history_sheet(wb) is None
    assert resolve_portfolio_sheet(wb) is None


def test_validators_do_not_keep_private_alias_lists():
    """The defect was three copies of one list. Keep it at one."""
    src = (ROOT / "backend" / "research" / "wave_regression.py").read_text(
        encoding="utf-8")
    assert 'for _cand in ("EXIT", "03_Exit_History"' not in src
    assert "resolve_exit_history_sheet" in src


# ── A19 · canonical sector reaches the rendered sheet ───────────────────

def test_lifecycle_attaches_sector_to_every_record():
    for m in MARKETS:
        d = lifecycle(m)
        if not d:
            pytest.skip("no lifecycle dataset for %s" % m)
        for key in ("current", "exits"):
            rows = d.get(key) or []
            assert rows, "%s/%s empty" % (m, key)
            for r in rows:
                assert "sector" in r, "%s/%s missing sector key" % (m, key)


def test_sector_is_never_blank_or_guessed():
    """Absence is stated, not left empty and not filled in."""
    for m in MARKETS:
        d = lifecycle(m)
        if not d:
            continue
        for r in (d.get("exits") or []):
            v = r.get("sector")
            assert v not in (None, ""), "blank sector for %s" % r.get("ticker")


def test_sector_comes_from_the_canonical_cache_only():
    """No second sector source · the renderer must not derive one."""
    src = (ROOT / "backend" / "delivery" / "sheets" / "workbook_two.py").read_text(
        encoding="utf-8")
    assert "_sector_lookup" not in src
    assert "yfinance" not in src
    assert 'e.get("sector")' in src


def test_canonical_sector_reaches_the_rendered_xlsx(tmp_path):
    """The full path the mandate names: canonical -> dataframe -> sheet."""
    for m in MARKETS:
        d = lifecycle(m)
        if not d:
            continue
        built = w2.build_two_sheet_workbook(ROOT, m, d.get("asof"))
        out = tmp_path / ("%s.xlsx" % m)
        built["workbook"].save(out)

        wb = load_workbook(out, read_only=True)
        name = resolve_exit_history_sheet(wb)
        assert name is not None, "no exit sheet in rendered workbook"
        ws = wb[name]
        hdr = [str(c.value).strip() if c.value else "" for c in ws[4]]
        assert "Sector" in hdr, "Sector column absent from rendered sheet"
        col = hdr.index("Sector") + 1

        # every body row carries the value the dataset carried
        want = {str(e["ticker"]).upper(): e["sector"] for e in d["exits"]}
        tcol = hdr.index("Ticker") + 1
        checked = 0
        for r in range(5, ws.max_row + 1):
            if ws.cell(r, 1).value in (None, ""):
                break
            tk = str(ws.cell(r, tcol).value or "").upper().strip()
            if tk in want:
                assert ws.cell(r, col).value == want[tk], (
                    "%s: rendered sector differs from canonical" % tk)
                checked += 1
        wb.close()
        assert checked > 0, "no rows verified for %s" % m


def test_a19_validates_the_rendered_sheet_not_the_dataframe():
    from backend.research.wave_regression import compute
    for m in MARKETS:
        rep = compute(ROOT, m, lifecycle(m).get("asof"))
        a19 = [c for c in rep.checks if c["code"] == "A19"]
        assert a19 and a19[0]["status"] == "PASS", a19


def test_a19_distinguishes_missing_sheet_from_missing_column():
    src = (ROOT / "backend" / "research" / "wave_regression.py").read_text(
        encoding="utf-8")
    assert "no Exit History sheet found" in src


# ── A23 · zero silent loss, proved mechanically ─────────────────────────

def _closed_registry(market: str) -> set:
    from backend.delivery.canonical.retirement import retired_runners
    from backend.research import opportunity_registry as oreg
    from scripts.build_aegis_3sheet_workbook import (_close_on_or_before,
                                                     _is_administrative_exit)
    reg, retired, out = oreg.load_all(ROOT), retired_runners(ROOT), set()
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market or o.status != "CLOSED":
                continue
            if o.runner in retired:
                continue
            ep = _close_on_or_before(ROOT, o.ticker, market, o.created_date or "")
            xp = _close_on_or_before(ROOT, o.ticker, market, o.closed_date or "")
            if _is_administrative_exit(o, ep, xp):
                continue
            out.add(o.ticker.upper())
    return out


def _exit_history_tickers(market: str) -> set:
    p = ROOT / "reports" / "telegram" / ("aegis_history_%s.xlsx" % market)
    if not p.exists():
        return set()
    wb = load_workbook(p, read_only=False, data_only=False)
    name = resolve_exit_history_sheet(wb)
    if name is None:
        wb.close()
        return set()
    ws = wb[name]
    hdr = [str(ws.cell(4, c).value or "").strip()
           for c in range(1, ws.max_column + 1)]
    tcol = (hdr.index("Ticker") + 1) if "Ticker" in hdr else 2
    out = set()
    for r in range(5, ws.max_row + 1):
        if ws.cell(r, 1).value in (None, ""):
            break
        v = ws.cell(r, tcol).value
        if v:
            out.add(str(v).upper().strip())
    wb.close()
    return out


def _orphan_audit_tickers(market: str) -> set:
    p = ROOT / "reports" / "delivery" / ("orphan_audit_%s.jsonl" % market)
    if not p.exists():
        return set()
    out = set()
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.strip():
            try:
                t = str(json.loads(ln).get("ticker", "")).upper()
                if t:
                    out.add(t)
            except Exception:
                pass
    return out


@pytest.mark.parametrize("market", MARKETS)
def test_unaccounted_closed_is_empty(market):
    """REGISTRY_CLOSED - EXIT_HISTORY - ORPHAN_AUDIT == empty."""
    unaccounted = (_closed_registry(market)
                   - _exit_history_tickers(market)
                   - _orphan_audit_tickers(market))
    assert not unaccounted, (
        "%d Registry-CLOSED tickers unaccounted for in %s: %s"
        % (len(unaccounted), market, sorted(unaccounted)[:10]))


@pytest.mark.parametrize("market", MARKETS)
def test_no_exit_history_row_is_fabricated(market):
    from backend.research import opportunity_registry as oreg
    known = {o.ticker.upper() for opps in oreg.load_all(ROOT).values()
             for o in opps if o.market.lower() == market}
    fabricated = _exit_history_tickers(market) - known
    assert not fabricated, "rows with no registry lineage: %s" % sorted(fabricated)[:8]


def test_the_reported_missing_usa_tickers_are_present():
    """ADBE/AJG/BLDR/CL/CRM were phantom · they were always tracked."""
    tracked = _exit_history_tickers("usa") | _orphan_audit_tickers("usa")
    for t in ("ADBE", "AJG", "BLDR", "CL", "CRM"):
        assert t in tracked, "%s genuinely untracked" % t


def test_a23_refuses_to_call_a_missing_sheet_a_silent_loss():
    src = (ROOT / "backend" / "research" / "wave_regression.py").read_text(
        encoding="utf-8")
    assert "refusing to report" in src
    # ...but an EMPTY sheet is still real silent loss. The guard must key
    # on sheet ABSENCE, never on "no rows found" - conflating those in
    # this direction would hide genuine lineage loss behind the fix for
    # the phantom one.
    assert "_eh_sheet_missing and _closed_reg" in src


@pytest.mark.parametrize("market", MARKETS)
def test_a23_passes(market):
    from backend.research.wave_regression import compute
    rep = compute(ROOT, market, lifecycle(market).get("asof"))
    a23 = [c for c in rep.checks if c["code"] == "A23"]
    assert a23 and a23[0]["status"] == "PASS", a23


# ── the gate itself ─────────────────────────────────────────────────────

@pytest.mark.parametrize("market", MARKETS)
def test_delivery_gate_allows_without_override(market):
    from backend.delivery import delivery_gate as dg
    d = dg.decide(ROOT, market)
    assert d.verdict == "ALLOW", d.reasons[:3]
    assert d.override_used is False


def test_two_sheet_contract_still_holds(tmp_path):
    """Asserted on a freshly built workbook.

    Reading the shipped artifact here races the daily sender, which
    legitimately rewrites it mid-run; a flaky delivery test is worse than
    no test because it trains people to ignore it. The contract is a
    property of the BUILDER, so build one and check that.
    """
    for m in MARKETS:
        d = lifecycle(m)
        if not d:
            continue
        built = w2.build_two_sheet_workbook(ROOT, m, d.get("asof"))
        assert built["sheets"] == ["CURRENT", "EXIT HISTORY"], built["sheets"]
        out = tmp_path / ("%s.xlsx" % m)
        built["workbook"].save(out)
        wb = load_workbook(out, read_only=True)
        assert wb.sheetnames == ["CURRENT", "EXIT HISTORY"], wb.sheetnames
        wb.close()


# ── exit populations must never be summed together ────────────────────
#
# The 2026-09-10 lock audit found 463 USA rows carrying
# `source = registry:production` whose reason was "Auto-close · orphaned
# position", 489 of 490 with a NON-ZERO realized P&L. The banner
# presented 517 rows as realized production exits; the genuine count was
# 18. `source` says where a record came from; `record_type` says what it
# is, and only the second is safe to build a performance statistic on.

def test_orphan_auto_close_is_not_a_realized_exit():
    from backend.delivery.lifecycle.canonical_daily_lifecycle import (
        RT_ORPHAN, RT_REALIZED, _record_type)
    assert _record_type("registry:production",
                        "ORPHAN_AUTO_CLOSE") == RT_ORPHAN
    assert _record_type("registry:production",
                        "Rotation swap") == RT_REALIZED


def test_every_population_is_classified_distinctly():
    from backend.delivery.lifecycle.canonical_daily_lifecycle import (
        BREACH_SOURCE, RT_ADMIN, RT_ADVISORY, RT_BREACH, _record_type)
    assert _record_type(BREACH_SOURCE, "Stop breached") == RT_BREACH
    assert _record_type("registry:administrative", "x") == RT_ADMIN
    assert _record_type("registry:advisory", "x") == RT_ADVISORY
    # A breach mark stays a mark even when its reason mentions an orphan.
    assert _record_type(BREACH_SOURCE, "ORPHAN_AUTO_CLOSE") == RT_BREACH


@pytest.mark.parametrize("market", MARKETS)
def test_realized_population_excludes_reconstructions(market):
    """No orphan, admin or breach record may carry REALIZED EXIT."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lifecycle(market)
    if not d:
        pytest.skip("no lifecycle dataset for %s" % market)
    rows = d.get("exits") or []
    if not rows:
        pytest.skip("no exits")
    assert all(e.get("record_type") for e in rows), "unclassified exit row"
    bad = [e["ticker"] for e in rows
           if e.get("record_type") == "REALIZED EXIT"
           and ("orphan" in str(e.get("exit_reason", "")).lower()
                or e.get("source") == "lifecycle:stop-breach"
                or e.get("source") == "registry:administrative")]
    assert not bad, "reconstructions counted as realized: %s" % bad[:6]


@pytest.mark.parametrize("market", MARKETS)
def test_populations_sum_to_the_sheet(market):
    """Every row belongs to exactly one population · nothing double-counted."""
    from collections import Counter
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lifecycle(market)
    if not d:
        pytest.skip("no lifecycle dataset for %s" % market)
    rows = d.get("exits") or []
    if not rows:
        pytest.skip("no exits")
    assert sum(Counter(e["record_type"] for e in rows).values()) == len(rows)


@pytest.mark.parametrize("market", MARKETS)
def test_exit_sheet_never_claims_every_closed_position(market):
    """Coverage is partial and must say so."""
    p = ROOT / "reports" / "telegram" / ("aegis_history_%s.xlsx" % market)
    if not p.exists():
        pytest.skip("workbook missing")
    wb = load_workbook(p, read_only=True)
    name = resolve_exit_history_sheet(wb)
    if name is None:
        wb.close()
        pytest.skip("no exit sheet")
    ws = wb[name]
    banner = " ".join(str(ws.cell(r, 1).value or "") for r in (1, 2, 3))
    hdr = [str(ws.cell(4, c).value or "").strip()
           for c in range(1, ws.max_column + 1)]
    wb.close()
    assert "every closed position" not in banner.lower(), (
        "the sheet claims complete history it does not have")
    assert "coverage begins" in banner.lower(), (
        "historical coverage start is not stated")
    assert "Record Type" in hdr, "populations are not separable by a reader"
    assert "Realized P&L %" not in hdr, (
        "a column header claims 'realized' for rows that are marks")


@pytest.mark.parametrize("market", MARKETS)
def test_legend_does_not_restate_the_removed_overclaim(market):
    """A legend is read as authoritative.

    The banner's "every closed position" was corrected while the LEGEND
    kept saying "Permanent record of every closed ... position", and kept
    naming a "Realized P&L %" column that no longer exists.
    """
    p = ROOT / "reports" / "telegram" / ("aegis_history_%s.xlsx" % market)
    if not p.exists():
        pytest.skip("workbook missing")
    wb = load_workbook(p, read_only=True)
    name = resolve_exit_history_sheet(wb)
    if name is None:
        wb.close()
        pytest.skip("no exit sheet")
    ws = wb[name]
    text = " ".join(str(ws.cell(r, 1).value or "")
                    for r in range(1, ws.max_row + 1)).lower()
    hdr = [str(ws.cell(4, c).value or "").strip()
           for c in range(1, ws.max_column + 1)]
    wb.close()
    assert "every closed" not in text, "the legend restates the overclaim"
    assert "realized p&l %" not in text, (
        "the legend names a column that no longer exists")
    assert "coverage begins" in text
    assert "Record Type" in hdr
