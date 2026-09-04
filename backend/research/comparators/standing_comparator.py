"""P5.5 · Standing Post-R1 Fixed Comparator.

Equal-weight top-10 by 3-month momentum · monthly rebalance · NO TUNING EVER.
Its entire value is being a fixed yardstick. Never modified without CEO auth.

Governance:
  · Comparator is NOT a candidate · it's a fixed baseline
  · Never enters production R2 · never touches R2 ensemble weights
  · Feeds three_way_comparator.py as the third leg (candidate vs R2 vs THIS)
  · AUDIT-02 unblocked by this file existing (no P5.5-as-candidate scope change)

Output · reports/research/comparators/standing_{market}.json (daily · append-only)
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# LOCKED per V2 §P5.5 · never override without CEO authorization
TOP_N = 10
MOMENTUM_LOOKBACK_DAYS = 63       # ~3 trading months
REBALANCE_INTERVAL_DAYS = 21      # monthly


@dataclass
class ComparatorPick:
    ticker: str
    momentum_3m_pct: float
    weight: float                  # equal · 1/N

    def to_dict(self) -> dict:
        return asdict(self)


def _load_price_close(root: Path, market: str, ticker: str, asof: str) -> Optional[float]:
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        asof_ts = pd.Timestamp(asof)
        before = df[df.index <= asof_ts]
        if before.empty: return None
        return float(before.iloc[-1]["close"])
    except Exception:
        return None


def _price_n_days_before(root: Path, market: str, ticker: str, asof: str,
                           n: int) -> Optional[float]:
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        asof_ts = pd.Timestamp(asof)
        before = df[df.index <= asof_ts]
        if len(before) < n + 1: return None
        return float(before.iloc[-(n+1)]["close"])
    except Exception:
        return None


def _universe(root: Path, market: str) -> list[str]:
    """Load the current live universe · same source as production."""
    import json as _j
    if market.lower() == "usa":
        p = root / "usa" / "reports" / "universe.json"
    else:
        p = root / "reports" / "india_universe.json"
    if not p.exists(): return []
    try:
        d = _j.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, list):
            return [str(t.get("symbol") if isinstance(t, dict) else t).upper() for t in d if t]
        if isinstance(d, dict):
            for k in ("tickers", "constituents", "members"):
                if k in d and isinstance(d[k], list):
                    return [str(t.get("symbol") if isinstance(t, dict) else t).upper()
                            for t in d[k] if t]
    except Exception: pass
    return []


def compute_picks(root: Path, market: str, asof: Optional[str] = None) -> list[ComparatorPick]:
    """Compute the standing comparator's top-N by 3-month momentum · asof today by default."""
    asof = asof or date.today().isoformat()
    universe = _universe(root, market)
    if not universe: return []
    scored = []
    for t in universe:
        base = str(t).upper().replace(".NS", "").replace(".BO", "")
        p_now = _load_price_close(root, market, base, asof)
        p_3m = _price_n_days_before(root, market, base, asof, MOMENTUM_LOOKBACK_DAYS)
        if p_now is None or p_3m is None or p_3m <= 0: continue
        mom = (p_now / p_3m - 1.0) * 100.0
        scored.append((base, mom))
    scored.sort(key=lambda x: -x[1])
    top = scored[:TOP_N]
    weight = 1.0 / len(top) if top else 0.0
    return [ComparatorPick(ticker=t, momentum_3m_pct=round(m, 4), weight=round(weight, 6))
            for t, m in top]


def _last_run_asof(root: Path, market: str) -> Optional[str]:
    """Return last emit date for rebalance-cadence check · None if never run."""
    p = root / "reports" / "research" / "comparators" / f"standing_{market}.jsonl"
    if not p.exists(): return None
    try:
        last_line = p.read_text(encoding="utf-8").strip().splitlines()[-1]
        return json.loads(last_line).get("asof")
    except Exception:
        return None


def _days_since(from_iso: Optional[str], to_iso: str) -> int:
    if not from_iso: return 10**9
    try:
        return (date.fromisoformat(to_iso) - date.fromisoformat(from_iso)).days
    except Exception:
        return 10**9


def emit_daily_observation(root: Path, market: str, asof: Optional[str] = None) -> dict:
    """Emit today's observation · rebalance only every REBALANCE_INTERVAL_DAYS."""
    asof = asof or date.today().isoformat()
    out_dir = root / "reports" / "research" / "comparators"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_p = out_dir / f"standing_{market}.jsonl"

    last_asof = _last_run_asof(root, market)
    days_since = _days_since(last_asof, asof)
    rebalance = (last_asof is None) or (days_since >= REBALANCE_INTERVAL_DAYS)

    if rebalance:
        picks = compute_picks(root, market, asof)
        observation = {
            "asof": asof,
            "market": market,
            "rebalance": True,
            "days_since_last_rebalance": days_since if last_asof else None,
            "top_n": TOP_N,
            "picks": [p.to_dict() for p in picks],
            "governance": "V2 §P5.5 · FIXED comparator · no tuning · never modified without CEO auth",
            "logged_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    else:
        # Hold last basket · rebalance not due
        observation = {
            "asof": asof,
            "market": market,
            "rebalance": False,
            "days_since_last_rebalance": days_since,
            "days_until_next_rebalance": REBALANCE_INTERVAL_DAYS - days_since,
            "governance": "V2 §P5.5 · holding · monthly cadence",
            "logged_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    # Append (immutable)
    with open(ledger_p, "a", encoding="utf-8") as f:
        f.write(json.dumps(observation, default=str) + "\n")
    return observation


def load_ledger(root: Path, market: str) -> list[dict]:
    p = root / "reports" / "research" / "comparators" / f"standing_{market}.jsonl"
    if not p.exists(): return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out
