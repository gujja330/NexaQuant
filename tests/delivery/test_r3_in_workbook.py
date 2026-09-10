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

from conftest import lifecycle   # computes from SOURCE, never a committed artifact

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
    d = lifecycle(market)
    if not d:
        pytest.skip("no lifecycle dataset for %s" % market)
    b = w2.build_two_sheet_workbook(ROOT, market, d.get("asof"))
    p = tmp_path / ("%s.xlsx" % market)
    b["workbook"].save(p)
    return p


# ── separation ──────────────────────────────────────────────────────────

def test_r3_surface_is_exactly_one_column():
    """CEO 2026-09-08 · locked presentation rule."""
    assert w2.CURRENT_COLUMNS_R3 == ["R3 SHADOW"], w2.CURRENT_COLUMNS_R3


def test_r3_column_sits_beside_action():
    # SUPERSEDED 2026-09-10 · R3 used to be pinned after every R2 column.
    # The CEO moved it beside Action so the shadow opinion is read next to
    # the decision it annotates. What must still hold is that there is
    # exactly ONE R3 column and it sits directly after Action — position,
    # not precedence. R2 Action is still decided before any R3 value is
    # read, and R3 still writes nothing.
    cols = w2.CURRENT_COLUMNS
    assert len(w2.CURRENT_COLUMNS_R3) == 1
    assert cols.index("R3 SHADOW") == cols.index("Action") + 1
    # No R2 column was dropped, renamed or reordered by the move.
    assert [c for c in cols if c != "R3 SHADOW"] == w2.CURRENT_COLUMNS_R2


def test_r2_column_set_is_unchanged_by_the_r3_block():
    assert w2.CURRENT_COLUMNS_R2 == [
        "Market", "Ticker", "Engine", "Action", "Admission Status",
        "Entry Date", "Entry Price", "Last Price", "Market Data As-of",
        "P&L %", "Confidence %", "Sector", "Current Market Cap",
        "Market Cap As-of", "Size",
        "Stop", "Stop State", "Stop Distance %", "Max Loss if Stop %",
        "Target", "Position ID", "Reason"]
    # The point of this test is that R3 adds exactly ONE column and does
    # not reorder or rename anything among the R2 block.
    assert w2.CURRENT_COLUMNS_R3 == ["R3 SHADOW"]
    # R3 sits BESIDE Action (CEO 2026-09-10) rather than at the end, so
    # the shadow opinion is read next to the decision it comments on.
    # Position is not precedence: the R2 column set is unchanged, R2
    # Action is still decided before any R3 value is read, and R3 still
    # writes nothing.
    assert w2.CURRENT_COLUMNS == w2._with_r3(w2.CURRENT_COLUMNS_R2)
    assert w2.CURRENT_COLUMNS.index("R3 SHADOW") ==         w2.CURRENT_COLUMNS.index("Action") + 1
    assert w2.CURRENT_COLUMNS.count("R3 SHADOW") == 1
    assert [c for c in w2.CURRENT_COLUMNS if c != "R3 SHADOW"] ==         w2.CURRENT_COLUMNS_R2


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


def test_every_r2_row_reads_abstain_or_not_evaluated(tmp_path):
    """Assert the CONTRACT, not the presence of an artifact.

    The first version of this test asserted ABSTAIN unconditionally and
    broke CI: the shadow ledger is generated by a separate stage, so on a
    runner without it every cell legitimately renders NOT_EVALUATED. A
    delivery test that fails because an upstream artifact is absent
    blocks the send for a non-reason, which is worse than no test.

    What must always hold: a candidate WITH a shadow record shows that
    record's decision; one WITHOUT shows NOT_EVALUATED. Neither may ever
    be a fabricated value.
    """
    for m in MARKETS:
        d = lifecycle(m)
        if not d:
            continue
        led = w2.load_r3_shadow(ROOT, m, d.get("asof"))
        hdr, rows = _current(_built(m, tmp_path))
        r2 = [r for r in rows
              if str(r.get("Engine") or "").upper() in w2.R3_ENGINES]
        assert r2, "no R2 rows in %s CURRENT" % m
        for r in r2:
            tk = str(r.get("Ticker") or "").upper()
            cell = str(r["R3 SHADOW"])
            # The sheet now speaks plain English (CEO 2026-09-10), so the
            # ledger's state name is mapped to its investor wording rather
            # than compared verbatim. The internal state is unchanged.
            state = led[tk]["r3_action"] if tk in led else None
            want = (w2.R3_TEXT.get(str(state).upper())
                    if state else w2.R3_NO_SNAPSHOT_TEXT)
            assert cell == want, (
                "%s: rendered %r, ledger says %r" % (tk, cell, state))
            # Whatever the ledger state, no verdict may be invented.
            assert cell in set(w2.R3_TEXT.values()) | {
                w2.R3_NO_SNAPSHOT_TEXT}, cell


