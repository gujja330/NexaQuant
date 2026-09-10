"""AEGIS · TWO-SHEET INVESTOR WORKBOOK CONTRACT · CEO 2026-09-08.

    CURRENT        what is investable now
    EXIT HISTORY   what has exited

Tests 1-15 from the directive. These pin the investor-facing contract and
the production-safety boundary around it: this was a PRESENTATION
refactor, and these tests are what prove no engine logic moved with it.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
XLSX = {m: ROOT / "reports" / "telegram" / f"aegis_history_{m}.xlsx"
        for m in ("india", "usa")}
MARKETS = ["india", "usa"]

TWO_SHEETS = ["CURRENT", "EXIT HISTORY"]
FORBIDDEN_STATES = [
    "HOLD", "WATCH", "REVIEW", "AVOID", "IGNORE", "NO SIGNAL", "PUMP_RISK",
    "MOMENTUM_WATCH", "NO_EVIDENCE", "REJECTED", "DORMANT", "BLOCKED",
    "NO_MODEL", "SUGGESTED", "SHADOW",
]


# Where a freshly built workbook is written for the duration of a test
# session · one build, reused, never touching reports/telegram.
_FRESH: dict = {}


def _wb(market: str):
    """The workbook the CURRENT RENDERER produces from the CURRENT
    lifecycle.

    This used to open reports/telegram/aegis_history_<mkt>.xlsx directly
    and compare it against a freshly computed lifecycle. Those two are
    from different cycles on any CI runner - the committed workbook is
    whatever the bot last pushed, while the lifecycle was rebuilt minutes
    ago - so `test_workbook_matches_the_lifecycle_dataset_exactly` and
    its neighbours failed three consecutive USA runs and skipped the
    send. Nothing was wrong with the workbook or the lifecycle; they were
    simply never the same age.

    These tests exist to prove the RENDERER is faithful to the dataset,
    which is a property of the code. So the workbook is built here from
    the current lifecycle. Whether the SHIPPED file is clean is the
    delivery gate's job - FIELDS_COMPLETE and stop_distance_invariant
    both block on it, and they read the live artifact.
    """
    from openpyxl import load_workbook
    if market in _FRESH:
        return load_workbook(_FRESH[market], data_only=True)

    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d:
        try:
            import tempfile

            from backend.delivery.sheets import workbook_two as w2
            built = w2.build_two_sheet_workbook(ROOT, market, d.get("asof"))
            out = (Path(tempfile.mkdtemp(prefix="aegis_wb_"))
                   / ("%s.xlsx" % market))
            built["workbook"].save(out)
            _FRESH[market] = out
            return load_workbook(out, data_only=True)
        except Exception:
            pass                      # fall back to the shipped file

    p = XLSX[market]
    if not p.exists():
        pytest.skip("workbook not built: %s" % p)
    wb = load_workbook(p, data_only=True)
    if "CURRENT" not in wb.sheetnames:
        sheets = list(wb.sheetnames)
        wb.close()
        pytest.skip("workbook predates the two-sheet layout (%s)" % sheets)
    return wb


def _rows(ws):
    return [[c.value for c in r] for r in ws.iter_rows()]


def _table(ws, must_have):
    """Body rows as dicts · stops at the first blank (legend follows)."""
    rows = _rows(ws)
    hi, hdr = -1, []
    for i, r in enumerate(rows):
        cells = {str(c).strip() for c in r if c is not None}
        if all(m in cells for m in must_have):
            hi, hdr = i, [str(c).strip() if c is not None else "" for c in r]
            break
    if hi < 0:
        return []
    out = []
    for r in rows[hi + 1:]:
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        rec = {hdr[i]: (r[i] if i < len(r) else None)
               for i in range(len(hdr)) if hdr[i]}
        first = rec.get(hdr[0])
        if first is None or str(first).strip() == "":
            continue
        if isinstance(first, str) and len(first) > 40:
            break                      # legend prose
        out.append(rec)
    return out


# ── TEST 1 · exactly two sheets ───────────────────────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_1_exactly_two_sheets(market):
    wb = _wb(market)
    names = list(wb.sheetnames)
    wb.close()
    assert names == TWO_SHEETS, "two-sheet contract violated · got %s" % names


@pytest.mark.parametrize("market", MARKETS)
def test_1b_no_legacy_sheets(market):
    wb = _wb(market)
    forbidden = {"R1", "R2", "MOMENTUM", "DAILY RECOMMENDATION", "EXIT",
                 "01_Portfolio", "01_Investments", "02_Today_Momentum",
                 "03_Exit_History", "00_Health", "05_R1_Advisory",
                 "06_Composite_Signals", "Portfolio", "Definitions"}
    leaked = forbidden & set(wb.sheetnames)
    wb.close()
    assert not leaked, "legacy sheets present: %s" % leaked


# ── TEST 2 · no forbidden state in CURRENT ────────────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_2_no_forbidden_state_in_current(market):
    wb = _wb(market)
    recs = _table(wb["CURRENT"], ["Ticker", "Engine", "Action"])
    bad = []
    for r in recs:
        act = str(r.get("Action") or "").upper().strip()
        if act in FORBIDDEN_STATES:
            bad.append((r.get("Ticker"), act))
    wb.close()
    assert not bad, "non-investable states leaked into CURRENT: %s" % bad[:6]


# ── TEST 3 · CURRENT holds only investable records ────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_3_current_is_only_investable(market):
    from backend.delivery.sheets.workbook_two import CURRENT_ACTIONS
    wb = _wb(market)
    recs = _table(wb["CURRENT"], ["Ticker", "Engine", "Action"])
    wb.close()
    bad = [r.get("Ticker") for r in recs
           if str(r.get("Action") or "").strip() not in CURRENT_ACTIONS]
    assert not bad, "non-investable rows in CURRENT: %s" % bad[:6]


# ── TEST 4 · ENGINE vocabulary ────────────────────────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_4_engine_values_are_closed_set(market):
    from backend.delivery.sheets.workbook_two import ALLOWED_ENGINES
    wb = _wb(market)
    recs = _table(wb["CURRENT"], ["Ticker", "Engine", "Action"])
    wb.close()
    bad = {str(r.get("Engine") or "").strip() for r in recs} - set(ALLOWED_ENGINES)
    assert not bad, "unexpected ENGINE values: %s" % bad


# ── TEST 5 · ACTION vocabulary · EXIT never in CURRENT ────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_5_action_vocabulary_and_no_exit(market):
    from backend.delivery.sheets.workbook_two import CURRENT_ACTIONS
    wb = _wb(market)
    recs = _table(wb["CURRENT"], ["Ticker", "Engine", "Action"])
    wb.close()
    acts = {str(r.get("Action") or "").strip() for r in recs}
    assert not (acts - set(CURRENT_ACTIONS)), "bad actions: %s" % (
        acts - set(CURRENT_ACTIONS))
    assert "EXIT" not in acts, "EXIT must move to EXIT HISTORY, not stay"


# ── TEST 6 · an exited position is in EXIT HISTORY, not CURRENT ───────
@pytest.mark.parametrize("market", MARKETS)
def test_6_exited_positions_move_to_exit_history(market):
    from backend.research import opportunity_registry as oreg
    wb = _wb(market)
    cur = {str(r.get("Position ID") or "")
           for r in _table(wb["CURRENT"], ["Ticker", "Engine", "Action"])}
    ex = {str(r.get("Position ID") or "")
          for r in _table(wb["EXIT HISTORY"], ["Ticker", "Engine", "Exit Date"])}
    wb.close()
    overlap = {p for p in (cur & ex) if p}
    assert not overlap, ("a position is in BOTH CURRENT and EXIT HISTORY: %s"
                         % sorted(overlap)[:5])


# ── TEST 7 · idempotent ·二 runs do not duplicate EXIT HISTORY ────────
@pytest.mark.parametrize("market", MARKETS)
def test_7_exit_history_has_no_duplicates(market):
    wb = _wb(market)
    recs = _table(wb["EXIT HISTORY"], ["Ticker", "Engine", "Exit Date"])
    wb.close()
    keys = [(str(r.get("Position ID") or ""), str(r.get("Exit Date") or ""))
            for r in recs]
    keys = [k for k in keys if k[0]]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, "duplicate exit rows: %s" % sorted(dupes)[:5]


# ── TEST 8 · R1 remains advisory ──────────────────────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_8_r1_remains_advisory(market):
    wb = _wb(market)
    recs = _table(wb["CURRENT"], ["Ticker", "Engine", "Action"])
    text = " ".join(str(c) for r in _rows(wb["CURRENT"]) for c in r
                    if c is not None)
    wb.close()
    r1 = [r for r in recs if str(r.get("Engine")).strip() == "R1"]
    if r1:
        assert "ADVISORY" in text.upper(), (
            "R1 rows present but the sheet never states R1 is advisory")
        for r in r1:
            assert "EXIT" not in str(r.get("Action") or "").upper()


# ── TEST 9 · R2 consumes the canonical dynamic-risk stop ──────────────
@pytest.mark.parametrize("market", MARKETS)
def test_9_r2_stop_is_canonical(market):
    import json
    p = ROOT / "reports" / "context" / f"dynamic_risk_{market}.json"
    if not p.exists():
        pytest.skip("canonical stop artifact absent")
    canon = {}
    for u in (json.loads(p.read_text(encoding="utf-8")).get("updates") or []):
        if u.get("new_stop") is not None:
            canon[str(u["ticker"]).upper().split(".", 1)[0]] = round(
                float(u["new_stop"]), 4)
    wb = _wb(market)
    recs = _table(wb["CURRENT"], ["Ticker", "Engine", "Action"])
    wb.close()
    bad, checked = [], 0
    for r in recs:
        if str(r.get("Engine")).strip() != "R2":
            continue
        tk = str(r.get("Ticker") or "").strip()
        s = r.get("Stop")
        if tk in canon and isinstance(s, (int, float)):
            checked += 1
            if round(float(s), 4) != canon[tk]:
                bad.append(f"{tk} sheet={s} canonical={canon[tk]}")
    assert not bad, "R2 stop diverged from dynamic_risk_v2: %s" % bad
    assert checked > 0 or not recs, "no R2 stop was cross-checked"


# ── TEST 10 · Momentum cannot bypass R2 governance ────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_10_momentum_cannot_bypass_r2(market):
    """A MOMENTUM row may appear only if the existing lifecycle made it
    investable. The momentum ledger sets production_impact=null on every
    entry by design, so momentum never opens a position on its own."""
    import inspect
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    src = inspect.getsource(lc.compute)
    assert "momentum_investable" in src
    # No code path may append a MOMENTUM row straight from the ledger ·
    # momentum reaches CURRENT only by first becoming an R2 position.
    body = src.split("_emit_exits")[0]
    assert "_emit_current(o, ENGINE_MOM)" not in body, (
        "a momentum row is added to CURRENT without passing R2 eligibility")


# ── TEST 11 · no stale legacy sheet lookup ────────────────────────────
def test_11_no_stale_sheet_lookup_remains():
    """Delegates to the structural guard so there is one owner of this."""
    from tests.standards import test_sheet_lookup_completeness as g
    g.test_every_sheet_lookup_knows_the_current_names()


# ── TEST 12 · every Registry-CLOSED is represented or explained ───────
@pytest.mark.parametrize("market", MARKETS)
def test_12_registry_closed_all_represented(market):
    import json
    from backend.research import opportunity_registry as oreg
    from backend.delivery.canonical.retirement import retired_runners
    from scripts.build_aegis_3sheet_workbook import (
        _is_administrative_exit, _close_on_or_before)
    reg = oreg.load_all(ROOT)
    retired = retired_runners(ROOT)
    closed = set()
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market or o.status != "CLOSED":
                continue
            closed.add(str(o.ticker).upper().split(".", 1)[0])
    wb = _wb(market)
    ex = {str(r.get("Ticker") or "").upper()
          for r in _table(wb["EXIT HISTORY"], ["Ticker", "Engine", "Exit Date"])}
    wb.close()
    aud = set()
    ap = ROOT / "reports" / "delivery" / f"orphan_audit_{market}.jsonl"
    if ap.exists():
        for ln in ap.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    aud.add(str(json.loads(ln).get("ticker", "")).upper())
                except Exception:
                    pass
    lost = closed - ex - aud
    assert not lost, ("Registry-CLOSED tickers neither in EXIT HISTORY nor "
                      "explained in orphan audit: %s" % sorted(lost)[:8])


# ── TEST 13 · production R2 logic untouched ───────────────────────────
def test_13_production_r2_logic_untouched():
    """The two-sheet refactor is PRESENTATION. The workbook must not
    import or call anything that mutates R2 production state."""
    import inspect
    from backend.delivery.sheets import workbook_two as wt
    src = inspect.getsource(wt)
    forbidden = ["oreg.close", "opportunity_registry.close", "get_or_create",
                 "publish_ssot", "update_from_recs", "dynamic_risk_v2.compute"]
    hits = [f for f in forbidden if f in src]
    assert not hits, "workbook mutates production state: %s" % hits


# ── TEST 14 · no R3 / research output in the investor workbook ────────
@pytest.mark.parametrize("market", MARKETS)
def test_14_no_r3_or_research_in_workbook(market):
    """Research INTERNALS stay out · the sanctioned R3 block may stay in.

    CEO 2026-09-08 directed R3 into CURRENT as a visible shadow-
    intelligence block, so a blanket ban on the token "R3" is no longer
    the contract. What this test still guards is the thing it was really
    protecting: research plumbing (ledger names, statistics, trial
    counts) must never surface on an investor sheet, and R3 must not
    appear on EXIT HISTORY or inside R2's own columns.
    """
    from backend.delivery.sheets import workbook_two as w2

    wb = _wb(market)
    text = " ".join(str(c) for sn in wb.sheetnames
                    for r in _rows(wb[sn]) for c in r if c is not None)

    # EXIT HISTORY carries no R3 at all · a closed trade has no decision.
    ex_text = " ".join(str(c) for r in _rows(wb["EXIT HISTORY"])
                       for c in r if c is not None)
    assert "R3" not in ex_text.replace("·", " ").split(),         "R3 leaked into EXIT HISTORY"

    # On CURRENT, R3 appears only as the declared trailing block.
    hdr = [str(c.value).strip() if c.value else "" for c in wb["CURRENT"][7]]
    wb.close()
    r3_hdr = [h for h in hdr if h.startswith("R3 ")]
    assert set(r3_hdr) == set(w2.CURRENT_COLUMNS_R3), (
        "R3 header block differs from the declared contract: %s" % r3_hdr)
    first_r3 = min(hdr.index(h) for h in r3_hdr)
    last_r2 = max(hdr.index(h) for h in w2.CURRENT_COLUMNS_R2 if h in hdr)
    assert first_r3 > last_r2, "R3 column interleaved with R2 columns"

    # Research plumbing never reaches an investor sheet · unchanged.
    for bad in ("shadow_ledger", "Tier-1", "FDR", "Brier", "trial_count",
                "p_value", "bootstrap", "AUC"):
        assert bad not in text, "research internal '%s' leaked" % bad


# ── TEST 15 · regeneration is content-stable ──────────────────────────
@pytest.mark.parametrize("market", MARKETS)
def test_15_regeneration_is_content_stable(market):
    """Building twice must yield the same rows · only timestamps may move."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    a = lc.compute(ROOT, market, date.today().isoformat())
    b = lc.compute(ROOT, market, date.today().isoformat())
    assert a["counts"] == b["counts"]
    assert [(r["ticker"], r["engine"], r["action"]) for r in a["current"]] == \
           [(r["ticker"], r["engine"], r["action"]) for r in b["current"]]
    assert [(e["position_id"], e["exit_date"]) for e in a["exits"]] == \
           [(e["position_id"], e["exit_date"]) for e in b["exits"]]


