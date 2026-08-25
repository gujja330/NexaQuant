# backend/research/short_term_momentum_backtest.py
"""AEGIS · Sprint M · Short-Term Momentum Backtest.

CEO directive 2026-08-25: "make it more advanced. do back testing too".

Walk-forward evaluation of the short_term_momentum classifier:
  For every trading day in lookback window:
    · Compute momentum signals AS-OF that day (point-in-time · no lookahead)
    · Take the categorization + verdict from short_term_momentum
    · Read forward 1D / 3D / 5D / 10D / 20D returns
    · Aggregate per-verdict metrics

Answers:
  · Does POTENTIAL_ENTRY actually make money going forward?
  · Are PUMP_RISK signals reliable filters?
  · What's the hit rate + expectancy per verdict category?

Emits reports/research/short_term_momentum_backtest_{market}.json ·
Constitutional invariant · READ ONLY.
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.short_term_momentum_backtest.v1.20260825"

FORWARD_HORIZONS = [1, 3, 5, 10, 20]


@dataclass
class BacktestSample:
    ticker: str
    as_of: str
    category: str          # QUICK_RISE / QUICK_FALL / etc.
    verdict: str
    quality_band: str
    entry_close: float
    fwd_1d_pct: Optional[float] = None
    fwd_3d_pct: Optional[float] = None
    fwd_5d_pct: Optional[float] = None
    fwd_10d_pct: Optional[float] = None
    fwd_20d_pct: Optional[float] = None


@dataclass
class VerdictMetrics:
    verdict: str
    n_samples: int = 0
    win_rate_5d_pct: Optional[float] = None
    win_rate_20d_pct: Optional[float] = None
    avg_5d_pct: Optional[float] = None
    avg_20d_pct: Optional[float] = None
    median_5d_pct: Optional[float] = None
    median_20d_pct: Optional[float] = None
    profit_factor_20d: Optional[float] = None
    expectancy_20d_pct: Optional[float] = None
    confidence: str = "observation-only"


@dataclass
class MomentumBacktestReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    lookback_days: int = 60
    n_samples: int = 0
    per_verdict: list = field(default_factory=list)
    top_winners: list = field(default_factory=list)   # samples with best 20d P&L
    worst_losers: list = field(default_factory=list)
    finding: str = ""


def _dataframe(root: Path, ticker: str, market: str):
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
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        return df
    except Exception:
        return None


def _universe(root: Path, market: str) -> list:
    if market.lower() == "usa":
        pat = str(root / "usa" / "data" / "raw" / "us" / "*_D1.parquet")
    else:
        pat = str(root / "data" / "raw" / "india" / "*_D1.parquet")
    return sorted(Path(f).stem.replace("_D1","") for f in glob.glob(pat))


def _return_at_i(series, entry_i: int, n_days: int) -> Optional[float]:
    if entry_i + n_days >= len(series): return None
    e_p = float(series.iloc[entry_i])
    if e_p <= 0: return None
    fwd_p = float(series.iloc[entry_i + n_days])
    return round((fwd_p - e_p) / e_p * 100, 2)


def _confidence(n: int) -> str:
    if n < 20:  return "observation-only"
    if n < 50:  return "directional"
    if n < 100: return "research-candidate"
    return "production-candidate"


def _bt_per_verdict(samples: list, verdict: str) -> VerdictMetrics:
    items = [s for s in samples if s.verdict == verdict]
    n = len(items)
    if n == 0: return VerdictMetrics(verdict=verdict)
    def _wr(field_name):
        vals = [getattr(s, field_name) for s in items
                if getattr(s, field_name) is not None]
        if not vals: return None
        return round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1)
    def _avg(field_name):
        vals = [getattr(s, field_name) for s in items
                if getattr(s, field_name) is not None]
        if not vals: return None
        return round(sum(vals) / len(vals), 2)
    def _median(field_name):
        vals = sorted(getattr(s, field_name) for s in items
                      if getattr(s, field_name) is not None)
        if not vals: return None
        return round(vals[len(vals) // 2], 2)
    _wins_20 = [s.fwd_20d_pct for s in items
                if s.fwd_20d_pct is not None and s.fwd_20d_pct > 0]
    _loss_20 = [s.fwd_20d_pct for s in items
                if s.fwd_20d_pct is not None and s.fwd_20d_pct < 0]
    avg_w = sum(_wins_20) / max(len(_wins_20), 1) if _wins_20 else 0
    avg_l = sum(_loss_20) / max(len(_loss_20), 1) if _loss_20 else 0
    pf = round(abs(avg_w / avg_l), 2) if avg_l else 0.0
    wr20 = _wr("fwd_20d_pct")
    exp20 = None
    if wr20 is not None:
        exp20 = round((wr20 / 100) * avg_w + (1 - wr20 / 100) * avg_l, 2)
    return VerdictMetrics(
        verdict=verdict, n_samples=n,
        win_rate_5d_pct=_wr("fwd_5d_pct"),
        win_rate_20d_pct=wr20,
        avg_5d_pct=_avg("fwd_5d_pct"),
        avg_20d_pct=_avg("fwd_20d_pct"),
        median_5d_pct=_median("fwd_5d_pct"),
        median_20d_pct=_median("fwd_20d_pct"),
        profit_factor_20d=pf,
        expectancy_20d_pct=exp20,
        confidence=_confidence(n),
    )


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str,
            lookback_days: int = 60,
            universe_limit: Optional[int] = 50) -> MomentumBacktestReport:
    """Walk-forward evaluation of momentum classifier.
    universe_limit caps universe for speed · pass None for full."""
    from backend.research.short_term_momentum import (
        categorize, verdict_for, _vol_adjustment, THRESHOLDS,
    )
    universe = _universe(root, market)
    if universe_limit:
        universe = universe[:universe_limit]
    rep = MomentumBacktestReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        lookback_days=lookback_days,
    )
    samples: list = []
    import pandas as pd
    for tk in universe:
        df = _dataframe(root, tk, market)
        if df is None or len(df) < 100: continue
        col = "close" if "close" in df.columns else "Close"
        s = df[col].astype(float)
        # Sample every 3rd day in lookback window · reduce noise + speed
        n = len(s)
        eligible_range = range(max(30, n - lookback_days), n - 22, 3)
        for i in eligible_range:
            # As-of point-in-time · use only rows up to i
            window = s.iloc[:i+1]
            if len(window) < 30: continue
            # Point-in-time returns
            e_p = float(window.iloc[-1])
            def _ret_back(nd):
                if len(window) < nd + 1: return None
                p_back = float(window.iloc[-(nd + 1)])
                if p_back <= 0: return None
                return round((e_p - p_back) / p_back * 100, 2)
            r1 = _ret_back(1); r3 = _ret_back(3)
            r5 = _ret_back(5); r20 = _ret_back(20)
            # Vol adjustment
            try:
                rets = window.pct_change().tail(30)
                ann_vol = float(rets.std()) * (252 ** 0.5) * 100
            except Exception:
                ann_vol = None
            vol_adj = _vol_adjustment(ann_vol)
            cat = categorize(r1, r3, r5, r20, vol_adjust=vol_adj)
            if cat == "IGNORE": continue
            # Point-in-time quality band (approximate · use UNKNOWN in backtest)
            v, _ = verdict_for(cat, "UNKNOWN")
            # Forward returns
            fwd = {}
            for h in FORWARD_HORIZONS:
                fwd[f"fwd_{h}d_pct"] = _return_at_i(s, i, h)
            samples.append(BacktestSample(
                ticker=tk.upper(), as_of=s.index[i],
                category=cat, verdict=v,
                quality_band="UNKNOWN",
                entry_close=round(e_p, 2),
                **fwd,
            ))
    rep.n_samples = len(samples)
    # Per-verdict metrics
    for v in ("POTENTIAL_ENTRY", "REBOUND_WATCH", "MOMENTUM_WATCH",
              "PUMP_RISK", "AVOID", "IGNORE"):
        m = _bt_per_verdict(samples, v)
        if m.n_samples > 0:
            rep.per_verdict.append(asdict(m))
    # Top winners / worst losers
    with_20 = [s for s in samples if s.fwd_20d_pct is not None]
    with_20.sort(key=lambda s: -s.fwd_20d_pct)
    rep.top_winners = [asdict(s) for s in with_20[:15]]
    rep.worst_losers = [asdict(s) for s in with_20[-15:]]
    # Finding
    if rep.per_verdict:
        # Which verdict has highest expectancy?
        by_exp = sorted(rep.per_verdict,
                        key=lambda v: -(v.get("expectancy_20d_pct") or -999))
        best = by_exp[0]
        rep.finding = (
            f"best verdict: {best['verdict']} · "
            f"n={best['n_samples']} · "
            f"expectancy {best.get('expectancy_20d_pct')}% · "
            f"win rate {best.get('win_rate_20d_pct')}%")
    return rep


def emit(root: Path, rep: MomentumBacktestReport) -> Path:
    p = (root / "reports" / "research"
         / f"short_term_momentum_backtest_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: MomentumBacktestReport) -> str:
    return (f"momentum_backtest · {rep.n_samples} samples · "
            f"{len(rep.per_verdict)} verdict-groups · {rep.finding[:80]}")
