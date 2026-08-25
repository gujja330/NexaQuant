# backend/research/win_discovery.py
"""AEGIS · Missed Winners Scanner · universe-wide walk-back.

CEO directive 2026-08-25: "we can try on history data to see if we have
missed any winning stocks".

For every ticker in the universe:
  1. Compute its 30-day return from parquet closes
  2. If return >= threshold (default 8%) it's a "winner"
  3. Cross-check: did our Registry ever recommend it during that window?
     · YES · we caught it (log as CAUGHT)
     · NO  · we MISSED it (log as MISSED + emit why-plausible-reason)

Emits reports/research/missed_winners_{market}.json ranked by return
desc so operator sees the biggest opportunity gaps first · plus a
sector breakdown of what we systematically miss.

This is the TRUE test of the recommendation engine: not just how well
our picks perform, but how much of the tradeable alpha we CAPTURE from
the investable universe.
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.win_discovery.v1.20260825"


@dataclass
class UniverseWinner:
    ticker: str
    market: str
    return_pct: float
    lookback_days: int
    start_price: float
    end_price: float
    sector: str
    caught: bool
    why_missed: str = ""       # brief reason if not caught


@dataclass
class DiscoveryReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    lookback_days: int = 30
    winner_threshold_pct: float = 8.0
    n_universe: int = 0
    n_winners: int = 0
    n_caught: int = 0
    n_missed: int = 0
    capture_rate_pct: float = 0.0    # caught / winners
    total_missed_return_pct: float = 0.0
    top_missed: list = field(default_factory=list)     # sorted desc
    caught: list = field(default_factory=list)
    sector_gap: list = field(default_factory=list)     # {sector, n_missed, avg_missed_ret}


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


def _sector_for(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / "sector_cache.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        bucket = d.get(market.lower(), {})
        return bucket.get(ticker.upper()) or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _universe_tickers(root: Path, market: str) -> list:
    if market.lower() == "usa":
        pat = str(root / "usa" / "data" / "raw" / "us" / "*_D1.parquet")
    else:
        pat = str(root / "data" / "raw" / "india" / "*_D1.parquet")
    files = glob.glob(pat)
    return sorted(Path(f).stem.replace("_D1", "") for f in files)


def _return_over_last(series, days: int):
    """Return over last N business days (based on parquet index length)."""
    if series is None or len(series) < days + 1:
        return None, None, None
    end_p = float(series.iloc[-1])
    start_p = float(series.iloc[-(days + 1)])
    if not (start_p and start_p > 0): return None, None, None
    return round((end_p - start_p) / start_p * 100, 2), start_p, end_p


def _was_recommended(root: Path, ticker: str, market: str,
                     since: str) -> bool:
    """Was this ticker in the Registry (any status) after `since`?"""
    try:
        from backend.research import opportunity_registry as _oreg
        reg = _oreg.load_all(root)
        for opps in reg.values():
            for o in opps:
                if o.market.lower() != market.lower(): continue
                if o.ticker.upper() != ticker.upper(): continue
                if str(o.created_date or "") >= since:
                    return True
        return False
    except Exception:
        return False


def _why_plausibly_missed(root: Path, ticker: str, market: str) -> str:
    """Best-effort reason we might have missed this winner."""
    # 1. Quality band from investability
    p_iv = root / "reports" / f"investability_{market.lower()}.json"
    if p_iv.exists():
        try:
            d = json.loads(p_iv.read_text(encoding="utf-8"))
            for r in (d.get("results") or []):
                if str(r.get("ticker") or "").upper() == ticker.upper():
                    _v = str(r.get("verdict") or "").upper()
                    if "AVOID" in _v:
                        return f"blocked by quality gate: {r.get('verdict', '')}"
                    if "MARGINAL" in _v:
                        return f"below quality threshold: {r.get('verdict', '')}"
                    _sc = r.get("score")
                    if isinstance(_sc, (int, float)) and _sc < 55:
                        return f"score {_sc:.1f} below quality bar"
                    return "was on watchlist but not surfaced as top pick"
        except Exception:
            pass
    return "not in current investability sample"


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str,
            lookback_days: int = 30,
            winner_threshold_pct: float = 8.0) -> DiscoveryReport:
    universe = _universe_tickers(root, market)
    rep = DiscoveryReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        lookback_days=lookback_days,
        winner_threshold_pct=winner_threshold_pct,
    )
    rep.n_universe = len(universe)
    since = (date.today() - timedelta(days=lookback_days)).isoformat()
    winners_all: list = []
    for tk in universe:
        s = _series(root, tk, market)
        if s is None: continue
        ret, start_p, end_p = _return_over_last(s, lookback_days)
        if ret is None or ret < winner_threshold_pct: continue
        caught = _was_recommended(root, tk, market, since)
        _sec = _sector_for(root, tk, market)
        _why = "" if caught else _why_plausibly_missed(root, tk, market)
        winners_all.append(UniverseWinner(
            ticker=tk.upper(), market=market.lower(),
            return_pct=ret, lookback_days=lookback_days,
            start_price=round(start_p, 2), end_price=round(end_p, 2),
            sector=_sec, caught=caught, why_missed=_why,
        ))
    winners_all.sort(key=lambda w: -w.return_pct)
    rep.n_winners = len(winners_all)
    rep.n_caught = sum(1 for w in winners_all if w.caught)
    rep.n_missed = rep.n_winners - rep.n_caught
    rep.capture_rate_pct = round(
        rep.n_caught / max(rep.n_winners, 1) * 100, 1)
    missed = [w for w in winners_all if not w.caught]
    rep.total_missed_return_pct = round(sum(w.return_pct for w in missed), 2)
    rep.top_missed = [asdict(w) for w in missed[:30]]
    rep.caught = [asdict(w) for w in winners_all if w.caught][:30]
    # Sector gap analysis
    from collections import defaultdict
    by_sec: dict = defaultdict(list)
    for w in missed:
        by_sec[w.sector].append(w)
    for sec, items in sorted(by_sec.items(),
                             key=lambda x: -len(x[1])):
        rep.sector_gap.append({
            "sector": sec,
            "n_missed": len(items),
            "total_missed_return_pct": round(sum(x.return_pct for x in items), 2),
            "avg_missed_return_pct": round(
                sum(x.return_pct for x in items) / max(len(items), 1), 2),
            "top_ticker": items[0].ticker,
            "top_return_pct": items[0].return_pct,
        })
    return rep


def emit(root: Path, report: DiscoveryReport) -> Path:
    p = (root / "reports" / "research"
         / f"missed_winners_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: DiscoveryReport) -> str:
    return (f"missed_winners · {rep.lookback_days}d ≥ "
            f"{rep.winner_threshold_pct}% · "
            f"{rep.n_winners} in universe · caught {rep.n_caught} "
            f"({rep.capture_rate_pct}%) · missed {rep.n_missed}")
