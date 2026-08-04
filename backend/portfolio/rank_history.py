"""R006 · Phase 9a · Rank History Tracker.

Answers operator's 2026-08-04 concern: *"when TCS on august 3rd was rank 1 ?
todays shows in rank 9 ? how i can judge august 3rd vs 4th ?"* — before
this module, rank at a given asof was implicit only in whatever XLSX/JSON
snapshot existed at that moment. This module makes it explicit and queryable.

Append-only JSONL at `reports/research/rank_history.jsonl` with one row per
(asof, market, runner, ticker) capturing rank + confidence + model_score.
Queried by:
    · XLSX renderer (Prior Rank + Rank Δ columns)
    · Profit Protection Trigger #2 (RANK_COLLAPSE)
    · Monthly rank-stability rollup report

Never overwritten · never deleted · walk-forward compatible.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass
class RankSnapshot:
    ts_utc: str
    asof: str
    market: str
    runner: str
    ticker: str
    rank: int | None
    confidence: float | None
    model_score: float | None
    status: str | None = None


def _path(root: Path) -> Path:
    p = root / "reports" / "research" / "rank_history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_snapshot(root: Path, asof: str, market: str, runner: str,
                        ticker: str, rank: int | None,
                        confidence: float | None = None,
                        model_score: float | None = None,
                        status: str | None = None) -> None:
    snap = RankSnapshot(
        ts_utc=datetime.now(timezone.utc).isoformat(),
        asof=asof, market=market, runner=runner, ticker=ticker,
        rank=rank, confidence=confidence, model_score=model_score, status=status,
    )
    with _path(root).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(snap), default=str, ensure_ascii=False) + "\n")


def load_all(root: Path, market: str | None = None,
                runner: str | None = None,
                ticker: str | None = None,
                since_asof: str | None = None) -> list[dict]:
    p = _path(root)
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if market and d.get("market") != market: continue
        if runner and d.get("runner") != runner: continue
        if ticker and d.get("ticker") != ticker: continue
        if since_asof and (d.get("asof") or "") < since_asof: continue
        rows.append(d)
    return rows


def get_prior_rank(root: Path, market: str, runner: str, ticker: str,
                       before_asof: str) -> tuple[int | None, str | None]:
    """Return (prior_rank, prior_asof) for ticker · most recent snapshot
    with asof < before_asof · (None, None) if nothing found."""
    rows = load_all(root, market=market, runner=runner, ticker=ticker)
    rows = [r for r in rows if (r.get("asof") or "") < before_asof]
    if not rows:
        return None, None
    rows.sort(key=lambda r: r.get("asof") or "")
    latest = rows[-1]
    return latest.get("rank"), latest.get("asof")


def stamp_today(root: Path, asof: str, market: str, runner: str,
                    recs: list) -> int:
    """Bulk-append today's ranks from a rec list · returns count written.

    Idempotent per (asof, market, runner, ticker) via a dedup check on the
    most-recent existing snapshot: if today's snapshot for this ticker is
    ALREADY in the ledger, we skip · never duplicate. Safe to call multiple
    times per day."""
    existing = {(r["asof"], r["market"], r["runner"], r["ticker"])
                     for r in load_all(root, market=market, runner=runner)
                     if r.get("asof") == asof}
    n = 0
    for r in recs:
        t = r.get("ticker") or ""
        if not t: continue
        key = (asof, market, runner, t)
        if key in existing: continue
        ia = r.get("investor_action") or {}
        pa = str(r.get("percentile_action") or "").upper()
        status = None
        if str(ia.get("entry") or "").upper() == "BUY":
            status = "STRONG BUY" if pa == "STRONG_BUY" else "BUY"
        elif ia.get("if_holding") in ("EXIT", "REDUCE"):
            status = "EXIT"
        else:
            status = "HOLD"
        append_snapshot(root, asof, market, runner, t,
                              rank=r.get("rank"),
                              confidence=r.get("calibrated_confidence") or r.get("confidence"),
                              model_score=r.get("ensemble_score"),
                              status=status)
        n += 1
    return n