def test_r1_rows_are_not_applicable(tmp_path):
    for m in MARKETS:
        hdr, rows = _current(_built(m, tmp_path))
        for r in rows:
            if str(r.get("Engine") or "").upper() == "R1":
                assert str(r["R3 SHADOW"]) == w2.R3_NOT_APPLICABLE_TEXT, (
                    r["R3 SHADOW"])


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
        d = lifecycle(m)
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
                # Plain-English wording maps 1:1 from the ledger state;
                # the mapping is the only thing between them.
                assert str(r["R3 SHADOW"]) == w2.R3_TEXT[
                    str(rec["r3_action"]).upper()]
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
        # Wording changed 2026-09-10; the CLAIM must still be on the sheet.
        assert "does NOT change" in text and "RESEARCH ONLY" in text, text[:300]
        for field in ("Action", "Confidence", "Stop", "Position"):
            assert field in text, "%s not named in the R3 note" % field
        assert "Not rated yet" in text, "the note does not explain the state"


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
    assert "insufficient validated evidence" in text
    assert "NOT Hold, Buy, Avoid" in text


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


# ── plain-English R3 wording · CEO 2026-09-10 "abstain is confusing" ──

def test_r3_cell_never_shows_audit_jargon():
    """The investor sheet must not carry state-machine vocabulary."""
    for eng in ("R2", "MOMENTUM", "R1"):
        for rec in (None, {"r3_action": "ABSTAIN"}, {"r3_action": "TAKE"},
                    {"r3_action": "AVOID"}, {"r3_action": "WEIRD_STATE"}):
            cell = w2.r3_cells(rec, eng)[0]
            for jargon in ("ABSTAIN", "NOT_EVALUATED", "N/A",
                           "INSUFFICIENT_SUBSTRATE", "NOT_AVAILABLE_AT_ASOF"):
                assert jargon not in cell, "%r leaked into %r" % (jargon, cell)


def test_no_r3_state_reads_as_a_neutral_opinion():
    """"No view"/"Neutral" would be heard as a mild HOLD.

    That is precisely the misreading ABSTAIN existed to prevent, so the
    cell must say the RATING IS ABSENT, not that it is middling.
    """
    cell = w2.r3_cells({"r3_action": "ABSTAIN"}, "R2")[0]
    assert "Not rated yet" in cell
    for wrong in ("hold", "neutral", "50/50", "no view", "unsure",
                  "buy", "sell"):
        assert wrong not in cell.lower(), "%r reads as an opinion" % cell


def test_caution_never_reads_as_exit_and_supports_never_as_buy():
    avoid = w2.r3_cells({"r3_action": "AVOID"}, "R2")[0]
    take = w2.r3_cells({"r3_action": "TAKE"}, "R2")[0]
    assert "not an exit" in avoid.lower(), avoid
    assert "exit" not in take.lower() and "buy" not in take.lower(), take


def test_r1_rows_are_marked_not_reviewed_not_abstaining():
    """R1 is out of R3's scope · that is different from having no view."""
    cell = w2.r3_cells({"r3_action": "ABSTAIN"}, "R1")[0]
    assert "Not reviewed" in cell and "R2 candidates only" in cell


def test_an_unknown_r3_state_is_never_dressed_up_as_a_decision():
    cell = w2.r3_cells({"r3_action": "SOMETHING_NEW"}, "R2")[0]
    assert cell.startswith("Not rated yet"), cell