# ── canonical ACTION rule · reused, not invented ──────────────────────
def test_action_rule_matches_the_legacy_canonical_definition():
    from backend.delivery.sheets.workbook_two import classify_action
    assert classify_action("CLOSED", "BUY", "2026-01-01", "2026-09-08") == "EXIT"
    assert classify_action("ACTIVE", "BUY", "2026-09-08", "2026-09-08") == "NEW"
    assert classify_action("ACTIVE", "BUY", "2026-01-01", "2026-09-08") == "ACTIVE+"
    assert classify_action("ACTIVE", "STRONG BUY", "2026-01-01", "2026-09-08") == "ACTIVE+"
    assert classify_action("ACTIVE", "HOLD", "2026-01-01", "2026-09-08") == "ACTIVE"
    assert classify_action("ACTIVE", "ROTATED_SAMEDAY", "2026-01-01",
                           "2026-09-08") == "ACTIVE"


def test_losing_positions_are_not_hidden():
    """A losing but still-active position must remain visible."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    for market in MARKETS:
        v = lc.compute(ROOT, market, date.today().isoformat())
        losers = [r for r in v["current"]
                  if isinstance(r.get("pnl_pct"), (int, float))
                  and r["pnl_pct"] < 0]
        # Not an assertion that losers must exist · an assertion that if
        # they exist they were NOT filtered out.
        for r in losers:
            assert r["action"] in ("NEW", "ACTIVE", "ACTIVE+")


# ── Pipeline integration · CEO 2026-09-08 ─────────────────────────────
#
# "The two-sheet lifecycle must be a first-class downstream stage of the
#  canonical daily pipeline, not an independent workbook-only
#  transformation. The pipeline must generate the canonical lifecycle
#  dataset first and the XLSX must render only that dataset."


def test_lifecycle_is_downstream_only():
    """The lifecycle layer may READ engines · it may never WRITE to them.

    This is what stops a delivery transformation from quietly becoming a
    trading engine. Checked by verb, not by convention.
    """
    import inspect
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    src = inspect.getsource(lc)
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    forbidden = [
        "oreg.close", "opportunity_registry.close", "oreg.get_or_create",
        "opportunity_registry.get_or_create", "oreg.reject",
        "publish_ssot", "update_from_recs", "dynamic_risk_v2.compute",
        "drv.compute", ".emit(",
    ]
    hits = [f for f in forbidden if f in code]
    assert not hits, (
        "the lifecycle layer writes back into an engine: %s · it must be "
        "downstream-only" % hits)


def test_renderer_computes_nothing():
    """The workbook renderer must own no business logic.

    Every delivery defect this month came from a renderer recomputing what
    an engine had decided - two sheets each deriving an R2 stop and
    disagreeing. A renderer that cannot compute cannot disagree.
    """
    import inspect
    from backend.delivery.sheets import workbook_two as wt
    src = inspect.getsource(wt)
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    # No derivation of the values it displays.
    for banned in ("_close_on_or_before", "_atr14_at_date", "_load_registry",
                   "_load_dynamic_risk", "_target_from_registry",
                   "classify_action(", "* 100", "/ entry"):
        assert banned not in code, (
            "renderer derives a value instead of rendering it: %r" % banned)
    # And it must read the canonical dataset.
    assert "load_lifecycle" in code and "canonical_daily_lifecycle" in code


def test_renderer_refuses_to_run_without_the_dataset(tmp_path):
    """A missing dataset must FAIL LOUDLY, never fall back to recomputing.

    A silent fallback would recreate exactly the divergence this design
    removes.
    """
    from backend.delivery.sheets.workbook_two import build_two_sheet_workbook
    with pytest.raises(RuntimeError, match="canonical lifecycle dataset missing"):
        build_two_sheet_workbook(tmp_path, "india", "2026-09-08")


def test_lifecycle_stage_runs_before_the_workbook_in_the_pipeline():
    """Ordering is the guarantee · the dataset must exist when rendering."""
    import re
    src = (ROOT / "scripts" / "aegis_daily_v2.py").read_text(encoding="utf-8")
    names = re.findall(r'"name":\s*"([^"]+)"', src)
    assert "canonical_daily_lifecycle" in names, "lifecycle stage not wired"
    assert "aegis_3sheet_workbook" in names
    assert names.index("canonical_daily_lifecycle") < names.index("aegis_3sheet_workbook"), (
        "the workbook is built BEFORE the lifecycle dataset exists")
    # And after exits are reconciled, so a same-day exit leaves CURRENT.
    if "dynamic_exit_bridge" in names:
        assert names.index("dynamic_exit_bridge") < names.index("canonical_daily_lifecycle")


@pytest.mark.parametrize("market", MARKETS)
def test_workbook_matches_the_lifecycle_dataset_exactly(market):
    """The rendered sheet must equal the dataset · no drift, no extra rows."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d is None:
        pytest.skip("lifecycle dataset not produced")
    wb = _wb(market)
    cur = _table(wb["CURRENT"], ["Ticker", "Engine", "Action"])
    ex = _table(wb["EXIT HISTORY"], ["Ticker", "Engine", "Exit Date"])
    wb.close()
    assert len(cur) == len(d["current"]), (
        "CURRENT has %d rows but the dataset has %d"
        % (len(cur), len(d["current"])))
    assert len(ex) == len(d["exits"]), (
        "EXIT HISTORY has %d rows but the dataset has %d"
        % (len(ex), len(d["exits"])))
    for sheet_row, data_row in zip(cur, d["current"]):
        assert str(sheet_row.get("Ticker")) == data_row["ticker"]
        assert str(sheet_row.get("Engine")) == data_row["engine"]
        assert str(sheet_row.get("Action")) == data_row["action"]


