"""Per-ticker persistent position state · append-only · idempotent per date.

Storage layout:
    reports/position_store/{market}/positions.json         (current state)
    reports/position_store/{market}/history.jsonl          (append-only ledger)

`positions.json` is a dict {ticker: PositionRecord} — current state for
all tickers ever recommended. Written atomically on each update.

`history.jsonl` appends one line per (ticker, date, event) — full audit
trail for backtesting + Sector Attribution + Recommendation Journey.

PositionRecord fields:
    ticker                str
    first_seen_date       ISO date · never overwritten
    first_seen_price      float · never overwritten
    first_seen_score      float · never overwritten
    last_seen_date        ISO date · updated each run
    last_seen_price       float · latest recorded
    high_water_price      float · max of first_seen_price and all last_seen_prices
    low_water_price       float · min likewise
    entry_score           float · at first_seen
    current_score         float · latest
    n_appearances         int   · number of daily runs seen
    current_stop          float · trailing stop (never lowers when price rises)
    initial_stop          float · at first_seen
    target_price          float · latest target from rec (may update)
    lifecycle_state       str   · latest RecommendationState
    is_active             bool  · in most recent recs?
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA_FINGERPRINT = "aegis.portfolio.position_store.v1.20260729"
SCHEMA_VERSION = "1.0.0"
ENGINE_ID = "aegis.portfolio.position_store.v1"

# Default trailing-stop percentage. 6% matches the enricher's default
# stop_pct so trail activates only when price has risen enough to raise
# the stop above initial. Configurable per rec via ez.risk_per_share_pct.
TRAIL_PCT = 0.06


@dataclass
class PositionRecord:
    ticker: str
    first_seen_date: str
    first_seen_price: float
    first_seen_score: float
    last_seen_date: str = ""
    last_seen_price: float = 0.0
    high_water_price: float = 0.0
    low_water_price: float = 0.0
    entry_score: float = 0.0
    current_score: float = 0.0
    n_appearances: int = 0
    current_stop: float | None = None
    initial_stop: float | None = None
    target_price: float | None = None
    lifecycle_state: str = "DISCOVERED"
    is_active: bool = True


def _store_dir(reports_root: Path, market: str) -> Path:
    return reports_root / "position_store" / market


def _positions_path(reports_root: Path, market: str) -> Path:
    return _store_dir(reports_root, market) / "positions.json"


def _history_path(reports_root: Path, market: str) -> Path:
    return _store_dir(reports_root, market) / "history.jsonl"


def _atomic_write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def load_all_positions(reports_root: Path, market: str) -> dict[str, PositionRecord]:
    p = _positions_path(reports_root, market)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    positions = raw.get("positions") or {}
    out: dict[str, PositionRecord] = {}
    for t, rec in positions.items():
        try:
            out[t] = PositionRecord(**rec)
        except TypeError:
            # Forward-compat: ignore unknown fields
            filtered = {k: v for k, v in rec.items() if k in PositionRecord.__dataclass_fields__}
            out[t] = PositionRecord(**filtered)
    return out


def load_position(reports_root: Path, market: str,
                     ticker: str) -> PositionRecord | None:
    return load_all_positions(reports_root, market).get(ticker)


def _save_all_positions(reports_root: Path, market: str,
                            positions: Mapping[str, PositionRecord]) -> None:
    payload = {
        "engine":              ENGINE_ID,
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "market":              market,
        "written_utc":         datetime.now(timezone.utc).isoformat(),
        "n_positions":         len(positions),
        "positions":           {t: asdict(r) for t, r in positions.items()},
    }
    _atomic_write(_positions_path(reports_root, market),
                    json.dumps(payload, indent=2, default=str, ensure_ascii=False))


def _append_history(reports_root: Path, market: str, event: dict) -> None:
    p = _history_path(reports_root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")


def upsert_position(reports_root: Path,
                       market: str,
                       ticker: str,
                       asof: str,
                       current_price: float,
                       current_score: float,
                       target_price: float | None = None,
                       initial_stop: float | None = None,
                       lifecycle_state: str = "DISCOVERED",
                       trail_pct: float = TRAIL_PCT) -> PositionRecord:
    """Insert new position or update existing one. Idempotent per (ticker, asof).

    Never overwrites first_seen_* fields. Updates high_water/low_water/
    current_stop atomically. Emits a history event.
    """
    positions = load_all_positions(reports_root, market)
    rec = positions.get(ticker)
    now_utc = datetime.now(timezone.utc).isoformat()
    event_type: str

    if rec is None:
        rec = PositionRecord(
            ticker=ticker,
            first_seen_date=asof,
            first_seen_price=float(current_price),
            first_seen_score=float(current_score),
            last_seen_date=asof,
            last_seen_price=float(current_price),
            high_water_price=float(current_price),
            low_water_price=float(current_price),
            entry_score=float(current_score),
            current_score=float(current_score),
            n_appearances=1,
            initial_stop=(float(initial_stop) if initial_stop is not None else None),
            current_stop=(float(initial_stop) if initial_stop is not None else None),
            target_price=(float(target_price) if target_price is not None else None),
            lifecycle_state=lifecycle_state,
            is_active=True,
        )
        event_type = "OPENED"
    else:
        # Idempotent: if we already recorded this ticker for this asof, do nothing new.
        if rec.last_seen_date == asof:
            return rec
        rec.last_seen_date = asof
        rec.last_seen_price = float(current_price)
        rec.current_score = float(current_score)
        rec.n_appearances += 1
        if float(current_price) > rec.high_water_price:
            rec.high_water_price = float(current_price)
        if float(current_price) < rec.low_water_price:
            rec.low_water_price = float(current_price)
        # Trailing stop: raise (never lower) as high_water rises.
        new_stop_from_hw = rec.high_water_price * (1.0 - trail_pct)
        if rec.current_stop is None:
            rec.current_stop = new_stop_from_hw
        elif new_stop_from_hw > rec.current_stop:
            rec.current_stop = new_stop_from_hw
        if target_price is not None:
            rec.target_price = float(target_price)
        rec.lifecycle_state = lifecycle_state
        rec.is_active = True
        event_type = "UPDATED"

    positions[ticker] = rec
    _save_all_positions(reports_root, market, positions)
    _append_history(reports_root, market, {
        "ts_utc":          now_utc,
        "asof":            asof,
        "ticker":          ticker,
        "event":           event_type,
        "price":           float(current_price),
        "score":           float(current_score),
        "high_water":      rec.high_water_price,
        "current_stop":    rec.current_stop,
        "n_appearances":   rec.n_appearances,
        "lifecycle_state": lifecycle_state,
    })
    return rec


def update_from_recs(reports_root: Path,
                        market: str,
                        recs: Sequence[Mapping],
                        asof: str,
                        trail_pct: float = TRAIL_PCT) -> dict[str, PositionRecord]:
    """Bulk-update the store from today's enriched recommendations list.

    Marks tickers not in today's recs as `is_active = False` (dropped from
    the top-N) but preserves their record for backtrack/history.

    Reads from each rec:
      · entry_zone.current_price → current_price
      · ensemble_score            → current_score
      · position_plan.entry_zone.target_1 → target_price
      · position_plan.entry_zone.stop_loss → initial_stop (only on OPEN)
      · lifecycle_state.current_state → lifecycle
    """
    active_tickers: set[str] = set()
    for r in recs:
        ticker = str(r.get("ticker") or "").strip()
        if not ticker:
            continue
        active_tickers.add(ticker)
        pp = r.get("position_plan") or {}
        ez = pp.get("entry_zone") or {}
        cp = ez.get("current_price")
        if cp is None:
            # Fall back to any raw price field on the rec
            cp = r.get("current_price") or r.get("price")
        if cp is None:
            continue
        upsert_position(
            reports_root=reports_root,
            market=market,
            ticker=ticker,
            asof=asof,
            current_price=float(cp),
            current_score=float(r.get("ensemble_score") or 0.0),
            target_price=ez.get("target_1"),
            initial_stop=ez.get("stop_loss"),
            lifecycle_state=(r.get("lifecycle_state") or {}).get("current_state") or "DISCOVERED",
            trail_pct=trail_pct,
        )

    # Mark stale tickers inactive (in store but not in today's recs)
    positions = load_all_positions(reports_root, market)
    changed = False
    for t, rec in positions.items():
        if t not in active_tickers and rec.is_active:
            rec.is_active = False
            positions[t] = rec
            changed = True
            _append_history(reports_root, market, {
                "ts_utc":     datetime.now(timezone.utc).isoformat(),
                "asof":       asof,
                "ticker":     t,
                "event":      "DROPPED_FROM_TOP_N",
                "n_appearances": rec.n_appearances,
                "days_tracked": _days_between(rec.first_seen_date, asof),
            })
    if changed:
        _save_all_positions(reports_root, market, positions)
    return positions


def _days_between(start: str, end: str) -> int:
    try:
        s = date.fromisoformat(str(start)[:10])
        e = date.fromisoformat(str(end)[:10])
        return max(0, (e - s).days)
    except (ValueError, TypeError):
        return 0


def compute_days_recommended(reports_root: Path, market: str,
                                 ticker: str, asof: str) -> int:
    """Days since first_seen for a ticker · used by enricher.evolution."""
    rec = load_position(reports_root, market, ticker)
    if rec is None:
        return 1
    return max(1, _days_between(rec.first_seen_date, asof) + 1)
