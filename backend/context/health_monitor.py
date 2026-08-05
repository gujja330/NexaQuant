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


# (relative_path, criticality, freshness_days, min_bytes)
# criticality: "CRITICAL" · "IMPORTANT" · "OPTIONAL"
# freshness_days: max age of the file (mtime) OR max age of asof-in-file · which is smaller
# min_bytes: file must be at least this big (skeleton files fail)

ENGINES = [
    # Existing engines (Waves 4-5) · ALL now CRITICAL per operator directive
    # "every report is a guard for our engines · ensure every engine works properly"
    ("reports/macro_regime.json",           "CRITICAL",  5, 400),
    ("reports/sector_rotation.json",        "CRITICAL",  5, 800),
    ("reports/volatility_intelligence.json", "CRITICAL",  5, 400),
    ("reports/bond_intelligence.json",       "CRITICAL",  5, 400),
    ("reports/currency_intelligence.json",   "CRITICAL",  5, 400),
    ("reports/commodity_intelligence.json",  "CRITICAL",  5, 400),
    ("reports/market_intelligence.json",     "CRITICAL",  5, 800),
    ("reports/ai_market_narrative.json",     "CRITICAL",  5, 400),
    ("reports/macro_history.parquet",        "IMPORTANT", 10, 1000),
    ("reports/factor_library.parquet",       "IMPORTANT", 10, 1000),
    # CIL layer engines (shipped 2026-08-05)
    ("reports/context/global_overnight.json", "CRITICAL",  1, 400),
    ("reports/context/market_breadth.json",   "CRITICAL",  1, 400),
    ("reports/context/economic_calendar.jsonl", "CRITICAL",  5, 400),
    ("reports/context/cil_run_india.json",    "CRITICAL",  1, 400),
    # R006 · Portfolio state (fires from R2 pipeline via ssot/run.py)
    ("reports/research/portfolio_snapshot_india.json", "IMPORTANT", 3, 200),
    ("reports/research/rank_history.jsonl",    "CRITICAL",  1, 100),
    # Sprint outputs
    ("reports/research/health_scores_india.json", "CRITICAL", 1, 400),
    # Newly-built context engines
    ("reports/fii_dii_flow.json",              "CRITICAL",  2, 200),
    ("reports/correlation_matrix.json",        "IMPORTANT", 5, 400),
    ("reports/ai_news_narrative.json",         "IMPORTANT", 3, 300),
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


def run_health_check(root: Path) -> dict:
    results = []
    for path, crit, days, min_b in ENGINES:
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

    return {
        "engine":        "aegis.context.health_monitor.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "overall_verdict": overall,
        "n_engines":     len(results),
        "n_pass":        sum(1 for r in results if r.verdict == "PASS"),
        "n_critical_fails": len(critical_fails),
        "n_important_fails": len(important_fails),
        "critical_fails":    [asdict(r) for r in critical_fails],
        "all_engines":       [asdict(r) for r in results],
        "recommendation": {
            "GREEN":  "All critical engines healthy · safe to send",
            "YELLOW": "Non-critical stale · notify operator in caption · allow send",
            "RED":    "Critical engine(s) missing/stale · block send unless "
                          "operator overrides with SEND_FORCE_STALE=1",
        }.get(overall, "unknown"),
    }


def emit(root: Path, payload: dict) -> Path:
    p = root / "reports" / "context" / "health_monitor.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p


def render_summary(payload: dict) -> str:
    """Compact one-liner for Telegram caption or CI log."""
    v = payload.get("overall_verdict", "?")
    n = payload.get("n_engines", 0)
    p = payload.get("n_pass", 0)
    cf = payload.get("n_critical_fails", 0)
    if v == "GREEN": return f"🟢 Context Health: {p}/{n} engines healthy"
    if v == "YELLOW": return f"🟡 Context Health: {p}/{n} · {cf} critical · {payload.get('n_important_fails', 0)} important stale"
    return f"🔴 Context Health: {p}/{n} · {cf} CRITICAL engine(s) FAILED · check reports/context/health_monitor.json"