@pytest.mark.parametrize("market", MARKETS)
def test_lifecycle_is_deterministic(market):
    """Two computations of the same as-of must be byte-identical except
    for the generation timestamp."""
    import hashlib, json as _j
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    a = lc.compute(ROOT, market, date.today().isoformat())
    b = lc.compute(ROOT, market, date.today().isoformat())

    def _h(d):
        c = dict(d)
        c.pop("generated_utc", None)
        return hashlib.sha256(
            _j.dumps(c, sort_keys=True, default=str).encode()).hexdigest()
    assert _h(a) == _h(b), "lifecycle aggregation is not deterministic"


# ═══════════════════════════════════════════════════════════════════════
# BREACHED IS AN EXIT TRANSITION · CEO 2026-09-08
#
#   > "Breached means EXIT transition, not CURRENT. Keeping a breached R1
#   >  position in CURRENT was wrong for the investor-facing lifecycle."
#
# These pin the rule AND the two ways it could quietly go wrong: a breach
# mark leaking into the realized-P&L statistics, and a latch that lets an
# exit un-exit when price recovers.
# ═══════════════════════════════════════════════════════════════════════

BREACH_SOURCE = "lifecycle:stop-breach"


@pytest.mark.parametrize("market", MARKETS)
def test_no_breached_row_survives_in_current(market):
    """CURRENT is breach-free · dataset AND rendered sheet."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d is None:
        pytest.skip("lifecycle dataset not produced")
    bad = [r["ticker"] for r in d["current"] if r.get("stop_state") == "BREACHED"]
    assert not bad, "breached positions still in CURRENT: %s" % bad
    assert d["counts"].get("stop_breached", 0) == 0

    wb = _wb(market)
    rows = _table(wb["CURRENT"], ["Ticker", "Stop State"])
    wb.close()
    on_sheet = [r["Ticker"] for r in rows if str(r.get("Stop State")) == "BREACHED"]
    assert not on_sheet, "breached rows rendered into CURRENT: %s" % on_sheet


@pytest.mark.parametrize("market", MARKETS)
def test_breach_exit_preserves_reason_and_pnl(market):
    """The loss must survive the transition · that is the whole point."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d is None:
        pytest.skip("lifecycle dataset not produced")
    bx = [e for e in d["exits"] if e.get("source") == BREACH_SOURCE]
    if not bx:
        pytest.skip("no breached positions in %s today" % market)
    for e in bx:
        assert e["exit_reason"] == "Stop breached", e
        assert "STOP BREACHED" in str(e["exit_trigger"]).upper(), e
        assert e.get("stop") is not None, "breach exit lost its stop: %s" % e
        assert e.get("realized_pnl_pct") is not None, (
            "breach exit dropped the P&L · the loss would be hidden: %s" % e)


