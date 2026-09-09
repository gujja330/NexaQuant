"""GATE 1 · DATA READY   and   GATE 2 · FEATURES READY.

    requested_asof = 2026-09-09
    feature_asof   = 2026-07-21
    -> BLOCK · no scoring · no lifecycle · no XLSX · no Telegram

THE RULE THIS EXISTS TO ENFORCE
--------------------------------
`list_snapshots()[-1]` returns the newest snapshot that EXISTS. It does
not return the snapshot for the day you asked about, and it cannot tell
you the difference. On 2026-09-09 it returned 2026-07-21, the full
universe was scored against seven-week-old features, and every downstream
guard truthfully reported that its own derived artifact was fresh.

A guard reading a DERIVED artifact can never see this. `ensemble.json` is
stamped today whether the features under it are one day old or fifty.
That is why freshness has to be a property of the LINEAGE, not of a file.

GOVERNED LAG, NOT SILENT LAG
-----------------------------
Some sources legitimately arrive late. Fundamentals under a 45-day
conservative PIT lag are fine; a price/feature snapshot used for today's
scoring is not. Each source declares its own budget, and anything outside
its budget blocks rather than being quietly accepted.

WHAT "COMPLETE" MEANS
---------------------
Not merely "a file exists". The universe that was expected must be the
universe that got featured, without unexplained shrinkage against the
previous run - because a snapshot covering 30 of 516 names looks perfectly
healthy to a file-existence check and produces a day with no candidates.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from backend.pipeline.contract.run_context import RunContext, StageContract

SCHEMA_VERSION = "aegis.pipeline.contract.readiness.v1"

STAGE_DATA = "DATA_READY"
STAGE_FEATURES = "FEATURES_READY"

# Per-source freshness budgets in CALENDAR days against requested_asof.
# A budget is a governed decision, not a tolerance for silent failure.
SOURCE_BUDGETS = {
    "feature_snapshot": 0,      # today's scoring needs today's features
    "price_bars": 4,            # weekends + a holiday
    "universe": 7,
    "fundamentals": 120,        # quarterly · PIT lag governs recency
    "corporate_actions": 7,
    "sector_metadata": 30,
    # ── MACRO / INTERMARKET · CEO 2026-09-09 ───────────────────────────
    #
    # These are not decoration. `regime` multiplies into the confidence
    # that gates entry, so a stale regime silently moves every threshold
    # in the book. On 2026-09-09 India's macro stack sat at 2026-09-03 -
    # six days old - while USA's was current, and India's
    # regime-adjusted confidence came out at 0.4643 against a 0.55 floor.
    # A market can legitimately produce no candidates; it must not do so
    # because last week's regime is still being applied.
    "macro_regime": 3,
    "market_intelligence": 3,
    "commodities": 4,           # Brent/WTI, gold/silver, metals
    "currencies": 4,            # DXY, USD/INR
    "bonds": 4,                 # yields
    "sector_rotation": 5,
    "fii_dii": 5,               # India flows · publishes on a lag
}

# artifact per market · (label, india path, usa path, blocking)
_MACRO_SOURCES = (
    ("macro_regime", "reports/macro_regime.json",
     "usa/reports/macro_regime.json", True),
    ("market_intelligence", "reports/market_intelligence_summary.json",
     "usa/reports/market_intelligence_summary.json", True),
    ("commodities", "reports/commodity_intelligence.json",
     "usa/reports/commodity_intelligence.json", False),
    ("currencies", "reports/currency_intelligence.json",
     "usa/reports/currency_intelligence.json", False),
    ("bonds", "reports/bond_intelligence.json",
     "usa/reports/bond_intelligence.json", False),
    ("sector_rotation", "reports/sector_rotation.json",
     "usa/reports/sector_rotation.json", False),
    ("fii_dii", "reports/fii_dii_flow.json", None, False),
)


def _artifact_asof(root: Path, rel: str):
    """The as-of an artifact CLAIMS · never its mtime.

    mtime says when a file was written, which a re-run refreshes even when
    the content is unchanged. Only the stamped as-of says what day the
    data describes.
    """
    import json
    p = Path(root) / rel
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    for k in ("asof", "as_of", "date", "reporting_date"):
        v = d.get(k)
        if v:
            return str(v)[:10]
    return None

# Below this share of the previous run's universe, the snapshot is treated
# as truncated rather than as a genuinely smaller market.
MIN_UNIVERSE_RETENTION_PCT = 90.0
MIN_FEATURE_COVERAGE_PCT = 95.0


def _age_days(asof: str, actual: Optional[str]) -> Optional[int]:
    if not actual:
        return None
    try:
        return (date.fromisoformat(str(asof)[:10])
                - date.fromisoformat(str(actual)[:10])).days
    except Exception:
        return None


def _feature_asof(root: Path, market: str) -> Optional[str]:
    try:
        from backend.feature_store.feature_history import list_snapshots
        s = list_snapshots(Path(root), market.lower())
        return s[-1].isoformat() if s else None
    except Exception:
        return None


def _snapshot_for(root: Path, market: str, asof: str):
    """The snapshot for THE REQUESTED DATE · never 'the latest one'."""
    try:
        from backend.feature_store.feature_history import (list_snapshots,
                                                           read_snapshot)
        want = date.fromisoformat(str(asof)[:10])
        if want not in set(list_snapshots(Path(root), market.lower())):
            return None
        return read_snapshot(Path(root), market.lower(), want)
    except Exception:
        return None


# Where each market actually declares its universe. A wrong path here
# silently yields size 0, which turns every coverage ratio into a
# division nobody can trust - the same class of defect as feature_store
# declaring the wrong artifact.
_UNIVERSE_FILES = {
    "usa": ("usa/reports/universe.json",),
    "india": ("reports/universe.json", "reports/context/universe_india.json",
              "india/reports/universe.json"),
}


def _universe_size(root: Path, market: str) -> Optional[int]:
    import json
    for rel in _UNIVERSE_FILES.get(market.lower(), ()):
        p = Path(root) / rel
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for k in ("tickers", "universe", "symbols", "members",
                  "active_universe"):
            v = d.get(k)
            if isinstance(v, list) and v:
                return len(v)
        for k in ("n_tickers", "count"):
            if isinstance(d.get(k), int) and d[k] > 0:
                return int(d[k])
    # Fall back to the feature snapshot's own breadth · better an honest
    # approximation than a silent zero.
    try:
        from backend.feature_store.feature_history import (list_snapshots,
                                                           read_snapshot)
        snaps = list_snapshots(Path(root), market.lower())
        if snaps:
            df = read_snapshot(Path(root), market.lower(), snaps[-1])
            if df is not None and len(df):
                col = next((c for c in ("ticker", "symbol", "Ticker")
                            if c in df.columns), None)
                if col:
                    return int(df[col].nunique())
    except Exception:
        pass
    return None


def _prev_feature_rows(root: Path, market: str, asof: str) -> Optional[int]:
    """Row count of the most recent snapshot BEFORE the requested one."""
    try:
        from backend.feature_store.feature_history import (list_snapshots,
                                                           read_snapshot)
        want = date.fromisoformat(str(asof)[:10])
        earlier = [d for d in list_snapshots(Path(root), market.lower())
                   if d < want]
        if not earlier:
            return None
        df = read_snapshot(Path(root), market.lower(), earlier[-1])
        return None if df is None else int(len(df))
    except Exception:
        return None


def check_data_ready(ctx: RunContext) -> StageContract:
    """GATE 1 · sources present and inside their governed budgets."""
    import time
    t0 = time.time()
    c = ctx.stage(STAGE_DATA)
    root, m, asof = Path(ctx.root), ctx.market, ctx.requested_asof

    sources = {}

    # ── the snapshot the whole run will be scored from ──────────────────
    fa = _feature_asof(root, m)
    fa_age = _age_days(asof, fa)
    sources["feature_snapshot"] = {"asof": fa, "age_days": fa_age,
                                   "budget_days": SOURCE_BUDGETS["feature_snapshot"]}

    # ── price bars · newest raw file mtime is the honest signal here ────
    bars_asof, n_bars = None, 0
    for rel in ("usa/data/raw/us", "data/raw/india", "india/data/raw"):
        p = root / rel
        if p.exists():
            fs = list(p.rglob("*.parquet"))
            n_bars = max(n_bars, len(fs))
            if fs:
                newest = max(f.stat().st_mtime for f in fs)
                bars_asof = date.fromtimestamp(newest).isoformat()
                break
    sources["price_bars"] = {"asof": bars_asof,
                             "age_days": _age_days(asof, bars_asof),
                             "budget_days": SOURCE_BUDGETS["price_bars"],
                             "n_files": n_bars}

    uni = _universe_size(root, m)
    sources["universe"] = {"size": uni}

    # ── macro / intermarket · the world the stock trades inside ────────
    for label, ind_rel, usa_rel, blocking in _MACRO_SOURCES:
        rel = usa_rel if m == "usa" else ind_rel
        if rel is None:
            continue                     # source does not apply to this market
        a_ = _artifact_asof(root, rel)
        sources[label] = {"asof": a_, "age_days": _age_days(asof, a_),
                          "budget_days": SOURCE_BUDGETS.get(label),
                          "path": rel, "blocking": blocking}

    c.detail["sources"] = sources
    c.source_timestamp = bars_asof
    c.expected_ticker_count = uni or 0

    # ── enforce ─────────────────────────────────────────────────────────
    for name, info in sources.items():
        budget = info.get("budget_days")
        if budget is None:
            continue
        a = info.get("asof")
        age = info.get("age_days")
        # A non-blocking source is recorded and warned about, never
        # silently accepted · but it does not stop a delivery on its own.
        _fail = (c.block if info.get("blocking", True)
                 else (lambda code, msg: c.detail.setdefault(
                     "warnings", []).append({"code": code, "message": msg})))
        if a is None:
            _fail("SOURCE_MISSING:%s" % name.upper(),
                  "%s has no resolvable as-of for %s" % (name, asof))
        elif age is None:
            _fail("SOURCE_ASOF_UNREADABLE:%s" % name.upper(),
                    "%s as-of %r could not be compared to %s"
                    % (name, a, asof))
        elif age > budget:
            _fail("SOURCE_STALE:%s" % name.upper(),
                    "%s is %d day(s) old (as-of %s, requested %s, budget %d)"
                    % (name, age, a, asof, budget))
        elif age < 0:
            _fail("SOURCE_FROM_THE_FUTURE:%s" % name.upper(),
                    "%s as-of %s is AFTER the requested %s" % (name, a, asof))

    c.elapsed_s = round(time.time() - t0, 2)
    return ctx.record(c.ok())


def check_features_ready(ctx: RunContext) -> StageContract:
    """GATE 2 · the snapshot for THIS as-of exists and is complete."""
    import time
    t0 = time.time()
    c = ctx.stage(STAGE_FEATURES)
    root, m, asof = Path(ctx.root), ctx.market, ctx.requested_asof

    why = ctx.upstream_ok(STAGE_DATA)
    if why:
        c.block("UPSTREAM_NOT_READY", why)
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    available = _feature_asof(root, m)
    c.output_asof = available
    c.detail["available_snapshot"] = available
    c.detail["requested_snapshot"] = asof

    # THE assertion. Not "is there a snapshot" · "is it THIS DAY'S".
    df = _snapshot_for(root, m, asof)
    if df is None:
        age = _age_days(asof, available)
        c.block("FEATURE_SNAPSHOT_ASOF_MISMATCH",
                "no feature snapshot for %s · newest available is %s (%s day(s) "
                "old) · refusing to score today against it"
                % (asof, available, age if age is not None else "?"))
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    c.row_count = int(len(df))
    tick_col = next((x for x in ("ticker", "symbol", "Ticker")
                     if x in df.columns), None)
    if tick_col:
        c.ticker_count = int(df[tick_col].nunique())
        c.duplicate_count = int(len(df) - c.ticker_count)

    exp = _universe_size(root, m) or 0
    c.expected_ticker_count = exp
    if exp and c.ticker_count:
        c.coverage_pct = round(c.ticker_count / exp * 100, 2)
        c.missing_count = max(0, exp - c.ticker_count)
        if c.coverage_pct < MIN_FEATURE_COVERAGE_PCT:
            c.block("FEATURE_COVERAGE_LOW",
                    "%d of %d universe names featured (%.1f%% · floor %.0f%%)"
                    % (c.ticker_count, exp, c.coverage_pct,
                       MIN_FEATURE_COVERAGE_PCT))

    if c.duplicate_count:
        c.block("FEATURE_DUPLICATE_ROWS",
                "%d duplicate ticker row(s) in the snapshot"
                % c.duplicate_count)

    # Unexplained shrinkage · 516 -> 30 looks healthy to a file check.
    prev = _prev_feature_rows(root, m, asof)
    if prev:
        retention = round(c.row_count / prev * 100, 1)
        c.detail["previous_rows"] = prev
        c.detail["retention_pct"] = retention
        if retention < MIN_UNIVERSE_RETENTION_PCT:
            c.block("FEATURE_UNIVERSE_SHRANK",
                    "snapshot has %d rows vs %d in the previous snapshot "
                    "(%.1f%% · floor %.0f%%) · a truncated snapshot produces "
                    "a day with no candidates and looks like a quiet market"
                    % (c.row_count, prev, retention,
                       MIN_UNIVERSE_RETENTION_PCT))

    try:
        from backend.feature_store import schema_fingerprint
        c.schema_fingerprint = schema_fingerprint()
    except Exception:
        pass

    c.elapsed_s = round(time.time() - t0, 2)
    return ctx.record(c.ok())
