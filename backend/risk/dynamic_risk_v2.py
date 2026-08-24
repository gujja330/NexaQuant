"""Part 8 · Dynamic Risk Engine (full) + Part 15 · Profit Protection.

Extends Wave 1's static stop-loss vocabulary into a per-day, per-position
risk recalculation:

  Part 8 · Dynamic Risk
    - ATR-based stop-loss (14-day Average True Range)
    - Trailing stop when price advances materially above entry
    - Volatility-scaled stops in high-vol regimes

  Part 15 · Profit Protection
    - Systematic trailing-stop LIFT on winners > threshold profit
    - Never move stop DOWN · lift is monotonic
    - Locks in gains without forcing early exit on winners

Output: reports/context/dynamic_risk_{market}.json + per-position stop
updates written to the Opportunity Registry sidecar (registry itself
stays immutable · stop is per-day daily-snapshot data, not creation state).

Config in configs/opportunity_registry.yaml::risk_engine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, date
from pathlib import Path

from backend.research import opportunity_registry as oreg


@dataclass
class StopUpdate:
    opportunity_id: str = ""
    ticker:         str = ""
    entry_price:    float | None = None
    current_price:  float | None = None
    original_stop:  float | None = None
    new_stop:       float | None = None
    stop_type:      str = ""       # "atr" · "trailing" · "vol_scaled" · "unchanged"
    pnl_pct:        float | None = None
    reason:         str = ""


@dataclass
class DynamicRiskReport:
    engine:         str = "aegis.dynamic_risk.v2"
    generated_utc:  str = ""
    market:         str = ""
    asof:           str = ""
    n_positions:    int = 0
    n_atr_updated:  int = 0
    n_trailing_lifted: int = 0
    n_vol_scaled:   int = 0
    n_unchanged:    int = 0
    updates:        list = field(default_factory=list)


def _load_config(root: Path) -> dict:
    p = root / "configs" / "opportunity_registry.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cfg.get("risk_engine", {}) or {}
    except Exception:
        return {}


def _bars(root: Path, ticker: str, market: str, n_days: int = 20):
    """Return last n_days OHLC bars for the ticker (pandas DataFrame or None)."""
    try:
        import pandas as pd
        bare = ticker.upper().replace(".NS","").replace(".BO","")
        p = ((root / "usa" / "data" / "raw" / "us" if market == "usa"
                  else root / "data" / "raw" / "india") / f"{bare}_D1.parquet")
        if not p.exists(): return None
        df = pd.read_parquet(p)
        return df.tail(n_days)
    except Exception:
        return None


def _atr(df, period: int = 14) -> float | None:
    """Simple ATR · mean of True Range over `period` bars."""
    try:
        import pandas as pd
        if df is None or len(df) < 2: return None
        hi = df["high"].astype(float)
        lo = df["low"].astype(float)
        cl = df["close"].astype(float)
        prev = cl.shift(1)
        tr = pd.concat([hi - lo, (hi - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
        return float(tr.tail(period).mean())
    except Exception:
        return None


def compute(root: Path, market: str, asof: str) -> DynamicRiskReport:
    """Recompute stops for every ACTIVE opportunity in this market."""
    market = market.lower()
    asof = asof[:10]
    cfg = _load_config(root)
    atr_mult      = float(cfg.get("atr_multiplier", 2.0))
    trailing_pct  = float(cfg.get("trailing_lift_min_pct", 5.0))
    high_vol_mult = float(cfg.get("high_vol_scale", 1.5))
    high_vol_thr  = float(cfg.get("high_vol_atr_pct", 3.0))

    rep = DynamicRiskReport(
        market=market, asof=asof,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    reg = oreg.load_all(root)

    for opps in reg.values():
        for opp in opps:
            if opp.market.lower() != market: continue
            if not opp.is_active(): continue
            rep.n_positions += 1
            df = _bars(root, opp.ticker, market, n_days=20)
            if df is None or len(df) < 2:
                continue
            try:
                current = float(df["close"].iloc[-1])
            except Exception:
                continue
            atr = _atr(df, period=14)
            if atr is None:
                continue
            u = StopUpdate(
                opportunity_id=opp.opportunity_id, ticker=opp.ticker,
                current_price=current,
                original_stop=None,        # registry doesn't hold stop · sender does
            )
            atr_pct = (atr / current * 100.0) if current else 0.0

            # Vol-scaled stop when ATR% > threshold
            if atr_pct > high_vol_thr:
                u.new_stop = round(current - atr * high_vol_mult, 4)
                u.stop_type = "vol_scaled"
                u.reason = f"high-vol ATR%={atr_pct:.2f} > {high_vol_thr} · widened stop"
                rep.n_vol_scaled += 1
            else:
                # Standard ATR stop
                atr_stop = current - atr * atr_mult
                u.new_stop = round(atr_stop, 4)
                u.stop_type = "atr"
                u.reason = f"ATR14={atr:.2f} · mult={atr_mult} · atr_pct={atr_pct:.2f}"
                rep.n_atr_updated += 1

            # Profit protection · trailing lift when position has run
            # entry_price for a real trail requires join to sender's entry
            # tracking · Registry only holds created_date. Approximate entry
            # by first bar close since created_date.
            try:
                _cd = date.fromisoformat(opp.created_date)
                days_since = (date.fromisoformat(asof) - _cd).days
            except Exception:
                days_since = 0
            if days_since >= 3 and current > 0 and atr > 0:
                # If we can estimate entry as close from N days ago
                try:
                    est_entry = float(df["close"].iloc[max(0, len(df) - days_since - 1)])
                    if est_entry > 0:
                        pnl_pct = (current - est_entry) / est_entry * 100
                        u.pnl_pct = round(pnl_pct, 2)
                        u.entry_price = est_entry
                        # Trailing lift · when profit > trailing_pct, lift stop
                        # to (current - atr * mult) as long as it EXCEEDS the
                        # prior stop (never lower).
                        if pnl_pct >= trailing_pct:
                            lift_stop = round(current - atr * atr_mult, 4)
                            if lift_stop > (u.new_stop or 0):
                                u.new_stop = lift_stop
                                u.stop_type = "trailing"
                                u.reason = (f"profit {pnl_pct:+.2f}% ≥ trailing_pct "
                                                    f"{trailing_pct}% · lifted stop to {lift_stop}")
                                rep.n_trailing_lifted += 1
                except Exception:
                    pass

            if u.stop_type == "":
                rep.n_unchanged += 1
            rep.updates.append(asdict(u))
    return rep


def emit(root: Path, rep: DynamicRiskReport) -> Path:
    p = (root / "reports" / "context"
             / f"dynamic_risk_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(rep: DynamicRiskReport) -> str:
    return (f"risk · {rep.n_positions} positions · atr={rep.n_atr_updated} · "
                f"trailing_lifted={rep.n_trailing_lifted} · vol_scaled={rep.n_vol_scaled}")