@pytest.mark.parametrize("market", MARKETS)
def test_breach_marks_never_pollute_realized_statistics(market):
    """A mark is not a fill.

    The position is still open in its engine, so counting it beside real
    closes would silently mix unrealized losses into the realized
    win-rate. Distinct source is what keeps the two apart.
    """
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d is None:
        pytest.skip("lifecycle dataset not produced")
    for e in d["exits"]:
        if e.get("source") == BREACH_SOURCE:
            assert not str(e["source"]).startswith("registry:")
        else:
            assert e.get("source", "").startswith("registry:"), e


@pytest.mark.parametrize("market", MARKETS)
def test_no_position_is_lost_in_the_transition(market):
    """Conservation · every active position is in CURRENT or in a breach
    exit, never in neither. A row that vanishes is the defect class this
    whole layer exists to remove."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.compute(ROOT, market, date.today().isoformat())
    seen = {r["position_id"] for r in d["current"] if r.get("position_id")}
    seen |= {e["position_id"] for e in d["exits"]
             if e.get("source") == BREACH_SOURCE and e.get("position_id")}
    ledger = lc.load_breach_ledger(ROOT, market)
    closed = {e["position_id"] for e in d["exits"]
              if str(e.get("source", "")).startswith("registry:")}
    for pid in ledger:
        assert pid in seen or pid in closed, (
            "latched breach %s is in neither CURRENT, a breach exit, nor a "
            "registry close · the position was silently dropped" % pid)


@pytest.mark.parametrize("market", MARKETS)
def test_breach_is_latched_and_idempotent(market):
    """Recomputing must not duplicate a ledger entry or move an exit date.

    Without the latch a recovery back above the stop would pull the row
    out of EXIT HISTORY and back into CURRENT · a permanent record that
    un-records is not permanent.
    """
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    asof = date.today().isoformat()
    before = lc.load_breach_ledger(ROOT, market)
    a = lc.compute(ROOT, market, asof)
    mid = lc.load_breach_ledger(ROOT, market)
    b = lc.compute(ROOT, market, asof)
    after = lc.load_breach_ledger(ROOT, market)
    assert set(mid) == set(after), "recompute appended duplicate ledger rows"
    for pid, rec in before.items():
        assert after[pid]["breach_date"] == rec["breach_date"], (
            "a latched breach date was rewritten for %s" % pid)
    da = {e["position_id"]: e["exit_date"] for e in a["exits"]
          if e.get("source") == BREACH_SOURCE}
    db = {e["position_id"]: e["exit_date"] for e in b["exits"]
          if e.get("source") == BREACH_SOURCE}
    assert da == db, "breach exit dates are not stable across recomputes"


def test_breach_transition_changed_no_engine():
    """The directive was explicit: lifecycle/presentation only.

    > "Do not change R1's advisory risk engine; this is lifecycle/
    >  presentation behavior."

    R1 must still derive an ADVISORY, non-enforced stop and must still
    never be auto-exited by this layer.
    """
    import inspect
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    src = inspect.getsource(lc)
    assert "ATR14 SUGGESTED · advisory · NOT enforced" in src, (
        "R1's advisory stop basis was altered")
    assert "dynamic_risk_v2 · ENFORCED" in src, "R2's canonical stop was altered"
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    for forbidden in ("oreg.close", "opportunity_registry.close",
                      "reject(", "publish_ssot"):
        assert forbidden not in code, (
            "the breach transition closes a real position: %r" % forbidden)


@pytest.mark.parametrize("market", MARKETS)
def test_breach_exit_rows_are_rendered_and_labelled(market):
    """An investor must be able to tell a mark from a completed trade."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d is None:
        pytest.skip("lifecycle dataset not produced")
    n = sum(1 for e in d["exits"] if e.get("source") == BREACH_SOURCE)
    if not n:
        pytest.skip("no breached positions in %s today" % market)
    wb = _wb(market)
    ws = wb["EXIT HISTORY"]
    rows = _table(ws, ["Ticker", "Source", "Exit Reason"])
    head = "\n".join(str(ws.cell(r, 1).value or "") for r in range(1, 5))
    wb.close()
    assert sum(1 for r in rows if str(r.get("Source")) == BREACH_SOURCE) == n
    assert "MARK" in head.upper() and "NOT sold".upper() in head.upper(), (
        "EXIT HISTORY does not warn that breach rows are marks, not fills")


