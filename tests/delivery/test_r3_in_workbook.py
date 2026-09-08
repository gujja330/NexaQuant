"""R3 shadow intelligence in the CURRENT sheet.

R3 is now VISIBLE to the operator, which is the point at which it becomes
dangerous. A column that looks like a signal will eventually be read as
one, so these tests defend the separation:

  * R3 columns never sit among R2's columns
  * R2 Action never depends on any R3 value
  * no probability is rendered while no specialist is validated
  * absence is stated (NOT_EVALUATED / NOT_APPLICABLE), never blank
  * the sheet says, in words, that R3 does not change R2
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
from backend.delivery.sheets import workbook_two as w2

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("india", "usa")
HDR = 7


def _current(path: Path):
    wb = load_workbook(path, read_only=True)
    ws = wb["CURRENT"]
    hdr = [str(c.value).strip() if c.value else "" for c in ws[HDR]]
    rows = []
    for r in range(HDR + 1, ws.max_row + 1):
        t = ws.cell(r, hdr.index("Ticker") + 1).value
        if not t or str(t).startswith("─"):
            break
        rows.append({h: ws.cell(r, i + 1).value
                     for i, h in enumerate(hdr) if h})
    wb.close()
    return hdr, rows


def _built(market: str, tmp_path: Path) -> Path:
    d = lc.load(ROOT, market)
    if not d:
        pytest.skip("no lifecycle dataset for %s" % market)
    b = w2.build_two_sheet_workbook(ROOT, market, d.get("asof"))
    p = tmp_path / ("%s.xlsx" % market)
    b["workbook"].save(p)
    return p


# ── separation ──────────────────────────────────────────────────────────

def test_r3_columns_come_after_every_r2_column():
    cols = w2.CURRENT_COLUMNS
    first_r3 = min(cols.index(c) for c in w2.CURRENT_COLUMNS_R3)
    last_r2 = max(cols.index(c) for c in w2.CURRENT_COLUMNS_R2)
    assert first_r3 > last_r2, "an R3 column is interleaved with R2 columns"


def test_r2_column_set_is_unchanged_by_the_r3_block():
    assert w2.CURRENT_COLUMNS_R2 == [
        "Market", "Ticker", "Engine", "Action", "Entry Date", "Entry Price",
        "Current Price", "P&L %", "Confidence %", "Stop", "Stop State",
        "Dist to Stop %", "Max Loss if Stop %", "Target", "Position ID",
        "Reason"]


def test_r2_action_does_not_read_any_r3_value():
    """The lifecycle layer decides Action and never sees the shadow ledger."""
    src = Path(lc.__file__).read_text(encoding="utf-8")
    for token in ("r3_", "R3_DECISION", "shadow"):
        assert token not in src, (
            "canonical lifecycle references %s · R2 Action must be decided "
            "without reading R3" % token)


def test_renderer_reads_the_artifact_not_the_research_package():
    src = Path(w2.__file__).read_text(encoding="utf-8")
    imports = [l.strip() for l in src.splitlines()
               if l.strip().startswith(("import ", "from "))]
    for ln in imports:
        assert "backend.research" not in ln, (
            "renderer imports the research package: %s" % ln)


# ── no manufactured numbers ─────────────────────────────────────────────

def test_no_probability_column_is_rendered():
    for c in w2.CURRENT_COLUMNS_R3:
        assert "probab" not in c.lower(), (
            "%s renders a probability while no specialist is validated" % c)


def test_every_r2_row_reads_abstain(tmp_path):
    for m in MARKETS:
        hdr, rows = _current(_built(m, tmp_path))
        r2 = [r for r in rows
              if str(r.get("Engine") or "").upper() in w2.R3_ENGINES]
        assert r2, "no R2 rows in %s CURRENT" % m
        for r in r2:
            assert r["R3 Decision"] == "ABSTAIN", (
                "%s: %s" % (r.get("Ticker"), r["R3 Decision"]))


def test_r1_rows_are_not_applicable(tmp_path):
    for m in MARKETS:
        hdr, rows = _current(_built(m, tmp_path))
        for r in rows:
            if str(r.get("Engine") or "").upper() == "R1":
                assert r["R3 Decision"] == w2.R3_NOT_APPLICABLE


def test_no_r3_cell_is_ever_blank(tmp_path):
    """Absence must be stated · a blank reads as an oversight."""
    for m in MARKETS:
        hdr, rows = _current(_built(m, tmp_path))
        for r in rows:
            for c in w2.CURRENT_COLUMNS_R3:
                v = r.get(c)
                assert v not in (None, ""), (
                    "%s/%s: blank %s" % (m, r.get("Ticker"), c))


def test_no_r3_cell_renders_a_bare_zero(tmp_path):
    for m in MARKETS:
        hdr, rows = _current(_built(m, tmp_path))
        for r in rows:
            for c in w2.CURRENT_COLUMNS_R3:
                assert r.get(c) not in (0, 0.0), (
                    "%s: %s rendered 0 · absence must not look like a "
                    "confident forecast" % (r.get("Ticker"), c))


def test_r3_cells_match_the_shadow_ledger(tmp_path):
    """Rendered, not derived."""
    for m in MARKETS:
        d = lc.load(ROOT, m)
        if not d:
            continue
        led = w2.load_r3_shadow(ROOT, m, d.get("asof"))
        if not led:
            continue
        hdr, rows = _current(_built(m, tmp_path))
        checked = 0
        for r in rows:
            rec = led.get(str(r.get("Ticker") or "").upper())
            if rec and str(r.get("Engine") or "").upper() in w2.R3_ENGINES:
                assert r["R3 Decision"] == rec["r3_action"]
                assert r["R3 As-of"] == rec["as_of"]
                checked += 1
        assert checked > 0, "no R3 rows verified for %s" % m


# ── the sheet says what it is ───────────────────────────────────────────

def test_sheet_states_r3_does_not_change_r2(tmp_path):
    for m in MARKETS:
        wb = load_workbook(_built(m, tmp_path), read_only=True)
        ws = wb["CURRENT"]
        text = " ".join(str(ws.cell(r, 1).value or "")
                        for r in range(1, HDR))
        wb.close()
        assert "DOES NOT CHANGE R2 ACTION" in text, text[:200]


def test_stale_warning_is_not_overwritten_by_the_r3_notice():
    """Both share row 6 · neither may silently replace the other."""
    src = Path(w2.__file__).read_text(encoding="utf-8")
    assert "_row6" in src
    assert src.count('n, 6)') == 1, (
        "more than one _sub writes row 6 · the second overwrites the first")


def test_legend_explains_abstain_is_not_a_placeholder(tmp_path):
    wb = load_workbook(_built("india", tmp_path), read_only=True)
    ws = wb["CURRENT"]
    text = " ".join(str(ws.cell(r, 1).value or "")
                    for r in range(1, ws.max_row + 1))
    wb.close()
    assert "does not know" in text
    assert "not a neutral default" in text


# ── contract still intact ───────────────────────────────────────────────

def test_two_sheet_contract_unchanged(tmp_path):
    for m in MARKETS:
        wb = load_workbook(_built(m, tmp_path), read_only=True)
        assert wb.sheetnames == ["CURRENT", "EXIT HISTORY"]
        wb.close()


def test_exit_history_carries_no_r3_columns(tmp_path):
    """R3 comments on live candidates · a closed trade has no decision."""
    for m in MARKETS:
        wb = load_workbook(_built(m, tmp_path), read_only=True)
        hdr = [str(c.value).strip() if c.value else ""
               for c in wb["EXIT HISTORY"][4]]
        wb.close()
        assert not [h for h in hdr if h.startswith("R3 ")], hdr
