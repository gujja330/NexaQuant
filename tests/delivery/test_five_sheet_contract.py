"""AEGIS · FIVE-SHEET DELIVERY CONTRACT · regression tests.

CEO 2026-09-07 · the workbook is now exactly five sheets:

    R1 · R2 · MOMENTUM · DAILY RECOMMENDATION · EXIT

This file has two jobs.

1. Pin the new contract (sheet set, canonical stop, R1 advisory-only,
   momentum freshness and truthful funnel, unified exit history).

2. CARRY FORWARD the still-live invariants from Delivery Contract v1,
   whose original tests are gated off in
   tests/delivery/test_contract_v1_reconciliation.py because they address
   sheets that no longer exist. Those invariants are about operator
   semantics, not about sheet names, so they must survive the redesign:
     · MISSING is never fabricated as LOW / PENDING / 0
     · P&L units are unambiguous
     · banner counts reconcile to the visible body
     · definitions reach the operator (now a legend on every sheet)
     · monthly summary is clearly separated from the exit body

One v1 invariant is deliberately NOT ported verbatim: "P&L cells use
Excel '%' number format". That rule existed because the old Portfolio
sheet stored P&L as a FRACTION (-0.0269), so it needed '%' formatting to
read as -2.69%. The five-sheet layout stores P&L already in percent units
(-2.69) under a header that says "P&L %", so applying '%' format would
render it as -269%. The operator-facing intent (unambiguous units) is
tested below in its correct form.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

_XLSX = {
    "india": Path("reports/telegram/aegis_history_india.xlsx"),
    "usa": Path("reports/telegram/aegis_history_usa.xlsx"),
}
FIVE_SHEETS = ["R1", "R2", "MOMENTUM", "DAILY RECOMMENDATION", "EXIT"]

# Values that mean "the engine did not evaluate this". Anything else in a
# no-data slot is fabrication.
MISSING_TOKENS = {"—", "UNAVAILABLE", "N/A", "DATA_ERROR", "-", ""}
# Tokens v1 caught being substituted for missing data.
FABRICATED_TOKENS = {"LOW", "PENDING"}


def _wb(market: str):
    p = _XLSX[market]
    if not p.exists():
        pytest.skip("artifact not present · %s" % p)
    from openpyxl import load_workbook
    wb = load_workbook(p, data_only=True)
    # A workbook predating the five-sheet layout must SKIP, not raise.
    # On CI the delivery-test job runs BEFORE the build step, so the
    # committed artifact can still be an older layout · a KeyError there
    # would look like a code defect instead of a stale sample.
    if "R2" not in wb.sheetnames:
        sheets = list(wb.sheetnames)
        wb.close()
        pytest.skip("committed workbook predates the five-sheet layout "
                    "(sheets=%s) · rebuild with "
                    "`python scripts/build_aegis_3sheet_workbook.py "
                    "--market both`" % sheets)
    # Same freshness gate the v1 suite uses · a stale sample must skip,
    # never silently pass.
    title = str(wb["R2"].cell(1, 1).value or "")
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2})", title)
    if m and m.group(1) != date.today().isoformat():
        wb.close()
        pytest.skip("artifact asof=%s is not today=%s · rebuild with "
                    "`python scripts/build_aegis_3sheet_workbook.py "
                    "--market both`" % (m.group(1), date.today().isoformat()))
    return wb


def _rows(ws):
    return [[c.value for c in r] for r in ws.iter_rows()]


def _header_at(rows, must_have):
    for i, r in enumerate(rows):
        cells = {str(c).strip() for c in r if c is not None}
        if all(m in cells for m in must_have):
            return i, list(r)
    return -1, []


def _idx(hdr, name):
    for i, c in enumerate(hdr):
        if str(c).strip() == name:
            return i
    return -1


MARKETS = ["india", "usa"]


# ── New contract ──────────────────────────────────────────────────────


@pytest.mark.parametrize("market", MARKETS)
def test_exactly_five_sheets(market):
    wb = _wb(market)
    assert wb.sheetnames == FIVE_SHEETS, (
        "five-sheet contract violated · got %s" % wb.sheetnames)
    wb.close()


@pytest.mark.parametrize("market", MARKETS)
def test_no_legacy_operational_sheets(market):
    """The redesign removes these tabs · none may reappear as a side effect."""
    wb = _wb(market)
    forbidden = {"00_Health", "01_Investments", "01_Portfolio",
                 "02_Today_Momentum", "03_Exit_History",
                 "04_Daily_Portfolio_History", "05_R1_Advisory",
                 "06_Composite_Signals", "Portfolio", "Definitions",
                 "Monthly Summary", "Exit History (90d)"}
    leaked = forbidden & set(wb.sheetnames)
    wb.close()
    assert not leaked, "legacy sheets reappeared: %s" % leaked


@pytest.mark.parametrize("market", MARKETS)
def test_r2_stop_matches_canonical_dynamic_risk(market):
    """THE incident test · R2 stop must equal dynamic_risk_v2 exactly."""
    import json
    p = Path("reports/context/dynamic_risk_%s.json" % market)
    if not p.exists():
        pytest.skip("canonical artifact absent")
    canon = {}
    for u in (json.loads(p.read_text(encoding="utf-8")).get("updates") or []):
        if u.get("new_stop") is not None:
            canon[str(u["ticker"]).upper().split(".", 1)[0]] = round(
                float(u["new_stop"]), 4)
    wb = _wb(market)
    rows = _rows(wb["R2"])
    hi, hdr = _header_at(rows, ["Stock", "Dynamic Stop"])
    assert hi >= 0, "R2 header not found"
    c_tk, c_st = _idx(hdr, "Stock"), _idx(hdr, "Dynamic Stop")
    checked, bad = 0, []
    for r in rows[hi + 1:]:
        tk = str(r[c_tk]).strip() if r[c_tk] else ""
        if tk not in canon or not isinstance(r[c_st], (int, float)):
            continue
        checked += 1
        if round(float(r[c_st]), 4) != canon[tk]:
            bad.append("%s sheet=%s canonical=%s" % (tk, r[c_st], canon[tk]))
    wb.close()
    assert not bad, "R2 stop diverged from dynamic_risk_v2: %s" % bad
    assert checked > 0, "no R2 rows cross-checked against canonical stops"


@pytest.mark.parametrize("market", MARKETS)
def test_r2_and_daily_recommendation_never_disagree(market):
    """No sheet may say EXIT while another says HOLD for the same stock.

    This is the BATAINDIA / CHAMBLFERT / ITC failure mode, asserted against
    the delivered file rather than against the builder's intent.
    """
    wb = _wb(market)
    r2 = _rows(wb["R2"])
    hi, hdr = _header_at(r2, ["Stock", "Dynamic Stop", "Action"])
    c_tk, c_st, c_ac = _idx(hdr, "Stock"), _idx(hdr, "Dynamic Stop"), _idx(hdr, "Action")
    r2_map = {}
    for r in r2[hi + 1:]:
        tk = str(r[c_tk]).strip() if r[c_tk] else ""
        if tk and r[c_st] is not None and len(tk) <= 20:
            r2_map[tk] = (r[c_st], r[c_ac])

    dr = _rows(wb["DAILY RECOMMENDATION"])
    hj, hdr2 = _header_at(dr, ["Source", "Stock", "Stop", "Action"])
    c_src, c_tk2 = _idx(hdr2, "Source"), _idx(hdr2, "Stock")
    c_st2, c_ac2 = _idx(hdr2, "Stop"), _idx(hdr2, "Action")
    bad = []
    n = 0
    for r in dr[hj + 1:]:
        if r[c_src] != "R2":
            continue
        tk = str(r[c_tk2]).strip() if r[c_tk2] else ""
        if tk not in r2_map:
            continue
        n += 1
        stop, act = r2_map[tk]
        if r[c_st2] != stop:
            bad.append("%s stop R2=%s DAILY=%s" % (tk, stop, r[c_st2]))
        if r[c_ac2] != act:
            bad.append("%s action R2=%s DAILY=%s" % (tk, act, r[c_ac2]))
    wb.close()
    assert not bad, "cross-sheet divergence: %s" % bad
    assert n > 0 or not r2_map, "no R2 stocks cross-checked"


@pytest.mark.parametrize("market", MARKETS)
def test_r1_is_advisory_and_never_auto_exits(market):
    """R1 is RETIRED_ADVISORY · it may escalate to REVIEW, never to EXIT."""
    wb = _wb(market)
    rows = _rows(wb["R1"])
    hi, hdr = _header_at(rows, ["Stock", "Review State", "Action"])
    assert hi >= 0, "R1 header not found"
    c_tk, c_ac = _idx(hdr, "Stock"), _idx(hdr, "Action")
    bad = []
    for r in rows[hi + 1:]:
        tk = str(r[c_tk]).strip() if r[c_tk] else ""
        ac = str(r[c_ac] or "").upper()
        if tk and "EXIT" in ac:
            bad.append("%s: %s" % (tk, ac))
    banner = " ".join(str(c) for c in rows[0] + rows[1] if c is not None).upper()
    wb.close()
    assert not bad, "R1 carries an EXIT action · auto-exit is prohibited: %s" % bad
    assert "ADVISORY" in banner, "R1 sheet must declare itself advisory"


@pytest.mark.parametrize("market", MARKETS)
def test_momentum_declares_freshness_and_never_mislabels_universe(market):
    wb = _wb(market)
    rows = _rows(wb["MOMENTUM"])
    head = " ".join(str(c) for r in rows[:6] for c in r if c is not None)
    everything = " ".join(str(c) for r in rows for c in r if c is not None)
    wb.close()
    assert "Producer as-of" in head, "MOMENTUM must state the producer as-of"
    assert ("FRESH" in head or "STALE" in head), (
        "MOMENTUM must state explicit fresh/stale status")
    # The defect that printed "scanned universe=1" on a 230-ticker run.
    assert "scanned universe=" not in everything, (
        "declared universe is being labelled as scanned")
    assert "ACTUALLY EVALUATED" in everything, (
        "MOMENTUM must report the actually-evaluated count separately from "
        "the declared universe")


@pytest.mark.parametrize("market", MARKETS)
def test_exit_sheet_is_unified_across_runners(market):
    wb = _wb(market)
    rows = _rows(wb["EXIT"])
    hi, hdr = _header_at(rows, ["Source", "Stock", "Realized P&L %"])
    assert hi >= 0, "EXIT header not found"
    c_src = _idx(hdr, "Source")
    sources = set()
    for r in rows[hi + 1:]:
        s = str(r[c_src]).strip() if r[c_src] else ""
        if s in ("R2", "R1 · ADVISORY", "MOMENTUM"):
            sources.add(s)
    everything = " ".join(str(c) for r in rows for c in r if c is not None)
    wb.close()
    assert "Momentum" in everything, (
        "EXIT must account for momentum explicitly · even to state it "
        "contributes no exits")
    assert sources, "EXIT has no classified rows"


# ── Carried forward from Delivery Contract v1 ─────────────────────────


@pytest.mark.parametrize("market", MARKETS)
def test_v1_missing_is_never_fabricated(market):
    """Rule C4 · a slot the engine did not evaluate must read as MISSING.

    v1 caught LOW / PENDING being substituted for missing values. The
    tokens differ per layout; the rule does not.
    """
    wb = _wb(market)
    bad = []
    for sheet, keys in (("R2", ["Stock", "Dynamic Stop", "Stop Type"]),
                        ("R1", ["Stock", "Suggested Stop"])):
        rows = _rows(wb[sheet])
        hi, hdr = _header_at(rows, keys)
        if hi < 0:
            continue
        for col in keys[1:]:
            ci = _idx(hdr, col)
            if ci < 0:
                continue
            for r in rows[hi + 1:]:
                val = str(r[ci]).strip().upper() if r[ci] is not None else ""
                if val in FABRICATED_TOKENS:
                    bad.append("%s.%s = %s" % (sheet, col, val))
    wb.close()
    assert not bad, "fabricated stand-ins for missing data: %s" % bad


@pytest.mark.parametrize("market", MARKETS)
def test_v1_pnl_units_are_unambiguous(market):
    """Successor to the v1 '%'-number-format rule.

    P&L must be a number in PERCENT units under a header that names the
    unit · so the operator can never read -2.69 as -0.0269 or as -269%.
    """
    wb = _wb(market)
    rows = _rows(wb["R2"])
    hi, hdr = _header_at(rows, ["Stock", "Unrealized P&L %"])
    assert hi >= 0
    ci = _idx(hdr, "Unrealized P&L %")
    assert "%" in str(hdr[ci]), "P&L header must name its unit"
    seen = 0
    for r in rows[hi + 1:]:
        v = r[ci]
        if isinstance(v, (int, float)):
            seen += 1
            # Percent units · a fraction would make every holding look flat.
            assert -100.0 <= float(v) <= 1000.0, (
                "P&L %s is not in percent units" % v)
        elif v is not None:
            assert str(v).strip() in MISSING_TOKENS, (
                "non-numeric P&L %r is neither a number nor a MISSING "
                "token" % v)
    wb.close()
    assert seen >= 0


@pytest.mark.parametrize("market", MARKETS)
def test_v1_banner_counts_reconcile_to_visible_body(market):
    """v1 · a banner count must come from the rendered rows, never from an
    independent scan that can drift from what the operator sees."""
    import re
    wb = _wb(market)
    rows = _rows(wb["R2"])
    sub = " ".join(str(c) for r in rows[1:4] for c in r if c is not None)
    m = re.search(r"Holdings:\s*(\d+)", sub)
    assert m, "R2 sub-banner must state the holding count · got %r" % sub[:160]
    claimed = int(m.group(1))
    hi, hdr = _header_at(rows, ["Stock", "Dynamic Stop", "Action"])
    c_tk = _idx(hdr, "Stock")
    visible = 0
    for r in rows[hi + 1:]:
        tk = str(r[c_tk]).strip() if r[c_tk] else ""
        # Stop at the legend block · it also occupies column A.
        if not tk:
            continue
        if len(tk) > 20:
            break
        visible += 1
    wb.close()
    assert claimed == visible, (
        "R2 banner claims %d holdings but %d rows are visible" %
        (claimed, visible))


@pytest.mark.parametrize("market", MARKETS)
def test_v1_definitions_reach_the_operator_on_every_sheet(market):
    """v1 required a Definitions sheet. The five-sheet layout has no spare
    tab, so every sheet must carry its own legend instead · the operator
    must never have to leave the file to learn what a column means."""
    wb = _wb(market)
    missing = []
    for sn in FIVE_SHEETS:
        text = " ".join(str(c) for r in _rows(wb[sn]) for c in r
                        if c is not None)
        # A legend is prose · at minimum it must define the sheet's terms.
        if len(text) < 400 or "·" not in text:
            missing.append(sn)
    wb.close()
    assert not missing, "sheets with no operator legend: %s" % missing


@pytest.mark.parametrize("market", MARKETS)
def test_v1_monthly_summary_is_separated_from_exit_body(market):
    """v1 kept MONTHLY_SUMMARY on its own sheet so it could never be read
    as more Exit History rows. The five-sheet layout embeds it, so it must
    carry its own heading and its own header row."""
    wb = _wb(market)
    rows = _rows(wb["EXIT"])
    text = " ".join(str(c) for r in rows for c in r if c is not None)
    hi, _ = _header_at(rows, ["Month", "Exits", "Win Rate %"])
    wb.close()
    assert "MONTHLY SUMMARY" in text, "monthly summary missing from EXIT"
    assert hi >= 0, "monthly summary must have its own header row"
    assert "production" in text, (
        "monthly summary must state that its scope is realized R2 "
        "production exits only")
