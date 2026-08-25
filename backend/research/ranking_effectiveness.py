# backend/research/ranking_effectiveness.py
"""AEGIS · Sprint M.1 · Ranking Effectiveness Study (CEO Part 8 / M.1).

CEO directive 2026-08-25: "Rank 10 can sometimes outperform Rank 1 · we
need to stop debating this manually. Produce per-rank 1D/3D/5D/10D/20D
returns · monotonicity test".

For each rank bucket 1-10, walks Registry entries that had that rank
at entry (from rank_history if available · else uses runner-level rank
field on the opportunity if present). Reads parquet for forward returns
at 1D/3D/5D/10D/20D. Aggregates per-rank metrics + tests monotonicity.

Never modifies R1/R2. Constitutional invariant · research only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.ranking_effectiveness.v1.20260825"

FORWARD_HORIZONS = [1, 3, 5, 10, 20]
RANK_BUCKETS = list(range(1, 11))     # ranks 1-10


@dataclass
class RankBucketMetrics:
    rank: int
    n: int
    fwd_1d_avg: Optional[float] = None
    fwd_3d_avg: Optional[float] = None
    fwd_5d_avg: Optional[float] = None
    fwd_10d_avg: Optional[float] = None
    fwd_20d_avg: Optional[float] = None
    win_rate_20d_pct: Optional[float] = None
    profit_factor_20d: Optional[float] = None
    expectancy_20d_pct: Optional[float] = None
    max_dd_pct: Optional[float] = None
    confidence: str = "observation-only"


@dataclass
class RankingReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_positions: int = 0
    per_rank: list = field(default_factory=list)
    monotonicity_test: dict = field(default_factory=dict)
    finding: str = ""


def _series(root: Path, ticker: str, market: str):
    if market.lower() == "usa":
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "usa" / "data" / "raw" / "us" / f"{tk}_D1.parquet"
    else:
        tk = str(ticker).upper().replace(".NS","").replace(".BO","")
        p = root / "data" / "raw" / "india" / f"{tk}_D1.parquet"
    if not p.exists(): return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df[col].astype(float)
    except Exception:
        return None


def _forward_return(series, entry_date: str, days: int) -> Optional[float]:
    if series is None: return None
    idx = list(series.index)
    after = [d for d in idx if d >= entry_date]
    if not after: return None
    entry_i = idx.index(after[0])
    if entry_i + days >= len(idx): return None
    e_p = float(series.iloc[entry_i])
    fwd_p = float(series.iloc[entry_i + days])
    if e_p <= 0: return None
    return round((fwd_p - e_p) / e_p * 100, 2)


def _load_rank_history(root: Path, market: str) -> list:
    """Read rank_history JSONL if present · else empty list."""
    p = (root / "reports" / "research"
         / f"rank_history_{market.lower()}.jsonl")
    if not p.exists():
        p = root / "reports" / "research" / "rank_history.jsonl"
    if not p.exists():
        return []
    try:
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                d = json.loads(line)
                out.append(d)
            except Exception:
                continue
        return out
    except Exception:
        return []


def _confidence(n: int) -> str:
    if n < 20: return "observation-only"
    if n < 50: return "directional"
    if n < 100: return "research-candidate"
    return "production-candidate"


def _bucket_metrics(rank: int, entries: list, root: Path, market: str) -> RankBucketMetrics:
    """entries is list of (ticker, date) for this rank bucket."""
    if not entries:
        return RankBucketMetrics(rank=rank, n=0)
    per_horizon = {h: [] for h in FORWARD_HORIZONS}
    for tk, dt in entries:
        s = _series(root, tk, market)
        if s is None: continue
        for h in FORWARD_HORIZONS:
            r = _forward_return(s, dt, h)
            if r is not None:
                per_horizon[h].append(r)
    def _avg(vals): return round(sum(vals) / len(vals), 2) if vals else None
    wins_20 = [v for v in per_horizon[20] if v > 0]
    losses_20 = [v for v in per_horizon[20] if v < 0]
    all_20 = per_horizon[20]
    n = len(all_20)
    avg_w = sum(wins_20) / len(wins_20) if wins_20 else 0
    avg_l = sum(losses_20) / len(losses_20) if losses_20 else 0
    pf = round(abs(avg_w / avg_l), 2) if avg_l else 0.0
    wr = round(len(wins_20) / n * 100, 1) if n else None
    exp = None
    if wr is not None:
        exp = round((wr / 100) * avg_w + (1 - wr / 100) * avg_l, 2)
    max_dd = round(min(all_20), 2) if all_20 else None
    return RankBucketMetrics(
        rank=rank, n=n,
        fwd_1d_avg=_avg(per_horizon[1]),
        fwd_3d_avg=_avg(per_horizon[3]),
        fwd_5d_avg=_avg(per_horizon[5]),
        fwd_10d_avg=_avg(per_horizon[10]),
        fwd_20d_avg=_avg(per_horizon[20]),
        win_rate_20d_pct=wr,
        profit_factor_20d=pf,
        expectancy_20d_pct=exp,
        max_dd_pct=max_dd,
        confidence=_confidence(n),
    )


def _monotonicity_test(per_rank: list) -> dict:
    """Test whether Rank 1 > 2 > 3 ... on 20d return."""
    ranked = [b for b in per_rank
              if b.get("n", 0) >= 5 and b.get("fwd_20d_avg") is not None]
    if len(ranked) < 3:
        return {"status": "insufficient-data",
                "detail": "need ≥ 3 rank buckets with N ≥ 5"}
    # ranks sorted by rank asc
    ranked.sort(key=lambda x: x["rank"])
    returns = [b["fwd_20d_avg"] for b in ranked]
    # Monotonic if strictly decreasing (Rank 1 highest)
    n_inversions = 0
    for i in range(len(returns) - 1):
        if returns[i] < returns[i + 1]:
            n_inversions += 1
    best_rank = max(ranked, key=lambda x: x["fwd_20d_avg"])["rank"]
    worst_rank = min(ranked, key=lambda x: x["fwd_20d_avg"])["rank"]
    return {
        "status": "MONOTONIC" if n_inversions == 0 else "NON_MONOTONIC",
        "n_inversions": n_inversions,
        "best_rank_by_20d": best_rank,
        "worst_rank_by_20d": worst_rank,
        "detail": (f"Rank {best_rank} produced best 20d avg · "
                   f"Rank {worst_rank} worst · {n_inversions} inversions"),
    }


def compute(root: Path, market: str, lookback_days: int = 90) -> RankingReport:
    """Build per-rank forward-return study from rank_history + Registry."""
    hist = _load_rank_history(root, market)
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    # Group by rank bucket
    by_rank: dict = {r: [] for r in RANK_BUCKETS}
    n_pos = 0
    for h in hist:
        if str(h.get("market", "")).lower() != market.lower(): continue
        _dt = str(h.get("asof") or h.get("date") or "")[:10]
        if _dt < cutoff: continue
        _rank = h.get("rank")
        _tk = h.get("ticker")
        if not (_tk and isinstance(_rank, int) and 1 <= _rank <= 10): continue
        by_rank[_rank].append((_tk, _dt))
        n_pos += 1
    rep = RankingReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        n_positions=n_pos,
    )
    for r in RANK_BUCKETS:
        m = _bucket_metrics(r, by_rank[r], root, market)
        rep.per_rank.append(asdict(m))
    rep.monotonicity_test = _monotonicity_test(rep.per_rank)
    rep.finding = rep.monotonicity_test.get("detail", "")
    return rep


def emit(root: Path, rep: RankingReport) -> Path:
    p = (root / "reports" / "research"
         / f"ranking_effectiveness_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: RankingReport) -> str:
    return (f"ranking_effectiveness · {rep.n_positions} observations · "
            f"{rep.monotonicity_test.get('status','?')} · "
            f"{rep.finding[:80]}")
