"""Recommendation Backtrack Engine · per-ticker timeline across history.

Consumes:
  · reports/recommendations_history/{market}/YYYY-MM-DD.json  (snapshot store)
  · reports/position_store/{market}/history.jsonl              (position events)
  · reports/learning.parquet                                    (closed trades)

Produces per market:
  reports/backtrack/{market}/summary.json   — cross-ticker rollup
  reports/backtrack/{market}/{ticker}.json  — one file per active ticker

Timeline row schema (per snapshot day):
  { date, action, rank, score, confidence, price, allocation_pct,
    lifecycle_state, high_water_price, current_stop, days_recommended,
    delta_narrative }

The operator sees:
  29 Jun → 5 Jul → 12 Jul → Today
per stock — with the AI's decision evolution visible over time.

Article 101.2 · pure surface, zero new analytics.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from backend.recommendation.snapshot.store import (
    list_snapshot_dates, load_snapshot_for_date,
)
from backend.portfolio.position_store import load_all_positions

SCHEMA_FINGERPRINT = "aegis.analytics.backtrack.v1.20260729"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.analytics.backtrack.v1"


@dataclass
class TimelineRow:
    date: str
    action: str = "-"
    rank: int | None = None
    score: float | None = None
    confidence: float | None = None
    price: float | None = None
    allocation_pct: float | None = None
    lifecycle_state: str = "-"
    high_water_price: float | None = None
    current_stop: float | None = None
    days_recommended: int | None = None
    delta_narrative: str = ""


@dataclass
class TickerBacktrack:
    engine: str = ENGINE_ID
    schema_fingerprint: str = SCHEMA_FINGERPRINT
    market: str = ""
    ticker: str = ""
    first_seen_date: str = ""
    latest_date: str = ""
    n_appearances: int = 0
    entry_price: float | None = None
    latest_price: float | None = None
    high_water_price: float | None = None
    total_return_pct: float | None = None
    rank_change: int | None = None
    confidence_change: float | None = None
    lifecycle_transitions: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)


def _extract_rec_for_ticker(snapshot: Mapping, ticker: str) -> Mapping | None:
    if not snapshot:
        return None
    for r in snapshot.get("recommendations") or []:
        if str(r.get("ticker") or "") == ticker:
            return r
    return None


def _row_from_rec(d: date, rec: Mapping) -> TimelineRow:
    ia = rec.get("investor_action") or {}
    pp = rec.get("position_plan") or {}
    ez = pp.get("entry_zone") or {}
    ls = rec.get("lifecycle_state") or {}
    ev = rec.get("evolution") or {}
    action = ia.get("entry") or rec.get("percentile_action") or rec.get("action") or "-"
    return TimelineRow(
        date=d.isoformat(),
        action=str(action),
        rank=(rec.get("rank") if isinstance(rec.get("rank"), int) else None),
        score=(round(float(rec.get("ensemble_score")), 4)
                if rec.get("ensemble_score") is not None else None),
        confidence=(round(float(rec.get("calibrated_confidence")), 4)
                     if rec.get("calibrated_confidence") is not None else None),
        price=ez.get("current_price"),
        allocation_pct=pp.get("suggested_allocation_pct"),
        lifecycle_state=str(ls.get("current_state") or "-"),
        days_recommended=ev.get("days_recommended"),
        delta_narrative=ev.get("narrative") or "",
    )


def build_ticker_backtrack(reports_root: Path, market: str, ticker: str) -> TickerBacktrack:
    """Reconstruct the per-day timeline for a single ticker."""
    tb = TickerBacktrack(market=market, ticker=ticker)
    dates = list_snapshot_dates(reports_root, market)
    positions = load_all_positions(reports_root, market)
    pos_record = positions.get(ticker)

    if pos_record:
        tb.first_seen_date = pos_record.first_seen_date
        tb.entry_price = pos_record.first_seen_price
        tb.high_water_price = pos_record.high_water_price
        tb.latest_price = pos_record.last_seen_price
        if tb.entry_price and tb.entry_price > 0:
            tb.total_return_pct = round(
                (pos_record.last_seen_price / pos_record.first_seen_price - 1.0) * 100, 2
            )

    prev_row: TimelineRow | None = None
    prev_lc = None
    for d in dates:
        snap = load_snapshot_for_date(reports_root, market, d)
        rec = _extract_rec_for_ticker(snap, ticker)
        if not rec:
            continue
        row = _row_from_rec(d, rec)
        # Enrich with position-store state (real trailing stop, high water)
        if pos_record and row.date == pos_record.last_seen_date:
            row.high_water_price = pos_record.high_water_price
            row.current_stop = pos_record.current_stop
        tb.timeline.append(asdict(row))
        tb.n_appearances += 1
        if row.lifecycle_state != "-" and row.lifecycle_state != prev_lc:
            if prev_lc:
                tb.lifecycle_transitions.append(f"{prev_lc}→{row.lifecycle_state}")
            prev_lc = row.lifecycle_state
        if prev_row is not None:
            if prev_row.rank is not None and row.rank is not None:
                tb.rank_change = (prev_row.rank - row.rank) + (tb.rank_change or 0)
            if prev_row.confidence is not None and row.confidence is not None:
                tb.confidence_change = round(row.confidence - prev_row.confidence, 4)
        prev_row = row

    if tb.timeline:
        tb.latest_date = tb.timeline[-1]["date"]
    return tb


def build_market_backtrack(reports_root: Path, market: str,
                              tickers: Sequence[str] | None = None) -> dict:
    """Build backtracks for all tickers · returns rollup summary + per-ticker files."""
    positions = load_all_positions(reports_root, market)
    if tickers is None:
        # Backtrack the current active universe · plus any recently-active ticker
        tickers = sorted([t for t, p in positions.items()])

    out_dir = reports_root / "backtrack" / market
    out_dir.mkdir(parents=True, exist_ok=True)
    per_ticker: dict[str, TickerBacktrack] = {}
    for t in tickers:
        tb = build_ticker_backtrack(reports_root, market, t)
        if tb.n_appearances == 0:
            continue
        per_ticker[t] = tb
        (out_dir / f"{t}.json").write_text(
            json.dumps(asdict(tb), indent=2, default=str, ensure_ascii=False),
            encoding="utf-8"
        )

    # Rollup summary
    summary = {
        "engine":             ENGINE_ID,
        "schema_fingerprint": SCHEMA_FINGERPRINT,
        "market":             market,
        "run_utc":            datetime.now(timezone.utc).isoformat(),
        "n_tickers_tracked":  len(per_ticker),
        "snapshot_dates":     [d.isoformat() for d in list_snapshot_dates(reports_root, market)],
        "top_by_return": sorted(
            [{"ticker": t, "return_pct": tb.total_return_pct,
              "days": tb.n_appearances, "first_seen": tb.first_seen_date}
              for t, tb in per_ticker.items() if tb.total_return_pct is not None],
            key=lambda x: -(x["return_pct"] or 0)
        )[:10],
        "bottom_by_return": sorted(
            [{"ticker": t, "return_pct": tb.total_return_pct,
              "days": tb.n_appearances, "first_seen": tb.first_seen_date}
              for t, tb in per_ticker.items() if tb.total_return_pct is not None],
            key=lambda x: (x["return_pct"] or 0)
        )[:5],
        "longest_held": sorted(
            [{"ticker": t, "n_appearances": tb.n_appearances,
              "first_seen": tb.first_seen_date}
              for t, tb in per_ticker.items()],
            key=lambda x: -x["n_appearances"]
        )[:5],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8"
    )
    return summary


def journey_row_for_command_center(reports_root: Path, market: str,
                                        ticker: str) -> str:
    """One-line journey string for Command Center appendix."""
    tb = build_ticker_backtrack(reports_root, market, ticker)
    if tb.n_appearances == 0:
        return f"{ticker}: no history"
    ret = f"{tb.total_return_pct:+.2f}%" if tb.total_return_pct is not None else "-"
    tx = ",".join(tb.lifecycle_transitions[-3:]) or "-"
    return (f"{ticker}: {tb.first_seen_date}→today ({tb.n_appearances}d) · "
              f"ret {ret} · states {tx}")