# ── CURRENT · the columns added by the 2026-09-10 lock audit ──────────

@pytest.mark.parametrize("market", ("india", "usa"))
def test_current_states_both_dates(market):
    """The workbook date and the PRICE date are different questions.

    The 2026-09-10 sheet showed 2026-09-09 closes under a 2026-09-10
    header with nothing stating the difference.
    """
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if not d:
        pytest.skip("no lifecycle dataset")
    ws = _wb(market)["CURRENT"]
    banner = str(ws.cell(1, 1).value or "")
    assert "workbook" in banner and "close" in banner, banner
    assert str(d.get("market_data_asof") or "") in banner, (
        "the price date is not on the sheet")


@pytest.mark.parametrize("market", ("india", "usa"))
def test_current_carries_sector_cap_and_admission(market):
    ws = _wb(market)["CURRENT"]
    hdr = [str(ws.cell(7, c).value or "").strip()
           for c in range(1, ws.max_column + 1)]
    for col in ("Sector", "Current Market Cap", "Size", "Admission Status",
                "Market Data As-of", "Last Price", "Stop Distance %"):
        assert col in hdr, "%s missing from CURRENT" % col
    # The renames must be complete, not additive.
    assert "Current Price" not in hdr
    assert "Dist to Stop %" not in hdr
    # Exactly one R3 column, still last.
    assert hdr.count("R3 SHADOW") == 1
    assert hdr[len([h for h in hdr if h]) - 1] == "R3 SHADOW"


