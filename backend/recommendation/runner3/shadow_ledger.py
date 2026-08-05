"""Runner 3 · Shadow Ledger · append-only picks log.

Never merged with R006 portfolio_ledger (which is R2's). Every daily run
appends today's Runner 3 picks + entry-time state so we can replay
outcomes without touching production ledgers.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass
class ShadowEntry:
    ts_utc: str
    asof: str
    market: str
    ticker: str
    rank: int | None
    raw_score: float
    calibrated_confidence: float
    predicted_probability: float
    features_used: dict = field(default_factory=dict)
    entry_price: float | None = None
    horizon_days: int = 21
    stop_pct: float = 5.0
    target_1_pct: float = 8.0
    target_2_pct: float = 15.0


def _path(root: Path) -> Path:
    p = root / "reports" / "research" / "runner3" / "shadow_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append(root: Path, asof: str, market: str, ticker: str,
              rank: int | None, raw_score: float,
              calibrated_confidence: float, predicted_probability: float,
              features_used: dict | None = None,
              entry_price: float | None = None,
              horizon_days: int = 21,
              stop_pct: float = 5.0,
              target_1_pct: float = 8.0,
              target_2_pct: float = 15.0) -> ShadowEntry:
    e = ShadowEntry(
        ts_utc=datetime.now(timezone.utc).isoformat(),
        asof=asof, market=market, ticker=ticker, rank=rank,
        raw_score=raw_score, calibrated_confidence=calibrated_confidence,
        predicted_probability=predicted_probability,
        features_used=features_used or {},
        entry_price=entry_price, horizon_days=horizon_days,
        stop_pct=stop_pct, target_1_pct=target_1_pct, target_2_pct=target_2_pct,
    )
    with _path(root).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(e), default=str, ensure_ascii=False) + "\n")
    return e


def load_all(root: Path, market: str | None = None,
                since_asof: str | None = None) -> list[dict]:
    p = _path(root)
    if not p.exists(): return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        if market and d.get("market") != market: continue
        if since_asof and (d.get("asof") or "") < since_asof: continue
        rows.append(d)
    return rows


def count_distinct_asofs(root: Path, market: str) -> int:
    return len({r["asof"] for r in load_all(root, market=market)})


def picks_for_asof(root: Path, market: str, asof: str) -> list[dict]:
    return [r for r in load_all(root, market=market) if r.get("asof") == asof]
