"""AEGIS · OPPORTUNITY-FUNNEL OBSERVABILITY + FULL-UNIVERSE SHADOW.

CEO 2026-09-08:

  > "Wire the diagnostics ... Then every day we can mechanically see
  >  Universe -> evaluated -> scored -> candidate -> eligible -> NEW ->
  >  CURRENT. No more guessing why NEW = 0."

  > "Do not change confidence floors or trading rules. Instead, create a
  >  shadow full-universe recommendation path ... This gives us the
  >  evidence before touching R2 production."

These pin the two ways this work could quietly rot: the diagnostics going
orphaned again, and the shadow drifting into something that can touch
production.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ["india", "usa"]


def _steps():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_adv", ROOT / "scripts" / "aegis_daily_v2.py")
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass
    return m.STEPS


# ═══════════════════════════════════════════════════════════════════════
# 1 · The diagnostics must stay WIRED
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("name", [
    "momentum_funnel_diagnostic", "momentum_funnel_diagnostic_usa",
    "r2_signal_funnel", "r2_signal_funnel_usa", "full_universe_shadow",
])
def test_funnel_diagnostics_are_pipeline_steps(name):
    """Both funnels already existed and BOTH were orphaned.

    The momentum funnel last ran 2026-09-02 and the India R2 funnel
    2026-07-30, so "NEW 0 · MOMENTUM 0" shipped for days with nothing to
    explain it. A diagnostic nobody runs is worse than none: it looks like
    coverage while providing none.
    """
    assert name in [s["name"] for s in _steps()], (
        "%s is not a pipeline step · the funnel is orphaned again" % name)


def test_funnel_runs_before_the_workbook():
    """The sheet cannot report today's reason from yesterday's funnel."""
    names = [s["name"] for s in _steps()]
    for n in ("momentum_funnel_diagnostic", "r2_signal_funnel",
              "full_universe_shadow"):
        assert names.index(n) < names.index("aegis_3sheet_workbook"), (
            "%s runs after the workbook is built" % n)


def test_momentum_diagnostic_defaults_asof_to_today():
    """The step runner passes script_args verbatim and injects no --asof.

    While --asof was required the wired step would have failed on every
    run - green pipeline, no diagnostic.
    """
    src = (ROOT / "scripts" / "momentum_funnel_diagnostic.py").read_text(
        encoding="utf-8")
    assert 'add_argument("--asof", required=True' not in src
    assert "date.today().isoformat()" in src


# ═══════════════════════════════════════════════════════════════════════
# 2 · The momentum funnel must not resurrect the false "0 scanned"
# ═══════════════════════════════════════════════════════════════════════

def test_momentum_funnel_reports_evaluated_not_the_deprecated_field():
    """M4 read `n_universe_scanned`, which the ledger itself labels
    DEPRECATED and defines as "in-universe candidate count · NOT the
    number of tickers scanned".

    India evaluated all 230 tickers and found 4 candidates, every one of
    them outside the declared NIFTY-50 production universe. That was
    reported as "CRITICAL · only 0 of 230 actually scanned" and sent the
    investigation after a scan failure that never happened.
    """
    src = (ROOT / "scripts" / "momentum_funnel_diagnostic.py").read_text(
        encoding="utf-8")
    assert "M3_evaluated" in src and "M4_producer_candidates" in src
    assert "M4_actually_scanned" not in src.split("MOMENTUM_STAGES")[1][:600]
    assert "producer_funnel" in src, "the producer's truthful funnel is unused"
    assert "UNIVERSE-BOUND" in src, (
        "a universe-filtered day must be distinguishable from a scan failure")


@pytest.mark.parametrize("market", MARKETS)
def test_momentum_funnel_stages_are_internally_consistent(market):
    p = ROOT / "reports" / "research" / "momentum_funnel" / market / "latest.json"
    if not p.exists():
        pytest.skip("momentum funnel not produced for %s" % market)
    st = json.loads(p.read_text(encoding="utf-8")).get("stages") or {}
    if "M3_evaluated" not in st:
        pytest.skip("pre-correction artifact")
    assert st["M3_evaluated"] <= st["M1_universe_raw"]
    assert st["M4_producer_candidates"] <= st["M3_evaluated"]
    assert st["M5_candidates_in_universe"] <= st["M4_producer_candidates"], (
        "more in-universe candidates than the producer found")
    assert st["M7_accepted"] + st["M8_watch"] <= st["M6_classified"]


# ═══════════════════════════════════════════════════════════════════════
# 3 · The shadow must never be able to touch production
# ═══════════════════════════════════════════════════════════════════════

def test_shadow_writes_no_production_artifact():
    """Measurement only · this is what keeps it a shadow.

    It may READ any production input, but its only write is its own
    research artifact. Registering a model or emitting ensemble.json would
    make it a second production path with no governance.
    """
    import ast
    import inspect
    from backend.research.shadow import full_universe_shadow as fus
    src = inspect.getsource(fus)
    # Strip comments AND docstrings before checking. The module documents
    # the production paths it deliberately avoids, and matching that prose
    # would fail the check on the very text describing the guarantee.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    for forbidden in ("register_model", "recommendations_v3.json",
                      "OUT_ENSEMBLE", "oreg.", "publish_ssot",
                      "opportunity_registry"):
        assert forbidden not in code, (
            "the shadow writes into production: %r" % forbidden)
    # Its only emit target is the research artifact.
    assert "'reports' / 'research' / 'shadow'" in code.replace('"', "'")


def test_shadow_uses_unchanged_production_thresholds():
    """> "Do not change confidence floors or trading rules."

    The shadow's whole value is that breadth is the ONLY variable. A tuned
    floor would make the comparison meaningless.
    """
    from backend.research.shadow import full_universe_shadow as fus
    assert fus.CONF_FLOOR == 0.55
    assert fus.REGIME_CONF_FLOOR == 0.55
    from importlib import import_module
    r2 = import_module("scripts.r2_signal_funnel")
    assert fus.CONF_FLOOR == r2.CONF_FLOOR, (
        "shadow and R2 funnel disagree on the confidence floor")
    assert fus.REGIME_CONF_FLOOR == r2.REG_CONF_FLOOR


def test_shadow_action_enum_is_normalised():
    """`str(Action.HOLD)` is "ACTION.HOLD", not "HOLD".

    The first shadow run compared the raw enum and reported 228 of 228 as
    non-HOLD when the true count was 0 - an inverted funnel that would
    have argued for widening R2 on entirely false evidence.
    """
    from backend.research.shadow.full_universe_shadow import _action

    class _E:
        value = "HOLD"

    class _Rec:
        action = _E()
    assert _action(_Rec()) == "HOLD"
    assert _action("Action.STRONG_BUY") == "STRONG_BUY"
    assert _action("") == ""


@pytest.mark.parametrize("market", MARKETS)
def test_shadow_funnel_is_monotonic(market):
    """Each gate can only remove names · a later stage exceeding an
    earlier one means the funnel is measuring different populations."""
    from backend.research.shadow import full_universe_shadow as fus
    d = fus.load(ROOT, market)
    if d is None:
        pytest.skip("shadow not produced for %s" % market)
    f = d["funnel"]
    order = ["F4_non_hold", "F5_survived_disagreement",
             "F6_survived_confidence_floor", "F7_survived_regime_floor",
             "F8_would_be_new"]
    for a, b in zip(order, order[1:]):
        assert f[b] <= f[a], "%s (%d) > %s (%d)" % (b, f[b], a, f[a])
    assert f["F3_recommendations_returned"] <= f["F1_universe_scored"]
    assert f["F9_would_be_new_missed_by_truncation"] <= f["F8_would_be_new"]


@pytest.mark.parametrize("market", MARKETS)
def test_shadow_gives_every_name_a_reason(market):
    """> "why each rejected candidate fails" · no silent rejections."""
    from backend.research.shadow import full_universe_shadow as fus
    d = fus.load(ROOT, market)
    if d is None:
        pytest.skip("shadow not produced for %s" % market)
    assert d["rows"], "shadow returned no rows"
    for r in d["rows"]:
        assert r.get("reason"), "no rejection reason for %s" % r.get("ticker")
    assert sum(d["rejection_reasons"].values()) == len(d["rows"]), (
        "reason tally does not account for every scored name")


@pytest.mark.parametrize("market", MARKETS)
def test_shadow_sees_more_than_production(market):
    """RE-BASELINED 2026-09-09 · the defect this measured is now fixed.

    This asserted `F2_persisted_to_production <= 15`, encoding the
    truncation as expected behaviour: production was offered only
    top_10 + bottom_5, and the shadow existed to show what it was
    missing. On 2026-09-09 that truncation discarded four qualified USA
    BUYs before any rule saw them, so ensemble.json now persists
    `all_candidates` and the eligibility engine reads it.

    The invariant worth keeping is the opposite one: production must now
    see the WHOLE universe the shadow scores. A gap reopening means the
    truncation came back.
    """
    from backend.research.shadow import full_universe_shadow as fus
    d = fus.load(ROOT, market)
    if d is None:
        pytest.skip("shadow not produced for %s" % market)
    f = d["funnel"]
    assert f["F2_persisted_to_production"] == f["F1_universe_scored"], (
        "production sees %d of the %d names the shadow scored · "
        "pre-eligibility truncation has returned"
        % (f["F2_persisted_to_production"], f["F1_universe_scored"]))


# ═══════════════════════════════════════════════════════════════════════
# 4 · Lifecycle reconciliation · "Why isn't this stock in CURRENT?"
# ═══════════════════════════════════════════════════════════════════════

def test_reconciler_is_wired_before_the_workbook():
    names = [s["name"] for s in _steps()]
    assert "why_not_current" in names
    assert (names.index("canonical_daily_lifecycle")
            < names.index("why_not_current")
            < names.index("aegis_3sheet_workbook")), (
        "the reconciler must join the lifecycle and be available to the sheet")


@pytest.mark.parametrize("market", MARKETS)
def test_every_scored_name_gets_exactly_one_verdict(market):
    """A reconciliation that leaves names unaccounted answers nothing."""
    from backend.delivery.lifecycle import why_not_current as wnc
    d = wnc.load(ROOT, market)
    if d is None:
        pytest.skip("reconciliation not produced for %s" % market)
    assert sum(d["tally"].values()) == d["n_reconciled"] == len(d["rows"])
    seen = [r["ticker"] for r in d["rows"]]
    assert len(seen) == len(set(seen)), "a ticker received two verdicts"
    for r in d["rows"]:
        assert r["verdict"] in wnc.VERDICT_TEXT
        assert r["meaning"]


@pytest.mark.parametrize("market", MARKETS)
def test_a_stale_close_is_not_a_reason(market):
    """L8 matched ANY exit in the 90-day window, so 489 of 516 USA names
    were reported as "registry closed" and every live verdict vanished
    behind a close that happened two months earlier.

    "Why isn't it in CURRENT today" is answered by today's gates.
    """
    from backend.delivery.lifecycle import why_not_current as wnc
    d = wnc.load(ROOT, market)
    if d is None:
        pytest.skip("reconciliation not produced for %s" % market)
    n = d["n_reconciled"]
    assert d["tally"]["L8_registry_closed"] < n * 0.25, (
        "L8 is swallowing the population again (%d of %d)"
        % (d["tally"]["L8_registry_closed"], n))


@pytest.mark.parametrize("market", MARKETS)
def test_current_rows_reconcile_to_the_lifecycle_dataset(market):
    """Every investable ticker must be reported as being in CURRENT.

    CURRENT can hold the same ticker twice (one R1 row and one R2 row), so
    the comparison is over the ticker SET, not the row count.
    """
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    from backend.delivery.lifecycle import why_not_current as wnc
    d = wnc.load(ROOT, market)
    life = lc.load(ROOT, market)
    if d is None or life is None:
        pytest.skip("artifacts not produced for %s" % market)
    in_cur = {wnc._bare(r["ticker"]) for r in life["current"]}
    verdicted = {r["ticker"] for r in d["rows"]
                 if r["verdict"] == "L10_in_current"}
    assert in_cur == verdicted, (
        "CURRENT and the reconciler disagree · only in CURRENT: %s · only "
        "in reconciler: %s" % (sorted(in_cur - verdicted),
                               sorted(verdicted - in_cur)))


@pytest.mark.parametrize("market", MARKETS)
def test_reconciler_publishes_a_new_zero_reason(market):
    """> "Every NEW = 0 must show the exact bottleneck/rejection reason." """
    from backend.delivery.lifecycle import why_not_current as wnc
    d = wnc.load(ROOT, market)
    if d is None:
        pytest.skip("reconciliation not produced for %s" % market)
    h = d.get("headline") or ""
    # The headline must state the ACTUAL count. It read "WHY NEW=0" on a
    # day India produced NEW 1 (JIOFIN) - a false statement on the sheet.
    assert ("WHY NEW=0" in h) or h.startswith("NEW="), h
    assert "biggest blocker" in h, h


def test_reconciler_is_downstream_only():
    import ast
    import inspect
    from backend.delivery.lifecycle import why_not_current as wnc
    tree = ast.parse(inspect.getsource(wnc))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) \
                and ast.get_docstring(node):
            node.body = node.body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    for forbidden in ("oreg.", "opportunity_registry", "publish_ssot",
                      "register_model", "get_or_create"):
        assert forbidden not in code, (
            "the reconciler writes into an engine: %r" % forbidden)


# ═══════════════════════════════════════════════════════════════════════
# 5 · Stale inputs must never silently build CURRENT
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("market", MARKETS)
def test_lifecycle_measures_input_freshness(market):
    """> "Reject stale inputs from becoming CURRENT."

    India's recommendation artifact sat at 2026-09-03 for five days while
    CURRENT was rebuilt each cycle and looked completely normal. Staleness
    that is not measured is indistinguishable from freshness.
    """
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d is None:
        pytest.skip("lifecycle not produced")
    fr = d.get("input_freshness")
    assert fr, "the lifecycle does not measure its own input freshness"
    labels = {f["input"] for f in fr}
    assert {"recommendations_v3", "ensemble", "dynamic_risk"} <= labels
    for f in fr:
        assert f["verdict"] in ("FRESH", "STALE", "MISSING")
        if f["verdict"] == "FRESH":
            assert (f["age_days"] or 0) <= 0
    assert d["counts"]["stale_inputs"] == sum(
        1 for f in fr if f["verdict"] != "FRESH")


@pytest.mark.parametrize("market", MARKETS)
def test_stale_input_is_declared_on_the_sheet(market):
    """A stale input the operator cannot see is the same defect again."""
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d is None:
        pytest.skip("lifecycle not produced")
    p = ROOT / "reports" / "telegram" / ("aegis_history_%s.xlsx" % market)
    if not p.exists():
        pytest.skip("workbook not built")
    from openpyxl import load_workbook
    wb = load_workbook(p, read_only=True)
    if "CURRENT" not in wb.sheetnames:
        wb.close()
        pytest.skip("pre-two-sheet workbook")
    head = " ".join(str(wb["CURRENT"].cell(r, 1).value or "")
                    for r in range(1, 8))
    wb.close()
    if d["counts"].get("stale_inputs"):
        assert "STALE INPUT" in head, (
            "%d stale input(s) but the sheet does not say so"
            % d["counts"]["stale_inputs"])
    assert ("WHY NEW=0" in head or "NEW=" in head), (
        "the sheet states counts without their reason")


# ═══════════════════════════════════════════════════════════════════════
# 6 · The momentum quality gate must never be starved again
# ═══════════════════════════════════════════════════════════════════════

def test_investability_shadow_is_runnable_and_wired():
    """It had run() but NO __main__, so nothing could invoke it and
    reports/investability_shadow_{market}.json was never produced.

    short_term_momentum._quality_band reads that file first and falls back
    to investability_{market}.json - 42 India / 30 USA names, last written
    2026-08-08. Every momentum candidate outside those resolved to
    quality_band=UNKNOWN, so 17 of USA's 18 in-universe candidates were
    recorded NO_EVIDENCE / R_QUALITY_UNAVAILABLE: discarded as unknowable
    because the evidence had never been generated.
    """
    src = (ROOT / "backend" / "investability" / "shadow_runner.py").read_text(
        encoding="utf-8")
    assert "__main__" in src and "def main(" in src, (
        "shadow_runner is not runnable · the quality gate will starve again")
    names = [s["name"] for s in _steps()]
    assert "investability_shadow" in names, "producer is orphaned again"
    assert names.index("investability_shadow") < names.index(
        "short_term_momentum_producer"), (
        "quality scores must exist BEFORE momentum classifies candidates")


@pytest.mark.parametrize("market", MARKETS)
def test_quality_band_source_covers_the_scanned_universe(market):
    """The narrow fallback covers ~30-42 names; momentum scans 230/908.

    Coverage below the scanned universe is what turns real verdicts into
    NO_EVIDENCE.
    """
    p = ROOT / "reports" / ("investability_shadow_%s.json" % market)
    if not p.exists():
        pytest.skip("investability shadow not produced for %s" % market)
    n = len(json.loads(p.read_text(encoding="utf-8")).get("results") or [])
    floor = {"india": 200, "usa": 500}[market]
    assert n >= floor, (
        "%s investability shadow covers only %d names · below the scanned "
        "universe, so momentum candidates will resolve to UNKNOWN" % (market, n))


def test_momentum_no_longer_discards_candidates_as_unknowable():
    """R_QUALITY_UNAVAILABLE must not be the verdict for most candidates.

    A momentum engine that answers "no evidence" for 17 of 18 candidates
    is not being selective, it is being starved.
    """
    p = (ROOT / "reports" / "research" / "multi_layer"
         / "momentum_ledger_usa_2026-09-08.json")
    if not p.exists():
        pytest.skip("USA momentum ledger not produced")
    d = json.loads(p.read_text(encoding="utf-8"))
    n_class = int(d.get("n_candidates_classified") or 0)
    if not n_class:
        pytest.skip("no classified candidates today")
    n_unknown = int((d.get("by_reason_code") or {}).get(
        "R_QUALITY_UNAVAILABLE", 0))
    assert n_unknown <= n_class * 0.5, (
        "%d of %d candidates are R_QUALITY_UNAVAILABLE · the quality source "
        "is missing or too narrow again" % (n_unknown, n_class))


# ═══════════════════════════════════════════════════════════════════════
# 7 · Pipeline ordering · a new position must exist before risk runs
# ═══════════════════════════════════════════════════════════════════════

def test_registry_materialization_precedes_risk_and_lifecycle():
    """> "registry write -> step 74 · dynamic risk -> step 53 ·
    >  lifecycle/CURRENT -> step 58. So a genuinely new candidate can be
    >  created AFTER the system has already calculated risk and CURRENT."

    A position admitted today did not exist when stops were computed, so
    it arrived with `stop none` (JIOFIN 2026-09-08) and could never appear
    on its own day.
    """
    names = [s["name"] for s in _steps()]
    assert "registry_materializer" in names
    i_mat = names.index("registry_materializer")
    assert i_mat < names.index("dynamic_risk_v2_both_markets"), (
        "stops are computed before today's positions exist")
    assert i_mat < names.index("canonical_daily_lifecycle"), (
        "CURRENT is rendered before today's positions exist")
    assert i_mat < names.index("telegram"), (
        "the delivery step must no longer be the first writer")


def test_materializer_owns_no_decision_logic():
    """It moves WHEN the transition happens, never WHAT is admitted.

    Reimplementing admission here would create a second definition of
    "is this admissible" - the exact failure this month's delivery rewrite
    exists to remove. It must delegate to the existing path.
    """
    import ast
    import inspect
    from backend.delivery.lifecycle import registry_materializer as rm
    tree = ast.parse(inspect.getsource(rm))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) \
                and ast.get_docstring(node):
            node.body = node.body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "_collect_rows_for_market" in code, (
        "the materializer must delegate to the existing admission path")
    for forbidden in ("CONF_FLOOR", "should_rotate", "ROTATION_EDGE",
                      "0.55", "get_or_create"):
        assert forbidden not in code, (
            "the materializer reimplements a decision: %r" % forbidden)


@pytest.mark.parametrize("market", MARKETS)
def test_materializer_is_idempotent(market):
    """get_or_create returns an existing ACTIVE unchanged · running the
    transition twice in a day must be a no-op the second time, which is
    what makes moving it safe."""
    from datetime import date as _date

    from backend.delivery.lifecycle import registry_materializer as rm
    if rm.load(ROOT, market) is None:
        pytest.skip("materialization not produced for %s" % market)
    # Idempotence is a property of the SECOND run, not of a stored artifact
    # from a first run that legitimately admitted positions.
    #
    # This previously called materialize ONCE and assumed some earlier run
    # had already covered today's date. That assumption broke the moment
    # the calendar rolled over: on a fresh date the first call correctly
    # admits the day's candidates, so the test failed on a system working
    # exactly as designed. Run it twice here and compare the second to the
    # first · then the property is tested, not the environment.
    asof = _date.today().isoformat()
    first = rm.materialize(ROOT, market, asof)
    assert not first.get("error"), first.get("error")
    second = rm.materialize(ROOT, market, asof)
    assert not second.get("error"), second.get("error")
    assert second["n_active_before"] == second["n_active_after"], (
        "a repeat run changed the active set: %d -> %d"
        % (second["n_active_before"], second["n_active_after"]))
    assert second["n_newly_materialized"] == 0, (
        "a repeat run created %d position(s) (first run created %d)"
        % (second["n_newly_materialized"], first.get("n_newly_materialized", 0)))
    assert second["n_active_before"] == first["n_active_after"], (
        "the second run did not start from where the first ended: %d vs %d"
        % (second["n_active_before"], first["n_active_after"]))


# ═══════════════════════════════════════════════════════════════════════
# 8 · A HOLD is not an admission
# ═══════════════════════════════════════════════════════════════════════

def test_only_buy_family_may_create_a_position():
    """get_or_create ran for EVERY rendered row, so a HOLD - or an EXIT -
    opened a brand-new registry position. The permanent bans masked it;
    releasing them admitted 23 positions on non-BUY signals in one run.

    They are filtered from CURRENT today because NEW requires a BUY-family
    signal, but tomorrow they age into ACTIVE, which carries no such
    requirement.
    """
    src = (ROOT / "backend" / "delivery" / "telegram"
           / "detail_xlsx.py").read_text(encoding="utf-8")
    assert "_BUY_FAMILY_ADMIT" in src, "no admission gate on position creation"
    assert "_has_active" in src, (
        "an EXISTING position must still be fetched on a HOLD signal")


def test_lifecycle_new_requires_a_buy_family_signal():
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    assert lc.is_investable(lc.ACTION_NEW, "BUY")
    assert lc.is_investable(lc.ACTION_NEW, "STRONG BUY")
    assert not lc.is_investable(lc.ACTION_NEW, "HOLD")
    assert not lc.is_investable(lc.ACTION_NEW, "EXIT")
    assert not lc.is_investable(lc.ACTION_NEW, "")
    # An EXISTING position keeps rendering whatever today's signal says.
    assert lc.is_investable(lc.ACTION_ACTIVE, "HOLD")
    assert lc.is_investable(lc.ACTION_ACTIVE_PLUS, "HOLD")


@pytest.mark.parametrize("market", MARKETS)
def test_no_new_row_lacks_a_buy_signal(market):
    from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
    d = lc.load(ROOT, market)
    if d is None:
        pytest.skip("lifecycle not produced")
    bad = [r["ticker"] for r in d["current"]
           if r["action"] == "NEW"
           and str(r.get("reason", "")).split("\u00b7")[0].strip().upper()
           not in lc.BUY_FAMILY]
    assert not bad, "NEW rows without a BUY-family signal: %s" % bad
