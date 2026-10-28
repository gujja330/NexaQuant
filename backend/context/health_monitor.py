"""Context Health Monitor · Guard 7.

Per operator directive 2026-08-05: "every report should flow and run daily
in pipeline · build guards to check thoroughly before sending notifications
· every report is a guard for our engines · ensure every engine works properly."

This is the META-GUARD that audits every context-layer output BEFORE the
daily XLSX ships to Telegram. If a critical engine is missing OR stale
(asof mismatch) OR empty (file exists but zero real data), the guard
either warns loudly or blocks the send entirely.

Called by scripts/telegram_command_center_send.py right before the XLSX
send. Emits:
    reports/context/health_monitor.json  · verdict + per-engine details

Verdict levels:
    · GREEN   · all critical engines fresh + populated
    · YELLOW  · some non-critical stale · notify but allow send
    · RED     · critical engine missing/stale · block send unless --force

Per Guard 6 pattern (payload asof freshness) · this is Guard 7 for
context freshness.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


# (relative_path, criticality, freshness_days, min_bytes, market)
# criticality: "CRITICAL" · "IMPORTANT" · "OPTIONAL"
# freshness_days: max age of the file (mtime) OR max age of asof-in-file · which is smaller
# min_bytes: file must be at least this big (skeleton files fail)
# market: None = applies to BOTH · "india" / "usa" = that market only
#
# CEO 2026-10-28 · THE MARKET SCOPE IS WHY USA HAS NEVER DELIVERED.
#
# This registry was one flat list and run_health_check() took no market, so
# EVERY market was graded against EVERY market's files. On the USA runner
# that meant the send was blocked by India's artifacts:
#
#   [guard7:health] BLOCKING send · 3 critical engines failed
#     ✗ reports/context/cil_run_india.json       age 49.5d > threshold 1d
#     ✗ reports/research/health_scores_india.json age 49.5d > threshold 1d
#     ✗ reports/fii_dii_flow.json                 age 49.5d > threshold 2d
#
# fii_dii_flow is FII/DII equity flows - an India-only concept with no USA
# meaning whatsoever, yet it was a CRITICAL blocker for the USA send.
#
# India never hit this because India's own pipeline REGENERATES
# cil_run_india.json during its run, so the file is fresh on the India
# runner. The USA workflow does not run India's CIL engine, so the USA
# runner only ever sees the committed copy - frozen at 2026-09-08. Every
# USA run therefore blocked, which is exactly the "USA has never worked"
# report. Same bug class as the market-blind path loop fixed in cc72d4df.
#
# The guard is NOT weakened for USA: the India-only rows are replaced by
# their USA counterparts (cil_run_usa, health_scores_usa), both of which
# exist and were measured fresh (1.6 MB and 196 KB, mtime 2026-10-28 08:47).
# portfolio_snapshot_usa.json does NOT exist, so it stays India-only rather
# than being added as a row that would fail MISSING forever.

ENGINES = [
    # Existing engines (Waves 4-5) · ALL now CRITICAL per operator directive
    # "every report is a guard for our engines · ensure every engine works properly"
    ("reports/macro_regime.json",           "CRITICAL",  5, 400, None),
    ("reports/sector_rotation.json",        "CRITICAL",  5, 800, None),
    ("reports/volatility_intelligence.json", "CRITICAL",  5, 400, None),
    ("reports/bond_intelligence.json",       "CRITICAL",  5, 400, None),
    ("reports/currency_intelligence.json",   "CRITICAL",  5, 400, None),
    ("reports/commodity_intelligence.json",  "CRITICAL",  5, 400, None),
    ("reports/market_intelligence.json",     "CRITICAL",  5, 800, None),
    ("reports/ai_market_narrative.json",     "CRITICAL",  5, 400, None),
    ("reports/macro_history.parquet",        "IMPORTANT", 10, 1000, None),
    ("reports/factor_library.parquet",       "IMPORTANT", 10, 1000, None),
    # CIL layer engines (shipped 2026-08-05)
    ("reports/context/global_overnight.json", "CRITICAL",  1, 400, None),
    ("reports/context/market_breadth.json",   "CRITICAL",  1, 400, None),
    ("reports/context/economic_calendar.jsonl", "CRITICAL",  5, 400, None),
    ("reports/context/cil_run_india.json",    "CRITICAL",  1, 400, "india"),
    ("reports/context/cil_run_usa.json",      "CRITICAL",  1, 400, "usa"),
    # R006 · Portfolio state (fires from R2 pipeline via ssot/run.py)
    # No USA counterpart exists on disk · deliberately NOT mirrored, because
    # a row for a file nothing writes fails MISSING on every run forever.
    ("reports/research/portfolio_snapshot_india.json", "IMPORTANT", 3, 200,
     "india"),
    ("reports/research/rank_history.jsonl",    "CRITICAL",  1, 100, None),
    # Sprint outputs
    ("reports/research/health_scores_india.json", "CRITICAL", 1, 400,
     "india"),
    ("reports/research/health_scores_usa.json",   "CRITICAL", 1, 400,
     "usa"),
    # Newly-built context engines
    # FII/DII = Foreign/Domestic Institutional Investor equity flows. This is
    # an NSE concept. It has no USA analogue, so it is India-scoped rather
    # than mirrored.
    ("reports/fii_dii_flow.json",              "CRITICAL",  2, 200, "india"),
    ("reports/correlation_matrix.json",        "IMPORTANT", 5, 400, None),
    ("reports/ai_news_narrative.json",         "IMPORTANT", 3, 300, None),
    # Sprint H · USA Runner 1 defensive derivative (operator lock blocker)
    # Was graded against INDIA runs too, where nothing regenerates it.
    ("usa/reports/runner1_orphans.json",       "CRITICAL",  1, 400, "usa"),
]


@dataclass
class EngineHealth:
    path: str
    criticality: str
    exists: bool
    size_bytes: int
    mtime_age_days: float | None
    asof_age_days: float | None
    verdict: str            # PASS · STALE · EMPTY · MISSING
    reason: str


def _check_one(root: Path, rel: str, criticality: str,
                    freshness_days: int, min_bytes: int) -> EngineHealth:
    p = root / rel
    if not p.exists():
        return EngineHealth(path=rel, criticality=criticality, exists=False,
                                    size_bytes=0, mtime_age_days=None, asof_age_days=None,
                                    verdict="MISSING", reason="file does not exist")
    size = p.stat().st_size
    mtime_age = (datetime.now(timezone.utc).timestamp() - p.stat().st_mtime) / 86400.0
    asof_age = None
    if p.suffix == ".json":
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            asof_str = d.get("asof") or d.get("as_of") or ""
            if asof_str:
                asof_dt = date.fromisoformat(asof_str[:10])
                asof_age = (date.today() - asof_dt).days
        except Exception:
            pass
    if size < min_bytes:
        return EngineHealth(path=rel, criticality=criticality, exists=True,
                                    size_bytes=size, mtime_age_days=round(mtime_age, 1),
                                    asof_age_days=asof_age,
                                    verdict="EMPTY",
                                    reason=f"size {size}B < min {min_bytes}B (likely skeleton)")
    effective_age = min(x for x in (mtime_age, asof_age) if x is not None) \
                             if any(x is not None for x in (mtime_age, asof_age)) \
                             else mtime_age
    if effective_age > freshness_days:
        return EngineHealth(path=rel, criticality=criticality, exists=True,
                                    size_bytes=size, mtime_age_days=round(mtime_age, 1),
                                    asof_age_days=asof_age,
                                    verdict="STALE",
                                    reason=f"age {effective_age:.1f}d > threshold {freshness_days}d")
    return EngineHealth(path=rel, criticality=criticality, exists=True,
                                size_bytes=size, mtime_age_days=round(mtime_age, 1),
                                asof_age_days=asof_age, verdict="PASS", reason="ok")


def run_health_check(root: Path, market: str | None = None) -> dict:
    """Grade the context engines that apply to `market`.

    market=None grades EVERY row, which is the old behaviour and is what a
    `--market both` send still wants. Passing "india" or "usa" drops the
    other market's rows - a USA send must not be blocked by an India
    artifact that nothing on the USA runner regenerates.

    The scope is recorded in the payload so a GREEN verdict always states
    what it actually graded. A health check that silently narrowed its own
    coverage would be worse than the bug it replaced.
    """
    scope = (market or "").strip().lower() or None
    if scope not in (None, "india", "usa"):
        raise ValueError(
            "market must be None, 'india' or 'usa' · got %r. A typo here "
            "would silently skip every scoped row and report GREEN."
            % (market,))
    results, skipped = [], []
    for path, crit, days, min_b, mkt in ENGINES:
        if scope is not None and mkt is not None and mkt != scope:
            skipped.append(path)
            continue
        results.append(_check_one(root, path, crit, days, min_b))

    # Verdict aggregation
    critical_fails = [r for r in results
                             if r.criticality == "CRITICAL"
                             and r.verdict in ("MISSING", "STALE", "EMPTY")]
    important_fails = [r for r in results
                              if r.criticality == "IMPORTANT"
                              and r.verdict in ("MISSING", "STALE", "EMPTY")]
    if critical_fails:
        overall = "RED"
    elif important_fails:
        overall = "YELLOW"
    else:
        overall = "GREEN"

    # 2026-08-11 CEO P0 pipeline hygiene · surface important_fails BY NAME
    # in the payload + summary. "1 important stale" without naming what is
    # stale is not operationally useful.
    return {
        "engine":        "aegis.context.health_monitor.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        # Scope is first-class: a GREEN that graded 18 of 24 rows must say so.
        "market_scope":  scope or "all",
        "n_skipped_other_market": len(skipped),
        "skipped_other_market":   skipped,
        "overall_verdict": overall,
        "n_engines":     len(results),
        "n_pass":        sum(1 for r in results if r.verdict == "PASS"),
        "n_critical_fails": len(critical_fails),
        "n_important_fails": len(important_fails),
        "critical_fails":    [asdict(r) for r in critical_fails],
        "important_fails":   [asdict(r) for r in important_fails],
        "all_engines":       [asdict(r) for r in results],
        "recommendation": {
            "GREEN":  "All critical engines healthy · safe to send",
            "YELLOW": "Non-critical stale · notify operator in caption · allow send",
            "RED":    "Critical engine(s) missing/stale · block send unless "
                          "operator overrides with SEND_FORCE_STALE=1",
        }.get(overall, "unknown"),
    }


def emit(root: Path, payload: dict) -> Path:
    """Write the report · scoped runs ALSO get their own file.

    health_monitor.json stays the canonical path because
    backend/portfolio/fresh_opportunities.py reads it by that name. But two
    markets writing one file means the second overwrites the first and the
    survivor's verdict is attributed to whichever ran last, so a scoped run
    additionally writes health_monitor_<market>.json.
    """
    d = root / "reports" / "context"
    d.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    p = d / "health_monitor.json"
    p.write_text(blob, encoding="utf-8")
    scope = str(payload.get("market_scope") or "all").lower()
    if scope in ("india", "usa"):
        (d / ("health_monitor_%s.json" % scope)).write_text(
            blob, encoding="utf-8")
    return p


def render_summary(payload: dict) -> str:
    """Compact one-liner for Telegram caption or CI log."""
    v = payload.get("overall_verdict", "?")
    n = payload.get("n_engines", 0)
    p = payload.get("n_pass", 0)
    cf = payload.get("n_critical_fails", 0)
    # Always say which market was graded · "18/18 healthy" means something
    # different when 6 rows belonging to the other market were not checked.
    sc = str(payload.get("market_scope") or "all").lower()
    sk = int(payload.get("n_skipped_other_market") or 0)
    tag = f"[{sc}]" + (f" (+{sk} other-market rows not graded)" if sk else "")
    if v == "GREEN":
        return f"🟢 Context Health {tag}: {p}/{n} engines healthy"
    if v == "YELLOW":
        # 2026-08-11 CEO P0 · name the important-stale item(s) so operator
        # doesn't have to open the JSON file to see WHAT is stale.
        imp = payload.get("important_fails") or []
        names = [f"{i.get('path','?')} (age {i.get('mtime_age_days',0):.1f}d)"
                     for i in imp[:5]]
        tail = f" · +{len(imp)-5} more" if len(imp) > 5 else ""
        detail = f" · stale: {' | '.join(names)}{tail}" if names else ""
        return (f"🟡 Context Health {tag}: {p}/{n} · {cf} critical · "
                    f"{payload.get('n_important_fails', 0)} important stale{detail}")
    # RED path · also name the critical fails
    crit = payload.get("critical_fails") or []
    crit_names = [i.get("path","?") for i in crit[:5]]
    crit_detail = f" · CRITICAL: {' | '.join(crit_names)}" if crit_names else ""
    return (f"🔴 Context Health {tag}: {p}/{n} · {cf} CRITICAL engine(s) "
            f"FAILED{crit_detail}")