@pytest.mark.parametrize("market", ("india", "usa"))
def test_market_cap_is_never_a_liquidity_bucket(market):
    """Cap is a size, not a turnover. Absence is stated, never substituted."""
    ws = _wb(market)["CURRENT"]
    hdr = [str(ws.cell(7, c).value or "").strip()
           for c in range(1, ws.max_column + 1)]
    ci = hdr.index("Current Market Cap") + 1
    seen = []
    for r in range(8, ws.max_row + 1):
        t = ws.cell(r, 1).value
        if not t or str(t).startswith("─"):
            break
        seen.append(ws.cell(r, ci).value)
    for v in seen:
        s = str(v)
        assert not any(k in s.lower() for k in
                       ("liquid", "large-cap", "mid-cap", "small-cap",
                        "bucket")), "a liquidity label is sitting in the cap column: %r" % v
        if s != "MARKET_CAP_UNAVAILABLE":
            assert isinstance(v, (int, float)), (
                "cap must be a number or the explicit unavailable token, got %r" % v)


@pytest.mark.parametrize("market", ("india", "usa"))
def test_admission_status_keeps_yesterdays_new_visible(market):
    """A name admitted yesterday must not become anonymous today."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if not d:
        pytest.skip("no lifecycle dataset")
    ws = _wb(market)["CURRENT"]
    hdr = [str(ws.cell(7, c).value or "").strip()
           for c in range(1, ws.max_column + 1)]
    ai = hdr.index("Admission Status") + 1
    vals = []
    for r in range(8, ws.max_row + 1):
        t = ws.cell(r, 1).value
        if not t or str(t).startswith("─"):
            break
        vals.append(str(ws.cell(r, ai).value or ""))
    assert vals, "no rows"
    assert all(v.strip() for v in vals), "an admission status cell is blank"
    assert all(v == "NEW today" or v.startswith("Admitted")
               or v == "Admission date unknown" for v in vals), set(vals)
