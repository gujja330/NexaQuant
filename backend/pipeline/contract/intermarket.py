"""INTERMARKET COMPLETENESS · the world the stock trades inside.

> "first make sure AEGIS reliably collects the complete world around the
>  stock every morning/evening; then let R3 research determine which parts
>  of that world actually improve prediction."

WHY THIS IS A FRESHNESS DOMAIN AND NOTHING MORE
------------------------------------------------
Sprint 6.5 already built macro/intermarket collection - commodities, FX,
bonds, volatility, sector rotation, regime. None of that is removed here.
What this module adds is the same standing prices and fundamentals have:
a named, per-series freshness contract that is checked BEFORE the model
scores anything.

The reason is concrete. `regime` multiplies into the confidence that gates
entry, so a stale regime silently moves every threshold in the book. On
2026-09-09 India's macro stack sat six days old while USA's was current,
and India's regime-adjusted confidence came out at 0.4643 against a 0.55
floor. A market may legitimately produce no candidates; it must not do so
because last week's regime is still being applied.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
------------------------------------------
It does not feed a single one of these series into R2. Collecting a
variable is not evidence that it predicts anything, and wiring fourteen
fresh series into the scorer because they are available is exactly how an
overfitting mess gets built.

The cross-market transmission chain

    US market -> USD/INR -> global risk -> commodity
              -> Indian sector -> Indian stock

remains D17, evidence-BLOCKED: descriptive relationship, then lead/lag,
then stock/sector conditional, then OOS, then multiple-testing
correction, then incremental value over R2, then R3 shadow - and only
then a promotion conversation. This module is the first link of that
chain, not a shortcut past it.

MISSING IS REPORTED, NEVER IMPUTED
-----------------------------------
A series that is absent is named as absent. Silver and the India sector
indices are not collected today; saying so is more useful than a
completeness score that quietly counts only what happens to exist.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from backend.pipeline.contract.run_context import RunContext, StageContract

SCHEMA_VERSION = "aegis.pipeline.contract.intermarket.v1"

STAGE = "INTERMARKET"

# label -> (kind, india source, usa source, budget days, critical)
#   kind "bar"  · a parquet whose last row date is the as-of
#   kind "json" · an artifact whose stamped asof is the as-of
SERIES = (
    ("S&P 500",        "bar",  "data/raw/india/global/SPX.parquet",
     "usa/data/raw/us/_IDX_GSPC_D1.parquet", 4, True),
    ("NASDAQ",         "bar",  None,
     "usa/data/raw/us/_IDX_NDX_D1.parquet", 4, False),
    ("Dow",            "bar",  None,
     "usa/data/raw/us/_IDX_DJI_D1.parquet", 4, False),
    ("VIX",            "bar",  "data/raw/india/global/USVIX.parquet",
     "usa/data/raw/us/_IDX_VIX_D1.parquet", 4, True),
    ("DXY",            "bar",  "data/raw/india/global/DXY.parquet", None, 4, True),
    ("USD/INR",        "bar",  "data/raw/india/global/USDINR.parquet", None, 4, True),
    ("US 10Y",         "bar",  "data/raw/india/global/US10Y.parquet", None, 4, True),
    ("Oil (Brent/WTI)", "bar", "data/raw/india/global/OIL.parquet", None, 4, True),
    ("Gold",           "bar",  "data/raw/india/global/GOLD.parquet", None, 4, False),
    ("India VIX",      "bar",  "data/raw/india/INDIAVIX_D1.parquet", None, 4, True),
    ("Nifty Bank",     "bar",  "data/raw/india/NSEBANK_D1.parquet", None, 4, False),
    # JSON intelligence artifacts · the derived layer over those series
    ("Commodities",    "json", "reports/commodity_intelligence.json",
     "usa/reports/commodity_intelligence.json", 4, False),
    ("Currencies",     "json", "reports/currency_intelligence.json",
     "usa/reports/currency_intelligence.json", 4, False),
    ("Bonds / yields", "json", "reports/bond_intelligence.json",
     "usa/reports/bond_intelligence.json", 4, False),
    ("Sector rotation", "json", "reports/sector_rotation.json",
     "usa/reports/sector_rotation.json", 5, False),
    ("Macro regime",   "json", "reports/macro_regime.json",
     "usa/reports/macro_regime.json", 3, True),
    ("FII / DII",      "json", "reports/fii_dii_flow.json", None, 5, False),
)

# Series the CEO named that AEGIS does not collect today. Named here so
# the report says "not collected" rather than silently scoring 100%.
NOT_COLLECTED = {
    "both": {"Silver": "no series on disk · would need a spot/ETF feed"},
    "india": {"India sector indices":
              "only Nifty Bank is collected · the remaining NSE sector "
              "indices are not"},
    "usa": {},
}


def _not_collected(market: str) -> dict:
    out = dict(NOT_COLLECTED["both"])
    out.update(NOT_COLLECTED.get(market.lower(), {}))
    return out


def _bar_asof(root: Path, rel: str) -> Optional[str]:
    """Last row date in a bar file · what the series actually covers."""
    p = Path(root) / rel
    if not p.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        if df is None or df.empty:
            return None
        for col in ("date", "Date", "asof", "timestamp"):
            if col in df.columns:
                return str(pd.to_datetime(df[col]).max().date())
        if df.index.name or len(df.index):
            return str(pd.to_datetime(df.index).max().date())
    except Exception:
        return None
    return None


def _json_asof(root: Path, rel: str) -> Optional[str]:
    import json
    p = Path(root) / rel
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    for k in ("asof", "as_of", "date", "reporting_date"):
        if d.get(k):
            return str(d[k])[:10]
    return None


def survey(root: Path, market: str, asof: str) -> dict:
    m = market.lower()
    rows, missing, stale = [], [], []
    for label, kind, ind, usa, budget, critical in SERIES:
        rel = usa if m == "usa" else ind
        if rel is None:
            continue                     # series does not apply to this market
        a = _bar_asof(root, rel) if kind == "bar" else _json_asof(root, rel)
        age = None
        if a:
            try:
                age = (date.fromisoformat(str(asof)[:10])
                       - date.fromisoformat(str(a)[:10])).days
            except Exception:
                age = None
        verdict = ("MISSING" if a is None else
                   "UNREADABLE" if age is None else
                   "STALE" if age > budget else "FRESH")
        rows.append({"series": label, "kind": kind, "path": rel, "asof": a,
                     "age_days": age, "budget_days": budget,
                     "critical": critical, "verdict": verdict})
        if verdict == "MISSING" and critical:
            missing.append(label)
        elif verdict == "STALE" and critical:
            stale.append("%s (%dd)" % (label, age))
    n_fresh = sum(1 for r in rows if r["verdict"] == "FRESH")
    return {
        "market": m, "asof": asof, "n_series": len(rows), "n_fresh": n_fresh,
        "completeness_pct": round(n_fresh / max(1, len(rows)) * 100, 1),
        "series": rows,
        "critical_missing": missing,
        "critical_stale": stale,
        "not_collected": _not_collected(m),
        "feeds_scoring": False,
        "note": ("collection and freshness only · none of these series is "
                 "fed to R2 · cross-market transmission remains D17 "
                 "evidence-BLOCKED until it earns OOS and incremental value"),
    }


def check_intermarket(ctx: RunContext) -> StageContract:
    import time
    t0 = time.time()
    c = ctx.stage(STAGE)
    root, m, asof = Path(ctx.root), ctx.market, ctx.requested_asof

    why = ctx.upstream_ok("DATA_READY")
    if why:
        c.block("UPSTREAM_NOT_READY", why)
        c.elapsed_s = round(time.time() - t0, 2)
        return ctx.record(c)

    s = survey(root, m, asof)
    c.detail.update({k: s[k] for k in
                     ("n_series", "n_fresh", "completeness_pct",
                      "critical_missing", "critical_stale", "not_collected")})
    c.detail["series"] = s["series"]
    c.row_count = s["n_series"]

    if s["critical_missing"]:
        c.block("INTERMARKET_SERIES_MISSING",
                "critical context series absent: %s · the model would score "
                "a stock without knowing the world it trades inside"
                % ", ".join(s["critical_missing"]))
    if s["critical_stale"]:
        c.block("INTERMARKET_SERIES_STALE",
                "critical context series stale: %s · regime multiplies into "
                "the confidence that gates entry, so a stale regime moves "
                "every threshold silently" % ", ".join(s["critical_stale"]))

    c.elapsed_s = round(time.time() - t0, 2)
    return ctx.record(c.ok())


def render(s: dict) -> str:
    """The MACRO / INTERMARKET block of the certification."""
    L = ["MACRO / INTERMARKET"]
    for r in s["series"]:
        mark = {"FRESH": "✓", "STALE": "⚠", "MISSING": "✗",
                "UNREADABLE": "?"}.get(r["verdict"], "?")
        crit = " (critical)" if r["critical"] else ""
        L.append("  %-18s %-12s %s%s" % (r["series"], r["asof"] or "—",
                                         mark, crit))
    for k, why in sorted(s["not_collected"].items()):
        L.append("  %-18s %-12s ✗ not collected · %s" % (k, "—", why))
    L.append("  INTERMARKET COMPLETENESS: %s  (%d/%d fresh · %.0f%%)"
             % ("PASS" if not (s["critical_missing"] or s["critical_stale"])
                else "FAIL", s["n_fresh"], s["n_series"],
                s["completeness_pct"]))
    return "\n".join(L)
