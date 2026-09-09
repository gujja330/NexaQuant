"""GATE 3 · SCORES READY   and   GATE 4 · DECISION READY.

    516 universe -> 516 scored -> 516 terminal dispositions

PRESENTATION TRUNCATION MUST NEVER PRECEDE ELIGIBILITY
-------------------------------------------------------
Production persists head(10) + tail(5) = 15 rows from the ensemble, and
the eligibility engine sees only those. On 2026-09-09 that discarded
COP, MPC and TRV - three BUY-family candidates at confidence 0.6045 that
had cleared every published gate. They did not fail a rule. They were
never offered to the rule.

Ranking to 15 for display is fine. Ranking to 15 BEFORE the decision is
made is data loss wearing the costume of a business rule, and it is
invisible downstream: the workbook shows a short list and looks correct.

CONSERVATION OF CANDIDATES
--------------------------
Every ticker that entered scoring must leave with exactly one terminal
disposition. If 516 are scored and 515 are accounted for, the run is red -
not "probably fine", not "one stock missing". That single invariant is
what turns OXY from a thing someone notices into a thing the pipeline
refuses to ship around.

OXY was `L7_eligible_no_registry`: it cleared every gate, was inside the
15 production sees, and no registry entry exists. The diagnostic already
found it. Nothing stopped.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.pipeline.contract.run_context import RunContext, StageContract

SCHEMA_VERSION = "aegis.pipeline.contract.scoring.v1"

STAGE_SCORES = "SCORES_READY"
STAGE_DECISION = "DECISION_READY"

# Every terminal state a scored ticker may legitimately end in. A ticker
# that matches none of these is an ORPHAN and blocks the run.
TERMINAL_DISPOSITIONS = {
    "L0_not_scored",            # never entered scoring · counted separately
    "L1_truncated",             # DEFECT · kept terminal so it is countable
    "L2_hold",
    "L3_disagreement",
    "L4_confidence",
    "L5_regime",
    "L6_not_buy",
    "L7_eligible_no_registry",  # DEFECT
    "L8_registry_closed",
    "L9_stop_breached",
    "L10_in_current",
}

# Dispositions that mean a qualified candidate was LOST rather than judged.
DEFECT_DISPOSITIONS = {"L1_truncated", "L7_eligible_no_registry"}

MIN_SCORED_COVERAGE_PCT = 99.0


def _norm(t) -> str:
    """One ticker spelling for the conservation check.

    Matches `why_not_current._t` exactly: upper, split on the first dot.
    That collapses MCX.NS -> MCX and also BRK.B -> BRK, which is lossy for
    US class shares - but a conservation check must compare against the
    SAME normalisation the funnel used, or it reports phantom orphans
    (BF.B and BRK.B were flagged as lost when both were present under
    their collapsed names).

    Divergence between the two spellings is a real issue worth fixing at
    the source; inventing a third normalisation here would only hide it.
    """
    return str(t or "").upper().split(".", 1)[0].strip()


def _shadow(root: Path, market: str) -> dict:
    try:
        from backend.research.shadow import full_universe_shadow as fus
        return fus.load(Path(root), market.lower()) or {}
    except Exception:
        return {}


def _cooling(root: Path, market: str) -> dict:
    """Tickers blocked from re-entry by the governed cooling period.

    COOLING is a legitimate terminal state, not a defect. COP closed on
    2026-09-04 and production called it BUY again on 2026-09-09 - five
    days into a seven-day cooling window. The funnel has no view of
    cooling, so it labelled that `L7_eligible_no_registry` and the gate
    called it a lost candidate.

    A conservation invariant that cannot tell "deliberately withheld"
    from "silently dropped" will cry wolf until someone switches it off,
    which is the worst outcome of all. So the cooling window is consulted
    directly, and a cooling name is ACCOUNTED FOR rather than lost.
    """
    out = {}
    try:
        from backend.research import opportunity_registry as oreg
        reg = oreg.load_all(Path(root))
        by_ticker = {}
        for opps in reg.values():
            for o in opps:
                if str(o.market).lower() != market.lower():
                    continue
                by_ticker.setdefault(_norm(o.ticker), []).append(o)
        for t, opps in by_ticker.items():
            try:
                blocked, reason = oreg.is_re_entry_blocked(
                    opps, str(_today()), Path(root))
            except Exception:
                continue
            if blocked:
                out[t] = str(reason)
    except Exception:
        pass
    return out


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _production_buys(root: Path, market: str) -> set:
    """The BUY-family names PRODUCTION itself decided · the only authority
    on whether production lost a candidate."""
    import json
    fam = {"BUY", "STRONG BUY", "STRONG_BUY", "ACCUMULATE", "ADD"}
    for rel in ("usa/reports/recommendations.json" if market.lower() == "usa"
                else "reports/recommendations.json",):
        p = Path(root) / rel
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out = set()
        for r in d.get("recommendations") or []:
            a = str(r.get("action") or r.get("Action") or "").upper().strip()
            if a in fam:
                out.add(_norm(r.get("ticker") or r.get("Stock")))
        return out
    return set()


def _funnel(root: Path, market: str) -> dict:
    try:
        from backend.delivery.lifecycle import why_not_current as wnc
        return wnc.load(Path(root), market.lower()) or {}
    except Exception:
        return {}


def check_scores_ready(ctx: RunContext) -> StageContract:
    """GATE 3 · the FULL universe was scored, and nothing was cut early."""
    import time
    t0 = time.time()
    c = ctx.stage(STAGE_SCORES)
    root, m, asof = Path(ctx.root), ctx.market, ctx.requested_asof

    why = ctx.upstream_ok("FEATURES_READY")
    if why:
        c.block("UPSTREAM_NOT_READY", why)
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    sh = _shadow(root, m)
    rows = sh.get("rows") or []
    c.output_asof = sh.get("asof")
    c.row_count = len(rows)
    c.ticker_count = len({_norm(r.get("ticker")) for r in rows})

    if not rows:
        c.block("SCORES_MISSING",
                "no full-universe scoring artifact for %s" % m)
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    # The scoring artifact must be for THIS run's date.
    if str(c.output_asof)[:10] != str(asof)[:10]:
        c.block("SCORE_ASOF_MISMATCH",
                "scores are as-of %s but this run is %s · scoring did not "
                "run on today's snapshot" % (c.output_asof, asof))

    fs = ctx.get("FEATURES_READY")
    exp = (fs.ticker_count if fs and fs.ticker_count
           else fs.expected_ticker_count if fs else 0)
    c.expected_ticker_count = exp
    if exp:
        c.coverage_pct = round(c.ticker_count / exp * 100, 2)
        c.missing_count = max(0, exp - c.ticker_count)
        if c.coverage_pct < MIN_SCORED_COVERAGE_PCT:
            c.block("SCORE_COVERAGE_LOW",
                    "%d of %d featured names scored (%.1f%% · floor %.0f%%)"
                    % (c.ticker_count, exp, c.coverage_pct,
                       MIN_SCORED_COVERAGE_PCT))

    # Truncation BEFORE eligibility · the COP/MPC/TRV defect.
    lost = [r for r in rows
            if r.get("would_be_new") and not r.get("in_persisted_15")]
    c.detail["would_be_new"] = sum(1 for r in rows if r.get("would_be_new"))
    c.detail["lost_to_truncation"] = [_norm(r.get("ticker")) for r in lost]
    if lost:
        c.block("TRUNCATION_BEFORE_ELIGIBILITY",
                "%d qualified candidate(s) never reached the eligibility "
                "engine because only 15 rows are persisted: %s · ranking to "
                "15 is a PRESENTATION limit and must not precede the decision"
                % (len(lost), ", ".join(sorted(
                    _norm(r.get("ticker")) for r in lost))))

    c.elapsed_s = round(time.time() - t0, 2)
    return ctx.record(c.ok())


def check_decision_ready(ctx: RunContext) -> StageContract:
    """GATE 4 · conservation · every scored ticker has ONE terminal state."""
    import time
    t0 = time.time()
    c = ctx.stage(STAGE_DECISION)
    root, m = Path(ctx.root), ctx.market

    why = ctx.upstream_ok(STAGE_SCORES)
    if why:
        c.block("UPSTREAM_NOT_READY", why)
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    sh = _shadow(root, m)
    scored = {_norm(r.get("ticker")) for r in (sh.get("rows") or [])}
    fn = _funnel(root, m)
    verdicts = fn.get("tickers") or fn.get("verdicts") or fn.get("rows") or []

    disp = {}
    for v in verdicts:
        t = _norm(v.get("ticker"))
        if t:
            disp.setdefault(t, []).append(str(v.get("verdict")))

    c.row_count = len(scored)
    c.ticker_count = len(scored)
    c.expected_ticker_count = len(scored)

    orphans = sorted(scored - set(disp))
    multi = sorted(t for t, vs in disp.items() if len(set(vs)) > 1)
    unknown = sorted({v for vs in disp.values() for v in vs}
                     - TERMINAL_DISPOSITIONS)
    defects = sorted(t for t, vs in disp.items()
                     if set(vs) & DEFECT_DISPOSITIONS)

    from collections import Counter
    c.detail["disposition_counts"] = dict(
        Counter(vs[0] for vs in disp.values()))
    c.detail["orphans"] = orphans[:20]
    c.detail["multi_disposition"] = multi[:20]
    c.detail["defect_tickers"] = defects[:20]
    c.missing_count = len(orphans)

    if orphans:
        c.block("CANDIDATE_CONSERVATION_FAILED",
                "%d of %d scored ticker(s) have NO terminal disposition: %s"
                % (len(orphans), len(scored), ", ".join(orphans[:8])))
    if multi:
        c.block("MULTIPLE_DISPOSITIONS",
                "%d ticker(s) hold more than one terminal state: %s"
                % (len(multi), ", ".join(multi[:8])))
    if unknown:
        c.block("UNKNOWN_DISPOSITION",
                "verdict(s) outside the declared terminal set: %s"
                % ", ".join(unknown[:8]))
    # ── shadow vs production · WHOSE verdict is this? ───────────────
    #
    # `L7_eligible_no_registry` is derived from the full-universe SHADOW,
    # and the shadow RE-TRAINS the model factory in-process rather than
    # reading production's persisted ensemble. Its scores are therefore
    # its own run, not production's. On 2026-09-09 it called COP, DVN,
    # MPC and OXY BUY while production - on the same features, same
    # regime, now seeing all 516 names - called every one HOLD.
    #
    # Blocking production on a research artifact's disagreement would be
    # letting R3-style evidence gate R2, which is exactly backwards. So
    # the divergence is REPORTED and named; only a candidate that
    # PRODUCTION itself called BUY and then failed to register is a lost
    # candidate, and that still blocks.
    prod_buys = _production_buys(root, m)
    cooling = _cooling(root, m)
    truly_lost = sorted(t for t in defects
                        if t in prod_buys and t not in cooling)
    c.detail["cooling"] = {t: cooling[t] for t in defects if t in cooling}
    c.detail["shadow_production_divergence"] = sorted(
        set(defects) - set(truly_lost))
    c.detail["production_buy_count"] = len(prod_buys)
    if truly_lost:
        c.block("ELIGIBLE_CANDIDATE_LOST",
                "%d candidate(s) PRODUCTION called BUY and did not reach the "
                "registry: %s · a BUY may never simply disappear"
                % (len(truly_lost), ", ".join(truly_lost[:8])))

    c.elapsed_s = round(time.time() - t0, 2)
    return ctx.record(c.ok())
