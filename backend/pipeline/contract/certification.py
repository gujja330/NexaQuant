"""GATE 5 · DELIVERY READY   +   the run certification.

One report, printed identically by the manual morning run, the manual
evening run and the scheduled CI run - because all three execute the same
contracts. A separate "CI check" is how the two paths drift until only one
of them is telling the truth.

WHY THE REPORT LEADS WITH THE FIRST FAILURE
--------------------------------------------
A wall of red crosses costs an hour of reverse-engineering. The pipeline
knows which contract broke FIRST and that everything after it is a
consequence, so it says so and stops. Downstream stages are reported as
NOT RUN rather than as additional failures.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.pipeline.contract.run_context import RunContext, StageContract

SCHEMA_VERSION = "aegis.pipeline.contract.certification.v1"

STAGE_LIFECYCLE = "LIFECYCLE_READY"
STAGE_DELIVERY = "DELIVERY_READY"

BAR = "═" * 60


def check_lifecycle_ready(ctx: RunContext) -> StageContract:
    """The canonical lifecycle is the ONLY producer of CURRENT / EXIT."""
    import time
    t0 = time.time()
    c = ctx.stage(STAGE_LIFECYCLE)
    root, m, asof = Path(ctx.root), ctx.market, ctx.requested_asof

    why = ctx.upstream_ok("DECISION_READY")
    if why:
        c.block("UPSTREAM_NOT_READY", why)
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    try:
        from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
        d = lc.load(root, m) or {}
    except Exception as e:
        c.block("LIFECYCLE_UNREADABLE", "%s: %s" % (type(e).__name__, e))
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    if not d:
        c.block("LIFECYCLE_MISSING", "no canonical lifecycle dataset for %s" % m)
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    c.output_asof = str(d.get("asof"))[:10]
    if c.output_asof != str(asof)[:10]:
        c.block("LIFECYCLE_ASOF_MISMATCH",
                "lifecycle is as-of %s but this run is %s"
                % (c.output_asof, asof))

    counts = d.get("counts") or {}
    c.row_count = int(counts.get("current_total", 0))
    c.detail["counts"] = {k: counts.get(k) for k in
                          ("current_total", "new", "active_plus", "active",
                           "exit_history_total", "stop_breached")}
    # CURRENT is breach-free by construction · non-zero means routing broke.
    if counts.get("stop_breached"):
        c.block("BREACHED_IN_CURRENT",
                "%d breached position(s) reached CURRENT"
                % counts["stop_breached"])
    c.elapsed_s = round(time.time() - t0, 2)
    return ctx.record(c.ok())


def check_delivery_ready(ctx: RunContext) -> StageContract:
    """GATE 5 · every published surface derives from the canonical state."""
    import time
    t0 = time.time()
    c = ctx.stage(STAGE_DELIVERY)
    root, m = Path(ctx.root), ctx.market

    why = ctx.upstream_ok(STAGE_LIFECYCLE)
    if why:
        c.block("UPSTREAM_NOT_READY", why)
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    try:
        from backend.delivery import delivery_gate as dg
        d = dg.decide(root, m)
        c.detail["gate_verdict"] = d.verdict
        c.detail["override_used"] = d.override_used
        c.detail["blocking_codes"] = list(d.blocking_codes)
        if d.override_used:
            c.block("DELIVERY_OVERRIDE_USED",
                    "the gate allowed a send it would otherwise have blocked")
        if d.verdict != "ALLOW":
            c.block("DELIVERY_GATE_BLOCK",
                    "; ".join(d.reasons[:2]) or "gate blocked")
    except Exception as e:
        c.block("DELIVERY_GATE_ERROR", "%s: %s" % (type(e).__name__, e))

    try:
        wr = root / "reports" / "context" / ("wave_regression_%s.json" % m)
        if wr.exists():
            j = json.loads(wr.read_text(encoding="utf-8"))
            chk = {x["code"]: x["status"] for x in j.get("checks", [])}
            c.detail["A19"] = chk.get("A19")
            c.detail["A23"] = chk.get("A23")
            for code in ("A19", "A23"):
                if chk.get(code) == "FAIL":
                    c.block("ACCEPTANCE_%s_FAIL" % code,
                            "%s failed on the rendered workbook" % code)
    except Exception:
        pass

    # R3 must remain shadow · zero production writes.
    try:
        from backend.research.r3_program import shadow as r3
        rep = r3.load(root, m) or {}
        c.detail["r3_production_writes"] = rep.get("production_writes", 0)
        if rep.get("production_writes"):
            c.block("R3_WROTE_TO_PRODUCTION",
                    "R3 is shadow-only and reported %d production write(s)"
                    % rep["production_writes"])
    except Exception:
        pass

    c.elapsed_s = round(time.time() - t0, 2)
    return ctx.record(c.ok())


# ── the report ──────────────────────────────────────────────────────────

def _row(label: str, value, status: Optional[str] = None) -> str:
    v = "" if value is None else str(value)
    s = "" if status is None else status
    return "  %-26s %-16s %s" % (label, v, s)


def render(ctx: RunContext) -> str:
    L = [BAR, "AEGIS DAILY RUN CERTIFICATION",
         "Run: %s" % ctx.run_id,
         "Requested ASOF: %s   ·   trigger: %s" % (ctx.requested_asof,
                                                   ctx.trigger),
         BAR]

    order = ["DATA_READY", "INTERMARKET", "FEATURES_READY", "SCORES_READY",
             "DECISION_READY", STAGE_LIFECYCLE, "FIELDS_COMPLETE",
             STAGE_DELIVERY]
    first_fail = ctx.first_failure
    hit = False

    for name in order:
        c = ctx.get(name)
        L.append("")
        if c is None:
            L.append("%s" % name)
            L.append(_row("(not run)", "", "SKIP"))
            continue
        L.append("%s" % name)
        if name == "DATA_READY":
            for src, info in (c.detail.get("sources") or {}).items():
                if "asof" in info:
                    txt = "asof %s · age %s" % (info.get("asof"),
                                                  info.get("age_days"))
                    # Price bars state WHERE the date came from and how
                    # broad it is. "asof 2026-09-10 · age 0" was printed
                    # for two days over data that ended 2026-09-09,
                    # because the old check read file mtimes. An operator
                    # must be able to see the bar date itself.
                    if src == "price_bars" and info.get("measured_from"):
                        txt += (" · median %s · %s/%s files (%s)"
                                % (info.get("median_asof"),
                                   info.get("n_readable"),
                                   info.get("n_files"),
                                   info.get("scope")))
                    L.append(_row(src, txt))
                else:
                    L.append(_row(src, info.get("size")))
        elif name == "INTERMARKET":
            for r in (c.detail.get("series") or []):
                mark = {"FRESH": "✓", "STALE": "⚠", "MISSING": "✗"}.get(
                    r["verdict"], "?")
                L.append(_row(r["series"], r["asof"] or "—",
                              mark + (" critical" if r["critical"] else "")))
            for k, why in sorted((c.detail.get("not_collected") or {}).items()):
                L.append(_row(k, "—", "✗ not collected"))
            L.append(_row("COMPLETENESS", "%s%% (%s/%s fresh)"
                          % (c.detail.get("completeness_pct"),
                             c.detail.get("n_fresh"),
                             c.detail.get("n_series"))))
        elif name == "FEATURES_READY":
            L.append(_row("requested snapshot", c.detail.get("requested_snapshot")))
            L.append(_row("available snapshot", c.detail.get("available_snapshot")))
            L.append(_row("rows / tickers", "%d / %d" % (c.row_count,
                                                         c.ticker_count)))
            L.append(_row("coverage", "%s%%" % c.coverage_pct))
            L.append(_row("duplicates", c.duplicate_count))
            L.append(_row("retention vs prev", "%s%%"
                          % c.detail.get("retention_pct")))
        elif name == "SCORES_READY":
            L.append(_row("scored", c.ticker_count))
            L.append(_row("expected", c.expected_ticker_count))
            L.append(_row("would-be NEW", c.detail.get("would_be_new")))
            L.append(_row("lost to truncation",
                          len(c.detail.get("lost_to_truncation") or [])))
        elif name == "DECISION_READY":
            L.append(_row("scored", c.row_count))
            L.append(_row("terminal dispositions",
                          c.row_count - c.missing_count))
            L.append(_row("orphans", c.missing_count))
            L.append(_row("defect tickers",
                          len(c.detail.get("defect_tickers") or [])))
        elif name == STAGE_LIFECYCLE:
            for k, v in (c.detail.get("counts") or {}).items():
                L.append(_row(k, v))
        elif name == "FIELDS_COMPLETE":
            L.append(_row("rows checked", c.row_count))
            L.append(_row("required gaps", c.detail.get("n_required_gaps")))
            L.append(_row("expected gaps", c.detail.get("n_expected_gaps")))
            L.append(_row("exit sector populated",
                          "%s / %s" % (c.detail.get("exit_sector_populated"),
                                       c.detail.get("exit_rows"))))
        elif name == STAGE_DELIVERY:
            L.append(_row("gate", c.detail.get("gate_verdict")))
            L.append(_row("override", c.detail.get("override_used")))
            L.append(_row("A19 / A23", "%s / %s" % (c.detail.get("A19"),
                                                    c.detail.get("A23"))))
            L.append(_row("R3 production writes",
                          c.detail.get("r3_production_writes")))
        L.append(_row("", "", "→ %s   (%.2fs)" % (c.status, c.elapsed_s)))
        for f in c.failures:
            L.append("    ✗ %s" % f["code"])
            L.append("      %s" % f["message"])
        if c.status == "BLOCK":
            hit = True
            # Everything after the first failure is a consequence.
            remaining = order[order.index(name) + 1:]
            if remaining:
                L.append("")
                L.append("  downstream NOT RUN: %s" % ", ".join(remaining))
            break

    total = sum(c.elapsed_s for c in ctx.contracts)
    L += ["", BAR, "RUNTIME"]
    for c in ctx.contracts:
        L.append(_row(c.stage, "%.2fs" % c.elapsed_s))
    L.append(_row("TOTAL", "%.2fs" % total))
    L.append(BAR)
    if hit and first_fail:
        L.append("FINAL: ❌ BLOCKED")
        L.append("FIRST FAILURE: %s  (%s)" % (first_fail["code"],
                                              first_fail["stage"]))
        L.append("No downstream stages executed. No XLSX. No Telegram.")
    else:
        L.append("FINAL: ✅ CERTIFIED")
    L.append(BAR)
    return "\n".join(L)


def emit(ctx: RunContext, text: str) -> Path:
    p = (Path(ctx.root) / "reports" / "context"
         / ("run_certification_%s.txt" % ctx.market))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    ctx.emit()
    return p
